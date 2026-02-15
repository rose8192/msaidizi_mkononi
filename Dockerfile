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
RUN printf '#!/bin/bash\n\
export RENDER_PORT=$PORT\n\
cd /app/backend/rasa\n\
# Force Rasa and Action Server to stay off the public port\n\
unset PORT\n\
python -m rasa run actions --port 5055 &\n\
python -m rasa run --enable-api --cors "*" --port 5005 --model models --num-threads 1 --endpoints endpoints.yml &\n\
echo "Waiting for Rasa to load model (checking /status)..."\n\
 for i in {1..150}; do\n\
    STATUS_JSON=$(curl -s http://127.0.0.1:5005/status || echo "offline")\n\
    if echo "$STATUS_JSON" | grep -v "null" | grep "model_file" > /dev/null; then\n\
      echo "Rasa is ready! Model loaded."\n\
      break\n\
    fi\n\
    echo "Rasa status: $STATUS_JSON... waiting ($((i*5))s)"\n\
    sleep 5\n\
  done\n\
cd /app\n\
echo "Starting Telegram Bot..."\n\
python telegram_bot.py &\n\
echo "Starting Flask on port $RENDER_PORT..."\n\
gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app\n' > /app/start.sh

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
