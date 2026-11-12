FROM python:3.12-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir ruff==0.17.5 splunk-appinspect==4.4.0 splunk-packaging-toolkit==1.2.8
WORKDIR /workspace
