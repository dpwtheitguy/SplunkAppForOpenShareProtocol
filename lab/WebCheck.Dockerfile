FROM mcr.microsoft.com/playwright/python:v1.56.0-noble
RUN pip install --no-cache-dir playwright==1.56.0
COPY web_check.py /web_check.py
ENTRYPOINT ["python", "/web_check.py"]
