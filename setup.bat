@echo off
echo ============================================
echo   AttendX v3 Setup
echo ============================================

echo [1/3] Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate

echo [2/3] Upgrading pip...
python -m pip install --upgrade pip

echo [3/3] Installing dependencies...
pip install flask flask-cors python-dotenv werkzeug numpy opencv-python-headless Pillow "qrcode[pil]"

echo.
echo ============================================
echo   Setup Complete!
echo   Run 'start.bat' to launch the server.
echo ============================================
pause