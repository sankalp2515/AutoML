FROM python:3.11-slim

RUN useradd -m -u 1001 sandbox

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN chown -R sandbox:sandbox /app
# Note: run as root so the container can write to the mounted /data volume

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
