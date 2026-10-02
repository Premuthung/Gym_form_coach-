"""Compare open image-text models on the curated gym photos (zero-shot).

This is the experiment behind the model choice in docs/03-models-and-techniques.md.
Run:  python training/compare_image_text_models.py openai/clip-vit-base-patch32 openai/clip-vit-base-patch16 google/siglip-base-patch16-224
Each model is downloaded on first use (0.6-0.8 GB each).
"""
import sys, json, csv, time, numpy as np, torch, psutil
from PIL import Image
from transformers import AutoModel, AutoProcessor
cat = json.load(open("backend/app/catalog.json", encoding="utf-8"))
rows = list(csv.DictReader(open("data/eval_machines/curated.csv")))
ids = [x["id"] for x in cat["machines"]]; y = np.array([ids.index(r["label"]) for r in rows])
T = ["a photo of a {}.", "a {} in a gym.", "a photo of gym equipment: {}.", "a person using a {}.", "a person exercising on a {}."]
groups = [[t.format(l) for l in x["labels"] for t in T] for x in cat["machines"]]
for name in sys.argv[1:]:
    try:
        t0=time.time(); m = AutoModel.from_pretrained(name).eval(); p = AutoProcessor.from_pretrained(name); load=time.time()-t0
        siglip = "siglip" in name.lower()
        def norm(e): return (e/e.norm(dim=-1,keepdim=True))
        def img(path):
            px = p(images=Image.open(path).convert("RGB"), return_tensors="pt")["pixel_values"]
            o = m.vision_model(pixel_values=px).pooler_output
            return norm(o if siglip else m.visual_projection(o)).numpy()[0]
        def txt(g):
            tk = p(text=g, return_tensors="pt", padding="max_length" if siglip else True, truncation=True, **({"max_length":64} if siglip else {}))
            kw = {"input_ids": tk["input_ids"]}
            if not siglip: kw["attention_mask"] = tk["attention_mask"]
            o = m.text_model(**kw).pooler_output
            e = norm(o if siglip else m.text_projection(o)); mean = e.mean(0); return (mean/mean.norm()).numpy()
        with torch.no_grad():
            t0=time.time(); I = np.stack([img("data/eval_machines/"+r["file"]) for r in rows]); per_img=(time.time()-t0)/len(rows)
            Tx = np.stack([txt(g) for g in groups])
        S = I @ Tx.T; order = np.argsort(-S, axis=1)
        top1 = (order[:,0]==y).mean(); top3 = (order[:,:3]==y[:,None]).any(1).mean()
        per = {ids[c]: f"{(order[y==c,0]==c).sum()}/{(y==c).sum()}" for c in np.unique(y)}
        print(f"\n## {name}: top1 {top1:.3f} top3 {top3:.3f} | load {load:.0f}s, {per_img:.2f}s/image, RSS {psutil.Process().memory_info().rss/1e6:.0f}MB\n   {per}", flush=True)
        del m, p
    except Exception as e:
        print(f"\n## {name}: FAILED {type(e).__name__}: {str(e)[:300]}", flush=True)
