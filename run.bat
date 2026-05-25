@echo off
setlocal
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "HERE=%~dp0"
set "PY=%HERE%.venv\Scripts\python.exe"
set "SCRIPT=%HERE%subtitle.py"

if "%~1"=="" (
    echo Usage:
    echo   Drag a video file onto this .bat
    echo   OR run:  run.bat "C:\path\to\video.mkv"
    echo.
    echo No file given. Looking for the first video in this folder...
    for %%F in ("%HERE%*.mkv" "%HERE%*.mp4" "%HERE%*.avi" "%HERE%*.mov") do (
        echo Found: %%F
        "%PY%" -u "%SCRIPT%" "%%F" --model medium --device cuda --languages he,ar,fr
        echo.
        echo === DONE ===
        echo Open the .mkv in VLC. The .he.srt next to it will load automatically.
        pause
        exit /b
    )
    echo No video file found in this folder.
    pause
    exit /b 1
)

"%PY%" -u "%SCRIPT%" "%~1" --model medium --device cuda --languages he,ar,fr
echo.
echo === DONE ===
echo Open the video in VLC. The .he.srt next to it will load automatically.
pause
