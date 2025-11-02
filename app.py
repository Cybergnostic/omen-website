# app.py
from flask import Flask, render_template, request, redirect, url_for, g, flash, jsonify, make_response
from pathlib import Path
from datetime import datetime
import sqlite3
import csv 
import os
import requests
from uuid import uuid4
import logging
import hmac
import hashlib

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv is optional; ignore if missing
    pass


# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
DATABASE = os.environ.get("OMEN_DB_PATH", str(BASE_DIR / 'data' / 'omen_orders.db'))
# IMPORTANT: This secret key is for development only. Use a long, random key in production.
app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)
app.secret_key = b'your_long_and_secret_key_here' 

# Configure logging
app.logger.setLevel(logging.INFO)


# --- DATABASE UTILITIES ---

def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    db = getattr(g, '_database', None)
    if db is None:
        Path("data").mkdir(exist_ok=True)
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row # Allows accessing columns by name
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Closes the database again at the end of the request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def migrate_orders_table(db):
    cols = {r[1] for r in db.execute("PRAGMA table_info(orders)")}
    def add(col, sql):
        if col not in cols:
            db.execute(sql)
    add("paypal_order_id", "ALTER TABLE orders ADD COLUMN paypal_order_id TEXT;")
    add("status",          "ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'created';")
    add("created_at",      "ALTER TABLE orders ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP;")
    add("captured_at",     "ALTER TABLE orders ADD COLUMN captured_at TEXT;")
    add("reading",         "ALTER TABLE orders ADD COLUMN reading TEXT;")
    add("mode",            "ALTER TABLE orders ADD COLUMN mode TEXT;")
    db.commit()

def init_db():
    """Initializes the database schema and migrates."""
    with app.app_context():
        db = get_db()
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                name TEXT,
                email TEXT,
                total_price REAL,
                payment_status TEXT,
                completion_status TEXT,
                birth_date TEXT,
                birth_time TEXT,
                birth_place TEXT,
                secondary_birth_date TEXT,
                secondary_birth_time TEXT,
                secondary_birth_place TEXT
            );
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS order_items (
                order_id TEXT NOT NULL,
                item_id TEXT PRIMARY KEY,
                reading_type TEXT,
                reading_mode TEXT,
                price REAL,
                question TEXT,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            );
            """
        )
        migrate_orders_table(db)
        db.commit()

# --- INITIAL SETUP ---
# Initialize the database when the app starts
init_db()


# --- READING DATA & PADDLE LINKS ---
# Dictionary of reading information (names and prices)
READINGS = {
    "natal": {"name": "Natal Chart Analysis", "pdf_price": 90, "video_price": 120},
    "orientation": {"name": "Orientation / Career Guidance", "pdf_price": 70, "video_price": 90},
    "love": {"name": "Love & Relationship Guidance", "pdf_price": 70, "video_price": 90},
    "focus": {"name": "Other Focus Area", "pdf_price": 60, "video_price": 80},
    "annual": {"name": "Annual Horoscope (Solar Return)", "pdf_price": 85, "video_price": 110},
    "horary": {"name": "Horary Chart Analysis", "pdf_price": 55, "video_price": 75},
    "synastry": {"name": "Synastry", "pdf_price": 95, "video_price": 125},
}

# Remove PADDLE_LINKS definition and all usage
# PADDLE_LINKS = {...}
# in /readings route and all others


# --- BASIC PAGES ---
@app.route("/", endpoint="home")
def home():
    # cart_count is always 0 now, as the cart is removed
    return render_template("index.html", cart_count=0)

@app.route("/about")
def about():
    return render_template("about.html", cart_count=0)

@app.route("/readings")
def readings():
    # Only pass readings data to the template
    return render_template("readings.html", readings=READINGS, cart_count=0)

@app.route("/order/details", methods=["GET", "POST"])
def order_details():
    reading_key = (request.values.get("reading") or "").strip()
    mode = (request.values.get("mode") or "").strip()
    reading = READINGS.get(reading_key)
    if not reading or mode not in ("pdf", "video"):
        flash("Invalid reading selection.", "danger")
        return redirect(url_for("readings"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        birth_date = request.form.get("birth_date")
        birth_time = request.form.get("birth_time")
        birth_place = request.form.get("birth_place")
        secondary_birth_date = request.form.get("secondary_birth_date")
        secondary_birth_time = request.form.get("secondary_birth_time")
        secondary_birth_place = request.form.get("secondary_birth_place")
        question = request.form.get("question")

        if not name or not email:
            flash("Name and email are required.", "danger")
            return redirect(url_for("order_details", reading=reading_key, mode=mode))

        oid = str(uuid4())
        try:
            db = get_db()
            db.execute(
                """
                INSERT INTO orders (
                    order_id, timestamp, name, email, total_price, payment_status, completion_status,
                    birth_date, birth_time, birth_place, secondary_birth_date, secondary_birth_time, secondary_birth_place,
                    status, created_at, reading, mode
                ) VALUES (
                    ?, datetime('now'), ?, ?, NULL, 'unpaid', 'new',
                    ?, ?, ?, ?, ?, ?, 'created', datetime('now'), ?, ?
                )
                """,
                (
                    oid, name, email,
                    birth_date, birth_time, birth_place,
                    secondary_birth_date, secondary_birth_time, secondary_birth_place,
                    reading_key, mode,
                ),
            )
            db.execute(
                """
                INSERT INTO order_items (order_id, item_id, reading_type, reading_mode, price, question)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (oid, str(uuid4()), reading_key, mode, question),
            )
            db.commit()
        except Exception:
            app.logger.exception("Failed to create order with details")
            flash("Could not create your order. Please try again.", "danger")
            return redirect(url_for("readings"))

        return redirect(url_for("checkout", reading=reading_key, mode=mode, order_id=oid))

    return render_template(
        "order_details.html",
        reading_key=reading_key,
        reading=reading,
        mode=mode,
        cart_count=0,
    )

@app.route("/contact")
def contact():
    return render_template("contact.html", cart_count=0)

@app.route("/faq")
def faq():
    return render_template("faq.html", cart_count=0)

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", cart_count=0)

# Updated thankyou for direct checkout flow
@app.route("/thankyou")
def thankyou():
    status = request.args.get('status')
    order_id = request.args.get('order_id')
    video_session_needed = False
    if order_id:
        try:
            db = get_db()
            row = db.execute("SELECT mode FROM orders WHERE order_id=?", (order_id,)).fetchone()
            if row and (row["mode"] or row[0]) == "video":
                video_session_needed = True
        except Exception:
            app.logger.exception("Failed to determine video_session_needed")
    return render_template(
        "thankyou.html",
        cart_count=0,
        status=status,
        order_id=order_id,
        video_session_needed=video_session_needed,
    )


# --- DEPRECATED/REMOVED CART & MOCK PAYMENT ROUTES --- removed

# --- PAYPAL ENV CONFIG ---
PAYPAL_ENV = os.environ.get("PAYPAL_ENV", "sandbox")  # default to sandbox
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "your-client-id")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "your-secret")
PAYPAL_WEBHOOK_ID = os.environ.get("PAYPAL_WEBHOOK_ID", "")
PAYPAL_API_BASE = (
    "https://api-m.sandbox.paypal.com"
    if PAYPAL_ENV == "sandbox"
    else "https://api-m.paypal.com"
)

# --- NOWPAYMENTS CONFIG --- (support legacy var names)
NOWPAYMENTS_API_KEY = (
    os.environ.get("NOWPAYMENTS_API_KEY")
    or os.environ.get("NOWPAY_API_KEY")
    or ""
)
NOWPAYMENTS_IPN_SECRET = (
    os.environ.get("NOWPAYMENTS_IPN_SECRET")
    or os.environ.get("NOWPAY_IPN_SECRET")
    or ""
)
NOWPAYMENTS_PAY_CURRENCY = os.environ.get("NOWPAYMENTS_PAY_CURRENCY", "USDTTRC20")
NOWPAYMENTS_API_BASE = "https://api.nowpayments.io/v1"

# --- PAYPAL OAUTH UTILITY ---
def get_paypal_access_token():
    url = f"{PAYPAL_API_BASE}/v1/oauth2/token"
    resp = requests.post(
        url,
        headers={"Accept": "application/json", "Accept-Language": "en_US"},
        data={"grant_type": "client_credentials"},
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

@app.route("/checkout", methods=["GET"])
def checkout():
    # Get reading and mode from query parameters
    reading_key = request.args.get("reading")
    mode = request.args.get("mode")
    existing_order_id = request.args.get("order_id")
    # fallback or error if invalid
    reading = READINGS.get(reading_key)
    if not reading or mode not in ("pdf", "video"):
        flash("Invalid reading selection.", "danger")
        return redirect(url_for("readings"))
    # Require order details first
    if not existing_order_id:
        flash("Please enter your details to continue.", "info")
        return redirect(url_for("order_details", reading=reading_key, mode=mode))

    # Build item details
    price = reading["pdf_price"] if mode == "pdf" else reading["video_price"]
    item = {
        "name": reading["name"],
        "reading_mode": mode,
        "price": price,
        "id": str(uuid4()),
        "reading_type": reading_key,
        "question": None,  # Not collected here
    }
    order_id = existing_order_id
    total_str = f"{price:.2f}"
    # All checkout now per-item; no cart, no user info at this page
    return render_template(
        "checkout.html",
        items=[item],
        total=total_str,
        currency="EUR",
        paypal_client_id=PAYPAL_CLIENT_ID,
        paypal_enabled=bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_ID != "your-client-id"),
        nowpayments_enabled=bool(NOWPAYMENTS_API_KEY),
        order_id=order_id,
        cart_count=0,
    )

# Create NOWPayments invoice and redirect user to payment page (POST only)
@app.route("/crypto/checkout", methods=["POST"])
def crypto_checkout():
    reading_key = request.form.get("reading")
    mode = request.form.get("mode")
    order_id = request.form.get("order_id")
    reading = READINGS.get(reading_key)
    if not reading or mode not in ("pdf", "video") or not order_id:
        flash("Invalid payment request.", "danger")
        return redirect(url_for("readings"))

    price = reading["pdf_price"] if mode == "pdf" else reading["video_price"]
    price_float = float(price)

    payload = {
        "price_amount": price_float,
        "price_currency": "EUR",
        "pay_currency": NOWPAYMENTS_PAY_CURRENCY,
        "order_id": order_id,
        "order_description": f"{reading['name']} ({mode})",
    }
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            f"{NOWPAYMENTS_API_BASE}/invoice", json=payload, headers=headers, timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
        invoice_url = data.get("invoice_url")
        if not invoice_url:
            raise Exception("No invoice_url returned")

        db = get_db()
        db.execute(
            """
            INSERT OR IGNORE INTO orders (
                order_id, timestamp, total_price, payment_status, completion_status,
                status, created_at, reading, mode
            ) VALUES (?, datetime('now'), ?, 'unpaid', 'new', 'created', datetime('now'), ?, ?)
            """,
            (order_id, price_float, reading_key, mode),
        )
        db.commit()

        return redirect(invoice_url)
    except Exception:
        app.logger.exception("NOWPayments invoice error")
        flash("Crypto payment initialization failed. Try again.", "danger")
        return redirect(url_for("readings"))
# Deprecated payment routes removed

# --- PAYPAL API ROUTES ---
@app.route("/api/paypal/orders", methods=["POST"])
def api_paypal_orders():
    order_id = request.args.get("order_id")
    reading_key = request.args.get("reading")
    mode = request.args.get("mode")
    reading = READINGS.get(reading_key)
    if not order_id or not reading or mode not in ("pdf", "video"):
        return jsonify({"error": "Invalid order parameters."}), 400
    price = reading["pdf_price"] if mode == "pdf" else reading["video_price"]
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {"currency_code": "EUR", "value": f"{price:.2f}"},
            "custom_id": order_id,
        }],
        "application_context": {
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING"
        }
    }
    try:
        headers = {
            "Authorization": f"Bearer {get_paypal_access_token()}",
            "Content-Type": "application/json",
        }
        r = requests.post(
            f"{PAYPAL_API_BASE}/v2/checkout/orders", json=body, headers=headers, timeout=20
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException:
        app.logger.exception("PayPal create order failed")
        return jsonify({"error": "paypal_create_failed"}), 502

    # Persist a 'created' order note (do not fail the PayPal call on DB error)
    internal_id = request.args.get("order_id")
    reading = request.args.get("reading")
    mode = request.args.get("mode")
    try:
        db = get_db()
        db.execute(
            """
        INSERT OR IGNORE INTO orders (
            order_id, timestamp, name, email, total_price, payment_status, completion_status,
            birth_date, birth_time, birth_place, secondary_birth_date, secondary_birth_time, secondary_birth_place,
            paypal_order_id, status, created_at, reading, mode
        ) VALUES (?, datetime('now'), NULL, NULL, NULL, 'unpaid', 'new',
                  NULL, NULL, NULL, NULL, NULL, NULL,
                  ?, 'created', datetime('now'), ?, ?)
        """,
            (internal_id, data.get("id"), reading, mode),
        )
        db.commit()
    except Exception:
        app.logger.exception("create-order DB note failed")

    return jsonify(data), 201

@app.route("/api/paypal/orders/<paypal_order_id>/capture", methods=["POST"])
def api_paypal_capture(paypal_order_id):
    try:
        token = get_paypal_access_token()
        r = requests.post(
            f"{PAYPAL_API_BASE}/v2/checkout/orders/{paypal_order_id}/capture",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException:
        app.logger.exception("PayPal capture failed")
        return {"error": "paypal_capture_failed"}, 502

    # require final status
    if data.get("status") != "COMPLETED":
        return {"error": "not_completed", "raw": data}, 400

    internal_id = request.args.get("order_id")
    reading = request.args.get("reading")
    mode = request.args.get("mode")

    # pull the paid amount from capture payload
    try:
        cap = data["purchase_units"][0]["payments"]["captures"][0]
        amount_value = float(cap["amount"]["value"])
        amount_ccy = cap["amount"]["currency_code"]
    except Exception as e:
        app.logger.exception("Failed to parse PayPal capture amount")
        return {"error": f"parse_amount_failed: {e}", "raw": data}, 500

    # attempt to read payer info
    payer_email = None
    payer_name = None
    try:
        payer = data.get("payer") or {}
        payer_email = payer.get("email_address")
        name = payer.get("name") or {}
        if name:
            gn = name.get("given_name") or ""
            sn = name.get("surname") or ""
            payer_name = (gn + " " + sn).strip() or None
        if not payer_name:
            ship = (data.get("purchase_units") or [{}])[0].get("shipping") or {}
            full_name = (ship.get("name") or {}).get("full_name")
            payer_name = full_name or payer_name
    except Exception:
        app.logger.info("No payer name/email in capture payload")

    db = get_db()
    try:
        # 1) upsert the order row as paid
        db.execute(
            """
            INSERT OR IGNORE INTO orders (
                order_id, timestamp, name, email, total_price, payment_status, completion_status,
                birth_date, birth_time, birth_place, secondary_birth_date, secondary_birth_time, secondary_birth_place,
                paypal_order_id, status, created_at, captured_at, reading, mode
            ) VALUES (?, datetime('now'), NULL, NULL, ?, 'paid', 'new',
                      NULL, NULL, NULL, NULL, NULL, NULL,
                      ?, 'captured', datetime('now'), datetime('now'), ?, ?)
            """,
            (internal_id, amount_value, paypal_order_id, reading, mode),
        )

        # 2) if it existed already, make sure totals/status are updated
        db.execute(
            """
            UPDATE orders
               SET total_price = COALESCE(?, total_price),
                   payment_status = 'paid',
                   status = 'captured',
                   captured_at = datetime('now'),
                   paypal_order_id = COALESCE(?, paypal_order_id),
                   reading = COALESCE(?, reading),
                   mode = COALESCE(?, mode),
                   email = COALESCE(?, email),
                   name = COALESCE(?, name)
             WHERE order_id = ?
            """,
            (amount_value, paypal_order_id, reading, mode, payer_email, payer_name, internal_id),
        )

        # 3) insert a single line item that mirrors the reading
        db.execute(
            """
            INSERT OR IGNORE INTO order_items (order_id, item_id, reading_type, reading_mode, price, question)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (internal_id, str(uuid4()), reading, mode, amount_value),
        )

        db.commit()
    except Exception as e:
        db.rollback()
        app.logger.exception("DB error updating order after capture")
        return {"error": f"db_error: {e}"}, 500

    return {"redirect": url_for("thankyou", status="paid", order_id=internal_id)}, 200

@app.route("/webhooks/paypal", methods=["POST"])
def paypal_webhook():
    if not PAYPAL_WEBHOOK_ID:
        app.logger.error("PAYPAL_WEBHOOK_ID not set; cannot verify webhook")
        return make_response("", 400)
    headers = request.headers
    required_headers = [
        "PAYPAL-TRANSMISSION-ID",
        "PAYPAL-TRANSMISSION-TIME",
        "PAYPAL-TRANSMISSION-SIG",
        "PAYPAL-AUTH-ALGO",
        "PAYPAL-CERT-URL"
    ]
    actual_headers = {h: headers.get(h) for h in required_headers}
    webhook_id = PAYPAL_WEBHOOK_ID
    verify_body = {
        "transmission_id": actual_headers["PAYPAL-TRANSMISSION-ID"],
        "transmission_time": actual_headers["PAYPAL-TRANSMISSION-TIME"],
        "cert_url": actual_headers["PAYPAL-CERT-URL"],
        "auth_algo": actual_headers["PAYPAL-AUTH-ALGO"],
        "transmission_sig": actual_headers["PAYPAL-TRANSMISSION-SIG"],
        "webhook_id": webhook_id,
        "webhook_event": request.get_json(force=True)
    }
    resp = requests.post(
        f"{PAYPAL_API_BASE}/v1/notifications/verify-webhook-signature",
        json=verify_body,
        headers={
            "Authorization": f"Bearer {get_paypal_access_token()}",
            "Content-Type": "application/json",
        },
        timeout=20,
    )
    try:
        resp.raise_for_status()
        result = resp.json()
    except Exception:
        app.logger.exception("PayPal webhook verify failed")
        return make_response("", 400)
    event = verify_body["webhook_event"]
    # Only update paid if verified and correct event
    if (
        result.get("verification_status") == "SUCCESS"
        and event.get("event_type") == "PAYMENT.CAPTURE.COMPLETED"
    ):
        custom_id = event.get("resource", {}).get("custom_id")
        if custom_id:
            with app.app_context():
                db = get_db()
                db.execute("UPDATE orders SET payment_status = 'paid' WHERE order_id = ?", (custom_id,))
                db.commit()
    return make_response("", 200)

@app.route("/webhooks/crypto", methods=["POST"])
def crypto_webhook():
    signature = request.headers.get("x-nowpayments-sig", "")
    raw_body = request.get_data()
    try:
        calc_sig = hmac.new(
            NOWPAYMENTS_IPN_SECRET.encode("utf-8"), raw_body, hashlib.sha512
        ).hexdigest()
    except Exception:
        app.logger.exception("NOWPayments signature generation failed")
        return "invalid signature", 403
    if not hmac.compare_digest(calc_sig, signature):
        app.logger.warning("NOWPayments signature mismatch")
        return "invalid signature", 403

    data = request.get_json(force=True)
    payment_status = data.get("payment_status")
    order_id = data.get("order_id")
    pay_amount = data.get("pay_amount")

    if not order_id:
        return "no order id", 200

    if payment_status in ("finished", "confirmed", "paid"):
        try:
            db = get_db()
            db.execute(
                """
                UPDATE orders
                SET payment_status='paid',
                    status='captured',
                    total_price=COALESCE(?, total_price),
                    captured_at=datetime('now')
                WHERE order_id=?
                """,
                (pay_amount, order_id),
            )
            db.execute(
                """
                INSERT OR IGNORE INTO order_items (order_id, item_id, reading_type, reading_mode, price, question)
                SELECT order_id, ?, reading, mode, total_price, NULL FROM orders WHERE order_id=?
                """,
                (str(uuid4()), order_id),
            )
            db.commit()
        except Exception:
            app.logger.exception("NOWPayments DB update error")
    return "OK", 200

# --- CONTACT FORM ---

@app.route("/submit_contact", methods=["POST"])
def submit_contact():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    message = request.form.get("message", "").strip()

    # Make sure data/ exists
    Path(BASE_DIR / "data").mkdir(exist_ok=True)

    # Append a CSV row safely (handles quotes/commas)
    with open(BASE_DIR / "data" / "contact_messages.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.utcnow().isoformat(), name, email, message])

    flash("Thank you — your message was sent.", "success")
    return redirect(url_for("thankyou"))

# --- PADDLE WEBHOOK ROUTE (Future Implementation) ---
# NOTE: This route is for future implementation. The logic will be complex.
# @app.route("/paddle-webhook", methods=["POST"])
# def paddle_webhook():
#     # 1. Verify Signature
#     # 2. Parse JSON body (get custom data: reading_slug, reading_mode)
#     # 3. Log order to SQLite (db.execute INSERT)
#     # 4. Send fulfillment email
#     # 5. Return 200 OK
#     pass 


if __name__ == "__main__":
    app.logger.info(">>> Initializing database...")
    init_db()
    app.logger.info(">>> Running app...")
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
