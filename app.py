# app.py
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from pathlib import Path
from datetime import datetime
import sqlite3
import csv 
import uuid # Still useful if we generate internal IDs, though not needed for cart logic now

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
DATABASE = 'data/omen_orders.db'
# IMPORTANT: This secret key is for development only. Use a long, random key in production.
app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)
app.secret_key = b'your_long_and_secret_key_here' 


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

def init_db():
    """Initializes the database schema."""
    with app.app_context():
        db = get_db()
        # The 'orders' table will store finalized, paid orders
        db.execute("""
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
                secondary_birth_place TEXT,
                UNIQUE (order_id)
            );
        """)
        # The 'order_items' table stores the details of each reading in the order
        db.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                order_id TEXT NOT NULL,
                item_id TEXT PRIMARY KEY,
                reading_type TEXT,
                reading_mode TEXT,
                price REAL,
                question TEXT,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            );
        """)
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

# **ACTION REQUIRED: PASTE YOUR 14 PADDLE CHECKOUT LINKS HERE**
PADDLE_LINKS = {
    "natal_pdf":       "https://pay.paddle.com/checkout/purchase?price_id=pri_01k8qevj415818w1pdqpw16pn7", # Based on your image
    "natal_call":      "https://pay.paddle.com/checkout/purchase?price_id=pri_01k8qf43yqv9w8jg3ta61h5cfy", # Based on your image
    
    "orientation_pdf": "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_ORIENTATION_PDF_PRICE_ID]",
    "orientation_call": "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_ORIENTATION_CALL_PRICE_ID]",
    
    "love_pdf":        "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_LOVE_PDF_PRICE_ID]",
    "love_call":       "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_LOVE_CALL_PRICE_ID]",
    
    "focus_pdf":       "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_FOCUS_PDF_PRICE_ID]",
    "focus_call":      "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_FOCUS_CALL_PRICE_ID]",
    
    "annual_pdf":      "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_ANNUAL_PDF_PRICE_ID]",
    "annual_call":     "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_ANNUAL_CALL_PRICE_ID]",
    
    "horary_pdf":      "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_HORARY_PDF_PRICE_ID]",
    "horary_call":     "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_HORARY_CALL_PRICE_ID]",
    
    "synastry_pdf":    "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_SYNASTRY_PDF_PRICE_ID]",
    "synastry_call":   "https://pay.paddle.com/checkout/purchase?price_id=[YOUR_SYNASTRY_CALL_PRICE_ID]",
}


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
    # Pass both readings data and paddle links to the template
    return render_template("readings.html", readings=READINGS, paddle_links=PADDLE_LINKS, cart_count=0)

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
    # Note: In a real integration, the webhook would trigger order logging, 
    # and this page would simply confirm receipt.
    status = request.args.get('status')
    order_id = request.args.get('order_id')
    
    # Simple status display
    if status == 'success':
        flash('Payment confirmed and order received. Thank you.', 'success')
    elif status == 'failed':
        flash('Payment failed. Please try again or contact support.', 'error')
    
    return render_template("thankyou.html", 
                           cart_count=0,
                           status=status,
                           order_id=order_id,
                           video_session_needed=False) # Simplified, assumed false for now


# --- DEPRECATED/REMOVED CART & MOCK PAYMENT ROUTES ---

@app.route("/booking")
def booking():
    # DEPRECATED: Redirecting to readings page to start flow over
    flash('The old booking page has been removed. Please select a reading below.', 'info')
    return redirect(url_for("readings"))

@app.route("/submit_booking", methods=["POST"])
def submit_booking():
    # DEPRECATED: Redirecting to readings page
    return redirect(url_for("readings")) 

@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    # DEPRECATED: The cart is removed.
    flash('The shopping cart has been removed. Please use the direct order buttons.', 'info')
    return redirect(url_for("readings"))

@app.route("/cart")
def cart():
    # DEPRECATED: The cart page is removed.
    return redirect(url_for("readings"))

@app.route("/remove_from_cart/<item_id>")
def remove_from_cart(item_id):
    # DEPRECATED: The cart is removed.
    return redirect(url_for("readings"))

@app.route("/data_entry")
def data_entry():
    # DEPRECATED: Data collection moves to a new pre-checkout form (not implemented yet)
    return redirect(url_for("readings"))

@app.route("/save_data", methods=["POST"])
def save_data():
    # DEPRECATED
    return redirect(url_for("readings"))

@app.route("/checkout")
def checkout():
    # DEPRECATED
    return redirect(url_for("readings"))

@app.route("/mock_payment_gateway")
def mock_payment_gateway():
    # DEPRECATED
    return redirect(url_for("readings"))

@app.route("/payment_success")
def payment_success():
    # DEPRECATED. A REAL PADDLE WEBHOOK WILL REPLACE THIS ROUTE LATER.
    return redirect(url_for("readings"))

@app.route("/clear_cart")
def clear_cart():
    # DEPRECATED
    return redirect(url_for("readings"))

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
    print(">>> Initializing database...")
    init_db()
    print(">>> Running app...")
    app.run(debug=True)