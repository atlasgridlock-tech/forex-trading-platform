FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /app/
COPY validation_framework.py /app/
COPY adaptive_learning.py /app/
COPY workspace /app/workspace/

RUN mkdir -p /app/workspace/versions /app/workspace/requests

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
