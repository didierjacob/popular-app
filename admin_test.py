#!/usr/bin/env python3
"""
Admin/Moderation Endpoints Testing for Popularoo App
Tests all 9 admin endpoints with REAL EFFECT verification
"""

import requests
import json
import time
import os
from typing import Dict, Any, List, Optional

# Backend URL and admin password
BACKEND_URL = "https://personality-launch.preview.emergentagent.com/api"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "CHANGE_ME")

# Test results tracking
test_results = []

def log_test(test_name: str, passed: bool, details: str = ""):
    """Log test result"""
    status = "✅ PASSED" if passed else "❌ FAILED"
    result = {
        "test": test_name,
        "passed": passed,
        "details": details
    }
    test_results.append(result)
    print(f"{status}: {test_name}")
    if details:
        print(f"  Details: {details}")
    print()

def get_valid_person_id() -> Optional[str]:
    """Get a valid person_id from the database"""
    try:
        response = requests.get(f"{BACKEND_URL}/people?limit=1", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("id")
            elif isinstance(data, dict) and "people" in data and len(data["people"]) > 0:
                return data["people"][0].get("id")
    except Exception as e:
        print(f"Error getting valid person_id: {e}")
    return None

def test_action_1_suspend_outsider():
    """
    Action 1 - Suspend Outsider
    - Create an outsider
    - Get its person_id
    - Suspend it
    - VERIFY REAL EFFECT: person filtered out from GET /api/people
    - VERIFY vote blocked: POST /api/people/{person_id}/vote returns 403
    - Unsuspend
    - VERIFY restored: person appears again
    """
    print("=" * 80)
    print("ACTION 1: SUSPEND/UNSUSPEND OUTSIDER")
    print("=" * 80)
    
    outsider_name = f"Test Outsider {int(time.time())}"
    person_id = None
    
    try:
        # Step 1: Create an outsider
        print("\n1.1: Creating outsider...")
        create_response = requests.post(
            f"{BACKEND_URL}/boost-myself",
            json={
                "user_id": f"test_user_{int(time.time())}",
                "name": outsider_name,
                "tier": "booster",
                "receipt": "TEST_RECEIPT_12345",
                "email": "test@test.com"
            },
            timeout=10
        )
        
        if create_response.status_code != 200:
            log_test("Action 1: Create outsider", False, f"HTTP {create_response.status_code}: {create_response.text}")
            return
        
        create_data = create_response.json()
        print(f"  Created outsider: {create_data}")
        
        # Step 2: Get person_id from GET /api/people
        print(f"\n1.2: Getting person_id for '{outsider_name}'...")
        search_response = requests.get(
            f"{BACKEND_URL}/people?include_outsiders=true&query={outsider_name}",
            timeout=10
        )
        
        if search_response.status_code != 200:
            log_test("Action 1: Get person_id", False, f"HTTP {search_response.status_code}: {search_response.text}")
            return
        
        search_data = search_response.json()
        people = search_data if isinstance(search_data, list) else search_data.get("people", [])
        
        if not people:
            log_test("Action 1: Get person_id", False, f"Outsider not found in search results")
            return
        
        person_id = people[0].get("id")
        print(f"  Found person_id: {person_id}")
        
        # Step 3: Suspend the outsider
        print(f"\n1.3: Suspending outsider {person_id}...")
        suspend_response = requests.post(
            f"{BACKEND_URL}/admin/outsider/{person_id}/suspend",
            json={
                "reason": "test suspension",
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        
        if suspend_response.status_code != 200:
            log_test("Action 1: Suspend outsider", False, f"HTTP {suspend_response.status_code}: {suspend_response.text}")
            return
        
        print(f"  Suspended successfully: {suspend_response.json()}")
        
        # Step 4: VERIFY REAL EFFECT - person should be filtered out
        print(f"\n1.4: VERIFYING REAL EFFECT - person should be filtered out...")
        verify_response = requests.get(
            f"{BACKEND_URL}/people?include_outsiders=true&query={outsider_name}",
            timeout=10
        )
        
        if verify_response.status_code != 200:
            log_test("Action 1: Verify suspension effect", False, f"HTTP {verify_response.status_code}: {verify_response.text}")
            return
        
        verify_data = verify_response.json()
        verify_people = verify_data if isinstance(verify_data, list) else verify_data.get("people", [])
        
        if len(verify_people) > 0:
            log_test("Action 1: Verify suspension effect", False, f"Suspended person still appears in search results (should be filtered out)")
            return
        
        print(f"  ✓ Suspended person correctly filtered out from search results")
        
        # Step 5: VERIFY vote blocked
        print(f"\n1.5: VERIFYING vote blocked (should return 403)...")
        vote_response = requests.post(
            f"{BACKEND_URL}/people/{person_id}/vote",
            json={"value": 1},
            headers={"X-Device-ID": "test-device-suspend"},
            timeout=10
        )
        
        if vote_response.status_code != 403:
            log_test("Action 1: Verify vote blocked", False, f"Expected 403, got {vote_response.status_code}: {vote_response.text}")
            return
        
        print(f"  ✓ Vote correctly blocked with 403: {vote_response.json()}")
        
        # Step 6: Unsuspend
        print(f"\n1.6: Unsuspending outsider...")
        unsuspend_response = requests.post(
            f"{BACKEND_URL}/admin/outsider/{person_id}/unsuspend",
            json={
                "reason": "",
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        
        if unsuspend_response.status_code != 200:
            log_test("Action 1: Unsuspend outsider", False, f"HTTP {unsuspend_response.status_code}: {unsuspend_response.text}")
            return
        
        print(f"  Unsuspended successfully: {unsuspend_response.json()}")
        
        # Step 7: VERIFY restored
        print(f"\n1.7: VERIFYING person restored (should appear in search)...")
        restore_response = requests.get(
            f"{BACKEND_URL}/people?include_outsiders=true&query={outsider_name}",
            timeout=10
        )
        
        if restore_response.status_code != 200:
            log_test("Action 1: Verify restoration", False, f"HTTP {restore_response.status_code}: {restore_response.text}")
            return
        
        restore_data = restore_response.json()
        restore_people = restore_data if isinstance(restore_data, list) else restore_data.get("people", [])
        
        if len(restore_people) == 0:
            log_test("Action 1: Verify restoration", False, f"Unsuspended person not found in search results")
            return
        
        print(f"  ✓ Person correctly restored and appears in search results")
        
        log_test(
            "Action 1: Suspend/Unsuspend Outsider",
            True,
            f"All steps passed: Created outsider, suspended (filtered out + vote blocked), unsuspended (restored)"
        )
        
    except Exception as e:
        log_test("Action 1: Suspend/Unsuspend Outsider", False, f"Exception: {str(e)}")

def test_action_2_ban_device():
    """
    Action 2 - Ban Device
    - Ban a device
    - VERIFY REAL EFFECT: vote with that device returns 403
    - VERIFY list: device appears in banned-devices list
    - Unban device
    - VERIFY unban: vote works again (200)
    """
    print("=" * 80)
    print("ACTION 2: BAN/UNBAN DEVICE")
    print("=" * 80)
    
    test_device_id = f"banned-test-device-{int(time.time())}"
    person_id = None
    
    try:
        # Get a valid person_id for voting tests
        person_id = get_valid_person_id()
        if not person_id:
            log_test("Action 2: Get valid person_id", False, "Could not get valid person_id")
            return
        
        print(f"Using person_id: {person_id}")
        
        # Step 1: Ban the device
        print(f"\n2.1: Banning device '{test_device_id}'...")
        ban_response = requests.post(
            f"{BACKEND_URL}/admin/ban-device",
            json={
                "device_id": test_device_id,
                "reason": "testing",
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        
        if ban_response.status_code != 200:
            log_test("Action 2: Ban device", False, f"HTTP {ban_response.status_code}: {ban_response.text}")
            return
        
        print(f"  Banned successfully: {ban_response.json()}")
        
        # Step 2: VERIFY REAL EFFECT - vote should be blocked
        print(f"\n2.2: VERIFYING vote blocked (should return 403)...")
        vote_response = requests.post(
            f"{BACKEND_URL}/people/{person_id}/vote",
            json={"value": 1},
            headers={"X-Device-ID": test_device_id},
            timeout=10
        )
        
        if vote_response.status_code != 403:
            log_test("Action 2: Verify vote blocked", False, f"Expected 403, got {vote_response.status_code}: {vote_response.text}")
            return
        
        print(f"  ✓ Vote correctly blocked with 403: {vote_response.json()}")
        
        # Step 3: VERIFY device in banned list
        print(f"\n2.3: VERIFYING device appears in banned-devices list...")
        list_response = requests.get(
            f"{BACKEND_URL}/admin/banned-devices?password={ADMIN_PASSWORD}",
            timeout=10
        )
        
        if list_response.status_code != 200:
            log_test("Action 2: List banned devices", False, f"HTTP {list_response.status_code}: {list_response.text}")
            return
        
        list_data = list_response.json()
        # Handle both list and dict responses
        if isinstance(list_data, list):
            banned_devices = list_data
        else:
            banned_devices = list_data.get("banned_devices", [])
        
        device_found = any(d.get("device_id") == test_device_id for d in banned_devices)
        
        if not device_found:
            log_test("Action 2: Verify device in list", False, f"Device not found in banned-devices list")
            return
        
        print(f"  ✓ Device found in banned-devices list")
        
        # Step 4: Unban the device
        print(f"\n2.4: Unbanning device '{test_device_id}'...")
        unban_response = requests.post(
            f"{BACKEND_URL}/admin/unban-device/{test_device_id}",
            json={"password": ADMIN_PASSWORD},
            timeout=10
        )
        
        if unban_response.status_code != 200:
            log_test("Action 2: Unban device", False, f"HTTP {unban_response.status_code}: {unban_response.text}")
            return
        
        print(f"  Unbanned successfully: {unban_response.json()}")
        
        # Step 5: VERIFY vote works again
        print(f"\n2.5: VERIFYING vote works after unban (should return 200)...")
        vote_after_response = requests.post(
            f"{BACKEND_URL}/people/{person_id}/vote",
            json={"value": 1},
            headers={"X-Device-ID": test_device_id},
            timeout=10
        )
        
        if vote_after_response.status_code != 200:
            log_test("Action 2: Verify vote works after unban", False, f"Expected 200, got {vote_after_response.status_code}: {vote_after_response.text}")
            return
        
        print(f"  ✓ Vote works correctly after unban: {vote_after_response.json()}")
        
        log_test(
            "Action 2: Ban/Unban Device",
            True,
            f"All steps passed: Banned device (vote blocked + in list), unbanned (vote works)"
        )
        
    except Exception as e:
        log_test("Action 2: Ban/Unban Device", False, f"Exception: {str(e)}")

def test_action_3_grant_booster():
    """
    Action 3 - Grant Booster
    - POST /api/admin/grant-booster
    - Verify response has boost_id, tier, duration, expires_at
    """
    print("=" * 80)
    print("ACTION 3: GRANT BOOSTER")
    print("=" * 80)
    
    try:
        grant_response = requests.post(
            f"{BACKEND_URL}/admin/grant-booster",
            json={
                "device_id": f"grant-test-device-{int(time.time())}",
                "name": f"Grant Test User {int(time.time())}",
                "tier": "super_booster",
                "email": "",
                "password": ADMIN_PASSWORD
            },
            timeout=10
        )
        
        if grant_response.status_code != 200:
            log_test("Action 3: Grant Booster", False, f"HTTP {grant_response.status_code}: {grant_response.text}")
            return
        
        data = grant_response.json()
        
        # Verify required fields (duration_hours is the actual field name)
        required_fields = ["boost_id", "tier", "duration_hours", "expires_at"]
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            log_test("Action 3: Grant Booster", False, f"Missing required fields: {missing_fields}. Response: {data}")
            return
        
        log_test(
            "Action 3: Grant Booster",
            True,
            f"Success with all required fields: boost_id={data['boost_id']}, tier={data['tier']}, duration_hours={data['duration_hours']}, expires_at={data['expires_at']}"
        )
        
        return data.get("boost_id")
        
    except Exception as e:
        log_test("Action 3: Grant Booster", False, f"Exception: {str(e)}")
        return None

def test_action_4_expire_booster(boost_id: Optional[str] = None):
    """
    Action 4 - Expire Booster
    - Use boost_id from Action 3 or create a new one
    - POST /api/admin/expire-booster/{boost_id}
    - Verify success response
    """
    print("=" * 80)
    print("ACTION 4: EXPIRE BOOSTER")
    print("=" * 80)
    
    try:
        # If no boost_id provided, create one
        if not boost_id:
            print("No boost_id provided, creating a new booster...")
            grant_response = requests.post(
                f"{BACKEND_URL}/admin/grant-booster",
                json={
                    "device_id": f"expire-test-device-{int(time.time())}",
                    "name": f"Expire Test User {int(time.time())}",
                    "tier": "booster",
                    "email": "",
                    "password": ADMIN_PASSWORD
                },
                timeout=10
            )
            
            if grant_response.status_code != 200:
                log_test("Action 4: Create booster for expiration", False, f"HTTP {grant_response.status_code}: {grant_response.text}")
                return
            
            boost_id = grant_response.json().get("boost_id")
            print(f"  Created boost_id: {boost_id}")
        
        # Expire the booster
        print(f"\nExpiring boost_id: {boost_id}...")
        expire_response = requests.post(
            f"{BACKEND_URL}/admin/expire-booster/{boost_id}",
            json={"password": ADMIN_PASSWORD},
            timeout=10
        )
        
        if expire_response.status_code != 200:
            log_test("Action 4: Expire Booster", False, f"HTTP {expire_response.status_code}: {expire_response.text}")
            return
        
        data = expire_response.json()
        
        log_test(
            "Action 4: Expire Booster",
            True,
            f"Successfully expired boost_id {boost_id}. Response: {data}"
        )
        
    except Exception as e:
        log_test("Action 4: Expire Booster", False, f"Exception: {str(e)}")

def test_action_5_activity_recent():
    """
    Action 5 - Activity Recent (SECURITY)
    - GET without password → must return 422 (validation error)
    - GET with wrong password → must return 403
    - GET with correct password → should return 200 with data
    """
    print("=" * 80)
    print("ACTION 5: ACTIVITY RECENT (SECURITY)")
    print("=" * 80)
    
    try:
        # Test 1: No password (should return 422)
        print("\n5.1: Testing without password (should return 422)...")
        no_pass_response = requests.get(
            f"{BACKEND_URL}/admin/activity/recent",
            timeout=10
        )
        
        if no_pass_response.status_code != 422:
            log_test("Action 5: No password test", False, f"Expected 422, got {no_pass_response.status_code}: {no_pass_response.text}")
            return
        
        print(f"  ✓ Correctly returned 422 without password")
        
        # Test 2: Wrong password (should return 403)
        print("\n5.2: Testing with wrong password (should return 403)...")
        wrong_pass_response = requests.get(
            f"{BACKEND_URL}/admin/activity/recent?password=wrong",
            timeout=10
        )
        
        if wrong_pass_response.status_code != 403:
            log_test("Action 5: Wrong password test", False, f"Expected 403, got {wrong_pass_response.status_code}: {wrong_pass_response.text}")
            return
        
        print(f"  ✓ Correctly returned 403 with wrong password")
        
        # Test 3: Correct password (should return 200)
        print("\n5.3: Testing with correct password (should return 200)...")
        correct_pass_response = requests.get(
            f"{BACKEND_URL}/admin/activity/recent?password={ADMIN_PASSWORD}",
            timeout=10
        )
        
        if correct_pass_response.status_code != 200:
            log_test("Action 5: Correct password test", False, f"Expected 200, got {correct_pass_response.status_code}: {correct_pass_response.text}")
            return
        
        data = correct_pass_response.json()
        print(f"  ✓ Correctly returned 200 with data: {list(data.keys())}")
        
        log_test(
            "Action 5: Activity Recent (Security)",
            True,
            f"All security tests passed: 422 without password, 403 with wrong password, 200 with correct password"
        )
        
    except Exception as e:
        log_test("Action 5: Activity Recent (Security)", False, f"Exception: {str(e)}")

def test_action_6_audit_log():
    """
    Action 6 - Audit Log
    - GET /api/admin/audit-log?password={ADMIN_PASSWORD}
    - Verify response contains logs with required fields
    - Test filter by action_type
    """
    print("=" * 80)
    print("ACTION 6: AUDIT LOG")
    print("=" * 80)
    
    try:
        # Test 1: Get audit log
        print("\n6.1: Getting audit log...")
        log_response = requests.get(
            f"{BACKEND_URL}/admin/audit-log?password={ADMIN_PASSWORD}",
            timeout=10
        )
        
        if log_response.status_code != 200:
            log_test("Action 6: Get audit log", False, f"HTTP {log_response.status_code}: {log_response.text}")
            return
        
        data = log_response.json()
        logs = data.get("logs", [])
        
        print(f"  Retrieved {len(logs)} audit log entries")
        
        # Verify log structure
        if logs:
            required_fields = ["action", "target", "success", "timestamp"]
            first_log = logs[0]
            missing_fields = [f for f in required_fields if f not in first_log]
            
            if missing_fields:
                log_test("Action 6: Verify log structure", False, f"Missing required fields: {missing_fields}. Log: {first_log}")
                return
            
            print(f"  ✓ Logs have required fields: {required_fields}")
            print(f"  Sample log: {first_log}")
        
        # Test 2: Filter by action_type
        print("\n6.2: Testing filter by action_type=ban_device...")
        filter_response = requests.get(
            f"{BACKEND_URL}/admin/audit-log?password={ADMIN_PASSWORD}&action_type=ban_device",
            timeout=10
        )
        
        if filter_response.status_code != 200:
            log_test("Action 6: Filter audit log", False, f"HTTP {filter_response.status_code}: {filter_response.text}")
            return
        
        filter_data = filter_response.json()
        filter_logs = filter_data.get("logs", [])
        
        print(f"  Retrieved {len(filter_logs)} filtered logs")
        
        # Verify all logs match the filter
        if filter_logs:
            all_match = all(log.get("action") == "ban_device" for log in filter_logs)
            if not all_match:
                log_test("Action 6: Verify filter", False, f"Some logs don't match filter action_type=ban_device")
                return
            print(f"  ✓ All filtered logs match action_type=ban_device")
        
        log_test(
            "Action 6: Audit Log",
            True,
            f"Retrieved {len(logs)} logs with correct structure, filter works correctly"
        )
        
    except Exception as e:
        log_test("Action 6: Audit Log", False, f"Exception: {str(e)}")

def test_action_7_selective_vote_invalidation():
    """
    Action 7 - Selective Vote Invalidation
    - Vote on a person
    - Full invalidation (no params)
    - Vote again
    - Selective invalidation by device_id
    """
    print("=" * 80)
    print("ACTION 7: SELECTIVE VOTE INVALIDATION")
    print("=" * 80)
    
    try:
        # Get a valid person_id
        person_id = get_valid_person_id()
        if not person_id:
            log_test("Action 7: Get valid person_id", False, "Could not get valid person_id")
            return
        
        print(f"Using person_id: {person_id}")
        
        # Step 1: Vote on the person
        print("\n7.1: Voting on person...")
        device_id_1 = f"invalidate-test-device-{int(time.time())}"
        vote_response = requests.post(
            f"{BACKEND_URL}/people/{person_id}/vote",
            json={"value": 1},
            headers={"X-Device-ID": device_id_1},
            timeout=10
        )
        
        if vote_response.status_code != 200:
            log_test("Action 7: Initial vote", False, f"HTTP {vote_response.status_code}: {vote_response.text}")
            return
        
        print(f"  ✓ Voted successfully")
        
        # Step 2: Full invalidation
        print("\n7.2: Full invalidation (no params)...")
        full_invalidate_response = requests.post(
            f"{BACKEND_URL}/admin/person/{person_id}/invalidate-votes",
            json={"password": ADMIN_PASSWORD},
            timeout=10
        )
        
        if full_invalidate_response.status_code != 200:
            log_test("Action 7: Full invalidation", False, f"HTTP {full_invalidate_response.status_code}: {full_invalidate_response.text}")
            return
        
        full_data = full_invalidate_response.json()
        
        if full_data.get("mode") != "full_reset":
            log_test("Action 7: Verify full reset mode", False, f"Expected mode='full_reset', got {full_data.get('mode')}")
            return
        
        print(f"  ✓ Full invalidation successful, mode=full_reset")
        
        # Step 3: Vote again
        print("\n7.3: Voting again after full reset...")
        vote_response_2 = requests.post(
            f"{BACKEND_URL}/people/{person_id}/vote",
            json={"value": 1},
            headers={"X-Device-ID": device_id_1},
            timeout=10
        )
        
        if vote_response_2.status_code != 200:
            log_test("Action 7: Vote after full reset", False, f"HTTP {vote_response_2.status_code}: {vote_response_2.text}")
            return
        
        print(f"  ✓ Voted successfully after full reset")
        
        # Step 4: Selective invalidation by device_id
        print("\n7.4: Selective invalidation by device_id...")
        selective_invalidate_response = requests.post(
            f"{BACKEND_URL}/admin/person/{person_id}/invalidate-votes",
            json={
                "password": ADMIN_PASSWORD,
                "device_id": device_id_1
            },
            timeout=10
        )
        
        if selective_invalidate_response.status_code != 200:
            log_test("Action 7: Selective invalidation", False, f"HTTP {selective_invalidate_response.status_code}: {selective_invalidate_response.text}")
            return
        
        selective_data = selective_invalidate_response.json()
        
        if selective_data.get("mode") != "selective":
            log_test("Action 7: Verify selective mode", False, f"Expected mode='selective', got {selective_data.get('mode')}")
            return
        
        print(f"  ✓ Selective invalidation successful, mode=selective")
        
        log_test(
            "Action 7: Selective Vote Invalidation",
            True,
            f"All steps passed: Full reset (mode=full_reset), Selective invalidation (mode=selective)"
        )
        
    except Exception as e:
        log_test("Action 7: Selective Vote Invalidation", False, f"Exception: {str(e)}")

def test_action_8_extended_stats():
    """
    Action 8 - Extended Stats (active_users_7d, 30d)
    - GET /api/admin/stats?password={ADMIN_PASSWORD}
    - Response MUST contain: active_users_24h, active_users_7d, active_users_30d
    """
    print("=" * 80)
    print("ACTION 8: EXTENDED STATS")
    print("=" * 80)
    
    try:
        stats_response = requests.get(
            f"{BACKEND_URL}/admin/stats?password={ADMIN_PASSWORD}",
            timeout=10
        )
        
        if stats_response.status_code != 200:
            log_test("Action 8: Extended Stats", False, f"HTTP {stats_response.status_code}: {stats_response.text}")
            return
        
        data = stats_response.json()
        
        # Verify required fields
        required_fields = ["active_users_24h", "active_users_7d", "active_users_30d"]
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            log_test("Action 8: Extended Stats", False, f"Missing required fields: {missing_fields}. Response keys: {list(data.keys())}")
            return
        
        log_test(
            "Action 8: Extended Stats",
            True,
            f"All required fields present: active_users_24h={data['active_users_24h']}, active_users_7d={data['active_users_7d']}, active_users_30d={data['active_users_30d']}"
        )
        
    except Exception as e:
        log_test("Action 8: Extended Stats", False, f"Exception: {str(e)}")

def test_action_9_lifetime_revenue():
    """
    Action 9 - Lifetime Revenue
    - GET /api/admin/stats?password={ADMIN_PASSWORD}
    - Response MUST contain: revenue_total_lifetime, revenue_lifetime_breakdown, revenue_24h_breakdown
    """
    print("=" * 80)
    print("ACTION 9: LIFETIME REVENUE")
    print("=" * 80)
    
    try:
        stats_response = requests.get(
            f"{BACKEND_URL}/admin/stats?password={ADMIN_PASSWORD}",
            timeout=10
        )
        
        if stats_response.status_code != 200:
            log_test("Action 9: Lifetime Revenue", False, f"HTTP {stats_response.status_code}: {stats_response.text}")
            return
        
        data = stats_response.json()
        
        # Verify required fields
        required_fields = ["revenue_total_lifetime", "revenue_lifetime_breakdown", "revenue_24h_breakdown"]
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            log_test("Action 9: Lifetime Revenue", False, f"Missing required fields: {missing_fields}. Response keys: {list(data.keys())}")
            return
        
        log_test(
            "Action 9: Lifetime Revenue",
            True,
            f"All required fields present: revenue_total_lifetime={data['revenue_total_lifetime']}, revenue_lifetime_breakdown={data['revenue_lifetime_breakdown']}, revenue_24h_breakdown={data['revenue_24h_breakdown']}"
        )
        
    except Exception as e:
        log_test("Action 9: Lifetime Revenue", False, f"Exception: {str(e)}")

def main():
    """Run all admin endpoint tests"""
    print("\n" + "=" * 80)
    print("ADMIN/MODERATION ENDPOINTS TESTING")
    print("Backend URL:", BACKEND_URL)
    print("Admin Password:", ADMIN_PASSWORD)
    print("=" * 80 + "\n")
    
    # Run all 9 actions
    test_action_1_suspend_outsider()
    test_action_2_ban_device()
    boost_id = test_action_3_grant_booster()
    test_action_4_expire_booster(boost_id)
    test_action_5_activity_recent()
    test_action_6_audit_log()
    test_action_7_selective_vote_invalidation()
    test_action_8_extended_stats()
    test_action_9_lifetime_revenue()
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    success_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {success_rate:.1f}%\n")
    
    # Show failed tests
    failed_tests = [r for r in test_results if not r["passed"]]
    if failed_tests:
        print("FAILED TESTS:")
        for r in failed_tests:
            print(f"  ❌ {r['test']}")
            if r["details"]:
                print(f"     {r['details']}")
    else:
        print("✅ ALL TESTS PASSED!")
    
    print("\n" + "=" * 80 + "\n")

if __name__ == "__main__":
    main()
