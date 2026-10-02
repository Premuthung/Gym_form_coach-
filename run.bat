@echo off
rem Start Gym Form Coach.
rem   run.bat        -> only this computer can open it:  http://localhost:8000
rem   run.bat lan    -> phones on the same Wi-Fi can open it too (Windows may ask to allow the firewall)
setlocal
set HOST=127.0.0.1
if /I "%1"=="lan" set HOST=0.0.0.0
echo.
echo  Gym Form Coach is starting. Open http://localhost:8000 in your browser.
if /I "%1"=="lan" (
  echo  On your phone, open http://YOUR-PC-IP:8000  - your PC's addresses:
  ipconfig | findstr /C:"IPv4"
)
echo  Press Ctrl+C to stop.
echo.
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir "%~dp0backend" --host %HOST% --port 8000
endlocal
