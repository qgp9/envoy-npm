import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from docker.models.containers import Container
from docker.errors import NotFound

from envoy_npm.docker_monitor import DockerMonitor


class TestDockerMonitorHelpers(unittest.TestCase):

    def setUp(self):
        # Patch the Docker client during initialization for all tests
        with patch('docker.DockerClient'), patch('docker.from_env'):
            self.monitor = DockerMonitor()

    def test_parse_container_env(self):
        """Test parsing of container environment variables."""
        mock_container = MagicMock(spec=Container)
        mock_container.attrs = {
            'Config': {
                'Env': [
                    'PATH=/usr/bin',
                    'NPM_HOST=test.com',
                    'EMPTY_VAR=',
                    'NO_VALUE'
                ]
            }
        }
        env = self.monitor._parse_container_env(mock_container)
        self.assertEqual(env, {
            'PATH': '/usr/bin',
            'NPM_HOST': 'test.com',
            'EMPTY_VAR': ''
        })

    def test_extract_npm_env_success(self):
        """Test successful extraction of NPM configuration from environment variables."""
        env_dict = {
            'NPM_HOST': 'test.example.com',
            'NPM_PORT': '8080',
            'NPM_SSL': 'true',
            'NPM_ENABLE_WS': 'True',
            'NPM_NETWORK': 'my_app_net',
            'NPM_ADVANCED_CONFIG': 'custom_setting' 
        }
        npm_config = self.monitor._extract_npm_env(env_dict)
        self.assertIsNotNone(npm_config)
        self.assertEqual(npm_config['host'], 'test.example.com')
        self.assertEqual(npm_config['port'], 8080)
        self.assertTrue(npm_config['ssl'])
        self.assertTrue(npm_config['enable_ws'])
        self.assertEqual(npm_config['network'], 'my_app_net')
        self.assertEqual(npm_config['advanced_config'], 'custom_setting')

    def test_extract_npm_env_missing_required(self):
        """Test that None is returned if required NPM variables are missing."""
        self.assertIsNone(self.monitor._extract_npm_env({'NPM_PORT': '8080'}))
        self.assertIsNone(self.monitor._extract_npm_env({'NPM_HOST': 'test.com'}))
        self.assertIsNone(self.monitor._extract_npm_env({}))

    def test_get_container_networks(self):
        """Test parsing of container network information."""
        mock_container = MagicMock(spec=Container)
        mock_container.attrs = {
            'NetworkSettings': {
                'Networks': {
                    'bridge': {
                        'IPAddress': '172.17.0.2',
                        'Gateway': '172.17.0.1',
                        'NetworkID': 'net1'
                    },
                    'host': {
                        'IPAddress': '',
                        'Gateway': '',
                        'NetworkID': 'net2'
                    }
                }
            }
        }
        networks = self.monitor._get_container_networks(mock_container)
        self.assertIn('bridge', networks)
        self.assertEqual(networks['bridge']['ip_address'], '172.17.0.2')
        self.assertIn('host', networks)
        self.assertEqual(networks['host']['ip_address'], '')

if __name__ == '__main__':
    unittest.main()


class TestDockerMonitorCoreFunctions(unittest.TestCase):

    def setUp(self):
        # Patch the Docker client during initialization
        self.patcher_client = patch('docker.DockerClient')
        self.patcher_from_env = patch('docker.from_env')
        self.MockDockerClient = self.patcher_client.start()
        self.MockFromEnv = self.patcher_from_env.start()
        
        # Create a mock client instance
        self.mock_client = self.MockDockerClient.return_value
        self.monitor = DockerMonitor()
        self.monitor.client = self.mock_client # Ensure the instance uses the mock

    def tearDown(self):
        self.patcher_client.stop()
        self.patcher_from_env.stop()

    def _create_mock_container(self, container_id, name, env_vars, networks):
        mock_container = MagicMock(spec=Container)
        mock_container.id = container_id
        mock_container.name = name
        mock_container.attrs = {
            'Config': {'Env': env_vars},
            'NetworkSettings': {'Networks': networks}
        }
        # Mock image property
        mock_image = PropertyMock()
        mock_image.tags = [f'{name}:latest']
        type(mock_container).image = mock_image
        return mock_container

    def test_get_container_info_success(self):
        """Test get_container_info for a container with NPM config."""
        mock_container = self._create_mock_container(
            'c1', 'test-app', 
            ['NPM_HOST=app.com', 'NPM_PORT=80'],
            {'bridge': {'IPAddress': '172.18.0.3'}}
        )
        self.mock_client.containers.get.return_value = mock_container

        info = self.monitor.get_container_info('c1')

        self.assertIsNotNone(info)
        self.assertEqual(info['id'], 'c1')
        self.assertEqual(info['name'], 'test-app')
        self.assertIn('npm_config', info)
        self.assertEqual(info['npm_config']['host'], 'app.com')

    def test_get_container_info_not_found(self):
        """Test get_container_info when the container is not found."""
        self.mock_client.containers.get.side_effect = NotFound('Container not found')
        info = self.monitor.get_container_info('non_existent_id')
        self.assertIsNone(info)

    def test_scan_running_containers(self):
        """Test scanning of running containers."""
        container1 = self._create_mock_container('c1', 'app1', ['NPM_HOST=a.com', 'NPM_PORT=80'], {})
        container2 = self._create_mock_container('c2', 'app2', ['NO_NPM=true'], {})
        container3 = self._create_mock_container('c3', 'app3', ['NPM_HOST=b.com', 'NPM_PORT=81'], {})

        self.mock_client.containers.list.return_value = [container1, container2, container3]
        # Mock get to return the container itself
        self.mock_client.containers.get.side_effect = lambda cid: { 'c1': container1, 'c3': container3 }[cid]

        containers = self.monitor.scan_running_containers()

        self.assertEqual(len(containers), 2)
        self.assertEqual(containers[0]['id'], 'c1')
        self.assertEqual(containers[1]['id'], 'c3')
        self.assertIn('c1', self.monitor.active_containers)
        self.assertNotIn('c2', self.monitor.active_containers)

    def test_start_monitoring_event_handling(self):
        """Test that start_monitoring correctly handles start and stop events."""
        start_event = {'type': 'container', 'status': 'start', 'id': 'c1'}
        stop_event = {'type': 'container', 'status': 'stop', 'id': 'c1'}
        
        # Mock the event stream
        self.mock_client.events.return_value = iter([start_event, stop_event])

        # Mock get_container_info for the start event
        container_info = {
            'id': 'c1', 'name': 'test-app', 
            'npm_config': {'host': 'app.com', 'port': 80}
        }
        self.monitor.get_container_info = MagicMock(return_value=container_info)
        
        # Mock callbacks
        on_start = MagicMock()
        on_stop = MagicMock()

        # Pre-populate active_containers for the stop event test
        self.monitor.active_containers['c1'] = container_info

        # Use a try-except block to break the infinite loop of event monitoring
        try:
            self.monitor.start_monitoring(on_start, on_stop)
        except StopIteration: # The mocked iterator will raise this
            pass

        # Assertions
        self.monitor.get_container_info.assert_called_once_with('c1')
        on_start.assert_called_once_with(container_info)
        on_stop.assert_called_once_with('c1')
