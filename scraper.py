import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
from utils import extract_otp_from_text, clean_phone_number, clean_service_name

class IVASMSScraper:
    """Scraper for IVASMS.com to fetch OTPs and messages"""
    
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.base_url = "https://www.ivasms.com"
        self.is_logged_in = False
        
        # Set headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
    
    def login(self):
        """Login to IVASMS account"""
        try:
            print(f"Attempting to login to IVASMS with email: {self.email}")
            
            # Get login page first
            login_url = f"{self.base_url}/login"
            response = self.session.get(login_url)
            
            if response.status_code != 200:
                print(f"Failed to access login page. Status: {response.status_code}")
                return False
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find CSRF token if present
            csrf_token = None
            csrf_input = soup.find('input', {'name': '_token'})
            if csrf_input:
                csrf_token = csrf_input.get('value')
            
            # Prepare login data
            login_data = {
                'email': self.email,
                'password': self.password,
            }
            
            if csrf_token:
                login_data['_token'] = csrf_token
            
            # Submit login form
            login_response = self.session.post(login_url, data=login_data)
            
            # Check if login was successful
            if login_response.status_code == 200:
                # Look for dashboard or account indicators
                if 'dashboard' in login_response.url.lower() or 'account' in login_response.url.lower():
                    self.is_logged_in = True
                    print("Successfully logged in to IVASMS")
                    return True
                
                # Check page content for login success indicators
                soup = BeautifulSoup(login_response.content, 'html.parser')
                if soup.find(text=re.compile(r'dashboard|account|logout', re.I)):
                    self.is_logged_in = True
                    print("Successfully logged in to IVASMS")
                    return True
            
            print("Login failed - invalid credentials or site structure changed")
            return False
            
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def fetch_messages(self):
        """Fetch recent messages/OTPs from account"""
        if not self.is_logged_in:
            if not self.login():
                return []
        
        try:
            # Common paths for SMS/message history
            possible_paths = [
                '/messages',
                '/sms',
                '/history',
                '/dashboard',
                '/account',
                '/numbers'
            ]
            
            messages = []
            
            for path in possible_paths:
                try:
                    url = f"{self.base_url}{path}"
                    response = self.session.get(url)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        page_messages = self._extract_messages_from_page(soup)
                        if page_messages:
                            messages.extend(page_messages)
                            print(f"Found {len(page_messages)} messages on {path}")
                            break
                except Exception as e:
                    continue
            
            if not messages:
                # Try to find any SMS-like content on the main page
                dashboard_response = self.session.get(f"{self.base_url}/dashboard")
                if dashboard_response.status_code == 200:
                    soup = BeautifulSoup(dashboard_response.content, 'html.parser')
                    messages = self._extract_messages_from_page(soup)
            
            return messages
            
        except Exception as e:
            print(f"Error fetching messages: {e}")
            return []
    
    def _extract_messages_from_page(self, soup):
        """Extract message data from a BeautifulSoup page object"""
        messages = []
        
        try:
            # Look for common table/list structures containing SMS data
            # Try different selectors that might contain SMS messages
            
            # Method 1: Look for tables with SMS data
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')[1:]  # Skip header row
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 3:  # Minimum columns for phone, service, message
                        message_data = self._extract_message_from_row(cells)
                        if message_data:
                            messages.append(message_data)
            
            # Method 2: Look for div containers with message data
            message_divs = soup.find_all('div', class_=re.compile(r'message|sms|otp', re.I))
            for div in message_divs:
                message_data = self._extract_message_from_div(div)
                if message_data:
                    messages.append(message_data)
            
            # Method 3: Look for any text that looks like OTP messages
            text_content = soup.get_text()
            potential_otps = re.findall(r'\b\d{4,6}\b', text_content)
            if potential_otps:
                # Try to extract context around OTPs
                for otp in potential_otps[:5]:  # Limit to first 5 to avoid spam
                    message_data = {
                        'otp': otp,
                        'phone': self._extract_phone_from_context(text_content, otp),
                        'service': self._extract_service_from_context(text_content, otp),
                        'timestamp': datetime.now().strftime('%H:%M:%S'),
                        'raw_message': f"OTP: {otp}"
                    }
                    messages.append(message_data)
            
        except Exception as e:
            print(f"Error extracting messages from page: {e}")
        
        return messages
    
    def _extract_message_from_row(self, cells):
        """Extract message data from table row cells"""
        try:
            if len(cells) < 3:
                return None
            
            # Common table structures:
            # [Phone, Service, Message, Time] or [Time, Phone, Service, Message]
            
            phone = ""
            service = ""
            message = ""
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            # Try to identify columns based on content
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                
                # Phone number detection
                if re.search(r'\+?\d{10,15}', cell_text):
                    phone = clean_phone_number(cell_text)
                
                # Service name detection
                elif re.search(r'facebook|google|instagram|twitter|whatsapp|telegram|discord', cell_text, re.I):
                    service = clean_service_name(cell_text)
                
                # Message content (usually longest text)
                elif len(cell_text) > 20:
                    message = cell_text
                
                # Time detection
                elif re.search(r'\d{1,2}:\d{2}', cell_text):
                    timestamp = cell_text
            
            # Extract OTP from message
            otp = extract_otp_from_text(message)
            
            if otp:
                return {
                    'otp': otp,
                    'phone': phone or "N/A",
                    'service': service or "Unknown",
                    'timestamp': timestamp,
                    'raw_message': message
                }
        
        except Exception as e:
            print(f"Error extracting from row: {e}")
        
        return None
    
    def _extract_message_from_div(self, div):
        """Extract message data from div container"""
        try:
            text = div.get_text(strip=True)
            
            # Extract OTP
            otp = extract_otp_from_text(text)
            if not otp:
                return None
            
            # Extract phone
            phone_match = re.search(r'\+?\d{10,15}', text)
            phone = clean_phone_number(phone_match.group()) if phone_match else "N/A"
            
            # Extract service
            service_match = re.search(r'(facebook|google|instagram|twitter|whatsapp|telegram|discord)', text, re.I)
            service = clean_service_name(service_match.group()) if service_match else "Unknown"
            
            return {
                'otp': otp,
                'phone': phone,
                'service': service,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'raw_message': text
            }
        
        except Exception as e:
            print(f"Error extracting from div: {e}")
        
        return None
    
    def _extract_phone_from_context(self, text, otp):
        """Extract phone number from context around OTP"""
        # Look for phone numbers near the OTP
        otp_index = text.find(otp)
        if otp_index != -1:
            context = text[max(0, otp_index-100):otp_index+100]
            phone_match = re.search(r'\+?\d{10,15}', context)
            if phone_match:
                return clean_phone_number(phone_match.group())
        return "N/A"
    
    def _extract_service_from_context(self, text, otp):
        """Extract service name from context around OTP"""
        # Look for service names near the OTP
        otp_index = text.find(otp)
        if otp_index != -1:
            context = text[max(0, otp_index-100):otp_index+100].lower()
            services = ['facebook', 'google', 'instagram', 'twitter', 'whatsapp', 'telegram', 'discord']
            for service in services:
                if service in context:
                    return clean_service_name(service)
        return "Unknown"
    
    def test_connection(self):
        """Test connection to IVASMS"""
        try:
            response = self.session.get(self.base_url)
            return response.status_code == 200
        except:
            return False

def create_scraper(email, password):
    """Factory function to create and test scraper"""
    scraper = IVASMSScraper(email, password)
    
    if not scraper.test_connection():
        print("Warning: Cannot connect to IVASMS.com")
        return None
    
    return scraper

# Demo/test function
def test_scraper():
    """Test the scraper with dummy data"""
    # This is for testing only - replace with real credentials
    email = "tawandamahachi07@gmail.com"
    password = "mahachi2007"
    
    scraper = create_scraper(email, password)
    if scraper:
        messages = scraper.fetch_messages()
        print(f"Found {len(messages)} messages")
        for msg in messages:
            print(f"OTP: {msg['otp']}, Phone: {msg['phone']}, Service: {msg['service']}")
    else:
        print("Failed to create scraper")

if __name__ == "__main__":
    test_scraper()
