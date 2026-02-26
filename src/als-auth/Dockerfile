FROM python:3.12-slim

LABEL maintainer="ITEGA — Newshare Network"
LABEL service="als-auth"

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ALS keys should be mounted at runtime
VOLUME /etc/als/keys

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
