# Use a lightweight Python image
FROM python:3.10-slim

# Install system dependencies (Minimal)
RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy project files
COPY . .

# Create startup script correctly using a single RUN command
# Deployment Timestamp: 2026-02-15 13:45:00
# --- PRODUCTION BUILD STEP ---
# Train model during image build if not present
# This moves the heavy lifting to build time, preventing runtime OOM kills
RUN cd /app/backend/rasa && \
    if [ -z "$(ls -A models 2>/dev/null)" ]; then \
        echo "No models found. Training during build..." && \
        rasa train; \
    else \
        echo "Model found. Skipping build-time training."; \
    fi

RUN cat <<'EOF' > /app/start.sh
#!/bin/bash

# Expose Render port
export RENDER_PORT=$PORT

# Go to Rasa folder
cd /app/backend/rasa

# Prevent Rasa from binding to public port
unset PORT

# --- SIMPLE RUNTIME STARTUP ---
# No safeguards, no logic, just run.

echo "Starting Rasa Action Server..."
rasa run actions --port 5055 > /app/actions.log 2>&1 &

# Start Rasa Open Source with REST API
# Using --model models to let Rasa pick the latest model automatically
# This prevents 409 errors caused by specifying exact filenames
echo "Starting Rasa Open Source..."
python -m rasa run --enable-api --cors "*" --port 5005 --model models --endpoints endpoints.yml --debug > /app/rasa.log 2>&1 &

# Start Telegram Bot in background
cd /app
echo "Starting Telegram Bot..."
python telegram_bot.py > /app/telegram.log 2>&1 &

# Start Flask backend via Gunicorn on the Render port (Foreground)
# We wait a few seconds to let background processes initialize, but we don't block
echo "Waiting 10s for services to warm up..."
sleep 10

echo "Starting Flask/Gunicorn on port $RENDER_PORT..."
# Ensure we are in the app root
cd /app
gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app
EOF

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
