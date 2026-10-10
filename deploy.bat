@echo off
rem Put Gym Form Coach on the internet as a Hugging Face Space, so it opens like any web page:
rem     https://YOUR-NAME-gym-form-coach.hf.space
rem
rem   deploy.bat YOUR-NAME                 first time, and again after every change to the app
rem   deploy.bat YOUR-NAME another-name    use a different Space name
rem
rem YOUR-NAME is your Hugging Face user name. Hosting a Docker Space needs a PRO subscription
rem (https://huggingface.co/pro); without it the script stops with "402 Payment Required".
rem The first run asks for an access token: make one with the "Write" role at
rem https://huggingface.co/settings/tokens
setlocal
if "%~1"=="" (
  echo  Usage: deploy.bat YOUR-HUGGING-FACE-NAME
  exit /b 1
)
set SPACE=%~1/gym-form-coach
if not "%~2"=="" set SPACE=%~1/%~2
set DATASET=%SPACE%-feedback
set HF_HUB_DISABLE_UPDATE_CHECK=1

hf auth whoami >nul 2>&1
if errorlevel 1 hf auth login
if errorlevel 1 exit /b 1

echo.
echo  Creating the Space %SPACE% (skipped if it exists)...
hf repos create %SPACE% --type space --sdk docker --public --exist-ok
if errorlevel 1 exit /b 1

echo  Uploading the app...
hf upload %SPACE% "%~dp0." . --type space --include "Dockerfile" --include "requirements.txt" --include "backend/app/*.py" --include "backend/app/*.json" --include "frontend/**" --include "models/*.joblib" --include "models/*.task" --commit-message "Update the app"
if errorlevel 1 exit /b 1
hf upload %SPACE% "%~dp0deploy\README.md" README.md --type space --commit-message "Space settings"
if errorlevel 1 exit /b 1

echo.
echo  Done. Hugging Face is now building the app. The first build takes about 10 minutes.
echo    Build progress:  https://huggingface.co/spaces/%SPACE%
echo    The web page:    the "Embed this Space" link on that page, https://...hf.space
echo.
echo  To keep testers' feedback when the Space restarts, do this once on
echo  https://huggingface.co/spaces/%SPACE%/settings  under "Variables and secrets":
echo    Variable  GFC_FEEDBACK_REPO = %DATASET%
echo    Secret    HF_TOKEN          = an access token with the "Write" role
echo  Feedback then appears in the private dataset https://huggingface.co/datasets/%DATASET%
endlocal
