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
# Deployment Timestamp: 2026-02-15 10:20:00
RUN cat <<'EOF' > /app/start.sh
#!/bin/bash
export RENDER_PORT=$PORT
cd /app/backend/rasa
# Force Rasa and Action Server to stay off the public port
unset PORT
echo "Current Memory Info:"
free -m || cat /proc/meminfo | grep MemAvailable
echo "Starting Rasa Action Server..."
python -m rasa run actions --port 5055 > /app/actions.log 2>&1 &
echo "Starting Rasa Open Source..."
python -m rasa run --enable-api --cors "*" --port 5005 --model models --num-threads 1 --endpoints endpoints.yml > /app/rasa.log 2>&1 &
echo "Waiting for Rasa to load model..."
for i in {1..150}; do
   STATUS_JSON=$(curl -s http://127.0.0.1:5005/status || echo "offline")
   curl -s http://127.0.0.1:5055/health > /dev/null
   if echo "$STATUS_JSON" | grep -v "null" | grep "model_file" > /dev/null; then
     echo "Rasa is ready! Model loaded."
     break
   fi
   if ! pgrep -f "rasa run" > /dev/null; then
     echo "CRITICAL: Rasa process has died. Checking logs:"
     tail -n 20 /app/rasa.log
     python -m rasa run --enable-api --cors "*" --port 5005 --model models --num-threads 1 --endpoints endpoints.yml > /app/rasa.log 2>&1 &
   fi
   echo "Rasa status: $STATUS_JSON... waiting ($((i*5))s)"
   if [ $((i % 6)) -eq 0 ]; then
     echo "--- Resource Check ---"
     free -m || cat /proc/meminfo | grep MemAvailable
     echo "--- Rasa Logs (Last 5 lines) ---"
     tail -n 5 /app/rasa.log
   fi
   sleep 5
done
cd /app
echo "Starting Telegram Bot..."
python telegram_bot.py &
echo "Starting Flask on port $RENDER_PORT..."
gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app
EOF

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
