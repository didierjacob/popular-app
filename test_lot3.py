#!/usr/bin/env python3
"""
Session 3 Lot 3 Testing: Outsider Moderation and Manual Celebrity Proposal
Tests all endpoints for admin celebrity proposal, user self-management, reporting, and moderation.
"""

import requests
import json
import time
from typing import Dict, Any, Optional

# Configuration
BASE_URL = "https://personality-launch.preview.emergentagent.com/api"
ADMIN_PASSWORD = "fab31230"  # Read from /app/backend/.env

# Test state
test_state = {
    "celebrity_person_id": None,
    "outsider_person_id": None,
    "outsider_person_id_del": None,
    "report_id_1": None,
    "report_id_2": None,
    "report_id_3": None,
    "report_id_4": None,
}

# Test results
results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "tests": []
}

def log_test(name: str, passed: bool, details: str = ""):
    """Log test result"""
    results["total"] += 1
    if passed:
        results["passed"] += 1
        print(f"✅ {name}")
    else:
        results["failed"] += 1
        print(f"❌ {name}")
    
    if details:
        print(f"   {details}")
    
    results["tests"].append({
        "name": name,
        "passed": passed,
        "details": details
    })

def admin_headers() -> Dict[str, str]:
    """Return headers with admin authentication"""
    return {
        "X-Admin-Password": ADMIN_PASSWORD,
        "Content-Type": "application/json"
    }

def device_headers(device_id: str) -> Dict[str, str]:
    """Return headers with device ID"""
    return {
        "X-Device-ID": device_id,
        "Content-Type": "application/json"
    }

# ============================================================================
# FAMILY 1: POST /api/admin/propose-celebrity
# ============================================================================

def test_1_propose_celebrity_validation_one_word():
    """Test 1: Validation - name must have at least 2 words"""
    try:
        response = requests.post(
            f"{BASE_URL}/admin/propose-celebrity",
            headers=admin_headers(),
            json={"name": "Madonna", "category": "culture"},
            timeout=30
        )
        
        if response.status_code == 400 and "at least 2 words" in response.text.lower():
            log_test("Test 1: Propose celebrity - 1 word validation", True, 
                    f"Status: {response.status_code}, Message: {response.text[:100]}")
        else:
            log_test("Test 1: Propose celebrity - 1 word validation", False,
                    f"Expected 400 with '2 words' message, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 1: Propose celebrity - 1 word validation", False, f"Exception: {str(e)}")

def test_2_propose_celebrity_validation_digits():
    """Test 2: Validation - name must not contain digits"""
    try:
        response = requests.post(
            f"{BASE_URL}/admin/propose-celebrity",
            headers=admin_headers(),
            json={"name": "Test 123", "category": "culture"},
            timeout=30
        )
        
        if response.status_code == 400 and "digit" in response.text.lower():
            log_test("Test 2: Propose celebrity - digits validation", True,
                    f"Status: {response.status_code}, Message: {response.text[:100]}")
        else:
            log_test("Test 2: Propose celebrity - digits validation", False,
                    f"Expected 400 with 'digits' message, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 2: Propose celebrity - digits validation", False, f"Exception: {str(e)}")

def test_3_propose_celebrity_validation_bad_category():
    """Test 3: Validation - category must be valid"""
    try:
        response = requests.post(
            f"{BASE_URL}/admin/propose-celebrity",
            headers=admin_headers(),
            json={"name": "Test Person", "category": "invalid"},
            timeout=30
        )
        
        if response.status_code == 400 and "invalid category" in response.text.lower():
            log_test("Test 3: Propose celebrity - bad category validation", True,
                    f"Status: {response.status_code}, Message: {response.text[:100]}")
        else:
            log_test("Test 3: Propose celebrity - bad category validation", False,
                    f"Expected 400 with 'Invalid category' message, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 3: Propose celebrity - bad category validation", False, f"Exception: {str(e)}")

def test_4_propose_celebrity_deceased():
    """Test 4: Deceased person should be rejected"""
    try:
        response = requests.post(
            f"{BASE_URL}/admin/propose-celebrity",
            headers=admin_headers(),
            json={"name": "John Lennon", "category": "culture"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") == False and data.get("error") == "deceased":
                log_test("Test 4: Propose celebrity - deceased check", True,
                        f"Correctly rejected deceased person: {data}")
            else:
                log_test("Test 4: Propose celebrity - deceased check", False,
                        f"Expected success=false, error='deceased', got: {data}")
        else:
            log_test("Test 4: Propose celebrity - deceased check", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 4: Propose celebrity - deceased check", False, f"Exception: {str(e)}")

def test_5_propose_celebrity_success():
    """Test 5: Successfully propose a celebrity"""
    try:
        response = requests.post(
            f"{BASE_URL}/admin/propose-celebrity",
            headers=admin_headers(),
            json={"name": "Giannis Antetokounmpo", "category": "sport"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if (data.get("success") == True and 
                "person_id" in data and 
                "popularity_external_score" in data and
                "popularoo_index" in data and
                "wikipedia_langs" in data and
                len(data.get("wikipedia_langs", [])) >= 2):
                
                test_state["celebrity_person_id"] = data["person_id"]
                log_test("Test 5: Propose celebrity - success", True,
                        f"Created celebrity: {data['name']}, person_id: {data['person_id']}, "
                        f"ext_score: {data['popularity_external_score']}, "
                        f"popularoo_index: {data['popularoo_index']}, "
                        f"langs: {len(data['wikipedia_langs'])}")
            else:
                log_test("Test 5: Propose celebrity - success", False,
                        f"Missing required fields or insufficient languages: {data}")
        else:
            log_test("Test 5: Propose celebrity - success", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 5: Propose celebrity - success", False, f"Exception: {str(e)}")

def test_6_propose_celebrity_duplicate():
    """Test 6: Duplicate celebrity should return already_exists"""
    try:
        response = requests.post(
            f"{BASE_URL}/admin/propose-celebrity",
            headers=admin_headers(),
            json={"name": "Giannis Antetokounmpo", "category": "sport"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") == False and data.get("error") == "already_exists":
                log_test("Test 6: Propose celebrity - duplicate check", True,
                        f"Correctly detected duplicate: {data}")
            else:
                log_test("Test 6: Propose celebrity - duplicate check", False,
                        f"Expected success=false, error='already_exists', got: {data}")
        else:
            log_test("Test 6: Propose celebrity - duplicate check", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 6: Propose celebrity - duplicate check", False, f"Exception: {str(e)}")

def test_7_cleanup_celebrity():
    """Test 7: Cleanup - delete test celebrity"""
    try:
        response = requests.post(
            f"{BASE_URL}/admin/delete-persons-batch",
            headers=admin_headers(),
            json={"names": ["Giannis Antetokounmpo"]},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") == True and data.get("total_deleted", 0) >= 1:
                log_test("Test 7: Cleanup celebrity via batch delete", True,
                        f"Deleted {data['total_deleted']} person(s)")
            else:
                log_test("Test 7: Cleanup celebrity via batch delete", False,
                        f"Expected deletion, got: {data}")
        else:
            log_test("Test 7: Cleanup celebrity via batch delete", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 7: Cleanup celebrity via batch delete", False, f"Exception: {str(e)}")

# ============================================================================
# FAMILY 2: User self-management
# ============================================================================

def test_8_create_outsider_for_profile_test():
    """Test 8: Setup - Create outsider for profile testing"""
    try:
        response = requests.post(
            f"{BASE_URL}/boost-myself",
            headers={"Content-Type": "application/json"},
            json={
                "user_id": "backend-test-lot3",
                "name": "BackendTest Outsider",
                "tier": "booster",
                "receipt": "test_receipt_backend_lot3",
                "email": "backendtest@example.com"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if "person_id" in data:
                test_state["outsider_person_id"] = data["person_id"]
                log_test("Test 8: Create outsider for profile test", True,
                        f"Created outsider: person_id={data['person_id']}")
            else:
                log_test("Test 8: Create outsider for profile test", False,
                        f"Missing person_id in response: {data}")
        else:
            log_test("Test 8: Create outsider for profile test", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 8: Create outsider for profile test", False, f"Exception: {str(e)}")

def test_9_get_outsider_profile():
    """Test 9: GET my-outsider-profile - should return profile"""
    try:
        response = requests.get(
            f"{BASE_URL}/me/my-outsider-profile",
            params={"device_id": "backend-test-lot3"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if (data.get("found") == True and
                "name" in data and
                "boost_active" in data and
                "boost_tier" in data and
                "email" in data):
                log_test("Test 9: GET my-outsider-profile - found", True,
                        f"Found profile: name={data['name']}, boost_active={data['boost_active']}, "
                        f"tier={data['boost_tier']}, email={data['email']}")
            else:
                log_test("Test 9: GET my-outsider-profile - found", False,
                        f"Missing required fields: {data}")
        else:
            log_test("Test 9: GET my-outsider-profile - found", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 9: GET my-outsider-profile - found", False, f"Exception: {str(e)}")

def test_10_get_outsider_profile_unknown():
    """Test 10: GET my-outsider-profile - unknown device should return found=false"""
    try:
        response = requests.get(
            f"{BASE_URL}/me/my-outsider-profile",
            params={"device_id": "nonexistent-xyz-999"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("found") == False:
                log_test("Test 10: GET my-outsider-profile - unknown device", True,
                        f"Correctly returned found=false: {data}")
            else:
                log_test("Test 10: GET my-outsider-profile - unknown device", False,
                        f"Expected found=false, got: {data}")
        else:
            log_test("Test 10: GET my-outsider-profile - unknown device", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 10: GET my-outsider-profile - unknown device", False, f"Exception: {str(e)}")

def test_11_create_outsider_for_deletion():
    """Test 11: Setup - Create second outsider for deletion test"""
    try:
        response = requests.post(
            f"{BASE_URL}/boost-myself",
            headers={"Content-Type": "application/json"},
            json={
                "user_id": "backend-test-lot3-del",
                "name": "BackendTest Outsider Del",
                "tier": "booster",
                "receipt": "test_receipt_backend_lot3_del",
                "email": "backendtest-del@example.com"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if "person_id" in data:
                test_state["outsider_person_id_del"] = data["person_id"]
                log_test("Test 11: Create outsider for deletion test", True,
                        f"Created outsider: person_id={data['person_id']}")
            else:
                log_test("Test 11: Create outsider for deletion test", False,
                        f"Missing person_id in response: {data}")
        else:
            log_test("Test 11: Create outsider for deletion test", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 11: Create outsider for deletion test", False, f"Exception: {str(e)}")

def test_12_delete_outsider_profile():
    """Test 12: DELETE my-outsider-profile - should succeed"""
    try:
        response = requests.delete(
            f"{BASE_URL}/me/my-outsider-profile",
            params={"device_id": "backend-test-lot3-del"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") == True:
                log_test("Test 12: DELETE my-outsider-profile", True,
                        f"Successfully deleted: {data.get('deleted_name', 'N/A')}")
            else:
                log_test("Test 12: DELETE my-outsider-profile", False,
                        f"Expected success=true, got: {data}")
        else:
            log_test("Test 12: DELETE my-outsider-profile", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 12: DELETE my-outsider-profile", False, f"Exception: {str(e)}")

def test_13_verify_deletion():
    """Test 13: Verify deletion - GET should return found=false"""
    try:
        response = requests.get(
            f"{BASE_URL}/me/my-outsider-profile",
            params={"device_id": "backend-test-lot3-del"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("found") == False:
                log_test("Test 13: Verify deletion - profile not found", True,
                        f"Correctly returned found=false after deletion")
            else:
                log_test("Test 13: Verify deletion - profile not found", False,
                        f"Expected found=false, got: {data}")
        else:
            log_test("Test 13: Verify deletion - profile not found", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 13: Verify deletion - profile not found", False, f"Exception: {str(e)}")

# ============================================================================
# FAMILY 3: Report outsider
# ============================================================================

def test_14_report_outsider_success():
    """Test 14: Report outsider - first report should succeed"""
    if not test_state["outsider_person_id"]:
        log_test("Test 14: Report outsider - first report", False, 
                "Skipped: No outsider_person_id from test 8")
        return
    
    try:
        response = requests.post(
            f"{BASE_URL}/report-outsider",
            headers=device_headers("report-test-001"),
            json={
                "outsider_person_id": test_state["outsider_person_id"],
                "reason": "spam",
                "comment": "Test report"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") == True and "report_id" in data:
                test_state["report_id_1"] = data["report_id"]
                log_test("Test 14: Report outsider - first report", True,
                        f"Report created: report_id={data['report_id']}, "
                        f"total_pending={data.get('total_pending_reports', 0)}")
            else:
                log_test("Test 14: Report outsider - first report", False,
                        f"Missing success or report_id: {data}")
        else:
            log_test("Test 14: Report outsider - first report", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 14: Report outsider - first report", False, f"Exception: {str(e)}")

def test_15_report_outsider_anti_spam():
    """Test 15: Report outsider - same device should get 429"""
    if not test_state["outsider_person_id"]:
        log_test("Test 15: Report outsider - anti-spam", False,
                "Skipped: No outsider_person_id from test 8")
        return
    
    try:
        response = requests.post(
            f"{BASE_URL}/report-outsider",
            headers=device_headers("report-test-001"),
            json={
                "outsider_person_id": test_state["outsider_person_id"],
                "reason": "spam",
                "comment": "Test report duplicate"
            },
            timeout=30
        )
        
        if response.status_code == 429:
            log_test("Test 15: Report outsider - anti-spam (24h cooldown)", True,
                    f"Correctly blocked duplicate report: {response.text[:100]}")
        else:
            log_test("Test 15: Report outsider - anti-spam (24h cooldown)", False,
                    f"Expected 429, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 15: Report outsider - anti-spam (24h cooldown)", False, f"Exception: {str(e)}")

def test_16_report_outsider_different_device():
    """Test 16: Report outsider - different device should succeed"""
    if not test_state["outsider_person_id"]:
        log_test("Test 16: Report outsider - different device", False,
                "Skipped: No outsider_person_id from test 8")
        return
    
    try:
        response = requests.post(
            f"{BASE_URL}/report-outsider",
            headers=device_headers("report-test-002"),
            json={
                "outsider_person_id": test_state["outsider_person_id"],
                "reason": "fake",
                "comment": "Test report from different device"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if (data.get("success") == True and 
                "report_id" in data and 
                data.get("total_pending_reports", 0) >= 2):
                test_state["report_id_2"] = data["report_id"]
                log_test("Test 16: Report outsider - different device", True,
                        f"Report created: report_id={data['report_id']}, "
                        f"total_pending={data['total_pending_reports']}")
            else:
                log_test("Test 16: Report outsider - different device", False,
                        f"Expected total_pending_reports >= 2, got: {data}")
        else:
            log_test("Test 16: Report outsider - different device", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 16: Report outsider - different device", False, f"Exception: {str(e)}")

def test_17_report_outsider_invalid_reason():
    """Test 17: Report outsider - invalid reason should return 400"""
    if not test_state["outsider_person_id"]:
        log_test("Test 17: Report outsider - invalid reason", False,
                "Skipped: No outsider_person_id from test 8")
        return
    
    try:
        response = requests.post(
            f"{BASE_URL}/report-outsider",
            headers=device_headers("report-test-003"),
            json={
                "outsider_person_id": test_state["outsider_person_id"],
                "reason": "xyz",
                "comment": "Invalid reason test"
            },
            timeout=30
        )
        
        if response.status_code == 400 and "invalid reason" in response.text.lower():
            log_test("Test 17: Report outsider - invalid reason", True,
                    f"Correctly rejected invalid reason: {response.text[:100]}")
        else:
            log_test("Test 17: Report outsider - invalid reason", False,
                    f"Expected 400 with 'Invalid reason', got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 17: Report outsider - invalid reason", False, f"Exception: {str(e)}")

# ============================================================================
# FAMILY 4: Admin moderation
# ============================================================================

def test_18_admin_list_pending_reports():
    """Test 18: Admin list pending reports - should show reports"""
    try:
        response = requests.get(
            f"{BASE_URL}/admin/outsider-reports",
            headers=admin_headers(),
            params={"status": "pending"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            reports = data.get("reports", [])
            
            # Find our test outsider
            our_outsider = None
            for r in reports:
                if r.get("outsider_person_id") == test_state["outsider_person_id"]:
                    our_outsider = r
                    break
            
            if our_outsider and our_outsider.get("report_count", 0) >= 2:
                log_test("Test 18: Admin list pending reports", True,
                        f"Found outsider with {our_outsider['report_count']} reports: "
                        f"{our_outsider.get('outsider_name', 'N/A')}")
            else:
                log_test("Test 18: Admin list pending reports", False,
                        f"Expected outsider with ≥2 reports, got: {data}")
        else:
            log_test("Test 18: Admin list pending reports", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 18: Admin list pending reports", False, f"Exception: {str(e)}")

def test_19_admin_ignore_report():
    """Test 19: Admin ignore report - should mark all reports as ignored"""
    if not test_state["report_id_1"]:
        log_test("Test 19: Admin ignore report", False,
                "Skipped: No report_id from test 14")
        return
    
    try:
        response = requests.post(
            f"{BASE_URL}/admin/outsider-reports/{test_state['report_id_1']}/ignore",
            headers=admin_headers(),
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") == True and data.get("reports_ignored", 0) >= 2:
                log_test("Test 19: Admin ignore report", True,
                        f"Ignored {data['reports_ignored']} reports for {data.get('outsider_name', 'N/A')}")
            else:
                log_test("Test 19: Admin ignore report", False,
                        f"Expected reports_ignored >= 2, got: {data}")
        else:
            log_test("Test 19: Admin ignore report", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 19: Admin ignore report", False, f"Exception: {str(e)}")

def test_20_verify_ignore():
    """Test 20: Verify ignore - pending reports should be 0 for that outsider"""
    try:
        response = requests.get(
            f"{BASE_URL}/admin/outsider-reports",
            headers=admin_headers(),
            params={"status": "pending"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            reports = data.get("reports", [])
            
            # Check if our outsider is still in pending
            our_outsider = None
            for r in reports:
                if r.get("outsider_person_id") == test_state["outsider_person_id"]:
                    our_outsider = r
                    break
            
            if our_outsider is None:
                log_test("Test 20: Verify ignore - no pending reports", True,
                        f"Correctly removed outsider from pending list")
            else:
                log_test("Test 20: Verify ignore - no pending reports", False,
                        f"Outsider still in pending with {our_outsider.get('report_count', 0)} reports")
        else:
            log_test("Test 20: Verify ignore - no pending reports", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 20: Verify ignore - no pending reports", False, f"Exception: {str(e)}")

def test_21_create_reports_for_warn_test():
    """Test 21: Setup - Create new reports for WARN test"""
    # Create a new outsider for warn test
    try:
        response = requests.post(
            f"{BASE_URL}/boost-myself",
            headers={"Content-Type": "application/json"},
            json={
                "user_id": "backend-test-lot3-warn",
                "name": "BackendTest Outsider Warn",
                "tier": "booster",
                "receipt": "test_receipt_backend_lot3_warn",
                "email": "backendtest-warn@example.com"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            person_id = data.get("person_id")
            
            # Create a report
            report_response = requests.post(
                f"{BASE_URL}/report-outsider",
                headers=device_headers("report-test-warn-001"),
                json={
                    "outsider_person_id": person_id,
                    "reason": "inappropriate",
                    "comment": "Test report for warn"
                },
                timeout=30
            )
            
            if report_response.status_code == 200:
                report_data = report_response.json()
                test_state["report_id_3"] = report_data.get("report_id")
                log_test("Test 21: Create reports for WARN test", True,
                        f"Created outsider and report: person_id={person_id}, report_id={test_state['report_id_3']}")
            else:
                log_test("Test 21: Create reports for WARN test", False,
                        f"Failed to create report: {report_response.status_code}")
        else:
            log_test("Test 21: Create reports for WARN test", False,
                    f"Failed to create outsider: {response.status_code}")
    except Exception as e:
        log_test("Test 21: Create reports for WARN test", False, f"Exception: {str(e)}")

def test_22_admin_warn_outsider():
    """Test 22: Admin warn outsider - should send email"""
    if not test_state["report_id_3"]:
        log_test("Test 22: Admin warn outsider", False,
                "Skipped: No report_id from test 21")
        return
    
    try:
        response = requests.post(
            f"{BASE_URL}/admin/outsider-reports/{test_state['report_id_3']}/warn",
            headers=admin_headers(),
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if (data.get("success") == True and 
                "email_sent_to" in data and
                data.get("email_sent_to")):
                log_test("Test 22: Admin warn outsider", True,
                        f"Warning sent to {data['email_sent_to']}, "
                        f"reports_warned={data.get('reports_warned', 0)}")
            else:
                log_test("Test 22: Admin warn outsider", False,
                        f"Missing email_sent_to or success: {data}")
        else:
            log_test("Test 22: Admin warn outsider", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 22: Admin warn outsider", False, f"Exception: {str(e)}")

def test_23_create_reports_for_delete_test():
    """Test 23: Setup - Create new reports for DELETE test"""
    # Create a new outsider for delete test
    try:
        response = requests.post(
            f"{BASE_URL}/boost-myself",
            headers={"Content-Type": "application/json"},
            json={
                "user_id": "backend-test-lot3-delete",
                "name": "BackendTest Outsider Delete",
                "tier": "booster",
                "receipt": "test_receipt_backend_lot3_delete",
                "email": "backendtest-delete@example.com"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            person_id = data.get("person_id")
            
            # Create a report
            report_response = requests.post(
                f"{BASE_URL}/report-outsider",
                headers=device_headers("report-test-delete-001"),
                json={
                    "outsider_person_id": person_id,
                    "reason": "offensive",
                    "comment": "Test report for delete"
                },
                timeout=30
            )
            
            if report_response.status_code == 200:
                report_data = report_response.json()
                test_state["report_id_4"] = report_data.get("report_id")
                log_test("Test 23: Create reports for DELETE test", True,
                        f"Created outsider and report: person_id={person_id}, report_id={test_state['report_id_4']}")
            else:
                log_test("Test 23: Create reports for DELETE test", False,
                        f"Failed to create report: {report_response.status_code}")
        else:
            log_test("Test 23: Create reports for DELETE test", False,
                    f"Failed to create outsider: {response.status_code}")
    except Exception as e:
        log_test("Test 23: Create reports for DELETE test", False, f"Exception: {str(e)}")

def test_24_admin_delete_outsider():
    """Test 24: Admin delete outsider - should delete and send email"""
    if not test_state["report_id_4"]:
        log_test("Test 24: Admin delete outsider", False,
                "Skipped: No report_id from test 23")
        return
    
    try:
        response = requests.post(
            f"{BASE_URL}/admin/outsider-reports/{test_state['report_id_4']}/delete",
            headers=admin_headers(),
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if (data.get("success") == True and
                "deleted_name" in data and
                "email_sent" in data and
                "blocked_slug" in data):
                log_test("Test 24: Admin delete outsider", True,
                        f"Deleted {data['deleted_name']}, email_sent={data['email_sent']}, "
                        f"blocked_slug={data['blocked_slug']}")
            else:
                log_test("Test 24: Admin delete outsider", False,
                        f"Missing required fields: {data}")
        else:
            log_test("Test 24: Admin delete outsider", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 24: Admin delete outsider", False, f"Exception: {str(e)}")

def test_25_final_cleanup():
    """Test 25: Final cleanup - delete all test outsiders"""
    try:
        # Collect all test outsider names
        names_to_delete = [
            "BackendTest Outsider",
            "BackendTest Outsider Del",
            "BackendTest Outsider Warn",
            "BackendTest Outsider Delete"
        ]
        
        response = requests.post(
            f"{BASE_URL}/admin/delete-persons-batch",
            headers=admin_headers(),
            json={"names": names_to_delete},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            log_test("Test 25: Final cleanup", True,
                    f"Deleted {data.get('total_deleted', 0)} outsiders, "
                    f"not found: {len(data.get('not_found', []))}")
        else:
            log_test("Test 25: Final cleanup", False,
                    f"Expected 200, got {response.status_code}: {response.text[:200]}")
    except Exception as e:
        log_test("Test 25: Final cleanup", False, f"Exception: {str(e)}")

# ============================================================================
# Main test runner
# ============================================================================

def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "="*80)
    print("SESSION 3 LOT 3 TESTING: Outsider Moderation & Manual Celebrity Proposal")
    print("="*80 + "\n")
    
    print("FAMILY 1: POST /api/admin/propose-celebrity")
    print("-" * 80)
    test_1_propose_celebrity_validation_one_word()
    test_2_propose_celebrity_validation_digits()
    test_3_propose_celebrity_validation_bad_category()
    test_4_propose_celebrity_deceased()
    test_5_propose_celebrity_success()
    test_6_propose_celebrity_duplicate()
    test_7_cleanup_celebrity()
    
    print("\nFAMILY 2: User self-management")
    print("-" * 80)
    test_8_create_outsider_for_profile_test()
    test_9_get_outsider_profile()
    test_10_get_outsider_profile_unknown()
    test_11_create_outsider_for_deletion()
    test_12_delete_outsider_profile()
    test_13_verify_deletion()
    
    print("\nFAMILY 3: Report outsider")
    print("-" * 80)
    test_14_report_outsider_success()
    test_15_report_outsider_anti_spam()
    test_16_report_outsider_different_device()
    test_17_report_outsider_invalid_reason()
    
    print("\nFAMILY 4: Admin moderation")
    print("-" * 80)
    test_18_admin_list_pending_reports()
    test_19_admin_ignore_report()
    test_20_verify_ignore()
    test_21_create_reports_for_warn_test()
    test_22_admin_warn_outsider()
    test_23_create_reports_for_delete_test()
    test_24_admin_delete_outsider()
    test_25_final_cleanup()
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total tests: {results['total']}")
    print(f"Passed: {results['passed']} ✅")
    print(f"Failed: {results['failed']} ❌")
    print(f"Success rate: {(results['passed']/results['total']*100):.1f}%")
    print("="*80 + "\n")
    
    # Print failed tests details
    if results['failed'] > 0:
        print("\nFAILED TESTS DETAILS:")
        print("-" * 80)
        for test in results['tests']:
            if not test['passed']:
                print(f"❌ {test['name']}")
                if test['details']:
                    print(f"   {test['details']}")
        print()

if __name__ == "__main__":
    run_all_tests()
