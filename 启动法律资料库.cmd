@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -X utf8 -m cn_contract.web.local_server start --library-directory "D:\Documents\群兴法律资料库" %*
if errorlevel 1 pause
