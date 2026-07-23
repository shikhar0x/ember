#!/usr/bin/env bash
set -e

echo "========================================="
echo "       Ember Environment Setup"
echo "========================================="

# 0. Install system dependencies for Linux AppImage bundling
if command -v apt-get &> /dev/null; then
    echo "Installing system dependencies for AppImage (requires sudo)..."
    sudo apt-get update
    sudo apt-get install -y libfuse2
fi

# 1. Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed or not on PATH."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 13 ]; }; then
    echo "Error: Python 3.13+ is required. Found Python $PYTHON_VERSION"
    exit 1
fi
echo "✓ Python $PYTHON_VERSION detected."

# 2. Check Node.js and npm
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed or not on PATH."
    exit 1
fi
NODE_VERSION=$(node -v)
echo "✓ Node.js $NODE_VERSION detected."

if ! command -v npm &> /dev/null; then
    echo "Error: npm is not installed or not on PATH."
    exit 1
fi
NPM_VERSION=$(npm -v)
echo "✓ npm $NPM_VERSION detected."

# 3. Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating .venv virtual environment..."
    python3 -m venv .venv
else
    echo "✓ .venv virtual environment already exists."
fi

# 4. Activate virtual environment and install dependencies
echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing Python dependencies from requirements.txt..."
pip install -r requirements.txt

echo "Building Python backend executable..."
pyinstaller ember-backend.spec

# 5. NPM install in frontend
echo "Installing frontend dependencies..."
cd frontend
npm install
cd ..

echo "========================================="
echo "  Setup completed successfully!"
echo "========================================="
echo "To run the app in development mode:"
echo "  cd frontend && npm run tauri dev"
echo ""
echo "To build the app for production release:"
echo "  cd frontend && npm run tauri:build"
echo "========================================="
