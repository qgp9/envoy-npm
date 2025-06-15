"""
EnvoyNPM 서비스 핵심 로직
Docker 이벤트 모니터링과 NPM API 연동을 통합하여 프록시 호스트를 관리합니다.
"""

import time
import json
import logging
import threading
import datetime
from typing import Dict, List, Any, Optional, Set
import schedule

from envoy_npm.npm_api import NPMApiClient
from envoy_npm.docker_monitor import DockerMonitor
from envoy_npm.config import EnvoyConfig

logger = logging.getLogger("envoy_npm.service")


class EnvoyService:
    """EnvoyNPM 서비스 클래스"""
    
    def __init__(self, config: EnvoyConfig):
        """EnvoyNPM 서비스 초기화"""
        self.config = config
        
        # NPM API 클라이언트 초기화
        self.npm_client = NPMApiClient(
            api_url=config.npm_api_url,
            email=config.npm_api_email,
            password=config.npm_api_password,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay
        )
        
        # Docker 모니터 초기화
        self.docker_monitor = DockerMonitor(docker_socket=config.docker_socket)
        
        # NPM 프록시 호스트 캐시
        self.current_npm_hosts = {}
        
        # 컨테이너 정보 캐시
        self.container_cache = {}
        
        # EnvoyNPM이 관리하는 호스트 ID 목록
        self.managed_host_ids = set()
    
    def start(self):
        """서비스를 시작합니다."""
        logger.info("EnvoyNPM 서비스를 시작합니다")
        
        # NPM API에 로그인
        if not self.npm_client.login():
            logger.error("NPM API 로그인 실패, 서비스를 종료합니다")
            return False
        
        # 초기 NPM 호스트 목록 로드
        self._load_npm_hosts()
        
        # 정기 동기화 스케줄링
        schedule.every(self.config.sync_interval).seconds.do(self._sync_all)
        
        # 서비스 시작 시 즉시 동기화 실행
        logger.info("서비스 시작 시 초기 동기화 실행")
        self._sync_all()
        
        try:
            # Docker 이벤트 모니터링 시작
            self.docker_monitor.start_monitoring(
                on_container_start=self.on_container_start,
                on_container_stop=self.on_container_stop
            )
        except Exception as e:
            logger.error(f"서비스 실행 중 오류 발생: {str(e)}")
            return False
        
        return True
    
    def _load_npm_hosts(self):
        """NPM 호스트 목록을 로드하고 캐시합니다."""
        hosts = self.npm_client.get_proxy_hosts()
        
        # 호스트 캐시 초기화
        self.current_npm_hosts = {}
        self.managed_host_ids = set()
        
        # 호스트 정보 파싱 및 캐시
        for host in hosts:
            host_id = host.get("id")
            domain = host.get("domain_names", [])[0] if host.get("domain_names") else None
            
            if host_id and domain:
                self.current_npm_hosts[domain] = host
                
                # EnvoyNPM이 관리하는 호스트인지 확인
                meta = self._parse_meta(host.get("meta", "{}"))
                if meta.get("managed_by") == "EnvoyNPM":
                    self.managed_host_ids.add(host_id)
                    logger.debug(f"EnvoyNPM이 관리하는 호스트 발견: {domain} (ID: {host_id})")
        
        logger.info(f"{len(hosts)}개의 NPM 호스트를 로드했습니다 (EnvoyNPM 관리: {len(self.managed_host_ids)}개)")
    
    def on_container_start(self, container_info: Dict[str, Any]):
        """
        컨테이너 시작 이벤트 처리
        
        Args:
            container_info: 컨테이너 정보
        """
        if "npm_config" not in container_info:
            return
        
        npm_config = container_info["npm_config"]
        container_id = container_info["id"]
        container_name = container_info["name"]
        domain = npm_config["host"]
        port = npm_config["port"]
        
        logger.info(f"컨테이너 시작 이벤트 처리: {container_name} ({domain}:{port})")
        
        # 컨테이너 IP 주소 확인
        ip_address = self._get_container_ip(container_info)
        if not ip_address:
            logger.error(f"컨테이너 IP 주소를 찾을 수 없습니다: {container_name}")
            return
        
        # 프록시 호스트 존재 여부 확인
        existing_host = self.current_npm_hosts.get(domain)
        
        if existing_host:
            host_id = existing_host["id"]
            
            # 메타데이터 파싱
            meta = self._parse_meta(existing_host.get("meta", "{}"))
            
            if host_id in self.managed_host_ids:
                # EnvoyNPM이 관리하는 호스트인 경우
                logger.info(f"기존 관리 호스트 업데이트: {domain} (ID: {host_id})")
                
                # 호스트 데이터 업데이트
                host_data = self._prepare_host_data(
                    domain=domain,
                    forward_host=ip_address,
                    forward_port=port,
                    container_id=container_id,
                    container_name=container_name,
                    npm_config=npm_config
                )
                
                # 활성화 상태로 설정
                host_data["enabled"] = 1
                
                # 호스트 업데이트
                if self.npm_client.update_proxy_host(host_id, host_data):
                    # 캐시 업데이트
                    self.current_npm_hosts[domain] = {**existing_host, **host_data}
            else:
                # 수동으로 생성된 호스트인 경우
                logger.warning(
                    f"도메인 {domain}에 대한 수동 생성 호스트가 이미 존재합니다. "
                    f"EnvoyNPM이 관리하도록 하려면 NPM에서 해당 호스트를 삭제하세요."
                )
        else:
            # 새로운 호스트 생성
            logger.info(f"새로운 프록시 호스트 생성: {domain}")
            
            # 호스트 데이터 준비
            host_data = self._prepare_host_data(
                domain=domain,
                forward_host=ip_address,
                forward_port=port,
                container_id=container_id,
                container_name=container_name,
                npm_config=npm_config
            )
            
            # 호스트 생성
            created_host = self.npm_client.create_proxy_host(host_data)
            if created_host:
                # 캐시 업데이트
                host_id = created_host.get("id")
                self.current_npm_hosts[domain] = created_host
                self.managed_host_ids.add(host_id)
    
    def on_container_stop(self, container_id: str):
        """
        컨테이너 정지/종료 이벤트 처리
        
        Args:
            container_id: 컨테이너 ID
        """
        logger.info(f"컨테이너 정지/종료 이벤트 처리: {container_id}")
        
        # 관리 중인 호스트 중 해당 컨테이너와 연결된 호스트 찾기
        for domain, host in list(self.current_npm_hosts.items()):
            host_id = host.get("id")
            
            if host_id not in self.managed_host_ids:
                continue
            
            meta = self._parse_meta(host.get("meta", "{}"))
            if meta.get("container_id") == container_id:
                logger.info(f"컨테이너 {container_id}와 연결된 호스트 비활성화: {domain} (ID: {host_id})")
                
                # 호스트 비활성화
                update_data = {
                    "enabled": False  # API 스키마에 따라 boolean으로 변경
                    # "comments" 필드는 API 스키마에 없으므로 제거합니다.
                    # 필요한 경우 meta 필드를 업데이트하여 상태를 기록할 수 있습니다.
                }
                
                if self.npm_client.update_proxy_host(host_id, update_data):
                    # 캐시 업데이트
                    self.current_npm_hosts[domain] = {**host, **update_data}
    
    def _sync_all(self):
        """
        모든 컨테이너와 NPM 호스트를 동기화합니다.
        """
        logger.info("전체 동기화 시작")
        
        # NPM 호스트 목록 다시 로드
        self._load_npm_hosts()
        
        # 실행 중인 컨테이너 스캔
        containers = self.docker_monitor.scan_running_containers()
        
        # 각 컨테이너에 대해 시작 이벤트 처리 로직 적용
        for container in containers:
            self.on_container_start(container)
        
        logger.info("전체 동기화 완료")
    
    def _get_container_ip(self, container_info: Dict[str, Any]) -> Optional[str]:
        """
        컨테이너의 IP 주소를 가져옵니다.
        
        Args:
            container_info: 컨테이너 정보
            
        Returns:
            Optional[str]: 컨테이너 IP 주소 또는 None
        """
        networks = container_info.get("networks", {})
        npm_config = container_info.get("npm_config", {})
        
        # NPM_NETWORK 환경변수가 설정된 경우 해당 네트워크의 IP 사용
        preferred_network = npm_config.get("network", "")
        if preferred_network and preferred_network in networks:
            ip = networks[preferred_network].get("ip_address")
            if ip:
                return ip
        
        # 기본: 첫 번째 네트워크의 IP 사용
        for network_name, network_data in networks.items():
            ip = network_data.get("ip_address")
            if ip:
                return ip
        
        return None
    
    def _prepare_host_data(self, domain: str, forward_host: str, forward_port: int,
                          container_id: str, container_name: str,
                          npm_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        NPM 프록시 호스트 데이터를 준비합니다.
        
        Args:
            domain: 프록시 도메인
            forward_host: 포워딩할 호스트 (컨테이너 IP)
            forward_port: 포워딩할 포트
            container_id: 컨테이너 ID
            container_name: 컨테이너 이름
            npm_config: NPM 설정
            
        Returns:
            Dict[str, Any]: NPM API에 전달할 호스트 데이터
        """
        # 메타데이터 준비
        meta = {
            "managed_by": "EnvoyNPM",
            "container_id": container_id,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        # 디버깅 로깅
        logger.debug(f"준비된 메타데이터: {meta}")
        
        # 기본 호스트 데이터
        # certificate_id 처리: npm_config에서 가져오되, 'new' 문자열이거나 정수여야 함.
        # 기본값은 0 (No certificate)
        cert_id_val = npm_config.get("certificate_id", 0)
        if isinstance(cert_id_val, str) and cert_id_val.lower() == 'new':
            certificate_id = 'new'
        else:
            try:
                certificate_id = int(cert_id_val)
            except ValueError:
                logger.warning(f"잘못된 certificate_id 값: {cert_id_val}. 기본값 0을 사용합니다.")
                certificate_id = 0

        host_data = {
            "domain_names": [domain], # API 스키마: array of strings
            "forward_scheme": npm_config.get("forward_scheme", "http"), # API 스키마: string ("http" or "https")
            "forward_host": forward_host, # API 스키마: string
            "forward_port": int(npm_config.get("forward_port", forward_port)), # API 스키마: integer
            
            "access_list_id": int(npm_config.get("access_list_id", 0)), # API 스키마: integer, min 0
            "certificate_id": certificate_id, # API 스키마: integer (min 0) or string "new"
            
            "ssl_forced": str(npm_config.get("ssl_forced", False)).lower() == 'true', # API 스키마: boolean
            "hsts_enabled": str(npm_config.get("hsts_enabled", False)).lower() == 'true', # API 스키마: boolean
            "hsts_subdomains": str(npm_config.get("hsts_subdomains", False)).lower() == 'true', # API 스키마: boolean
            "http2_support": str(npm_config.get("http2_support", False)).lower() == 'true', # API 스키마: boolean
            "block_exploits": str(npm_config.get("block_exploits", True)).lower() == 'true', # API 스키마: boolean
            "caching_enabled": str(npm_config.get("caching_enabled", False)).lower() == 'true', # API 스키마: boolean. 이전 cache_enabled는 여기서 처리 안함.
            "allow_websocket_upgrade": str(npm_config.get("allow_websocket_upgrade", False)).lower() == 'true', # API 스키마: boolean
            
            "advanced_config": npm_config.get("advanced_config", ""), # API 스키마: string
            "meta": meta, # API 스키마: object
            "enabled": True  # 항상 활성화 상태로 생성/업데이트 (비활성화는 on_container_stop에서 별도 처리)
            # locations 필드는 현재 EnvoyNPM에서 지원하지 않으므로 포함하지 않음
        }
        # forward_scheme은 컨테이너 레이블에서 직접 가져오도록 수정 (기본값 http)
        host_data["forward_scheme"] = npm_config.get("scheme", "http")
        
        # 디버깅 로깅
        logger.debug(f"준비된 호스트 데이터: {json.dumps(host_data, ensure_ascii=False)}")
        
        return host_data
    
    def _parse_meta(self, meta_data) -> Dict[str, Any]:
        """
        NPM 호스트 메타데이터 파싱
        
        Args:
            meta_data: 메타데이터 JSON 문자열 또는 디셔너리
            
        Returns:
            파싱된 메타데이터 디셔너리
        """
        if isinstance(meta_data, dict):
            return meta_data
        elif isinstance(meta_data, str):
            try:
                return json.loads(meta_data) if meta_data else {}
            except json.JSONDecodeError:
                logger.warning(f"메타데이터 파싱 실패: {meta_data}")
                return {}
        else:
            logger.warning(f"알 수 없는 메타데이터 형식: {type(meta_data)}")
            return {}
