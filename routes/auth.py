from flask import Blueprint, request, render_template, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Message
from extensions import mail, db

import random
import time

auth_bp = Blueprint("auth", __name__)

OTP_EXPIRY = 300  # 5 minutes


# ------------------ SIGNUP ------------------
@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        mobile = request.form.get("mobile")
        email = request.form.get("email")
        password = request.form.get("password")

        # Basic validation
        if not all([name, mobile, email, password]):
            return render_template(
                "signup.html",
                error="Fill in all the fields to continue.",
                form_data={
                    "name": name or "",
                    "mobile": mobile or "",
                    "email": email or ""
                },
                seo_title="Sign Up | Prodigy Unite Classes",
                seo_description="Create your Prodigy Unite Classes account to access books, notes, downloads, and tests.",
                seo_robots="noindex, nofollow",
            )

        # Check if user already exists
        if db.users.find_one({"email": email}):
            return render_template(
                "signup.html",
                error="An account with that email already exists.",
                form_data={
                    "name": name,
                    "mobile": mobile,
                    "email": email
                },
                seo_title="Sign Up | Prodigy Unite Classes",
                seo_description="Create your Prodigy Unite Classes account to access books, notes, downloads, and tests.",
                seo_robots="noindex, nofollow",
            )

        # Generate OTP
        otp = str(random.randint(100000, 999999))

        # Store temp data in session
        session["otp"] = otp
        session["otp_time"] = time.time()
        session["temp_user"] = {
            "name": name,
            "mobile": mobile,
            "email": email,
            "password": generate_password_hash(password)
        }

        try:
            # Send OTP email with text + HTML body for better client compatibility.
            msg = Message(
                subject="Your Prodigy Unite Classes verification code",
                recipients=[email]
            )
            msg.body = (
                "Hello,\n\n"
                "Your Prodigy Unite Classes verification code is: "
                f"{otp}\n\n"
                "This code is valid for 5 minutes.\n"
                "Please do not share this code with anyone.\n\n"
                "If you did not request this, you can safely ignore this email.\n\n"
                "Regards,\n"
                "Prodigy Unite Classes Team"
            )
            msg.html = f"""
            <div style="margin:0;padding:24px;background:#f1f5f9;font-family:Arial,sans-serif;color:#0f172a;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;margin:0 auto;background:#ffffff;border-radius:14px;border:1px solid #e2e8f0;overflow:hidden;">
                <tr>
                  <td style="padding:20px 24px;background:#0f172a;color:#ffffff;">
                    <h2 style="margin:0;font-size:20px;line-height:1.3;">Prodigy Unite Classes</h2>
                    <p style="margin:8px 0 0;font-size:13px;color:#cbd5e1;">Email Verification</p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:24px;">
                    <p style="margin:0 0 14px;font-size:14px;line-height:1.7;">Hello,</p>
                    <p style="margin:0 0 14px;font-size:14px;line-height:1.7;">
                      Use the following one-time password (OTP) to complete your signup:
                    </p>
                    <div style="margin:18px 0;padding:14px 16px;border:1px dashed #94a3b8;border-radius:10px;background:#f8fafc;text-align:center;">
                      <span style="display:inline-block;font-size:30px;letter-spacing:8px;font-weight:700;color:#0f172a;">{otp}</span>
                    </div>
                    <p style="margin:0 0 10px;font-size:13px;line-height:1.7;color:#334155;">
                      This code will expire in <strong>5 minutes</strong>.
                    </p>
                    <p style="margin:0;font-size:13px;line-height:1.7;color:#334155;">
                      For your security, never share this OTP with anyone.
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="padding:16px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;">
                    <p style="margin:0;font-size:12px;line-height:1.6;color:#64748b;">
                      If you did not request this email, please ignore it. This is an automated message, please do not reply.
                    </p>
                  </td>
                </tr>
              </table>
            </div>
            """

            mail.send(msg)

        except Exception as e:
            print("MAIL ERROR:", e)
            return render_template(
                "signup.html",
                error="Could not send OTP right now. Please try again.",
                form_data={
                    "name": name,
                    "mobile": mobile,
                    "email": email
                },
                seo_title="Sign Up | Prodigy Unite Classes",
                seo_description="Create your Prodigy Unite Classes account to access books, notes, downloads, and tests.",
                seo_robots="noindex, nofollow",
            )

        return redirect("/verify-otp")

    return render_template(
        "signup.html",
        seo_title="Sign Up | Prodigy Unite Classes",
        seo_description="Create your Prodigy Unite Classes account to access books, notes, downloads, and tests.",
        seo_robots="noindex, nofollow",
    )


# ------------------ VERIFY OTP ------------------
@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        user_otp = request.form.get("otp")

        if not user_otp:
            return "Enter OTP"

        # Check if session exists
        if "otp" not in session or "temp_user" not in session:
            return "Session expired. Please signup again."

        # Check expiry
        if time.time() - session.get("otp_time", 0) > OTP_EXPIRY:
            session.clear()
            return "OTP expired. Please signup again."

        # Verify OTP
        if user_otp == session.get("otp"):
            user = session.get("temp_user")

            db.users.insert_one(user)

            # Clear session
            session.pop("otp", None)
            session.pop("otp_time", None)
            session.pop("temp_user", None)

            return redirect("/login")

        return "Invalid OTP"

    return render_template(
        "verify_otp.html",
        seo_title="Verify OTP | Prodigy Unite Classes",
        seo_description="Verify your OTP to activate your Prodigy Unite Classes student account.",
        seo_robots="noindex, nofollow",
    )


# ------------------ LOGIN ------------------
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return render_template(
                "login.html",
                error="Enter both email and password.",
                email=email or "",
                seo_title="Login | Prodigy Unite Classes",
                seo_description="Log in to Prodigy Unite Classes to access your books, notes, downloads, and tests.",
                seo_robots="noindex, nofollow",
            )

        user = db.users.find_one({"email": email})

        if not user:
            return render_template(
                "login.html",
                error="No account found with that email.",
                email=email,
                seo_title="Login | Prodigy Unite Classes",
                seo_description="Log in to Prodigy Unite Classes to access your books, notes, downloads, and tests.",
                seo_robots="noindex, nofollow",
            )

        if not check_password_hash(user["password"], password):
            return render_template(
                "login.html",
                error="Password does not match.",
                email=email,
                seo_title="Login | Prodigy Unite Classes",
                seo_description="Log in to Prodigy Unite Classes to access your books, notes, downloads, and tests.",
                seo_robots="noindex, nofollow",
            )

        session["user_id"] = str(user["_id"])

        return redirect("/")

    return render_template(
        "login.html",
        seo_title="Login | Prodigy Unite Classes",
        seo_description="Log in to Prodigy Unite Classes to access your books, notes, downloads, and tests.",
        seo_robots="noindex, nofollow",
    )


# ------------------ LOGOUT ------------------
@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
