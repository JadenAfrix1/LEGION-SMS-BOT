import os
import asyncio
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template
from dotenv import load_dotenv
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from scraper import create_scraper
from otp_filter import otp_filter
from utils import format_otp_message, format_multiple_otps, get_status_message
import threading
import time

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')
IVASMS_EMAIL = os.getenv('IVASMS_EMAIL')
IVASMS_PASSWORD = os.getenv('IVASMS_PASSWORD')
# Telegram webhook secret token must be 1-256 characters, only A-Z, a-z, 0-9, _ and -
WEBHOOK_TOKEN = os.getenv('WEBHOOK_TOKEN', 'webhook_' + str(abs(hash(BOT_TOKEN)))[:12] if BOT_TOKEN else 'webhook_fallback123')
ADMIN_TOKEN = os.getenv('ADMIN_TOKEN', 'admin_' + str(abs(hash(BOT_TOKEN)))[:12] if BOT_TOKEN else 'admin_fallback123')

# Bot statistics
bot_stats = {
    'start_time': datetime.now(),
    'total_otps_sent': 0,
    'last_check': 'Never',
    'last_error': None,
    'is_running': False
}

# Global bot instances
bot = None
telegram_app = None
scraper = None

# Telegram Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = """🤖 <b>Telegram OTP Bot</b>

🎯 <b>Available Commands:</b>
/start - Show this help message
/status - Show bot status and statistics
/check - Manually check for new OTPs
/test - Send a test OTP message
/stats - Show detailed statistics

🔐 <b>What I do:</b>
• Monitor IVASMS.com for new OTPs
• Send formatted OTPs to the group
• Prevent duplicate notifications
• Run 24/7 with automatic monitoring

📊 <b>Current Status:</b>
Bot is running and monitoring every 60 seconds.

💡 <b>Need help?</b> Contact the bot administrator."""

    await update.message.reply_text(welcome_message, parse_mode='HTML')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    uptime = datetime.now() - bot_stats['start_time']
    uptime_str = str(uptime).split('.')[0]
    
    cache_stats = otp_filter.get_cache_stats()
    
    status_data = {
        'uptime': uptime_str,
        'total_otps_sent': bot_stats['total_otps_sent'],
        'last_check': bot_stats['last_check'],
        'cache_size': cache_stats['total_cached'],
        'monitor_running': bot_stats['is_running']
    }
    
    status_msg = get_status_message(status_data)
    await update.message.reply_text(status_msg, parse_mode='HTML')

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /check command - manually check for OTPs"""
    await update.message.reply_text("🔍 <b>Checking for new OTPs...</b>", parse_mode='HTML')
    
    try:
        # Run check in thread to avoid blocking
        import threading
        check_thread = threading.Thread(target=check_and_send_otps)
        check_thread.start()
        check_thread.join(timeout=10)  # Wait max 10 seconds
        
        await update.message.reply_text(
            "✅ <b>OTP check completed!</b>\n\n"
            f"Last check: {bot_stats['last_check']}\n"
            f"Total OTPs sent: {bot_stats['total_otps_sent']}",
            parse_mode='HTML'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Error during OTP check:</b>\n<code>{str(e)}</code>",
            parse_mode='HTML'
        )

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /test command - send test message"""
    test_otp = {
        'otp': '123456',
        'phone': '+8801234567890',
        'service': 'Test Service',
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'raw_message': 'This is a test OTP message from the bot'
    }
    
    try:
        test_message = format_otp_message(test_otp)
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=test_message,
            parse_mode='HTML'
        )
        await update.message.reply_text(
            "✅ <b>Test message sent to the group!</b>",
            parse_mode='HTML'
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Failed to send test message:</b>\n<code>{str(e)}</code>",
            parse_mode='HTML'
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command - detailed statistics"""
    uptime = datetime.now() - bot_stats['start_time']
    uptime_str = str(uptime).split('.')[0]
    
    cache_stats = otp_filter.get_cache_stats()
    
    stats_message = f"""📊 <b>Detailed Bot Statistics</b>

⏱️ <b>Runtime Information:</b>
• Uptime: {uptime_str}
• Started: {bot_stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}
• Status: {'🟢 Running' if bot_stats['is_running'] else '🔴 Stopped'}

📨 <b>OTP Statistics:</b>
• Total OTPs Sent: {bot_stats['total_otps_sent']}
• Last Check: {bot_stats['last_check']}
• Cache Size: {cache_stats['total_cached']} items
• Cache Expiry: {cache_stats['expire_minutes']} minutes

🔧 <b>System Information:</b>
• IVASMS Account: {IVASMS_EMAIL[:20]}...
• Target Group: {GROUP_ID}
• Check Interval: 60 seconds
• Last Error: {bot_stats['last_error'] or 'None'}

🌐 <b>Endpoints:</b>
• Dashboard: Available
• Manual Check: /check-otp
• Status API: /status"""

    await update.message.reply_text(stats_message, parse_mode='HTML')

def initialize_bot():
    """Initialize Telegram bot and scraper"""
    global bot, telegram_app, scraper
    
    try:
        if not BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
        
        if not GROUP_ID:
            raise ValueError("TELEGRAM_GROUP_ID not found in environment variables")
        
        if not IVASMS_EMAIL or not IVASMS_PASSWORD:
            raise ValueError("IVASMS credentials not found in environment variables")
        
        # Initialize Telegram bot
        bot = Bot(token=BOT_TOKEN)
        
        # Initialize Telegram application with command handlers
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        
        # Add command handlers
        telegram_app.add_handler(CommandHandler("start", start_command))
        telegram_app.add_handler(CommandHandler("status", status_command))
        telegram_app.add_handler(CommandHandler("check", check_command))
        telegram_app.add_handler(CommandHandler("test", test_command))
        telegram_app.add_handler(CommandHandler("stats", stats_command))
        
        logger.info("Telegram bot with commands initialized successfully")
        
        # Initialize scraper
        scraper = create_scraper(IVASMS_EMAIL, IVASMS_PASSWORD)
        if scraper:
            logger.info("IVASMS scraper initialized successfully")
        else:
            logger.warning("Failed to initialize IVASMS scraper")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize bot: {e}")
        bot_stats['last_error'] = str(e)
        return False

def verify_admin_auth():
    """Verify admin authentication from request headers"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return False
    
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        return token == ADMIN_TOKEN
    
    return False

def send_telegram_message(message, parse_mode='HTML', reply_markup=None):
    """Send message to Telegram group with optional markup buttons"""
    try:
        if not bot or not GROUP_ID:
            logger.error("Bot or Group ID not configured")
            return False
        
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # We're in an event loop, use a different approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_send_message_sync, message, parse_mode, reply_markup)
                return future.result(timeout=30)
        except RuntimeError:
            # No event loop running, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                async def send_message():
                    await bot.send_message(
                        chat_id=GROUP_ID,
                        text=message,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                
                loop.run_until_complete(send_message())
                logger.info("Message sent to Telegram successfully")
                return True
            finally:
                loop.close()
        
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        bot_stats['last_error'] = str(e)
        return False

def _send_message_sync(message, parse_mode='HTML', reply_markup=None):
    """Synchronous helper for sending messages from within event loops"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def send_message():
            await bot.send_message(
                chat_id=GROUP_ID,
                text=message,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
        
        loop.run_until_complete(send_message())
        loop.close()
        logger.info("Message sent to Telegram successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send message in sync mode: {e}")
        return False

def setup_webhook():
    """Set up Telegram webhook"""
    try:
        if not bot or not telegram_app:
            logger.error("Bot not initialized, cannot set webhook")
            return False
        
        # Get the public URL for the webhook
        # In Replit, construct the webhook URL properly
        repl_id = os.environ.get('REPL_ID')
        repl_user = os.environ.get('REPL_OWNER', 'user')
        
        if repl_id:
            # Use proper Replit domain format
            webhook_url = f"https://{repl_id}.{repl_user}.replit.app/webhook/{WEBHOOK_TOKEN}"
        else:
            # Fallback for local testing
            webhook_url = f"http://localhost:5000/webhook/{WEBHOOK_TOKEN}"
        
        # Set up webhook with asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def set_webhook_async():
            # Clean the webhook token to only contain allowed characters
            clean_token = ''.join(c for c in WEBHOOK_TOKEN if c.isalnum() or c in '_-')[:256]
            
            await bot.set_webhook(
                url=webhook_url,
                secret_token=clean_token,
                drop_pending_updates=True
            )
            logger.info(f"Webhook set successfully: {webhook_url[:50]}...")
            logger.info(f"Using clean secret token: {clean_token[:10]}...")
        
        loop.run_until_complete(set_webhook_async())
        loop.close()
        return True
        
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        return False

def start_telegram_bot():
    """Start the Telegram bot command handlers"""
    if telegram_app:
        logger.info("Telegram command handlers initialized and ready")
        logger.info("Setting up webhook...")
        
        # Try to set up webhook if running in production
        if os.environ.get('REPL_ID'):
            setup_webhook()
        else:
            logger.info("Running locally, skipping webhook setup")

def check_and_send_otps():
    """Check for new OTPs and send to Telegram with improved error handling"""
    global bot_stats
    
    try:
        if not scraper:
            logger.error("Scraper not initialized")
            return
        
        # Fetch messages from IVASMS with timeout handling
        logger.info("Checking for new OTPs...")
        
        # Add retry logic for network issues
        max_retries = 3
        retry_delay = 2
        messages = None
        
        for attempt in range(max_retries):
            try:
                messages = scraper.fetch_messages()
                break  # Success, exit retry loop
            except Exception as e:
                logger.warning(f"OTP fetch attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    raise  # Re-raise on final attempt
        
        bot_stats['last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if not messages:
            logger.info("No messages found")
            return
        
        # Filter out duplicates
        new_messages = otp_filter.filter_new_otps(messages)
        
        if not new_messages:
            logger.info("No new OTPs found (all were duplicates)")
            return
        
        logger.info(f"Found {len(new_messages)} new OTPs")
        
        # Create beautiful markup buttons for channel and group
        keyboard = [
            [
                InlineKeyboardButton("📡 Join Channel", url="https://t.me/cybixtech"),
                InlineKeyboardButton("💬 OTP Group", url="https://t.me/legionsms")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send messages to Telegram with beautiful buttons
        if len(new_messages) == 1:
            message = format_otp_message(new_messages[0])
        else:
            message = format_multiple_otps(new_messages)
        
        if send_telegram_message(message, reply_markup=reply_markup):
            bot_stats['total_otps_sent'] += len(new_messages)
            logger.info(f"Successfully sent {len(new_messages)} OTPs to Telegram with markup buttons")
        else:
            logger.error("Failed to send OTPs to Telegram")
        
    except Exception as e:
        logger.error(f"Error in check_and_send_otps: {e}")
        bot_stats['last_error'] = str(e)

def background_monitor():
    """Background thread to monitor for OTPs"""
    global bot_stats
    
    bot_stats['is_running'] = True
    logger.info("Background OTP monitor started")
    
    while bot_stats['is_running']:
        try:
            check_and_send_otps()
            # Wait 60 seconds before next check
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in background monitor: {e}")
            bot_stats['last_error'] = str(e)
            # Wait longer on error
            time.sleep(120)

# Flask routes
@app.route('/')
def home():
    """Home route - serve dashboard or JSON based on Accept header"""
    # Check if request wants HTML (browser) or JSON (API)
    if 'text/html' in request.headers.get('Accept', ''):
        # Serve HTML dashboard for browsers
        return render_template('dashboard.html')
    
    # Serve JSON for API calls
    uptime = datetime.now() - bot_stats['start_time']
    uptime_str = str(uptime).split('.')[0]  # Remove microseconds
    
    status = {
        'status': 'running',
        'uptime': uptime_str,
        'total_otps_sent': bot_stats['total_otps_sent'],
        'last_check': bot_stats['last_check'],
        'last_error': bot_stats['last_error'],
        'monitor_running': bot_stats['is_running']
    }
    
    return jsonify(status)

@app.route('/check-otp')
def manual_check():
    """Manual OTP check endpoint (admin only)"""
    if not verify_admin_auth():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    try:
        check_and_send_otps()
        return jsonify({
            'status': 'success',
            'message': 'OTP check completed',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/status')
def bot_status():
    """Get detailed bot status"""
    uptime = datetime.now() - bot_stats['start_time']
    uptime_str = str(uptime).split('.')[0]
    
    cache_stats = otp_filter.get_cache_stats()
    
    status = {
        'uptime': uptime_str,
        'total_otps_sent': bot_stats['total_otps_sent'],
        'last_check': bot_stats['last_check'],
        'cache_size': cache_stats['total_cached'],
        'monitor_running': bot_stats['is_running']
    }
    
    message = get_status_message(status)
    
    if request.args.get('send') == 'true':
        # Send status to Telegram
        if send_telegram_message(message):
            return jsonify({'status': 'success', 'message': 'Status sent to Telegram'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to send status'}), 500
    
    return jsonify(status)

@app.route('/test-message')
def test_message():
    """Send test message to Telegram with beautiful buttons"""
    test_msg = """🧪 <b>Test Message</b>

🔢 OTP: <code>123456</code>
📱 Number: <code>+1234567890</code>
🌐 Service: <b>Test Service</b>
⏰ Time: Test Time

<i>This is a test message from the bot!</i>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Powered by @cybixdev</i>"""
    
    # Create beautiful markup buttons for channel and group
    keyboard = [
        [
            InlineKeyboardButton("📡 Join Channel", url="https://t.me/cybixtech"),
            InlineKeyboardButton("💬 OTP Group", url="https://t.me/legionsms")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if send_telegram_message(test_msg, reply_markup=reply_markup):
        return jsonify({'status': 'success', 'message': 'Test message sent with buttons'})
    else:
        return jsonify({'status': 'error', 'message': 'Failed to send test message'}), 500

@app.route('/clear-cache')
def clear_cache():
    """Clear OTP cache"""
    try:
        result = otp_filter.clear_cache()
        return jsonify({'status': 'success', 'message': result})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/webhook/<token>', methods=['POST'])
def webhook(token):
    """Handle Telegram webhook updates with security verification"""
    if not telegram_app:
        return jsonify({'status': 'error', 'message': 'Bot not initialized'}), 500
    
    # Verify webhook token
    if token != WEBHOOK_TOKEN:
        logger.warning(f"Webhook called with invalid token: {token[:10]}...")
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    # Verify Telegram secret token if provided
    telegram_secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    clean_token = ''.join(c for c in WEBHOOK_TOKEN if c.isalnum() or c in '_-')[:256]
    if telegram_secret and telegram_secret != clean_token:
        logger.warning("Webhook called with invalid Telegram secret")
        return jsonify({'status': 'error', 'message': 'Invalid secret'}), 401
    
    try:
        # Get the update from Telegram
        update_data = request.get_json()
        
        # Process the update
        if update_data:
            # Create an asyncio event loop for this thread
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def process_update():
                update = Update.de_json(update_data, telegram_app.bot)
                await telegram_app.process_update(update)
            
            loop.run_until_complete(process_update())
            loop.close()
            
            return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
    return jsonify({'status': 'error', 'message': 'No update data'}), 400

@app.route('/start-monitor')
def start_monitor():
    """Start background monitor (admin only)"""
    if not verify_admin_auth():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    global bot_stats
    
    if bot_stats['is_running']:
        return jsonify({'status': 'info', 'message': 'Monitor already running'})
    
    try:
        monitor_thread = threading.Thread(target=background_monitor, daemon=True)
        monitor_thread.start()
        return jsonify({'status': 'success', 'message': 'Background monitor started'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/stop-monitor')
def stop_monitor():
    """Stop background monitor (admin only)"""
    if not verify_admin_auth():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    global bot_stats
    
    bot_stats['is_running'] = False
    return jsonify({'status': 'success', 'message': 'Background monitor stopped'})

@app.errorhandler(404)
def not_found(error):
    return jsonify({'status': 'error', 'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

def main():
    """Main function to start the bot"""
    logger.info("Starting Telegram OTP Bot...")
    
    # Initialize bot and scraper
    if not initialize_bot():
        logger.error("Failed to initialize bot. Check your configuration.")
        return
    
    # Initialize Telegram command handlers (no polling to avoid threading issues)
    start_telegram_bot()
    
    # Send startup message after Flask server starts
    def send_startup_message():
        time.sleep(2)  # Wait for everything to be ready
        startup_message = """🚀 <b>Bot Started Successfully!</b>

✅ Telegram bot connected
✅ Command handlers active
✅ Webhook configured
🔍 Monitoring for new OTPs...

📋 <b>Available Commands:</b>
/start - Show help and commands
/status - Bot status
/check - Manual OTP check
/test - Send test message
/stats - Detailed statistics

<i>Bot is now running and will automatically send new OTPs to this group.</i>"""
        
        if send_telegram_message(startup_message):
            logger.info("Startup message sent successfully")
        else:
            logger.warning("Failed to send startup message")
    
    # Send startup message in background thread to avoid blocking
    startup_thread = threading.Thread(target=send_startup_message, daemon=True)
    startup_thread.start()
    
    # Start background monitor
    monitor_thread = threading.Thread(target=background_monitor, daemon=True)
    monitor_thread.start()
    
    # Get port for deployment
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    main()
