FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
COPY git-miner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY git-miner/ .
COPY python/cppulse/ /opt/cppulse/python/cppulse/
ENV PYTHONPATH=/opt/cppulse/python
CMD ["python3", "-m", "src.main"]
