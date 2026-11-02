FROM python:3.11-slim
WORKDIR /app
COPY ml_service/requirements-service.txt /app/requirements-service.txt
RUN pip install --no-cache-dir -r requirements-service.txt
COPY ml /app/ml
COPY ml_service /app/ml_service
ENV PYTHONPATH=/app ML_SERVICE_PORT=8001
EXPOSE 8001
CMD ["sh","-c","uvicorn ml_service.main:app --host 0.0.0.0 --port ${ML_SERVICE_PORT:-8001}"]
