from pymongo import MongoClient
from flask_mail import Mail

# MongoDB
client = MongoClient(
    "mongodb+srv://chiragrohada40:Chirag%40123@cluster0.l9en3av.mongodb.net/flaskdb?retryWrites=true&w=majority"
)
db = client.get_default_database()

# Mail (INIT only, no app yet)
mail = Mail()