@echo off
title JARVIS Local Server
echo ==============================================
echo   Demarrage de JARVIS Local...
echo ==============================================
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python server.py
pause
