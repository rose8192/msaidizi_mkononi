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
# Deployment Timestamp: 2026-02-15 12:45:00
RUN cat <<'EOF' > /app/start.sh
#!/bin/bash

# Expose Render port
export RENDER_PORT=$PORT

# Go to Rasa folder
cd /app/backend/rasa

# Prevent Rasa from binding to public port
unset PORT

echo "Checking for Rasa models..."
# Explicitly find the latest model to avoid ambiguity
LATEST_MODEL=$(ls -t models/*.tar.gz 2>/dev/null | head -n 1)

if [ -f "$LATEST_MODEL" ]; then
    echo "Model found: $LATEST_MODEL. Skipping training."
else
    echo "No model found. Training Rasa model..."
    rasa train
    LATEST_MODEL=$(ls -t models/*.tar.gz 2>/dev/null | head -n 1)
fi

# Start Rasa Action Server in background
echo "Starting Rasa Action Server..."
rasa run actions --port 5055 > /app/actions.log 2>&1 &

# Start Rasa Open Source with REST API in background
# Use explicit model path and python -m for robustness
echo "Starting Rasa Open Source with model: $LATEST_MODEL"
python -m rasa run --enable-api --cors "*" --port 5005 --model "$LATEST_MODEL" --endpoints endpoints.yml --debug > /app/rasa.log 2>&1 &

# Start Telegram Bot in background
cd /app
echo "Starting Telegram Bot..."
python telegram_bot.py > /app/telegram.log 2>&1 &

# Start a background monitoring loop that doesn't block Gunicorn
# This ensures Render sees the app as "Live" immediately via Gunicorn
(
  echo "Monitoring Rasa status in background..."
  for i in $(seq 1 300); do
    STATUS_RESPONSE=$(curl -s http://127.0.0.1:5005/status || echo "connection_failed")
    
    if echo "$STATUS_RESPONSE" | grep "model_file" | grep -v "null" > /dev/null; then
      echo "Rasa is ready! Status: $STATUS_RESPONSE"
      # Keep monitoring but slower
      sleep 60
      continue
    fi
    
    # Only log every 10th attempt to reduce noise
    if [ $((i % 10)) -eq 0 ]; then
        echo "Rasa status: $STATUS_RESPONSE... waiting ($((i*5))s)"
        echo "--- Last 5 lines of Rasa logs ---"
        tail -n 5 /app/rasa.log
        
        # Restart if dead
        if ! pgrep -f "rasa run" > /dev/null; then
            echo "Rasa process died, restarting..."
            cd /app/backend/rasa
            python -m rasa run --enable-api --cors "*" --port 5005 --model "$LATEST_MODEL" --endpoints endpoints.yml --debug >> /app/rasa.log 2>&1 &
        fi
    fi
    
    sleep 5
  done
) &

# Start Flask backend via Gunicorn on the Render port (Foreground)
# This MUST be the last command and must run in foreground
echo "Starting Flask/Gunicorn on port $RENDER_PORT..."
# Ensure we are in the app root
cd /app
gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app
EOF

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
