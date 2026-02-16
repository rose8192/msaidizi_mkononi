$projectRoot = $PSScriptRoot
Write-Host "Starting Msaidizi Mkononi Demo Services from: $projectRoot"

# 1. Start Action Server (Port 5055)
Write-Host "Launching Action Server..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$projectRoot'; echo 'Starting Action Server on 5055...'; python -m rasa_sdk --actions actions -p 5055"

# 2. Start Rasa Core + NLU (Port 5005)
Write-Host "Launching Rasa Server..."
# Using the model from backend/rasa/models
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$projectRoot'; echo 'Starting Rasa Core on 5005...'; python -m rasa run --enable-api --cors '*' --port 5005 --model backend/rasa/models --endpoints endpoints.yml"

# 3. Start Flask App (Port 10000)
Write-Host "Launching Flask App..."
# Set environment variables for Flask
$flaskCmd = "cd '$projectRoot'; `$env:PORT=10000; `$env:RASA_URL='http://127.0.0.1:5005/webhooks/rest/webhook'; echo 'Starting Flask on 10000...'; python app.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "$flaskCmd"

# 4. Start Ngrok (Port 10000)
Write-Host "Launching Ngrok..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "echo 'Exposing Port 10000...'; ngrok http 10000"

# 5. Start Telegram Bot
Write-Host "Launching Telegram Bot..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$projectRoot'; echo 'Starting Telegram Bot...'; python telegram_bot.py"

Write-Host "All services launched in separate windows!"
Write-Host "Please check the Ngrok window for your Public URL (e.g., https://xyz.ngrok-free.app)"
