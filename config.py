import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Flask Secret Key
SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key")

# MySQL Database Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "anilyadav")
DB_NAME = os.getenv("DB_NAME", "smartcart")

# Gmail SMTP Configuration
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() in ("true", "1", "t")
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "kadapaanilyadav@gmail.com")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "ioqx zdwb qunq olkb")

# Razorpay API Credentials
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_TLeM6Ox9b7K9Dp")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "dU4b4haEuqjJU1pc61pvF0UE")
