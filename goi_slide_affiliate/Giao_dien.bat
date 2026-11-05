@echo off
cd /d "%~dp0"
where python >nul 2>nul || (
    echo Chua cai Python. Tai tai https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) roi chay lai.
    pause & exit /b 1
)
rem ffmpeg dung de xuat video; may moi chua co thi tu cai bang winget (co san tren Windows 10/11)
set "PATH=%~dp0ffmpeg;%~dp0ffmpeg\bin;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
where ffmpeg >nul 2>nul || (
    echo Dang cai ffmpeg ^(chuong trinh xuat video^), lan dau mat 1-2 phut...
    winget install -e --id Gyan.FFmpeg.Essentials --accept-package-agreements --accept-source-agreements
)
where ffmpeg >nul 2>nul || (
    echo.
    echo Chua cai duoc ffmpeg. Tai ban "essentials" o https://www.gyan.dev/ffmpeg/builds/
    echo giai nen, chep ffmpeg.exe va ffplay.exe vao thu muc: %~dp0ffmpeg
    pause & exit /b 1
)
python giao_dien.py
if errorlevel 1 pause
