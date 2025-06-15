import unittest
from unittest.mock import MagicMock, patch, call
import logging
import json # Added for potential future use with json.JSONDecodeError

from envoy_npm.npm_api import NPMApiClient
from envoy_npm.config import EnvoyConfig

# Configure logger for testing to capture log messages
logger = logging.getLogger('envoy_npm.npm_api')
logger.setLevel(logging.DEBUG) # Ensure all levels are captured

class TestNPMApiClient(unittest.TestCase):

    def setUp(self):
        self.mock_config = MagicMock(spec=EnvoyConfig)
        self.mock_config.npm_api_url = "http://mock-npm.com/api"
        self.mock_config.npm_api_email = "test@example.com"
        self.mock_config.npm_api_password = "password"
        self.mock_config.max_retries = 1 # Keep retries low for tests
        self.mock_config.retry_delay = 0.1

        self.client = NPMApiClient(
            api_url=self.mock_config.npm_api_url,
            email=self.mock_config.npm_api_email,
            password=self.mock_config.npm_api_password,
            max_retries=self.mock_config.max_retries,
            retry_delay=self.mock_config.retry_delay
        )
        # Mock the _login method to prevent actual login attempts during tests
        self.client.token = "fake_token" # Simulate token is already acquired
        self.client.session.headers.update({"Authorization": f"Bearer {self.client.token}"}) # Simulate session header is set
        # Mock _login to prevent actual calls during tests, especially if _make_request tries to re-login
        self.client._login = MagicMock(return_value=True) # Ensure it returns True if called

    @patch('envoy_npm.npm_api.requests.Session.request')
    def test_create_proxy_host_success(self, mock_session_request):
        """Test create_proxy_host successfully creates a host."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 123, "domain_names": ["test.com"]}
        mock_session_request.return_value = mock_response

        host_data = {"domain_names": ["test.com"], "forward_scheme": "http", "forward_host": "1.2.3.4", "forward_port": 80}
        with self.assertLogs(logger, level='INFO') as log_cm:
            result_id = self.client.create_proxy_host(host_data)
        
        self.assertEqual(result_id, 123)
        mock_session_request.assert_called_once_with(
            "POST", 
            f"{self.client.api_url}/nginx/proxy-hosts", 
            json=host_data,
            timeout=30 # Default timeout from _make_request
        )
        self.assertIn("프록시 호스트 생성 성공: ID 123", "\n".join(log_cm.output))

    @patch('envoy_npm.npm_api.requests.Session.request')
    def test_create_proxy_host_failure_400(self, mock_session_request):
        """Test create_proxy_host handles 400 error with detailed logging."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {
                "message": "Validation failed",
                "errors": [{"field": "domain_names", "message": "Is required"}]
            }
        }
        mock_session_request.return_value = mock_response

        host_data = {"forward_scheme": "http", "forward_host": "1.2.3.4", "forward_port": 80} # Missing domain_names
        with self.assertLogs(logger, level='ERROR') as log_cm:
            result_id = self.client.create_proxy_host(host_data)

        self.assertIsNone(result_id)
        self.assertIn("프록시 호스트 생성 실패: 상태 코드 400", "\n".join(log_cm.output))
        self.assertIn("API 오류 메시지: Validation failed", "\n".join(log_cm.output))
        self.assertIn("필드 'domain_names': Is required", "\n".join(log_cm.output))

    @patch('envoy_npm.npm_api.requests.Session.request')
    def test_create_proxy_host_failure_other_status(self, mock_session_request):
        """Test create_proxy_host handles non-201/400 failure."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.json.side_effect = json.JSONDecodeError # Simulate non-JSON response
        mock_session_request.return_value = mock_response

        host_data = {"domain_names": ["test.com"], "forward_scheme": "http", "forward_host": "1.2.3.4", "forward_port": 80}
        with self.assertLogs(logger, level='ERROR') as log_cm:
            result_id = self.client.create_proxy_host(host_data)
        
        self.assertIsNone(result_id)
        self.assertIn("프록시 호스트 생성 실패: 상태 코드 500", "\n".join(log_cm.output))
        self.assertIn("응답 내용: Internal Server Error", "\n".join(log_cm.output))

    @patch('envoy_npm.npm_api.requests.Session.request')
    def test_update_proxy_host_success(self, mock_session_request):
        """Test update_proxy_host successfully updates a host."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "enabled": False}
        mock_session_request.return_value = mock_response

        host_id = 1
        host_data = {"enabled": False}
        with self.assertLogs(logger, level='INFO') as log_cm:
            success = self.client.update_proxy_host(host_id, host_data)
        
        self.assertTrue(success)
        mock_session_request.assert_called_once_with(
            "PUT",
            f"{self.client.api_url}/nginx/proxy-hosts/{host_id}",
            json=host_data,
            timeout=30 # Default timeout from _make_request
        )
        self.assertIn(f"프록시 호스트 업데이트 성공: ID {host_id}", "\n".join(log_cm.output))

    @patch('envoy_npm.npm_api.requests.Session.request')
    def test_update_proxy_host_failure_400(self, mock_session_request):
        """Test update_proxy_host handles 400 error with detailed logging."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {"message": "Invalid data", "errors": [{"field": "forward_port", "message": "Must be int"}]}
        }
        mock_session_request.return_value = mock_response

        host_id = 1
        host_data = {"forward_port": "not-an-int"}
        with self.assertLogs(logger, level='ERROR') as log_cm:
            success = self.client.update_proxy_host(host_id, host_data)

        self.assertFalse(success)
        self.assertIn(f"프록시 호스트 업데이트 실패: ID {host_id}, 상태 코드 400", "\n".join(log_cm.output))
        self.assertIn("API 오류 메시지: Invalid data", "\n".join(log_cm.output))
        self.assertIn("필드 'forward_port': Must be int", "\n".join(log_cm.output))

    @patch('envoy_npm.npm_api.requests.Session.request')
    def test_update_proxy_host_failure_other_status(self, mock_session_request):
        """Test update_proxy_host handles non-200/400 failure."""
        mock_response = MagicMock()
        mock_response.status_code = 404 # Not Found
        mock_response.text = "Host not found"
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0) # Simulate non-JSON response
        mock_session_request.return_value = mock_response

        host_id = 999
        host_data = {"enabled": True}
        with self.assertLogs(logger, level='ERROR') as log_cm:
            success = self.client.update_proxy_host(host_id, host_data)
        
        self.assertFalse(success)
        self.assertIn(f"프록시 호스트 업데이트 실패: ID {host_id}, 상태 코드 404", "\n".join(log_cm.output))
        self.assertIn("응답 내용: Host not found", "\n".join(log_cm.output))

if __name__ == '__main__':
    unittest.main()
