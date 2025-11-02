"""
Tests for health check endpoints.

Verifies that the /health/live/ and /health/ready/ endpoints
are working correctly and checking dependencies as expected.
"""

from django.test import TestCase, Client
from django.http import JsonResponse
from django.urls import reverse
from django.db import connections
import json


class HealthCheckLiveTestCase(TestCase):
    """Tests for the liveness probe endpoint."""

    def setUp(self):
        self.client = Client()
        self.url = reverse("health_live")

    def test_health_live_endpoint_exists(self):
        """Test that the health live endpoint is accessible."""
        response = self.client.get(self.url)
        self.assertIn(response.status_code, [200, 500])  # Should return one of these

    def test_health_live_returns_200(self):
        """Test that the health live endpoint returns 200 when healthy."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_health_live_returns_json(self):
        """Test that the health live endpoint returns valid JSON."""
        response = self.client.get(self.url)
        try:
            data = json.loads(response.content)
            self.assertIn("status", data)
            self.assertEqual(data["status"], "alive")
            self.assertIn("timestamp", data)
        except json.JSONDecodeError:
            self.fail("Response is not valid JSON")

    def test_health_live_has_timestamp(self):
        """Test that the health live response includes a timestamp."""
        response = self.client.get(self.url)
        data = json.loads(response.content)
        self.assertIn("timestamp", data)
        # Verify it's a valid ISO format timestamp
        self.assertTrue(data["timestamp"].endswith("Z"))


class HealthCheckReadyTestCase(TestCase):
    """Tests for the readiness probe endpoint."""

    def setUp(self):
        self.client = Client()
        self.url = reverse("health_ready")

    def test_health_ready_endpoint_exists(self):
        """Test that the health ready endpoint is accessible."""
        response = self.client.get(self.url)
        self.assertIn(response.status_code, [200, 503])

    def test_health_ready_returns_200_when_ready(self):
        """Test that the health ready endpoint returns 200 when all systems are ready."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_health_ready_returns_json(self):
        """Test that the health ready endpoint returns valid JSON."""
        response = self.client.get(self.url)
        try:
            data = json.loads(response.content)
            self.assertIn("status", data)
            self.assertIn("checks", data)
            self.assertIn("timestamp", data)
        except json.JSONDecodeError:
            self.fail("Response is not valid JSON")

    def test_health_ready_has_required_checks(self):
        """Test that the health ready response includes all required checks."""
        response = self.client.get(self.url)
        data = json.loads(response.content)

        self.assertIn("checks", data)
        checks = data["checks"]

        # Verify all required checks are present
        self.assertIn("database", checks)
        self.assertIn("cache", checks)
        self.assertIn("config", checks)

    def test_health_ready_checks_have_status(self):
        """Test that each check has a status field."""
        response = self.client.get(self.url)
        data = json.loads(response.content)

        for check_name, check_data in data["checks"].items():
            self.assertIn("status", check_data, f"Check {check_name} missing status")
            self.assertIn("message", check_data, f"Check {check_name} missing message")

    def test_health_ready_database_check_passes(self):
        """Test that the database check passes when DB is available."""
        response = self.client.get(self.url)
        data = json.loads(response.content)

        db_check = data["checks"]["database"]
        self.assertEqual(db_check["status"], "ok")
        self.assertIn("Database", db_check["message"])

    def test_health_ready_config_check_passes(self):
        """Test that the configuration check passes."""
        response = self.client.get(self.url)
        data = json.loads(response.content)

        config_check = data["checks"]["config"]
        self.assertEqual(config_check["status"], "ok")
        self.assertIn("Configuration", config_check["message"])

    def test_health_ready_cache_check_present(self):
        """Test that the cache check is present."""
        response = self.client.get(self.url)
        data = json.loads(response.content)

        cache_check = data["checks"]["cache"]
        # Cache might be ok or show as unavailable - both are acceptable
        self.assertIn(cache_check["status"], ["ok", "error"])

    def test_health_ready_timestamp_format(self):
        """Test that the timestamp is in ISO format."""
        response = self.client.get(self.url)
        data = json.loads(response.content)

        timestamp = data["timestamp"]
        self.assertTrue(timestamp.endswith("Z"))
        # Verify it contains expected time components
        self.assertIn("T", timestamp)

    def test_health_ready_status_field_present(self):
        """Test that status field is either 'ready' or 'not_ready'."""
        response = self.client.get(self.url)
        data = json.loads(response.content)

        status = data["status"]
        self.assertIn(status, ["ready", "not_ready"])


class HealthCheckPermissionsTestCase(TestCase):
    """Tests that health check endpoints don't require authentication."""

    def setUp(self):
        self.client = Client()

    def test_health_live_no_authentication_required(self):
        """Test that health live endpoint is accessible without authentication."""
        response = self.client.get(reverse("health_live"))
        # Should not return 403 Forbidden
        self.assertNotEqual(response.status_code, 403)

    def test_health_ready_no_authentication_required(self):
        """Test that health ready endpoint is accessible without authentication."""
        response = self.client.get(reverse("health_ready"))
        # Should not return 403 Forbidden
        self.assertNotEqual(response.status_code, 403)

    def test_health_checks_with_invalid_method(self):
        """Test that health check endpoints only accept GET requests."""
        # Test POST method
        response = self.client.post(reverse("health_live"))
        self.assertEqual(response.status_code, 405)  # Method Not Allowed

        response = self.client.post(reverse("health_ready"))
        self.assertEqual(response.status_code, 405)  # Method Not Allowed
