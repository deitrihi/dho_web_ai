@echo off
REM Double-click launcher: runs deploy.sh via Git Bash. Args (webapp/chat) pass through.
setlocal

set "GITBASH=C:\Program Files\Git\bin\bash.exe"
if not exist "%GITBASH%" (
  echo Git Bash not found: %GITBASH%
  echo Install Git for Windows: https://git-scm.com/download/win
  pause
  exit /b 1
)

cd /d "%~dp0"
"%GITBASH%" ./deploy.sh %*

echo.
echo Press any key to close this window...
pause >nul
