FROM python:3.11-slim
WORKDIR /app
COPY predictor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY predictor/ .
COPY python/cppulse/ /opt/cppulse/python/cppulse/
ENV PYTHONPATH=/opt/cppulse/python
RUN chmod +x /app/docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["--input", "/output", "--output", "/output"]
