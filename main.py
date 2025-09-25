#!/usr/bin/env python3
"""
Telegram OTP Bot - Complete Implementation
Monitors IVASMS.com for new OTPs and sends them to Telegram groups
Includes Flask web dashboard for monitoring and control
"""

import os
import json
import asyncio
import logging
import re
import requests
import threading
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import func
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from telegram import Bot

# Load environment variables
load_dotenv()

# Configure logging with debug support
log_level = logging.DEBUG if os.environ.get('DEBUG') == '1' else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('otp_bot.log', mode='a') if os.path.exists('.') else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================================
# FLASK APP SETUP
# ================================

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "telegram-otp-bot-secret-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///bot.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
db.init_app(app)

# ================================
# DATABASE MODELS
# ================================

class OTPLog(db.Model):
    """Model to store OTP processing logs for statistics and tracking"""
    id = db.Column(db.Integer, primary_key=True)
    otp_code = db.Column(db.String(20), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    service_name = db.Column(db.String(100), nullable=True)
    raw_message = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    sent_to_telegram = db.Column(db.Boolean, default=False, nullable=False)
    
    def __repr__(self):
        return f'<OTPLog {self.id}: {self.otp_code} - {self.service_name}>'

class BotStats(db.Model):
    """Model to store bot statistics and status"""
    id = db.Column(db.Integer, primary_key=True)
    stat_name = db.Column(db.String(50), unique=True, nullable=False)
    stat_value = db.Column(db.String(255), nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<BotStats {self.stat_name}: {self.stat_value}>'

# ================================
# UTILITY FUNCTIONS
# ================================

def format_otp_message(otp_data):
    """Format OTP data for Telegram with touch-to-copy functionality"""
    otp = otp_data.get('otp', 'N/A')
    phone = otp_data.get('phone', 'N/A')
    service = otp_data.get('service', 'Unknown')
    timestamp = otp_data.get('timestamp', datetime.now().strftime('%H:%M:%S'))
    
    message = f"""🔐 <b>New OTP Received</b>

🔢 OTP: <code>{otp}</code>
📱 Number: <code>{phone}</code>
🌐 Service: <b>{service}</b>
⏰ Time: {timestamp}

<i>Tap the OTP to copy it!</i>"""
    
    return message

def format_multiple_otps(otp_list):
    """Format multiple OTPs into a single message"""
    if not otp_list:
        return "No new OTPs found."
    
    if len(otp_list) == 1:
        return format_otp_message(otp_list[0])
    
    header = f"🔐 <b>{len(otp_list)} New OTPs Received</b>\n\n"
    
    messages = []
    for i, otp_data in enumerate(otp_list, 1):
        otp = otp_data.get('otp', 'N/A')
        phone = otp_data.get('phone', 'N/A')
        service = otp_data.get('service', 'Unknown')
        
        msg = f"<b>{i}.</b> <code>{otp}</code> | {service} | <code>{phone}</code>"
        messages.append(msg)
    
    footer = "\n\n<i>Tap any OTP to copy it!</i>"
    
    return header + "\n".join(messages) + footer

def extract_otp_from_text(text):
    """Extract OTP code from SMS text using various patterns"""
    if not text:
        return None
    
    patterns = [
        r'\b(\d{6})\b',  # 6-digit codes
        r'\b(\d{5})\b',  # 5-digit codes
        r'\b(\d{4})\b',  # 4-digit codes
        r'code[:\s]*(\d+)',  # "code: 123456"
        r'verification[:\s]*(\d+)',  # "verification: 123456"
        r'otp[:\s]*(\d+)',  # "otp: 123456"
        r'pin[:\s]*(\d+)',  # "pin: 123456"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None

def clean_phone_number(phone):
    """Clean and format phone number"""
    if not phone:
        return "N/A"
    
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    if cleaned and not cleaned.startswith('+'):
        if cleaned.startswith('88'):  # Bangladesh numbers
            cleaned = '+' + cleaned
        elif len(cleaned) >= 10:
            cleaned = '+' + cleaned
    
    return cleaned or phone

def clean_service_name(service):
    """Clean and format service name"""
    if not service:
        return "Unknown"
    
    cleaned = service.strip().title()
    
    service_mappings = {
        'fb': 'Facebook',
        'google': 'Google',
        'whatsapp': 'WhatsApp',
        'telegram': 'Telegram',
        'instagram': 'Instagram',
        'twitter': 'Twitter',
        'linkedin': 'LinkedIn',
        'tiktok': 'TikTok',
        'snapchat': 'Snapchat',
        'discord': 'Discord'
    }
    
    service_lower = cleaned.lower()
    for key, value in service_mappings.items():
        if key in service_lower:
            return value
    
    return cleaned

def get_status_message(stats):
    """Generate status message for bot health check"""
    uptime = stats.get('uptime', 'Unknown')
    total_otps = stats.get('total_otps_sent', 0)
    last_check = stats.get('last_check', 'Never')
    cache_size = stats.get('cache_size', 0)
    
    return f"""🤖 <b>Bot Status</b>

⚡ Status: <b>Online</b>
⏱️ Uptime: {uptime}
📨 Total OTPs Sent: <b>{total_otps}</b>
🔍 Last Check: {last_check}
💾 Cache Size: {cache_size} items

<i>Bot is running and monitoring for new OTPs</i>"""

# ================================
# OTP FILTER CLASS
# ================================

class OTPFilter:
    """Manages OTP filtering to prevent duplicates"""
    
    def __init__(self, cache_file='otp_cache.json', expire_minutes=30):
        self.cache_file = cache_file
        self.expire_minutes = expire_minutes
        self.cache = self._load_cache()
    
    def _load_cache(self):
        """Load existing cache from file"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return {}
    
    def _save_cache(self):
        """Save cache to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def _cleanup_expired(self):
        """Remove expired entries from cache"""
        current_time = datetime.now()
        expired_keys = []
        
        for key, entry in self.cache.items():
            try:
                entry_time = datetime.fromisoformat(entry['timestamp'])
                if current_time - entry_time > timedelta(minutes=self.expire_minutes):
                    expired_keys.append(key)
            except (KeyError, ValueError):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
    
    def _generate_key(self, otp_data):
        """Generate unique key for OTP entry"""
        otp = otp_data.get('otp', '')
        phone = otp_data.get('phone', '')
        service = otp_data.get('service', '')
        return f"{otp}_{phone}_{service}"
    
    def is_duplicate(self, otp_data):
        """Check if OTP has been processed recently"""
        self._cleanup_expired()
        key = self._generate_key(otp_data)
        return key in self.cache
    
    def add_otp(self, otp_data):
        """Add OTP to cache to mark as processed"""
        key = self._generate_key(otp_data)
        self.cache[key] = {
            'timestamp': datetime.now().isoformat(),
            'otp': otp_data.get('otp', ''),
            'phone': otp_data.get('phone', ''),
            'service': otp_data.get('service', '')
        }
        self._save_cache()
    
    def filter_new_otps(self, otp_list):
        """Filter out duplicate OTPs from a list"""
        new_otps = []
        
        for otp_data in otp_list:
            if not self.is_duplicate(otp_data):
                new_otps.append(otp_data)
                self.add_otp(otp_data)
        
        return new_otps
    
    def get_cache_stats(self):
        """Get statistics about cached OTPs"""
        self._cleanup_expired()
        return {
            'total_cached': len(self.cache),
            'cache_file': self.cache_file,
            'expire_minutes': self.expire_minutes
        }
    
    def clear_cache(self):
        """Clear all cached OTPs"""
        self.cache = {}
        self._save_cache()
        return "Cache cleared successfully"

# ================================
# IVASMS SCRAPER CLASS
# ================================

class IVASMSScraper:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.base_url = "https://www.ivasms.com"
        self.is_logged_in = False

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

    def login(self):
        try:
            login_url = f"{self.base_url}/login"
            response = self.session.get(login_url)
            if response.status_code != 200:
                logger.error("Login page unreachable.")
                return False

            soup = BeautifulSoup(response.content, 'html.parser')
            csrf_input = soup.find('input', {'name': '_token'})
            csrf_token = csrf_input.get('value', '') if csrf_input else ''

            login_data = {
                'email': self.email,
                'password': self.password,
                '_token': csrf_token
            }

            login_response = self.session.post(login_url, data=login_data)
            if login_response.status_code == 200 and "logout" in login_response.text.lower():
                self.is_logged_in = True
                logger.info("✅ Login successful")
                return True

            logger.error("❌ Login failed")
            return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    def fetch_messages(self):
        if not self.is_logged_in:
            if not self.login():
                return []

        try:
            url = f"{self.base_url}/portal/live/my_sms"
            response = self.session.get(url)
            if response.status_code != 200:
                logger.error("Failed to load SMS page.")
                return []

            soup = BeautifulSoup(response.content, 'html.parser')
            return self._extract_messages(soup)
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            return []

    def _extract_messages(self, soup):
        messages = []

        # Try different table structures
        rows = soup.find_all('tr')
        for row in rows[1:]:  # Skip header row
            cells = row.find_all('td')
            if len(cells) < 3:
                continue

            phone = clean_phone_number(cells[0].text)
            service = clean_service_name(cells[1].text)
            raw_text = cells[2].text.strip()
            otp = extract_otp_from_text(raw_text)

            if otp:
                messages.append({
                    'otp': otp,
                    'phone': phone or "N/A",
                    'service': service or "Unknown",
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'raw_message': raw_text
                })

        return messages

# ================================
# TELEGRAM BOT CLASS
# ================================

class TelegramOTPBot:
    def __init__(self, token, group_id):
        self.token = token
        self.group_id = group_id
        self.bot = Bot(token=token)
        self.start_time = datetime.now()


    async def send_otp_message(self, otp_data):
        """Send OTP message to Telegram group"""
        try:
            message = format_otp_message(otp_data)
            await self.bot.send_message(
                chat_id=self.group_id,
                text=message,
                parse_mode='HTML'
            )
            return True
        except Exception as e:
            logger.error(f"Error sending OTP message: {e}")
            return False

    async def send_multiple_otps(self, otp_list):
        """Send multiple OTPs in a single message"""
        try:
            message = format_multiple_otps(otp_list)
            await self.bot.send_message(
                chat_id=self.group_id,
                text=message,
                parse_mode='HTML'
            )
            return True
        except Exception as e:
            logger.error(f"Error sending multiple OTPs: {e}")
            return False

    async def send_test_message(self):
        """Send a test message to verify bot functionality"""
        try:
            test_message = """🧪 <b>Test Message</b>

This is a test message to verify that the Telegram OTP Bot is working correctly.

✅ Bot is online and functional
✅ Message formatting is working
✅ Connection to Telegram is established

<i>Test completed successfully!</i>"""
            
            await self.bot.send_message(
                chat_id=self.group_id,
                text=test_message,
                parse_mode='HTML'
            )
            return True
        except Exception as e:
            logger.error(f"Error sending test message: {e}")
            return False

# ================================
# MAIN BOT CONTROLLER
# ================================

class OTPBotController:
    def __init__(self):
        self.scraper = None
        self.telegram_bot = None
        self.otp_filter = OTPFilter()
        self.is_running = False
        self.monitor_thread = None
        self.start_time = datetime.now()
        
        # Initialize components
        self._init_scraper()
        self._init_telegram_bot()

    def _init_scraper(self):
        """Initialize IVASMS scraper with error handling"""
        try:
            email = os.environ.get("IVASMS_EMAIL")
            password = os.environ.get("IVASMS_PASSWORD")
            
            if not email or not password:
                logger.warning("IVASMS credentials not found in environment variables. Scraper will not be initialized.")
                logger.debug(f"Email: {'Found' if email else 'Missing'}, Password: {'Found' if password else 'Missing'}")
                return False
            
            self.scraper = IVASMSScraper(email, password)
            logger.info("IVASMS scraper initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize IVASMS scraper: {e}")
            return False

    def _init_telegram_bot(self):
        """Initialize Telegram bot with error handling"""
        try:
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
            group_id = os.environ.get("TELEGRAM_GROUP_ID")
            
            if not token or not group_id:
                logger.warning("Telegram credentials not found in environment variables. Bot will not be initialized.")
                logger.debug(f"Token: {'Found' if token else 'Missing'}, Group ID: {'Found' if group_id else 'Missing'}")
                return False
            
            self.telegram_bot = TelegramOTPBot(token, group_id)
            logger.info("Telegram bot initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            return False

    def start_monitoring(self):
        """Start OTP monitoring in background thread with proper validation"""
        if self.is_running:
            return "Monitoring is already running"
        
        # Check if components are properly initialized
        if not self.scraper:
            logger.error("IVASMS scraper not initialized. Please check your credentials.")
            return "Error: IVASMS scraper not initialized. Please check your IVASMS_EMAIL and IVASMS_PASSWORD environment variables."
        
        if not self.telegram_bot:
            logger.error("Telegram bot not initialized. Please check your credentials.")
            return "Error: Telegram bot not initialized. Please check your TELEGRAM_BOT_TOKEN and TELEGRAM_GROUP_ID environment variables."
        
        try:
            self.is_running = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            
            logger.info("OTP monitoring started successfully")
            return "OTP monitoring started successfully"
        except Exception as e:
            logger.error(f"Failed to start monitoring: {e}")
            self.is_running = False
            return f"Error starting monitoring: {str(e)}"

    def stop_monitoring(self):
        """Stop OTP monitoring"""
        self.is_running = False
        logger.info("OTP monitoring stopped")
        return "OTP monitoring stopped"

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_running:
            try:
                # Fetch messages from IVASMS
                messages = self.scraper.fetch_messages()
                
                if messages:
                    # Filter new OTPs
                    new_otps = self.otp_filter.filter_new_otps(messages)
                    
                    if new_otps:
                        # Log OTPs to database
                        self._log_otps_to_db(new_otps)
                        
                        # Send to Telegram
                        if len(new_otps) == 1:
                            asyncio.run(self.telegram_bot.send_otp_message(new_otps[0]))
                        else:
                            asyncio.run(self.telegram_bot.send_multiple_otps(new_otps))
                        
                        logger.info(f"Sent {len(new_otps)} new OTPs to Telegram")
                
                # Update statistics
                self._update_stats()
                
                # Wait before next check
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)  # Wait longer on error

    def _log_otps_to_db(self, otp_list):
        """Log OTPs to database"""
        try:
            with app.app_context():
                for otp_data in otp_list:
                    otp_log = OTPLog(
                        otp_code=otp_data.get('otp', ''),
                        phone_number=otp_data.get('phone', ''),
                        service_name=otp_data.get('service', ''),
                        raw_message=otp_data.get('raw_message', ''),
                        sent_to_telegram=True
                    )
                    db.session.add(otp_log)
                
                db.session.commit()
        except Exception as e:
            logger.error(f"Error logging OTPs to database: {e}")

    def _update_stats(self):
        """Update bot statistics"""
        try:
            with app.app_context():
                # Update last check time
                last_check_stat = db.session.query(BotStats).filter_by(stat_name='last_check').first()
                if last_check_stat:
                    last_check_stat.stat_value = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    last_check_stat.last_updated = datetime.utcnow()
                else:
                    last_check_stat = BotStats(
                        stat_name='last_check',
                        stat_value=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    )
                    db.session.add(last_check_stat)
                
                db.session.commit()
        except Exception as e:
            logger.error(f"Error updating statistics: {e}")

    def get_stats(self):
        """Get bot statistics"""
        try:
            with app.app_context():
                total_otps = db.session.query(OTPLog).count()
                sent_otps = db.session.query(OTPLog).filter_by(sent_to_telegram=True).count()
                
                uptime = datetime.now() - self.start_time
                uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m"
                
                last_check_stat = db.session.query(BotStats).filter_by(stat_name='last_check').first()
                last_check = last_check_stat.stat_value if last_check_stat else 'Never'
                
                cache_stats = self.otp_filter.get_cache_stats()
                
                return {
                    'is_running': self.is_running,
                    'uptime': uptime_str,
                    'total_otps_logged': total_otps,
                    'total_otps_sent': sent_otps,
                    'last_check': last_check,
                    'cache_size': cache_stats['total_cached']
                }
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}

    async def send_test_message(self):
        """Send test message through Telegram bot"""
        if not self.telegram_bot:
            return False
        return await self.telegram_bot.send_test_message()

    def check_for_otps_manually(self):
        """Manually check for new OTPs with detailed status reporting"""
        try:
            if not self.scraper:
                logger.warning("Manual check requested but scraper not initialized")
                return "❌ Error: IVASMS scraper not initialized. Please check credentials."
            
            logger.info("Manual OTP check initiated")
            messages = self.scraper.fetch_messages()
            new_otps = self.otp_filter.filter_new_otps(messages)
            
            if new_otps:
                logger.info(f"Processing {len(new_otps)} new OTPs")
                self._log_otps_to_db(new_otps)
                
                if self.telegram_bot:
                    success = False
                    if len(new_otps) == 1:
                        success = asyncio.run(self.telegram_bot.send_otp_message(new_otps[0]))
                    else:
                        success = asyncio.run(self.telegram_bot.send_multiple_otps(new_otps))
                    
                    if success:
                        return f"✅ Found and sent {len(new_otps)} new OTPs to Telegram"
                    else:
                        return f"⚠️ Found {len(new_otps)} new OTPs but failed to send to Telegram"
                else:
                    return f"⚠️ Found {len(new_otps)} new OTPs but Telegram bot not initialized"
            else:
                return "✅ Check completed - No new OTPs found (might be duplicates)"
                
        except Exception as e:
            logger.error(f"Error in manual OTP check: {e}")
            return f"❌ Error checking for OTPs: {str(e)}"

# ================================
# GLOBAL BOT INSTANCE
# ================================

# This will be initialized after database setup
bot_controller = None

# ================================
# FLASK ROUTES
# ================================

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """Get bot status and statistics"""
    if bot_controller is None:
        return jsonify({
            'error': 'Bot controller not initialized',
            'is_running': False,
            'uptime': '0d 0h 0m',
            'total_otps_logged': 0,
            'total_otps_sent': 0,
            'last_check': 'Never',
            'cache_size': 0
        })
    
    stats = bot_controller.get_stats()
    return jsonify(stats)

@app.route('/api/start', methods=['POST'])
def api_start():
    """Start OTP monitoring"""
    if bot_controller is None:
        return jsonify({'message': 'Bot controller not initialized', 'success': False})
    
    result = bot_controller.start_monitoring()
    success = not result.startswith('Error')
    return jsonify({'message': result, 'success': success})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Stop OTP monitoring"""
    if bot_controller is None:
        return jsonify({'message': 'Bot controller not initialized', 'success': False})
    
    result = bot_controller.stop_monitoring()
    return jsonify({'message': result, 'success': True})

@app.route('/api/test', methods=['POST'])
def api_test():
    """Send test message"""
    if bot_controller is None:
        return jsonify({'message': 'Bot controller not initialized', 'success': False})
    
    try:
        result = asyncio.run(bot_controller.send_test_message())
        return jsonify({
            'message': 'Test message sent successfully' if result else 'Failed to send test message',
            'success': result
        })
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}', 'success': False})

@app.route('/api/check', methods=['POST'])
def api_check():
    """Manually check for OTPs"""
    if bot_controller is None:
        return jsonify({'message': 'Bot controller not initialized', 'success': False})
    
    result = bot_controller.check_for_otps_manually()
    success = not result.startswith('❌')
    return jsonify({'message': result, 'success': success})

@app.route('/api/clear-cache', methods=['POST'])
def api_clear_cache():
    """Clear OTP cache"""
    if bot_controller is None:
        return jsonify({'message': 'Bot controller not initialized', 'success': False})
    
    result = bot_controller.otp_filter.clear_cache()
    return jsonify({'message': result, 'success': True})

@app.route('/api/logs')
def api_logs():
    """Get recent OTP logs"""
    try:
        logs = db.session.query(OTPLog).order_by(OTPLog.timestamp.desc()).limit(20).all()
        log_data = []
        
        for log in logs:
            log_data.append({
                'id': log.id,
                'otp_code': log.otp_code,
                'phone_number': log.phone_number,
                'service_name': log.service_name,
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'sent_to_telegram': log.sent_to_telegram
            })
        
        return jsonify({'logs': log_data, 'success': True})
    except Exception as e:
        logger.error(f"Error fetching logs: {e}")
        return jsonify({'logs': [], 'success': False, 'error': str(e)})

@app.route('/api/debug')
def api_debug():
    """Debug information for troubleshooting"""
    debug_info = {
        'python_version': f"{sys.version}",
        'flask_app_running': True,
        'environment_variables': {
            'TELEGRAM_BOT_TOKEN': 'Found' if os.environ.get('TELEGRAM_BOT_TOKEN') else 'Missing',
            'TELEGRAM_GROUP_ID': 'Found' if os.environ.get('TELEGRAM_GROUP_ID') else 'Missing',
            'IVASMS_EMAIL': 'Found' if os.environ.get('IVASMS_EMAIL') else 'Missing',
            'IVASMS_PASSWORD': 'Found' if os.environ.get('IVASMS_PASSWORD') else 'Missing',
            'DATABASE_URL': 'Found' if os.environ.get('DATABASE_URL') else 'Missing',
            'DEBUG': os.environ.get('DEBUG', '0')
        },
        'bot_controller_status': 'Initialized' if bot_controller else 'Not Initialized',
        'database_status': 'Connected',
        'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'log_level': logging.getLevelName(logger.level)
    }
    
    if bot_controller:
        debug_info['scraper_status'] = 'Initialized' if bot_controller.scraper else 'Not Initialized'
        debug_info['telegram_bot_status'] = 'Initialized' if bot_controller.telegram_bot else 'Not Initialized'
        debug_info['monitoring_status'] = 'Running' if bot_controller.is_running else 'Stopped'
    
    return jsonify(debug_info)

# ================================
# APP INITIALIZATION
# ================================

# Initialize database and bot controller
bot_controller = None

try:
    with app.app_context():
        db.create_all()
        logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Database initialization failed: {e}")

# Initialize bot controller after database setup
try:
    bot_controller = OTPBotController()
    logger.info("Bot controller initialized successfully")
except Exception as e:
    logger.error(f"Bot controller initialization failed: {e}")
    logger.debug("This might be due to missing environment variables or network issues")
    bot_controller = None

# Auto-start monitoring if credentials are available and bot controller is initialized
if bot_controller and (os.environ.get("TELEGRAM_BOT_TOKEN") and 
    os.environ.get("TELEGRAM_GROUP_ID") and 
    os.environ.get("IVASMS_EMAIL") and 
    os.environ.get("IVASMS_PASSWORD")):
    
    # Start monitoring in a separate thread after a short delay
    def delayed_start():
        try:
            time.sleep(5)  # Wait 5 seconds for app to fully initialize
            result = bot_controller.start_monitoring()
            logger.info(f"Auto-start result: {result}")
        except Exception as e:
            logger.error(f"Auto-start failed: {e}")
    
    threading.Thread(target=delayed_start, daemon=True).start()
    logger.info("Auto-starting OTP monitoring...")
else:
    logger.warning("Auto-start disabled: Missing credentials or bot controller not initialized")
    if not bot_controller:
        logger.error("Bot controller is None - check initialization errors above")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
