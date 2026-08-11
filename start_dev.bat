@echo off
setlocal
echo.
echo  AirOS Development Mode
echo  Starting Vite + Electron in parallel...
echo.

set "ROOT=%~dp0"

:: Start Vite dev server in a new window
start "AirOS Vite Dev Server" cmd /k "cd /d "%ROOT%apps\desktop" && npx vite"

:: Wait 3 seconds for Vite to start
timeout /t 3 /nobreak >nul

:: Start Electron in dev mode
set NODE_ENV=development
cd "%ROOT%apps\desktop"
npx electron . 2>&1

cd "%ROOT%"
