FROM python:3.12-slim

WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY app.py .
COPY assets ./assets

EXPOSE 7860

CMD ["python", "app.py"]