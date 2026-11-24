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
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return fetch_one(
        """
        SELECT user_id, username, email, role, full_name, phone, address, created_at
        FROM users
        WHERE user_id = %s
        """,
        (user_id,),
    )


def flash(request: Request, message: str, category: str = "success"):
    flashes = request.session.get("_flashes", [])
    flashes.append({"message": message, "category": category})
    request.session["_flashes"] = flashes


def pop_flashes(request: Request):
    return request.session.pop("_flashes", [])
