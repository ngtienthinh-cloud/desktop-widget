@echo off
REM ===================================================================
REM  Tu build DesktopWidget.exe tren may ban (chi can neu khong dung
REM  ban .exe tai tu GitHub). Can Python 3.9+ da cai san.
REM  Ket qua: dist\DesktopWidget.exe  (chay doc lap, khong can Python)
REM ===================================================================
cd /d "%~dp0"
where python >nul 2>nul || (echo Chua cai Python. Tai tai https://www.python.org/downloads/ & pause & exit /b 1)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller pillow || (pause & exit /b 1)
python make_icon.py assets\icon.ico
python -m PyInstaller --noconfirm --clean --onefile --windowed --name DesktopWidget --icon assets\icon.ico desktop_widget.py || (pause & exit /b 1)
echo.
echo XONG: dist\DesktopWidget.exe
explorer dist
pause
