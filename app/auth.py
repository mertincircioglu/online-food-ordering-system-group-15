import bcrypt
from fastapi import Request
from db import fetch_one


def hash_password(plain_password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception:
        return False


def get_current_user(request: Request):
    member_id = request.session.get("member_id")
    if not member_id:
        return None
    row = fetch_one(
        """
        SELECT
            m.member_id,
            m.email,
            m.first_name,
            m.middle_name,
            m.last_name,
            m.phone_number,
            m.is_banned,
            a.admin_id,
            rm.manager_id,
            rm.restaurant_id AS managed_restaurant_id,
            r.name           AS managed_restaurant_name,
            c.customer_id,
            c.gender,
            CASE
                WHEN a.admin_id IS NOT NULL THEN 'admin'
                WHEN rm.manager_id IS NOT NULL THEN 'manager'
                WHEN c.customer_id IS NOT NULL THEN 'customer'
                ELSE 'member'
            END AS role
        FROM member m
        LEFT JOIN admin a               ON m.member_id = a.member_id
        LEFT JOIN restaurant_manager rm ON m.member_id = rm.member_id
        LEFT JOIN restaurant r          ON rm.restaurant_id = r.restaurant_id
        LEFT JOIN customer c            ON m.member_id = c.member_id
        WHERE m.member_id = %s
        """,
        (member_id,),
    )
    if not row:
        return None
    if row["is_banned"]:
        request.session.clear()
        return None
    parts = [row["first_name"], row["middle_name"], row["last_name"]]
    row["full_name"] = " ".join(p for p in parts if p)
    return row


def flash(request: Request, message: str, category: str = "success"):
    flashes = request.session.get("_flashes", [])
    flashes.append({"message": message, "category": category})
    request.session["_flashes"] = flashes


def pop_flashes(request: Request):
    return request.session.pop("_flashes", [])
