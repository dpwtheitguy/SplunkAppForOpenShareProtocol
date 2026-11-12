FROM python:3.13-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py ocsf.py .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "9000", "--no-access-log", "--no-proxy-headers"]
