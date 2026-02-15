# Use a lightweight Python image
FROM python:3.10-slim

# Force Python unbuffered mode for immediate logs
ENV PYTHONUNBUFFERED=1

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
# Deployment Timestamp: 2026-02-15 14:00:00
# --- PRODUCTION BUILD STEP ---
# Train model during image build if not present
# This moves the heavy lifting to build time, preventing runtime OOM kills
RUN cd /app/backend/rasa && rasa train --force

RUN cat <<'EOF' > /app/start.sh
#!/bin/bash

# Expose Render port
export RENDER_PORT=$PORT

# Go to Rasa folder
cd /app/backend/rasa

# Prevent Rasa from binding to public port
# CRITICAL: This prevents Render from misidentifying Rasa as the primary web service
unset PORT

# --- FINAL CORRECT ARCHITECTURE ---
# 1. Start Action Server
echo "Starting Rasa Action Server..."
rasa run actions --port 5055 &

# 2. Start Rasa Open Source
# --model models: Loads latest model from directory (Prevents 400/409 errors)
# --port 5005: Internal port
echo "Checking for trained model..."
ls -lh models/
echo "Starting Rasa Open Source..."
python -m rasa run --enable-api --cors "*" --port 5005 --model models --endpoints endpoints.yml &

# 3. Start Telegram Bot (Background)
cd /app
echo "Starting Telegram Bot..."
python telegram_bot.py &

# Wait for services to initialize
echo "Waiting 10s for Rasa to initialize..."
sleep 10

# 4. Start Flask/Gunicorn (Foreground)
# This MUST bind to $RENDER_PORT to pass health checks
echo "Starting Flask/Gunicorn on port $RENDER_PORT..."
cd /app
gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 1 --timeout 120 --access-logfile - --error-logfile - app:app
EOF

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
