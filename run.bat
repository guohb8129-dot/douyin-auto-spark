@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" set PY=python

if "%~1"=="" goto loop
"%PY%" spark.py %*
goto :eof

:loop
"%PY%" spark.py
