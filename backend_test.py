#!/usr/bin/env python3
"""
Comprehensive Backend API Tests for Popularity App
Tests all endpoints with focus on voting functionality and edge cases
"""

import requests
import json
import uuid
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Backend URL from frontend env
BACKEND_URL = "https://public-opinion.preview.emergentagent.com/api"

class PopularityAPITester:
    def __init__(self):
        self.base_url = BACKEND_URL
        self.device_id = str(uuid.uuid4())
        self.test_results = []
        self.created_person_id = None
        
    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = f"{status} {test_name}"
        if details:
            result += f" - {details}"
        print(result)
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
        
    def test_api_health(self):
        """Test basic API connectivity"""
        try:
            response = requests.get(f"{self.base_url}/", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}, Response: {response.text[:100]}"
            self.log_result("API Health Check", success, details)
            return success
        except Exception as e:
            self.log_result("API Health Check", False, f"Connection error: {str(e)}")
            return False
            
    def test_seed_and_list_people(self):
        """Test 1: Seeding and listing people"""
        try:
            # Test basic listing
            response = requests.get(f"{self.base_url}/people", timeout=10)
            if response.status_code != 200:
                self.log_result("List People", False, f"Status: {response.status_code}")
                return False
                
            people = response.json()
            if not isinstance(people, list) or len(people) == 0:
                self.log_result("List People - Seeded Data", False, "No seeded people found")
                return False
                
            # Test case-insensitive query filter
            response = requests.get(f"{self.base_url}/people?query=elon", timeout=10)
            if response.status_code != 200:
                self.log_result("List People - Query Filter", False, f"Status: {response.status_code}")
                return False
                
            filtered = response.json()
            elon_found = any("elon" in person["name"].lower() for person in filtered)
            
            self.log_result("List People - Seeded Data", True, f"Found {len(people)} people")
            self.log_result("List People - Query Filter", elon_found, f"Case-insensitive search: {len(filtered)} results")
            return True
            
        except Exception as e:
            self.log_result("List People", False, f"Error: {str(e)}")
            return False
            
    def test_add_person(self):
        """Test 2: Add person functionality"""
        try:
            # Test creating new person
            new_person = {
                "name": "Test Celebrity",
                "category": "culture"
            }
            
            response = requests.post(f"{self.base_url}/people", 
                                   json=new_person, timeout=10)
            if response.status_code != 200:
                self.log_result("Add Person - Create New", False, f"Status: {response.status_code}")
                return False
                
            person_data = response.json()
            self.created_person_id = person_data["id"]
            
            # Test duplicate slug returns existing
            response2 = requests.post(f"{self.base_url}/people", 
                                    json=new_person, timeout=10)
            if response2.status_code != 200:
                self.log_result("Add Person - Duplicate Slug", False, f"Status: {response2.status_code}")
                return False
                
            person_data2 = response2.json()
            is_same_person = person_data["id"] == person_data2["id"]
            
            self.log_result("Add Person - Create New", True, f"Created person ID: {self.created_person_id}")
            self.log_result("Add Person - Duplicate Slug", is_same_person, "Returns existing person")
            return True
            
        except Exception as e:
            self.log_result("Add Person", False, f"Error: {str(e)}")
            return False
            
    def test_voting_comprehensive(self):
        """Test 3: Comprehensive voting functionality"""
        if not self.created_person_id:
            self.log_result("Voting Tests", False, "No test person available")
            return False
            
        try:
            person_id = self.created_person_id
            headers = {"X-Device-ID": self.device_id}
            
            # Test missing X-Device-ID header
            response = requests.post(f"{self.base_url}/people/{person_id}/vote",
                                   json={"value": 1}, timeout=10)
            missing_header_test = response.status_code == 400
            self.log_result("Voting - Missing X-Device-ID", missing_header_test, 
                          f"Status: {response.status_code}")
            
            # Test first vote (like)
            response = requests.post(f"{self.base_url}/people/{person_id}/vote",
                                   json={"value": 1}, headers=headers, timeout=10)
            if response.status_code != 200:
                self.log_result("Voting - First Vote", False, f"Status: {response.status_code}")
                return False
                
            vote_result1 = response.json()
            first_vote_correct = (vote_result1["likes"] == 1 and 
                                vote_result1["dislikes"] == 0 and
                                vote_result1["total_votes"] == 1 and
                                vote_result1["voted_value"] == 1)
            
            self.log_result("Voting - First Vote (Like)", first_vote_correct,
                          f"Likes: {vote_result1['likes']}, Total: {vote_result1['total_votes']}")
            
            # Test repeat same vote (idempotent)
            response = requests.post(f"{self.base_url}/people/{person_id}/vote",
                                   json={"value": 1}, headers=headers, timeout=10)
            vote_result2 = response.json()
            idempotent_test = (vote_result2["likes"] == vote_result1["likes"] and
                             vote_result2["total_votes"] == vote_result1["total_votes"])
            
            self.log_result("Voting - Idempotent Same Vote", idempotent_test,
                          f"Likes unchanged: {vote_result2['likes']}")
            
            # Test switching vote (like to dislike)
            response = requests.post(f"{self.base_url}/people/{person_id}/vote",
                                   json={"value": -1}, headers=headers, timeout=10)
            vote_result3 = response.json()
            switch_test = (vote_result3["likes"] == 0 and 
                         vote_result3["dislikes"] == 1 and
                         vote_result3["total_votes"] == 1 and
                         vote_result3["voted_value"] == -1)
            
            self.log_result("Voting - Switch Vote", switch_test,
                          f"Likes: {vote_result3['likes']}, Dislikes: {vote_result3['dislikes']}")
            
            # Test score adjustment
            score_adjusted = vote_result3["score"] == 99.0  # Initial 100 + 1 - 2 = 99
            self.log_result("Voting - Score Adjustment", score_adjusted,
                          f"Score: {vote_result3['score']}")
            
            return True
            
        except Exception as e:
            self.log_result("Voting Tests", False, f"Error: {str(e)}")
            return False
            
    def test_chart_functionality(self):
        """Test 4: Chart data functionality"""
        if not self.created_person_id:
            self.log_result("Chart Tests", False, "No test person available")
            return False
            
        try:
            person_id = self.created_person_id
            
            # Test valid windows
            for window in ["60m", "24h"]:
                response = requests.get(f"{self.base_url}/people/{person_id}/chart?window={window}",
                                      timeout=10)
                if response.status_code != 200:
                    self.log_result(f"Chart - {window} Window", False, f"Status: {response.status_code}")
                    continue
                    
                chart_data = response.json()
                has_required_fields = all(key in chart_data for key in ["id", "name", "points"])
                has_points = isinstance(chart_data["points"], list)
                
                self.log_result(f"Chart - {window} Window", has_required_fields and has_points,
                              f"Points: {len(chart_data['points'])}")
            
            # Test invalid window
            response = requests.get(f"{self.base_url}/people/{person_id}/chart?window=invalid",
                                  timeout=10)
            invalid_window_test = response.status_code == 400
            self.log_result("Chart - Invalid Window", invalid_window_test,
                          f"Status: {response.status_code}")
            
            # Test invalid person ID
            response = requests.get(f"{self.base_url}/people/invalid_id/chart",
                                  timeout=10)
            invalid_id_test = response.status_code == 400
            self.log_result("Chart - Invalid Person ID", invalid_id_test,
                          f"Status: {response.status_code}")
            
            return True
            
        except Exception as e:
            self.log_result("Chart Tests", False, f"Error: {str(e)}")
            return False
            
    def test_trends_functionality(self):
        """Test 5: Trends functionality"""
        try:
            # Test basic trends
            response = requests.get(f"{self.base_url}/trends?window=60m&limit=10", timeout=10)
            if response.status_code != 200:
                self.log_result("Trends - Basic", False, f"Status: {response.status_code}")
                return False
                
            trends = response.json()
            is_list = isinstance(trends, list)
            
            # Test ordering (should be by delta desc)
            if len(trends) > 1:
                ordered_correctly = all(trends[i].get("delta", 0) >= trends[i+1].get("delta", 0) 
                                      for i in range(len(trends)-1))
            else:
                ordered_correctly = True
                
            self.log_result("Trends - Basic", is_list, f"Found {len(trends)} trends")
            self.log_result("Trends - Ordering", ordered_correctly, "Ordered by delta desc")
            
            # Test limit
            response = requests.get(f"{self.base_url}/trends?window=24h&limit=5", timeout=10)
            if response.status_code == 200:
                limited_trends = response.json()
                limit_works = len(limited_trends) <= 5
                self.log_result("Trends - Limit", limit_works, f"Limited to {len(limited_trends)}")
            
            return True
            
        except Exception as e:
            self.log_result("Trends Tests", False, f"Error: {str(e)}")
            return False
            
    def test_search_tracking(self):
        """Test 6: Search tracking functionality"""
        try:
            headers = {"X-Device-ID": self.device_id}
            
            # Test empty query
            response = requests.post(f"{self.base_url}/searches",
                                   json={"query": ""}, headers=headers, timeout=10)
            empty_query_test = response.status_code == 400
            self.log_result("Search - Empty Query", empty_query_test,
                          f"Status: {response.status_code}")
            
            # Test valid search
            response = requests.post(f"{self.base_url}/searches",
                                   json={"query": "test search"}, headers=headers, timeout=10)
            valid_search = response.status_code == 200
            self.log_result("Search - Valid Query", valid_search,
                          f"Status: {response.status_code}")
            
            # Test search suggestions
            response = requests.get(f"{self.base_url}/search-suggestions?window=24h&limit=10",
                                  timeout=10)
            if response.status_code == 200:
                suggestions = response.json()
                has_terms = "terms" in suggestions and isinstance(suggestions["terms"], list)
                self.log_result("Search - Suggestions", has_terms,
                              f"Found {len(suggestions.get('terms', []))} suggestions")
            else:
                self.log_result("Search - Suggestions", False, f"Status: {response.status_code}")
            
            return True
            
        except Exception as e:
            self.log_result("Search Tests", False, f"Error: {str(e)}")
            return False
            
    def test_error_handling(self):
        """Test 7: Error handling"""
        try:
            # Test invalid person ID formats
            invalid_ids = ["invalid", "123", "not-an-objectid"]
            
            for invalid_id in invalid_ids:
                response = requests.get(f"{self.base_url}/people/{invalid_id}", timeout=10)
                if response.status_code == 400:
                    self.log_result(f"Error - Invalid ID ({invalid_id})", True, "Returns 400")
                else:
                    self.log_result(f"Error - Invalid ID ({invalid_id})", False, 
                                  f"Status: {response.status_code}")
            
            # Test non-existent person (valid ObjectId format)
            fake_id = "507f1f77bcf86cd799439011"  # Valid ObjectId format
            response = requests.get(f"{self.base_url}/people/{fake_id}", timeout=10)
            not_found_test = response.status_code == 404
            self.log_result("Error - Person Not Found", not_found_test,
                          f"Status: {response.status_code}")
            
            return True
            
        except Exception as e:
            self.log_result("Error Handling Tests", False, f"Error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print(f"🚀 Starting Popularity API Tests")
        print(f"Backend URL: {self.base_url}")
        print(f"Device ID: {self.device_id}")
        print("=" * 60)
        
        # Run tests in order
        if not self.test_api_health():
            print("❌ API not accessible, stopping tests")
            return False
            
        self.test_seed_and_list_people()
        self.test_add_person()
        self.test_voting_comprehensive()
        self.test_chart_functionality()
        self.test_trends_functionality()
        self.test_search_tracking()
        self.test_error_handling()
        
        # Summary
        print("=" * 60)
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"📊 TEST SUMMARY:")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        return failed_tests == 0

if __name__ == "__main__":
    tester = PopularityAPITester()
    success = tester.run_all_tests()
    exit(0 if success else 1)