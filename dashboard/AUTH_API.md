# LiveCold Authentication API Documentation

## Overview
Complete JWT-based authentication system with role-based access control for LiveCold platform. Supports three roles: `driver`, `client` (company), and `admin`.

---

## Authentication Flow

### 1. Registration
User creates account → Account created with `is_active=false` → Admin activation required → User can login

### 2. Login
User submits email + password → Credentials verified → JWT token issued → Token used for subsequent requests

### 3. Protected Routes
Include token in `Authorization: Bearer <token>` header on all protected endpoints

---

## Endpoints

### POST `/api/auth/login`

**Purpose:** Authenticate user and obtain JWT token

**Request Headers:**
```
Content-Type: application/json
```

**Request Body:**
```json
{
  "email": "driver@example.com",
  "password": "SecretPass1!",
  "role": "driver"          // "driver" | "client" | "admin"
}
```

**Success Response (200):**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "role": "driver",
  "id": "USR-abc123def456",
  "name": "Rajesh Kumar",
  "email": "driver@example.com",
  "driverId": "DRV-xyz789"           // For driver role
}
```

**Error Responses:**

Invalid credentials (401):
```json
{ "message": "Invalid credentials" }
```

Account not activated (403):
```json
{ "message": "Account is inactive. Please wait for admin approval or contact support." }
```

---

### POST `/api/auth/register`

**Purpose:** Create new user account (driver or client)

**Request Headers:**
```
Content-Type: application/json
```

**Request Body - Driver:**
```json
{
  "role": "driver",
  "name": "Rajesh Kumar",
  "email": "rajesh@example.com",
  "phone": "+91 98765 43210",
  "password": "SecretPass1!",
  "vehicleId": "HR 26DQ5551",
  "licenseNo": "DL-1234567890123"    // optional
}
```

**Request Body - Client (Company):**
```json
{
  "role": "client",
  "name": "Company Admin",
  "email": "admin@agrofreeze.com",
  "phone": "+91 98765 43210",
  "password": "SecretPass1!",
  "companyName": "AgroFreeze Pvt Ltd",
  "gstNo": "22AAAAA0000A1Z5",        // optional
  "city": "Delhi"                    // optional
}
```

**Success Response (201):**
```json
{
  "message": "Registration successful. Your account will be activated after admin review.",
  "driverId": "DRV-xyz789"           // For driver role
}
```

OR

```json
{
  "message": "Registration successful. Awaiting admin activation.",
  "clientId": "CLT-abc123"           // For client role
}
```

**Error Responses:**

Email already registered (409):
```json
{ "message": "Email already registered" }
```

Invalid password (400):
```json
{ "message": "Password must contain at least one special character (!@#$%^&*)" }
```

Missing required fields (400):
```json
{ "message": "role, name, email, phone, and password are required" }
```

---

### GET `/api/auth/verify`

**Purpose:** Verify token validity and get user info

**Request Headers:**
```
Authorization: Bearer <token>
Content-Type: application/json
```

**Success Response (200):**
```json
{
  "valid": true,
  "user_id": "USR-abc123",
  "email": "driver@example.com",
  "role": "driver",
  "exp": 1234567890
}
```

**Error Response (401):**
```json
{ "message": "Unauthorized - invalid or expired token" }
```

---

### POST `/api/auth/logout`

**Purpose:** Log out user (mainly for frontend cleanup)

**Request Headers:**
```
Authorization: Bearer <token>
```

**Success Response (200):**
```json
{ "message": "Logged out successfully" }
```

---

## Password Requirements

Passwords must meet the following criteria:
- ✅ Minimum 8 characters
- ✅ At least one uppercase letter (A-Z)
- ✅ At least one digit (0-9)
- ✅ At least one special character (!@#$%^&*)

**Example Valid Passwords:**
- `SecurePass123!`
- `Driver@2024`
- `AgroFreeze#456`

---

## JWT Token Structure

Tokens are valid for **24 hours** by default. Include in all subsequent requests:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Token contains:
- `user_id`: Unique user identifier
- `email`: User email
- `role`: User role (driver/client/admin)
- `iat`: Issued at timestamp
- `exp`: Expiration timestamp

---

## Role-Based Access Control

### Driver Role
- View own shipments and tracking
- Update delivery status
- Access notifications
- Upload delivery proofs

### Client (Company) Role
- Manage company profile
- Create and manage shipments
- View fleet analytics
- Invoice management

### Admin Role
- Activate/deactivate users
- View audit logs
- System configuration
- Generate reports

---

## Error Codes & Messages

| Status | Code | Message | Action |
|--------|------|---------|--------|
| 400 | Bad Request | Missing required fields | Check JSON payload |
| 401 | Unauthorized | Invalid credentials | Verify email/password |
| 401 | Unauthorized | Invalid or expired token | Refresh/re-login |
| 403 | Forbidden | Account is inactive | Wait for admin activation |
| 409 | Conflict | Email already registered | Use different email |
| 500 | Server Error | Failed to create user | Contact support |

---

## Implementation Example (JavaScript/React)

### Login
```javascript
async function login(email, password, role) {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, role })
  });
  
  if (response.ok) {
    const data = await response.json();
    sessionStorage.setItem('livecold_token', data.token);
    sessionStorage.setItem('livecold_role', data.role);
    sessionStorage.setItem('livecold_id', data.id);
    return data;
  } else {
    throw new Error((await response.json()).message);
  }
}
```

### Protected API Call
```javascript
async function fetchUserData() {
  const token = sessionStorage.getItem('livecold_token');
  const response = await fetch('/api/shipments', {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  return response.json();
}
```

### Verify Token
```javascript
async function verifyToken() {
  const token = sessionStorage.getItem('livecold_token');
  const response = await fetch('/api/auth/verify', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.ok;
}
```

---

## Environment Variables

Create a `.env` file in the project root:

```env
# Authentication
JWT_SECRET=your-secret-key-change-this-in-production
SUPER_ADMIN_EMAIL=admin@livecold.com
SUPER_ADMIN_PASSWORD=SuperAdmin@123

# CORS (if needed)
CORS_ORIGIN=http://localhost:5050

# Database
# SQLite database file: dashboard/livecold.db
```

---

## Database Schema

### users
```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,              -- USR-xxxxx
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,      -- bcrypt hash
  role TEXT NOT NULL,               -- driver | client | admin
  name TEXT NOT NULL,
  phone TEXT,
  is_active BOOLEAN DEFAULT false,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

### drivers
```sql
CREATE TABLE drivers (
  id TEXT PRIMARY KEY,              -- DRV-xxxxx
  user_id TEXT UNIQUE NOT NULL,
  vehicle_id TEXT NOT NULL,
  license_no TEXT,
  status TEXT DEFAULT 'inactive',   -- active | inactive | suspended
  created_at TIMESTAMP
);
```

### clients
```sql
CREATE TABLE clients (
  id TEXT PRIMARY KEY,              -- CLT-xxxxx
  user_id TEXT UNIQUE NOT NULL,
  company_name TEXT NOT NULL,
  gst_no TEXT,
  city TEXT,
  status TEXT DEFAULT 'pending_approval', -- active | pending_approval | suspended
  created_at TIMESTAMP
);
```

### admins
```sql
CREATE TABLE admins (
  id TEXT PRIMARY KEY,              -- ADM-xxxxx
  user_id TEXT UNIQUE NOT NULL,
  permission_level TEXT DEFAULT 'standard', -- standard | super
  created_at TIMESTAMP
);
```

### audit_log
```sql
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  user_id TEXT,
  action TEXT,                      -- login | logout | registration | etc
  resource TEXT,                    -- auth | shipment | profile | etc
  timestamp TIMESTAMP,
  details TEXT                      -- JSON details
);
```

---

## SuperAdmin Setup

On first deployment, a super admin account is automatically created with credentials from environment variables:

```env
SUPER_ADMIN_EMAIL=admin@livecold.com
SUPER_ADMIN_PASSWORD=SuperAdmin@123
```

**⚠️ IMPORTANT:** Change these credentials immediately in production!

---

## Security Notes

1. **HTTPS Required:** Always use HTTPS in production
2. **Token Storage:** Store JWT tokens securely (httpOnly cookies preferred)
3. **Password Hashing:** Passwords are hashed with bcrypt (10 rounds)
4. **Rate Limiting:** Implement rate limiting on login attempts
5. **CORS:** Configure CORS appropriately for your domain
6. **Secret Key:** Change `JWT_SECRET` in production

---

## Testing

Use curl:

```bash
# Register
curl -X POST http://localhost:5050/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "role": "driver",
    "name": "Test Driver",
    "email": "test@example.com",
    "phone": "+91 98765 43210",
    "password": "TestPass@123",
    "vehicleId": "MH01AB1234"
  }'

# Login
TOKEN=$(curl -X POST http://localhost:5050/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass@123",
    "role": "driver"
  }' | jq -r '.token')

# Verify
curl -X GET http://localhost:5050/api/auth/verify \
  -H "Authorization: Bearer $TOKEN"
```

---

## Support

For issues or questions:
- Check audit logs in `dashboard/livecold.db`
- Enable Flask debug logging: `FLASK_DEBUG=1`
- Review SQL errors in console output
