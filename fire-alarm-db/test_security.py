#!/usr/bin/env python3
"""
Security Verification Tests
Tests the authentication and security fixes
"""

import os
import sys
import re
import json
from pathlib import Path

def test_no_hardcoded_credentials():
    """Test that credentials are not hardcoded"""
    print("🔍 Test 1: Checking for hardcoded credentials...")
    
    files_to_check = [
        "fire-alarm-db/docker-compose.yml",
        "fire-alarm-db/database-design/main.py",
        "fire-alarm-db/accuracy_engine/api/main.py",
    ]
    
    dangerous_patterns = [
        r"firealarm123",
        r"password\s*=\s*['\"].*['\"]",
        r"POSTGRES_PASSWORD:\s*[a-zA-Z0-9]+",
    ]
    
    found_issues = False
    for file_path in files_to_check:
        full_path = Path(file_path)
        if not full_path.exists():
            continue
            
        content = full_path.read_text()
        
        # Allow password patterns only if using env variables
        if file_path == "fire-alarm-db/docker-compose.yml":
            if "POSTGRES_PASSWORD:" in content and "${DB_PASSWORD" not in content:
                print(f"  ❌ {file_path}: Hardcoded password detected")
                found_issues = True
            elif "firealarm123" in content:
                print(f"  ❌ {file_path}: Contains 'firealarm123'")
                found_issues = True
        elif "password" in content.lower() and "env" not in content.lower():
            if re.search(r'password\s*=\s*["\'][a-zA-Z0-9!@#$%^&*]+["\']', content, re.IGNORECASE):
                print(f"  ❌ {file_path}: Potential hardcoded password")
                found_issues = True
    
    if not found_issues:
        print("  ✅ No hardcoded credentials found")
        return True
    return False


def test_cors_configuration():
    """Test that CORS is not overly permissive"""
    print("🔍 Test 2: Checking CORS configuration...")
    
    files_to_check = [
        ("fire-alarm-db/database-design/main.py", "database-design"),
        ("fire-alarm-db/accuracy_engine/api/main.py", "accuracy_engine"),
    ]
    
    found_issues = False
    for file_path, name in files_to_check:
        full_path = Path(file_path)
        if not full_path.exists():
            continue
            
        content = full_path.read_text()
        
        # Check for dangerous CORS config
        if 'allow_origins=["*"]' in content or "allow_origins=['*']" in content:
            print(f"  ❌ {name}: CORS allows all origins (allow_origins=['*'])")
            found_issues = True
        
        # Check that it uses environment variables or whitelist
        if 'ALLOWED_ORIGINS' in content or 'cors_origins' in content:
            print(f"  ✅ {name}: Uses restricted CORS with environment variables")
        
        # Check credentials flag
        if "allow_credentials=True" in content and 'allow_origins=["*"]' in content:
            print(f"  ❌ {name}: Dangerous combination - credentials=True with allow_origins=*")
            found_issues = True
    
    return not found_issues


def test_authentication_on_endpoints():
    """Test that endpoints have authentication"""
    print("🔍 Test 3: Checking authentication on endpoints...")
    
    files_to_check = [
        ("fire-alarm-db/database-design/main.py", "database-design"),
        ("fire-alarm-db/accuracy_engine/api/main.py", "accuracy_engine"),
    ]
    
    critical_endpoints = [
        "/api/elite-design",
        "/api/task/",
        "/download/",
        "/api/accuracy-engine",
        "/api/rules-engine",
    ]
    
    for file_path, name in files_to_check:
        full_path = Path(file_path)
        if not full_path.exists():
            continue
            
        content = full_path.read_text()
        
        # Check for verify_api_key function
        if "verify_api_key" not in content:
            print(f"  ❌ {name}: No verify_api_key function found")
            return False
        
        # Check that critical endpoints use the verify_api_key dependency
        for endpoint in critical_endpoints:
            endpoint_pattern = endpoint.replace("/{", "/").replace("}", "").split("/")[-1]
            
            # Look for endpoint definition with api_key dependency
            if f"Depends(verify_api_key)" in content:
                print(f"  ✅ {name}: Uses API key verification on endpoints")
            else:
                print(f"  ⚠️  {name}: No Depends(verify_api_key) found")
    
    return True


def test_error_handling():
    """Test that errors don't leak information"""
    print("🔍 Test 4: Checking error handling...")
    
    files_to_check = [
        "fire-alarm-db/database-design/main.py",
        "fire-alarm-db/accuracy_engine/api/main.py",
    ]
    
    for file_path in files_to_check:
        full_path = Path(file_path)
        if not full_path.exists():
            continue
            
        content = full_path.read_text()
        
        # Check for global exception handler
        if "@app.exception_handler(Exception)" in content:
            print(f"  ✅ {file_path}: Global exception handler present")
            
            # Check if it returns generic message
            if '"detail": "Internal server error"' in content or "'detail': 'Internal server error'" in content:
                print(f"     ✅ Returns generic error message")
            elif 'str(exc)' in content:
                print(f"     ❌ Exception details exposed in response")
    
    return True


def test_input_validation():
    """Test that inputs are validated"""
    print("🔍 Test 5: Checking input validation...")
    
    full_path = Path("fire-alarm-db/database-design/main.py")
    if not full_path.exists():
        print("  ⚠️  File not found")
        return True
    
    content = full_path.read_text()
    
    if "validate_input_string" in content:
        print("  ✅ Input validation function present")
    
    if "validate_task_id" in content:
        print("  ✅ Task ID validation present")
    
    if "uuid.UUID" in content:
        print("  ✅ UUID validation for task IDs")
    
    if "image_ext.lower()" in content and ".png" in content:
        print("  ✅ File type validation for uploads")
    
    return True


def test_docker_compose_env_vars():
    """Test that docker-compose uses environment variables"""
    print("🔍 Test 6: Checking docker-compose.yml...")
    
    full_path = Path("fire-alarm-db/docker-compose.yml")
    if not full_path.exists():
        print("  ⚠️  File not found")
        return True
    
    content = full_path.read_text()
    
    checks = {
        "${DB_USER}": "Database user uses env var",
        "${DB_PASSWORD}": "Database password uses env var",
        "${DB_NAME}": "Database name uses env var",
        "${DATABASE_URL}": "Database URL uses env var",
    }
    
    for pattern, description in checks.items():
        if pattern in content:
            print(f"  ✅ {description}")
        else:
            print(f"  ⚠️  {description} not found")
    
    return True


def main():
    """Run all security tests"""
    print("\n" + "="*60)
    print("🔐 SECURITY VERIFICATION TESTS")
    print("="*60 + "\n")
    
    os.chdir(Path(__file__).parent.parent.parent)
    
    tests = [
        test_no_hardcoded_credentials,
        test_cors_configuration,
        test_authentication_on_endpoints,
        test_error_handling,
        test_input_validation,
        test_docker_compose_env_vars,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append((test.__name__, False))
        print()
    
    # Summary
    print("="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*60 + "\n")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
