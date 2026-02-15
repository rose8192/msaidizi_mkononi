import subprocess
import time
import sys
import os
import signal

def start_service(name, command, cwd=None):
    print(f"Starting {name}...")
    try:
        # Use shell=True for Windows to execute commands properly
        return subprocess.Popen(command, shell=True, cwd=cwd)
    except Exception as e:
        print(f"Error starting {name}: {e}")
        return None

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    python_exe = sys.executable  # Use current python executable
    rasa_exe = "rasa" # Assume rasa is in PATH or use python -m rasa

    processes = []

    try:
        # 1. Start Rasa Action Server
        # Use python -m rasa_sdk to avoid path issues
        processes.append(start_service(
            "Rasa Action Server",
            [python_exe, "-m", "rasa_sdk.endpoint", "--actions", "actions.actions"],
            cwd=os.path.join(root_dir, "backend", "rasa")
        ))
        
        # Wait a bit for action server
        time.sleep(2)

        # 2. Start Rasa Server (enable API)
        # Use python -m rasa to be safe
        processes.append(start_service(
            "Rasa Server",
            [python_exe, "-m", "rasa", "run", "--model", "models", "--enable-api", "--cors", "*", "--debug"],
            cwd=os.path.join(root_dir, "backend", "rasa")
        ))
        
        # Wait for Rasa to initialize (can take time)
        print("Waiting for Rasa to initialize (15s)...")
        time.sleep(15)

        # 3. Start Flask App (Proxy)
        processes.append(start_service(
            "Flask Proxy App",
            [python_exe, "app.py"],
            cwd=os.path.join(root_dir)
        ))

        print("\nAll Msaidizi Mkononi services are starting up.")
        print("Rasa API: http://localhost:5005")
        print("Flask Proxy: http://localhost:10000 (default)")
        print("\nPress Ctrl+C to stop all services.")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping all services...")
        for p in processes:
            if p:
                p.terminate() # This might not kill child processes on Windows with shell=True
                # Using taskkill for cleanup
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(p.pid)])
        print("Done.")

if __name__ == "__main__":
    main()
