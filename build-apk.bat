@echo off
rem Build GymFormCoach.apk, an Android app you can send to testers.
rem
rem   build-apk.bat                         the app asks for the server link when it is first opened
rem   build-apk.bat https://your-link       the app opens that server straight away
rem
rem The APK is a shell around the web app: the models run on the server (run.bat public, or a hosted
rem copy), so the server must be running while testers use the app.
rem Needs the Android SDK and Java 11 or newer. See "Android app" in README.md.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0android\build-apk.ps1" %*
