# app.py
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from pathlib import Path
from datetime import datetime
import sqlite3
import uuid
import csv # Keeping this import for contact form only

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


# --- READING DATA (MOCK PRICES) ---
READINGS = {
    "natal": {"name": "Natal Chart Analysis", "pdf_price": 90, "video_price": 120},
    "orientation": {"name": "Orientation / Career Guidance", "pdf_price": 70, "video_price": 90},
    "love": {"name": "Love & Relationship Guidance", "pdf_price": 70, "video_price": 90},
    "focus": {"name": "Other Focus Area", "pdf_price": 60, "video_price": 80},
    "annual": {"name": "Annual Horoscope (Solar Return)", "pdf_price": 85, "video_price": 110},
    "horary": {"name": "Horary Chart Analysis", "pdf_price": 55, "video_price": 75},
    "synastry": {"name": "Synastry", "pdf_price": 95, "video_price": 125},
}


# --- CART UTILITIES ---

def get_cart_data():
    """Retrieves and calculates total for the current cart in the session."""
    cart_items = session.get('cart', {})
    cart_list = []
    total_price = 0
    
    # Data is considered filled if all required fields are present in the 'customer_info'
    # and all questions have been answered.
    data_is_filled = (
        session.get('customer_info', {}).get('name') and 
        session.get('customer_info', {}).get('email') and
        session.get('customer_info', {}).get('birth_date') and
        all(item.get('question') for item in cart_items.values())
    )
    
    # Check for Synastry to see if secondary person's details are needed
    synastry_in_cart = any(item.get('reading_type') == 'synastry' for item in cart_items.values())
    
    for item_id, item in cart_items.items():
        type_key = item['reading_type']
        mode = item['reading_mode']
        
        reading_info = READINGS.get(type_key, {})
        
        if mode == 'pdf':
            price = reading_info.get('pdf_price', 0)
        else:
            price = reading_info.get('video_price', 0)
        
        item['name'] = reading_info.get('name', 'Unknown Reading')
        item['price'] = price
        item['id'] = item_id
        cart_list.append(item)
        total_price += price

    return cart_list, total_price, data_is_filled, synastry_in_cart

def get_cart_count():
    return len(session.get('cart', {}))

# --- BASIC PAGES ---
@app.route("/", endpoint="home")
def home():
    return render_template("index.html", cart_count=get_cart_count())

@app.route("/about")
def about():
    return render_template("about.html", cart_count=get_cart_count())

@app.route("/readings")
def readings():
    return render_template("readings.html", readings=READINGS, cart_count=get_cart_count())

@app.route("/contact")
def contact():
    return render_template("contact.html", cart_count=get_cart_count())

@app.route("/faq")
def faq():
    return render_template("faq.html", cart_count=get_cart_count())

@app.route("/privacy")
def privacy():
    return render_template("privacy.html", cart_count=get_cart_count())

# Updated thankyou to handle success/failure status
@app.route("/thankyou")
def thankyou():
    status = request.args.get('status')
    order_id = request.args.get('order_id')
    
    db = get_db()
    video_session_needed = False
    
    if order_id:
        cursor = db.execute("SELECT reading_mode FROM order_items WHERE order_id = ?", (order_id,))
        items = cursor.fetchall()
        for item in items:
            if item['reading_mode'] == 'video':
                video_session_needed = True
                break

    return render_template("thankyou.html", 
                           cart_count=get_cart_count(),
                           status=status,
                           order_id=order_id,
                           video_session_needed=video_session_needed)


# --- CART ROUTES ---

@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    reading_type = request.form.get("reading_type")
    reading_mode = request.form.get("reading_mode")
    
    if reading_type not in READINGS:
        flash('Invalid reading type.', 'error')
        return redirect(url_for("readings"))

    if 'cart' not in session:
        session['cart'] = {}
    
    item_id = str(uuid.uuid4())
    
    session['cart'][item_id] = {
        'reading_type': reading_type,
        'reading_mode': reading_mode,
        'question': None # Only question is stored per item
    }
    
    # Ensure session modification is recognized
    session.modified = True
    
    # **TWEAK:** Redirect back to readings page, do not go to cart immediately
    flash(f'{READINGS[reading_type]["name"]} ({reading_mode.upper()}) added to cart.', 'success')
    return redirect(url_for("readings"))

@app.route("/cart")
def cart():
    cart_list, total_price, data_is_filled, synastry_in_cart = get_cart_data()
    return render_template("cart.html", 
                           cart_items=cart_list, 
                           total_price=total_price,
                           data_is_filled=data_is_filled,
                           synastry_in_cart=synastry_in_cart,
                           cart_count=len(cart_list))

@app.route("/remove_from_cart/<item_id>")
def remove_from_cart(item_id):
    if 'cart' in session and item_id in session['cart']:
        reading_type = session['cart'][item_id]['reading_type']
        reading_name = READINGS.get(reading_type, {}).get('name', 'Item')
        
        del session['cart'][item_id]
        session.modified = True # Ensure session modification is recognized
        flash(f'{reading_name} removed from cart.', 'success')
    else:
        flash('Item not found in cart.', 'error')
        
    return redirect(url_for("cart"))


# --- 1. DATA ENTRY ROUTES (UNIFIED FORM) ---

@app.route("/data_entry")
def data_entry():
    cart_items, _, _, synastry_in_cart = get_cart_data()
    if not cart_items:
        flash('Your cart is empty. Nothing to fill.', 'warning')
        return redirect(url_for('readings'))
        
    # Get the latest data from the session to pre-fill the form
    customer_info = session.get('customer_info', {})
    cart_data = session.get('cart', {})

    return render_template("data_entry.html", 
                           cart_items=cart_items,
                           customer_info=customer_info,
                           cart_data=cart_data, # Pass raw data for pre-filling
                           synastry_in_cart=synastry_in_cart,
                           cart_count=get_cart_count())

@app.route("/save_data", methods=["POST"])
def save_data():
    cart = session.get('cart', {})
    
    # 1. Collect name/email and main chart data
    session['customer_info'] = {
        'name': request.form.get("customer_name"),
        'email': request.form.get("customer_email"),
        'birth_date': request.form.get("main_birth_date"),
        'birth_time': request.form.get("main_birth_time"),
        'birth_place': request.form.get("main_birth_place"),
        # Secondary person (optional/synastry)
        'secondary_birth_date': request.form.get("secondary_birth_date"),
        'secondary_birth_time': request.form.get("secondary_birth_time"),
        'secondary_birth_place': request.form.get("secondary_birth_place"),
    }
    
    # Simple validation on main fields
    is_valid = (
        session['customer_info'].get('name') and
        session['customer_info'].get('email') and
        session['customer_info'].get('birth_date') and
        session['customer_info'].get('birth_place')
    )

    # 2. Iterate through form submissions for each item's specific question
    all_questions_answered = True
    for item_id, item_data in cart.items():
        question = request.form.get(f'question_{item_id}', '').strip()
        
        # Horary does not require birth data, but still requires a question
        if not question:
            all_questions_answered = False

        # Update session cart item with collected question
        item_data['question'] = question
        
    session.modified = True
    
    if is_valid and all_questions_answered:
        flash('All required details saved successfully. Proceed to checkout.', 'success')
    else:
        # Check specific reasons for error
        if not is_valid:
             flash('Please fill in your Contact Info (Name, Email) and your Main Birth Data (Date, Time, Place).', 'warning')
        if not all_questions_answered:
             flash('Please provide a specific Question/Focus for every reading in your cart.', 'warning')

    return redirect(url_for("cart"))


# --- 2. MOCK PAYMENT LOGIC (Generic Hosted Gateway) ---

@app.route("/checkout")
def checkout():
    cart_items, total_price, data_is_filled, _ = get_cart_data()
    customer_info = session.get('customer_info', {})
    
    if not cart_items:
        flash('Cannot checkout: cart is empty.', 'error')
        return redirect(url_for('readings'))

    if not data_is_filled:
        flash('Please fill in ALL required chart details and contact info before checking out.', 'warning')
        return redirect(url_for('data_entry'))
        
    # Generate a unique Order ID for this transaction (to track from the gateway)
    order_id = str(uuid.uuid4())
    session['checkout_order_id'] = order_id
    
    # --- MOCK PAYMENT GATEWAY REDIRECTION ---
    mock_gateway_url = url_for('mock_payment_gateway', 
                                total=total_price, 
                                order_id=order_id, 
                                email=customer_info.get('email'))
                                
    return redirect(mock_gateway_url)

@app.route("/mock_payment_gateway")
def mock_payment_gateway():
    """Simulates the external payment page of 2Checkout, Paddle, etc."""
    total = request.args.get('total')
    order_id = request.args.get('order_id')
    email = request.args.get('email')
    
    success_url = url_for('payment_success', order_id=order_id, status='paid')
    fail_url = url_for('thankyou', status='failed')

    return render_template("mock_payment_gateway.html", 
                            total=total, 
                            order_id=order_id,
                            email=email,
                            success_url=success_url,
                            fail_url=fail_url)
                            
                            
# --- 3. FINALIZATION ROUTE (Simulating Gateway Webhook/Return) ---

@app.route("/payment_success")
def payment_success():
    """
    This simulates the success/return URL from the Payment Gateway.
    The order is ONLY saved permanently here, after payment is confirmed.
    """
    order_id = request.args.get('order_id')
    
    if order_id != session.get('checkout_order_id'):
        flash('Security check failed. Order ID mismatch.', 'error')
        return redirect(url_for('thankyou', status='error'))

    cart_items, total_price, _, _ = get_cart_data()
    customer_info = session.get('customer_info', {})
    
    if not cart_items:
        # Allow processing if order was already saved but user refreshed
        db = get_db()
        cursor = db.execute("SELECT order_id FROM orders WHERE order_id = ?", (order_id,))
        if cursor.fetchone():
             flash('Order was already recorded. Redirecting.', 'info')
             return redirect(url_for('thankyou', status='paid', order_id=order_id)) 
        else:
             flash('Order error: Cart empty and ID not found in database.', 'error')
             return redirect(url_for('thankyou', status='error'))

    # --- SAVE TO PERMANENT DATABASE (SQLite) ---
    db = get_db()
    
    try:
        # Save the main Order row with the UNIFIED chart data
        db.execute(
            """INSERT INTO orders (
                order_id, timestamp, name, email, total_price, payment_status, completion_status,
                birth_date, birth_time, birth_place, secondary_birth_date, secondary_birth_time, secondary_birth_place
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, datetime.utcnow().isoformat(), 
             customer_info['name'], customer_info['email'], total_price, 'paid', 'new',
             customer_info.get('birth_date'), customer_info.get('birth_time'), customer_info.get('birth_place'),
             customer_info.get('secondary_birth_date'), customer_info.get('secondary_birth_time'), customer_info.get('secondary_birth_place'),
            )
        )

        # Save the Order Items (only the question is stored here)
        for item in cart_items:
            db.execute(
                "INSERT INTO order_items (order_id, item_id, reading_type, reading_mode, price, question) VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, item['id'], item['reading_type'], item['reading_mode'], item['price'], item['question'])
            )
        
        db.commit()
        
        # --- CLEAR SESSION CART & INFO ---
        session.pop('cart', None)
        session.pop('customer_info', None)
        session.pop('checkout_order_id', None)
        session.modified = True
        
        flash('Payment successful and order details saved.', 'success')
        
    except sqlite3.IntegrityError:
        flash('Order was already recorded. Redirecting.', 'info')
    except Exception as e:
        db.rollback()
        flash(f'An error occurred saving the order: {e}. Please contact support.', 'error')
        return redirect(url_for('thankyou', status='error'))

    return redirect(url_for('thankyou', status='paid', order_id=order_id))


# --- OTHER ROUTES ---

@app.route("/booking")
def booking():
    # Redirecting users to the proper flow
    return redirect(url_for("readings"))

@app.route("/submit_booking", methods=["POST"])
def submit_booking():
    # Deprecated route, redirecting
    return redirect(url_for("readings")) 


@app.route("/clear_cart")
def clear_cart():
    # Remove the entire cart dictionary from the session
    session.pop('cart', None)
    
    # Optionally remove customer info as well, since the cart is empty
    session.pop('customer_info', None)
    
    session.modified = True
    flash('Your cart has been emptied.', 'success')
    return redirect(url_for("readings")) # Redirect them back to shopping

@app.route("/submit_contact", methods=["POST"])
def submit_contact():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    message = request.form.get("message", "").strip()

    # Make sure data/ exists
    Path(BASE_DIR / "data").mkdir(exist_ok=True)

    # Append a CSV row safely (handles quotes/commas)
    import csv
    with open(BASE_DIR / "data" / "contact_messages.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        from datetime import datetime
        writer.writerow([datetime.utcnow().isoformat(), name, email, message])

    flash("Thank you — your message was sent.", "success")
    return redirect(url_for("thankyou"))

if __name__ == "__main__":
    print(">>> Initializing database...")
    init_db()
    print(">>> Running app...")
    app.run(debug=True)