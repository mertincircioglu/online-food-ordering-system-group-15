import math
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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

DELIVERY_TYPES = ["Platform_carrier", "Restaurant_carrier", "Pick_up"]
PAYMENT_METHODS = ["Online", "Card at the door", "Cash at the door"]
ORDER_STATUSES = ["Order Confirmed", "Preparing", "On the way", "Delivered", "Cancelled"]
PRODUCT_CATEGORIES = ["Main Course", "Drinks", "Sweets", "Other"]
DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[0-9]{10,15}$")


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.fullmatch(value.strip()))


def is_valid_phone(value: str) -> bool:
    return bool(PHONE_RE.fullmatch(value.strip()))


def safe_decimal(value, default=None):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return default


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


def require_customer(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return None, redirect
    if user["role"] != "customer":
        return None, render(
            request,
            "forbidden.html",
            {"required_role": "Customer"},
            status_code=403,
        )
    return user, None


def require_manager(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return None, redirect
    if user["role"] != "manager":
        return None, render(
            request,
            "forbidden.html",
            {"required_role": "Restaurant Manager"},
            status_code=403,
        )
    return user, None


def require_admin(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return None, redirect
    if user["role"] != "admin":
        return None, render(
            request,
            "forbidden.html",
            {"required_role": "Administrator"},
            status_code=403,
        )
    return user, None


def effective_price(price: Decimal, discount_available: bool, discount_percentage: Optional[Decimal]) -> Decimal:
    if discount_available and discount_percentage:
        discounted = price * (Decimal("100") - discount_percentage) / Decimal("100")
        return discounted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def estimate_delivery_minutes(lat1, lon1, lat2, lon2, delivery_type: str) -> int:
    if delivery_type == "Pick_up" or lat2 is None or lon2 is None:
        return 15
    r_km = 6371.0
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    dist_km = 2 * r_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    # 15 min prep + ~3 min per km
    return max(15, min(75, int(round(15 + dist_km * 3))))


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
    email: str = Form(...),
    password: str = Form(...),
):
    member = fetch_one(
        """
        SELECT m.member_id, m.email, m.first_name, m.last_name, m.password_hash, m.is_banned,
               CASE
                   WHEN a.admin_id IS NOT NULL THEN 'admin'
                   WHEN rm.manager_id IS NOT NULL THEN 'manager'
                   ELSE 'customer'
               END AS role
        FROM member m
        LEFT JOIN admin a               ON m.member_id = a.member_id
        LEFT JOIN restaurant_manager rm ON m.member_id = rm.member_id
        WHERE LOWER(m.email) = %s
        """,
        (email.strip().lower(),),
    )
    if not member or not verify_password(password, member["password_hash"]):
        flash(request, "Invalid email or password.", "error")
        return RedirectResponse("/login", status_code=303)

    if member["is_banned"]:
        flash(request, "This account has been banned by an administrator.", "error")
        return RedirectResponse("/login", status_code=303)

    request.session["member_id"] = member["member_id"]
    flash(request, f"Welcome back, {member['first_name']} {member['last_name']}!", "success")
    if member["role"] == "admin":
        return RedirectResponse("/admin", status_code=303)
    if member["role"] == "manager":
        return RedirectResponse("/manager", status_code=303)
    return RedirectResponse("/", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/", status_code=303)
    return render(request, "register.html")


@app.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    middle_name: str = Form(""),
    last_name: str = Form(...),
    phone_number: str = Form(...),
    gender: str = Form(...),
    province: str = Form("Ankara"),
    district: str = Form(...),
    subdistrict: str = Form(...),
    neighborhood: str = Form(...),
    street: str = Form(...),
):
    email_clean = email.strip().lower()
    phone_clean = phone_number.strip()
    if not is_valid_email(email_clean):
        flash(request, "Please enter a valid email address (e.g. name@example.com).", "error")
        return RedirectResponse("/register", status_code=303)
    if not is_valid_phone(phone_clean):
        flash(request, "Phone number must contain digits only (10 to 15 digits, e.g. 05321234567).", "error")
        return RedirectResponse("/register", status_code=303)
    if len(password) < 6:
        flash(request, "Password must be at least 6 characters long.", "error")
        return RedirectResponse("/register", status_code=303)

    pw_hash = hash_password(password)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO member (email, first_name, middle_name, last_name, password_hash, phone_number)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING member_id
                    """,
                    (
                        email_clean,
                        first_name.strip(),
                        middle_name.strip() or None,
                        last_name.strip(),
                        pw_hash,
                        phone_number.strip(),
                    ),
                )
                member_id = cur.fetchone()["member_id"]

                cur.execute(
                    "INSERT INTO customer (member_id, gender) VALUES (%s, %s) RETURNING customer_id",
                    (member_id, gender),
                )
                customer_id = cur.fetchone()["customer_id"]

                cur.execute(
                    """
                    INSERT INTO address (address_title, province, district, subdistrict, neighborhood, street, latitude, longitude)
                    VALUES ('Home', %s, %s, %s, %s, %s, 39.900000, 32.850000)
                    RETURNING address_id
                    """,
                    (province.strip(), district.strip(), subdistrict.strip(), neighborhood.strip(), street.strip()),
                )
                address_id = cur.fetchone()["address_id"]

                cur.execute(
                    "INSERT INTO customer_address (customer_id, address_id) VALUES (%s, %s)",
                    (customer_id, address_id),
                )
    except pg_errors.UniqueViolation:
        flash(request, "An account with this email already exists.", "error")
        return RedirectResponse("/register", status_code=303)

    request.session["member_id"] = member_id
    flash(request, "Customer account created! Welcome to BiteFlow.", "success")
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    flash(request, "You have been signed out.", "info")
    return RedirectResponse("/login", status_code=303)


# ---------------------------------------------------------------------------
# Public Storefront & Restaurant Details
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    q: Optional[str] = None,
    cuisine: Optional[str] = None,
    delivery_type: Optional[str] = None,
):
    cuisines = fetch_all("SELECT DISTINCT cuisine_type FROM restaurant_cuisine ORDER BY cuisine_type")
    query = """
        SELECT
            r.restaurant_id,
            r.name,
            r.phone_number,
            r.email,
            r.min_order_amount,
            a.province,
            a.district,
            a.neighborhood,
            COALESCE(rev_stats.avg_rating, 0.0)   AS avg_rating,
            COALESCE(rev_stats.review_count, 0)   AS review_count,
            COALESCE(prod_stats.product_count, 0) AS product_count,
            COALESCE(cuis.cuisine_list, '')       AS cuisine_list,
            COALESCE(deliv.delivery_list, '')     AS delivery_list
        FROM restaurant r
        INNER JOIN address a ON r.address_id = a.address_id
        LEFT JOIN (
            SELECT restaurant_id, ROUND(AVG(rating), 1) AS avg_rating, COUNT(*) AS review_count
            FROM restaurant_review
            GROUP BY restaurant_id
        ) rev_stats ON r.restaurant_id = rev_stats.restaurant_id
        LEFT JOIN (
            SELECT restaurant_id, COUNT(*) AS product_count
            FROM product
            WHERE is_available = TRUE
            GROUP BY restaurant_id
        ) prod_stats ON r.restaurant_id = prod_stats.restaurant_id
        LEFT JOIN (
            SELECT restaurant_id, STRING_AGG(cuisine_type, ', ' ORDER BY cuisine_type) AS cuisine_list
            FROM restaurant_cuisine
            GROUP BY restaurant_id
        ) cuis ON r.restaurant_id = cuis.restaurant_id
        LEFT JOIN (
            SELECT restaurant_id, STRING_AGG(delivery_type, ', ' ORDER BY delivery_type) AS delivery_list
            FROM restaurant_delivery_type
            GROUP BY restaurant_id
        ) deliv ON r.restaurant_id = deliv.restaurant_id
        WHERE 1=1
    """
    params = []
    if cuisine:
        query += """
            AND EXISTS (
                SELECT 1 FROM restaurant_cuisine rc
                WHERE rc.restaurant_id = r.restaurant_id AND rc.cuisine_type = %s
            )
        """
        params.append(cuisine)
    if delivery_type:
        query += """
            AND EXISTS (
                SELECT 1 FROM restaurant_delivery_type rd
                WHERE rd.restaurant_id = r.restaurant_id AND rd.delivery_type = %s
            )
        """
        params.append(delivery_type)
    if q:
        like = f"%{q.strip().lower()}%"
        query += """
            AND (
                LOWER(r.name) LIKE %s
                OR LOWER(a.district) LIKE %s
                OR LOWER(COALESCE(cuis.cuisine_list, '')) LIKE %s
            )
        """
        params.extend([like, like, like])

    query += " ORDER BY avg_rating DESC, r.name ASC"
    restaurants = fetch_all(query, params)

    stats = fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM restaurant) AS restaurant_count,
            (SELECT COUNT(*) FROM product WHERE is_available = TRUE) AS product_count,
            (SELECT COUNT(*) FROM orders) AS order_count
        """
    )
    return render(
        request,
        "home.html",
        {
            "restaurants": restaurants,
            "cuisines": [c["cuisine_type"] for c in cuisines],
            "delivery_types": DELIVERY_TYPES,
            "selected_cuisine": cuisine or "",
            "selected_delivery_type": delivery_type or "",
            "search_query": q or "",
            "stats": stats,
        },
    )


@app.get("/restaurants/{restaurant_id}", response_class=HTMLResponse)
def restaurant_detail(
    request: Request,
    restaurant_id: int,
    category: Optional[str] = None,
    discount: Optional[str] = None,
):
    user = get_current_user(request)
    restaurant = fetch_one(
        """
        SELECT
            r.*,
            a.province, a.district, a.subdistrict, a.neighborhood, a.street,
            a.building_no, a.floor, a.latitude, a.longitude,
            COALESCE(ROUND(AVG(rev.rating), 1), 0.0) AS avg_rating,
            COUNT(rev.restaurant_review_id)          AS review_count
        FROM restaurant r
        INNER JOIN address a ON r.address_id = a.address_id
        LEFT JOIN restaurant_review rev ON r.restaurant_id = rev.restaurant_id
        WHERE r.restaurant_id = %s
        GROUP BY r.restaurant_id, a.address_id
        """,
        (restaurant_id,),
    )
    if not restaurant:
        flash(request, "Restaurant not found.", "error")
        return RedirectResponse("/", status_code=303)

    cuisines = fetch_all(
        "SELECT cuisine_type FROM restaurant_cuisine WHERE restaurant_id = %s ORDER BY cuisine_type",
        (restaurant_id,),
    )
    delivery_types = fetch_all(
        "SELECT delivery_type FROM restaurant_delivery_type WHERE restaurant_id = %s ORDER BY delivery_type",
        (restaurant_id,),
    )
    working_hours = fetch_all(
        """
        SELECT day, opening_time, closing_time
        FROM restaurant_working_hours
        WHERE restaurant_id = %s
        ORDER BY ARRAY_POSITION(ARRAY['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'], day)
        """,
        (restaurant_id,),
    )

    prod_sql = "SELECT * FROM product WHERE restaurant_id = %s"
    prod_params = [restaurant_id]
    if category:
        prod_sql += " AND category = %s"
        prod_params.append(category)
    if discount == "1":
        prod_sql += " AND discount_available = TRUE"
    prod_sql += " ORDER BY category, product_name"
    products = fetch_all(prod_sql, prod_params)
    for p in products:
        p["final_price"] = effective_price(p["price"], p["discount_available"], p["discount_percentage"])

    reviews = fetch_all(
        """
        SELECT rev.*, m.first_name, m.last_name, m.email
        FROM restaurant_review rev
        INNER JOIN customer c ON rev.customer_id = c.customer_id
        INNER JOIN member m   ON c.member_id     = m.member_id
        WHERE rev.restaurant_id = %s
        ORDER BY rev.date DESC
        """,
        (restaurant_id,),
    )

    saved_addresses = []
    if user and user["customer_id"]:
        saved_addresses = fetch_all(
            """
            SELECT a.*
            FROM address a
            INNER JOIN customer_address ca ON a.address_id = ca.address_id
            WHERE ca.customer_id = %s
            ORDER BY a.address_id ASC
            """,
            (user["customer_id"],),
        )

    return render(
        request,
        "restaurant.html",
        {
            "restaurant": restaurant,
            "cuisines": [c["cuisine_type"] for c in cuisines],
            "delivery_types": [d["delivery_type"] for d in delivery_types],
            "working_hours": working_hours,
            "products": products,
            "categories": PRODUCT_CATEGORIES,
            "selected_category": category or "",
            "discount_only": discount == "1",
            "reviews": reviews,
            "saved_addresses": saved_addresses,
            "payment_methods": PAYMENT_METHODS,
        },
    )


# ---------------------------------------------------------------------------
# Customer Ordering (INSERT) & Order Lifecycle (UPDATE / DELETE)
# ---------------------------------------------------------------------------
@app.post("/restaurants/{restaurant_id}/order")
async def place_order(request: Request, restaurant_id: int):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    form = await request.form()
    delivery_type = str(form.get("delivery_type", "Platform_carrier")).strip()
    payment_method = str(form.get("payment_method", "Online")).strip()
    raw_addr_id = str(form.get("delivery_address_id", "")).strip()

    if payment_method not in PAYMENT_METHODS:
        payment_method = "Online"

    valid_dt = fetch_one(
        "SELECT 1 FROM restaurant_delivery_type WHERE restaurant_id = %s AND delivery_type = %s",
        (restaurant_id, delivery_type),
    )
    if not valid_dt:
        flash(request, "Selected delivery type is not offered by this restaurant.", "error")
        return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)

    restaurant = fetch_one(
        """
        SELECT r.*, a.latitude, a.longitude
        FROM restaurant r
        INNER JOIN address a ON r.address_id = a.address_id
        WHERE r.restaurant_id = %s
        """,
        (restaurant_id,),
    )
    if not restaurant:
        flash(request, "Restaurant not found.", "error")
        return RedirectResponse("/", status_code=303)

    delivery_address_id = None
    dest_lat, dest_lon = None, None
    if delivery_type != "Pick_up":
        if not raw_addr_id.isdigit():
            flash(request, "Please select a saved delivery address (or add one in Profile).", "warning")
            return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)
        addr = fetch_one(
            """
            SELECT a.address_id, a.latitude, a.longitude
            FROM address a
            INNER JOIN customer_address ca ON a.address_id = ca.address_id
            WHERE ca.customer_id = %s AND a.address_id = %s
            """,
            (user["customer_id"], int(raw_addr_id)),
        )
        if not addr:
            flash(request, "Selected delivery address was not found in your saved addresses.", "error")
            return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)
        delivery_address_id = addr["address_id"]
        dest_lat, dest_lon = addr["latitude"], addr["longitude"]

    selected = []
    for key, val in form.items():
        if key.startswith("qty_"):
            try:
                pid = int(key.replace("qty_", ""))
                qty = int(val)
                if qty > 0:
                    selected.append((pid, qty))
            except ValueError:
                continue

    if not selected:
        flash(request, "Please select at least one product before placing an order.", "warning")
        return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)

    pids = [s[0] for s in selected]
    db_products = fetch_all(
        """
        SELECT product_id, price, discount_available, discount_percentage
        FROM product
        WHERE restaurant_id = %s AND is_available = TRUE AND product_id = ANY(%s)
        """,
        (restaurant_id, pids),
    )
    prod_map = {
        row["product_id"]: effective_price(
            row["price"], row["discount_available"], row["discount_percentage"]
        )
        for row in db_products
    }

    line_items = []
    total_price = Decimal("0.00")
    for pid, qty in selected:
        if pid in prod_map:
            uprice = prod_map[pid]
            total_price += uprice * qty
            line_items.append((pid, uprice, qty))

    if not line_items:
        flash(request, "Selected products are unavailable.", "error")
        return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)

    if total_price < restaurant["min_order_amount"]:
        flash(
            request,
            f"Minimum order amount for {restaurant['name']} is {restaurant['min_order_amount']:.2f} TL.",
            "warning",
        )
        return RedirectResponse(f"/restaurants/{restaurant_id}", status_code=303)

    est_minutes = estimate_delivery_minutes(
        restaurant["latitude"], restaurant["longitude"], dest_lat, dest_lon, delivery_type
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (
                    restaurant_id, customer_id, delivery_address_id,
                    delivery_type, payment_method, order_status,
                    estimated_delivery_time, total_price
                )
                VALUES (%s, %s, %s, %s, %s, 'Order Confirmed', %s, %s)
                RETURNING order_id
                """,
                (
                    restaurant_id,
                    user["customer_id"],
                    delivery_address_id,
                    delivery_type,
                    payment_method,
                    est_minutes,
                    total_price,
                ),
            )
            order_id = cur.fetchone()["order_id"]

            for pid, uprice, qty in line_items:
                cur.execute(
                    """
                    INSERT INTO order_items (order_id, product_id, unit_price, quantity)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (order_id, pid, uprice, qty),
                )

    flash(
        request,
        f"Order #{order_id} placed ({total_price:.2f} TL, est. {est_minutes} min)!",
        "success",
    )
    return RedirectResponse("/my-orders", status_code=303)


@app.get("/my-orders", response_class=HTMLResponse)
def my_orders(request: Request):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    orders = fetch_all(
        """
        SELECT
            o.*,
            r.name AS restaurant_name,
            COALESCE(
                a.address_title || ' — ' || a.district || ', ' || a.neighborhood || ', ' || a.street,
                a.district || ', ' || a.neighborhood || ', ' || a.street,
                'Self Pick-up at Restaurant'
            ) AS delivery_location,
            STRING_AGG(p.product_name || ' × ' || oi.quantity, ', ' ORDER BY p.product_name) AS items_summary,
            rev.restaurant_review_id,
            rev.rating  AS review_rating,
            rev.comment AS review_comment,
            (
                o.order_status IN ('Preparing', 'On the way')
                AND EXTRACT(EPOCH FROM (NOW() - o.order_date)) >= 3600
            ) AS can_late_cancel
        FROM orders o
        INNER JOIN restaurant r      ON o.restaurant_id       = r.restaurant_id
        LEFT  JOIN address a         ON o.delivery_address_id = a.address_id
        LEFT  JOIN order_items oi    ON o.order_id            = oi.order_id
        LEFT  JOIN product p         ON oi.product_id         = p.product_id
        LEFT  JOIN restaurant_review rev ON o.order_id        = rev.order_id
        WHERE o.customer_id = %s
        GROUP BY o.order_id, r.name, a.address_id, rev.restaurant_review_id
        ORDER BY o.order_date DESC
        """,
        (user["customer_id"],),
    )
    saved_addresses = fetch_all(
        """
        SELECT a.*
        FROM address a
        INNER JOIN customer_address ca ON a.address_id = ca.address_id
        WHERE ca.customer_id = %s
        ORDER BY a.address_id ASC
        """,
        (user["customer_id"],),
    )
    return render(
        request,
        "my_orders.html",
        {
            "orders": orders,
            "saved_addresses": saved_addresses,
            "payment_methods": PAYMENT_METHODS,
        },
    )


@app.post("/my-orders/{order_id}/update")
def update_my_order(
    request: Request,
    order_id: int,
    payment_method: str = Form(...),
    delivery_address_id: str = Form(""),
):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    addr_val = int(delivery_address_id) if delivery_address_id.isdigit() else None
    updated = execute_query(
        """
        UPDATE orders
        SET payment_method = %s,
            delivery_address_id = CASE WHEN delivery_type = 'Pick_up' THEN NULL ELSE COALESCE(%s, delivery_address_id) END
        WHERE order_id = %s AND customer_id = %s AND order_status = 'Order Confirmed'
        """,
        (payment_method, addr_val, order_id, user["customer_id"]),
    )
    if updated:
        flash(request, f"Order #{order_id} updated.", "success")
    else:
        flash(request, "Only orders in 'Order Confirmed' status can be edited.", "warning")
    return RedirectResponse("/my-orders", status_code=303)


@app.post("/my-orders/{order_id}/delete")
def delete_my_order(request: Request, order_id: int):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    deleted = execute_query(
        """
        DELETE FROM orders
        WHERE order_id = %s AND customer_id = %s AND order_status = 'Order Confirmed'
        """,
        (order_id, user["customer_id"]),
    )
    if deleted:
        flash(request, f"Order #{order_id} cancelled and removed.", "info")
        return RedirectResponse("/my-orders", status_code=303)

    # Business Rule: customer may cancel if >= 1 hour passed and order is still not Delivered
    late_cancelled = execute_query(
        """
        UPDATE orders
        SET order_status = 'Cancelled'
        WHERE order_id = %s
          AND customer_id = %s
          AND order_status IN ('Preparing', 'On the way')
          AND EXTRACT(EPOCH FROM (NOW() - order_date)) >= 3600
        """,
        (order_id, user["customer_id"]),
    )
    if late_cancelled:
        flash(request, f"Delayed Order #{order_id} (>1 hour) has been cancelled.", "info")
    else:
        flash(
            request,
            "Orders can only be cancelled while 'Order Confirmed' or if more than 1 hour has passed without delivery.",
            "warning",
        )
    return RedirectResponse("/my-orders", status_code=303)


# ---------------------------------------------------------------------------
# Order-Linked Restaurant Reviews (INSERT / UPDATE / DELETE)
# ---------------------------------------------------------------------------
@app.post("/my-orders/{order_id}/review")
def create_order_review(
    request: Request,
    order_id: int,
    rating: int = Form(...),
    comment: str = Form(""),
):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    order = fetch_one(
        """
        SELECT order_id, restaurant_id, order_status
        FROM orders
        WHERE order_id = %s AND customer_id = %s
        """,
        (order_id, user["customer_id"]),
    )
    if not order or order["order_status"] != "Delivered":
        flash(request, "You can only review your own Delivered orders.", "warning")
        return RedirectResponse("/my-orders", status_code=303)

    try:
        execute_query(
            """
            INSERT INTO restaurant_review (customer_id, restaurant_id, order_id, rating, comment)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user["customer_id"], order["restaurant_id"], order_id, rating, comment.strip() or None),
        )
        flash(request, f"Review submitted for Order #{order_id}!", "success")
    except pg_errors.UniqueViolation:
        flash(request, "This order has already been reviewed.", "warning")
    return RedirectResponse("/my-orders", status_code=303)


@app.post("/reviews/{review_id}/update")
def update_review(
    request: Request,
    review_id: int,
    rating: int = Form(...),
    comment: str = Form(""),
):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    updated = execute_query(
        """
        UPDATE restaurant_review
        SET rating = %s, comment = %s
        WHERE restaurant_review_id = %s AND customer_id = %s
        """,
        (rating, comment.strip() or None, review_id, user["customer_id"]),
    )
    if updated:
        flash(request, "Your review has been updated.", "success")
    else:
        flash(request, "Could not update review.", "error")
    return RedirectResponse("/my-orders", status_code=303)


@app.post("/reviews/{review_id}/delete")
def delete_review(request: Request, review_id: int):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    deleted = execute_query(
        "DELETE FROM restaurant_review WHERE restaurant_review_id = %s AND customer_id = %s",
        (review_id, user["customer_id"]),
    )
    if deleted:
        flash(request, "Review deleted.", "info")
    else:
        flash(request, "Could not delete review.", "error")
    return RedirectResponse("/my-orders", status_code=303)


# ---------------------------------------------------------------------------
# Member Profile + Customer Saved Addresses & Payment Info CRUD
# ---------------------------------------------------------------------------
@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    saved_addresses = []
    saved_payments = []
    if user["customer_id"]:
        saved_addresses = fetch_all(
            """
            SELECT a.*
            FROM address a
            INNER JOIN customer_address ca ON a.address_id = ca.address_id
            WHERE ca.customer_id = %s
            ORDER BY a.address_id DESC
            """,
            (user["customer_id"],),
        )
        saved_payments = fetch_all(
            """
            SELECT * FROM customer_payment_info
            WHERE customer_id = %s
            ORDER BY payment_info_id DESC
            """,
            (user["customer_id"],),
        )
    return render(
        request,
        "profile.html",
        {"saved_addresses": saved_addresses, "saved_payments": saved_payments},
    )


@app.post("/profile")
def profile_update(
    request: Request,
    email: str = Form(...),
    first_name: str = Form(...),
    middle_name: str = Form(""),
    last_name: str = Form(...),
    phone_number: str = Form(...),
    gender: Optional[str] = Form(None),
):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    email_clean = email.strip().lower()
    phone_clean = phone_number.strip()
    if not is_valid_email(email_clean):
        flash(request, "Please enter a valid email address (e.g. name@example.com).", "error")
        return RedirectResponse("/profile", status_code=303)
    if not is_valid_phone(phone_clean):
        flash(request, "Phone number must contain digits only (10 to 15 digits).", "error")
        return RedirectResponse("/profile", status_code=303)

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE member
                    SET email = %s, first_name = %s, middle_name = %s, last_name = %s, phone_number = %s
                    WHERE member_id = %s
                    """,
                    (email_clean, first_name.strip(), middle_name.strip() or None, last_name.strip(), phone_clean, user["member_id"]),
                )
                if user["customer_id"] and gender:
                    cur.execute(
                        "UPDATE customer SET gender = %s WHERE customer_id = %s",
                        (gender, user["customer_id"]),
                    )
        flash(request, "Account information updated.", "success")
    except pg_errors.UniqueViolation:
        flash(request, "That email address is already used by another account.", "error")
    return RedirectResponse("/profile", status_code=303)


@app.post("/profile/password")
def profile_password_update(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    user, redirect = require_login(request)
    if redirect:
        return redirect

    row = fetch_one("SELECT password_hash FROM member WHERE member_id = %s", (user["member_id"],))
    if not row or not verify_password(current_password, row["password_hash"]):
        flash(request, "Current password is incorrect.", "error")
        return RedirectResponse("/profile", status_code=303)
    if len(new_password) < 6:
        flash(request, "New password must be at least 6 characters long.", "error")
        return RedirectResponse("/profile", status_code=303)
    if new_password != confirm_password:
        flash(request, "New passwords do not match.", "error")
        return RedirectResponse("/profile", status_code=303)

    execute_query(
        "UPDATE member SET password_hash = %s WHERE member_id = %s",
        (hash_password(new_password), user["member_id"]),
    )
    flash(request, "Password updated and securely hashed with bcrypt.", "success")
    return RedirectResponse("/profile", status_code=303)


@app.post("/profile/addresses/create")
def customer_address_create(
    request: Request,
    address_title: str = Form(""),
    province: str = Form("Ankara"),
    district: str = Form(...),
    subdistrict: str = Form(...),
    neighborhood: str = Form(...),
    street: str = Form(...),
    floor: str = Form(""),
    building_no: str = Form(""),
    latitude: Decimal = Form(Decimal("39.900000")),
    longitude: Decimal = Form(Decimal("32.850000")),
    details: str = Form(""),
):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO address (
                    address_title, province, district, subdistrict, neighborhood,
                    street, floor, building_no, latitude, longitude, details
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING address_id
                """,
                (
                    address_title.strip() or None,
                    province.strip(),
                    district.strip(),
                    subdistrict.strip(),
                    neighborhood.strip(),
                    street.strip(),
                    floor.strip() or None,
                    building_no.strip() or None,
                    latitude,
                    longitude,
                    details.strip() or None,
                ),
            )
            aid = cur.fetchone()["address_id"]
            cur.execute(
                "INSERT INTO customer_address (customer_id, address_id) VALUES (%s, %s)",
                (user["customer_id"], aid),
            )
    flash(request, "Saved delivery address added.", "success")
    return RedirectResponse("/profile", status_code=303)


@app.post("/profile/addresses/{address_id}/update")
def customer_address_update(
    request: Request,
    address_id: int,
    address_title: str = Form(""),
    province: str = Form("Ankara"),
    district: str = Form(...),
    subdistrict: str = Form(...),
    neighborhood: str = Form(...),
    street: str = Form(...),
    floor: str = Form(""),
    building_no: str = Form(""),
    details: str = Form(""),
):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    owns = fetch_one(
        "SELECT 1 FROM customer_address WHERE customer_id = %s AND address_id = %s",
        (user["customer_id"], address_id),
    )
    if not owns:
        flash(request, "You cannot edit this address.", "error")
        return RedirectResponse("/profile", status_code=303)

    execute_query(
        """
        UPDATE address
        SET address_title = %s, province = %s, district = %s, subdistrict = %s,
            neighborhood = %s, street = %s, floor = %s, building_no = %s, details = %s
        WHERE address_id = %s
        """,
        (
            address_title.strip() or None,
            province.strip(),
            district.strip(),
            subdistrict.strip(),
            neighborhood.strip(),
            street.strip(),
            floor.strip() or None,
            building_no.strip() or None,
            details.strip() or None,
            address_id,
        ),
    )
    flash(request, "Saved delivery address updated.", "success")
    return RedirectResponse("/profile", status_code=303)


@app.post("/profile/addresses/{address_id}/delete")
def customer_address_delete(request: Request, address_id: int):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    execute_query(
        "DELETE FROM customer_address WHERE customer_id = %s AND address_id = %s",
        (user["customer_id"], address_id),
    )
    flash(request, "Saved address removed from your account.", "info")
    return RedirectResponse("/profile", status_code=303)


@app.post("/profile/payments/create")
def customer_payment_create(request: Request, saved_payment_info: str = Form(...)):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    execute_query(
        "INSERT INTO customer_payment_info (customer_id, saved_payment_info) VALUES (%s, %s)",
        (user["customer_id"], saved_payment_info.strip()),
    )
    flash(request, "Saved payment method added.", "success")
    return RedirectResponse("/profile", status_code=303)


@app.post("/profile/payments/{payment_info_id}/delete")
def customer_payment_delete(request: Request, payment_info_id: int):
    user, blocked = require_customer(request)
    if blocked:
        return blocked

    execute_query(
        "DELETE FROM customer_payment_info WHERE payment_info_id = %s AND customer_id = %s",
        (payment_info_id, user["customer_id"]),
    )
    flash(request, "Saved payment method removed.", "info")
    return RedirectResponse("/profile", status_code=303)


# ---------------------------------------------------------------------------
# RESTAURANT MANAGER PORTAL (Strict RBAC: role == 'manager')
# ---------------------------------------------------------------------------
@app.get("/manager", response_class=HTMLResponse)
def manager_dashboard(request: Request):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    rid = user["managed_restaurant_id"]
    restaurant = fetch_one(
        """
        SELECT r.*, a.province, a.district, a.neighborhood, a.street,
               COALESCE(ROUND(AVG(rev.rating), 2), 0.00) AS avg_rating,
               COUNT(rev.restaurant_review_id)           AS review_count
        FROM restaurant r
        INNER JOIN address a ON r.address_id = a.address_id
        LEFT JOIN restaurant_review rev ON r.restaurant_id = rev.restaurant_id
        WHERE r.restaurant_id = %s
        GROUP BY r.restaurant_id, a.address_id
        """,
        (rid,),
    )
    kpis = fetch_one(
        """
        SELECT
            COALESCE(SUM(total_price) FILTER (WHERE order_status <> 'Cancelled'), 0) AS revenue,
            COUNT(*) AS order_count,
            (SELECT COUNT(*) FROM product WHERE restaurant_id = %s) AS product_count
        FROM orders
        WHERE restaurant_id = %s
        """,
        (rid, rid),
    )
    cuisines = [
        r["cuisine_type"]
        for r in fetch_all(
            "SELECT cuisine_type FROM restaurant_cuisine WHERE restaurant_id = %s ORDER BY cuisine_type",
            (rid,),
        )
    ]
    delivery_types = [
        r["delivery_type"]
        for r in fetch_all(
            "SELECT delivery_type FROM restaurant_delivery_type WHERE restaurant_id = %s",
            (rid,),
        )
    ]
    working_hours = fetch_all(
        """
        SELECT day, opening_time, closing_time
        FROM restaurant_working_hours
        WHERE restaurant_id = %s
        ORDER BY ARRAY_POSITION(ARRAY['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'], day)
        """,
        (rid,),
    )
    reviews = fetch_all(
        """
        SELECT rev.*, m.first_name, m.last_name
        FROM restaurant_review rev
        INNER JOIN customer c ON rev.customer_id = c.customer_id
        INNER JOIN member m   ON c.member_id     = m.member_id
        WHERE rev.restaurant_id = %s
        ORDER BY rev.date DESC
        """,
        (rid,),
    )
    return render(
        request,
        "manager/dashboard.html",
        {
            "active_nav": "overview",
            "restaurant": restaurant,
            "kpis": kpis,
            "cuisines_str": ", ".join(cuisines),
            "selected_delivery_types": delivery_types,
            "all_delivery_types": DELIVERY_TYPES,
            "working_hours": working_hours,
            "reviews": reviews,
        },
    )


@app.post("/manager/working-hours/update")
async def manager_working_hours_update(request: Request):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    rid = user["managed_restaurant_id"]
    form = await request.form()
    with get_db() as conn:
        with conn.cursor() as cur:
            for day in DAYS_OF_WEEK:
                open_t = str(form.get(f"open_{day}", "10:00")).strip()
                close_t = str(form.get(f"close_{day}", "23:00")).strip()
                cur.execute(
                    """
                    INSERT INTO restaurant_working_hours (restaurant_id, day, opening_time, closing_time)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (restaurant_id, day)
                    DO UPDATE SET opening_time = EXCLUDED.opening_time, closing_time = EXCLUDED.closing_time
                    """,
                    (rid, day, open_t, close_t),
                )
    flash(request, "Weekly working hours updated.", "success")
    return RedirectResponse("/manager", status_code=303)


@app.post("/manager/restaurant/update")
async def manager_restaurant_update(request: Request):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    rid = user["managed_restaurant_id"]
    form = await request.form()
    name = str(form.get("name", "")).strip()
    phone_number = str(form.get("phone_number", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    min_order_amount = safe_decimal(form.get("min_order_amount", "0"))
    cuisines_raw = str(form.get("cuisines", ""))
    selected_dt = form.getlist("delivery_types")

    if not is_valid_phone(phone_number):
        flash(request, "Phone number must contain digits only (10 to 15 digits).", "error")
        return RedirectResponse("/manager", status_code=303)
    if not is_valid_email(email):
        flash(request, "Please enter a valid restaurant email address.", "error")
        return RedirectResponse("/manager", status_code=303)
    if min_order_amount is None or min_order_amount < 0:
        flash(request, "Minimum order amount must be 0 or greater.", "error")
        return RedirectResponse("/manager", status_code=303)

    cuisines = [c.strip() for c in cuisines_raw.split(",") if c.strip()]
    if not selected_dt:
        selected_dt = ["Platform_carrier"]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE restaurant
                SET name = %s, phone_number = %s, email = %s, min_order_amount = %s
                WHERE restaurant_id = %s
                """,
                (name, phone_number, email, min_order_amount, rid),
            )
            if cuisines:
                cur.execute("DELETE FROM restaurant_cuisine WHERE restaurant_id = %s", (rid,))
                for c in dict.fromkeys(cuisines):
                    cur.execute(
                        "INSERT INTO restaurant_cuisine (restaurant_id, cuisine_type) VALUES (%s, %s)",
                        (rid, c),
                    )
            cur.execute("DELETE FROM restaurant_delivery_type WHERE restaurant_id = %s", (rid,))
            for dt in dict.fromkeys(selected_dt):
                if dt in DELIVERY_TYPES:
                    cur.execute(
                        "INSERT INTO restaurant_delivery_type (restaurant_id, delivery_type) VALUES (%s, %s)",
                        (rid, dt),
                    )
    flash(request, "Restaurant profile updated.", "success")
    return RedirectResponse("/manager", status_code=303)


@app.get("/manager/products", response_class=HTMLResponse)
def manager_products(request: Request):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    rid = user["managed_restaurant_id"]
    products = fetch_all(
        "SELECT * FROM product WHERE restaurant_id = %s ORDER BY product_id DESC",
        (rid,),
    )
    for p in products:
        p["final_price"] = effective_price(p["price"], p["discount_available"], p["discount_percentage"])
    return render(
        request,
        "manager/products.html",
        {
            "active_nav": "products",
            "products": products,
            "categories": PRODUCT_CATEGORIES,
        },
    )


@app.post("/manager/products/create")
def manager_product_create(
    request: Request,
    product_name: str = Form(...),
    description: str = Form(""),
    category: str = Form(...),
    price: Decimal = Form(...),
    discount_available: Optional[str] = Form(None),
    discount_percentage: str = Form(""),
):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    disc_flag = bool(discount_available)
    disc_pct = safe_decimal(discount_percentage) if (disc_flag and discount_percentage.strip()) else None
    if disc_flag and (disc_pct is None or disc_pct <= 0 or disc_pct > 90):
        disc_flag = False
        disc_pct = None

    execute_query(
        """
        INSERT INTO product (
            restaurant_id, product_name, description, category,
            price, is_available, discount_available, discount_percentage
        )
        VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)
        """,
        (
            user["managed_restaurant_id"],
            product_name.strip(),
            description.strip() or None,
            category,
            price,
            disc_flag,
            disc_pct,
        ),
    )
    flash(request, f"Product '{product_name.strip()}' added to your menu.", "success")
    return RedirectResponse("/manager/products", status_code=303)


@app.post("/manager/products/{product_id}/update")
def manager_product_update(
    request: Request,
    product_id: int,
    product_name: str = Form(...),
    description: str = Form(""),
    category: str = Form(...),
    price: Decimal = Form(...),
    is_available: Optional[str] = Form(None),
    discount_available: Optional[str] = Form(None),
    discount_percentage: str = Form(""),
):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    disc_flag = bool(discount_available)
    disc_pct = safe_decimal(discount_percentage) if (disc_flag and discount_percentage.strip()) else None
    if disc_flag and (disc_pct is None or disc_pct <= 0 or disc_pct > 90):
        disc_flag = False
        disc_pct = None

    execute_query(
        """
        UPDATE product
        SET product_name = %s, description = %s, category = %s, price = %s,
            is_available = %s, discount_available = %s, discount_percentage = %s
        WHERE product_id = %s AND restaurant_id = %s
        """,
        (
            product_name.strip(),
            description.strip() or None,
            category,
            price,
            bool(is_available),
            disc_flag,
            disc_pct,
            product_id,
            user["managed_restaurant_id"],
        ),
    )
    flash(request, f"Product #{product_id} updated.", "success")
    return RedirectResponse("/manager/products", status_code=303)


@app.post("/manager/products/{product_id}/delete")
def manager_product_delete(request: Request, product_id: int):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    execute_query(
        "DELETE FROM product WHERE product_id = %s AND restaurant_id = %s",
        (product_id, user["managed_restaurant_id"]),
    )
    flash(request, f"Product #{product_id} deleted.", "info")
    return RedirectResponse("/manager/products", status_code=303)


@app.get("/manager/orders", response_class=HTMLResponse)
def manager_orders(request: Request):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    orders = fetch_all(
        """
        SELECT
            o.*,
            m.first_name || ' ' || m.last_name AS customer_name,
            m.phone_number                     AS customer_phone,
            COALESCE(a.district || ', ' || a.neighborhood || ', ' || a.street, 'Self Pick-up') AS delivery_location,
            STRING_AGG(p.product_name || ' × ' || oi.quantity, ', ' ORDER BY p.product_name) AS items_summary
        FROM orders o
        INNER JOIN customer c     ON o.customer_id         = c.customer_id
        INNER JOIN member m       ON c.member_id           = m.member_id
        LEFT  JOIN address a      ON o.delivery_address_id = a.address_id
        LEFT  JOIN order_items oi ON o.order_id            = oi.order_id
        LEFT  JOIN product p      ON oi.product_id         = p.product_id
        WHERE o.restaurant_id = %s
          AND o.order_status IN ('Order Confirmed', 'Preparing', 'On the way')
        GROUP BY o.order_id, m.first_name, m.last_name, m.phone_number, a.address_id
        ORDER BY o.order_date DESC
        """,
        (user["managed_restaurant_id"],),
    )
    return render(
        request,
        "manager/orders.html",
        {"active_nav": "orders", "orders": orders, "order_statuses": ORDER_STATUSES},
    )


@app.get("/manager/past-orders", response_class=HTMLResponse)
def manager_past_orders(request: Request):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    orders = fetch_all(
        """
        SELECT
            o.*,
            m.first_name || ' ' || m.last_name AS customer_name,
            m.phone_number                     AS customer_phone,
            COALESCE(a.district || ', ' || a.neighborhood || ', ' || a.street, 'Self Pick-up') AS delivery_location,
            STRING_AGG(p.product_name || ' × ' || oi.quantity, ', ' ORDER BY p.product_name) AS items_summary
        FROM orders o
        INNER JOIN customer c     ON o.customer_id         = c.customer_id
        INNER JOIN member m       ON c.member_id           = m.member_id
        LEFT  JOIN address a      ON o.delivery_address_id = a.address_id
        LEFT  JOIN order_items oi ON o.order_id            = oi.order_id
        LEFT  JOIN product p      ON oi.product_id         = p.product_id
        WHERE o.restaurant_id = %s
          AND o.order_status IN ('Delivered', 'Cancelled')
        GROUP BY o.order_id, m.first_name, m.last_name, m.phone_number, a.address_id
        ORDER BY o.order_date DESC
        """,
        (user["managed_restaurant_id"],),
    )
    return render(
        request,
        "manager/past_orders.html",
        {"active_nav": "past_orders", "orders": orders},
    )


@app.post("/manager/orders/{order_id}/update")
def manager_order_update(request: Request, order_id: int, order_status: str = Form(...)):
    user, blocked = require_manager(request)
    if blocked:
        return blocked

    execute_query(
        "UPDATE orders SET order_status = %s WHERE order_id = %s AND restaurant_id = %s",
        (order_status, order_id, user["managed_restaurant_id"]),
    )
    if order_status in ("Delivered", "Cancelled"):
        flash(request, f"Order #{order_id} marked as '{order_status}' and moved to Past Orders.", "success")
    else:
        flash(request, f"Order #{order_id} moved to '{order_status}'.", "success")
    return RedirectResponse("/manager/orders", status_code=303)


# ---------------------------------------------------------------------------
# ADMIN PANEL (Strict RBAC: role == 'admin')
# ---------------------------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked

    kpis = fetch_one(
        """
        SELECT
            (SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE order_status <> 'Cancelled') AS total_revenue,
            (SELECT COUNT(*) FROM orders) AS total_orders,
            (SELECT COUNT(*) FROM restaurant) AS total_restaurants,
            (SELECT COUNT(*) FROM member) AS total_members
        """
    )

    # Complex Query 1: Multi-table JOIN (7 tables!)
    q1_join = fetch_all(
        """
        SELECT
            o.order_id,
            m.first_name || ' ' || m.last_name AS customer_name,
            r.name                              AS restaurant_name,
            COALESCE(a.district || ', ' || a.neighborhood, 'Self Pick-up') AS delivery_location,
            o.delivery_type,
            o.payment_method,
            o.order_status,
            STRING_AGG(p.product_name || ' (x' || oi.quantity || ')', ', ' ORDER BY p.product_name) AS ordered_products,
            o.total_price
        FROM orders o
        INNER JOIN customer c     ON o.customer_id         = c.customer_id
        INNER JOIN member m       ON c.member_id           = m.member_id
        INNER JOIN restaurant r   ON o.restaurant_id       = r.restaurant_id
        INNER JOIN order_items oi ON o.order_id            = oi.order_id
        INNER JOIN product p      ON oi.product_id         = p.product_id
        LEFT  JOIN address a      ON o.delivery_address_id = a.address_id
        GROUP BY o.order_id, m.first_name, m.last_name, r.name, a.district, a.neighborhood,
                 o.delivery_type, o.payment_method, o.order_status, o.total_price
        ORDER BY o.order_date DESC
        """
    )

    # Complex Query 2: GROUP BY + ORDER BY
    q2_groupby = fetch_all(
        """
        SELECT
            r.restaurant_id,
            r.name                                       AS restaurant_name,
            COALESCE(cuisines.cuisine_list, 'General')   AS cuisines,
            COUNT(o.order_id)                            AS total_orders,
            COALESCE(SUM(o.total_price), 0.00)           AS total_revenue,
            COALESCE(ROUND(AVG(o.total_price), 2), 0.00) AS avg_order_value,
            COALESCE(rev_stats.derived_rating, 0.00)     AS derived_rating
        FROM restaurant r
        LEFT JOIN orders o
               ON r.restaurant_id = o.restaurant_id AND o.order_status <> 'Cancelled'
        LEFT JOIN (
            SELECT restaurant_id, ROUND(AVG(rating), 2) AS derived_rating
            FROM restaurant_review
            GROUP BY restaurant_id
        ) rev_stats ON r.restaurant_id = rev_stats.restaurant_id
        LEFT JOIN (
            SELECT restaurant_id, STRING_AGG(cuisine_type, ', ' ORDER BY cuisine_type) AS cuisine_list
            FROM restaurant_cuisine
            GROUP BY restaurant_id
        ) cuisines ON r.restaurant_id = cuisines.restaurant_id
        GROUP BY r.restaurant_id, r.name, cuisines.cuisine_list, rev_stats.derived_rating
        ORDER BY total_revenue DESC, derived_rating DESC
        """
    )

    # Complex Query 3: Subquery
    q3_subquery = fetch_all(
        """
        SELECT
            c.customer_id,
            m.email,
            m.first_name || ' ' || m.last_name AS customer_name,
            COUNT(o.order_id)                   AS order_count,
            SUM(o.total_price)                  AS total_spent,
            ROUND((
                SELECT AVG(customer_total)
                FROM (
                    SELECT SUM(total_price) AS customer_total
                    FROM orders
                    WHERE order_status <> 'Cancelled'
                    GROUP BY customer_id
                ) AS sub_avg
            ), 2)                               AS platform_avg_spending
        FROM customer c
        INNER JOIN member m ON c.member_id   = m.member_id
        INNER JOIN orders o ON c.customer_id = o.customer_id
        WHERE o.order_status <> 'Cancelled'
        GROUP BY c.customer_id, m.email, m.first_name, m.last_name
        HAVING SUM(o.total_price) > (
            SELECT AVG(customer_total)
            FROM (
                SELECT SUM(total_price) AS customer_total
                FROM orders
                WHERE order_status <> 'Cancelled'
                GROUP BY customer_id
            ) AS avg_calc
        )
        ORDER BY total_spent DESC
        """
    )

    table_stats = fetch_all(
        """
        SELECT
            table_name,
            (xpath('/row/cnt/text()', query_to_xml(
                format('SELECT count(*) AS cnt FROM %%I.%%I', table_schema, table_name),
                false, true, ''
            )))[1]::text::int AS row_count
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
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
            "table_stats": table_stats,
        },
    )


# --- Admin: Restaurants CRUD ---
@app.get("/admin/restaurants", response_class=HTMLResponse)
def admin_restaurants(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    restaurants = fetch_all(
        """
        SELECT
            r.*,
            a.province, a.district, a.neighborhood, a.street,
            COALESCE(cuis.cuisine_list, '')   AS cuisine_list,
            COALESCE(deliv.delivery_list, '') AS delivery_list,
            COALESCE(ROUND(AVG(rev.rating), 1), 0.0) AS derived_rating
        FROM restaurant r
        INNER JOIN address a ON r.address_id = a.address_id
        LEFT JOIN restaurant_review rev ON r.restaurant_id = rev.restaurant_id
        LEFT JOIN (
            SELECT restaurant_id, STRING_AGG(cuisine_type, ', ' ORDER BY cuisine_type) AS cuisine_list
            FROM restaurant_cuisine
            GROUP BY restaurant_id
        ) cuis ON r.restaurant_id = cuis.restaurant_id
        LEFT JOIN (
            SELECT restaurant_id, STRING_AGG(delivery_type, ', ' ORDER BY delivery_type) AS delivery_list
            FROM restaurant_delivery_type
            GROUP BY restaurant_id
        ) deliv ON r.restaurant_id = deliv.restaurant_id
        GROUP BY r.restaurant_id, a.address_id, cuis.cuisine_list, deliv.delivery_list
        ORDER BY r.restaurant_id DESC
        """
    )
    return render(
        request,
        "admin/restaurants.html",
        {
            "active_nav": "restaurants",
            "restaurants": restaurants,
            "delivery_types": DELIVERY_TYPES,
        },
    )


@app.post("/admin/restaurants/create")
async def admin_restaurant_create(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked

    form = await request.form()
    name = str(form.get("name", "")).strip()
    phone_number = str(form.get("phone_number", "")).strip()
    email = str(form.get("email", "")).strip().lower()
    min_order_amount = safe_decimal(form.get("min_order_amount", "100"))
    province = str(form.get("province", "Ankara")).strip()
    district = str(form.get("district", "")).strip()
    subdistrict = str(form.get("subdistrict", "")).strip()
    neighborhood = str(form.get("neighborhood", "")).strip()
    street = str(form.get("street", "")).strip()
    cuisines = [c.strip() for c in str(form.get("cuisines", "Turkish")).split(",") if c.strip()]
    selected_dt = form.getlist("delivery_types") or ["Platform_carrier"]

    if not is_valid_phone(phone_number):
        flash(request, "Phone number must contain digits only (10 to 15 digits).", "error")
        return RedirectResponse("/admin/restaurants", status_code=303)
    if not is_valid_email(email):
        flash(request, "Please enter a valid restaurant email address.", "error")
        return RedirectResponse("/admin/restaurants", status_code=303)
    if min_order_amount is None or min_order_amount < 0:
        flash(request, "Minimum order amount must be 0 or greater.", "error")
        return RedirectResponse("/admin/restaurants", status_code=303)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO address (address_title, province, district, subdistrict, neighborhood, street, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s, %s, 39.900000, 32.850000)
                RETURNING address_id
                """,
                (name, province, district, subdistrict, neighborhood, street),
            )
            addr_id = cur.fetchone()["address_id"]

            cur.execute(
                """
                INSERT INTO restaurant (address_id, name, phone_number, email, min_order_amount)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING restaurant_id
                """,
                (addr_id, name, phone_number, email, min_order_amount),
            )
            rid = cur.fetchone()["restaurant_id"]

            for c in dict.fromkeys(cuisines or ["General"]):
                cur.execute(
                    "INSERT INTO restaurant_cuisine (restaurant_id, cuisine_type) VALUES (%s, %s)",
                    (rid, c),
                )
            for dt in dict.fromkeys(selected_dt):
                if dt in DELIVERY_TYPES:
                    cur.execute(
                        "INSERT INTO restaurant_delivery_type (restaurant_id, delivery_type) VALUES (%s, %s)",
                        (rid, dt),
                    )
            for day in DAYS_OF_WEEK:
                cur.execute(
                    """
                    INSERT INTO restaurant_working_hours (restaurant_id, day, opening_time, closing_time)
                    VALUES (%s, %s, '10:00', '23:00')
                    """,
                    (rid, day),
                )
    flash(request, f"Restaurant '{name}' created with address, cuisines, delivery types, and working hours.", "success")
    return RedirectResponse("/admin/restaurants", status_code=303)


@app.post("/admin/restaurants/{restaurant_id}/update")
def admin_restaurant_update(
    request: Request,
    restaurant_id: int,
    name: str = Form(...),
    phone_number: str = Form(...),
    email: str = Form(...),
    min_order_amount: Decimal = Form(...),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    phone_clean = phone_number.strip()
    email_clean = email.strip().lower()
    if not is_valid_phone(phone_clean):
        flash(request, "Phone number must contain digits only (10 to 15 digits).", "error")
        return RedirectResponse("/admin/restaurants", status_code=303)
    if not is_valid_email(email_clean):
        flash(request, "Please enter a valid restaurant email address.", "error")
        return RedirectResponse("/admin/restaurants", status_code=303)
    if min_order_amount < 0:
        flash(request, "Minimum order amount cannot be negative.", "error")
        return RedirectResponse("/admin/restaurants", status_code=303)
    execute_query(
        """
        UPDATE restaurant
        SET name = %s, phone_number = %s, email = %s, min_order_amount = %s
        WHERE restaurant_id = %s
        """,
        (name.strip(), phone_clean, email_clean, min_order_amount, restaurant_id),
    )
    flash(request, f"Restaurant #{restaurant_id} updated.", "success")
    return RedirectResponse("/admin/restaurants", status_code=303)


@app.post("/admin/restaurants/{restaurant_id}/delete")
def admin_restaurant_delete(request: Request, restaurant_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query("DELETE FROM restaurant WHERE restaurant_id = %s", (restaurant_id,))
    flash(request, f"Restaurant #{restaurant_id} deleted.", "info")
    return RedirectResponse("/admin/restaurants", status_code=303)


# --- Admin: Products CRUD ---
@app.get("/admin/products", response_class=HTMLResponse)
def admin_products(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    products = fetch_all(
        """
        SELECT p.*, r.name AS restaurant_name
        FROM product p
        INNER JOIN restaurant r ON p.restaurant_id = r.restaurant_id
        ORDER BY p.product_id DESC
        """
    )
    for p in products:
        p["final_price"] = effective_price(p["price"], p["discount_available"], p["discount_percentage"])
    restaurants = fetch_all("SELECT restaurant_id, name FROM restaurant ORDER BY name")
    return render(
        request,
        "admin/products.html",
        {
            "active_nav": "products",
            "products": products,
            "restaurants": restaurants,
            "categories": PRODUCT_CATEGORIES,
        },
    )


@app.post("/admin/products/create")
def admin_product_create(
    request: Request,
    restaurant_id: int = Form(...),
    product_name: str = Form(...),
    description: str = Form(""),
    category: str = Form(...),
    price: Decimal = Form(...),
    discount_available: Optional[str] = Form(None),
    discount_percentage: str = Form(""),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    disc_flag = bool(discount_available)
    disc_pct = safe_decimal(discount_percentage) if (disc_flag and discount_percentage.strip()) else None
    if disc_flag and (disc_pct is None or disc_pct <= 0 or disc_pct > 90):
        disc_flag = False
        disc_pct = None

    execute_query(
        """
        INSERT INTO product (
            restaurant_id, product_name, description, category,
            price, is_available, discount_available, discount_percentage
        )
        VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)
        """,
        (restaurant_id, product_name.strip(), description.strip() or None, category, price, disc_flag, disc_pct),
    )
    flash(request, f"Product '{product_name.strip()}' added.", "success")
    return RedirectResponse("/admin/products", status_code=303)


@app.post("/admin/products/{product_id}/update")
def admin_product_update(
    request: Request,
    product_id: int,
    restaurant_id: int = Form(...),
    product_name: str = Form(...),
    description: str = Form(""),
    category: str = Form(...),
    price: Decimal = Form(...),
    is_available: Optional[str] = Form(None),
    discount_available: Optional[str] = Form(None),
    discount_percentage: str = Form(""),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    disc_flag = bool(discount_available)
    disc_pct = safe_decimal(discount_percentage) if (disc_flag and discount_percentage.strip()) else None
    if disc_flag and (disc_pct is None or disc_pct <= 0 or disc_pct > 90):
        disc_flag = False
        disc_pct = None

    execute_query(
        """
        UPDATE product
        SET restaurant_id = %s, product_name = %s, description = %s, category = %s,
            price = %s, is_available = %s, discount_available = %s, discount_percentage = %s
        WHERE product_id = %s
        """,
        (
            restaurant_id,
            product_name.strip(),
            description.strip() or None,
            category,
            price,
            bool(is_available),
            disc_flag,
            disc_pct,
            product_id,
        ),
    )
    flash(request, f"Product #{product_id} updated.", "success")
    return RedirectResponse("/admin/products", status_code=303)


@app.post("/admin/products/{product_id}/delete")
def admin_product_delete(request: Request, product_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query("DELETE FROM product WHERE product_id = %s", (product_id,))
    flash(request, f"Product #{product_id} deleted.", "info")
    return RedirectResponse("/admin/products", status_code=303)


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
            m.first_name || ' ' || m.last_name AS customer_name,
            m.email                            AS customer_email,
            r.name                             AS restaurant_name,
            COALESCE(a.district || ', ' || a.neighborhood, 'Self Pick-up') AS delivery_location,
            STRING_AGG(p.product_name || ' × ' || oi.quantity, ', ' ORDER BY p.product_name) AS items_summary
        FROM orders o
        INNER JOIN customer c     ON o.customer_id         = c.customer_id
        INNER JOIN member m       ON c.member_id           = m.member_id
        INNER JOIN restaurant r   ON o.restaurant_id       = r.restaurant_id
        LEFT  JOIN address a      ON o.delivery_address_id = a.address_id
        LEFT  JOIN order_items oi ON o.order_id            = oi.order_id
        LEFT  JOIN product p      ON oi.product_id         = p.product_id
        GROUP BY o.order_id, m.first_name, m.last_name, m.email, r.name, a.address_id
        ORDER BY o.order_date DESC
        """
    )
    return render(
        request,
        "admin/orders.html",
        {"active_nav": "orders", "orders": orders, "order_statuses": ORDER_STATUSES},
    )


@app.post("/admin/orders/{order_id}/update")
def admin_order_update(request: Request, order_id: int, order_status: str = Form(...)):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query("UPDATE orders SET order_status = %s WHERE order_id = %s", (order_status, order_id))
    flash(request, f"Order #{order_id} status updated to '{order_status}'.", "success")
    return RedirectResponse("/admin/orders", status_code=303)


@app.post("/admin/orders/{order_id}/delete")
def admin_order_delete(request: Request, order_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query("DELETE FROM orders WHERE order_id = %s", (order_id,))
    flash(request, f"Order #{order_id} deleted.", "info")
    return RedirectResponse("/admin/orders", status_code=303)


# --- Admin: Reviews Moderation ---
@app.get("/admin/reviews", response_class=HTMLResponse)
def admin_reviews(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    reviews = fetch_all(
        """
        SELECT rev.*, r.name AS restaurant_name,
               m.first_name || ' ' || m.last_name AS customer_name, m.email AS customer_email
        FROM restaurant_review rev
        INNER JOIN restaurant r ON rev.restaurant_id = r.restaurant_id
        INNER JOIN customer c   ON rev.customer_id   = c.customer_id
        INNER JOIN member m     ON c.member_id       = m.member_id
        ORDER BY rev.date DESC
        """
    )
    return render(request, "admin/reviews.html", {"active_nav": "reviews", "reviews": reviews})


@app.post("/admin/reviews/{review_id}/delete")
def admin_review_delete(request: Request, review_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    execute_query("DELETE FROM restaurant_review WHERE restaurant_review_id = %s", (review_id,))
    flash(request, f"Review #{review_id} removed.", "info")
    return RedirectResponse("/admin/reviews", status_code=303)


# --- Admin: Members & Restaurant Managers Management ---
@app.get("/admin/members", response_class=HTMLResponse)
def admin_members(request: Request):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    members = fetch_all(
        """
        SELECT
            m.member_id, m.email, m.first_name, m.middle_name, m.last_name, m.phone_number, m.is_banned,
            CASE
                WHEN a.admin_id IS NOT NULL THEN 'admin'
                WHEN rm.manager_id IS NOT NULL THEN 'manager'
                WHEN c.customer_id IS NOT NULL THEN 'customer'
                ELSE 'member'
            END AS role,
            r.name AS managed_restaurant,
            c.gender
        FROM member m
        LEFT JOIN admin a               ON m.member_id = a.member_id
        LEFT JOIN restaurant_manager rm ON m.member_id = rm.member_id
        LEFT JOIN restaurant r          ON rm.restaurant_id = r.restaurant_id
        LEFT JOIN customer c            ON m.member_id = c.member_id
        ORDER BY m.member_id ASC
        """
    )
    restaurants = fetch_all("SELECT restaurant_id, name FROM restaurant ORDER BY name")
    return render(
        request,
        "admin/members.html",
        {"active_nav": "members", "members": members, "restaurants": restaurants},
    )


@app.post("/admin/members/create-manager")
def admin_create_manager(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone_number: str = Form(...),
    restaurant_id: int = Form(...),
):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    email_clean = email.strip().lower()
    phone_clean = phone_number.strip()
    if not is_valid_email(email_clean):
        flash(request, "Please enter a valid email address for the manager.", "error")
        return RedirectResponse("/admin/members", status_code=303)
    if not is_valid_phone(phone_clean):
        flash(request, "Phone number must contain digits only (10 to 15 digits).", "error")
        return RedirectResponse("/admin/members", status_code=303)
    if len(password) < 6:
        flash(request, "Password must be at least 6 characters long.", "error")
        return RedirectResponse("/admin/members", status_code=303)
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO member (email, first_name, last_name, password_hash, phone_number)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING member_id
                    """,
                    (email_clean, first_name.strip(), last_name.strip(), hash_password(password), phone_clean),
                )
                mid = cur.fetchone()["member_id"]
                cur.execute(
                    "INSERT INTO restaurant_manager (member_id, restaurant_id) VALUES (%s, %s)",
                    (mid, restaurant_id),
                )
        flash(request, f"Restaurant Manager '{email.strip()}' created.", "success")
    except pg_errors.UniqueViolation:
        flash(request, "That email is already registered.", "error")
    return RedirectResponse("/admin/members", status_code=303)


@app.post("/admin/members/{member_id}/toggle-ban")
def admin_member_toggle_ban(request: Request, member_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    if member_id == user["member_id"]:
        flash(request, "You cannot ban your own active admin account.", "warning")
        return RedirectResponse("/admin/members", status_code=303)
    row = fetch_one(
        "UPDATE member SET is_banned = NOT is_banned WHERE member_id = %s RETURNING email, is_banned",
        (member_id,),
    )
    if row:
        state = "banned" if row["is_banned"] else "unbanned"
        flash(request, f"Member '{row['email']}' has been {state}.", "warning" if row["is_banned"] else "success")
    return RedirectResponse("/admin/members", status_code=303)


@app.post("/admin/members/{member_id}/delete")
def admin_member_delete(request: Request, member_id: int):
    user, blocked = require_admin(request)
    if blocked:
        return blocked
    if member_id == user["member_id"]:
        flash(request, "You cannot delete your own active admin account.", "warning")
        return RedirectResponse("/admin/members", status_code=303)
    execute_query("DELETE FROM member WHERE member_id = %s", (member_id,))
    flash(request, f"Member #{member_id} deleted.", "info")
    return RedirectResponse("/admin/members", status_code=303)
