# app.py
from flask import Flask, render_template, request, redirect, url_for
import csv
from pathlib import Path
from datetime import datetime

app = Flask(
    __name__,
    static_folder="static",        # /static -> static/
    template_folder="templates"    # Jinja templates
)

# ---------- PAGES ----------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/readings")
def readings():
    return render_template("readings.html")

@app.route("/booking")
def booking():
    return render_template("booking.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/faq")
def faq():
    return render_template("faq.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/thankyou")
def thankyou():
    return render_template("thankyou.html")  # create a tiny template

# =========================================
# [APP.PY - SUBMIT BOOKING HANDLER]
# =========================================
@app.route("/submit_booking", methods=["POST"])
def submit_booking():
    # Grab fields from the form
    name         = request.form.get("name", "").strip()
    email        = request.form.get("email", "").strip()
    reading_type = request.form.get("reading_type", "").strip()
    birth_date   = request.form.get("birth_date", "").strip()
    birth_time   = request.form.get("birth_time", "").strip()
    birth_place  = request.form.get("birth_place", "").strip()
    question     = request.form.get("question", "").strip()
    agree        = request.form.get("agree", "") == "on"

    if not name or not email or not reading_type or not agree:
        return redirect(url_for("booking"))

    # Save to CSV (as before)
    from pathlib import Path
    from datetime import datetime
    import csv
    data_dir = Path("data"); data_dir.mkdir(exist_ok=True)
    csv_path = data_dir / "bookings.csv"
    new_file = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp","name","email","reading_type","birth_date","birth_time","birth_place","question"])
        w.writerow([datetime.utcnow().isoformat(), name, email, reading_type, birth_date, birth_time, birth_place, question])

    # Redirect back to Booking with a hash to trigger the modal (no JS)
    return redirect(url_for("booking") + "#thanks")



if __name__ == "__main__":
    # Debug mode for local testing; remove or set via env in production
    app.run(debug=True)
