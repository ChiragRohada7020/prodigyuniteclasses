import os
from dotenv import load_dotenv
import cloudinary

load_dotenv()

# Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

SECRET_KEY = os.getenv("SECRET_KEY")

MAIL_SERVER = os.getenv("MAIL_SERVER")
MAIL_PORT = int(os.getenv("MAIL_PORT"))
MAIL_USE_TLS = os.getenv("MAIL_USE_TLS") == "True"
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_TEXT_MODEL = os.getenv("GROQ_TEXT_MODEL")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL")