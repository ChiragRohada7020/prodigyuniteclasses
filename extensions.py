from pymongo import MongoClient
from flask_mail import Mail

# MongoDB
client = MongoClient("mongodb://localhost:27017/ebook")
db = client.get_default_database()

# Mail (INIT only, no app yet)
mail = Mail()