@echo off
title AquaSense Smart Irrigation System Server
echo ===================================================
echo   AquaSense Smart Irrigation System
echo   FastAPI Backend ^& Dashboard Server
echo ===================================================
echo.

:: Ensure python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

echo Starting AquaSense Server on http://localhost:8000 ...
echo Press Ctrl+C to terminate.
echo.

python -m uvicorn app:app --host 0.0.0.0 --port 8000
pause
