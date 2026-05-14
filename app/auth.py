from functools import wraps
from flask import session, redirect, url_for, g


SESSION_USER_KEY = "current_user"


def login_user(user: dict):
    session[SESSION_USER_KEY] = {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


def logout_user():
    session.pop(SESSION_USER_KEY, None)


def get_current_user():
    return session.get(SESSION_USER_KEY)


def is_logged_in() -> bool:
    return get_current_user() is not None


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped_view


def inject_current_user():
    g.current_user = get_current_user()