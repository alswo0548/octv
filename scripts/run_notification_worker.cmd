@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv Python not found.
    exit /b 1
)
echo [OCTV] Starting notification Worker - queue: notifications
".venv\Scripts\python.exe" -m celery -A backend.app.workers.celery_app worker -Q notifications -l info -P solo -n notifications@%%h
