#!/bin/bash
# build_linux.sh
# Linux build script for FVTT Journal -> PDF

# Exit on error
set -e

echo "=== FVTT Journal to PDF: Linux Build Process ==="

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed. Please install Python 3.10+ to continue."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing dependencies..."
pip install -r requirements.txt
pip install pyinstaller

# Create backgrounds directory if it doesn't exist
if [ ! -d "backgrounds" ]; then
    mkdir backgrounds
    touch backgrounds/.gitkeep
fi

# Build app executable
echo "Building Linux executable..."
pyinstaller --noconfirm app_with_dividers.spec

echo "=================================================="
echo "Build complete! Linux executable built successfully."
echo "You can find it at: dist/FVTT-Journal-to-PDF"
echo "=================================================="
