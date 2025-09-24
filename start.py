#!/usr/bin/env python3
"""
Quick start script for the Telegram OTP Bot
This script helps set up and run the bot locally
"""

import os
import subprocess
import sys

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Error: Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True

def install_dependencies():
    """Install required dependencies"""
    print("📦 Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def check_env_file():
    """Check if .env file exists and has required variables"""
    if not os.path.exists('.env'):
        print("❌ .env file not found")
        print("📝 Please create .env file with your credentials:")
        print("   - Copy .env.example to .env")
        print("   - Fill in your IVASMS and Telegram credentials")
        return False
    
    required_vars = [
        'IVASMS_EMAIL',
        'IVASMS_PASSWORD', 
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_GROUP_ID'
    ]
    
    from dotenv import load_dotenv
    load_dotenv()
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        return False
    
    print("✅ Environment variables configured")
    return True

def run_bot():
    """Run the bot"""
    print("🚀 Starting Telegram OTP Bot...")
    try:
        subprocess.run([sys.executable, "main.py"])
    except KeyboardInterrupt:
        print("\n⏹️ Bot stopped by user")
    except Exception as e:
        print(f"❌ Error running bot: {e}")

def main():
    """Main setup and run function"""
    print("🤖 Telegram OTP Bot Setup")
    print("=" * 30)
    
    # Check Python version
    if not check_python_version():
        return
    
    # Install dependencies
    if not install_dependencies():
        return
    
    # Check environment variables
    if not check_env_file():
        return
    
    print("\n🎉 Setup complete! Starting bot...")
    print("=" * 30)
    
    # Run the bot
    run_bot()

if __name__ == "__main__":
    main()
