# Use a lightweight Python image
FROM python:3.10-slim

# Install system dependencies (Minimal)
RUN apt-get update && apt-get install -y \
    curl \
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

# Create startup script
RUN echo '#!/bin/bash\n\
cd /app/backend/rasa\n\
# Start Rasa Actions\n\
python -m rasa run actions --port 5055 &\n\
# Start Rasa Server with memory optimization\n\
python -m rasa run --enable-api --cors "*" --port 5005 --model models --num-threads 1 &\n\
# Wait for Rasa to warm up (Free tier is slow)\n\
sleep 20\n\
# Start Flask via Gunicorn\n\
cd /app\n\
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 app:app\n\
' > /app/start.sh

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
