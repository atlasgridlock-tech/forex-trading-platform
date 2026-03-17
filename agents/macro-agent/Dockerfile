FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    httpx \
    feedparser \
    redis \
    pydantic

# Copy application
COPY app.py /app/
COPY fundamentals.py /app/
COPY workspace /app/workspace/

# Create memory directory
RUN mkdir -p /app/workspace/memory

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
