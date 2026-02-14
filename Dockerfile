# Use a lightweight Python image
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first
COPY requirements.txt .
COPY backend/requirements.txt ./backend_requirements.txt

# Install dependencies
RUN pip install --no-cache-dir "packaging==20.9" "limits==2.8.0"
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r backend_requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy project files
COPY . .

# Create startup script
RUN echo '#!/bin/bash\n\
cd /app/backend/rasa\n\
# Start Rasa Actions\n\
python -m rasa run actions --port 5055 &\n\
# Start Rasa Server\n\
python -m rasa run --enable-api --cors "*" --port 5005 --model models &\n\
# Wait for Rasa to warm up (Free tier is slow)\n\
sleep 15\n\
# Start Flask via Gunicorn\n\
cd /app\n\
gunicorn --bind 0.0.0.0:$PORT app:app\n\
' > /app/start.sh

RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
