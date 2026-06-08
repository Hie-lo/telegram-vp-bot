import requests
from typing import Optional, Dict
from datetime import datetime, timedelta
import config

class PasarGuardAPI:
    def __init__(self):
        self.base_url = config.PASARGUARD_URL.rstrip('/')
        self.username = config.PASARGUARD_USERNAME
        self.password = config.PASARGUARD_PASSWORD
        self.token = None
        self.token_expiry = None
    
    def _login(self) -> bool:
        """Login to panel and get JWT token"""
        try:
            # ابتدا با متد POST امتحان می‌کنیم
            url = f"{self.base_url}/api/admin/token"
            print(f"🔄 Trying POST to {url}")
            
            response = requests.post(
                url,
                data={
                    "username": self.username,
                    "password": self.password
                },
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                timeout=10,
                verify=False
            )
            
            # اگر POST جواب نداد، با GET امتحان می‌کنیم
            if response.status_code == 405:
                print("⚠️ POST not allowed, trying GET...")
                response = requests.get(
                    url,
                    params={
                        "username": self.username,
                        "password": self.password
                    },
                    headers={"accept": "application/json"},
                    timeout=10,
                    verify=False
                )
            
            print(f"📡 Response status: {response.status_code}")
            print(f"📄 Response body: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access_token')
                self.token_expiry = datetime.now() + timedelta(hours=23)
                print("✅ Login successful")
                return True
            else:
                print(f"Login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def _ensure_token(self) -> bool:
        """Ensure token is valid, refresh if needed"""
        if not self.token or datetime.now() >= self.token_expiry:
            return self._login()
        return True
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make authenticated request to panel API"""
        if not self._ensure_token():
            return None
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 401:
                if self._login():
                    headers["Authorization"] = f"Bearer {self.token}"
                    response = requests.request(
                        method=method, url=url, headers=headers, json=data, timeout=30
                    )
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                print(f"API Error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Request error: {e}")
            return None
    
    def create_user(self, traffic_gb: int, expire_days: int, username: str = None) -> Optional[Dict]:
        """Create a new user in PasarGuard panel"""
        if username is None:
            username = f"user_{datetime.now().timestamp()}"
        
        # حجم به بایت
        data_limit_bytes = traffic_gb * 1024 * 1024 * 1024
        
        # زمان انقضا به صورت timestamp (ثانیه) از UTC
        expire_timestamp = int((datetime.now() + timedelta(days=expire_days)).timestamp())
        
        payload = {
            "username": username,
            "data_limit": data_limit_bytes,
            "expire": expire_timestamp,
            "status": "active",
            "data_limit_reset_strategy": "no_reset",
            "group_ids": [9,8]
            #15 , 9 , 8
        }
        
        print(f"📤 Sending: {traffic_gb}GB = {data_limit_bytes} bytes, expire timestamp: {expire_timestamp}")
        
        result = self._make_request("POST", "/api/user", payload)
        
        if result and 'subscription_url' in result:
            return {
                "config_link": result['subscription_url'],
                "username": result.get('username', username),
                "success": True
            }
        
        print(f"API Error: {result}")
        return None
        
    def create_test_user(self) -> Optional[Dict]:
        # 30 دقیقه = 0.020833 روز
        expire_days = 30 / (24 * 60)  # 30 / 1440 = 0.020833...
        return self.create_user(traffic_gb=1, expire_days=expire_days, username=f"test_{datetime.now().timestamp()}")