from flask import Blueprint, request, session, redirect, render_template
from extensions import db
from bson import ObjectId

cart_bp = Blueprint("cart", __name__)


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


# ------------------ ADD TO CART ------------------
@cart_bp.route("/add_to_cart/<book_id>")
def add_to_cart(book_id):

    if "user_id" not in session:
        return redirect("/login")

    existing = db.purchases.find_one({
        "user_id": session["user_id"],
        "book_id": book_id
    })

    if existing:
        return redirect(f"/read/{book_id}")

    cart = session.get("cart", [])

    if book_id not in cart:
        cart.append(book_id)

    session["cart"] = cart

    return redirect("/cart")


# ------------------ VIEW CART ------------------
@cart_bp.route("/cart")
def cart():

    cart_ids = session.get("cart", [])
    user_id = session.get("user_id")
    coupon_error = session.pop("coupon_error", None)

    if not cart_ids:
        return render_template(
            "cart.html",
            books=[],
            subtotal=0,
            discount_amount=0,
            total=0,
            applied_coupon=None,
            coupon_error=coupon_error,
            seo_title="Your Cart | Prodigy Unite Classes",
            seo_description="Review your selected books and complete checkout on Prodigy Unite Classes.",
            seo_robots="noindex, nofollow",
        )

    purchased_book_ids = set()
    if user_id:
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
        session.pop("applied_coupon", None)
        return render_template(
            "cart.html",
            books=[],
            subtotal=0,
            discount_amount=0,
            total=0,
            applied_coupon=None,
            coupon_error=coupon_error,
            seo_title="Your Cart | Prodigy Unite Classes",
            seo_description="Review your selected books and complete checkout on Prodigy Unite Classes.",
            seo_robots="noindex, nofollow",
        )

    books = list(db.books.find({
        "_id": {"$in": [ObjectId(i) for i in cart_ids]}
    }))

    coupon = None
    coupon_data = session.get("applied_coupon")
    if coupon_data and coupon_data.get("code"):
        coupon = db.coupons.find_one({"code": coupon_data["code"]})

    totals = calculate_cart_totals(books, coupon)
    if not totals["applied_coupon"]:
        session.pop("applied_coupon", None)
    else:
        session["applied_coupon"] = totals["applied_coupon"]

    return render_template(
        "cart.html",
        books=books,
        subtotal=totals["subtotal"],
        discount_amount=totals["discount_amount"],
        total=totals["total"],
        applied_coupon=totals["applied_coupon"],
        coupon_error=coupon_error,
        seo_title="Your Cart | Prodigy Unite Classes",
        seo_description="Review your selected books and complete checkout on Prodigy Unite Classes.",
        seo_robots="noindex, nofollow",
    )


@cart_bp.route("/apply_coupon", methods=["POST"])
def apply_coupon():
    code = request.form.get("code", "").strip().upper()

    if not code:
        return redirect("/cart")

    coupon = db.coupons.find_one({"code": code})

    if coupon:
        session["applied_coupon"] = {
            "code": coupon.get("code", ""),
            "discount": int(coupon.get("discount", 0))
        }
    else:
        session.pop("applied_coupon", None)
        session["coupon_error"] = "Invalid promo code."

    return redirect("/cart")


@cart_bp.route("/remove_coupon")
def remove_coupon():
    session.pop("applied_coupon", None)
    return redirect("/cart")


# ------------------ REMOVE FROM CART ------------------
@cart_bp.route("/remove_from_cart/<book_id>")
def remove_from_cart(book_id):

    cart = session.get("cart", [])

    if book_id in cart:
        cart.remove(book_id)

    session["cart"] = cart
    if not cart:
        session.pop("applied_coupon", None)

    return redirect("/cart")
