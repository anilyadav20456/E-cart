import os
import random
import bcrypt
import traceback
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for, flash, make_response
from utils.pdf_generator import generate_pdf
from flask_mail import Mail, Message
import mysql.connector
import sqlite3
from werkzeug.utils import secure_filename
import config  # Imports settings from config.py
import razorpay

app = Flask(__name__)
@app.context_processor
def inject_product_image_url():
    """Allow products to use either a local upload or an external HTTPS image."""
    def product_image_url(image):
        if image and image.startswith(("https://", "http://")):
            return image
        return url_for("static", filename="uploads/product_images/" + (image or ""))

    return {"product_image_url": product_image_url}

@app.context_processor
def inject_cart_count():

    if "user_id" not in session:
        return {"cart_count": 0}

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COALESCE(SUM(quantity),0)
        FROM cart
        WHERE user_id=%s
        """,
        (session["user_id"],)
    )

    cart_count = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return {"cart_count": cart_count}
# -------------------------------
# Configuration Setup
# -------------------------------
UPLOAD_FOLDER = "static/uploads/product_images"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.secret_key = config.SECRET_KEY

ADMIN_UPLOAD_FOLDER = "static/uploads/admin_profiles"
app.config["ADMIN_UPLOAD_FOLDER"] = ADMIN_UPLOAD_FOLDER

app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD

mail = Mail(app)

razorpay_client = razorpay.Client(
    auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)
)


# -------------------------------
# SQLite Database Wrapper
# -------------------------------
class SQLiteDictCursor:
    def __init__(self, conn, dictionary=False):
        self.conn = conn
        self.cursor = conn.cursor()
        self.dictionary = dictionary
        self.lastrowid = None

    def execute(self, query, params=None):
        query_sql = query.replace('%s', '?')
        if params is not None:
            res = self.cursor.execute(query_sql, params)
        else:
            res = self.cursor.execute(query_sql)
        self.lastrowid = self.cursor.lastrowid
        return res

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        if self.dictionary:
            colnames = [d[0] for d in self.cursor.description]
            return dict(zip(colnames, row))
        return row

    def fetchall(self):
        rows = self.cursor.fetchall()
        if self.dictionary:
            colnames = [d[0] for d in self.cursor.description]
            return [dict(zip(colnames, r)) for r in rows]
        return rows

    def close(self):
        self.cursor.close()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, 'smartcart.db')

class SQLiteConnWrapper:
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)

    def cursor(self, dictionary=False):
        return SQLiteDictCursor(self.conn, dictionary=dictionary)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

def _ensure_sqlite_columns(conn_wrapper):
    try:
        cur = conn_wrapper.cursor(dictionary=True)
        cur.execute("PRAGMA table_info(users)")
        u_cols = [r['name'] for r in cur.fetchall() if isinstance(r, dict) and 'name' in r]
        if 'address' not in u_cols:
            cur.execute("ALTER TABLE users ADD COLUMN address TEXT")

        cur.execute("PRAGMA table_info(orders)")
        o_cols = [r['name'] for r in cur.fetchall() if isinstance(r, dict) and 'name' in r]
        if 'shipping_address' not in o_cols:
            cur.execute("ALTER TABLE orders ADD COLUMN shipping_address TEXT")
        conn_wrapper.commit()
        cur.close()
    except Exception:
        pass

def get_db_connection():
    try:
        wrapper = SQLiteConnWrapper(DEFAULT_DB_PATH)
        _ensure_sqlite_columns(wrapper)
        return wrapper
    except Exception:
        return mysql.connector.connect(
            host=config.DB_HOST,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME
        )
    
    
# --------------------------------
# User Signup Page
# --------------------------------
@app.route('/user-signup', methods=['GET'])
def user_signup_page():
    return render_template("user/user_signup.html")


# --------------------------------
# User Signup
# --------------------------------
@app.route("/user-signup", methods=["POST"])
def user_signup():

    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    phone = request.form["phone"].strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE email=%s",
        (email,)
    )

    user = cursor.fetchone()

    if user:
        flash("Email already registered!", "danger")

        cursor.close()
        conn.close()

        return redirect("/user-signup")
    
    

    # These keys are consumed after the user confirms the OTP.
    session["user_fullname"] = name
    session["user_email"] = email
    session["user_phone"] = phone

    otp = random.randint(100000,999999)

    session["user_otp"] = otp

    message = Message(
        subject="SmartCart User OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )

    message.body=f"""
Hello {name},

Your SmartCart OTP is:

{otp}

Thank You.
"""

    mail.send(message)

    cursor.close()
    conn.close()

    flash("OTP sent successfully!", "success")

    return redirect("/verify-user-otp")



# --------------------------------
# User Verify OTP Page
# --------------------------------
@app.route("/verify-user-otp", methods=["GET"])
def verify_user_otp_page():

    return render_template("user/verify_user_otp.html")


# --------------------------------
# Verify User OTP
# --------------------------------
@app.route("/verify-user-otp", methods=["POST"])
def verify_user_otp():

    user_otp = request.form["otp"]
    password = request.form["password"]

    if str(session.get("user_otp")) != str(user_otp):

        flash("Invalid OTP!", "danger")
        return redirect("/verify-user-otp")

    hashed_password = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    session["user_password"] = hashed_password

    fullname = session.get("user_fullname")
    email = session.get("user_email")
    if not fullname or not email:
        flash("Your registration session expired. Please sign up again.", "danger")
        return redirect("/user-signup")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO users(fullname, email, phone, password)
    VALUES (%s, %s, %s, %s)
    """, (fullname, email, session.get("user_phone"), hashed_password))

    conn.commit()

    cursor.close()
    conn.close()

    session.pop("user_otp", None)
    session.pop("user_fullname", None)
    session.pop("user_email", None)
    session.pop("user_phone", None)
    session.pop("user_password", None)

    flash("Registration Successful!", "success")

    return redirect("/user-login")

# --------------------------------
# User Login Page
# --------------------------------
@app.route("/user-login", methods=["GET"])
def user_login_page():

    return render_template("user/user_login.html")


# --------------------------------
# User Login
# --------------------------------
@app.route("/user-login", methods=["POST"])
def user_login():

    email = request.form["email"].strip().lower()
    password = request.form["password"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id AS user_id, fullname, email, password FROM users WHERE email=%s",
        (email,)
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user and bcrypt.checkpw(
        password.encode("utf-8"),
        user["password"].encode("utf-8")
    ):

        session["user_id"] = user["user_id"]
        session["user_name"] = user["fullname"]
        session["user_email"] = user["email"]

        flash("Login Successful!", "success")

        return redirect("/user-home")

    flash("Invalid Email or Password!", "danger")

    return redirect("/user-login")


# --------------------------------
# Forgot Password Page
# --------------------------------
@app.route("/forgot-password", methods=["GET"])
def forgot_password_page():

    return render_template("user/forgot_password.html")


# --------------------------------
# Forgot Password
# --------------------------------
@app.route("/forgot-password", methods=["POST"])
def forgot_password():

    email = request.form.get("email", "").strip().lower()

    if not email:
        flash("Please enter a valid email address!", "danger")
        return redirect("/forgot-password")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE email=%s",
        (email,)
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user:

        flash("Email not registered!", "danger")

        return redirect("/forgot-password")

    otp = random.randint(100000, 999999)

    session["reset_email"] = email
    session["reset_otp"] = otp
    session["reset_verified"] = False

    message = Message(
        subject="SmartCart Password Reset OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )

    message.body = f"""
Hello,

Your Password Reset OTP is:

{otp}

Thank You.
"""

    try:
        mail.send(message)
    except Exception as e:
        flash(f"Failed to send OTP email: {str(e)}", "danger")
        return redirect("/forgot-password")

    flash("OTP sent successfully!", "success")

    return redirect("/verify-reset-otp")


# --------------------------------
# Verify Reset OTP Page
# --------------------------------
@app.route("/verify-reset-otp", methods=["GET"])
def verify_reset_otp_page():

    if not session.get("reset_email") or not session.get("reset_otp"):
        flash("Please request a password reset first.", "warning")
        return redirect("/forgot-password")

    return render_template("user/verify_reset_otp.html")


# --------------------------------
# Verify Reset OTP
# --------------------------------
@app.route("/verify-reset-otp", methods=["POST"])
def verify_reset_otp():

    if not session.get("reset_email") or not session.get("reset_otp"):
        flash("Session expired. Please request a new password reset OTP.", "danger")
        return redirect("/forgot-password")

    otp = request.form.get("otp", "").strip()

    if str(session.get("reset_otp")) != str(otp):

        flash("Invalid OTP!", "danger")

        return redirect("/verify-reset-otp")

    session["reset_verified"] = True

    flash("OTP Verified Successfully!", "success")

    return redirect("/reset-password")


# --------------------------------
# Reset Password Page
# --------------------------------
@app.route("/reset-password", methods=["GET"])
def reset_password_page():

    if not session.get("reset_email") or not session.get("reset_verified"):
        flash("Please verify your OTP first.", "warning")
        return redirect("/forgot-password")

    return render_template("user/reset_password.html")


# --------------------------------
# Update Password
# --------------------------------
@app.route("/reset-password", methods=["POST"])
def reset_password():

    if not session.get("reset_email") or not session.get("reset_verified"):
        flash("Session expired or unauthorized request. Please try again.", "danger")
        return redirect("/forgot-password")

    password = request.form.get("password", "")

    if not password:
        flash("Please enter a new password!", "danger")
        return redirect("/reset-password")

    hashed_password = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE users
        SET password=%s
        WHERE email=%s
        """,
        (
            hashed_password,
            session["reset_email"]
        )
    )

    conn.commit()

    cursor.close()
    conn.close()

    session.pop("reset_email", None)
    session.pop("reset_otp", None)
    session.pop("reset_verified", None)

    flash("Password Updated Successfully!", "success")

    return redirect("/user-login")

# --------------------------------
# User Home
# --------------------------------
@app.route("/user-home")
def user_home():

    if "user_id" not in session:

        flash("Please login first!", "danger")
        return redirect("/user-login")

    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM products
        ORDER BY product_id DESC
        LIMIT 8
    """)

    products = cursor.fetchall()

    cursor.close()

    conn.close()

    return render_template(
        "user/home.html",
        user_name=session["user_name"],
        products=products
    )
    
# --------------------------------
# User Products
# --------------------------------
# User Products
# --------------------------------
@app.route("/products")
def user_products():

    if "user_id" not in session:

        flash("Please login first!", "danger")
        return redirect("/user-login")

    search = request.args.get("search", "")
    category = request.args.get("category", "")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = "SELECT * FROM products WHERE 1=1"
    values = []

    if search:

        query += " AND name LIKE %s"
        values.append(f"%{search}%")

    if category:

        query += " AND category=%s"
        values.append(category)

    cursor.execute(query, values)

    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "user/products.html",
        products=products,
        search=search,
        category=category
    )
# --------------------------------
# User Product Details
# --------------------------------
@app.route("/product/<int:product_id>")
def product_details(product_id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM products WHERE product_id=%s",
        (product_id,)
    )

    product = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "user/product_details.html",
        product=product
    )
    
  
# --------------------------------
# Add To Cart
# --------------------------------
@app.route("/add-to-cart/<int:product_id>")
def add_to_cart(product_id):

    # Check User Login
    if "user_id" not in session:

        flash("Please login first!", "danger")
        return redirect("/user-login")

    user_id = session["user_id"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check if product already exists in cart
    cursor.execute(
        """
        SELECT * FROM cart
        WHERE user_id=%s AND product_id=%s
        """,
        (user_id, product_id)
    )

    existing = cursor.fetchone()

    if existing:

        # Increase Quantity
        cursor.execute(
            """
            UPDATE cart
            SET quantity = quantity + 1
            WHERE user_id=%s AND product_id=%s
            """,
            (user_id, product_id)
        )

    else:

        # Insert New Product
        cursor.execute(
            """
            INSERT INTO cart(user_id, product_id, quantity)
            VALUES(%s,%s,%s)
            """,
            (user_id, product_id, 1)
        )

    conn.commit()

    cursor.execute("""
        SELECT COALESCE(SUM(quantity),0)
        FROM cart
        WHERE user_id=%s
    """, (user_id,))

    cart_count = cursor.fetchone()["COALESCE(SUM(quantity),0)"]

    cursor.execute("SELECT name FROM products WHERE product_id=%s", (product_id,))
    prod_row = cursor.fetchone()
    product_name = prod_row["name"] if prod_row else "Product"

    cursor.close()
    conn.close()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":

        return {
            "success": True,
            "cart_count": cart_count,
            "product_name": product_name
        }

    flash(f"'{product_name}' added to cart successfully!", "success")

    return redirect(request.referrer or url_for("user_products"))   

# --------------------------------
# My Cart
# --------------------------------
@app.route("/cart")
def view_cart():

    if "user_id" not in session:

        flash("Please login first!", "danger")
        return redirect("/user-login")

    user_id = session["user_id"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            cart.cart_id,
            cart.quantity,
            products.product_id,
            products.name,
            products.category,
            products.price,
            products.image
            
        FROM cart
        JOIN products
        ON cart.product_id = products.product_id
        WHERE cart.user_id=%s
    """, (user_id,))

    cart_items = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "user/cart.html",
        cart_items=cart_items
    )
    
#  ➕ Increase Quantity   
@app.route("/cart/increase/<int:cart_id>")
def increase_quantity(cart_id):

    if "user_id" not in session:

        return redirect("/user-login")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE cart
        SET quantity = quantity + 1
        WHERE cart_id=%s
    """, (cart_id,))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/cart")

# ➖ Decrease Quantity


@app.route("/cart/decrease/<int:cart_id>")
def decrease_quantity(cart_id):

    if "user_id" not in session:

        return redirect("/user-login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT quantity FROM cart WHERE cart_id=%s",
        (cart_id,)
    )

    item = cursor.fetchone()

    if item["quantity"] > 1:

        cursor.execute("""
            UPDATE cart
            SET quantity = quantity - 1
            WHERE cart_id=%s
        """, (cart_id,))

    else:

        cursor.execute(
            "DELETE FROM cart WHERE cart_id=%s",
            (cart_id,)
        )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/cart")

# 🗑 Remove Product

@app.route("/cart/remove/<int:cart_id>")
def remove_cart_item(cart_id):

    if "user_id" not in session:

        return redirect("/user-login")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM cart WHERE cart_id=%s",
        (cart_id,)
    )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/cart")
    




# --------------------------------
# Checkout Page
# --------------------------------
@app.route("/checkout")
def checkout():
    if "user_id" not in session:
        flash("Please login first!", "danger")
        return redirect("/user-login")

    try:
        selected_cart_ids = list({int(cart_id) for cart_id in request.args.get("cart_ids", "").split(",") if cart_id})
    except ValueError:
        selected_cart_ids = []

    if not selected_cart_ids:
        flash("Select at least one item before proceeding to checkout.", "warning")
        return redirect(url_for("view_cart"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    placeholders = ", ".join(["%s"] * len(selected_cart_ids))
    cursor.execute(f"""
        SELECT cart.*, products.name, products.price, products.image
        FROM cart
        JOIN products ON cart.product_id = products.product_id
        WHERE cart.user_id=%s AND cart.cart_id IN ({placeholders})
    """, [session["user_id"], *selected_cart_ids])
    cart_items = cursor.fetchall()

    cursor.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],))
    user_info = cursor.fetchone() or {}

    cursor.close()
    conn.close()

    if not cart_items:
        flash("The selected cart items are no longer available.", "warning")
        return redirect(url_for("view_cart"))

    total = sum(item["price"] * item["quantity"] for item in cart_items)
    return render_template("user/checkout.html", cart_items=cart_items, total=total, user=user_info)


# =================================================================
# ROUTE: CREATE RAZORPAY ORDER
# =================================================================
@app.route('/user/pay', methods=['GET', 'POST'])
def user_pay():

    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    cart_ids = request.form.get("cart_ids", "") or request.args.get("cart_ids", "")
    address = request.form.get("address", "").strip()
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip()
    pincode = request.form.get("pincode", "").strip()

    full_address = address
    location_parts = [p for p in [city, state, pincode] if p]
    if location_parts:
        if full_address:
            full_address += ", " + ", ".join(location_parts)
        else:
            full_address = ", ".join(location_parts)

    session['checkout_address'] = full_address

    selected_cart_ids = []
    if cart_ids:
        try:
            selected_cart_ids = [int(cart_id) for cart_id in cart_ids.split(",") if cart_id.strip()]
        except ValueError:
            selected_cart_ids = []

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if full_address:
        try:
            cursor.execute("UPDATE users SET address=%s WHERE id=%s AND (address IS NULL OR address='')", (full_address, session["user_id"]))
            conn.commit()
        except Exception:
            pass

    if selected_cart_ids:
        placeholders = ", ".join(["%s"] * len(selected_cart_ids))
        cursor.execute(f"""
            SELECT cart.*, products.name, products.price, products.image
            FROM cart
            JOIN products ON cart.product_id = products.product_id
            WHERE cart.user_id=%s AND cart.cart_id IN ({placeholders})
        """, [session["user_id"], *selected_cart_ids])
        cart_items = cursor.fetchall()
    else:
        cursor.execute("""
            SELECT cart.*, products.name, products.price, products.image
            FROM cart
            JOIN products ON cart.product_id = products.product_id
            WHERE cart.user_id=%s
        """, (session["user_id"],))
        cart_items = cursor.fetchall()

    cursor.close()
    conn.close()

    if not cart_items:
        cart = session.get('cart', {})
        if cart:
            total_amount = sum(item['price'] * item['quantity'] for item in cart.values())
        else:
            flash("Your cart is empty!", "danger")
            return redirect('/cart')
    else:
        total_amount = sum(item['price'] * item['quantity'] for item in cart_items)
        session["selected_cart_ids"] = [item["cart_id"] for item in cart_items]

    razorpay_amount = int(total_amount * 100)

    razorpay_order = razorpay_client.order.create({
        "amount": razorpay_amount,
        "currency": "INR",
        "payment_capture": "1"
    })

    session['razorpay_order_id'] = razorpay_order['id']
    session['checkout_total'] = total_amount

    return render_template(
        "user/payment.html",
        amount=total_amount,
        key_id=config.RAZORPAY_KEY_ID,
        order_id=razorpay_order['id']
    )


# =================================================================
# PAYMENT SUCCESS PAGE & INVOICE GENERATION
# =================================================================
@app.route('/payment-success')
def payment_success():

    payment_id = request.args.get('payment_id')
    order_id = request.args.get('order_id')

    if not payment_id:
        flash("Payment failed!", "danger")
        return redirect('/cart')

    user_id = session.get('user_id')
    user_info = {}
    cart_items = []
    total_amount = session.get('checkout_total', 0)

    if user_id:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get user details
        try:
            cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
            user_info = cursor.fetchone() or {}
        except mysql.connector.Error:
            try:
                cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
                user_info = cursor.fetchone() or {}
            except mysql.connector.Error:
                user_info = {}

        # Fetch cart items before removing from cart table
        selected_cart_ids = session.get('selected_cart_ids', [])
        if selected_cart_ids:
            placeholders = ", ".join(["%s"] * len(selected_cart_ids))
            cursor.execute(f"""
                SELECT cart.*, products.name, products.price, products.image
                FROM cart
                JOIN products ON cart.product_id = products.product_id
                WHERE cart.user_id=%s AND cart.cart_id IN ({placeholders})
            """, [user_id, *selected_cart_ids])
            cart_items = cursor.fetchall()

            # Remove paid items from cart table
            cursor.execute(f"DELETE FROM cart WHERE user_id=%s AND cart_id IN ({placeholders})", [user_id, *selected_cart_ids])
            conn.commit()
        else:
            cursor.execute("""
                SELECT cart.*, products.name, products.price, products.image
                FROM cart
                JOIN products ON cart.product_id = products.product_id
                WHERE cart.user_id=%s
            """, (user_id,))
            cart_items = cursor.fetchall()
            cursor.execute("DELETE FROM cart WHERE user_id=%s", (user_id,))
            conn.commit()

        cursor.close()
        conn.close()

    if not total_amount and cart_items:
        total_amount = sum(item['price'] * item['quantity'] for item in cart_items)

    invoice_date = datetime.now().strftime("%d %B %Y, %I:%M %p")

    # Format items for invoice
    invoice_items = []
    for item in cart_items:
        line_total = item['price'] * item['quantity']
        invoice_items.append({
            'name': item['name'],
            'price': item['price'],
            'quantity': item['quantity'],
            'total': line_total,
            'image': item['image']
        })

    invoice_data = {
        'invoice_no': f"INV-{(order_id or '1001')[-8:].upper()}",
        'payment_id': payment_id,
        'order_id': order_id or session.get('razorpay_order_id', 'N/A'),
        'date': invoice_date,
        'user_name': user_info.get('fullname') or user_info.get('name') or session.get('user_name', 'Customer'),
        'user_email': user_info.get('email') or session.get('user_email', ''),
        'user_phone': user_info.get('phone') or 'N/A',
        'address': session.get('checkout_address') or user_info.get('address') or 'N/A',
        'items': invoice_items,
        'total_amount': total_amount
    }

    session['last_invoice'] = invoice_data

    return render_template(
        "user/payment_success.html",
        payment_id=payment_id,
        order_id=order_id,
        invoice=invoice_data
    )


# =================================================================
# INVOICE VIEW ROUTES
# =================================================================
@app.route('/user/invoice')
@app.route('/user/invoice/<int:order_id>')
def user_invoice(order_id=None):
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    order = None
    if order_id:
        cursor.execute("SELECT * FROM orders WHERE order_id=%s AND user_id=%s", (order_id, user_id))
        order = cursor.fetchone()
    else:
        # Fallback to latest order if order_id is not specified
        cursor.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY order_id DESC LIMIT 1", (user_id,))
        order = cursor.fetchone()

    if not order and not session.get('last_invoice'):
        cursor.close()
        conn.close()
        flash("No order or invoice found.", "warning")
        return redirect('/user/my-orders')

    if order:
        cursor.execute("SELECT * FROM order_items WHERE order_id=%s", (order['order_id'],))
        items = cursor.fetchall()

        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        user_info = cursor.fetchone() or {}

        cursor.close()
        conn.close()

        invoice_date = order['created_at'].strftime("%d %B %Y, %I:%M %p") if isinstance(order['created_at'], datetime) else str(order['created_at'])

        invoice_data = {
            'invoice_no': f"INV-{order['order_id']:04d}",
            'payment_id': order.get('razorpay_payment_id', 'N/A'),
            'order_id': order.get('razorpay_order_id', 'N/A'),
            'date': invoice_date,
            'user_name': user_info.get('fullname') or user_info.get('name') or session.get('user_name', 'Customer'),
            'user_email': user_info.get('email') or session.get('user_email', ''),
            'user_phone': user_info.get('phone') or 'N/A',
            'address': order.get('shipping_address') or user_info.get('address') or session.get('checkout_address') or 'N/A',
            'items': [{'name': item['product_name'], 'price': item['price'], 'quantity': item['quantity'], 'total': item['price'] * item['quantity']} for item in items],
            'total_amount': order['amount']
        }
        return render_template("user/invoice.html", order=order, items=items, invoice=invoice_data)

    cursor.close()
    conn.close()
    invoice = session.get('last_invoice')
    return render_template("user/invoice.html", invoice=invoice)


# =================================================================
# DAY 13: Verify Razorpay Payment & Store Order + Order Items
# =================================================================
@app.route('/verify-payment', methods=['POST'])
def verify_payment():
    if 'user_id' not in session:
        flash("Please login to complete the payment.", "danger")
        return redirect('/user-login')

    razorpay_payment_id = request.form.get('razorpay_payment_id')
    razorpay_order_id = request.form.get('razorpay_order_id')
    razorpay_signature = request.form.get('razorpay_signature')

    if not (razorpay_payment_id and razorpay_order_id and razorpay_signature):
        flash("Payment verification failed (missing data).", "danger")
        return redirect('/cart')

    payload = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }

    try:
        razorpay_client.utility.verify_payment_signature(payload)
    except Exception as e:
        app.logger.error("Razorpay signature verification failed: %s", str(e))
        flash("Payment verification failed. Please contact support.", "danger")
        return redirect('/cart')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    selected_cart_ids = session.get('selected_cart_ids', [])
    if selected_cart_ids:
        placeholders = ", ".join(["%s"] * len(selected_cart_ids))
        cursor.execute(f"""
            SELECT cart.*, products.name, products.price, products.image
            FROM cart
            JOIN products ON cart.product_id = products.product_id
            WHERE cart.user_id=%s AND cart.cart_id IN ({placeholders})
        """, [user_id, *selected_cart_ids])
        cart_items = cursor.fetchall()
    else:
        cursor.execute("""
            SELECT cart.*, products.name, products.price, products.image
            FROM cart
            JOIN products ON cart.product_id = products.product_id
            WHERE cart.user_id=%s
        """, (user_id,))
        cart_items = cursor.fetchall()

    if not cart_items:
        session_cart = session.get('cart', {})
        if session_cart:
            cart_items = [
                {'product_id': int(pid), 'name': item['name'], 'price': item['price'], 'quantity': item['quantity'], 'image': item.get('image', '')}
                for pid, item in session_cart.items()
            ]

    if not cart_items:
        cursor.close()
        conn.close()
        flash("Cart is empty. Cannot create order.", "danger")
        return redirect('/products')

    total_amount = sum(item['price'] * item['quantity'] for item in cart_items)

    shipping_address = session.get('checkout_address', '')
    if not shipping_address:
        try:
            cursor.execute("SELECT address FROM users WHERE id=%s", (user_id,))
            u_row = cursor.fetchone()
            if u_row and u_row.get('address'):
                shipping_address = u_row['address']
        except Exception:
            pass

    try:
        cursor.execute("""
            INSERT INTO orders (user_id, razorpay_order_id, razorpay_payment_id, amount, payment_status, shipping_address)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, razorpay_order_id, razorpay_payment_id, total_amount, 'paid', shipping_address))

        order_db_id = cursor.lastrowid

        for item in cart_items:
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, product_name, quantity, price)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_db_id, item['product_id'], item['name'], item['quantity'], item['price']))

        if selected_cart_ids:
            placeholders = ", ".join(["%s"] * len(selected_cart_ids))
            cursor.execute(f"DELETE FROM cart WHERE user_id=%s AND cart_id IN ({placeholders})", [user_id, *selected_cart_ids])
        else:
            cursor.execute("DELETE FROM cart WHERE user_id=%s", (user_id,))

        conn.commit()

        session.pop('cart', None)
        session.pop('razorpay_order_id', None)
        session.pop('selected_cart_ids', None)

        flash("Payment successful and order placed!", "success")
        return redirect(f"/user/order-success/{order_db_id}")

    except Exception as e:
        conn.rollback()
        app.logger.error("Order storage failed: %s\n%s", str(e), traceback.format_exc())
        flash("There was an error saving your order. Contact support.", "danger")
        return redirect('/cart')
    finally:
        cursor.close()
        conn.close()


# =================================================================
# ROUTE: ORDER SUCCESS PAGE
# =================================================================
@app.route('/user/order-success/<int:order_db_id>')
def order_success(order_db_id):
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM orders WHERE order_id=%s AND user_id=%s", (order_db_id, user_id))
    order = cursor.fetchone()

    if not order:
        cursor.close()
        conn.close()
        flash("Order not found.", "danger")
        return redirect('/products')

    cursor.execute("SELECT * FROM order_items WHERE order_id=%s", (order_db_id,))
    items = cursor.fetchall()

    try:
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        user_info = cursor.fetchone() or {}
    except mysql.connector.Error:
        user_info = {}

    cursor.close()
    conn.close()

    invoice_date = order['created_at'].strftime("%d %B %Y, %I:%M %p") if isinstance(order['created_at'], datetime) else str(order['created_at'])

    invoice_data = {
        'invoice_no': f"INV-{order_db_id:04d}",
        'payment_id': order['razorpay_payment_id'],
        'order_id': order['razorpay_order_id'],
        'date': invoice_date,
        'user_name': user_info.get('fullname') or user_info.get('name') or session.get('user_name', 'Customer'),
        'user_email': user_info.get('email') or session.get('user_email', ''),
        'user_phone': user_info.get('phone') or 'N/A',
        'address': order.get('shipping_address') or user_info.get('address') or session.get('checkout_address') or 'N/A',
        'items': [{'name': item['product_name'], 'price': item['price'], 'quantity': item['quantity'], 'total': item['price'] * item['quantity']} for item in items],
        'total_amount': order['amount']
    }

    session['last_invoice'] = invoice_data

    return render_template("user/order_success.html", order=order, items=items, invoice=invoice_data)


# =================================================================
# ROUTE: MY ORDERS PAGE
# =================================================================
@app.route('/user/my-orders')
def my_orders():
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC", (session['user_id'],))
    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("user/my_orders.html", orders=orders)


# ----------------------------
# GENERATE & DOWNLOAD INVOICE PDF
# ----------------------------
@app.route("/user/download-invoice/<int:order_id>")
def download_invoice(order_id):
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM orders WHERE order_id=%s AND user_id=%s", (order_id, session['user_id']))
    order = cursor.fetchone()

    cursor.execute("SELECT * FROM order_items WHERE order_id=%s", (order_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT * FROM users WHERE id=%s", (session['user_id'],))
    user_info = cursor.fetchone() or {}

    cursor.close()
    conn.close()

    if not order:
        flash("Order not found.", "danger")
        return redirect('/user/my-orders')

    invoice_date = order['created_at'].strftime("%d %B %Y, %I:%M %p") if isinstance(order['created_at'], datetime) else str(order['created_at'])

    invoice_data = {
        'invoice_no': f"INV-{order_id:04d}",
        'payment_id': order.get('razorpay_payment_id', 'N/A'),
        'order_id': order.get('razorpay_order_id', 'N/A'),
        'date': invoice_date,
        'user_name': user_info.get('fullname') or user_info.get('name') or session.get('user_name', 'Customer'),
        'user_email': user_info.get('email') or session.get('user_email', ''),
        'user_phone': user_info.get('phone') or 'N/A',
        'address': order.get('shipping_address') or user_info.get('address') or session.get('checkout_address') or 'N/A',
        'items': [{'name': item['product_name'], 'price': item['price'], 'quantity': item['quantity'], 'total': item['price'] * item['quantity']} for item in items],
        'total_amount': order['amount']
    }

    html = render_template("user/invoice.html", order=order, items=items, invoice=invoice_data)

    pdf = generate_pdf(html)
    if not pdf:
        flash("Error generating PDF", "danger")
        return redirect('/user/my-orders')

    mode = request.args.get('mode', 'inline')
    if mode not in ['inline', 'attachment']:
        mode = 'inline'

    response = make_response(pdf.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f"{mode}; filename=invoice_{order_id}.pdf"

    return response



# =================================================================
# ROUTE: USER PROFILE PAGE
# =================================================================
@app.route('/profile', methods=['GET', 'POST'])
@app.route('/user/profile', methods=['GET', 'POST'])
def user_profile():
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        password = request.form.get('password', '').strip()

        if not fullname or not email:
            flash("Full name and email are required.", "warning")
            return redirect(url_for('user_profile'))

        if password:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute("""
                UPDATE users
                SET fullname=%s, email=%s, phone=%s, address=%s, password=%s
                WHERE id=%s
            """, (fullname, email, phone, address, hashed_password, user_id))
        else:
            cursor.execute("""
                UPDATE users
                SET fullname=%s, email=%s, phone=%s, address=%s
                WHERE id=%s
            """, (fullname, email, phone, address, user_id))

        conn.commit()
        session['user_name'] = fullname
        session['user_email'] = email
        flash("Profile updated successfully!", "success")
        return redirect(url_for('user_profile'))

    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        flash("User not found.", "danger")
        return redirect('/user-login')

    return render_template("user/profile.html", user=user)


# Alias routes for convenience
@app.route('/user/cart')
def user_cart_alias():
    return redirect(url_for('view_cart'))

@app.route('/user/products')
def user_products_alias():
    return redirect(url_for('user_products'))

@app.route('/orders')
def orders_alias():
    return redirect(url_for('my_orders'))






# --------------------------------
# General Routes
# --------------------------------
@app.route('/')
def home():
    return render_template("index.html")


# --------------------------------
# Admin Authentication
# --------------------------------
@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():
    if request.method == "GET":
        return render_template("admin/admin_signup.html")

    name = request.form['name']
    email = request.form['email']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT admin_id FROM admin WHERE email=%s", (email,))
    existing_admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if existing_admin:
        flash("This email is already registered. Please login instead.", "danger")
        return redirect('/admin-signup')

    session['signup_name'] = name
    session['signup_email'] = email

    otp = random.randint(100000, 999999)
    session['otp'] = otp

    message = Message(
        subject="SmartCart Admin OTP",
        sender=config.MAIL_USERNAME,
        recipients=[email]
    )
    message.body = f"Your OTP for SmartCart Admin Registration is: {otp}"
    mail.send(message)

    flash("OTP sent to your email!", "success")
    return redirect('/verify-otp')


@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'GET':
        return render_template("admin/verify_otp.html")

    user_otp = request.form['otp']
    password = request.form['password']

    if str(session.get('otp')) != str(user_otp):
        flash("Invalid OTP. Try again!", "danger")
        return redirect('/verify-otp')

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO admin (name, email, password) VALUES (%s, %s, %s)",
        (session.get('signup_name'), session.get('signup_email'), hashed_password)
    )
    conn.commit()
    cursor.close()
    conn.close()

    session.pop('otp', None)
    session.pop('signup_name', None)
    session.pop('signup_email', None)

    flash("Admin Registered Successfully! Please login.", "success")
    return redirect('/admin-login')


@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == "GET":
        return render_template("admin/admin_login.html")

    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM admin WHERE email=%s", (email,))
    admin = cursor.fetchone()
    cursor.close()
    conn.close()

    if admin and bcrypt.checkpw(password.encode('utf-8'), admin['password'].encode('utf-8')):
        session['admin_id'] = admin['admin_id']
        session['admin_name'] = admin['name']
        session['admin_email'] = admin['email']

        flash("Login Successful!", "success")
        return redirect('/admin-dashboard')

    flash("Invalid Email or Password!", "danger")
    return redirect('/admin-login')


@app.route('/admin-logout')
def admin_logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect('/admin-login')


# --------------------------------
# Admin Dashboard & Product Actions
# --------------------------------
@app.route('/admin-dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        flash("Please login first!", "warning")
        return redirect('/admin-login')

    return render_template("admin/dashboard.html", admin_name=session['admin_name'])


@app.route('/admin/add-item', methods=['GET', 'POST'])
def add_item():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    if request.method == 'GET':
        last_added = session.pop('last_added_product', None)
        return render_template("admin/add_item.html", last_added=last_added)

    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    price = request.form['price']
    image_file = request.files.get('image')

    if not image_file or image_file.filename == "":
        flash("Please upload a product image!", "danger")
        return redirect('/admin/add-item')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    filename = secure_filename(image_file.filename)
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_file.save(image_path)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO products (name, description, category, price, image)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (name, description, category, price, filename)
    )
    conn.commit()
    cursor.close()
    conn.close()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return {
            "success": True,
            "message": f"Product '{name}' added successfully!",
            "product": {
                "name": name,
                "description": description,
                "category": category,
                "price": price,
                "image": filename,
                "image_url": url_for("static", filename="uploads/product_images/" + filename)
            }
        }

    flash(f"Product '{name}' added successfully!", "success")
    return redirect('/admin/add-item')


@app.route('/admin/view-products')
def view_products():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '')
    category = request.args.get('category', '')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT DISTINCT category FROM products")
    categories = cursor.fetchall()

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append(f"%{search}%")

    if category:
        query += " AND category = %s"
        params.append(category)

    cursor.execute(query, params)
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/view_products.html",
        products=products,
        categories=categories
    )


@app.route("/admin/edit-product/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    if "admin_id" not in session:
        flash("Please login first.", "danger")
        return redirect("/admin-login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["name"]
        description = request.form["description"]
        category = request.form["category"]
        price = request.form["price"]
        image_file = request.files.get("image")

        # Check if user updated the image
        if image_file and image_file.filename != "":
            filename = secure_filename(image_file.filename)
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            image_file.save(image_path)

            cursor.execute("""
                UPDATE products
                SET name=%s, description=%s, category=%s, price=%s, image=%s
                WHERE product_id=%s
            """, (name, description, category, price, filename, product_id))
        else:
            cursor.execute("""
                UPDATE products
                SET name=%s, description=%s, category=%s, price=%s
                WHERE product_id=%s
            """, (name, description, category, price, product_id))

        conn.commit()
        cursor.close()
        conn.close()

        flash("Product updated successfully!", "success")
        return redirect("/admin/view-products")

    cursor.execute("SELECT * FROM products WHERE product_id=%s", (product_id,))
    product = cursor.fetchone()
    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect("/admin/view-products")

    return render_template("admin/edit_product.html", product=product)


@app.route("/admin/delete-product/<int:product_id>")
def delete_product(product_id):
    if "admin_id" not in session:
        flash("Please login first!", "danger")
        return redirect("/admin-login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT image FROM products WHERE product_id=%s", (product_id,))
    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        flash("Product not found!", "danger")
        return redirect("/admin/view-products")

    # Remove image from filesystem if it exists
    if product.get("image"):
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], product["image"])
        if os.path.exists(image_path):
            os.remove(image_path)

    cursor.execute("DELETE FROM products WHERE product_id=%s", (product_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Product deleted successfully!", "success")
    return redirect("/admin/view-products")

@app.route("/admin/profile")
def admin_profile():

    if "admin_id" not in session:
        flash("Please login first!", "danger")
        return redirect("/admin-login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM admin WHERE admin_id=%s",
        (session["admin_id"],)
    )

    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "admin/admin_profile.html",
        admin=admin
    )



@app.route("/admin/profile", methods=["POST"])
def update_admin_profile():

    if "admin_id" not in session:
        flash("Please login first!", "danger")
        return redirect("/admin-login")

    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]
    profile_image = request.files.get("profile_image")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM admin WHERE admin_id=%s",
        (session["admin_id"],)
    )
    admin = cursor.fetchone()

    image_name = admin["profile_image"]

    # Upload new image
    if profile_image and profile_image.filename != "":
        os.makedirs(app.config["ADMIN_UPLOAD_FOLDER"], exist_ok=True)

        filename = secure_filename(profile_image.filename)
        image_path = os.path.join(
            app.config["ADMIN_UPLOAD_FOLDER"],
            filename
        )

        profile_image.save(image_path)

        # Delete old image
        if image_name:
            old_path = os.path.join(
                app.config["ADMIN_UPLOAD_FOLDER"],
                image_name
            )

            if os.path.exists(old_path):
                os.remove(old_path)

        image_name = filename

    # Update password only if entered
    if password:
        hashed_password = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

    else:
        hashed_password = admin["password"]

    cursor.execute("""
        UPDATE admin
        SET
            name=%s,
            email=%s,
            password=%s,
            profile_image=%s
        WHERE admin_id=%s
    """, (
        name,
        email,
        hashed_password,
        image_name,
        session["admin_id"]
    ))

    conn.commit()

    cursor.close()
    conn.close()

    session["admin_name"] = name
    session["admin_email"] = email

    flash("Profile updated successfully!", "success")

    return redirect("/admin/profile")

# --------------------------------
# User Logout
# --------------------------------
@app.route("/user-logout")
def user_logout():

    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)

    flash("Logged out successfully!", "success")

    return redirect("/user-login")

# --------------------------------
# Application Entry Point
# --------------------------------
if __name__ == '__main__':
    app.run(debug=True)
