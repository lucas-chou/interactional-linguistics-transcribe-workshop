@echo off
chcp 65001 >nul
set "ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%打包分发.ps1"
pause
