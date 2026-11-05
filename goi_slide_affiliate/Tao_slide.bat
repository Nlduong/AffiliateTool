@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
where python >nul 2>nul || (echo Chua cai Python. Tai tai https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) roi chay lai. & pause & exit /b 1)
python tao_slide.py
pause
