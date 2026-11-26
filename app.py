import sqlite3
from flask import Flask, g, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = "change-this-secret-key"   # needed for session (cart) and flash messages
DATABASE = "shop.db"

SAMPLE_PRODUCTS = [
    ("Wireless Mouse", 599, "Electronics", "🖱️", "Comfortable 2.4GHz wireless mouse."),
    ("Bluetooth Headphones", 1999, "Electronics", "🎧", "Over-ear headphones with deep bass."),
    ("Smart Watch", 3499, "Electronics", "⌚", "Track steps, heart rate and notifications."),
    ("Cotton T-Shirt", 499, "Fashion", "👕", "Soft 100% cotton, regular fit."),
    ("Running Shoes", 2499, "Fashion", "👟", "Lightweight shoes for daily running."),
    ("Backpack", 1299, "Fashion", "🎒", "Water-resistant, fits a 15-inch laptop."),
    ("Python Crash Course", 699, "Books", "📘", "Beginner-friendly Python book."),
    ("Notebook Set (3)", 249, "Books", "📓", "Ruled notebooks, 200 pages each."),
    ("Coffee Mug", 199, "Home", "☕", "Ceramic mug, 350 ml."),
    ("Desk Lamp", 899, "Home", "💡", "LED lamp with adjustable brightness."),
]


# ---------- Database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            emoji TEXT,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            email TEXT NOT NULL,
            address TEXT NOT NULL,
            total REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        """
    )
    if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO products (name, price, category, emoji, description) VALUES (?,?,?,?,?)",
            SAMPLE_PRODUCTS,
        )
    db.commit()
    db.close()


# ---------- Cart helpers ----------
def get_cart_items():
    """Return (list of cart rows, total) from the session cart."""
    cart = session.get("cart", {})
    items, total = [], 0
    if cart:
        db = get_db()
        for pid, qty in cart.items():
            p = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
            if p:
                subtotal = p["price"] * qty
                total += subtotal
                items.append({"product": p, "qty": qty, "subtotal": subtotal})
    return items, total


@app.context_processor
def inject_cart_count():
    return {"cart_count": sum(session.get("cart", {}).values())}


# ---------- Routes ----------
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    sql, params = "SELECT * FROM products WHERE 1=1", []
    if q:
        sql += " AND name LIKE ?"
        params.append(f"%{q}%")
    if category:
        sql += " AND category = ?"
        params.append(category)
    db = get_db()
    products = db.execute(sql, params).fetchall()
    categories = [r["category"] for r in db.execute("SELECT DISTINCT category FROM products")]
    return render_template("index.html", products=products, categories=categories,
                           q=q, selected=category)


@app.route("/product/<int:pid>")
def product_detail(pid):
    p = get_db().execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if not p:
        return redirect(url_for("index"))
    return render_template("product.html", p=p)


@app.route("/add/<int:pid>", methods=["POST"])
def add_to_cart(pid):
    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    flash("Added to cart.")
    return redirect(request.referrer or url_for("index"))


@app.route("/cart")
def cart():
    items, total = get_cart_items()
    return render_template("cart.html", items=items, total=total)


@app.route("/update/<int:pid>", methods=["POST"])
def update_cart(pid):
    cart = session.get("cart", {})
    try:
        qty = int(request.form.get("qty", 1))
    except ValueError:
        qty = 1
    if qty <= 0:
        cart.pop(str(pid), None)
    else:
        cart[str(pid)] = qty
    session["cart"] = cart
    return redirect(url_for("cart"))


@app.route("/remove/<int:pid>", methods=["POST"])
def remove_from_cart(pid):
    cart = session.get("cart", {})
    cart.pop(str(pid), None)
    session["cart"] = cart
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, total = get_cart_items()
    if not items:
        flash("Your cart is empty.")
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        if not (name and email and address):
            flash("Please fill in all fields.")
            return render_template("checkout.html", items=items, total=total)

        db = get_db()
        cur = db.execute(
            "INSERT INTO orders (customer_name, email, address, total) VALUES (?,?,?,?)",
            (name, email, address, total),
        )
        order_id = cur.lastrowid
        for it in items:
            db.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?,?,?,?)",
                (order_id, it["product"]["id"], it["qty"], it["product"]["price"]),
            )
        db.commit()
        session.pop("cart", None)
        return redirect(url_for("success", order_id=order_id))

    return render_template("checkout.html", items=items, total=total)


@app.route("/success/<int:order_id>")
def success(order_id):
    return render_template("success.html", order_id=order_id)


@app.route("/orders")
def orders():
    rows = get_db().execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return render_template("orders.html", orders=rows)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
