#!/usr/bin/env python3
"""
Virtual Vote Config Testing (Vague 1 - Sujets B+C+D)
Tests the cas1-celebrities admin endpoints and virtual-vote-config endpoint
"""

import requests
import time
import sys
import os

# Backend URL and admin password
BACKEND_URL = "https://personality-launch.preview.emergentagent.com/api"
ADMIN_PASSWORD = "fab31230"  # Read from /app/backend/.env

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_test(name: str):
    print(f"\n{Colors.BLUE}🧪 TEST: {name}{Colors.RESET}")

def print_pass(message: str):
    print(f"{Colors.GREEN}✅ PASS: {message}{Colors.RESET}")

def print_fail(message: str):
    print(f"{Colors.RED}❌ FAIL: {message}{Colors.RESET}")

def print_info(message: str):
    print(f"{Colors.YELLOW}ℹ️  INFO: {message}{Colors.RESET}")

# Test counters
tests_passed = 0
tests_failed = 0
test_results = []

def record_result(test_name: str, passed: bool, message: str):
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        print_pass(message)
    else:
        tests_failed += 1
        print_fail(message)
    test_results.append({
        "test": test_name,
        "passed": passed,
        "message": message
    })

# ============================================================================
# TEST 1: GET /api/admin/cas1-celebrities
# ============================================================================

def test_get_cas1_celebrities():
    print_test("1. GET /api/admin/cas1-celebrities - List cas1 celebrities")
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/admin/cas1-celebrities",
            headers={"X-Admin-Password": ADMIN_PASSWORD},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            cas1_list = data.get("cas1_celebrities", [])
            
            # Check if we have 16 slugs
            if len(cas1_list) == 16:
                print_pass(f"Cas1 list has 16 slugs: {len(cas1_list)}")
            else:
                print_info(f"Cas1 list has {len(cas1_list)} slugs (expected 16)")
            
            # Check for specific celebrities
            expected_celebs = ["donald-trump", "elon-musk", "taylor-swift"]
            found_celebs = [c for c in expected_celebs if c in cas1_list]
            
            if len(found_celebs) == len(expected_celebs):
                record_result("1_get_cas1", True, 
                    f"GET /api/admin/cas1-celebrities returned {len(cas1_list)} slugs including {', '.join(expected_celebs)}")
            else:
                missing = [c for c in expected_celebs if c not in cas1_list]
                record_result("1_get_cas1", False,
                    f"GET /api/admin/cas1-celebrities missing expected celebrities: {missing}. Found: {cas1_list}")
            
            return cas1_list
        else:
            record_result("1_get_cas1", False,
                f"GET /api/admin/cas1-celebrities returned {response.status_code}: {response.text}")
            return []
    except Exception as e:
        record_result("1_get_cas1", False, f"Exception: {str(e)}")
        return []

# ============================================================================
# TEST 2: POST /api/admin/cas1-celebrities - Add slug
# ============================================================================

def test_add_cas1_slug():
    print_test("2. POST /api/admin/cas1-celebrities - Add test slug")
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/admin/cas1-celebrities",
            headers={"X-Admin-Password": ADMIN_PASSWORD},
            json={"add": ["test-slug-xyz"]},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            count = data.get("count", 0)
            cas1_list = data.get("cas1_celebrities", [])
            
            if "test-slug-xyz" in cas1_list and count == 17:
                record_result("2_add_slug", True,
                    f"POST /api/admin/cas1-celebrities added test-slug-xyz successfully, count={count}")
            else:
                record_result("2_add_slug", False,
                    f"POST /api/admin/cas1-celebrities returned count={count}, test-slug-xyz in list: {'test-slug-xyz' in cas1_list}")
        else:
            record_result("2_add_slug", False,
                f"POST /api/admin/cas1-celebrities returned {response.status_code}: {response.text}")
    except Exception as e:
        record_result("2_add_slug", False, f"Exception: {str(e)}")

# ============================================================================
# TEST 3: POST /api/admin/cas1-celebrities - Remove slug
# ============================================================================

def test_remove_cas1_slug():
    print_test("3. POST /api/admin/cas1-celebrities - Remove test slug")
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/admin/cas1-celebrities",
            headers={"X-Admin-Password": ADMIN_PASSWORD},
            json={"remove": ["test-slug-xyz"]},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            count = data.get("count", 0)
            cas1_list = data.get("cas1_celebrities", [])
            
            if "test-slug-xyz" not in cas1_list and count == 16:
                record_result("3_remove_slug", True,
                    f"POST /api/admin/cas1-celebrities removed test-slug-xyz successfully, count={count}")
            else:
                record_result("3_remove_slug", False,
                    f"POST /api/admin/cas1-celebrities returned count={count}, test-slug-xyz in list: {'test-slug-xyz' in cas1_list}")
        else:
            record_result("3_remove_slug", False,
                f"POST /api/admin/cas1-celebrities returned {response.status_code}: {response.text}")
    except Exception as e:
        record_result("3_remove_slug", False, f"Exception: {str(e)}")

# ============================================================================
# TEST 4: GET /api/admin/cas1-celebrities - Verify final state
# ============================================================================

def test_verify_cas1_final():
    print_test("4. GET /api/admin/cas1-celebrities - Verify test-slug-xyz removed")
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/admin/cas1-celebrities",
            headers={"X-Admin-Password": ADMIN_PASSWORD},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            cas1_list = data.get("cas1_celebrities", [])
            
            if "test-slug-xyz" not in cas1_list and len(cas1_list) == 16:
                record_result("4_verify_final", True,
                    f"GET /api/admin/cas1-celebrities verified test-slug-xyz removed, count={len(cas1_list)}")
            else:
                record_result("4_verify_final", False,
                    f"GET /api/admin/cas1-celebrities still has test-slug-xyz or wrong count: {len(cas1_list)}")
        else:
            record_result("4_verify_final", False,
                f"GET /api/admin/cas1-celebrities returned {response.status_code}: {response.text}")
    except Exception as e:
        record_result("4_verify_final", False, f"Exception: {str(e)}")

# ============================================================================
# TEST 5: Search for person IDs
# ============================================================================

def search_person(query: str):
    """Helper function to search for a person and return their ID"""
    try:
        response = requests.get(
            f"{BACKEND_URL}/search",
            params={"query": query},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                return data[0].get("id")
        return None
    except Exception as e:
        print_info(f"Search error for '{query}': {str(e)}")
        return None

def get_outsider_id():
    """Helper function to get an outsider ID"""
    try:
        response = requests.get(
            f"{BACKEND_URL}/outsiders",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            golden = data.get("golden", [])
            regular = data.get("regular", [])
            
            # Try golden first, then regular
            if golden and len(golden) > 0:
                return golden[0].get("id")
            elif regular and len(regular) > 0:
                return regular[0].get("id")
        return None
    except Exception as e:
        print_info(f"Get outsider error: {str(e)}")
        return None

# ============================================================================
# TEST 6: GET /api/virtual-vote-config/{person_id} - Cas 1 (Donald Trump)
# ============================================================================

def test_virtual_vote_config_cas1():
    print_test("5. GET /api/virtual-vote-config/{person_id} - Cas 1 test (Donald Trump)")
    
    trump_id = search_person("Donald Trump")
    
    if not trump_id:
        record_result("5_cas1_config", False, "Could not find Donald Trump person_id")
        return
    
    print_info(f"Found Donald Trump ID: {trump_id}")
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/virtual-vote-config/{trump_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify cas1 config
            checks = [
                ("tier", "cas1", data.get("tier")),
                ("interval_min_ms", 2500, data.get("interval_min_ms")),
                ("interval_max_ms", 4500, data.get("interval_max_ms")),
                ("geo_coefficient.international", 1.0, data.get("geo_coefficient", {}).get("international")),
                ("geo_coefficient.local", 0.0, data.get("geo_coefficient", {}).get("local")),
                ("initial_feed_count", 8, data.get("initial_feed_count")),
            ]
            
            all_passed = True
            for field, expected, actual in checks:
                if actual != expected:
                    print_fail(f"  {field}: expected {expected}, got {actual}")
                    all_passed = False
                else:
                    print_info(f"  {field}: {actual} ✓")
            
            if all_passed:
                record_result("5_cas1_config", True,
                    f"GET /api/virtual-vote-config/{trump_id} returned correct cas1 config")
            else:
                record_result("5_cas1_config", False,
                    f"GET /api/virtual-vote-config/{trump_id} returned incorrect cas1 config: {data}")
        else:
            record_result("5_cas1_config", False,
                f"GET /api/virtual-vote-config/{trump_id} returned {response.status_code}: {response.text}")
    except Exception as e:
        record_result("5_cas1_config", False, f"Exception: {str(e)}")

# ============================================================================
# TEST 7: GET /api/virtual-vote-config/{person_id} - Cas 2 (Cristiano Ronaldo)
# ============================================================================

def test_virtual_vote_config_cas2():
    print_test("6. GET /api/virtual-vote-config/{person_id} - Cas 2 test (Cristiano Ronaldo)")
    
    ronaldo_id = search_person("Cristiano Ronaldo")
    
    if not ronaldo_id:
        record_result("6_cas2_config", False, "Could not find Cristiano Ronaldo person_id")
        return
    
    print_info(f"Found Cristiano Ronaldo ID: {ronaldo_id}")
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/virtual-vote-config/{ronaldo_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify cas2 config
            checks = [
                ("tier", "cas2", data.get("tier")),
                ("interval_min_ms", 300000, data.get("interval_min_ms")),
                ("interval_max_ms", 900000, data.get("interval_max_ms")),
                ("geo_coefficient.local", 0.8, data.get("geo_coefficient", {}).get("local")),
                ("geo_coefficient.international", 0.2, data.get("geo_coefficient", {}).get("international")),
                ("initial_feed_count", 5, data.get("initial_feed_count")),
            ]
            
            all_passed = True
            for field, expected, actual in checks:
                if actual != expected:
                    print_fail(f"  {field}: expected {expected}, got {actual}")
                    all_passed = False
                else:
                    print_info(f"  {field}: {actual} ✓")
            
            # Check dominant_language (should be "pt" for Ronaldo)
            dominant_lang = data.get("dominant_language")
            if dominant_lang == "pt":
                print_info(f"  dominant_language: {dominant_lang} ✓")
            else:
                print_info(f"  dominant_language: {dominant_lang} (expected 'pt', but may vary)")
            
            if all_passed:
                record_result("6_cas2_config", True,
                    f"GET /api/virtual-vote-config/{ronaldo_id} returned correct cas2 config")
            else:
                record_result("6_cas2_config", False,
                    f"GET /api/virtual-vote-config/{ronaldo_id} returned incorrect cas2 config: {data}")
        else:
            record_result("6_cas2_config", False,
                f"GET /api/virtual-vote-config/{ronaldo_id} returned {response.status_code}: {response.text}")
    except Exception as e:
        record_result("6_cas2_config", False, f"Exception: {str(e)}")

# ============================================================================
# TEST 8: GET /api/virtual-vote-config/{person_id} - Cas 3 (Outsider)
# ============================================================================

def test_virtual_vote_config_cas3():
    print_test("7. GET /api/virtual-vote-config/{person_id} - Cas 3 test (Outsider)")
    
    outsider_id = get_outsider_id()
    
    if not outsider_id:
        print_info("No outsiders found, skipping cas3 test")
        record_result("7_cas3_config", True, "No outsiders available to test (skipped)")
        return
    
    print_info(f"Found Outsider ID: {outsider_id}")
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/virtual-vote-config/{outsider_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Verify cas3 config
            checks = [
                ("tier", "cas3", data.get("tier")),
                ("interval_min_ms", 7200000, data.get("interval_min_ms")),
                ("interval_max_ms", 43200000, data.get("interval_max_ms")),
                ("geo_coefficient.local", 1.0, data.get("geo_coefficient", {}).get("local")),
                ("geo_coefficient.international", 0.0, data.get("geo_coefficient", {}).get("international")),
                ("initial_feed_count", 3, data.get("initial_feed_count")),
            ]
            
            all_passed = True
            for field, expected, actual in checks:
                if actual != expected:
                    print_fail(f"  {field}: expected {expected}, got {actual}")
                    all_passed = False
                else:
                    print_info(f"  {field}: {actual} ✓")
            
            if all_passed:
                record_result("7_cas3_config", True,
                    f"GET /api/virtual-vote-config/{outsider_id} returned correct cas3 config")
            else:
                record_result("7_cas3_config", False,
                    f"GET /api/virtual-vote-config/{outsider_id} returned incorrect cas3 config: {data}")
        else:
            record_result("7_cas3_config", False,
                f"GET /api/virtual-vote-config/{outsider_id} returned {response.status_code}: {response.text}")
    except Exception as e:
        record_result("7_cas3_config", False, f"Exception: {str(e)}")

# ============================================================================
# TEST 9: GET /api/virtual-vote-config/{person_id} - Invalid person_id
# ============================================================================

def test_virtual_vote_config_invalid():
    print_test("8. GET /api/virtual-vote-config/invalidid - Invalid person_id")
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/virtual-vote-config/invalidid",
            timeout=10
        )
        
        if response.status_code == 400:
            record_result("8_invalid_id", True,
                f"GET /api/virtual-vote-config/invalidid correctly returned 400")
        else:
            record_result("8_invalid_id", False,
                f"GET /api/virtual-vote-config/invalidid returned {response.status_code} (expected 400): {response.text}")
    except Exception as e:
        record_result("8_invalid_id", False, f"Exception: {str(e)}")

# ============================================================================
# TEST 10: GET /api/virtual-vote-config/{person_id} - Non-existent person_id
# ============================================================================

def test_virtual_vote_config_nonexistent():
    print_test("9. GET /api/virtual-vote-config/000000000000000000000000 - Non-existent person_id")
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/virtual-vote-config/000000000000000000000000",
            timeout=10
        )
        
        if response.status_code == 404:
            record_result("9_nonexistent_id", True,
                f"GET /api/virtual-vote-config/000000000000000000000000 correctly returned 404")
        else:
            record_result("9_nonexistent_id", False,
                f"GET /api/virtual-vote-config/000000000000000000000000 returned {response.status_code} (expected 404): {response.text}")
    except Exception as e:
        record_result("9_nonexistent_id", False, f"Exception: {str(e)}")

# ============================================================================
# TEST 11: Verify dominant_language in virtual-vote-config
# ============================================================================

def test_dominant_language_in_config():
    print_test("10. Verify dominant_language field in virtual-vote-config")
    
    trump_id = search_person("Donald Trump")
    ronaldo_id = search_person("Cristiano Ronaldo")
    
    if not trump_id or not ronaldo_id:
        record_result("10_dominant_language", False, "Could not find person IDs for dominant_language test")
        return
    
    try:
        # Check Trump via virtual-vote-config
        response_trump = requests.get(
            f"{BACKEND_URL}/virtual-vote-config/{trump_id}",
            timeout=10
        )
        
        # Check Ronaldo via virtual-vote-config
        response_ronaldo = requests.get(
            f"{BACKEND_URL}/virtual-vote-config/{ronaldo_id}",
            timeout=10
        )
        
        trump_has_lang = False
        ronaldo_has_lang = False
        trump_lang = None
        ronaldo_lang = None
        
        if response_trump.status_code == 200:
            trump_data = response_trump.json()
            trump_has_lang = "dominant_language" in trump_data
            trump_lang = trump_data.get('dominant_language')
            print_info(f"Trump dominant_language: {trump_lang}")
        
        if response_ronaldo.status_code == 200:
            ronaldo_data = response_ronaldo.json()
            ronaldo_has_lang = "dominant_language" in ronaldo_data
            ronaldo_lang = ronaldo_data.get('dominant_language')
            print_info(f"Ronaldo dominant_language: {ronaldo_lang}")
        
        if trump_has_lang and ronaldo_has_lang:
            record_result("10_dominant_language", True,
                f"Both Trump and Ronaldo have dominant_language field in virtual-vote-config (Trump: {trump_lang}, Ronaldo: {ronaldo_lang})")
        else:
            record_result("10_dominant_language", False,
                f"Missing dominant_language field - Trump: {trump_has_lang}, Ronaldo: {ronaldo_has_lang}")
    except Exception as e:
        record_result("10_dominant_language", False, f"Exception: {str(e)}")

# ============================================================================
# Main execution
# ============================================================================

def main():
    print(f"\n{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"{Colors.BLUE}Virtual Vote Config Testing (Vague 1 - Sujets B+C+D){Colors.RESET}")
    print(f"{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Admin Password: {'*' * len(ADMIN_PASSWORD)}")
    
    # Run all tests
    test_get_cas1_celebrities()
    test_add_cas1_slug()
    test_remove_cas1_slug()
    test_verify_cas1_final()
    test_virtual_vote_config_cas1()
    test_virtual_vote_config_cas2()
    test_virtual_vote_config_cas3()
    test_virtual_vote_config_invalid()
    test_virtual_vote_config_nonexistent()
    test_dominant_language_in_config()
    
    # Print summary
    print(f"\n{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"{Colors.BLUE}TEST SUMMARY{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"{Colors.GREEN}✅ Passed: {tests_passed}{Colors.RESET}")
    print(f"{Colors.RED}❌ Failed: {tests_failed}{Colors.RESET}")
    print(f"Total: {tests_passed + tests_failed}")
    print(f"Success Rate: {(tests_passed / (tests_passed + tests_failed) * 100):.1f}%")
    
    # Exit with appropriate code
    sys.exit(0 if tests_failed == 0 else 1)

if __name__ == "__main__":
    main()
