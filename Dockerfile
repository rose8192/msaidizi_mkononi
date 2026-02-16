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
# Use localhost to prevent Render from detecting port 5055
echo "Starting Rasa Action Server..."
export SANIC_HOST=127.0.0.1
rasa run actions --port 5055 &

# Wait for Action Server to stabilize (memory spike reduction)
sleep 5

# 2. Start Rasa Open Source
# --model models: Loads latest model from directory
# --port 5005: Internal port (localhost)
# --interface 127.0.0.1: Force internal binding
echo "Checking for trained model..."
ls -lh models/
if ! ls models/*.tar.gz 1> /dev/null 2>&1; then
   echo "ERROR: No model found in models/ directory!"
   exit 1
fi
echo "Starting Rasa Open Source..."
# Force minimal workers and enable API
rasa run --enable-api --cors "*" --port 5005 --interface 127.0.0.1 --model models --endpoints endpoints.yml &

# 3. Start Telegram Bot (Background)
cd /app
echo "Starting Telegram Bot..."
python telegram_bot.py &

# 4. Start Flask/Gunicorn (Foreground)
# Start immediately to satisfy Render port detection (port 10000)
# Flask will handle Rasa unavailability gracefully
echo "Starting Flask/Gunicorn on port $RENDER_PORT..."
cd /app
gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 1 --timeout 120 --access-logfile - --error-logfile - app:app
EOF

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
