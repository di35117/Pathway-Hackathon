#!/usr/bin/env python
"""
LiveCold Authentication Backend - Quick Setup & Verification Script
This script verifies that all authentication components are properly installed and configured.
"""

import sys
import os
from pathlib import Path

def check_environment():
    """Verify Python environment and dependencies"""
    print("\n" + "="*60)
    print("🧪 LiveCold Authentication Backend - Verification")
    print("="*60 + "\n")
    
    # Check Python version
    print("📋 Environment Check:")
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"  ✓ Python: {py_version}")
    
    # Check required packages
    required_packages = [
        ('flask', 'Flask'),
        ('flask_cors', 'flask-cors'),
        ('jwt', 'PyJWT'),
        ('bcrypt', 'bcrypt'),
        ('dotenv', 'python-dotenv'),
        ('paho', 'paho-mqtt'),
    ]
    
    print("\n📦 Required Packages:")
    all_installed = True
    for import_name, display_name in required_packages:
        try:
            __import__(import_name)
            print(f"  ✓ {display_name}")
        except ImportError:
            print(f"  ✗ {display_name} - NOT INSTALLED")
            all_installed = False
    
    return all_installed


def check_files():
    """Verify all authentication files are present"""
    print("\n📁 Project Files:")
    
    required_files = [
        ('dashboard/__init__.py', 'Package init'),
        ('dashboard/models.py', 'Database models'),
        ('dashboard/auth.py', 'Auth utilities'),
        ('dashboard/auth_routes.py', 'API routes'),
        ('dashboard/app.py', 'Flask app'),
        ('dashboard/test_auth.py', 'Test suite'),
        ('dashboard/AUTH_API.md', 'API docs'),
        ('AUTHENTICATION_SETUP.md', 'Setup guide'),
        ('AUTH_BACKEND_SUMMARY.md', 'Summary'),
        ('.env', 'Environment config'),
    ]
    
    all_exist = True
    for file_path, description in required_files:
        if Path(file_path).exists():
            size = Path(file_path).stat().st_size
            print(f"  ✓ {description:.<40} ({size:,} bytes)")
        else:
            print(f"  ✗ {description:.<40} MISSING")
            all_exist = False
    
    return all_exist


def check_modules():
    """Test that all modules can be imported"""
    print("\n🔧 Module Imports:")
    
    try:
        from dashboard.models import init_db, get_db
        print("  ✓ dashboard.models")
    except Exception as e:
        print(f"  ✗ dashboard.models - {e}")
        return False
    
    try:
        from dashboard.auth import hash_password, generate_token, verify_token
        print("  ✓ dashboard.auth")
    except Exception as e:
        print(f"  ✗ dashboard.auth - {e}")
        return False
    
    try:
        from dashboard.auth_routes import auth_bp
        print("  ✓ dashboard.auth_routes")
    except Exception as e:
        print(f"  ✗ dashboard.auth_routes - {e}")
        return False
    
    return True


def check_database():
    """Verify database initialization"""
    print("\n💾 Database:")
    
    try:
        from dashboard.models import init_db
        init_db()
        
        db_path = Path("dashboard/livecold.db")
        if db_path.exists():
            size = db_path.stat().st_size
            print(f"  ✓ Database initialized ({size:,} bytes)")
            
            # Check tables
            from dashboard.models import get_db
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            expected_tables = ['users', 'drivers', 'clients', 'admins', 'audit_log']
            for table in expected_tables:
                if table in tables:
                    print(f"    ✓ {table} table")
                else:
                    print(f"    ✗ {table} table MISSING")
            
            return all(t in tables for t in expected_tables)
        else:
            print("  ✗ Database file not created")
            return False
            
    except Exception as e:
        print(f"  ✗ Database error: {e}")
        return False


def check_superadmin():
    """Verify super admin account"""
    print("\n👤 Super Admin Account:")
    
    try:
        from dashboard.auth import initialize_super_admin
        from dashboard.models import get_user_by_email
        
        email = os.getenv("SUPER_ADMIN_EMAIL", "admin@livecold.com")
        initialize_super_admin()
        
        user = get_user_by_email(email)
        if user:
            print(f"  ✓ Admin user exists: {email}")
            print(f"    ID: {user['id']}")
            print(f"    Role: {user['role']}")
            print(f"    Active: {'Yes' if user['is_active'] else 'No'}")
            return True
        else:
            print(f"  ✗ Admin user not found: {email}")
            return False
            
    except Exception as e:
        print(f"  ✗ Error checking admin: {e}")
        return False


def test_password_hashing():
    """Test password hashing and verification"""
    print("\n🔐 Password Hashing:")
    
    try:
        from dashboard.auth import hash_password, verify_password
        
        password = "TestPass@123"
        hashed = hash_password(password)
        
        if verify_password(password, hashed):
            print("  ✓ Password hashing works")
            print("  ✓ Password verification works")
            return True
        else:
            print("  ✗ Password verification failed")
            return False
            
    except Exception as e:
        print(f"  ✗ Password hashing error: {e}")
        return False


def test_jwt():
    """Test JWT token generation and verification"""
    print("\n🎫 JWT Tokens:")
    
    try:
        from dashboard.auth import generate_token, verify_token
        
        token = generate_token("USR-test", "test@example.com", "driver")
        print(f"  ✓ Token generated")
        
        payload = verify_token(token)
        if payload and payload['user_id'] == "USR-test":
            print("  ✓ Token verification works")
            print(f"    Role: {payload['role']}")
            return True
        else:
            print("  ✗ Token verification failed")
            return False
            
    except Exception as e:
        print(f"  ✗ JWT error: {e}")
        return False


def main():
    """Run all verification checks"""
    checks = [
        ("Environment", check_environment),
        ("Files", check_files),
        ("Modules", check_modules),
        ("Database", check_database),
        ("Super Admin", check_superadmin),
        ("Password Hashing", test_password_hashing),
        ("JWT Tokens", test_jwt),
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n❌ Error in {name}: {e}")
            results[name] = False
    
    # Summary
    print("\n" + "="*60)
    print("📊 Verification Summary")
    print("="*60 + "\n")
    
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"\n✨ Score: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 All checks passed! Ready to deploy.\n")
        print("📚 Next steps:")
        print("  1. Start server: python main.py dashboard")
        print("  2. Run tests: python dashboard/test_auth.py")
        print("  3. Update frontend: see AUTHENTICATION_SETUP.md")
        print("\n📖 Documentation:")
        print("  - API Reference: dashboard/AUTH_API.md")
        print("  - Setup Guide: AUTHENTICATION_SETUP.md")
        print("  - Summary: AUTH_BACKEND_SUMMARY.md")
        return 0
    else:
        print("\n⚠️ Some checks failed. Please review errors above.")
        print("\n💡 Troubleshooting:")
        print("  1. Install packages: pip install -r requirements-slim.txt")
        print("  2. Check .env file is present")
        print("  3. Ensure you're in the project root directory")
        print("  4. Try deleting dashboard/livecold.db and rerun this script")
        return 1


if __name__ == "__main__":
    sys.exit(main())
