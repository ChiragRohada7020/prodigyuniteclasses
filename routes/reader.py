import os
import re
import base64
import json
from io import BytesIO

from bson import ObjectId
from flask import Blueprint, jsonify, redirect, render_template, request, session
from datetime import datetime
import requests

from config import GROQ_API_KEY, GROQ_TEXT_MODEL, GROQ_VISION_MODEL
from extensions import db

reader_bp = Blueprint("reader", __name__)


def user_can_access_book(book, user_id):
    if book.get("is_free"):
        return True

    purchase = db.purchases.find_one({
        "user_id": user_id,
        "book_id": str(book["_id"])
    })

    return bool(purchase)


def build_pdf_url(book):
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "dodkdhrvm")
    return f"https://res.cloudinary.com/{cloud_name}/raw/upload/{book['public_id']}"


def generate_mcq_questions(book, count):
    title = book.get("title", "this book")
    category = book.get("category", "the subject")
    class_name = book.get("class", "the selected class")
    description = book.get("description", "")
    keywords = [
        word.strip(".,:;!?()[]{}").title()
        for word in re.findall(r"[A-Za-z0-9]+", description)
        if len(word) > 4
    ]
    keywords = list(dict.fromkeys(keywords))[:12]

    if not keywords:
        keywords = [category, title, f"Class {class_name}", "Concepts", "Practice"]

    question_templates = [
        {
            "question": "Which topic is most closely related to {title}?",
            "answer": "{category}",
            "options": ["{category}", "Sports", "Music", "Cooking"]
        },
        {
            "question": "This book is mainly intended for which class?",
            "answer": "Class {class_name}",
            "options": ["Class {class_name}", "Class 1", "Class 5", "College only"]
        },
        {
            "question": "Which keyword appears important in the book description?",
            "answer": "{keyword}",
            "options": ["{keyword}", "Unrelated", "Random", "Unknown"]
        },
        {
            "question": "What should a student use this book for?",
            "answer": "Learning and practice",
            "options": ["Learning and practice", "Watching movies", "Playing games", "Shopping"]
        },
        {
            "question": "Which label best describes the selected material?",
            "answer": "{category} study material",
            "options": ["{category} study material", "Travel guide", "Recipe book", "News report"]
        }
    ]

    questions = []

    for index in range(count):
        template = question_templates[index % len(question_templates)]
        keyword = keywords[index % len(keywords)]
        values = {
            "title": title,
            "category": category,
            "class_name": class_name,
            "keyword": keyword
        }
        questions.append({
            "number": index + 1,
            "question": template["question"].format(**values),
            "options": [option.format(**values) for option in template["options"]],
            "answer": template["answer"].format(**values)
        })

    return questions


def call_groq_chat(messages, model, temperature=0.2, max_tokens=2048, json_mode=False):
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing in config.py")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=60
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def extract_pdf_text_with_ocr(pdf_bytes, max_pages=20):
    try:
        import fitz
    except Exception:
        return extract_pdf_text_with_pypdf(pdf_bytes, max_pages)

    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_parts = []
    image_pages = []

    for page_index in range(min(len(document), max_pages)):
        page = document.load_page(page_index)
        page_text = page.get_text("text").strip()

        if page_text:
            text_parts.append(f"Page {page_index + 1}:\n{page_text}")

        if len(page_text) < 120:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
            image_bytes = pixmap.tobytes("jpeg", jpg_quality=70)
            image_pages.append((page_index + 1, image_bytes))

    document.close()

    for batch_start in range(0, len(image_pages), 5):
        batch = image_pages[batch_start:batch_start + 5]
        content = [{
            "type": "text",
            "text": "Extract all readable text from these PDF page images. Return only the extracted text, grouped by page."
        }]

        for page_number, image_bytes in batch:
            encoded = base64.b64encode(image_bytes).decode("utf-8")
            content.append({
                "type": "text",
                "text": f"Page {page_number}"
            })
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encoded}"
                }
            })

        ocr_text = call_groq_chat(
            [{"role": "user", "content": content}],
            GROQ_VISION_MODEL,
            temperature=0.1,
            max_tokens=2048
        )
        text_parts.append(ocr_text)

    return "\n\n".join(text_parts).strip()


def extract_pdf_text_with_pypdf(pdf_bytes, max_pages=20):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install PyMuPDF or pypdf to read PDF text.") from exc

    reader = PdfReader(BytesIO(pdf_bytes))
    text_parts = []

    for index, page in enumerate(reader.pages[:max_pages], start=1):
        page_text = (page.extract_text() or "").strip()
        if page_text:
            text_parts.append(f"Page {index}:\n{page_text}")

    if not text_parts:
        raise RuntimeError(
            "No selectable text found. This looks like a scanned/image PDF, but the local PDF renderer is blocked by Windows policy, so Groq vision OCR cannot receive page images."
        )

    return "\n\n".join(text_parts).strip()


def generate_groq_mcq_test(book, pdf_text, count):
    prompt = f"""
Create exactly {count} multiple-choice questions from the PDF text below.

Rules:
- Use only the PDF text and book metadata.
- Make questions useful for a student revision test.
- Each question must have exactly 4 options.
- Mark the correct answer exactly as one of the options.
- Return only valid JSON with this shape:
{{
  "questions": [
    {{
      "number": 1,
      "question": "...",
      "options": ["...", "...", "...", "..."],
      "answer": "..."
    }}
  ]
}}

Book title: {book.get("title", "")}
Class: {book.get("class", "")}
Category: {book.get("category", "")}

PDF text:
{pdf_text[:18000]}
"""

    content = call_groq_chat(
        [
            {"role": "system", "content": "You create accurate student MCQ tests from textbook PDFs."},
            {"role": "user", "content": prompt}
        ],
        GROQ_TEXT_MODEL,
        temperature=0.2,
        max_tokens=4096,
        json_mode=True
    )
    parsed = json.loads(content)
    questions = parsed.get("questions", [])

    cleaned_questions = []
    for index, question in enumerate(questions[:count], start=1):
        options = question.get("options", [])[:4]
        if len(options) != 4 or question.get("answer") not in options:
            continue
        cleaned_questions.append({
            "number": index,
            "question": question.get("question", ""),
            "options": options,
            "answer": question.get("answer", "")
        })

    if not cleaned_questions:
        raise RuntimeError("Groq did not return valid questions.")

    return cleaned_questions


@reader_bp.route("/read/<book_id>")
def read(book_id):
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    try:
        book = db.books.find_one({"_id": ObjectId(book_id)})
    except:
        return "Invalid book ID"

    if not book:
        return "Book not found"

    db.books.update_one(
        {"_id": ObjectId(book_id)},
        {"$inc": {"views": 1}}
    )

    if not user_can_access_book(book, user_id):
        return "You need to purchase this book"

    return render_template(
        "reader.html",
        book_id=book_id,
        seo_title="Read Book | Prodigy Unite Classes",
        seo_description="Read your purchased or free study book on Prodigy Unite Classes.",
        seo_robots="noindex, nofollow",
    )


@reader_bp.route("/get_secure_pdf/<book_id>")
def get_pdf(book_id):
    if "user_id" not in session:
        return "Unauthorized", 403

    user_id = session["user_id"]

    try:
        book = db.books.find_one({"_id": ObjectId(book_id)})
    except:
        return "Invalid book ID", 400

    if not book:
        return "Book not found", 404

    if not user_can_access_book(book, user_id):
        return "Unauthorized", 403

    return jsonify({"url": build_pdf_url(book)})


@reader_bp.route("/download_pdf/<book_id>")
def download_pdf(book_id):
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    try:
        book = db.books.find_one({"_id": ObjectId(book_id)})
    except:
        return "Invalid book ID", 400

    if not book:
        return "Book not found", 404

    if not user_can_access_book(book, user_id):
        return "Unauthorized", 403

    db.downloads.update_one(
        {"user_id": user_id, "book_id": book_id},
        {"$set": {
            "user_id": user_id,
            "book_id": book_id,
            "downloaded_at": datetime.utcnow()
        }},
        upsert=True
    )

    return redirect(build_pdf_url(book))


@reader_bp.route("/downloads")
def downloads():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    download_rows = list(db.downloads.find({"user_id": user_id}).sort("downloaded_at", -1))
    book_ids = [ObjectId(row["book_id"]) for row in download_rows if row.get("book_id")]
    books_by_id = {}

    if book_ids:
        books_by_id = {
            str(book["_id"]): book
            for book in db.books.find({"_id": {"$in": book_ids}})
        }

    downloaded_books = []
    for row in download_rows:
        book = books_by_id.get(row.get("book_id"))
        if book:
            book["downloaded_at"] = row.get("downloaded_at")
            downloaded_books.append(book)

    return render_template(
        "downloads.html",
        books=downloaded_books,
        seo_title="Downloads | Prodigy Unite Classes",
        seo_description="Access your downloaded study books and continue learning on Prodigy Unite Classes.",
        seo_robots="noindex, nofollow",
    )


@reader_bp.route("/test-panel")
def test_panel():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    books = list(db.books.find())
    accessible_books = [
        book
        for book in books
        if user_can_access_book(book, user_id)
    ]

    return render_template(
        "test_panel.html",
        books=accessible_books,
        seo_title="AI Test Panel | Prodigy Unite Classes",
        seo_description="Generate quick revision MCQ tests from your accessible books on Prodigy Unite Classes.",
        seo_robots="noindex, nofollow",
    )


@reader_bp.route("/generate_test", methods=["POST"])
def generate_test():
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 403

    data = request.json or {}
    book_id = data.get("book_id")
    count = min(max(int(data.get("count", 5)), 3), 10)

    try:
        book = db.books.find_one({"_id": ObjectId(book_id)})
    except:
        return jsonify({"error": "Invalid book ID"}), 400

    if not book:
        return jsonify({"error": "Book not found"}), 404

    if not user_can_access_book(book, session["user_id"]):
        return jsonify({"error": "Unauthorized"}), 403

    try:
        pdf_response = requests.get(build_pdf_url(book), timeout=45)
        pdf_response.raise_for_status()
        pdf_text = extract_pdf_text_with_ocr(pdf_response.content)

        if not pdf_text:
            return jsonify({"error": "No readable text found in the selected PDF."}), 422

        questions = generate_groq_mcq_test(book, pdf_text, count)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "book_title": book.get("title", "Selected book"),
        "questions": questions
    })


@reader_bp.route("/save_note", methods=["POST"])
def save_note():
    if "user_id" not in session:
        return "Unauthorized", 403

    data = request.json
    book_id = data["book_id"]

    try:
        book = db.books.find_one({"_id": ObjectId(book_id)})
    except:
        return "Invalid book ID", 400

    if not book or not user_can_access_book(book, session["user_id"]):
        return "Unauthorized", 403

    db.notes.update_one(
        {
            "user_id": session["user_id"],
            "book_id": book_id,
            "page": data["page"]
        },
        {
            "$set": {
                "user_id": session["user_id"],
                "book_id": book_id,
                "page": data["page"],
                "note": data["note"],
                "updated_at": datetime.utcnow()
            }
        },
        upsert=True
    )

    return {"status": "saved"}


@reader_bp.route("/get_note/<book_id>/<int:page>")
def get_note(book_id, page):
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 403

    try:
        book = db.books.find_one({"_id": ObjectId(book_id)})
    except:
        return jsonify({"error": "Invalid book ID"}), 400

    if not book or not user_can_access_book(book, session["user_id"]):
        return jsonify({"error": "Unauthorized"}), 403

    note = db.notes.find_one({
        "user_id": session["user_id"],
        "book_id": book_id,
        "page": page
    })

    return jsonify({"note": note.get("note", "") if note else ""})


@reader_bp.route("/ai_explain", methods=["POST"])
def ai():
    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 403

    data = request.json or {}
    book_id = data.get("book_id")
    page = data.get("page", 1)
    page_text = (data.get("text") or "").strip()
    user_message = (data.get("message") or "Explain this page in simple language.").strip()

    try:
        book = db.books.find_one({"_id": ObjectId(book_id)})
    except:
        return jsonify({"error": "Invalid book ID"}), 400

    if not book or not user_can_access_book(book, session["user_id"]):
        return jsonify({"error": "Unauthorized"}), 403

    if not page_text:
        return jsonify({"error": "I could not read text from this page. Try another page or zoom the PDF text layer."}), 422

    try:
        result = call_groq_chat(
            [
                {
                    "role": "system",
                    "content": "You are a friendly study assistant. Be warm, concise, and helpful. Explain textbook pages in simple language and suggest what to remember."
                },
                {
                    "role": "user",
                    "content": f"Page number: {page}\nStudent request: {user_message}\n\nPage text:\n{page_text[:7000]}"
                }
            ],
            GROQ_TEXT_MODEL,
            temperature=0.35,
            max_tokens=900
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({"result": result})
