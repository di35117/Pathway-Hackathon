"""
LiveCold Authentication Models
User, Driver, Client, and Admin database models with SQLite
"""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(__file__), "livecold.db")


def get_db():
    """Get or create database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()

    # Users table (base table for all roles)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            is_active BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Drivers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            vehicle_id TEXT NOT NULL,
            license_no TEXT,
            status TEXT DEFAULT 'inactive',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Clients (Companies) table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            company_name TEXT NOT NULL,
            gst_no TEXT,
            city TEXT,
            status TEXT DEFAULT 'pending_approval',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Admins table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            permission_level TEXT DEFAULT 'standard',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Audit log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            action TEXT,
            resource TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            details TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


def user_exists(email):
    """Check if user already exists"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_user_by_email(email):
    """Get user by email"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id):
    """Get user by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None


def create_user(email, password_hash, role, name, phone=None):
    """Create new user"""
    from uuid import uuid4
    user_id = f"USR-{uuid4().hex[:12].upper()}"

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO users (id, email, password_hash, role, name, phone, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, email, password_hash, role, name, phone, 1),
        )
        conn.commit()
        conn.close()
        return user_id
    except sqlite3.IntegrityError as e:
        conn.close()
        return None


def create_driver(user_id, vehicle_id, license_no=None):
    """Create driver record"""
    from uuid import uuid4
    driver_id = f"DRV-{uuid4().hex[:12].upper()}"

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO drivers (id, user_id, vehicle_id, license_no, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (driver_id, user_id, vehicle_id, license_no, "active"),
        )
        conn.commit()
        conn.close()
        return driver_id
    except Exception as e:
        conn.close()
        return None


def create_client(user_id, company_name, gst_no=None, city=None):
    """Create client (company) record"""
    from uuid import uuid4
    client_id = f"CLT-{uuid4().hex[:12].upper()}"

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO clients (id, user_id, company_name, gst_no, city, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (client_id, user_id, company_name, gst_no, city, "active"),
        )
        conn.commit()
        conn.close()
        return client_id
    except Exception as e:
        conn.close()
        return None


def get_driver_by_user_id(user_id):
    """Get driver info by user ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM drivers WHERE user_id = ?", (user_id,))
    driver = cursor.fetchone()
    conn.close()
    return dict(driver) if driver else None


def get_client_by_user_id(user_id):
    """Get client info by user ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients WHERE user_id = ?", (user_id,))
    client = cursor.fetchone()
    conn.close()
    return dict(client) if client else None


def activate_user(user_id):
    """Activate a user account"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def log_action(user_id, action, resource, details=None):
    """Log user action"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO audit_log (user_id, action, resource, details)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, action, resource, json.dumps(details) if details else None),
    )
    conn.commit()
    conn.close()


# Initialize DB on module load
if not os.path.exists(DB_PATH):
    init_db()
