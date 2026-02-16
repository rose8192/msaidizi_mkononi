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

# Ensure data directories exist for Action Server (SQLite, etc.)
RUN mkdir -p /app/backend/data

# Create startup script correctly using a single RUN command
# Deployment Timestamp: 2026-02-15 14:00:00
# --- PRODUCTION BUILD STEP ---
# Model is now trained locally and committed to Git.
# No build-time training to save memory and time.

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
if [ -z "$(ls -A models)" ]; then
   echo "ERROR: No model found in models/ directory!"
   exit 1
fi
echo "Starting Rasa Open Source..."
rasa run --enable-api --cors "*" --port 5005 --model models --endpoints endpoints.yml &

# Wait for services to initialize
echo "Waiting for Rasa to be ready..."
# Loop until Rasa's /status endpoint returns 200 OK (max 60 seconds)
for i in {1..12}; do
    if curl -s http://localhost:5005/status | grep "ok" > /dev/null; then
        echo "Rasa is ready!"
        break
    fi
    echo "Waiting for Rasa... ($i/12)"
    sleep 5
done

# 3. Start Telegram Bot (Background)
cd /app
echo "Starting Telegram Bot..."
python telegram_bot.py &


# 4. Start Flask/Gunicorn (Foreground)
# This MUST bind to $RENDER_PORT to pass health checks
echo "Starting Flask/Gunicorn on port $RENDER_PORT..."
cd /app
gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 1 --timeout 120 --access-logfile - --error-logfile - app:app
EOF

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
