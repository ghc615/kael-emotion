@echo off
chcp 65001 >nul
cd /d %~dp0
if exist key.txt (
  set /p K=<key.txt
  set DEEPSEEK_API_KEY=%K%
)
python kael_web.py
pause
