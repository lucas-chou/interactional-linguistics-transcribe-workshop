@echo off
chcp 65001 >nul
set "ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%安装依赖.ps1"
pause
