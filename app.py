from datetime import datetime, timezone
import os

from bson import ObjectId
from flask import Flask, Response, request, session

from config import SECRET_KEY
from extensions import db, mail


app = Flask(__name__)
app.secret_key = SECRET_KEY


def get_site_url():
    env_site_url = os.getenv("SITE_URL", "").strip()
    if env_site_url:
        return env_site_url.rstrip("/")
    return request.url_root.rstrip("/")


@app.context_processor
def inject_user():
    user = None

    if "user_id" in session:
        try:
            user = db.users.find_one({"_id": ObjectId(session["user_id"])})
        except Exception:
            user = None

    return dict(current_user=user, cart_count=len(session.get("cart", [])))


@app.context_processor
def inject_seo_defaults():
    site_url = get_site_url()
    canonical_url = request.base_url
    og_image_url = f"{site_url}/static/images/logo1.png"

    return {
        "site_name": "Prodigy Unite Classes",
        "default_seo_title": "Prodigy Unite Classes | Digital Classes, Books, Notes & Tests",
        "default_seo_description": "Prodigy Unite Classes is a learning platform for class-wise books, notes, downloads, and AI-powered test practice.",
        "default_seo_keywords": "Prodigy Unite Classes, digital classes, online study materials, class notes, books, MCQ tests",
        "canonical_url": canonical_url,
        "og_image_url": og_image_url,
    }


@app.route("/robots.txt")
def robots_txt():
    site_url = get_site_url()
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /read/",
        "Disallow: /get_secure_pdf/",
        "Disallow: /download_pdf/",
        "Disallow: /create_order/",
        "Disallow: /create_cart_order",
        "Disallow: /verify_payment",
        "Disallow: /verify_cart_payment",
        f"Sitemap: {site_url}/sitemap.xml",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    site_url = get_site_url()
    now_iso = datetime.now(timezone.utc).date().isoformat()

    public_urls = [
        {"loc": f"{site_url}/", "changefreq": "daily", "priority": "1.0"},
    ]

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for item in public_urls:
        xml_parts.extend(
            [
                "  <url>",
                f"    <loc>{item['loc']}</loc>",
                f"    <lastmod>{now_iso}</lastmod>",
                f"    <changefreq>{item['changefreq']}</changefreq>",
                f"    <priority>{item['priority']}</priority>",
                "  </url>",
            ]
        )

    xml_parts.append("</urlset>")
    return Response("\n".join(xml_parts), mimetype="application/xml")


# Mail config
app.config.update(
    MAIL_SERVER="smtp.gmail.com",
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME="prodigyuniteclasses@gmail.com",
    MAIL_PASSWORD="cnqgxyakeitfzhzs",
    MAIL_DEFAULT_SENDER="prodigyuniteclasses@gmail.com",
)

mail.init_app(app)


# register routes
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.books import books_bp
from routes.cart import cart_bp
from routes.payment import payment_bp
from routes.reader import reader_bp

app.register_blueprint(cart_bp)
app.register_blueprint(payment_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(books_bp)
app.register_blueprint(reader_bp)
app.register_blueprint(admin_bp)


if __name__ == "__main__":
    app.run(debug=True)
