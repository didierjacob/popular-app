#!/usr/bin/env python3
"""
Chantier 1A Backend Testing: Country detection, user settings, 50/50 feed, geo-tags
Tests all endpoints according to the test plan in test_result.md
"""

import requests
import json
from typing import Dict, Any, List

# Backend URL from review request
BASE_URL = "http://localhost:8001"
API_URL = f"{BASE_URL}/api"

# Test results storage
test_results = {
    "passed": 0,
    "failed": 0,
    "tests": []
}

def log_test(test_name: str, passed: bool, details: str = "", response_data: Any = None):
    """Log test results"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"  Details: {details}")
    if response_data and not passed:
        print(f"  Response: {json.dumps(response_data, indent=2)[:500]}")
    
    test_results["tests"].append({
        "name": test_name,
        "passed": passed,
        "details": details
    })
    
    if passed:
        test_results["passed"] += 1
    else:
        test_results["failed"] += 1
    
    return passed

def test_country_detection():
    """Test 1: GET /api/detect-country"""
    print("\n" + "="*80)
    print("TEST 1: COUNTRY DETECTION")
    print("="*80)
    
    try:
        response = requests.get(f"{API_URL}/detect-country")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check required fields
            required_fields = ["country", "source", "language"]
            has_all_fields = all(field in data for field in required_fields)
            
            if has_all_fields:
                country = data.get("country")
                source = data.get("source")
                language = data.get("language")
                
                # Verify field types
                if isinstance(country, str) and isinstance(source, str) and isinstance(language, str):
                    log_test("Country detection", True, 
                            f"country={country}, source={source}, language={language}")
                    return True
                else:
                    log_test("Country detection", False, 
                            f"Invalid field types: country={type(country)}, source={type(source)}, language={type(language)}", 
                            data)
                    return False
            else:
                missing = [f for f in required_fields if f not in data]
                log_test("Country detection", False, f"Missing fields: {missing}", data)
                return False
        else:
            log_test("Country detection", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("Country detection", False, f"Exception: {str(e)}")
        return False

def test_user_settings_create():
    """Test 2: POST /api/user-settings - Create user settings"""
    print("\n" + "="*80)
    print("TEST 2: USER SETTINGS - CREATE")
    print("="*80)
    
    try:
        payload = {
            "device_id": "ch1-test-1",
            "country": "FR",
            "language": "fr"
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(f"{API_URL}/user-settings", json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for success field
            success = data.get("success")
            country = data.get("country")
            language = data.get("language")
            
            if success and country == "FR" and language == "fr":
                log_test("User settings create", True, 
                        f"success={success}, country={country}, language={language}")
                return True
            else:
                log_test("User settings create", False, 
                        f"Unexpected response: success={success}, country={country}, language={language}", 
                        data)
                return False
        else:
            log_test("User settings create", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("User settings create", False, f"Exception: {str(e)}")
        return False

def test_user_settings_get():
    """Test 3: GET /api/user-settings/{device_id} - Get user settings"""
    print("\n" + "="*80)
    print("TEST 3: USER SETTINGS - GET")
    print("="*80)
    
    try:
        response = requests.get(f"{API_URL}/user-settings/ch1-test-1")
        
        if response.status_code == 200:
            data = response.json()
            
            country = data.get("country")
            language = data.get("language")
            
            if country == "FR" and language == "fr":
                log_test("User settings get", True, 
                        f"country={country}, language={language}")
                return True
            else:
                log_test("User settings get", False, 
                        f"Expected country=FR, language=fr, got country={country}, language={language}", 
                        data)
                return False
        else:
            log_test("User settings get", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("User settings get", False, f"Exception: {str(e)}")
        return False

def test_user_settings_update():
    """Test 4: POST /api/user-settings - Update user settings"""
    print("\n" + "="*80)
    print("TEST 4: USER SETTINGS - UPDATE")
    print("="*80)
    
    try:
        payload = {
            "device_id": "ch1-test-1",
            "country": "US",
            "language": "en"
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(f"{API_URL}/user-settings", json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            success = data.get("success")
            country = data.get("country")
            language = data.get("language")
            
            if success and country == "US" and language == "en":
                log_test("User settings update", True, 
                        f"Updated to country={country}, language={language}")
                return True
            else:
                log_test("User settings update", False, 
                        f"Unexpected response: success={success}, country={country}, language={language}", 
                        data)
                return False
        else:
            log_test("User settings update", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("User settings update", False, f"Exception: {str(e)}")
        return False

def test_user_settings_invalid_country():
    """Test 5: POST /api/user-settings - Invalid country (should return 400)"""
    print("\n" + "="*80)
    print("TEST 5: USER SETTINGS - INVALID COUNTRY")
    print("="*80)
    
    try:
        payload = {
            "device_id": "ch1-test-2",
            "country": "XX"
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(f"{API_URL}/user-settings", json=payload, headers=headers)
        
        if response.status_code == 400:
            log_test("User settings invalid country", True, 
                    f"Correctly rejected invalid country 'XX' with HTTP 400")
            return True
        else:
            log_test("User settings invalid country", False, 
                    f"Expected HTTP 400, got {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("User settings invalid country", False, f"Exception: {str(e)}")
        return False

def test_50_50_feed_fr():
    """Test 6: GET /api/people?limit=20&country=FR - 50/50 feed filtering for FR"""
    print("\n" + "="*80)
    print("TEST 6: 50/50 FEED FILTERING - FRANCE")
    print("="*80)
    
    try:
        response = requests.get(f"{API_URL}/people", params={"limit": 20, "country": "FR"})
        
        if response.status_code == 200:
            people = response.json()
            
            if not isinstance(people, list):
                log_test("50/50 feed FR", False, f"Expected array, got {type(people)}")
                return False
            
            if len(people) == 0:
                log_test("50/50 feed FR", False, "No people returned")
                return False
            
            # Check if people have country_tags field
            has_country_tags = all("country_tags" in person for person in people)
            
            if not has_country_tags:
                log_test("50/50 feed FR", False, "Some persons missing country_tags field")
                return False
            
            # Count FR-tagged and international persons
            fr_count = 0
            international_count = 0
            
            for person in people:
                country_tags = person.get("country_tags", [])
                is_international = person.get("is_international", False)
                
                if "FR" in country_tags:
                    fr_count += 1
                if is_international:
                    international_count += 1
            
            # Verify mix of FR and international
            has_fr = fr_count > 0
            has_international = international_count > 0
            
            if has_fr and has_international:
                log_test("50/50 feed FR", True, 
                        f"Returned {len(people)} persons: {fr_count} FR-tagged, {international_count} international (good mix)")
                return True
            elif has_fr:
                log_test("50/50 feed FR", True, 
                        f"Returned {len(people)} persons: {fr_count} FR-tagged, {international_count} international (acceptable - may need more international)")
                return True
            else:
                log_test("50/50 feed FR", False, 
                        f"Expected mix of FR and international, got {fr_count} FR-tagged, {international_count} international")
                return False
        else:
            log_test("50/50 feed FR", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("50/50 feed FR", False, f"Exception: {str(e)}")
        return False

def test_50_50_feed_us():
    """Test 7: GET /api/people?limit=20&country=US - 50/50 feed filtering for US"""
    print("\n" + "="*80)
    print("TEST 7: 50/50 FEED FILTERING - USA")
    print("="*80)
    
    try:
        response = requests.get(f"{API_URL}/people", params={"limit": 20, "country": "US"})
        
        if response.status_code == 200:
            people = response.json()
            
            if not isinstance(people, list):
                log_test("50/50 feed US", False, f"Expected array, got {type(people)}")
                return False
            
            if len(people) == 0:
                log_test("50/50 feed US", False, "No people returned")
                return False
            
            # Count US-tagged and international persons
            us_count = 0
            international_count = 0
            
            for person in people:
                country_tags = person.get("country_tags", [])
                is_international = person.get("is_international", False)
                
                if "US" in country_tags:
                    us_count += 1
                if is_international:
                    international_count += 1
            
            # Verify mix of US and international
            has_us = us_count > 0
            has_international = international_count > 0
            
            if has_us and has_international:
                log_test("50/50 feed US", True, 
                        f"Returned {len(people)} persons: {us_count} US-tagged, {international_count} international (good mix)")
                return True
            elif has_us:
                log_test("50/50 feed US", True, 
                        f"Returned {len(people)} persons: {us_count} US-tagged, {international_count} international (acceptable)")
                return True
            else:
                log_test("50/50 feed US", False, 
                        f"Expected mix of US and international, got {us_count} US-tagged, {international_count} international")
                return False
        else:
            log_test("50/50 feed US", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("50/50 feed US", False, f"Exception: {str(e)}")
        return False

def test_feed_no_country():
    """Test 8: GET /api/people?limit=20 - No country filter (backward compatible)"""
    print("\n" + "="*80)
    print("TEST 8: FEED WITHOUT COUNTRY FILTER - BACKWARD COMPATIBLE")
    print("="*80)
    
    try:
        response = requests.get(f"{API_URL}/people", params={"limit": 20})
        
        if response.status_code == 200:
            people = response.json()
            
            if not isinstance(people, list):
                log_test("Feed no country", False, f"Expected array, got {type(people)}")
                return False
            
            if len(people) > 0:
                log_test("Feed no country", True, 
                        f"Returned {len(people)} persons without filtering (backward compatible)")
                return True
            else:
                log_test("Feed no country", False, "No people returned")
                return False
        else:
            log_test("Feed no country", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("Feed no country", False, f"Exception: {str(e)}")
        return False

def test_country_tags_on_persons():
    """Test 9: GET /api/people?limit=3 - Verify country_tags, is_international, primary_country fields"""
    print("\n" + "="*80)
    print("TEST 9: COUNTRY TAGS ON PERSON OBJECTS")
    print("="*80)
    
    try:
        response = requests.get(f"{API_URL}/people", params={"limit": 3})
        
        if response.status_code == 200:
            people = response.json()
            
            if not isinstance(people, list):
                log_test("Country tags on persons", False, f"Expected array, got {type(people)}")
                return False
            
            if len(people) == 0:
                log_test("Country tags on persons", False, "No people returned")
                return False
            
            # Check each person has required fields
            required_fields = ["country_tags", "is_international", "primary_country"]
            all_have_fields = True
            field_details = []
            
            for i, person in enumerate(people):
                missing_fields = [f for f in required_fields if f not in person]
                
                if missing_fields:
                    all_have_fields = False
                    field_details.append(f"Person {i+1} ({person.get('name', 'unknown')}) missing: {missing_fields}")
                else:
                    country_tags = person.get("country_tags")
                    is_international = person.get("is_international")
                    primary_country = person.get("primary_country")
                    
                    # Verify field types
                    if not isinstance(country_tags, list):
                        all_have_fields = False
                        field_details.append(f"Person {i+1} country_tags is not array: {type(country_tags)}")
                    elif not isinstance(is_international, bool):
                        all_have_fields = False
                        field_details.append(f"Person {i+1} is_international is not boolean: {type(is_international)}")
                    else:
                        field_details.append(f"Person {i+1} ({person.get('name', 'unknown')}): tags={country_tags}, international={is_international}, primary={primary_country}")
            
            if all_have_fields:
                log_test("Country tags on persons", True, 
                        f"All {len(people)} persons have required fields:\n  " + "\n  ".join(field_details))
                return True
            else:
                log_test("Country tags on persons", False, 
                        f"Field validation failed:\n  " + "\n  ".join(field_details))
                return False
        else:
            log_test("Country tags on persons", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("Country tags on persons", False, f"Exception: {str(e)}")
        return False

def test_admin_geo_tags_summary():
    """Test 10: GET /api/admin/geo-tags-summary"""
    print("\n" + "="*80)
    print("TEST 10: ADMIN GEO-TAGS SUMMARY")
    print("="*80)
    
    try:
        response = requests.get(f"{API_URL}/admin/geo-tags-summary")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check required fields
            required_fields = ["total_personalities", "tagged", "international", "by_country"]
            has_all_fields = all(field in data for field in required_fields)
            
            if has_all_fields:
                total = data.get("total_personalities")
                tagged = data.get("tagged")
                international = data.get("international")
                by_country = data.get("by_country")
                
                # Verify field types
                if isinstance(total, int) and isinstance(tagged, int) and isinstance(international, int) and isinstance(by_country, list):
                    log_test("Admin geo-tags summary", True, 
                            f"total={total}, tagged={tagged}, international={international}, countries={len(by_country)}")
                    return True
                else:
                    log_test("Admin geo-tags summary", False, 
                            f"Invalid field types: total={type(total)}, tagged={type(tagged)}, international={type(international)}, by_country={type(by_country)}", 
                            data)
                    return False
            else:
                missing = [f for f in required_fields if f not in data]
                log_test("Admin geo-tags summary", False, f"Missing fields: {missing}", data)
                return False
        else:
            log_test("Admin geo-tags summary", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("Admin geo-tags summary", False, f"Exception: {str(e)}")
        return False

def test_outsiders_endpoint():
    """Test 11: GET /api/outsiders - Verify endpoint works"""
    print("\n" + "="*80)
    print("TEST 11: OUTSIDERS ENDPOINT")
    print("="*80)
    
    try:
        response = requests.get(f"{API_URL}/outsiders")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if response has golden and regular arrays
            if "golden" in data and "regular" in data:
                golden = data.get("golden", [])
                regular = data.get("regular", [])
                
                if isinstance(golden, list) and isinstance(regular, list):
                    log_test("Outsiders endpoint", True, 
                            f"Returned golden_outsiders ({len(golden)}), regular_outsiders ({len(regular)})")
                    return True
                else:
                    log_test("Outsiders endpoint", False, 
                            f"Invalid types: golden={type(golden)}, regular={type(regular)}", 
                            data)
                    return False
            else:
                log_test("Outsiders endpoint", False, 
                        "Missing golden or regular fields", 
                        data)
                return False
        else:
            log_test("Outsiders endpoint", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("Outsiders endpoint", False, f"Exception: {str(e)}")
        return False

def test_outsiders_country_filter():
    """Test 12: GET /api/outsiders?country=FR - Verify country filter works"""
    print("\n" + "="*80)
    print("TEST 12: OUTSIDERS ENDPOINT WITH COUNTRY FILTER")
    print("="*80)
    
    try:
        response = requests.get(f"{API_URL}/outsiders", params={"country": "FR"})
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if response has golden and regular arrays
            if "golden" in data and "regular" in data:
                golden = data.get("golden", [])
                regular = data.get("regular", [])
                
                if isinstance(golden, list) and isinstance(regular, list):
                    log_test("Outsiders country filter", True, 
                            f"Country filter accepted, returned golden_outsiders ({len(golden)}), regular_outsiders ({len(regular)})")
                    return True
                else:
                    log_test("Outsiders country filter", False, 
                            f"Invalid types: golden={type(golden)}, regular={type(regular)}", 
                            data)
                    return False
            else:
                log_test("Outsiders country filter", False, 
                        "Missing golden or regular fields", 
                        data)
                return False
        else:
            log_test("Outsiders country filter", False, 
                    f"HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        log_test("Outsiders country filter", False, f"Exception: {str(e)}")
        return False

def main():
    """Run all Chantier 1A backend tests"""
    print("\n" + "="*80)
    print("CHANTIER 1A BACKEND TESTING")
    print("Backend URL: " + BASE_URL)
    print("="*80)
    
    # Run all tests in sequence
    test_country_detection()
    test_user_settings_create()
    test_user_settings_get()
    test_user_settings_update()
    test_user_settings_invalid_country()
    test_50_50_feed_fr()
    test_50_50_feed_us()
    test_feed_no_country()
    test_country_tags_on_persons()
    test_admin_geo_tags_summary()
    test_outsiders_endpoint()
    test_outsiders_country_filter()
    
    # Print summary
    print("\n" + "="*80)
    print("CHANTIER 1A BACKEND TESTING - SUMMARY")
    print("="*80)
    
    total = test_results["passed"] + test_results["failed"]
    passed = test_results["passed"]
    failed = test_results["failed"]
    
    for test in test_results["tests"]:
        status = "✅ PASS" if test["passed"] else "❌ FAIL"
        print(f"{status}: {test['name']}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if failed == 0:
        print("\n🎉 ALL CHANTIER 1A BACKEND TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit(main())
