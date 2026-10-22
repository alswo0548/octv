@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv Python not found.
    exit /b 1
)
if not exist "local_data" mkdir "local_data"
echo [OCTV] Start only ONE Beat for this environment.
echo [OCTV] Recovery requires OCTV_PUSH_ENABLED=1 and OCTV_PUSH_RECOVERY_ENABLED=1.
".venv\Scripts\python.exe" -m celery -A backend.app.workers.celery_app beat -l info --schedule local_data/celerybeat-notifications
