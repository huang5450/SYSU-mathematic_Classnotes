@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0workflow.ps1" %*
exit /b %ERRORLEVEL%
