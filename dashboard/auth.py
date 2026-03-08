"""
LiveCold Authentication Module
JWT token generation, password hashing, and token validation
"""

import jwt
import bcrypt
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "livecold-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def hash_password(password):
    """Hash password using bcrypt"""
    if isinstance(password, str):
        password = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(password, salt).decode("utf-8")


def verify_password(password, password_hash):
    """Verify password against hash"""
    if isinstance(password, str):
        password = password.encode("utf-8")
    if isinstance(password_hash, str):
        password_hash = password_hash.encode("utf-8")
    return bcrypt.checkpw(password, password_hash)


def generate_token(user_id, email, role):
    """Generate JWT token for user"""
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def verify_token(token):
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Token expired
    except jwt.InvalidTokenError:
        return None  # Invalid token


def extract_token_from_request():
    """Extract JWT token from Authorization header"""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


def require_auth(f):
    """Decorator to protect routes - requires valid token"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = extract_token_from_request()
        if not token:
            return (
                jsonify({"message": "Unauthorized - missing token"}),
                401,
            )

        payload = verify_token(token)
        if not payload:
            return (
                jsonify({"message": "Unauthorized - invalid or expired token"}),
                401,
            )

        # Add payload to request context
        request.user = payload
        return f(*args, **kwargs)

    return decorated_function


def require_role(*allowed_roles):
    """Decorator to check user role"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = extract_token_from_request()
            if not token:
                return (
                    jsonify({"message": "Unauthorized - missing token"}),
                    401,
                )

            payload = verify_token(token)
            if not payload:
                return (
                    jsonify({"message": "Unauthorized - invalid or expired token"}),
                    401,
                )

            if payload["role"] not in allowed_roles:
                return (
                    jsonify({"message": f"Forbidden - requires role(s): {', '.join(allowed_roles)}"}),
                    403,
                )

            request.user = payload
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def validate_email(email):
    """Basic email validation"""
    import re

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_password(password):
    """Check password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"
    if not any(c in "!@#$%^&*" for c in password):
        return False, "Password must contain at least one special character (!@#$%^&*)"
    return True, "Password is valid"


# SuperAdmin credentials for LiveCold (set in .env)
SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "admin@livecold.com")
SUPER_ADMIN_PASSWORD_HASH = None  # Will be set on first startup


def initialize_super_admin():
    """Initialize super admin account on first startup"""
    from .models import user_exists, create_user

    if user_exists(SUPER_ADMIN_EMAIL):
        return

    # Default password for initial setup - MUST BE CHANGED
    default_password = os.getenv("SUPER_ADMIN_PASSWORD", "SuperAdmin@123")
    password_hash = hash_password(default_password)

    user_id = create_user(
        email=SUPER_ADMIN_EMAIL,
        password_hash=password_hash,
        role="admin",
        name="LiveCold Admin",
    )

    if user_id:
        print(
            f"⚠️ SuperAdmin initialized with email: {SUPER_ADMIN_EMAIL} and default password: {default_password}"
        )
        print("🔴 IMPORTANT: Change this password immediately in production!")
