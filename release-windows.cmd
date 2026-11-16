@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0release-windows.ps1" %*
exit /b %ERRORLEVEL%
