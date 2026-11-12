FROM python:3.12-slim
RUN pip install --no-cache-dir delta-sharing==1.3.3
ENTRYPOINT ["python", "/consume.py"]
