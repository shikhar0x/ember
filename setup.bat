@echo off
setlocal enabledelayedexpansion

echo =========================================
echo        Ember Environment Setup
echo =========================================

:: 1. Check python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: python is not installed or not on PATH.
    exit /b 1
)

:: Check python version
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: Python 3.13+ is required.
    exit /b 1
)
echo ✓ Python 3.13+ detected.

:: 2. Check Node.js and npm
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: Node.js is not installed or not on PATH.
    exit /b 1
)
echo ✓ Node.js detected.

where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: npm is not installed or not on PATH.
    exit /b 1
)
echo ✓ npm detected.

:: 3. Create virtual environment
if not exist ".venv" (
    echo Creating .venv virtual environment...
    python -m venv .venv
    if !ERRORLEVEL! neq 0 (
        echo Error: Failed to create virtual environment.
        exit /b 1
    )
) else (
    echo ✓ .venv virtual environment already exists.
)

:: 4. Activate virtual environment and install dependencies
echo Activating virtual environment...
call .venv\Scripts\activate.bat
if !ERRORLEVEL! neq 0 (
    echo Error: Failed to activate virtual environment.
    exit /b 1
)

echo Installing Python dependencies from requirements.txt...
pip install -r requirements.txt
if !ERRORLEVEL! neq 0 (
    echo Error: Failed to install Python dependencies.
    exit /b 1
)

echo Building Python backend executable...
pyinstaller ember-backend.spec
if !ERRORLEVEL! neq 0 (
    echo Error: Failed to build backend executable.
    exit /b 1
)

:: 5. Install Node dependencies
echo Installing frontend dependencies...
cd frontend
call npm install
if !ERRORLEVEL! neq 0 (
    echo Error: Failed to install Node dependencies.
    cd ..
    exit /b 1
)
cd ..

echo.
echo =========================================
echo   Setup completed successfully^!
echo =========================================
echo To run the app in development mode:
echo   cd frontend
echo   npm run tauri dev
echo.
echo To build the app for production release:
echo   cd frontend
echo   npm run tauri:build
echo =========================================
