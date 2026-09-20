# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# curl is only needed for the Docker healthcheck below
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# credentials/ and logs/ are provided at runtime via the bind mount in
# docker-compose.yml, not baked into the image — see .dockerignore
RUN mkdir -p credentials logs

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:8502/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "streamlit_app.py", \
    "--server.port=8502", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]