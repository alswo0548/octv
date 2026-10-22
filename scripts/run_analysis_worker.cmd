@echo off
setlocal

cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv Python not found.
    exit /b 1
)

echo [OCTV] Starting Analysis Celery Worker
echo [OCTV] Queue: analysis

".venv\Scripts\python.exe" -m celery -A backend.app.workers.celery_app worker -Q analysis -l info -P sologit status --short