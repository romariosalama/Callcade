# Callcade in a container
#   docker build -t callcade .
#   docker run -p 8000:8000 --env-file .env -v callcade-data:/data callcade
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend backend
COPY frontend frontend

# keep the database in a volume so it survives restarts
ENV CALLCADE_DB=/data/callcade.db
RUN mkdir -p /data

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
