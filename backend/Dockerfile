FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN mkdir -p /app/db /app/models
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY data ./data
COPY ml ./ml
COPY eval ./eval
RUN python ml/augment.py && python ml/train_triage.py
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
