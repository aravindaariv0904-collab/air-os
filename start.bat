@echo off
setlocal
echo.
echo  ___  _        ___  ____
echo / _ \(_)_____ / _ \/ ___)
echo / _  // // __// // /\__ \
echo \___//_//_/  \___/(____/
echo.
echo  Touchless Computing Interface
echo  Starting AirOS...
echo.

set "ROOT=%~dp0"

:: Start the Electron app (which launches the Python engine internally)
cd "%ROOT%apps\desktop"
npx electron . 2>&1

cd "%ROOT%"
