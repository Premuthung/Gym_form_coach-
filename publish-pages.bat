@echo off
rem Publish the page to GitHub Pages, so it has a permanent address:
rem     https://YOUR-GITHUB-NAME.github.io/REPOSITORY/
rem
rem   publish-pages.bat                 use the link of the "run.bat public" that is running now
rem   publish-pages.bat https://link    use this server address
rem
rem "run.bat public" does this by itself every time it starts, because its link changes every time.
rem GitHub serves only the page. Scanning and form checks still need the server on this computer.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\publish-pages.ps1" %*
