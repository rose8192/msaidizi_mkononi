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
RUN echo '#!/bin/bash' > /app/start.sh && \
    echo 'export RENDER_PORT=$PORT' >> /app/start.sh && \
    echo 'cd /app/backend/rasa' >> /app/start.sh && \
    echo '# Force Rasa and Action Server to stay off the public port' >> /app/start.sh && \
    echo 'unset PORT' >> /app/start.sh && \
    echo 'python -m rasa run actions --port 5055 &' >> /app/start.sh && \
    echo 'python -m rasa run --enable-api --cors "*" --port 5005 --model models --num-threads 1 &' >> /app/start.sh && \
    echo 'echo "Waiting for Rasa to load model (checking /status)..."' >> /app/start.sh && \
    echo 'for i in {1..40}; do' >> /app/start.sh && \
    echo '  if curl -s http://127.0.0.1:5005/status | grep "model_file" > /dev/null; then' >> /app/start.sh && \
    echo '    echo "Rasa is ready!"' >> /app/start.sh && \
    echo '    break' >> /app/start.sh && \
    echo '  fi' >> /app/start.sh && \
    echo '  echo "Still waiting for Rasa model... ($((i*5))s)"' >> /app/start.sh && \
    echo '  sleep 5' >> /app/start.sh && \
    echo 'done' >> /app/start.sh && \
    echo 'cd /app' >> /app/start.sh && \
    echo 'echo "Starting Telegram Bot..."' >> /app/start.sh && \
    echo 'python telegram_bot.py &' >> /app/start.sh && \
    echo 'echo "Starting Flask on port $RENDER_PORT..."' >> /app/start.sh && \
    echo 'gunicorn --bind 0.0.0.0:$RENDER_PORT --workers 1 --threads 2 --timeout 120 app:app' >> /app/start.sh

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
