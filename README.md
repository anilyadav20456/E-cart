# SmartCart Flask E-Commerce Application

An e-commerce web application built with Python Flask, MySQL / SQLite, Razorpay Payment Gateway, and Gmail SMTP integration.

## Features
- User Registration, Login & Profile Management
- Product Browsing, Search, Cart & Checkout
- Razorpay Payment Gateway Integration
- PDF Invoice Generation (`xhtml2pdf`)
- Email Notifications & Password Resets (`Flask-Mail`)
- Environment Variable Configuration via `.env`

---

## Local Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/anilyadav20456/E-cart.git
   cd E-cart
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Environment Variables:**
   Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

5. **Run the Flask application:**
   ```bash
   python app.py
   ```
   Open `http://127.0.0.1:5000` in your browser.

---

## PythonAnywhere Deployment Guide

Follow these steps to deploy this app on **PythonAnywhere**:

### Step 1: Open Bash Console on PythonAnywhere
Log in to your [PythonAnywhere Account](https://www.pythonanywhere.com) and open a **Bash Console**.

### Step 2: Clone Repository
Run the following command in Bash:
```bash
git clone https://github.com/anilyadav20456/E-cart.git
cd E-cart
```

### Step 3: Create Virtual Environment & Install Dependencies
```bash
python3 -m venv myenv
source myenv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Create `.env` Credentials File
Create the `.env` file on PythonAnywhere using `nano`:
```bash
nano .env
```
Paste your configuration values (Secret Key, Mail settings, Razorpay keys, DB settings) and save (`Ctrl+O`, `Enter`, `Ctrl+X`).

### Step 5: Configure Web App on PythonAnywhere
1. Go to the **Web** tab in PythonAnywhere dashboard.
2. Click **Add a new web app**.
3. Choose **Manual configuration** (or Flask) and select Python **3.10+**.
4. Set **Source code path**:
   `/home/YOUR_USERNAME/E-cart`
5. Set **Virtualenv path**:
   `/home/YOUR_USERNAME/E-cart/myenv`

### Step 6: Configure WSGI File
In the **Web** tab, click on the **WSGI configuration file** link (e.g., `/var/www/YOUR_USERNAME_pythonanywhere_com_wsgi.py`). Replace its content with:

```python
import sys
import os

project_home = '/home/YOUR_USERNAME/E-cart'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(project_home, '.env'))

from app import app as application
```
*(Replace `YOUR_USERNAME` with your actual PythonAnywhere username)*.

### Step 7: Reload & Test
Click the green **Reload** button at the top of the Web tab. Visit your site at `https://YOUR_USERNAME.pythonanywhere.com`.
