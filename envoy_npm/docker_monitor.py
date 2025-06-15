"""
Docker 이벤트 모니터링 모듈
Docker 컨테이너의 라이프사이클 이벤트를 모니터링합니다.
"""

import logging
import docker
import os
from typing import Dict, Any, List, Callable, Optional
import docker
from docker.models.containers import Container

logger = logging.getLogger("envoy_npm.docker_monitor")


class DockerMonitor:
    """Docker 컨테이너 이벤트 모니터링 클래스"""
    
    def __init__(self, docker_socket=None):
        """Docker 모니터 초기화"""
        try:
            # 환경변수에서 지정된 Docker 소켓 경로 사용
            if docker_socket:
                # 경로에 unix:// 프리픽스가 없으면 추가
                if not docker_socket.startswith('unix://') and not docker_socket.startswith('tcp://'):
                    docker_socket = f'unix://{docker_socket}'
                
                logger.info(f"지정된 Docker 소켓 경로 사용: {docker_socket}")
                self.client = docker.DockerClient(base_url=docker_socket)
                # 연결 테스트
                self.client.ping()
                logger.info(f"Docker 클라이언트 초기화 성공 (소켓: {docker_socket})")
            else:
                # 여러 가능한 Docker 소켓 경로 시도
                docker_socket_paths = [
                    None,  # 기본 환경 변수 사용
                    'unix://var/run/docker.sock',  # 표준 Linux 경로
                    'unix:///var/run/docker.sock',  # 표준 Linux 경로 (슬래시 3개)
                    'unix://~/Library/Containers/com.docker.docker/Data/docker.sock',  # Mac 경로
                    'unix:///Users/Shared/docker.sock',  # 일부 Mac 설정
                    'unix://' + os.path.expanduser('~/.colima/default/docker.sock'),  # Colima Docker 경로
                    'tcp://localhost:2375'  # TCP 소켓
                ]
                
                # 각 경로 시도
                for socket_path in docker_socket_paths:
                    try:
                        if socket_path:
                            self.client = docker.DockerClient(base_url=socket_path)
                        else:
                            self.client = docker.from_env()
                        
                        # 연결 테스트
                        self.client.ping()
                        logger.info(f"Docker 클라이언트 초기화 성공 (소켓: {socket_path or '환경변수'})")
                        break
                    except Exception as e:
                        logger.debug(f"Docker 소켓 {socket_path or '환경변수'} 연결 실패: {str(e)}")
                else:
                    # 모든 경로 시도 실패
                    raise ConnectionError("사용 가능한 Docker 소켓을 찾을 수 없습니다. DOCKER_SOCKET 환경변수를 설정해주세요.")
                
        except Exception as e:
            logger.error(f"Docker 클라이언트 초기화 실패: {str(e)}")
            raise
        
        # 활성 컨테이너 캐시
        self.active_containers = {}
    
    def get_container_info(self, container_id: str) -> Optional[Dict[str, Any]]:
        """
        컨테이너 ID로 컨테이너 정보를 가져옵니다.
        
        Args:
            container_id: 컨테이너 ID 또는 이름
            
        Returns:
            Optional[Dict[str, Any]]: 컨테이너 정보 또는 None (컨테이너를 찾을 수 없는 경우)
        """
        try:
            container = self.client.containers.get(container_id)
            
            # 컨테이너 기본 정보 수집
            info = {
                "id": container.id,
                "name": container.name,
                "status": container.status,
                "image": container.image.tags[0] if container.image.tags else container.image.id,
                "env": self._parse_container_env(container),
                "networks": self._get_container_networks(container)
            }
            
            # NPM 관련 환경변수 확인
            npm_env = self._extract_npm_env(info["env"])
            if npm_env:
                info["npm_config"] = npm_env
            
            return info
        except docker.errors.NotFound:
            logger.warning(f"컨테이너를 찾을 수 없음: {container_id}")
            return None
        except Exception as e:
            logger.error(f"컨테이너 정보 가져오기 실패: {str(e)}")
            return None
    
    def scan_running_containers(self) -> List[Dict[str, Any]]:
        """
        현재 실행 중인 모든 컨테이너를 스캔합니다.
        
        Returns:
            List[Dict[str, Any]]: 실행 중인 컨테이너 정보 목록
        """
        containers = []
        try:
            running_containers = self.client.containers.list(filters={"status": "running"})
            logger.info(f"{len(running_containers)}개의 실행 중인 컨테이너를 발견했습니다")
            
            for container in running_containers:
                info = self.get_container_info(container.id)
                if info and "npm_config" in info:
                    containers.append(info)
                    self.active_containers[container.id] = info
            
            logger.info(f"{len(containers)}개의 NPM 설정이 있는 컨테이너를 발견했습니다")
            return containers
        except Exception as e:
            logger.error(f"실행 중인 컨테이너 스캔 중 오류 발생: {str(e)}")
            return []
    
    def start_monitoring(self, 
                         on_container_start: Callable[[Dict[str, Any]], None],
                         on_container_stop: Callable[[str], None]):
        """
        Docker 이벤트 모니터링을 시작합니다.
        
        Args:
            on_container_start: 컨테이너 시작 이벤트 처리 콜백 함수
            on_container_stop: 컨테이너 정지/종료 이벤트 처리 콜백 함수
        """
        logger.info("Docker 이벤트 모니터링을 시작합니다")
        
        # 초기 스캔은 EnvoyService._sync_all()에서 수행하미로 여기서는 제거
        
        # 이벤트 필터 설정
        filters = {
            "type": "container",
            "event": ["start", "stop", "die"]
        }
        
        try:
            for event in self.client.events(decode=True, filters=filters):
                container_id = event.get("id")
                action = event.get("status")
                
                if not container_id or not action:
                    continue
                
                logger.debug(f"컨테이너 이벤트 감지: {action} - {container_id}")
                
                if action == "start":
                    # 컨테이너 시작 이벤트 처리
                    container_info = self.get_container_info(container_id)
                    if container_info and "npm_config" in container_info:
                        logger.info(f"NPM 설정이 있는 컨테이너 시작: {container_info['name']}")
                        self.active_containers[container_id] = container_info
                        on_container_start(container_info)
                
                elif action in ["stop", "die"]:
                    # 컨테이너 정지/종료 이벤트 처리
                    if container_id in self.active_containers:
                        container_name = self.active_containers[container_id].get("name", container_id)
                        logger.info(f"NPM 설정이 있는 컨테이너 정지/종료: {container_name}")
                        on_container_stop(container_id)
                        # 캐시에서 제거
                        self.active_containers.pop(container_id, None)
        
        except KeyboardInterrupt:
            logger.info("사용자에 의해 모니터링이 중지되었습니다")
        except Exception as e:
            logger.error(f"이벤트 모니터링 중 오류 발생: {str(e)}")
            raise
    
    def _parse_container_env(self, container: Container) -> Dict[str, str]:
        """
        컨테이너의 환경변수를 파싱합니다.
        
        Args:
            container: Docker 컨테이너 객체
            
        Returns:
            Dict[str, str]: 환경변수 딕셔너리
        """
        env_dict = {}
        try:
            env_list = container.attrs.get("Config", {}).get("Env", [])
            for env_var in env_list:
                if "=" in env_var:
                    key, value = env_var.split("=", 1)
                    env_dict[key] = value
        except Exception as e:
            logger.error(f"환경변수 파싱 중 오류 발생: {str(e)}")
        
        return env_dict
    
    def _extract_npm_env(self, env_dict: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        환경변수에서 NPM 관련 설정을 추출합니다.
        
        Args:
            env_dict: 환경변수 딕셔너리
            
        Returns:
            Optional[Dict[str, Any]]: NPM 설정 딕셔너리 또는 None (필수 설정이 없는 경우)
        """
        # 필수 환경변수 확인
        if "NPM_HOST" not in env_dict or "NPM_PORT" not in env_dict:
            return None
        
        # NPM 설정 추출
        npm_config = {
            "host": env_dict["NPM_HOST"],
            "port": int(env_dict["NPM_PORT"]),
            "ssl": env_dict.get("NPM_SSL", "false").lower() == "true",
            "enable_ws": env_dict.get("NPM_ENABLE_WS", "false").lower() == "true",
            "enable_hsts": env_dict.get("NPM_ENABLE_HSTS", "false").lower() == "true",
            "network": env_dict.get("NPM_NETWORK", ""),
            "advanced_config": env_dict.get("NPM_ADVANCED_CONFIG", "")
        }
        
        return npm_config
    
    def _get_container_networks(self, container: Container) -> Dict[str, Dict[str, Any]]:
        """
        컨테이너의 네트워크 정보를 가져옵니다.
        
        Args:
            container: Docker 컨테이너 객체
            
        Returns:
            Dict[str, Dict[str, Any]]: 네트워크 정보 딕셔너리
        """
        networks = {}
        try:
            networks_data = container.attrs.get("NetworkSettings", {}).get("Networks", {})
            for network_name, network_data in networks_data.items():
                networks[network_name] = {
                    "ip_address": network_data.get("IPAddress", ""),
                    "gateway": network_data.get("Gateway", ""),
                    "network_id": network_data.get("NetworkID", "")
                }
        except Exception as e:
            logger.error(f"네트워크 정보 가져오기 중 오류 발생: {str(e)}")
        
        return networks
