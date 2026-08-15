FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose HTTP API & Web Dashboard (8000), SMTP (25 / 2525), IMAP (1143 / 143)
EXPOSE 8000 2525 1143

CMD ["python", "app/main.py"]
