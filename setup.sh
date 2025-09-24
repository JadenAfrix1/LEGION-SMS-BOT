#!/bin/bash

echo "========================================"
echo "   Telegram OTP Bot - Linux/Mac Setup"
echo "========================================"
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: Python 3 is not installed"
    echo "Please install Python 3.8+ from your package manager"
    exit 1
fi

echo "✅ Python is installed"
python3 --version

# Check if pip is available
if ! command -v pip3 &> /dev/null; then
    echo "❌ ERROR: pip3 is not available"
    echo "Please install pip3 from your package manager"
    exit 1
fi

echo "✅ pip3 is available"

# Install dependencies
echo
echo "📦 Installing dependencies..."
pip3 install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ ERROR: Failed to install dependencies"
    echo "Please check your internet connection and try again"
    exit 1
fi

echo "✅ Dependencies installed successfully"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo
    echo "📝 Creating .env file..."
    cp ".env.example" ".env"
    echo
    echo "⚠️  IMPORTANT: Please edit .env file with your credentials:"
    echo "   - IVASMS_EMAIL"
    echo "   - IVASMS_PASSWORD"
    echo "   - TELEGRAM_BOT_TOKEN" 
    echo "   - TELEGRAM_GROUP_ID"
    echo
    echo "Opening .env file for editing..."
    
    # Try different editors
    if command -v nano &> /dev/null; then
        nano .env
    elif command -v vim &> /dev/null; then
        vim .env
    elif command -v code &> /dev/null; then
        code .env
    else
        echo "Please edit .env file manually with your preferred editor"
        echo "Press Enter after you've saved your credentials..."
        read
    fi
fi

# Run tests
echo
echo "🧪 Running tests..."
python3 test_bot.py

if [ $? -ne 0 ]; then
    echo
    echo "⚠️  Some tests failed. Please check the output above."
    echo "You may still be able to run the bot if core components work."
    echo
fi

echo
echo "========================================"
echo "   Setup Complete!"
echo "========================================"
echo
echo "🚀 To start the bot:"
echo "   python3 main.py"
echo
echo "🌐 Dashboard will be available at:"
echo "   http://localhost:5000"
echo
echo "📋 Quick test:"
echo "   python3 start.py"
echo
echo "Press Enter to start the bot now..."
read

python3 main.py
