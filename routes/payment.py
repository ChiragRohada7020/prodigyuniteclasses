import razorpay
from flask import Blueprint, request, jsonify, session
from extensions import db
from bson import ObjectId
from datetime import datetime

payment_bp = Blueprint("payment", __name__)

from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
import razorpay

client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)


def calculate_cart_totals(books, coupon=None):
    subtotal = sum([
        b.get("price", 0)
        for b in books
        if not b.get("is_free")
    ])

    discount = 0
    applied_coupon = None

    if coupon and subtotal > 0:
        discount_percent = max(0, min(int(coupon.get("discount", 0)), 100))
        discount = int(round((subtotal * discount_percent) / 100))
        applied_coupon = {
            "code": coupon.get("code", ""),
            "discount": discount_percent
        }

    total = max(subtotal - discount, 0)

    return {
        "subtotal": subtotal,
        "discount_amount": discount,
        "total": total,
        "applied_coupon": applied_coupon
    }

# ------------------ CREATE ORDER ------------------
@payment_bp.route("/create_order/<book_id>")
def create_order(book_id):

    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 403

    user_id = session["user_id"]
    book = db.books.find_one({"_id": ObjectId(book_id)})

    if not book:
        return jsonify({"error": "Book not found"}), 404

    if book.get("is_free"):
        return jsonify({"error": "Free books do not need payment"}), 400

    existing = db.purchases.find_one({
        "user_id": user_id,
        "book_id": book_id
    })

    if existing:
        return jsonify({"error": "Already purchased", "already_purchased": True}), 409

    amount = int(book["price"] * 100)  # paise

    order = client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1
    })

    return jsonify({
        "order_id": order["id"],
        "amount": amount,
        "book_id": book_id
    })


# ------------------ VERIFY PAYMENT ------------------
@payment_bp.route("/verify_payment", methods=["POST"])
def verify_payment():

    data = request.json

    user_id = session["user_id"]
    book_id = data["book_id"]

    existing = db.purchases.find_one({
        "user_id": user_id,
        "book_id": book_id
    })

    if existing:
        return {"status": "already_purchased"}

    book = db.books.find_one({"_id": ObjectId(book_id)})

    if not book:
        return {"error": "Book not found"}, 404

    # Save purchase
    db.purchases.insert_one({
        "user_id": user_id,
        "book_id": book_id,
        "payment_id": data["payment_id"],
        "price": book.get("price", 0),
        "created_at": datetime.utcnow()
    })

    db.books.update_one(
        {"_id": ObjectId(book_id)},
        {"$inc": {"purchases": 1}}
    )

    return {"status": "success"}

@payment_bp.route("/create_cart_order")
def create_cart_order():

    from flask import session, jsonify
    from bson import ObjectId

    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 403

    user_id = session["user_id"]
    cart_ids = session.get("cart", [])

    if not cart_ids:
        return jsonify({"error": "Cart empty"}), 400

    purchases = db.purchases.find(
        {"user_id": user_id},
        {"book_id": 1}
    )
    purchased_book_ids = {
        purchase.get("book_id")
        for purchase in purchases
        if purchase.get("book_id")
    }
    cart_ids = [book_id for book_id in cart_ids if book_id not in purchased_book_ids]
    session["cart"] = cart_ids

    if not cart_ids:
        return jsonify({"error": "All cart books are already purchased"}), 409

    books = list(db.books.find({
        "_id": {"$in": [ObjectId(i) for i in cart_ids]}
    }))
    coupon = None
    coupon_data = session.get("applied_coupon")
    if coupon_data and coupon_data.get("code"):
        coupon = db.coupons.find_one({"code": coupon_data["code"]})

    totals = calculate_cart_totals(books, coupon)
    if totals["applied_coupon"]:
        session["applied_coupon"] = totals["applied_coupon"]
    else:
        session.pop("applied_coupon", None)

    amount = int(totals["total"] * 100)

    order = client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1
    })

    return jsonify({
        "order_id": order["id"],
        "amount": amount,
        "discount_amount": totals["discount_amount"],
        "coupon_code": totals["applied_coupon"]["code"] if totals["applied_coupon"] else ""
    })


@payment_bp.route("/verify_cart_payment", methods=["POST"])
def verify_cart_payment():

    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 403

    data = request.json
    user_id = session["user_id"]
    cart_ids = session.get("cart", [])
    coupon_data = session.get("applied_coupon")

    if not cart_ids:
        return jsonify({"error": "Cart empty"}), 400

    purchases = db.purchases.find(
        {"user_id": user_id},
        {"book_id": 1}
    )
    purchased_book_ids = {
        purchase.get("book_id")
        for purchase in purchases
        if purchase.get("book_id")
    }

    new_purchase_ids = [
        book_id
        for book_id in cart_ids
        if book_id not in purchased_book_ids
    ]

    if new_purchase_ids:
        books = list(db.books.find({
            "_id": {"$in": [ObjectId(book_id) for book_id in new_purchase_ids]}
        }))
        prices_by_id = {
            str(book["_id"]): book.get("price", 0)
            for book in books
        }

        db.purchases.insert_many([
            {
                "user_id": user_id,
                "book_id": book_id,
                "payment_id": data["payment_id"],
                "order_id": data.get("order_id"),
                "price": prices_by_id.get(book_id, 0),
                "coupon_code": coupon_data.get("code") if coupon_data else "",
                "created_at": datetime.utcnow()
            }
            for book_id in new_purchase_ids
        ])

        db.books.update_many(
            {"_id": {"$in": [ObjectId(book_id) for book_id in new_purchase_ids]}},
            {"$inc": {"purchases": 1}}
        )

    session["cart"] = []
    session.pop("applied_coupon", None)

    return jsonify({"status": "success"})
