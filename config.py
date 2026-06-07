import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))
# ADMIN_IDS = [int(id_str) for id_str in os.getenv('ADMIN_IDS', '').split(',') if id_str.strip()]

PASARGUARD_URL = os.getenv('PASARGUARD_URL')
PASARGUARD_USERNAME = os.getenv('PASARGUARD_USERNAME')
PASARGUARD_PASSWORD = os.getenv('PASARGUARD_PASSWORD')