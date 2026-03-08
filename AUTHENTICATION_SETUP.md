# LiveCold Authentication Backend - Setup & Installation Guide

## Overview

The LiveCold authentication backend is a Flask-based JWT system that provides secure user registration and login for three roles:
- **Driver**: Vehicle operators monitoring cold chain shipments
- **Client**: Companies shipping perishable goods
- **Admin**: System administrators who activate users and manage platform

---

## Prerequisites

- **Python 3.11+**
- **pip** (Python package manager)
- **Virtual environment** (recommended)

---

## Installation Steps

### 1. Install Dependencies

Navigate to the project root and install the updated requirements:

```bash
cd Pathway-Hackathon
pip install -r requirements-slim.txt
```

**New packages added:**
- `flask-cors` - Enable cross-origin requests
- `pyjwt` - JWT token generation and validation
- `bcrypt` - Password hashing
- `cryptography` - Encryption support

### 2. Verify Database Setup

The database will auto-initialize on first run:

```bash
python -c "from dashboard.models import init_db; init_db()"
```

This creates `dashboard/livecold.db` with:
- `users` table
- `drivers` table
- `clients` table
- `admins` table
- `audit_log` table

### 3. Environment Configuration

The `.env` file has been updated with required variables:

```env
# Authentication
JWT_SECRET=livecold-secret-key-change-this-in-production
SUPER_ADMIN_EMAIL=admin@livecold.com
SUPER_ADMIN_PASSWORD=SuperAdmin@123

# MQTT
MQTT_HOST=localhost
MQTT_PORT=1883

# Flask
FLASK_ENV=development
FLASK_DEBUG=0
```

**⚠️ For Production:**
- Change `JWT_SECRET` to a strong random value
- Change `SUPER_ADMIN_PASSWORD` immediately after first login
- Set `FLASK_ENV=production`
- Set `FLASK_DEBUG=0`

### 4. Run the Dashboard Server

```bash
python main.py dashboard
```

The server will:
1. Initialize the database
2. Create super admin account
3. Start Flask on `http://localhost:5050`
4. Enable CORS for all routes
5. Register authentication endpoints

**Expected output:**
```
INFO [...] 🔑 Loaded 1 API key(s)
INFO [...] 📄 Loaded SOP document (XXXXX chars)
INFO [...] ⚠️ SuperAdmin initialized with email: admin@livecold.com
============================================================
🌐 LiveCold Dashboard
============================================================
📊 Dashboard: http://localhost:5050
📡 MQTT: localhost:1883
============================================================
```

---

## Quick Start Example

### 1. Admin Login

```bash
curl -X POST http://localhost:5050/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@livecold.com",
    "password": "SuperAdmin@123",
    "role": "admin"
  }'
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "role": "admin",
  "id": "USR-abc123",
  "name": "LiveCold Admin",
  "email": "admin@livecold.com"
}
```

### 2. Register Driver

```bash
curl -X POST http://localhost:5050/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "role": "driver",
    "name": "Rajesh Kumar",
    "email": "rajesh@example.com",
    "phone": "+91 9876543210",
    "password": "SecurePass@123",
    "vehicleId": "MH01AB1234",
    "licenseNo": "DL-1234567890123"
  }'
```

**Response:**
```json
{
  "message": "Registration successful. Your account will be activated after admin review.",
  "driverId": "DRV-abc123"
}
```

### 3. Verify Token

```bash
curl -X GET http://localhost:5050/api/auth/verify \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

---

## Testing

### Automated Tests

Run the comprehensive test suite:

```bash
python dashboard/test_auth.py
```

**Tests covered:**
- ✅ Driver registration
- ✅ Client registration  
- ✅ Duplicate email rejection
- ✅ Invalid password validation
- ✅ Missing fields validation
- ✅ Admin login
- ✅ Token verification
- ✅ Invalid token rejection
- ✅ Missing token rejection
- ✅ Invalid credentials rejection

### Manual Testing

Use the REST API documentation in [`dashboard/AUTH_API.md`](AUTH_API.md) for complete endpoint reference.

---

## Frontend Integration

### 1. Update login.jsx

Uncomment the production code in `frontend/src/components/login.jsx`:

```javascript
const res = await fetch("/api/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ role, identifier, password })  // ⚠️ Change "identifier" to "email"
});
```

**Fix required:** Change `identifier` to `email`:
```javascript
body: JSON.stringify({ role, email: identifier, password })
```

### 2. Update RegisterPage.jsx

Uncomment production code and update to match API spec (request field names).

### 3. Store Token

```javascript
if (data.token) {
  sessionStorage.setItem('livecold_token', data.token);
  sessionStorage.setItem('livecold_role', data.role);
  sessionStorage.setItem('livecold_id', data.id);
}
```

### 4. Use Token in API Calls

```javascript
const token = sessionStorage.getItem('livecold_token');
fetch('/api/shipments', {
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});
```

---

## Database Management

### View Database

SQLite database is stored at: `dashboard/livecold.db`

**Using SQLite CLI:**
```bash
sqlite3 dashboard/livecold.db
> .tables
> SELECT * FROM users;
> SELECT * FROM audit_log;
```

### Reset Database

Delete the database file and it will be recreated on next startup:

```bash
rm dashboard/livecold.db
```

### Backup Database

```bash
cp dashboard/livecold.db dashboard/livecold.db.backup
```

---

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'dashboard'`

**Solution:** Ensure you're running from the project root directory:
```bash
cd Pathway-Hackathon
python main.py dashboard
```

### Issue: `ImportError: cannot import name 'CORS' from 'flask'`

**Solution:** Install flask-cors:
```bash
pip install flask-cors
```

### Issue: Database is locked

**Solution:** Only one process can write to SQLite at a time. Ensure only one instance is running.

### Issue: Token verification failed

**Reasons:**
- Token expired (24 hours default)
- Invalid JWT_SECRET in .env
- Corrupted token

**Solution:** Re-login to get a new token.

### Issue: Database not created

**Solution:** Manually initialize:
```bash
python -c "from dashboard.models import init_db; init_db()"
```

---

## Security Checklist

- [ ] Change `JWT_SECRET` in `.env` to a strong random value
- [ ] Change `SUPER_ADMIN_PASSWORD` after first login
- [ ] Enable HTTPS in production
- [ ] Set `FLASK_ENV=production`
- [ ] Disable `FLASK_DEBUG`
- [ ] Use environment variables for all secrets
- [ ] Implement rate limiting on login endpoint
- [ ] Regular database backups
- [ ] Monitor `audit_log` table for suspicious activity
- [ ] Use strong passwords (min 8 chars, uppercase, digit, special char)

---

## API Endpoints Summary

| Method | Endpoint | Auth Required | Description |
|--------|----------|---|-------------|
| POST | `/api/auth/login` | ❌ | Login user |
| POST | `/api/auth/register` | ❌ | Register new user |
| GET | `/api/auth/verify` | ✅ | Verify token |
| POST | `/api/auth/logout` | ✅ | Logout user |

**✅ = Bearer token required**

---

## File Structure

```
dashboard/
├── __init__.py              # Package initialization
├── app.py                   # Main Flask app
├── models.py                # Database models & queries
├── auth.py                  # JWT & password utilities
├── auth_routes.py           # Authentication endpoints
├── test_auth.py             # Test suite
├── AUTH_API.md              # API documentation
├── livecold.db              # SQLite database (auto-created)
├── templates/
│   └── index.html           # Dashboard UI
└── static/                  # Static assets
```

---

## Next Steps

1. ✅ Install dependencies
2. ✅ Verify `.env` configuration
3. ✅ Start the server: `python main.py dashboard`
4. ✅ Run tests: `python dashboard/test_auth.py`
5. ✅ Update frontend to use production API calls
6. ✅ Deploy to production with secured credentials

---

## Support & Resources

- **API Documentation:** [`dashboard/AUTH_API.md`](AUTH_API.md)
- **Test Suite:** `python dashboard/test_auth.py`
- **Database Schema:** See models.py
- **JWT Implementation:** See auth.py

For issues, check the audit log:
```bash
sqlite3 dashboard/livecold.db "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 10;"
```
