FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/app/hf_cache

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Bake the model into the image so the app starts fast
RUN python -c "from transformers import AutoTokenizer, AutoModelForSeq2SeqLM; AutoTokenizer.from_pretrained('banwaa/generator-mcq'); AutoModelForSeq2SeqLM.from_pretrained('banwaa/generator-mcq')"

COPY app.py db.py scoring.py ./
COPY assets ./assets
COPY model ./model

EXPOSE 7860
CMD ["python", "app.py"]