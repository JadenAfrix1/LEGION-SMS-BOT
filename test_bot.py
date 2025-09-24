#!/usr/bin/env python3
"""
Test script to verify bot components work correctly
"""

import sys
import os
from datetime import datetime

def test_imports():
    """Test if all required modules can be imported"""
    print("🧪 Testing imports...")
    
    try:
        import requests
        print("✅ requests imported")
    except ImportError:
        print("❌ requests not available - install with: pip install requests")
        return False
    
    try:
        from bs4 import BeautifulSoup
        print("✅ beautifulsoup4 imported")
    except ImportError:
        print("❌ beautifulsoup4 not available - install with: pip install beautifulsoup4")
        return False
    
    try:
        import telegram
        print("✅ python-telegram-bot imported")
    except ImportError:
        print("❌ python-telegram-bot not available - install with: pip install python-telegram-bot")
        return False
    
    try:
        from flask import Flask
        print("✅ flask imported")
    except ImportError:
        print("❌ flask not available - install with: pip install flask")
        return False
    
    try:
        from dotenv import load_dotenv
        print("✅ python-dotenv imported")
    except ImportError:
        print("❌ python-dotenv not available - install with: pip install python-dotenv")
        return False
    
    return True

def test_env_variables():
    """Test environment variables"""
    print("\n🧪 Testing environment variables...")
    
    if not os.path.exists('.env'):
        print("❌ .env file not found")
        return False
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        required_vars = [
            'IVASMS_EMAIL',
            'IVASMS_PASSWORD',
            'TELEGRAM_BOT_TOKEN', 
            'TELEGRAM_GROUP_ID'
        ]
        
        for var in required_vars:
            value = os.getenv(var)
            if value:
                # Mask sensitive data for display
                if 'PASSWORD' in var or 'TOKEN' in var:
                    masked = '*' * (len(value) - 4) + value[-4:] if len(value) > 4 else '*' * len(value)
                    print(f"✅ {var}: {masked}")
                else:
                    print(f"✅ {var}: {value}")
            else:
                print(f"❌ {var}: Not set")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error loading environment: {e}")
        return False

def test_bot_components():
    """Test individual bot components"""
    print("\n🧪 Testing bot components...")
    
    try:
        # Test utils
        from utils import format_otp_message, extract_otp_from_text
        
        test_otp = {
            'otp': '123456',
            'phone': '+1234567890',
            'service': 'Facebook',
            'timestamp': '12:34:56'
        }
        
        message = format_otp_message(test_otp)
        if '<code>123456</code>' in message:
            print("✅ utils.format_otp_message working")
        else:
            print("❌ utils.format_otp_message failed")
            return False
        
        otp = extract_otp_from_text("Your verification code is 654321")
        if otp == '654321':
            print("✅ utils.extract_otp_from_text working")
        else:
            print("❌ utils.extract_otp_from_text failed")
            return False
        
        # Test OTP filter
        from otp_filter import OTPFilter
        
        filter_instance = OTPFilter()
        test_data = {'otp': '999999', 'phone': '+9999999999', 'service': 'Test'}
        
        # Should not be duplicate first time
        if not filter_instance.is_duplicate(test_data):
            print("✅ otp_filter working")
            filter_instance.add_otp(test_data)
            
            # Should be duplicate second time
            if filter_instance.is_duplicate(test_data):
                print("✅ otp_filter duplicate detection working")
            else:
                print("❌ otp_filter duplicate detection failed")
                return False
        else:
            print("❌ otp_filter failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing components: {e}")
        return False

def test_telegram_connection():
    """Test Telegram bot connection"""
    print("\n🧪 Testing Telegram connection...")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            print("❌ No bot token found")
            return False
        
        from telegram import Bot
        bot = Bot(token=bot_token)
        
        # Test bot info
        bot_info = bot.get_me()
        print(f"✅ Connected to bot: @{bot_info.username}")
        return True
        
    except Exception as e:
        print(f"❌ Telegram connection failed: {e}")
        return False

def test_ivasms_connection():
    """Test IVASMS connection"""
    print("\n🧪 Testing IVASMS connection...")
    
    try:
        import requests
        
        response = requests.get("https://www.ivasms.com", timeout=10)
        if response.status_code == 200:
            print("✅ IVASMS.com is accessible")
            return True
        else:
            print(f"❌ IVASMS.com returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ IVASMS connection failed: {e}")
        return False

def create_sample_data():
    """Create sample data for testing"""
    print("\n🧪 Creating sample test data...")
    
    sample_otps = [
        {
            'otp': '123456',
            'phone': '+8801234567890',
            'service': 'Facebook',
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'raw_message': 'Your Facebook verification code is 123456'
        },
        {
            'otp': '789012',
            'phone': '+8801987654321', 
            'service': 'Google',
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'raw_message': 'Google verification code: 789012'
        }
    ]
    
    try:
        from utils import format_multiple_otps
        formatted = format_multiple_otps(sample_otps)
        print("✅ Sample data created and formatted")
        print("\nSample formatted message:")
        print("-" * 40)
        print(formatted)
        print("-" * 40)
        return True
        
    except Exception as e:
        print(f"❌ Error creating sample data: {e}")
        return False

def main():
    """Run all tests"""
    print("🤖 Telegram OTP Bot - Component Tests")
    print("=" * 50)
    
    tests = [
        ("Import Test", test_imports),
        ("Environment Variables", test_env_variables),
        ("Bot Components", test_bot_components),
        ("Telegram Connection", test_telegram_connection),
        ("IVASMS Connection", test_ivasms_connection),
        ("Sample Data", create_sample_data)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print(f"\n{'='*50}")
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Bot is ready to run.")
        print("\nNext steps:")
        print("1. Run: python main.py")
        print("2. Check the Flask endpoints at http://localhost:5000")
        print("3. Monitor the console for OTP detection")
    else:
        print("⚠️  Some tests failed. Please fix the issues before running the bot.")
        
        if passed < 2:  # Critical failures
            print("\n📋 Installation help:")
            print("pip install -r requirements.txt")

if __name__ == "__main__":
    main()
