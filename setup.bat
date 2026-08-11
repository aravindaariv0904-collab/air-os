@echo off
setlocal
echo.
echo ==========================================
echo   AirOS Setup Verification
echo ==========================================
echo.

set "ROOT=%~dp0"
set "VENV=%ROOT%venv\Scripts\python.exe"
set "NODE_EXE=node"

:: Check Python venv
if exist "%VENV%" (
    echo [OK] Python venv found
    "%VENV%" --version
) else (
    echo [ERROR] Python venv not found at %ROOT%venv
    echo         Run: python -m venv venv
    echo         Then: venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

:: Check Python imports
echo.
echo Checking Python dependencies...
"%VENV%" -c "import mediapipe, cv2, numpy, websockets; print('[OK] All Python deps installed')" 2>&1
if errorlevel 1 (
    echo [ERROR] Some Python dependencies missing. Run:
    echo   venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

:: Check MediaPipe model
if exist "%ROOT%assets\models\hand_landmarker.task" (
    echo [OK] MediaPipe model found
) else (
    echo [INFO] MediaPipe model not found - will be downloaded on first run
)

:: Check Node.js
%NODE_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org
    pause
    exit /b 1
) else (
    echo [OK] Node.js found
    %NODE_EXE% --version
)

:: Check desktop app deps
if exist "%ROOT%apps\desktop\node_modules" (
    echo [OK] Desktop app dependencies found
) else (
    echo [INFO] Installing desktop app dependencies...
    cd "%ROOT%apps\desktop"
    npm install --legacy-peer-deps
    cd "%ROOT%"
)

echo.
echo ==========================================
echo   Setup verification complete!
echo   Run: start.bat to launch AirOS
echo ==========================================
echo.
pause
