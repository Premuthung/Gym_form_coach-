@echo off
rem Start Gym Form Coach.
rem   run.bat          -> only this computer can open it:  http://localhost:8000
rem   run.bat lan      -> phones on the same Wi-Fi can open it too (Windows may ask to allow the firewall)
rem   run.bat public   -> anyone with the link can open it, on any network (for testers).
rem                       A second window opens and shows an https://....trycloudflare.com link to share.
rem                       The link works while this computer is on and both windows stay open.
setlocal
set HOST=127.0.0.1
if /I "%1"=="lan" set HOST=0.0.0.0
echo.
echo  Gym Form Coach is starting. Open http://localhost:8000 in your browser.
if /I "%1"=="lan" goto lan
if /I "%1"=="public" goto public
goto start

:lan
echo  On your phone, open http://YOUR-PC-IP:8000  - your PC's addresses:
ipconfig | findstr /C:"IPv4"
goto start

:public
set TUNNEL=%~dp0data\tools\cloudflared.exe
if exist "%TUNNEL%" goto tunnel
echo  Downloading the Cloudflare tunnel program, one time only...
if not exist "%~dp0data\tools" mkdir "%~dp0data\tools"
curl.exe -L --fail -o "%TUNNEL%" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
if errorlevel 1 (
  echo  The download failed. Check the internet connection and run this again.
  exit /b 1
)
:tunnel
echo  A second window is opening. Share the https://....trycloudflare.com link it shows.
echo  The link is also written to data\tools\tunnel.log
echo  Feedback from testers is saved in data\feedback.csv
if exist "%~dp0data\tools\tunnel.log" del "%~dp0data\tools\tunnel.log"
start "Gym Form Coach - public link" "%TUNNEL%" tunnel --url http://localhost:8000 --logfile "%~dp0data\tools\tunnel.log"
rem The link is new every time. Tell the permanent GitHub page where the server is now.
start "Gym Form Coach - updating the GitHub page" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\publish-pages.ps1" -Wait

:start
echo  Press Ctrl+C to stop.
echo.
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir "%~dp0backend" --host %HOST% --port 8000
endlocal
