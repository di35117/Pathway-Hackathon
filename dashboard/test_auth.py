"""
LiveCold Authentication System Tests
Test login, registration, and token verification
"""

import requests
import json
import time

BASE_URL = "http://localhost:5050"

# Test data
test_driver = {
    "role": "driver",
    "name": "Test Driver",
    "email": "testdriver@example.com",
    "phone": "+91 9876543210",
    "password": "TestPass@123",
    "vehicleId": "MH01AB1234",
    "licenseNo": "DL-1234567890123"
}

test_client = {
    "role": "client",
    "name": "Test Company Admin",
    "email": "testclient@example.com",
    "phone": "+91 9876543210",
    "password": "TestPass@123",
    "companyName": "Test Company Ltd",
    "gstNo": "22AAAAA0000A1Z5",
    "city": "Delhi"
}


def test_driver_registration():
    """Test driver registration"""
    print("\n📝 Testing Driver Registration...")
    response = requests.post(f"{BASE_URL}/api/auth/register", json=test_driver)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 201


def test_client_registration():
    """Test client registration"""
    print("\n📝 Testing Client Registration...")
    response = requests.post(f"{BASE_URL}/api/auth/register", json=test_client)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 201


def test_duplicate_email():
    """Test duplicate email rejection"""
    print("\n🔄 Testing Duplicate Email Registration...")
    # First registration should succeed
    requests.post(f"{BASE_URL}/api/auth/register", json=test_driver)
    
    # Second registration with same email should fail
    response = requests.post(f"{BASE_URL}/api/auth/register", json=test_driver)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 409


def test_invalid_password():
    """Test weak password rejection"""
    print("\n🔐 Testing Invalid Password...")
    invalid_user = test_driver.copy()
    invalid_user["email"] = f"test-weak-{int(time.time())}@example.com"
    invalid_user["password"] = "weak"  # Too weak
    
    response = requests.post(f"{BASE_URL}/api/auth/register", json=invalid_user)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 400


def test_missing_fields():
    """Test missing required fields"""
    print("\n⚠️ Testing Missing Fields...")
    incomplete_user = {
        "role": "driver",
        "name": "Incomplete User"
        # Missing email, phone, password, vehicleId
    }
    
    response = requests.post(f"{BASE_URL}/api/auth/register", json=incomplete_user)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 400


def test_admin_login():
    """Test admin login (should work with default credentials)"""
    print("\n🔑 Testing Admin Login...")
    login_data = {
        "email": "admin@livecold.com",
        "password": "SuperAdmin@123",
        "role": "admin"
    }
    
    response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    if response.status_code == 200:
        token = response.json().get("token")
        return token
    return None


def test_token_verification(token):
    """Test token verification"""
    print("\n✅ Testing Token Verification...")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.get(f"{BASE_URL}/api/auth/verify", headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200


def test_invalid_token():
    """Test invalid token rejection"""
    print("\n❌ Testing Invalid Token...")
    headers = {
        "Authorization": "Bearer invalid_token_123",
        "Content-Type": "application/json"
    }
    
    response = requests.get(f"{BASE_URL}/api/auth/verify", headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 401


def test_missing_token():
    """Test missing token"""
    print("\n🚫 Testing Missing Token...")
    response = requests.get(f"{BASE_URL}/api/auth/verify")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 401


def test_invalid_credentials():
    """Test invalid login credentials"""
    print("\n🔐 Testing Invalid Login Credentials...")
    login_data = {
        "email": "admin@livecold.com",
        "password": "WrongPassword123!",
        "role": "admin"
    }
    
    response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 401


def run_all_tests():
    """Run all authentication tests"""
    print("=" * 60)
    print("🧪 LiveCold Authentication Tests")
    print("=" * 60)
    
    results = {}
    
    # Registration tests
    results["driver_registration"] = test_driver_registration()
    results["client_registration"] = test_client_registration()
    results["invalid_password"] = test_invalid_password()
    results["missing_fields"] = test_missing_fields()
    results["invalid_credentials"] = test_invalid_credentials()
    
    # Token tests
    admin_token = test_admin_login()
    if admin_token:
        results["token_verification"] = test_token_verification(admin_token)
    
    results["invalid_token"] = test_invalid_token()
    results["missing_token"] = test_missing_token()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n📈 Total: {passed}/{total} tests passed")
    print("=" * 60)


if __name__ == "__main__":
    print("⏳ Make sure the LiveCold server is running on http://localhost:5050")
    input("Press Enter to start tests...")
    run_all_tests()
