"""Recognise a gym machine from one photo with zero-shot classification.

Model: CLIP ViT-B/32 (OpenAI, open weights). CLIP was trained on 400 million
image + caption pairs to put a picture and the text that describes it close
together in the same number space (an "embedding").

Zero-shot means we never train on gym photos. Instead:

1. We write a few short descriptions for every machine ("a photo of a leg press machine").
2. CLIP turns each description into a vector. We do this once and save it.
3. CLIP turns the user's photo into a vector.
4. The machine whose text vector points in the most similar direction wins.

Adding a new machine is one new entry in catalog.json. No training is needed.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

# Any CLIP or SigLIP model from the Hugging Face Hub works. The default was chosen by measuring
# several models on the same photos (see docs/06-test-report.md). Override it with an environment
# variable to try another one:  set GFC_IMAGE_TEXT_MODEL=openai/clip-vit-base-patch32
MODEL_NAME = os.environ.get("GFC_IMAGE_TEXT_MODEL", "google/siglip-base-patch16-224")
IS_SIGLIP = "siglip" in MODEL_NAME.lower()
CACHE = Path(__file__).resolve().parents[2] / "models" / "text_embeddings.npz"
TEMPLATES = ["a photo of a {}.", "a {} in a gym.", "a photo of gym equipment: {}.",
             "a person using a {}.", "a person exercising on a {}."]
OTHER = "not_gym"
MIN_CONFIDENCE = 0.30  # below this we ask the user to choose from the list instead


class MachineRecognizer:
    def __init__(self, catalog: dict):
        self.machines = catalog["machines"]
        self.not_gym_labels = catalog["not_gym_labels"]
        self.status = "not loaded"
        self.error: str | None = None
        self._lock = threading.Lock()
        self._model = self._processor = self._text = None
        self._ids = [m["id"] for m in self.machines] + [OTHER]

    # ---- loading ------------------------------------------------------------------
    def load_in_background(self) -> None:
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self) -> None:
        with self._lock:
            if self.status == "ready":
                return
            self.status = "loading"
            try:
                import torch
                from transformers import AutoModel, AutoProcessor
                try:  # use the copy already on disk; only go online the first time
                    self._model = AutoModel.from_pretrained(MODEL_NAME, local_files_only=True)
                    self._processor = AutoProcessor.from_pretrained(MODEL_NAME, local_files_only=True)
                except Exception:
                    self._model = AutoModel.from_pretrained(MODEL_NAME)
                    self._processor = AutoProcessor.from_pretrained(MODEL_NAME)
                self._model.eval()
                self._torch = torch
                self._text = self._text_embeddings()
                self.status = "ready"
            except Exception as e:
                self.status, self.error = "error", str(e)

    def _prompts(self) -> list[list[str]]:
        groups = [[t.format(label) for label in m["labels"] for t in TEMPLATES] for m in self.machines]
        groups.append([f"a photo of {label}." for label in self.not_gym_labels])
        return groups

    def _embed_text(self, prompts: list[str]):
        """Unit-length vectors for a list of sentences. CLIP and SigLIP need slightly different calls."""
        if IS_SIGLIP:
            tokens = self._processor(text=prompts, return_tensors="pt", padding="max_length", max_length=64, truncation=True)
            emb = self._model.text_model(input_ids=tokens["input_ids"]).pooler_output
        else:
            tokens = self._processor(text=prompts, return_tensors="pt", padding=True, truncation=True)
            out = self._model.text_model(input_ids=tokens["input_ids"], attention_mask=tokens["attention_mask"])
            emb = self._model.text_projection(out.pooler_output)
        return emb / emb.norm(dim=-1, keepdim=True)

    def _text_embeddings(self) -> np.ndarray:
        """One averaged, unit-length text vector per class. Cached on disk."""
        groups = self._prompts()
        key = hashlib.sha256(json.dumps([MODEL_NAME, groups]).encode()).hexdigest()
        if CACHE.exists():
            saved = np.load(CACHE)
            if str(saved["key"]) == key:
                return saved["text"]
        rows = []
        with self._torch.no_grad():
            for prompts in groups:
                emb = self._embed_text(prompts)
                mean = emb.mean(dim=0)
                rows.append((mean / mean.norm()).numpy())
        text = np.stack(rows)
        np.savez(CACHE, key=key, text=text)
        return text

    # ---- inference ----------------------------------------------------------------
    def probabilities(self, image: Image.Image) -> np.ndarray:
        """Probability for every machine class plus the final "not gym equipment" class."""
        if self.status != "ready":
            self._load()
        if self.status != "ready":
            raise RuntimeError(f"Machine recogniser is not available: {self.error}")
        image = ImageOps.exif_transpose(image).convert("RGB")  # phone photos carry a rotation tag
        with self._torch.no_grad():
            pixels = self._processor(images=image, return_tensors="pt")["pixel_values"]
            emb = self._model.vision_model(pixel_values=pixels).pooler_output
            if not IS_SIGLIP:  # CLIP adds one more linear layer; SigLIP's output is already final
                emb = self._model.visual_projection(emb)
            emb = (emb / emb.norm(dim=-1, keepdim=True)).numpy()[0]
            scale = float(self._model.logit_scale.exp())
        logits = scale * (self._text @ emb)
        p = np.exp(logits - logits.max())
        return p / p.sum()

    def identify(self, image: Image.Image, top: int = 3) -> dict:
        p = self.probabilities(image)
        order = np.argsort(-p)
        best = int(order[0])
        candidates = [
            {"machine_id": self._ids[i], "name": self.machines[i]["name"], "confidence": round(float(p[i]), 3)}
            for i in order if self._ids[i] != OTHER
        ][:top]
        recognized = self._ids[best] != OTHER and float(p[best]) >= MIN_CONFIDENCE
        return {"recognized": recognized, "candidates": candidates,
                "not_gym_probability": round(float(p[-1]), 3)}
