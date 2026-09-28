@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
call npm run dev:web
exit /b %errorlevel%
