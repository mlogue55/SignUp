FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data persists in a volume mounted at /data
ENV DATA_FILE=/data/data.json

EXPOSE 5000

CMD ["python", "app.py"]
