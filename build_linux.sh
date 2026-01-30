#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status.

# Build Script for Kraken VSA Bot

echo "Starting build process..."

# Ensure env is active
# Check for .venv in root or venv in root
if [ -d ".venv" ]; then
    echo "Activating .venv..."
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo "Activating venv..."
    source venv/bin/activate
else
    echo "WARNING: No .venv or venv found in current directory."
    echo "Attempting to continue using system python or active environment..."
fi

# Clean previous builds
echo "Cleaning build artifacts..."
rm -rf build dist

# Run PyInstaller
# Using python -m PyInstaller is safer than relying on the binary being in PATH
echo "Running PyInstaller..."
python -m PyInstaller --clean --noconfirm KrakenVSABot.spec

echo "Build Complete. Executable is in dist/KrakenVSABot"
