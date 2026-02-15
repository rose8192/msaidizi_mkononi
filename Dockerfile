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
# Deployment Timestamp: 2026-02-15 10:40:00
RUN cat <<'EOF' > /app/start.sh
#!/bin/bash

# Expose Render port
export RENDER_PORT=$PORT

# Go to Rasa folder
cd /app/backend/rasa

# Prevent Rasa from binding to public port
unset PORT

echo "Checking for Rasa models..."
ls -la models/

# Find the latest model file to be explicit
LATEST_MODEL=$(ls -t models/*.tar.gz 2>/dev/null | head -n 1)
if [ -z "$LATEST_MODEL" ]; then
    echo "WARNING: No model files found in backend/rasa/models/"
    MODEL_PATH="models"
else
    echo "Found latest model: $LATEST_MODEL"
    MODEL_PATH="$LATEST_MODEL"
fi

# Start Rasa Action Server in background
echo "Starting Rasa Action Server..."
python -m rasa run actions --port 5055 > /app/actions.log 2>&1 &

# Start Rasa Open Source with REST API in background
echo "Starting Rasa Open Source with model: $MODEL_PATH"
python -m rasa run --enable-api --cors "*" --port 5005 --model "$MODEL_PATH" --endpoints endpoints.yml --debug > /app/rasa.log 2>&1 &

# Wait for Rasa model to load
echo "Waiting for Rasa to load model..."
for i in {1..120}; do
  STATUS_RESPONSE=$(curl -s http://127.0.0.1:5005/status || echo "connection_failed")
  
  if echo "$STATUS_RESPONSE" | grep "model_file" | grep -v "null" > /dev/null; then
    echo "Rasa is ready! Status: $STATUS_RESPONSE"
    break
  fi
  
  echo "Rasa status: $STATUS_RESPONSE... waiting ($((i*5))s)"
  
  # Periodically check logs if still offline
  if [ $((i % 6)) -eq 0 ]; then
    echo "--- Last 5 lines of Rasa logs ---"
    tail -n 5 /app/rasa.log
  fi
  
  sleep 5
done

# Start Telegram Bot
cd /app
echo "Starting Telegram Bot..."
python telegram_bot.py > /app/telegram.log 2>&1 &

# Start Flask backend via Gunicorn on the Render port
echo "Starting Flask/Gunicorn on port $RENDER_PORT..."
gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app
EOF

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
