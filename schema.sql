-- =========================================================
-- SmartCart SQLite Database Schema & Sample Data Setup
-- Database File: smartcart.db
-- =========================================================

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fullname TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    password TEXT NOT NULL,
    profile_pic TEXT
);

-- 2. Admin Table
CREATE TABLE IF NOT EXISTS admin (
    admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    profile_pic TEXT
);

-- 3. Products Table
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    price REAL NOT NULL,
    image TEXT
);

-- 4. Cart Table
CREATE TABLE IF NOT EXISTS cart (
    cart_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (product_id) REFERENCES products (product_id)
);

-- 5. Orders Table
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    razorpay_order_id TEXT,
    razorpay_payment_id TEXT,
    amount REAL NOT NULL,
    payment_status TEXT DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

-- 6. Order Items Table
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders (order_id)
);

-- =========================================================
-- SAMPLE SEED DATA
-- =========================================================

-- Default Admin Account (Email: admin@gmail.com | Password: admin123)
INSERT OR IGNORE INTO admin (admin_id, name, email, password)
VALUES (1, 'Admin', 'admin@gmail.com', '$2b$12$q7n9vS9mE1Z0d0xY8h5kI.tT6/0Rz5E9g9Q8u7k6j5h4g3f2e1d0c');

-- Initial Products
INSERT OR IGNORE INTO products (product_id, name, description, category, price, image) VALUES
(1, 'Apple Watch Series 9 GPS', 'Smartwatch with advanced fitness tracking and Retina display.', 'Electronics', 41900.00, 'watch.png'),
(2, 'Samsung Galaxy S24 Ultra', 'Flagship smartphone with Snapdragon 8 Gen 3 and 200MP camera.', 'Electronics', 129999.00, 'samsung.png'),
(3, 'Wireless ANC Headphones', 'High quality noise cancelling over-ear headphones with 40h battery life.', 'Electronics', 4999.00, 'headphones.png'),
(4, 'Premium Cotton T-Shirt', '100% combed cotton breathable t-shirt for daily comfort.', 'Fashion', 999.00, 'tshirt.png'),
(5, 'Fresh Organic Apples (1kg)', 'Farm fresh crispy red apples rich in fiber and vitamins.', 'Grocery', 240.00, 'apples.png');
