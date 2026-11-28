@echo off
cd /d "e:\java\newProject"
echo [%date% %time%] Starting SafetyApplication... >> runtime-logs\safety-web.stdout.log
java -Xms512m -Xmx1024m -jar safety-web\target\safety-web-1.0.0-SNAPSHOT.jar >> runtime-logs\safety-web.stdout.log 2>&1
echo [%date% %time%] SafetyApplication exited with code %ERRORLEVEL% >> runtime-logs\safety-web.stdout.log