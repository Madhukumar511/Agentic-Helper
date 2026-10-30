#!/usr/bin/env bash
set -e

echo "========================================================"
echo "  Agentic-Helper: 1-Click Setup for Linux / macOS"
echo "========================================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found. Please install Python 3.10+."
    exit 1
fi

echo "[1/2] Installing package dependencies..."
python3 -m pip install -e .

echo "[2/2] Verifying Playwright browser engine..."
python3 -m playwright install chromium

echo ""
echo "========================================================"
echo "  Setup Complete!"
echo ""
echo "  How to use in Antigravity IDE:"
echo "  1. Start browser: google-chrome (or brave, microsoft-edge, vivaldi) --remote-debugging-port=9222 --user-data-dir=/tmp/agent_browser &"
echo "  2. Navigate to your Coursera/Canvas quiz in that browser."
echo "  3. In Antigravity IDE chat, type: /agentic-helper"
echo "========================================================"
