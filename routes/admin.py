from datetime import datetime
from functools import wraps

import cloudinary.uploader
from bson import ObjectId
from flask import Blueprint, jsonify, redirect, render_template, request, session

from config import ADMIN_EMAIL, ADMIN_PASSWORD
from extensions import db

admin_bp = Blueprint("admin", __name__)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect("/admin/login")
        return view(*args, **kwargs)

    return wrapped


@admin_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect("/admin")

        return render_template("admin_login.html", error="Invalid admin email or password.")

    return render_template("admin_login.html")


@admin_bp.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/admin/login")


@admin_bp.route("/admin")
@admin_required
def admin_dashboard():
    books = list(db.books.find())
    classes = list(db.classes.find())
    categories = list(db.categories.find())

    total_books = len(books)
    total_sales = db.purchases.count_documents({})
    revenue = sum([p.get("price", 0) for p in db.purchases.find()])
    top_books = list(db.books.find().sort("views", -1).limit(5))

    dashboard_books = []
    for book in books:
        dashboard_books.append({
            "_id": str(book["_id"]),
            "title": book.get("title", ""),
            "description": book.get("description", ""),
            "class": book.get("class", ""),
            "category": book.get("category", ""),
            "price": book.get("price", 0),
            "is_free": book.get("is_free", False),
            "views": book.get("views", 0),
            "purchases": book.get("purchases", 0),
            "cover_url": book.get("cover_url", "")
        })

    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        total_sales=total_sales,
        revenue=revenue,
        top_books=top_books,
        books=dashboard_books,
        classes=classes,
        categories=categories,
        live_users=0
    )


@admin_bp.route("/admin/taxonomy")
@admin_required
def admin_taxonomy():
    classes = list(db.classes.find())
    categories = list(db.categories.find())

    return render_template(
        "admin_taxonomy.html",
        classes=classes,
        categories=categories
    )


@admin_bp.route("/admin/coupons")
@admin_required
def admin_coupons():
    coupons = list(db.coupons.find().sort("created_at", -1))

    return render_template(
        "admin_coupons.html",
        coupons=coupons,
        total_coupons=len(coupons)
    )


@admin_bp.route("/admin/upload", methods=["GET", "POST"])
@admin_required
def upload_book():
    if request.method == "POST":
        file = request.files["pdf"]
        cover = request.files.get("cover_image")

        result = cloudinary.uploader.upload(
            file,
            resource_type="raw",
            folder="books"
        )
        cover_result = None

        if cover and cover.filename:
            cover_result = cloudinary.uploader.upload(
                cover,
                resource_type="image",
                folder="book_covers"
            )

        is_free = request.form.get("is_free") == "on"
        price = 0 if is_free else int(request.form.get("price", 0))

        db.books.insert_one({
            "title": request.form["title"],
            "description": request.form["description"],
            "class": request.form["class"],
            "category": request.form["category"],
            "price": price,
            "is_free": is_free,
            "cover_url": cover_result["secure_url"] if cover_result else "",
            "cover_public_id": cover_result["public_id"] if cover_result else "",
            "public_id": result["public_id"],
            "views": 0,
            "purchases": 0,
            "created_at": datetime.utcnow()
        })

        return redirect("/admin")

    return render_template(
        "admin_upload.html",
        classes=db.classes.find(),
        categories=db.categories.find()
    )


@admin_bp.route("/admin/edit_book/<book_id>")
@admin_required
def edit_book_page(book_id):
    book = db.books.find_one({"_id": ObjectId(book_id)})
    classes = list(db.classes.find())
    categories = list(db.categories.find())

    return render_template(
        "admin_edit_book.html",
        book=book,
        classes=classes,
        categories=categories
    )


@admin_bp.route("/admin/delete_book/<book_id>")
@admin_required
def delete_book(book_id):
    db.books.delete_one({"_id": ObjectId(book_id)})
    return redirect("/admin")


@admin_bp.route("/admin/toggle_free/<book_id>")
@admin_required
def toggle_free(book_id):
    book = db.books.find_one({"_id": ObjectId(book_id)})

    db.books.update_one(
        {"_id": ObjectId(book_id)},
        {"$set": {"is_free": not book.get("is_free", False)}}
    )

    return redirect("/admin")


@admin_bp.route("/admin/update_book/<book_id>", methods=["POST"])
@admin_required
def update_book(book_id):
    is_free = True if request.form.get("is_free") else False
    update_data = {
        "title": request.form["title"],
        "description": request.form["description"],
        "class": request.form["class"],
        "category": request.form["category"],
        "price": 0 if is_free else int(request.form.get("price", 0)),
        "is_free": is_free
    }

    cover = request.files.get("cover_image")

    if cover and cover.filename:
        cover_result = cloudinary.uploader.upload(
            cover,
            resource_type="image",
            folder="book_covers"
        )
        update_data["cover_url"] = cover_result["secure_url"]
        update_data["cover_public_id"] = cover_result["public_id"]

    db.books.update_one(
        {"_id": ObjectId(book_id)},
        {"$set": update_data}
    )

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        saved_book = db.books.find_one({"_id": ObjectId(book_id)})
        return jsonify({
            "status": "success",
            "book": {
                "_id": book_id,
                "title": saved_book.get("title", ""),
                "description": saved_book.get("description", ""),
                "class": saved_book.get("class", ""),
                "category": saved_book.get("category", ""),
                "price": saved_book.get("price", 0),
                "is_free": saved_book.get("is_free", False),
                "views": saved_book.get("views", 0),
                "purchases": saved_book.get("purchases", 0),
                "cover_url": saved_book.get("cover_url", "")
            }
        })

    return redirect("/admin")


@admin_bp.route("/admin/add_class", methods=["POST"])
@admin_required
def add_class():
    name = request.form["name"].strip()

    if name:
        db.classes.insert_one({"name": name})

    return redirect("/admin/taxonomy")


@admin_bp.route("/admin/add_category", methods=["POST"])
@admin_required
def add_category():
    name = request.form["name"].strip()

    if name:
        db.categories.insert_one({"name": name})

    return redirect("/admin/taxonomy")


@admin_bp.route("/admin/delete_class/<class_id>")
@admin_required
def delete_class(class_id):
    db.classes.delete_one({"_id": ObjectId(class_id)})
    return redirect("/admin/taxonomy")


@admin_bp.route("/admin/delete_category/<category_id>")
@admin_required
def delete_category(category_id):
    db.categories.delete_one({"_id": ObjectId(category_id)})
    return redirect("/admin/taxonomy")


@admin_bp.route("/admin/add_coupon", methods=["POST"])
@admin_required
def add_coupon():
    code = request.form["code"].strip().upper()
    discount = int(request.form.get("discount", 0))

    if code and discount > 0:
        db.coupons.insert_one({
            "code": code,
            "discount": discount,
            "created_at": datetime.utcnow()
        })

    return redirect("/admin/coupons")


@admin_bp.route("/admin/delete_coupon/<coupon_id>")
@admin_required
def delete_coupon(coupon_id):
    db.coupons.delete_one({"_id": ObjectId(coupon_id)})
    return redirect("/admin/coupons")
