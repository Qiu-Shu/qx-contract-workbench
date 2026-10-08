@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -X utf8 -m cn_contract.web.local_server start
if errorlevel 1 pause
