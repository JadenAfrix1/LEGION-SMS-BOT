import re
from datetime import datetime

def format_otp_message(otp_data):
    """
    Format OTP data for Telegram with touch-to-copy functionality
    
    Args:
        otp_data (dict): Dictionary containing 'otp', 'phone', 'service', 'timestamp'
    
    Returns:
        str: Formatted HTML message for Telegram
    """
    otp = otp_data.get('otp', 'N/A')
    phone = otp_data.get('phone', 'N/A')
    service = otp_data.get('service', 'Unknown')
    timestamp = otp_data.get('timestamp', datetime.now().strftime('%H:%M:%S'))
    
    # Format the message with HTML for touch-to-copy OTP
    message = f"""🔐 <b>New OTP Received</b>

🔢 OTP: <code>{otp}</code>
📱 Number: <code>{phone}</code>
🌐 Service: <b>{service}</b>
⏰ Time: {timestamp}

<i>Tap the OTP to copy it!</i>"""
    
    return message

def format_multiple_otps(otp_list):
    """
    Format multiple OTPs into a single message
    
    Args:
        otp_list (list): List of OTP dictionaries
    
    Returns:
        str: Formatted HTML message for Telegram
    """
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
    """
    Extract OTP code from SMS text using various patterns
    
    Args:
        text (str): SMS text content
    
    Returns:
        str or None: Extracted OTP code
    """
    if not text:
        return None
    
    # Common OTP patterns
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
    """
    Clean and format phone number
    
    Args:
        phone (str): Raw phone number
    
    Returns:
        str: Cleaned phone number
    """
    if not phone:
        return "N/A"
    
    # Remove common prefixes and clean
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Ensure it starts with +
    if cleaned and not cleaned.startswith('+'):
        if cleaned.startswith('88'):  # Bangladesh numbers
            cleaned = '+' + cleaned
        elif len(cleaned) >= 10:
            cleaned = '+' + cleaned
    
    return cleaned or phone

def clean_service_name(service):
    """
    Clean and format service name
    
    Args:
        service (str): Raw service name
    
    Returns:
        str: Cleaned service name
    """
    if not service:
        return "Unknown"
    
    # Clean and capitalize
    cleaned = service.strip().title()
    
    # Handle common service names
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

def sanitize_for_telegram(text):
    """
    Sanitize text for Telegram HTML parsing
    
    Args:
        text (str): Raw text
    
    Returns:
        str: Sanitized text safe for Telegram HTML
    """
    if not text:
        return ""
    
    # Escape HTML characters
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    
    return text

def truncate_message(message, max_length=4096):
    """
    Truncate message to Telegram's limit
    
    Args:
        message (str): Message to truncate
        max_length (int): Maximum message length
    
    Returns:
        str: Truncated message
    """
    if len(message) <= max_length:
        return message
    
    truncated = message[:max_length - 50]
    return truncated + "\n\n<i>... (message truncated)</i>"

def get_status_message(stats):
    """
    Generate status message for bot health check
    
    Args:
        stats (dict): Bot statistics
    
    Returns:
        str: Formatted status message
    """
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
