"""
EnvoyNPM 메인 애플리케이션 진입점
"""

import os
import sys
import time
import logging
import signal
import threading
from dotenv import load_dotenv

from envoy_npm.config import load_config, setup_logging
from envoy_npm.envoy_service import EnvoyService
from envoy_npm.health_server import start_health_server

# 로거 설정
logger = logging.getLogger("envoy_npm.main")

# 종료 이벤트
stop_event = threading.Event()


def signal_handler(sig, frame):
    """시그널 핸들러"""
    logger.info("종료 신호를 받았습니다. 서비스를 종료합니다...")
    stop_event.set()


def run_scheduler():
    """스케줄러 실행 함수"""
    import schedule
    
    logger.info("스케줄러 스레드를 시작합니다")
    
    while not stop_event.is_set():
        schedule.run_pending()
        time.sleep(1)
    
    logger.info("스케줄러 스레드를 종료합니다")


def main():
    """메인 함수"""
    # 환경변수 로드
    load_dotenv()
    
    try:
        # 설정 로드
        config = load_config()
        
        # 로깅 설정
        setup_logging(config.log_level)
        
        logger.info("EnvoyNPM 서비스를 초기화합니다")
        
        # 서비스 인스턴스 생성
        service = EnvoyService(config)
        
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # 헬스체크 서버 시작
        health_server = start_health_server(port=config.health_port)
        logger.info(f"헬스체크 서버가 포트 {config.health_port}에서 시작되었습니다")
        
        # 스케줄러 스레드 시작
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        
        # 서비스 시작
        if not service.start():
            logger.error("서비스 시작에 실패했습니다")
            return 1
        
        # 종료 이벤트 대기
        stop_event.wait()

        # 서비스 정리
        service.stop()
        
        # 헬스체크 서버 종료
        if health_server:
            health_server.shutdown()
            logger.info("헬스체크 서버가 종료되었습니다")
        
        logger.info("EnvoyNPM 서비스를 종료합니다")
        return 0
    
    except KeyboardInterrupt:
        logger.info("사용자에 의해 프로그램이 중단되었습니다")
        return 0
    except Exception as e:
        logger.exception(f"예기치 않은 오류가 발생했습니다: {str(e)}")
        return 1


def run():
    """애플리케이션 진입점"""
    return main()

if __name__ == "__main__":
    sys.exit(run())
