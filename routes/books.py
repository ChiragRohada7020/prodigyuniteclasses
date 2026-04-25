from flask import Blueprint, render_template, session, redirect
from extensions import db
from bson import ObjectId

from datetime import datetime

books_bp = Blueprint("books", __name__)

@books_bp.route("/")
def home():

    books = list(db.books.find())
    classes = list(db.classes.find())
    categories = list(db.categories.find())
    purchased_book_ids = set()

    if "user_id" in session:
        purchases = db.purchases.find(
            {"user_id": session["user_id"]},
            {"book_id": 1}
        )
        purchased_book_ids = {
            purchase.get("book_id")
            for purchase in purchases
            if purchase.get("book_id")
        }

    grouped = {}
    purchased_books = []

    for book in books:
        book["_id_str"] = str(book["_id"])
        book["is_purchased"] = book["_id_str"] in purchased_book_ids

        if book["is_purchased"]:
            purchased_books.append(book)
            continue

        cls = book.get("class", "Other")

        if cls not in grouped:
            grouped[cls] = []

        grouped[cls].append(book)

    return render_template(
        "home.html",
        grouped_books=grouped,
        purchased_books=purchased_books,
        classes=classes,
        categories=categories,
        seo_title="Prodigy Unite Classes | Class-wise Books, Notes & Practice Tests",
        seo_description="Explore class-wise books and study resources on Prodigy Unite Classes. Read, download, and practice with smart test tools.",
        seo_keywords="class-wise books, online study notes, student tests, Prodigy Unite Classes, digital learning platform",
    )


@books_bp.route("/purchase/<book_id>")
def purchase(book_id):

    # 🔐 Login check
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    book = db.books.find_one({"_id": ObjectId(book_id)})

    if not book:
        return "Book not found"

    # ✅ If book is FREE
    if book.get("is_free"):
        return redirect(f"/read/{book_id}")

    # ✅ Check if already purchased
    existing = db.purchases.find_one({
        "user_id": user_id,
        "book_id": book_id
    })

    if existing:
        return redirect(f"/read/{book_id}")

    # 💰 Simulate payment (for now)
    db.purchases.insert_one({
        "user_id": user_id,
        "book_id": book_id,
        "price": book.get("price", 0),
        "created_at": datetime.utcnow()
    })

    # 📊 update analytics
    db.books.update_one(
        {"_id": ObjectId(book_id)},
        {"$inc": {"purchases": 1}}
    )

    return redirect(f"/read/{book_id}")
