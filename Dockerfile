# Gym Form Coach as one container: the web page and the models together.
# Built for a Hugging Face Space (Docker type), and works on any host that runs a container.
#   docker build -t gym-form-coach .
#   docker run -p 7860:7860 gym-form-coach        then open http://localhost:7860
FROM python:3.12-slim

# System libraries that OpenCV and MediaPipe load (graphics libraries, used even without a screen).
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libegl1 libgles2 \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces run the container as user 1000, so everything the app writes must belong to it.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# The extra index gives the CPU build of torch (about 200 MB instead of 2 GB with GPU libraries).
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --timeout 120 --retries 10 --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# Download the machine recogniser now (0.8 GB), so the page is ready as soon as the container starts.
# A slow connection can drop the download; each new try continues where the last one stopped.
RUN for attempt in 1 2 3 4 5 6; do \
      python -c "from transformers import AutoModel, AutoProcessor; n = 'google/siglip-base-patch16-224'; AutoModel.from_pretrained(n); AutoProcessor.from_pretrained(n)" \
      && exit 0; sleep 5; \
    done; exit 1

COPY --chown=user backend backend
COPY --chown=user frontend frontend
COPY --chown=user models models
RUN mkdir -p data

EXPOSE 7860
CMD ["sh", "-c", "exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-7860}"]
