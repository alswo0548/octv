@echo off
setlocal
cd /d "%~dp0.."
echo ==========================================
echo OCTV - isolated local live bbox preview
echo No production server, DB, Redis or FCM.
echo ==========================================
set "OCTV_PY=python"
if exist "%~dp0..\..\octv\.venv\Scripts\python.exe" set "OCTV_PY=%~dp0..\..\octv\.venv\Scripts\python.exe"
if not exist "node_modules\.bin\vite.cmd" (
  echo Installing local frontend dependencies in SEPARATE worktree...
  call npm ci
  if errorlevel 1 (
    echo npm ci failed. Check network/npm output.
    exit /b 1
  )
)
"%OCTV_PY%" -c "import cv2,ultralytics; print('Python YOLO packages OK')"
if errorlevel 1 (
  echo Python venv missing cv2 or ultralytics.
  exit /b 1
)
echo Starting local-only Python API...
start "OCTV YOLO local API" cmd /k ""%OCTV_PY%" "%~dp0live_bbox_local_preview.py""
echo Starting local-only Vite web...
start "OCTV local web" cmd /k "npm run dev --workspace=@octv/web -- --host 127.0.0.1 --strictPort"
timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:4173/live-bbox-preview.html"
echo.
echo If the page is blank, wait for both terminal windows to say READY, then refresh.
echo Close both new terminal windows to stop. Production is unchanged.
