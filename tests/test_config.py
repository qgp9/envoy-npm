import unittest
import os
from unittest.mock import patch, MagicMock
import logging

from envoy_npm.config import load_config, setup_logging, EnvoyConfig


class TestConfig(unittest.TestCase):

    @patch.dict(os.environ, {
        "NPM_API_URL": "http://test-npm:81",
        "NPM_API_EMAIL": "test@test.com",
        "NPM_API_PASSWORD": "password123",
        "LOG_LEVEL": "DEBUG",
        "MAX_RETRIES": "5",
        "SYNC_INTERVAL": "300"
    })
    def test_load_config_from_env(self):
        """Test that config is loaded correctly from environment variables."""
        config = load_config()
        self.assertEqual(config.npm_api_url, "http://test-npm:81")
        self.assertEqual(config.npm_api_email, "test@test.com")
        self.assertEqual(config.npm_api_password, "password123")
        self.assertEqual(config.log_level, "DEBUG")
        self.assertEqual(config.max_retries, 5)
        self.assertEqual(config.sync_interval, 300)
        # Check default for unset value
        self.assertEqual(config.retry_delay, 5)

    @patch.dict(os.environ, {"NPM_API_EMAIL": "test@test.com"}, clear=True)
    def test_load_config_missing_required_vars(self):
        """Test that ValueError is raised if required environment variables are missing."""
        with self.assertRaises(ValueError) as cm:
            load_config()
        self.assertIn("NPM_API_URL", str(cm.exception))
        self.assertIn("NPM_API_PASSWORD", str(cm.exception))

    @patch('logging.basicConfig')
    def test_setup_logging_levels(self, mock_basic_config):
        """Test that logging is configured with the correct level."""
        setup_logging("DEBUG")
        mock_basic_config.assert_called_with(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        setup_logging("INVALID_LEVEL")
        mock_basic_config.assert_called_with(
            level=logging.INFO, # Should default to INFO
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )


if __name__ == '__main__':
    unittest.main()
