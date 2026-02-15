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
# Deployment Timestamp: 2026-02-15 10:35:00
RUN cat <<'EOF' > /app/start.sh
#!/bin/bash

# Expose Render port
export RENDER_PORT=$PORT

# Go to Rasa folder
cd /app/backend/rasa

# Prevent Rasa from binding to public port
unset PORT

# Start Rasa Action Server in background
python -m rasa run actions --port 5055 &

# Start Rasa Open Source with REST API in background
# (Removed --num-threads to ensure standard bash compatibility)
python -m rasa run --enable-api --cors "*" --port 5005 --model models --endpoints endpoints.yml &

# Wait for Rasa model to load
echo "Waiting for Rasa to load model..."
for i in {1..60}; do
  if curl -s http://127.0.0.1:5005/status | grep "model_file" > /dev/null; then
    echo "Rasa is ready!"
    break
  fi
  echo "Rasa status: offline... waiting ($((i*5))s)"
  sleep 5
done

# Start Telegram Bot
cd /app
echo "Starting Telegram Bot..."
python telegram_bot.py &

# Start Flask backend via Gunicorn on the Render port
echo "Starting Flask/Gunicorn on port $RENDER_PORT..."
gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app
EOF

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
