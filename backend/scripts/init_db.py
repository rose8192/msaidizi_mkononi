
import sys
import os
import importlib.util

# Absolute path to backend/rasa/actions/actions.py
actions_path = os.path.abspath(os.path.join(os.getcwd(), 'backend', 'rasa', 'actions', 'actions.py'))

spec = importlib.util.spec_from_file_location("actions_module", actions_path)
actions_module = importlib.util.module_from_spec(spec)
sys.modules["actions_module"] = actions_module
spec.loader.exec_module(actions_module)

try:
    print(f"Using database path: {actions_module.SERVICES_DB}")
    print("Initializing database...")
    actions_module.ensure_db()
    print("Database initialized successfully.")
except Exception as e:
    print(f"Error initializing database: {e}")
    import traceback
    traceback.print_exc()
