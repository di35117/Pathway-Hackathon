"""
LiveCold Authentication Routes
/api/auth/login and /api/auth/register endpoints
"""

from flask import Blueprint, request, jsonify
from .auth import (
    hash_password,
    verify_password,
    generate_token,
    validate_email,
    validate_password,
    require_auth,
)
from .models import (
    user_exists,
    get_user_by_email,
    create_user,
    create_driver,
    create_client,
    get_driver_by_user_id,
    get_client_by_user_id,
    log_action,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /api/auth/login
    Login endpoint for driver, client, and admin roles
    """
    data = request.get_json()

    # Validate input
    if not data:
        return jsonify({"message": "Request body is required"}), 400

    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "").strip()

    if not email or not password or not role:
        return (
            jsonify({"message": "email, password, and role are required"}),
            400,
        )

    if role not in ["driver", "client", "admin"]:
        return jsonify({"message": "role must be driver, client, or admin"}), 400

    # Get user by email
    user = get_user_by_email(email)
    if not user:
        return jsonify({"message": "Invalid credentials"}), 401

    # Check role matches
    if user["role"] != role:
        return jsonify({"message": "Invalid credentials"}), 401

    # Check if user is active
    if not user["is_active"]:
        return (
            jsonify(
                {
                    "message": "Account is inactive. Please wait for admin approval or contact support."
                }
            ),
            403,
        )

    # Verify password
    if not verify_password(password, user["password_hash"]):
        # Log failed attempt
        log_action(user["id"], "login_failed", "auth", {"reason": "invalid_password"})
        return jsonify({"message": "Invalid credentials"}), 401

    # Generate token
    token = generate_token(user["id"], user["email"], user["role"])

    # Log successful login
    log_action(user["id"], "login_success", "auth", {})

    # Build response
    response_data = {
        "token": token,
        "role": user["role"],
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
    }

    # Include role-specific info
    if role == "driver":
        driver = get_driver_by_user_id(user["id"])
        if driver:
            response_data["driverId"] = driver["id"]
            response_data["vehicleId"] = driver["vehicle_id"]
    elif role == "client":
        client = get_client_by_user_id(user["id"])
        if client:
            response_data["clientId"] = client["id"]
            response_data["companyName"] = client["company_name"]

    return jsonify(response_data), 200


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    POST /api/auth/register
    Registration endpoint for driver and client roles
    """
    data = request.get_json()

    # Validate input
    if not data:
        return jsonify({"message": "Request body is required"}), 400

    role = data.get("role", "").strip()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()

    # Validate role
    if role not in ["driver", "client"]:
        return (
            jsonify({"message": "role must be driver or client"}),
            400,
        )

    # Validate required common fields
    if not all([role, name, email, phone, password]):
        return (
            jsonify(
                {"message": "role, name, email, phone, and password are required"}
            ),
            400,
        )

    # Validate email format
    if not validate_email(email):
        return jsonify({"message": "Invalid email format"}), 400

    # Check if email already exists
    if user_exists(email):
        return jsonify({"message": "Email already registered"}), 409

    # Validate password strength
    is_valid, message = validate_password(password)
    if not is_valid:
        return jsonify({"message": message}), 400

    # Role-specific validation
    if role == "driver":
        vehicle_id = data.get("vehicleId", "").strip()
        license_no = data.get("licenseNo", "").strip()

        if not vehicle_id:
            return jsonify({"message": "vehicleId is required for drivers"}), 400

        # Create user
        password_hash = hash_password(password)
        user_id = create_user(email, password_hash, "driver", name, phone)

        if not user_id:
            return jsonify({"message": "Failed to create user account"}), 500

        # Create driver record
        driver_id = create_driver(user_id, vehicle_id, license_no)
        if not driver_id:
            return jsonify({"message": "Failed to create driver record"}), 500

        log_action(user_id, "registration", "driver", {
            "vehicle_id": vehicle_id,
            "license_no": license_no
        })

        return (
            jsonify(
                {
                    "message": "Registration successful. Your account will be activated after admin review.",
                    "driverId": driver_id,
                }
            ),
            201,
        )

    elif role == "client":
        company_name = data.get("companyName", "").strip()
        gst_no = data.get("gstNo", "").strip()
        city = data.get("city", "").strip()

        if not company_name:
            return jsonify({"message": "companyName is required for clients"}), 400

        # Create user
        password_hash = hash_password(password)
        user_id = create_user(email, password_hash, "client", name, phone)

        if not user_id:
            return jsonify({"message": "Failed to create user account"}), 500

        # Create client record
        client_id = create_client(user_id, company_name, gst_no, city)
        if not client_id:
            return jsonify({"message": "Failed to create client record"}), 500

        log_action(user_id, "registration", "client", {
            "company_name": company_name,
            "gst_no": gst_no,
            "city": city
        })

        return (
            jsonify(
                {
                    "message": "Registration successful. Awaiting admin activation.",
                    "clientId": client_id,
                }
            ),
            201,
        )


@auth_bp.route("/verify", methods=["GET"])
@require_auth
def verify():
    """
    GET /api/auth/verify
    Verify and refresh token - requires valid token in Authorization header
    """
    user_payload = request.user

    return (
        jsonify(
            {
                "valid": True,
                "user_id": user_payload["user_id"],
                "email": user_payload["email"],
                "role": user_payload["role"],
                "exp": user_payload["exp"],
            }
        ),
        200,
    )


@auth_bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    """
    POST /api/auth/logout
    Log out user (mainly for frontend cleanup)
    """
    user_id = request.user["user_id"]
    log_action(user_id, "logout", "auth", {})
    return jsonify({"message": "Logged out successfully"}), 200
