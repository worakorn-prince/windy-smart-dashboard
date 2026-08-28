@echo off
REM run.bat — calls run.ps1 with the same arguments
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
