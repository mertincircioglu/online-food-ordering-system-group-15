import os
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg2 import errors as pg_errors
from starlette.middleware.sessions import SessionMiddleware

from auth import flash, get_current_user, hash_password, pop_flashes, verify_password
from db import execute_query, fetch_all, fetch_one, get_db

app = FastAPI(title="BiteFlow - Online Food Ordering System (Group 15)")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "biteflow-cmpe341-group15-secret-key-2026"),
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def render(request: Request, template_name: str, context: dict = None, status_code: int = 200):
    ctx = {
        "request": request,
        "user": get_current_user(request),
        "flashes": pop_flashes(request),
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, template_name, ctx, status_code=status_code)


def require_login(request: Request):
    user = get_current_user(request)
    if not user:
        flash(request, "Please sign in to continue.", "warning")
        return None, RedirectResponse("/login", status_code=303)
    return user, None


def require_admin(request: Request):
    user = get_current_user(request)
    if not user:
        flash(request, "Please sign in with an admin account.", "warning")
        return None, RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        return None, render(request, "forbidden.html", status_code=403)
    return user, None


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    row = fetch_one("SELECT 1 AS ok")
    return JSONResponse({"status": "ok", "db": bool(row)})


# ---------------------------------------------------------------------------
# Authentication (Login, Register, Logout)
# ---------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html")


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = fetch_one(
        "SELECT user_id, username, password_hash, role, full_name FROM users WHERE username = %s",
        (username.strip(),),
    )
    if not user or not verify_password(password, user["password_hash"]):
        flash(request, "Invalid username or password.", "error")
        return RedirectResponse("/login", status_code=303)

    request.session["user_id"] = user["user_id"]
    flash(request, f"Welcome back, {user['full_name']}!", "success")
    if user["role"] == "admin":
        return RedirectResponse("/admin", status_code=303)
    return RedirectResponse("/", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/", status_code=303)
    return render(request, "register.html")


@app.post("/register")
def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
):
    username = username.strip()
    email = email.strip().lower()
    if len(password) < 6:
        flash(request, "Password must be at least 6 characters long.", "error")
        return RedirectResponse("/register", status_code=303)

    pw_hash = hash_password(password)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, email, password_hash, role, full_name, phone, address)
                    VALUES (%s, %s, %s, 'customer', %s, %s, %s)
                    RETURNING user_id
                    """,
                    (username, email, pw_hash, full_name.strip(), phone.strip(), address.strip()),
                )
                new_user = cur.fetchone()
    except pg_errors.UniqueViolation:
        flash(request, "Username or email is already registered.", "error")
        return RedirectResponse("/register", status_code=303)

    request.session["user_id"] = new_user["user_id"]
    flash(request, "Account created! You can now browse menus and place orders.", "success")
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    flash(request, "You have been signed out.", "info")
    return RedirectResponse("/login", status_code=303)


# ---------------------------------------------------------------------------
# Storefront & Restaurant Details
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    q: Optional[str] = None,
    cuisine: Optional[str] = None,
):
    cuisines = fetch_all(
        "SELECT DISTINCT cuisine_type FROM restaurants WHERE is_active = TRUE ORDER BY cuisine_type"
    )
    query = """
        SELECT
            r.restaurant_id,
            r.name,
            r.cuisine_type,
            r.address,
            r.phone,
            r.delivery_time_min,
            r.min_order_amount,
            COALESCE(ROUND(AVG(rev.rating), 1), 0.0) AS avg_rating,
            COUNT(DISTINCT rev.review_id)            AS review_count,
            COUNT(DISTINCT m.item_id)                AS item_count
        FROM restaurants r
        LEFT JOIN reviews rev  ON r.restaurant_id = rev.restaurant_id
        LEFT JOIN menu_items m ON r.restaurant_id = m.restaurant_id AND m.is_available = TRUE
        WHERE r.is_active = TRUE
    """
    params = []
    if cuisine:
        query += " AND r.cuisine_type = %s"
        params.append(cuisine)
    if q:
        query += " AND (LOWER(r.name) LIKE %s OR LOWER(r.cuisine_type) LIKE %s)"
        like = f"%{q.strip().lower()}%"
        params.extend([like, like])

    query += """
        GROUP BY r.restaurant_id
        ORDER BY avg_rating DESC, r.name ASC
    """
    restaurants = fetch_all(query, params)
    stats = fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM restaurants WHERE is_active = TRUE) AS restaurant_count,
            (SELECT COUNT(*) FROM menu_items WHERE is_available = TRUE) AS dish_count,
            (SELECT COUNT(*) FROM orders) AS order_count
        """
    )
    return render(
        request,
        "home.html",
        {
            "restaurants": restaurants,
            "cuisines": [c["cuisine_type"] for c in cuisines],
            "selected_cuisine": cuisine or "",
            "search_query": q or "",
            "stats": stats,
        },
    )


@app.get("/restaurants/{restaurant_id}", response_class=HTMLResponse)
def restaurant_detail(request: Request, restaurant_id: int):
    restaurant = fetch_one(
        """
        SELECT
            r.*,
            COALESCE(ROUND(AVG(rev.rating), 1), 0.0) AS avg_rating,
            COUNT(rev.review_id)                     AS review_count
        FROM restaurants r
        LEFT JOIN reviews rev ON r.restaurant_id = rev.restaurant_id
        WHERE r.restaurant_id = %s
        GROUP BY r.restaurant_id
        """,
        (restaurant_id,),
    )
    if not restaurant:
        flash(request, "Restaurant not found.", "error")
        return RedirectResponse("/", status_code=303)

    menu_items = fetch_all(
        """
        SELECT m.*, c.name AS category_name
        FROM menu_items m
        INNER JOIN categories c ON m.category_id = c.category_id
        WHERE m.restaurant_id = %s
        ORDER BY c.name, m.name
        """,
        (restaurant_id,),
    )
    reviews = fetch_all(
        """
        SELECT rev.*, u.username, u.full_name
        FROM reviews rev
        INNER JOIN users u ON rev.user_id = u.user_id
        WHERE rev.restaurant_id = %s
        ORDER BY rev.created_at DESC
        """,
        (restaurant_id,),
    )
    return render(
        request,
        "restaurant.html",
        {
            "restaurant": restaurant,
            "menu_items": menu_items,
            "reviews": reviews,
        },
    )


# ---------------------------------------------------------------------------
# Customer Ordering (INSERT) & Order Management (UPDATE / DELETE)
# ---------------------------------------------------------------------------
@app.post("/restaurants/{restaurant_id}/order")
async def place_order(request: Request, restaurant_id: int):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    form = await request.form()
    delivery_address = str(form.get("delivery_address", "")).strip() or user["address"]
    payment_method = str(form.get("payment_method", "Credit Card")).strip()
    notes = str(form.get("notes", "")).strip()

    if payment_method not in ("Credit Card", "Cash on Delivery", "Online Wallet"):
        payment_method = "Credit Card"

    selected_items = []
    for key, val in form.items():
        if key.startswith("qty_"):
            try:
                item_id = int(key.replace("qty_", ""))
                qty = int(val)
                if qty > 0:
                    selected_items.append((item_id, qty))
            except ValueError:
                continue

    if not selected_items:
        flash(request, "Please select at least one item before placing an order.", "warning")
        return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)

    restaurant = fetch_one(
        "SELECT * FROM restaurants WHERE restaurant_id = %s AND is_active = TRUE",
        (restaurant_id,),
    )
    if not restaurant:
        flash(request, "This restaurant is currently unavailable.", "error")
        return RedirectResponse("/", status_code=303)

    item_ids = [i[0] for i in selected_items]
    db_items = fetch_all(
        """
        SELECT item_id, name, price
        FROM menu_items
        WHERE restaurant_id = %s AND is_available = TRUE AND item_id = ANY(%s)
        """,
        (restaurant_id, item_ids),
    )
    price_map = {row["item_id"]: row["price"] for row in db_items}

    line_items = []
    total_amount = Decimal("0.00")
    for item_id, qty in selected_items:
        if item_id in price_map:
            unit_price = price_map[item_id]
            total_amount += unit_price * qty
            line_items.append((item_id, qty, unit_price))

    if not line_items:
        flash(request, "Selected menu items are unavailable.", "error")
        return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)

    if total_amount < restaurant["min_order_amount"]:
        flash(
            request,
            f"Minimum order amount for {restaurant['name']} is {restaurant['min_order_amount']:.2f} TL.",
            "warning",
        )
        return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)

    payment_status = "Pending" if payment_method == "Cash on Delivery" else "Completed"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (user_id, restaurant_id, status, total_amount, delivery_address, notes)
                VALUES (%s, %s, 'Pending', %s, %s, %s)
                RETURNING order_id
                """,
                (user["user_id"], restaurant_id, total_amount, delivery_address, notes or None),
            )
            order_id = cur.fetchone()["order_id"]

            for item_id, qty, unit_price in line_items:
                cur.execute(
                    """
                    INSERT INTO order_items (order_id, item_id, quantity, unit_price)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (order_id, item_id, qty, unit_price),
                )

            cur.execute(
                """
                INSERT INTO payments (order_id, payment_method, payment_status, amount, paid_at)
                VALUES (%s, %s, %s, %s, CASE WHEN %s = 'Completed' THEN NOW() ELSE NULL END)
                """,
                (order_id, payment_method, payment_status, total_amount, payment_status),
            )

    flash(request, f"Order #{order_id} placed successfully ({total_amount:.2f} TL)!", "success")
    return RedirectResponse("/my-orders", status_code=303)


@app.get("/my-orders", response_class=HTMLResponse)
def my_orders(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    orders = fetch_all(
        """
        SELECT
            o.*,
            r.name AS restaurant_name,
            r.cuisine_type,
            p.payment_method,
            p.payment_status,
            STRING_AGG(m.name || ' × ' || oi.quantity, ', ' ORDER BY m.name) AS items_summary
        FROM orders o
        INNER JOIN restaurants r  ON o.restaurant_id = r.restaurant_id
        LEFT  JOIN payments p     ON o.order_id      = p.order_id
        LEFT  JOIN order_items oi ON o.order_id      = oi.order_id
        LEFT  JOIN menu_items m   ON oi.item_id      = m.item_id
        WHERE o.user_id = %s
        GROUP BY o.order_id, r.name, r.cuisine_type, p.payment_method, p.payment_status
        ORDER BY o.order_date DESC
        """,
        (user["user_id"],),
    )
    return render(request, "my_orders.html", {"orders": orders})


@app.post("/my-orders/{order_id}/update")
def update_my_order(
    request: Request,
    order_id: int,
    delivery_address: str = Form(...),
    notes: str = Form(""),
):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    updated = execute_query(
        """
        UPDATE orders
        SET delivery_address = %s, notes = %s
        WHERE order_id = %s AND user_id = %s AND status = 'Pending'
        """,
        (delivery_address.strip(), notes.strip() or None, order_id, user["user_id"]),
    )
    if updated:
        flash(request, f"Order #{order_id} delivery details updated.", "success")
    else:
        flash(request, "Only your own Pending orders can be modified.", "warning")
    return RedirectResponse("/my-orders", status_code=303)


@app.post("/my-orders/{order_id}/delete")
def delete_my_order(request: Request, order_id: int):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    deleted = execute_query(
        "DELETE FROM orders WHERE order_id = %s AND user_id = %s AND status = 'Pending'",
        (order_id, user["user_id"]),
    )
    if deleted:
        flash(request, f"Pending order #{order_id} has been cancelled and removed.", "info")
    else:
        flash(request, "Only your own Pending orders can be cancelled.", "warning")
    return RedirectResponse("/my-orders", status_code=303)


# ---------------------------------------------------------------------------
# Customer Reviews (INSERT / UPDATE / DELETE)
# ---------------------------------------------------------------------------
@app.post("/restaurants/{restaurant_id}/reviews")
def add_review(
    request: Request,
    restaurant_id: int,
    rating: int = Form(...),
    comment: str = Form(...),
):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    if rating < 1 or rating > 5 or not comment.strip():
        flash(request, "Please provide a rating (1–5) and a review comment.", "error")
        return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)

    execute_query(
        """
        INSERT INTO reviews (user_id, restaurant_id, rating, comment)
        VALUES (%s, %s, %s, %s)
        """,
        (user["user_id"], restaurant_id, rating, comment.strip()),
    )
    flash(request, "Thank you! Your review has been published.", "success")
    return RedirectResponse(f"/restaurants/{restaurant_id}#reviews", status_code=303)


@app.post("/reviews/{review_id}/update")
def update_review(
    request: Request,
    review_id: int,
    restaurant_id: int = Form(...),
    rating: int = Form(...),
    comment: str = Form(...),
):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    if user["role"] == "admin":
        updated = execute_query(
            "UPDATE reviews SET rating = %s, comment = %s WHERE review_id = %s",
            (rating, comment.strip(), review_id),
        )
    else:
        updated = execute_query(
            "UPDATE reviews SET rating = %s, comment = %s WHERE review_id = %s AND user_id = %s",
            (rating, comment.strip(), review_id, user["user_id"]),
        )

    if updated:
        flash(request, "Review updated.", "success")
    else:
        flash(request, "You do not have permission to edit this review.", "error")
    return RedirectResponse(f"/restaurants/{restaurant_id}#reviews", status_code=303)


@app.post("/reviews/{review_id}/delete")
def delete_review(
    request: Request,
    review_id: int,
    restaurant_id: int = Form(...),
):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    if user["role"] == "admin":
        deleted = execute_query("DELETE FROM reviews WHERE review_id = %s", (review_id,))
    else:
        deleted = execute_query(
            "DELETE FROM reviews WHERE review_id = %s AND user_id = %s",
            (review_id, user["user_id"]),
        )

    if deleted:
        flash(request, "Review deleted.", "info")
    else:
        flash(request, "You do not have permission to delete this review.", "error")
    return RedirectResponse(f"/restaurants/{restaurant_id}#reviews", status_code=303)


# ---------------------------------------------------------------------------
# User Profile (UPDATE)
# ---------------------------------------------------------------------------
@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return redirect
    return render(request, "profile.html")


@app.post("/profile")
def profile_update(
    request: Request,
    full_name: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    execute_query(
        "UPDATE users SET full_name = %s, phone = %s, address = %s WHERE user_id = %s",
        (full_name.strip(), phone.strip(), address.strip(), user["user_id"]),
    )
    flash(request, "Your profile has been updated.", "success")
    return RedirectResponse("/profile", status_code=303)


# ---------------------------------------------------------------------------
# ADMIN PANEL (Strict Role-Based Access Control: role == 'admin')
# ---------------------------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked

    kpis = fetch_one(
        """
        SELECT
            (SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status <> 'Cancelled') AS total_revenue,
            (SELECT COUNT(*) FROM orders) AS total_orders,
            (SELECT COUNT(*) FROM restaurants WHERE is_active = TRUE) AS active_restaurants,
            (SELECT COUNT(*) FROM users) AS total_users
        """
    )

    # Complex Query 1: Multi-table JOIN
    q1_join = fetch_all(
        """
        SELECT
            o.order_id,
            u.full_name AS customer_name,
            r.name      AS restaurant_name,
            STRING_AGG(m.name || ' (x' || oi.quantity || ')', ', ' ORDER BY m.name) AS ordered_items,
            o.status    AS order_status,
            p.payment_method,
            p.payment_status,
            o.total_amount
        FROM orders o
        INNER JOIN users u        ON o.user_id       = u.user_id
        INNER JOIN restaurants r  ON o.restaurant_id = r.restaurant_id
        INNER JOIN order_items oi ON o.order_id      = oi.order_id
        INNER JOIN menu_items m   ON oi.item_id      = m.item_id
        LEFT  JOIN payments p     ON o.order_id      = p.order_id
        GROUP BY o.order_id, u.full_name, r.name, o.status, p.payment_method, p.payment_status, o.total_amount
        ORDER BY o.order_date DESC
        """
    )

    # Complex Query 2: GROUP BY + ORDER BY
    q2_groupby = fetch_all(
        """
        SELECT
            r.restaurant_id,
            r.name                                        AS restaurant_name,
            r.cuisine_type,
            COUNT(o.order_id)                             AS total_orders,
            COALESCE(SUM(o.total_amount), 0.00)           AS total_revenue,
            COALESCE(ROUND(AVG(o.total_amount), 2), 0.00) AS avg_order_value,
            COALESCE(rev_stats.avg_rating, 0.00)          AS avg_rating
        FROM restaurants r
        LEFT JOIN orders o
               ON r.restaurant_id = o.restaurant_id AND o.status <> 'Cancelled'
        LEFT JOIN (
            SELECT restaurant_id, ROUND(AVG(rating), 2) AS avg_rating
            FROM reviews
            GROUP BY restaurant_id
        ) rev_stats
               ON r.restaurant_id = rev_stats.restaurant_id
        GROUP BY r.restaurant_id, r.name, r.cuisine_type, rev_stats.avg_rating
        ORDER BY total_revenue DESC, avg_rating DESC
        """
    )

    # Complex Query 3: Subquery
    q3_subquery = fetch_all(
        """
        SELECT
            u.user_id,
            u.username,
            u.full_name,
            COUNT(o.order_id)   AS order_count,
            SUM(o.total_amount) AS total_spent,
            ROUND((
                SELECT AVG(customer_total)
                FROM (
                    SELECT SUM(total_amount) AS customer_total
                    FROM orders
                    WHERE status <> 'Cancelled'
                    GROUP BY user_id
                ) AS sub_avg
            ), 2)               AS avg_customer_spending
        FROM users u
        INNER JOIN orders o ON u.user_id = o.user_id
        WHERE o.status <> 'Cancelled'
        GROUP BY u.user_id, u.username, u.full_name
        HAVING SUM(o.total_amount) > (
            SELECT AVG(customer_total)
            FROM (
                SELECT SUM(total_amount) AS customer_total
                FROM orders
                WHERE status <> 'Cancelled'
                GROUP BY user_id
            ) AS avg_calc
        )
        ORDER BY total_spent DESC
        """
    )

    return render(
        request,
        "admin/dashboard.html",
        {
            "active_nav": "dashboard",
            "kpis": kpis,
            "q1_join": q1_join,
            "q2_groupby": q2_groupby,
            "q3_subquery": q3_subquery,
        },
    )


# --- Admin: Restaurants CRUD ---
@app.get("/admin/restaurants", response_class=HTMLResponse)
def admin_restaurants(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    restaurants = fetch_all("SELECT * FROM restaurants ORDER BY restaurant_id DESC")
    return render(
        request,
        "admin/restaurants.html",
        {"active_nav": "restaurants", "restaurants": restaurants},
    )


@app.post("/admin/restaurants/create")
def admin_restaurant_create(
    request: Request,
    name: str = Form(...),
    cuisine_type: str = Form(...),
    address: str = Form(...),
    phone: str = Form(...),
    delivery_time_min: int = Form(...),
    min_order_amount: Decimal = Form(...),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query(
        """
        INSERT INTO restaurants (name, cuisine_type, address, phone, delivery_time_min, min_order_amount, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        """,
        (name.strip(), cuisine_type.strip(), address.strip(), phone.strip(), delivery_time_min, min_order_amount),
    )
    flash(request, f"Restaurant '{name.strip()}' added.", "success")
    return RedirectResponse("/admin/restaurants", status_code=303)


@app.post("/admin/restaurants/{restaurant_id}/update")
def admin_restaurant_update(
    request: Request,
    restaurant_id: int,
    name: str = Form(...),
    cuisine_type: str = Form(...),
    address: str = Form(...),
    phone: str = Form(...),
    delivery_time_min: int = Form(...),
    min_order_amount: Decimal = Form(...),
    is_active: Optional[str] = Form(None),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query(
        """
        UPDATE restaurants
        SET name = %s, cuisine_type = %s, address = %s, phone = %s,
            delivery_time_min = %s, min_order_amount = %s, is_active = %s
        WHERE restaurant_id = %s
        """,
        (
            name.strip(),
            cuisine_type.strip(),
            address.strip(),
            phone.strip(),
            delivery_time_min,
            min_order_amount,
            bool(is_active),
            restaurant_id,
        ),
    )
    flash(request, f"Restaurant #{restaurant_id} updated.", "success")
    return RedirectResponse("/admin/restaurants", status_code=303)


@app.post("/admin/restaurants/{restaurant_id}/delete")
def admin_restaurant_delete(request: Request, restaurant_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query("DELETE FROM restaurants WHERE restaurant_id = %s", (restaurant_id,))
    flash(request, f"Restaurant #{restaurant_id} deleted.", "info")
    return RedirectResponse("/admin/restaurants", status_code=303)


# --- Admin: Categories CRUD ---
@app.get("/admin/categories", response_class=HTMLResponse)
def admin_categories(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    categories = fetch_all(
        """
        SELECT c.*, COUNT(m.item_id) AS item_count
        FROM categories c
        LEFT JOIN menu_items m ON c.category_id = m.category_id
        GROUP BY c.category_id
        ORDER BY c.category_id ASC
        """
    )
    return render(
        request,
        "admin/categories.html",
        {"active_nav": "categories", "categories": categories},
    )


@app.post("/admin/categories/create")
def admin_category_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        execute_query(
            "INSERT INTO categories (name, description) VALUES (%s, %s)",
            (name.strip(), description.strip() or None),
        )
        flash(request, f"Category '{name.strip()}' created.", "success")
    except pg_errors.UniqueViolation:
        flash(request, "A category with this name already exists.", "error")
    return RedirectResponse("/admin/categories", status_code=303)


@app.post("/admin/categories/{category_id}/update")
def admin_category_update(
    request: Request,
    category_id: int,
    name: str = Form(...),
    description: str = Form(""),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        execute_query(
            "UPDATE categories SET name = %s, description = %s WHERE category_id = %s",
            (name.strip(), description.strip() or None, category_id),
        )
        flash(request, f"Category #{category_id} updated.", "success")
    except pg_errors.UniqueViolation:
        flash(request, "Another category already has that name.", "error")
    return RedirectResponse("/admin/categories", status_code=303)


@app.post("/admin/categories/{category_id}/delete")
def admin_category_delete(request: Request, category_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    try:
        execute_query("DELETE FROM categories WHERE category_id = %s", (category_id,))
        flash(request, f"Category #{category_id} deleted.", "info")
    except pg_errors.ForeignKeyViolation:
        flash(
            request,
            "Cannot delete this category because menu items still reference it.",
            "error",
        )
    return RedirectResponse("/admin/categories", status_code=303)


# --- Admin: Menu Items CRUD ---
@app.get("/admin/menu-items", response_class=HTMLResponse)
def admin_menu_items(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    items = fetch_all(
        """
        SELECT m.*, r.name AS restaurant_name, c.name AS category_name
        FROM menu_items m
        INNER JOIN restaurants r ON m.restaurant_id = r.restaurant_id
        INNER JOIN categories c  ON m.category_id   = c.category_id
        ORDER BY m.item_id DESC
        """
    )
    restaurants = fetch_all("SELECT restaurant_id, name FROM restaurants ORDER BY name")
    categories = fetch_all("SELECT category_id, name FROM categories ORDER BY name")
    return render(
        request,
        "admin/menu_items.html",
        {
            "active_nav": "menu_items",
            "items": items,
            "restaurants": restaurants,
            "categories": categories,
        },
    )


@app.post("/admin/menu-items/create")
def admin_menu_item_create(
    request: Request,
    restaurant_id: int = Form(...),
    category_id: int = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    price: Decimal = Form(...),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query(
        """
        INSERT INTO menu_items (restaurant_id, category_id, name, description, price, is_available)
        VALUES (%s, %s, %s, %s, %s, TRUE)
        """,
        (restaurant_id, category_id, name.strip(), description.strip() or None, price),
    )
    flash(request, f"Menu item '{name.strip()}' added.", "success")
    return RedirectResponse("/admin/menu-items", status_code=303)


@app.post("/admin/menu-items/{item_id}/update")
def admin_menu_item_update(
    request: Request,
    item_id: int,
    restaurant_id: int = Form(...),
    category_id: int = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    price: Decimal = Form(...),
    is_available: Optional[str] = Form(None),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query(
        """
        UPDATE menu_items
        SET restaurant_id = %s, category_id = %s, name = %s,
            description = %s, price = %s, is_available = %s
        WHERE item_id = %s
        """,
        (
            restaurant_id,
            category_id,
            name.strip(),
            description.strip() or None,
            price,
            bool(is_available),
            item_id,
        ),
    )
    flash(request, f"Menu item #{item_id} updated.", "success")
    return RedirectResponse("/admin/menu-items", status_code=303)


@app.post("/admin/menu-items/{item_id}/delete")
def admin_menu_item_delete(request: Request, item_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query("DELETE FROM menu_items WHERE item_id = %s", (item_id,))
    flash(request, f"Menu item #{item_id} deleted.", "info")
    return RedirectResponse("/admin/menu-items", status_code=303)


# --- Admin: Orders Management ---
@app.get("/admin/orders", response_class=HTMLResponse)
def admin_orders(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    orders = fetch_all(
        """
        SELECT
            o.*,
            u.full_name AS customer_name,
            u.username  AS customer_username,
            r.name      AS restaurant_name,
            p.payment_method,
            p.payment_status,
            STRING_AGG(m.name || ' × ' || oi.quantity, ', ' ORDER BY m.name) AS items_summary
        FROM orders o
        INNER JOIN users u        ON o.user_id       = u.user_id
        INNER JOIN restaurants r  ON o.restaurant_id = r.restaurant_id
        LEFT  JOIN payments p     ON o.order_id      = p.order_id
        LEFT  JOIN order_items oi ON o.order_id      = oi.order_id
        LEFT  JOIN menu_items m   ON oi.item_id      = m.item_id
        GROUP BY o.order_id, u.full_name, u.username, r.name, p.payment_method, p.payment_status
        ORDER BY o.order_date DESC
        """
    )
    return render(
        request,
        "admin/orders.html",
        {"active_nav": "orders", "orders": orders},
    )


@app.post("/admin/orders/{order_id}/update")
def admin_order_update(
    request: Request,
    order_id: int,
    status: str = Form(...),
    payment_status: str = Form(...),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET status = %s WHERE order_id = %s",
                (status, order_id),
            )
            cur.execute(
                """
                UPDATE payments
                SET payment_status = %s,
                    paid_at = CASE
                        WHEN %s = 'Completed' AND paid_at IS NULL THEN NOW()
                        ELSE paid_at
                    END
                WHERE order_id = %s
                """,
                (payment_status, payment_status, order_id),
            )
    flash(request, f"Order #{order_id} status updated to {status} ({payment_status}).", "success")
    return RedirectResponse("/admin/orders", status_code=303)


@app.post("/admin/orders/{order_id}/delete")
def admin_order_delete(request: Request, order_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query("DELETE FROM orders WHERE order_id = %s", (order_id,))
    flash(request, f"Order #{order_id} deleted.", "info")
    return RedirectResponse("/admin/orders", status_code=303)


# --- Admin: Users Management ---
@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    users = fetch_all(
        """
        SELECT u.user_id, u.username, u.email, u.role, u.full_name, u.phone, u.address, u.created_at,
               COUNT(o.order_id) AS order_count
        FROM users u
        LEFT JOIN orders o ON u.user_id = o.user_id
        GROUP BY u.user_id
        ORDER BY u.user_id ASC
        """
    )
    return render(
        request,
        "admin/users.html",
        {"active_nav": "users", "users": users},
    )


@app.post("/admin/users/{user_id}/update")
def admin_user_update(
    request: Request,
    user_id: int,
    role: str = Form(...),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    if user_id == user["user_id"] and role != "admin":
        flash(request, "You cannot remove your own admin privileges.", "warning")
        return RedirectResponse("/admin/users", status_code=303)
    execute_query("UPDATE users SET role = %s WHERE user_id = %s", (role, user_id))
    flash(request, f"User #{user_id} role updated to '{role}'.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@app.post("/admin/users/{user_id}/delete")
def admin_user_delete(request: Request, user_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    if user_id == user["user_id"]:
        flash(request, "You cannot delete your own active account.", "warning")
        return RedirectResponse("/admin/users", status_code=303)
    execute_query("DELETE FROM users WHERE user_id = %s", (user_id,))
    flash(request, f"User #{user_id} deleted.", "info")
    return RedirectResponse("/admin/users", status_code=303)
