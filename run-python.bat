@echo off
cd /d "e:\java\newProject\ai-module"
echo [%date% %time%] Starting Python AI Module... >> "e:\java\newProject\runtime-logs\ai-module.stdout.log"
python server.py >> "e:\java\newProject\runtime-logs\ai-module.stdout.log" 2>&1
echo [%date% %time%] Python AI Module exited with code %ERRORLEVEL% >> "e:\java\newProject\runtime-logs\ai-module.stdout.log"