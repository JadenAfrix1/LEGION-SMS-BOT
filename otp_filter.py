import json
import os
from datetime import datetime, timedelta

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
            print(f"Error saving cache: {e}")
    
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
        # Use OTP code + phone number as unique identifier
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

# Global filter instance
otp_filter = OTPFilter()
