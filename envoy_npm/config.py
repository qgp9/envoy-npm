"""
EnvoyNPM 설정 모듈
환경변수 및 설정 관련 코드를 관리합니다.
"""

import os
import logging
from typing import Optional
from pydantic import BaseModel, Field


class ConfigError(Exception):
    """설정 관련 오류를 나타내는 예외 클래스"""
    pass



class EnvoyConfig(BaseModel):
    """EnvoyNPM 설정 클래스"""
    
    # NPM API 관련 설정
    npm_api_url: str = Field(..., description="NPM API의 기본 URL")
    npm_api_email: str = Field(..., description="NPM 관리자 계정 이메일")
    npm_api_password: str = Field(..., description="NPM 관리자 계정 비밀번호")
    
    # Docker 설정
    docker_socket: Optional[str] = Field(default=None, description="Docker 소켓 경로")
    
    # 로깅 설정
    log_level: str = Field(default="INFO", description="로깅 레벨 설정")
    
    # API 재시도 설정
    max_retries: int = Field(default=3, description="API 호출 최대 재시도 횟수")
    retry_delay: int = Field(default=5, description="재시도 간 지연 시간(초)")
    
    # 동기화 설정
    sync_interval: int = Field(default=3600, description="전체 동기화 간격(초)")
    
    # 헬스체크 설정
    health_port: int = Field(default=8080, description="헬스체크 서버 포트")


def load_config() -> EnvoyConfig:
    """환경변수에서 설정을 로드합니다."""
    
    # 기본 설정값
    DEFAULT_CONFIG = {
        "npm_api_url": "http://localhost:81",
        "npm_api_email": "admin@example.com",
        "npm_api_password": "changeme",
        "docker_socket": None,  # Docker 소켓 경로, None이면 자동 탐지
        "log_level": "INFO",
        "max_retries": 3,
        "retry_delay": 5,
        "sync_interval": 60,
        "health_port": 8080,  # 헬스체크 서버 포트
    }
    
    # 필수 환경변수 확인
    required_vars = ["NPM_API_URL", "NPM_API_EMAIL", "NPM_API_PASSWORD"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise ValueError(f"필수 환경변수가 설정되지 않았습니다: {', '.join(missing_vars)}")
    
    # 설정 객체 생성 및 반환
    return EnvoyConfig(
        npm_api_url=os.getenv("NPM_API_URL", DEFAULT_CONFIG["npm_api_url"]),
        npm_api_email=os.getenv("NPM_API_EMAIL", DEFAULT_CONFIG["npm_api_email"]),
        npm_api_password=os.getenv("NPM_API_PASSWORD", DEFAULT_CONFIG["npm_api_password"]),
        docker_socket=os.getenv("DOCKER_SOCKET", DEFAULT_CONFIG["docker_socket"]),
        log_level=os.getenv("LOG_LEVEL", DEFAULT_CONFIG["log_level"]),
        max_retries=int(os.getenv("MAX_RETRIES", DEFAULT_CONFIG["max_retries"])),
        retry_delay=int(os.getenv("RETRY_DELAY", DEFAULT_CONFIG["retry_delay"])),
        sync_interval=int(os.getenv("SYNC_INTERVAL", DEFAULT_CONFIG["sync_interval"])),
        health_port=int(os.getenv("HEALTH_PORT", DEFAULT_CONFIG["health_port"])),
    )


def setup_logging(log_level: str = "INFO") -> None:
    """로깅 설정을 초기화합니다."""
    
    # 로그 레벨 매핑
    log_levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    
    # 로그 포맷 설정
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=log_levels.get(log_level.upper(), logging.INFO),
        format=log_format
    )
    
    # 로거 반환
    logger = logging.getLogger("envoy_npm")
    logger.info(f"로깅 레벨이 {log_level}로 설정되었습니다.")
