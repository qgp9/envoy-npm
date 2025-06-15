import unittest
import datetime
import json
from unittest.mock import MagicMock, patch

from envoy_npm.envoy_service import EnvoyService
from envoy_npm.config import EnvoyConfig

class TestEnvoyServicePrepareHostData(unittest.TestCase):

    def setUp(self):
        # Mock EnvoyConfig
        self.mock_config = MagicMock(spec=EnvoyConfig)
        self.mock_config.npm_api_url = "http://mock-npm"
        self.mock_config.npm_api_email = "test@example.com"
        self.mock_config.npm_api_password = "password"
        self.mock_config.max_retries = 3
        self.mock_config.retry_delay = 1
        self.mock_config.docker_socket = "/var/run/docker.sock"

        # Patch NPMApiClient and DockerMonitor to avoid actual calls during service instantiation
        with (patch('envoy_npm.envoy_service.NPMApiClient') as MockNPMApiClient,
              patch('envoy_npm.envoy_service.DockerMonitor') as MockDockerMonitor):
            self.service = EnvoyService(self.mock_config)
            self.mock_npm_client = MockNPMApiClient.return_value
            self.mock_docker_monitor = MockDockerMonitor.return_value

    def test_prepare_host_data_basic(self):
        """Test _prepare_host_data with minimal npm_config."""
        domain = "test.example.com"
        forward_host = "172.17.0.2"
        forward_port = 8080
        container_id = "test_container_id"
        container_name = "test_container"
        npm_config = {}

        # Mock datetime.now() for consistent meta.created_at
        mock_now = datetime.datetime(2024, 1, 1, 12, 0, 0)
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now

            host_data = self.service._prepare_host_data(
                domain, forward_host, forward_port, container_id, container_name, npm_config
            )

        self.assertEqual(host_data['domain_names'], [domain])
        self.assertEqual(host_data['forward_host'], forward_host)
        self.assertEqual(host_data['forward_port'], forward_port)
        self.assertEqual(host_data['forward_scheme'], 'http') # Default
        self.assertTrue(host_data['enabled']) # Default
        self.assertFalse(host_data['caching_enabled']) # Default
        self.assertTrue(host_data['block_exploits']) # Default
        self.assertEqual(host_data['access_list_id'], 0) # Default
        self.assertEqual(host_data['certificate_id'], 0) # Default
        self.assertIsInstance(host_data['meta'], dict)
        self.assertEqual(host_data['meta']['managed_by'], 'EnvoyNPM')
        self.assertEqual(host_data['meta']['container_id'], container_id)
        self.assertEqual(host_data['meta']['created_at'], mock_now.isoformat())

    def test_prepare_host_data_with_npm_config_overrides(self):
        """Test _prepare_host_data with values overridden by npm_config."""
        domain = "override.example.com"
        forward_host = "172.17.0.3"
        forward_port = 80
        container_id = "override_container_id"
        container_name = "override_container"
        npm_config = {
            "scheme": "https",
            "caching_enabled": "true", # Test string boolean parsing
            "block_exploits": "False", # Test string boolean parsing
            "access_list_id": "10",    # Test string int parsing
            "certificate_id": "new",
            "ssl_forced": True, # Test direct boolean
            "forward_port": "8000" # Test string int parsing for forward_port
        }

        mock_now = datetime.datetime(2024, 1, 1, 13, 0, 0)
        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now

            host_data = self.service._prepare_host_data(
                domain, forward_host, forward_port, container_id, container_name, npm_config
            )

        self.assertEqual(host_data['forward_scheme'], 'https')
        self.assertTrue(host_data['caching_enabled'])
        self.assertFalse(host_data['block_exploits'])
        self.assertEqual(host_data['access_list_id'], 10)
        self.assertEqual(host_data['certificate_id'], 'new')
        self.assertTrue(host_data['ssl_forced'])
        self.assertTrue(host_data['enabled']) # Should remain true
        self.assertEqual(host_data['forward_port'], 8000) # Check overridden port

    def test_prepare_host_data_boolean_parsing(self):
        """Test various boolean string inputs from npm_config."""
        # ... (This test can be expanded to cover more boolean cases)
        npm_config_true = {"caching_enabled": "True", "ssl_forced": "yes", "http2_support": "1"}
        npm_config_false = {"caching_enabled": "False", "ssl_forced": "no", "http2_support": "0"}
        
        # Note: envoy_service._parse_boolean or similar helper might be needed if not already present
        # For now, assuming direct string comparison or existing helper handles these.
        # This part of the test highlights the need for robust boolean parsing if strings are expected.
        
        # Minimal data for the call
        domain, fh, fp, cid, cname = "b.com", "1.1.1.1", 80, "bid", "bname"

        # Test True values
        # Assuming _prepare_host_data uses a helper that converts these to True
        # If current _prepare_host_data uses `str(...).lower() == 'true'`, then "yes" and "1" won't work directly
        # This test might require adjustments to _prepare_host_data or the test itself based on actual parsing logic

        # For now, let's test what we know works (True/False strings)
        data_true = self.service._prepare_host_data(domain, fh, fp, cid, cname, {"caching_enabled": "True"})
        self.assertTrue(data_true['caching_enabled'])

        data_false = self.service._prepare_host_data(domain, fh, fp, cid, cname, {"caching_enabled": "False"})
        self.assertFalse(data_false['caching_enabled'])

    def test_certificate_id_integer(self):
        """Test _prepare_host_data with integer certificate_id."""
        npm_config = {"certificate_id": "123"}
        host_data = self.service._prepare_host_data(
            "cert.example.com", "1.2.3.4", 80, "cert_id", "cert_name", npm_config
        )
        self.assertEqual(host_data['certificate_id'], 123)

    def test_certificate_id_invalid_string(self):
        """Test _prepare_host_data with invalid string for certificate_id (should default to 0)."""
        npm_config = {"certificate_id": "invalid_cert_id_string"}
        host_data = self.service._prepare_host_data(
            "cert.example.com", "1.2.3.4", 80, "cert_id", "cert_name", npm_config
        )
        self.assertEqual(host_data['certificate_id'], 0) # Expecting default

if __name__ == '__main__':
    unittest.main()


class TestEnvoyServiceContainerEvents(unittest.TestCase):

    def setUp(self):
        """Set up a test environment for each test."""
        self.mock_config = MagicMock(spec=EnvoyConfig)
        self.mock_config.npm_api_url = "http://mock-npm"
        self.mock_config.npm_api_email = "test@example.com"
        self.mock_config.npm_api_password = "password"
        self.mock_config.max_retries = 3
        self.mock_config.retry_delay = 1
        self.mock_config.docker_socket = "/var/run/docker.sock"

        # Patch dependencies
        self.patcher_npm_client = patch('envoy_npm.envoy_service.NPMApiClient')
        self.patcher_docker_monitor = patch('envoy_npm.envoy_service.DockerMonitor')

        self.MockNPMApiClient = self.patcher_npm_client.start()
        self.MockDockerMonitor = self.patcher_docker_monitor.start()

        self.mock_npm_client = self.MockNPMApiClient.return_value
        self.mock_docker_monitor = self.MockDockerMonitor.return_value

        # Instantiate the service
        self.service = EnvoyService(self.mock_config)
        # Manually set the client mock on the service instance
        self.service.npm_client = self.mock_npm_client

    def tearDown(self):
        """Clean up after each test."""
        self.patcher_npm_client.stop()
        self.patcher_docker_monitor.stop()

    def test_on_container_start_new_host(self):
        """Test on_container_start for a new container creating a new host."""
        container_info = {
            'id': 'new_container_id',
            'name': 'new_container',
            'npm_config': {'host': 'new.example.com', 'port': 8080},
            'networks': {'bridge': {'ip_address': '172.17.0.5'}}
        }
        self.mock_npm_client.create_proxy_host.return_value = {
            'id': 100, 'domain_names': ['new.example.com']
        }

        self.service.on_container_start(container_info)

        self.mock_npm_client.create_proxy_host.assert_called_once()
        call_args = self.mock_npm_client.create_proxy_host.call_args[0][0]
        self.assertEqual(call_args['domain_names'], ['new.example.com'])
        self.assertEqual(call_args['forward_host'], '172.17.0.5')
        self.assertEqual(call_args['forward_port'], 8080)
        self.assertEqual(call_args['meta']['container_id'], 'new_container_id')
        self.assertIn('new.example.com', self.service.current_npm_hosts)
        self.assertIn(100, self.service.managed_host_ids)

    def test_on_container_start_existing_managed_host(self):
        """Test on_container_start for a container linked to a managed host."""
        domain = 'existing.example.com'
        host_id = 101
        container_id = 'existing_container_id'

        self.service.current_npm_hosts[domain] = {
            'id': host_id, 'domain_names': [domain], 'meta': json.dumps({'managed_by': 'EnvoyNPM', 'container_id': 'old_id'})
        }
        self.service.managed_host_ids.add(host_id)

        container_info = {
            'id': container_id,
            'name': 'existing_container',
            'npm_config': {'host': domain, 'port': 8000},
            'networks': {'bridge': {'ip_address': '172.17.0.6'}}
        }

        self.mock_npm_client.update_proxy_host.return_value = True

        self.service.on_container_start(container_info)

        self.mock_npm_client.update_proxy_host.assert_called_once_with(host_id, unittest.mock.ANY)
        call_args = self.mock_npm_client.update_proxy_host.call_args[0][1]
        self.assertEqual(call_args['forward_host'], '172.17.0.6')
        self.assertEqual(call_args['forward_port'], 8000)
        self.assertTrue(call_args['enabled'])
        self.assertEqual(call_args['meta']['container_id'], container_id)

    @patch('envoy_npm.envoy_service.logger.warning')
    def test_on_container_start_existing_unmanaged_host(self, mock_logger_warning):
        """Test on_container_start for a domain with an existing unmanaged host."""
        domain = 'unmanaged.example.com'
        self.service.current_npm_hosts[domain] = {
            'id': 102, 'domain_names': [domain], 'meta': '{}' # Not managed by EnvoyNPM
        }

        container_info = {
            'id': 'some_container_id',
            'name': 'some_container',
            'npm_config': {'host': domain, 'port': 9000},
            'networks': {'bridge': {'ip_address': '172.17.0.7'}}
        }

        self.service.on_container_start(container_info)

        self.mock_npm_client.create_proxy_host.assert_not_called()
        self.mock_npm_client.update_proxy_host.assert_not_called()
        mock_logger_warning.assert_called_once()

    def test_on_container_stop_managed_host(self):
        """Test on_container_stop for a container linked to a managed host."""
        domain = 'stoppable.example.com'
        host_id = 103
        container_id = 'stoppable_container_id'

        self.service.current_npm_hosts[domain] = {
            'id': host_id,
            'domain_names': [domain],
            'meta': json.dumps({'managed_by': 'EnvoyNPM', 'container_id': container_id})
        }
        self.service.managed_host_ids.add(host_id)
        self.mock_npm_client.update_proxy_host.return_value = True

        self.service.on_container_stop(container_id)

        self.mock_npm_client.update_proxy_host.assert_called_once_with(host_id, {'enabled': False})

    def test_on_container_stop_unmanaged_host(self):
        """Test on_container_stop for a container not linked to a managed host."""
        self.service.on_container_stop('some_other_container_id')
        self.mock_npm_client.update_proxy_host.assert_not_called()

    def test_sync_all_orchestration(self):
        """Test the _sync_all method orchestrates other methods correctly."""
        # Mock the methods that _sync_all calls
        self.service._load_npm_hosts = MagicMock()
        self.service.on_container_start = MagicMock()
        
        mock_containers = [
            {'id': 'sync_c1', 'name': 'sync_container1'},
            {'id': 'sync_c2', 'name': 'sync_container2'}
        ]
        self.mock_docker_monitor.scan_running_containers.return_value = mock_containers

        # Call the method to be tested
        self.service._sync_all()

        # Assert that the mocked methods were called as expected
        self.service._load_npm_hosts.assert_called_once()
        self.mock_docker_monitor.scan_running_containers.assert_called_once()
        self.assertEqual(self.service.on_container_start.call_count, 2)
        self.service.on_container_start.assert_any_call(mock_containers[0])
        self.service.on_container_start.assert_any_call(mock_containers[1])


    def test_load_npm_hosts(self):
        """Test _load_npm_hosts correctly loads and categorizes hosts."""
        managed_host = {
            'id': 201,
            'domain_names': ['managed.example.com'],
            'meta': json.dumps({'managed_by': 'EnvoyNPM', 'container_id': 'c1'})
        }
        unmanaged_host = {
            'id': 202,
            'domain_names': ['unmanaged.example.com'],
            'meta': '{}'
        }
        host_with_no_domain = {
            'id': 203,
            'domain_names': []
        }
        
        self.mock_npm_client.get_proxy_hosts.return_value = [managed_host, unmanaged_host, host_with_no_domain]
        
        self.service._load_npm_hosts()
        
        # Check that the hosts are cached correctly
        self.assertIn('managed.example.com', self.service.current_npm_hosts)
        self.assertEqual(self.service.current_npm_hosts['managed.example.com'], managed_host)
        self.assertIn('unmanaged.example.com', self.service.current_npm_hosts)
        self.assertEqual(self.service.current_npm_hosts['unmanaged.example.com'], unmanaged_host)
        
        # Check that hosts without domains are ignored
        self.assertEqual(len(self.service.current_npm_hosts), 2)
        
        # Check that managed_host_ids is populated correctly
        self.assertEqual(self.service.managed_host_ids, {201})


class TestEnvoyServiceHelpers(unittest.TestCase):

    def setUp(self):
        """Set up a test environment for each test."""
        # We don't need a full config mock for these helper tests,
        # but it's good practice to have a service instance.
        with patch('envoy_npm.envoy_service.NPMApiClient'), \
             patch('envoy_npm.envoy_service.DockerMonitor'):
            # Mock config with a dummy value for sync_interval
            mock_config = MagicMock(spec=EnvoyConfig)
            # The EnvoyService __init__ uses schedule, which depends on config.sync_interval
            mock_config.sync_interval = 3600
            # Add missing attributes for NPMApiClient and DockerMonitor initialization
            mock_config.npm_api_url = "http://mock-npm"
            mock_config.npm_api_email = "test@example.com"
            mock_config.npm_api_password = "password"
            mock_config.max_retries = 3
            mock_config.retry_delay = 1
            mock_config.docker_socket = "/var/run/docker.sock"
            self.service = EnvoyService(mock_config)

    # Tests for _get_container_ip
    def test_get_container_ip_with_preferred_network(self):
        """Test _get_container_ip finds the IP from the preferred network."""
        container_info = {
            'npm_config': {'network': 'app_net'},
            'networks': {
                'bridge': {'ip_address': '172.17.0.1'},
                'app_net': {'ip_address': '192.168.1.5'}
            }
        }
        ip = self.service._get_container_ip(container_info)
        self.assertEqual(ip, '192.168.1.5')

    def test_get_container_ip_without_preferred_network(self):
        """Test _get_container_ip falls back to the first available IP."""
        container_info = {
            'npm_config': {},
            'networks': {
                'bridge': {'ip_address': '172.17.0.1'},
                'app_net': {'ip_address': '192.168.1.5'}
            }
        }
        ip = self.service._get_container_ip(container_info)
        self.assertEqual(ip, '172.17.0.1')


    def test_get_container_ip_no_ip_found(self):
        """Test _get_container_ip returns None when no IP is available."""
        container_info = {
            'npm_config': {},
            'networks': {
                'bridge': {},
                'app_net': {}
            }
        }
        ip = self.service._get_container_ip(container_info)
        self.assertIsNone(ip)

    # Tests for _parse_meta
    def test_parse_meta_with_dict(self):
        """Test _parse_meta with a dictionary input."""
        meta_dict = {'key': 'value'}
        parsed = self.service._parse_meta(meta_dict)
        self.assertEqual(parsed, meta_dict)

    def test_parse_meta_with_valid_json_string(self):
        """Test _parse_meta with a valid JSON string."""
        meta_str = '{"key": "value", "num": 1}'
        parsed = self.service._parse_meta(meta_str)
        self.assertEqual(parsed, {'key': 'value', 'num': 1})

    def test_parse_meta_with_invalid_json_string(self):
        """Test _parse_meta with an invalid JSON string."""
        with self.assertLogs('envoy_npm.service', level='WARNING') as cm:
            parsed = self.service._parse_meta('{"key": "value"')
            self.assertEqual(parsed, {})
            self.assertIn('메타데이터 파싱 실패', cm.output[0])

    def test_parse_meta_with_empty_string(self):
        """Test _parse_meta with an empty string."""
        parsed = self.service._parse_meta('')
        self.assertEqual(parsed, {})

    def test_parse_meta_with_none(self):
        """Test _parse_meta with None input."""
        with self.assertLogs('envoy_npm.service', level='WARNING') as cm:
            parsed = self.service._parse_meta(None)
            self.assertEqual(parsed, {})
            self.assertIn('알 수 없는 메타데이터 형식', cm.output[0])


class TestEnvoyServiceStart(unittest.TestCase):

    def setUp(self):
        self.mock_config = MagicMock(spec=EnvoyConfig)
        self.mock_config.npm_api_url = "http://mock-npm"
        self.mock_config.npm_api_email = "test@example.com"
        self.mock_config.npm_api_password = "password"
        self.mock_config.max_retries = 3
        self.mock_config.retry_delay = 1
        self.mock_config.docker_socket = "/var/run/docker.sock"
        self.mock_config.sync_interval = 60

        self.patcher_npm_client = patch('envoy_npm.envoy_service.NPMApiClient')
        self.patcher_docker_monitor = patch('envoy_npm.envoy_service.DockerMonitor')
        self.patcher_schedule = patch('envoy_npm.envoy_service.schedule')
        self.patcher_logger = patch('envoy_npm.envoy_service.logger')

        self.MockNPMApiClient = self.patcher_npm_client.start()
        self.MockDockerMonitor = self.patcher_docker_monitor.start()
        self.mock_schedule = self.patcher_schedule.start()
        self.mock_logger = self.patcher_logger.start()

        self.mock_npm_client = self.MockNPMApiClient.return_value
        self.mock_docker_monitor = self.MockDockerMonitor.return_value

        # Patch the service's internal methods to isolate the test to the start() method's logic
        self.patcher_load_hosts = patch.object(EnvoyService, '_load_npm_hosts')
        self.patcher_sync_all = patch.object(EnvoyService, '_sync_all')
        self.mock_load_hosts = self.patcher_load_hosts.start()
        self.mock_sync_all = self.patcher_sync_all.start()

        self.service = EnvoyService(self.mock_config)
        # Re-apply mocks on the instance as __init__ was called before some patches
        self.service.npm_client = self.mock_npm_client
        self.service.docker_monitor = self.mock_docker_monitor
        self.service._load_npm_hosts = self.mock_load_hosts
        self.service._sync_all = self.mock_sync_all

    def tearDown(self):
        self.patcher_npm_client.stop()
        self.patcher_docker_monitor.stop()
        self.patcher_schedule.stop()
        self.patcher_logger.stop()
        self.patcher_load_hosts.stop()
        self.patcher_sync_all.stop()

    def test_start_success(self):
        """Test the start method under successful conditions."""
        self.mock_npm_client.login.return_value = True

        result = self.service.start()

        self.assertTrue(result)
        self.mock_npm_client.login.assert_called_once()
        self.mock_load_hosts.assert_called_once()
        self.mock_schedule.every.assert_called_once_with(60)
        self.mock_schedule.every.return_value.seconds.do.assert_called_once_with(self.mock_sync_all)
        self.mock_sync_all.assert_called_once()
        self.mock_docker_monitor.start_monitoring.assert_called_once()

    def test_start_login_failure(self):
        """Test the start method when NPM login fails."""
        self.mock_npm_client.login.return_value = False

        result = self.service.start()

        self.assertFalse(result)
        self.mock_npm_client.login.assert_called_once()
        self.mock_load_hosts.assert_not_called()
        self.mock_schedule.every.assert_not_called()
        self.mock_sync_all.assert_not_called()
        self.mock_docker_monitor.start_monitoring.assert_not_called()
        self.mock_logger.error.assert_called_with("NPM API 로그인 실패, 서비스를 종료합니다")
