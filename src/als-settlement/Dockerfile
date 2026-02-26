FROM python:3.12-slim

LABEL maintainer="ITEGA — Newshare Network"
LABEL service="als-settlement"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Reports are written here; mount a volume in production
VOLUME /app/reports

# No CMD — this is a batch job, not a long-running service.
# Run via: docker run als-settlement python settle.py --period=weekly
ENTRYPOINT ["python", "settle.py"]
