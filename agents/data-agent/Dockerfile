FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    httpx \
    feedparser \
    redis \
    pydantic \
    psycopg2-binary \
    pandas

# Copy application
COPY app.py /app/
COPY timescale_store.py /app/
COPY workspace /app/workspace/

# Create memory directory
RUN mkdir -p /app/workspace/memory

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
