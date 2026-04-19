FROM node:22-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    cron \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create Python venv and install dependencies
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Set up app directory
WORKDIR /app

# Copy scripts and config
COPY scripts/ /app/scripts/
COPY crontab /etc/cron.d/obsidian-automator

# Set permissions
RUN chmod +x /app/scripts/entrypoint.sh /app/scripts/weather.sh \
    && chmod 0644 /etc/cron.d/obsidian-automator \
    && crontab /etc/cron.d/obsidian-automator \
    && touch /var/log/cron.log

# Ensure Python venv is in PATH
ENV PATH="/opt/venv/bin:$PATH"
ENV CREDENTIALS_DIR=/credentials

# Run cron in foreground
CMD ["cron", "-f"]
