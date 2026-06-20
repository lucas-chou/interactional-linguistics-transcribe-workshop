@echo off
set "ROOT=%~dp0"
set "SCRIPT=%ROOT%start.ps1"
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if not exist "%SCRIPT%" (
  echo Cannot find "%SCRIPT%"
  pause
  exit /b 1
)

"%POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
if errorlevel 1 (
  echo.
  echo Startup failed. Please check the log files shown above.
  pause
  exit /b %errorlevel%
)
