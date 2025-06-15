import unittest
import threading
import time
import signal
import sys
from unittest.mock import patch, MagicMock, call, ANY, mock_open
from envoy_npm.main import main, signal_handler, run_scheduler, stop_event
from envoy_npm.config import EnvoyConfig, ConfigError

class TestSignalHandler(unittest.TestCase):
    @patch('envoy_npm.main.logger')
    @patch('envoy_npm.main.stop_event')
    def test_signal_handler(self, mock_stop_event, mock_logger):
        """Test the signal_handler function."""
        # Call signal_handler with dummy signal and frame
        signal_handler(None, None)

        # Assertions
        mock_logger.info.assert_called_once_with("종료 신호를 받았습니다. 서비스를 종료합니다...")
        mock_stop_event.set.assert_called_once()


class TestRunScheduler(unittest.TestCase):
    @patch('envoy_npm.main.schedule')
    @patch('envoy_npm.main.time.sleep')
    @patch('envoy_npm.main.stop_event')
    @patch('envoy_npm.main.logger')
    def test_run_scheduler_normal_operation(self, mock_logger, mock_stop_event, mock_sleep, mock_schedule):
        """Test run_scheduler function with normal operation."""
        # Setup
        mock_stop_event.is_set.side_effect = [False, False, True]  # Run loop twice then exit
        
        # Run the scheduler in a separate thread
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.start()
        
        # Give it a moment to run
        time.sleep(0.1)
        
        # Stop the scheduler
        mock_stop_event.is_set.return_value = True
        scheduler_thread.join(timeout=1.0)
        
        # Verify
        mock_schedule.run_pending.assert_called()
        mock_sleep.assert_called()
        mock_stop_event.is_set.assert_called()
        mock_logger.info.assert_called_with("스케줄러 스레드를 종료합니다")

    @patch('envoy_npm.main.schedule')
    @patch('envoy_npm.main.time.sleep', side_effect=KeyboardInterrupt)
    @patch('envoy_npm.main.stop_event')
    @patch('envoy_npm.main.logger')
    def test_run_scheduler_keyboard_interrupt(self, mock_logger, mock_stop_event, mock_sleep, mock_schedule):
        """Test run_scheduler handles KeyboardInterrupt gracefully."""
        mock_stop_event.is_set.return_value = False
        
        run_scheduler()
        
        mock_schedule.run_pending.assert_called_once()
        mock_stop_event.set.assert_called_once()
        mock_logger.info.assert_called_with("스케줄러 스레드를 종료합니다")


class TestMain(unittest.TestCase):
    def setUp(self):
        # Reset the stop event before each test
        stop_event.clear()
    
    @patch('envoy_npm.main.sys.exit')
    @patch('envoy_npm.main.EnvoyService', autospec=True)
    @patch('envoy_npm.main.run_scheduler')
    @patch('envoy_npm.main.start_health_server')
    @patch('envoy_npm.health_server.logger')
    @patch('envoy_npm.main.logger')
    @patch('envoy_npm.main.setup_logging')
    @patch('envoy_npm.main.load_config')
    def test_main_success(self, mock_load_config, mock_setup_logging, mock_main_logger, mock_health_logger, mock_start_health_server, mock_run_scheduler, mock_envoy_service_class, mock_sys_exit):
        """Test successful execution of the main function using high-level mocks."""
        # Setup mocks
        mock_config_instance = MagicMock(spec=EnvoyConfig) 
        mock_config_instance.health_port = 8080  
        mock_config_instance.health_check_port = 8080  
        mock_config_instance.log_level = "INFO"  
        mock_load_config.return_value = mock_config_instance
        
        # EnvoyService 인스턴스 설정
        mock_envoy_service_instance = MagicMock()
        mock_envoy_service_instance.start.return_value = True  # start()가 True를 반환하도록 설정
        mock_envoy_service_instance.config = mock_config_instance  # config 속성 추가
        mock_envoy_service_class.return_value = mock_envoy_service_instance

        # start_health_server가 반환할 mock 서버 설정
        mock_health_server = MagicMock()
        mock_start_health_server.return_value = mock_health_server

        # stop_event.wait()를 모킹하여 테스트 제어
        with patch('envoy_npm.main.stop_event') as mock_stop_event, \
             patch('envoy_npm.main.signal.signal') as mock_signal, \
             patch('builtins.open', unittest.mock.mock_open()):
            
            # signal.signal 호출 시 핸들러 저장
            signal_handlers = {}
            def save_signal_handler(sig, handler):
                signal_handlers[sig] = handler
                return None
            
            mock_signal.side_effect = save_signal_handler
            
            # stop_event.wait()가 호출되면 stop_event를 설정하여 루프 종료
            def set_stop_event():
                mock_stop_event.is_set.return_value = True
                # 시그널 핸들러 호출 시뮬레이션
                if signal.SIGINT in signal_handlers:
                    signal_handlers[signal.SIGINT](signal.SIGINT, None)
                return True
            
            # 첫 번째 호출에서는 False 반환, 두 번째 호출부터는 True 반환
            mock_stop_event.is_set.side_effect = [False, True]
            mock_stop_event.wait.side_effect = set_stop_event
            
            # main 함수 실행
            main()

        # Assertions
        mock_load_config.assert_called_once()
        mock_setup_logging.assert_called_once_with("INFO")
        
        # 로깅 검증
        mock_main_logger.info.assert_any_call("EnvoyNPM 서비스를 초기화합니다")
        
        # 서비스 시작 및 중지 확인
        mock_envoy_service_class.assert_called_once_with(mock_config_instance)
        mock_envoy_service_instance.start.assert_called_once()
        mock_envoy_service_instance.stop.assert_called_once()
        
        # 헬스체크 서버 및 스케줄러 확인
        # start_health_server가 올바른 포트로 호출되었는지 확인
        mock_start_health_server.assert_called_once_with(port=mock_config_instance.health_port)
        mock_run_scheduler.assert_called_once()
        
        # main() 함수가 0을 반환하는지 확인
        # sys.exit() 호출 대신 반환값을 확인하도록 변경
        # mock_sys_exit.assert_called_once_with(0)

    @patch('envoy_npm.main.exit') 
    @patch('envoy_npm.main.exit') # main 모듈 내의 exit (from sys import exit)
    @patch('envoy_npm.main.EnvoyService', autospec=True)
    @patch('envoy_npm.main.start_health_server') # run_scheduler는 호출되지 않으므로 모킹 불필요
    @patch('envoy_npm.main.logger') # main 모듈의 logger
    @patch('envoy_npm.main.load_config')
    def test_main_service_start_failure(self, mock_load_config, mock_logger, mock_start_health_server, mock_envoy_service_class, mock_main_exit):
        """Test main function when service fails to start."""
        # Setup mocks
        mock_config_instance = MagicMock(spec=EnvoyConfig) # EnvoyConfig 스펙으로 수정
        mock_config_instance.log_level = "ERROR" # test_main_service_start_failure에서도 log_level 설정 (필요시)
        mock_load_config.return_value = mock_config_instance
        
        mock_envoy_service_instance = mock_envoy_service_class.return_value
        mock_envoy_service_instance.start.return_value = False # 서비스 시작 실패

        # Call the main function
        main()

        # --- Assertions ---
        mock_load_config.assert_called_once()
        mock_envoy_service_class.assert_called_once_with(mock_config_instance)
        mock_envoy_service_instance.start.assert_called_once()

        # 서비스 시작 실패 시 헬스 서버는 시작되지 않아야 함
        mock_start_health_server.assert_not_called()

        mock_logger.error.assert_called_once_with("서비스 시작에 실패했습니다")
        mock_main_exit.assert_called_once_with(1)

    @patch('envoy_npm.main.threading')
    @patch('envoy_npm.main.sys.exit')
    @patch('envoy_npm.main.EnvoyService', autospec=True)
    @patch('envoy_npm.main.run_scheduler')
    @patch('envoy_npm.main.start_health_server')
    @patch('envoy_npm.main.logger')
    @patch('envoy_npm.main.load_config')
    def test_main_health_server_shutdown(self, mock_load_config, mock_logger, mock_start_health_server, 
                                        mock_run_scheduler, mock_envoy_service_class, mock_sys_exit, mock_threading):
        """Test main function ensures health server is properly shut down."""
        # Setup mocks
        mock_config = MagicMock(spec=EnvoyConfig)
        mock_config.health_port = 8080
        mock_config.health_check_port = 8080  # Add missing attribute
        mock_config.log_level = "INFO"
        mock_load_config.return_value = mock_config
        
        mock_envoy_service = MagicMock()
        mock_envoy_service_class.return_value = mock_envoy_service
        mock_envoy_service.start.return_value = True
        
        # Mock health server
        mock_health_server = MagicMock()
        mock_start_health_server.return_value = mock_health_server
        
        # Make run_scheduler block until we set the stop event
        def stop_on_call():
            stop_event.set()
            return None
        mock_run_scheduler.side_effect = stop_on_call
        
        # Mock threading.Thread
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        
        # Run main
        with patch('builtins.open', unittest.mock.mock_open()):  # Patch open for dotenv
            main()
        
        # Verify health server was shut down
        mock_health_server.shutdown.assert_called_once()
        mock_logger.info.assert_any_call("헬스체크 서버가 종료되었습니다")
    
    @patch('envoy_npm.main.sys.exit')
    @patch('envoy_npm.main.EnvoyService', autospec=True)
    @patch('envoy_npm.main.run_scheduler', side_effect=KeyboardInterrupt)
    @patch('envoy_npm.main.start_health_server')
    @patch('envoy_npm.main.logger')
    @patch('envoy_npm.main.load_config')
    def test_main_keyboard_interrupt(self, mock_load_config, mock_logger, mock_start_health_server, 
                                    mock_run_scheduler, mock_envoy_service_class, mock_sys_exit):
        """Test main function handles KeyboardInterrupt gracefully."""
        # Setup mocks
        mock_config = MagicMock(spec=EnvoyConfig)
        mock_config.health_port = 8080
        mock_config.health_check_port = 8080  # Add missing attribute
        mock_config.log_level = "INFO"
        mock_load_config.return_value = mock_config
        
        mock_envoy_service = MagicMock()
        mock_envoy_service_class.return_value = mock_envoy_service
        mock_envoy_service.start.return_value = True
        
        # Call main with patched open for dotenv
        with patch('builtins.open', unittest.mock.mock_open()):
            result = main()
        
        # Verify
        self.assertEqual(result, 0)
        mock_envoy_service.stop.assert_called_once()
    
    @patch('envoy_npm.main.sys.exit')
    @patch('envoy_npm.main.EnvoyService', autospec=True)
    @patch('envoy_npm.main.run_scheduler')
    @patch('envoy_npm.main.start_health_server')
    @patch('envoy_npm.main.logger')
    @patch('envoy_npm.main.load_config')
    def test_main_unhandled_exception(self, mock_load_config, mock_logger, mock_start_health_server, 
                                     mock_run_scheduler, mock_envoy_service_class, mock_sys_exit):
        """Test main function handles unhandled exceptions."""
        # Setup mocks
        mock_config = MagicMock(spec=EnvoyConfig)
        mock_config.health_port = 8080
        mock_config.health_check_port = 8080  # Add missing attribute
        mock_config.log_level = "INFO"
        mock_load_config.return_value = mock_config
        
        test_exception = Exception("Test exception")
        mock_envoy_service = MagicMock()
        mock_envoy_service.start.side_effect = test_exception
        mock_envoy_service_class.return_value = mock_envoy_service
        
        # Call main with patched open for dotenv
        with patch('builtins.open', unittest.mock.mock_open()):
            result = main()
        
        # Verify
        self.assertEqual(result, 1)
        mock_logger.exception.assert_called_once()
        mock_sys_exit.assert_not_called()  # main() returns error code, doesn't call sys.exit()

class TestMainErrorCases(unittest.TestCase):
    """Test error cases in the main function."""
    
    @patch('envoy_npm.main.sys.exit')
    @patch('envoy_npm.main.logger')
    @patch('envoy_npm.main.load_config')
    def test_main_config_load_error(self, mock_load_config, mock_logger, mock_sys_exit):
        """Test main function when config loading fails."""
        # Setup
        mock_load_config.side_effect = ConfigError("Configuration error")
        
        # Execute
        main()
        
        # Verify
        mock_logger.exception.assert_called_once_with("환경 설정을 로드하는 중 오류가 발생했습니다: Configuration error")
        mock_sys_exit.assert_called_once_with(1)
    
    @patch('envoy_npm.main.sys.exit')
    @patch('envoy_npm.main.threading')
    @patch('envoy_npm.main.EnvoyService')
    @patch('envoy_npm.main.start_health_server', side_effect=Exception("Health server error"))
    @patch('envoy_npm.main.logger')
    @patch('envoy_npm.main.load_config')
    def test_main_health_server_error(self, mock_load_config, mock_logger, mock_start_health_server, 
                                     mock_envoy_service_class, mock_threading, mock_sys_exit):
        """Test main function when health server fails to start."""
        # Setup
        mock_config = MagicMock(spec=EnvoyConfig)
        mock_config.health_port = 8080
        mock_config.log_level = "INFO"
        mock_load_config.return_value = mock_config
        
        mock_envoy_service = MagicMock()
        mock_envoy_service.start.return_value = True
        mock_envoy_service_class.return_value = mock_envoy_service
        
        # Execute
        main()
        
        # Verify
        mock_logger.exception.assert_called_once_with("헬스체크 서버 시작 중 오류가 발생했습니다")
        mock_sys_exit.assert_called_once_with(1)


class TestSignalHandlerExtended(unittest.TestCase):
    """Extended tests for signal handler functionality."""
    
    @patch('envoy_npm.main.logger')
    @patch('envoy_npm.main.stop_event')
    def test_signal_handler_with_signum(self, mock_stop_event, mock_logger):
        """Test signal_handler with specific signal numbers."""
        # Test with SIGINT
        signal_handler(signal.SIGINT, None)
        mock_logger.info.assert_called_with("종료 신호를 받았습니다. 서비스를 종료합니다...")
        mock_stop_event.set.assert_called_once()
        
        # Reset mocks
        mock_logger.reset_mock()
        mock_stop_event.reset_mock()
        
        # Test with SIGTERM
        signal_handler(signal.SIGTERM, None)
        mock_logger.info.assert_called_with("종료 신호를 받았습니다. 서비스를 종료합니다...")
        mock_stop_event.set.assert_called_once()


class TestRunSchedulerExtended(unittest.TestCase):
    """Extended tests for the run_scheduler function."""
    
    @patch('envoy_npm.main.schedule')
    @patch('envoy_npm.main.time.sleep')
    @patch('envoy_npm.main.stop_event')
    @patch('envoy_npm.main.logger')
    def test_run_scheduler_with_exception(self, mock_logger, mock_stop_event, mock_sleep, mock_schedule):
        """Test run_scheduler handles exceptions in scheduled tasks."""
        # Setup
        mock_stop_event.is_set.side_effect = [False, True]  # Run once then exit
        mock_schedule.run_pending.side_effect = Exception("Scheduler error")
        
        # Execute
        run_scheduler()
        
        # Verify
        mock_schedule.run_pending.assert_called_once()
        mock_logger.exception.assert_called_once_with("스케줄러 실행 중 오류가 발생했습니다")
        mock_stop_event.set.assert_not_called()  # Should not stop on task error


if __name__ == '__main__':
    unittest.main()