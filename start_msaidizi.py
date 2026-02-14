import subprocess
import time
import sys
import os

def start_service(name, command, cwd=None):
    print(f"Starting {name}...")
    return subprocess.Popen(command, shell=True, cwd=cwd)

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(root_dir, ".venv", "Scripts", "python.exe")
    venv_rasa = os.path.join(root_dir, ".venv", "Scripts", "rasa.exe")

    processes = []

    try:
        # 1. Start Rasa Action Server
        processes.append(start_service(
            "Rasa Action Server",
            [venv_python, "-m", "rasa_sdk.endpoint", "--actions", "backend.rasa.actions.actions"],
            cwd=root_dir
        ))

        # 2. Start Rasa Server
        processes.append(start_service(
            "Rasa Server",
            [venv_rasa, "run", "--enable-api", "--cors", "*"],
            cwd=os.path.join(root_dir, "backend", "rasa")
        ))

        # 3. Start USSD Gateway
        processes.append(start_service(
            "USSD Gateway",
            [venv_python, "app.py"],
            cwd=root_dir
        ))

        # 4. Start Admin Dashboard
        processes.append(start_service(
            "Admin Dashboard",
            [venv_python, "app.py"],
            cwd=os.path.join(root_dir, "backend", "admin_dashboard")
        ))

        print("\nAll Msaidizi Mkononi services are starting up.")
        print("Rasa API: http://localhost:5005")
        print("USSD Gateway: http://localhost:5000")
        print("Admin Dashboard: http://localhost:5001")
        print("\nPress Ctrl+C to stop all services.")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping all services...")
        for p in processes:
            p.terminate()
        print("Done.")

if __name__ == "__main__":
    main()
