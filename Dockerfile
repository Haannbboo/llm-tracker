FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/
COPY frontend/dist/ frontend/dist/
COPY config.example.yaml VERSION ./

# Create directories for runtime
RUN mkdir -p /root/.llm-tracker/logs

# Copy entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy supervisord config
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf

EXPOSE 4000 4001 4002

ENV LLM_TRACKER_CONFIG=/root/.llm-tracker/config.yaml

ENTRYPOINT ["/entrypoint.sh"]
