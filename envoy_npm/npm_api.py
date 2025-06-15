"""
Nginx Proxy Manager API 클라이언트 모듈
NPM API와의 통신을 담당합니다.
"""

import time
import logging
import json
from typing import Dict, List, Any, Optional
import requests
from requests.exceptions import RequestException

logger = logging.getLogger("envoy_npm.npm_api")


class NPMApiClient:
    """Nginx Proxy Manager API 클라이언트 클래스"""
    
    def __init__(self, api_url: str, email: str, password: str, max_retries: int = 3, retry_delay: int = 5):
        """
        NPM API 클라이언트 초기화
        
        Args:
            api_url: NPM API의 기본 URL (예: http://npm-ip:81)
            email: NPM 관리자 계정 이메일
            password: NPM 관리자 계정 비밀번호
            max_retries: API 호출 최대 재시도 횟수
            retry_delay: 재시도 간 지연 시간(초)
        """
        self.api_url = api_url.rstrip("/")
        self.email = email
        self.password = password
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.token = None
        self.session = requests.Session()
    
    def login(self) -> bool:
        """
        NPM API에 로그인하고 JWT 토큰을 획득합니다.
        
        Returns:
            bool: 로그인 성공 여부
        """
        login_url = f"{self.api_url}/tokens"
        login_data = {
            "identity": self.email,
            "secret": self.password
        }
        
        try:
            response = self._make_request("POST", login_url, json=login_data)
            if response and response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                if self.token:
                    logger.info("NPM API 로그인 성공")
                    # 세션에 인증 헤더 설정
                    self.session.headers.update({"Authorization": f"Bearer {self.token}"})
                    return True
                else:
                    logger.error("NPM API 로그인 응답에 토큰이 없습니다")
            else:
                status = response.status_code if response else "알 수 없음"
                logger.error(f"NPM API 로그인 실패: 상태 코드 {status}")
        except Exception as e:
            logger.error(f"NPM API 로그인 중 예외 발생: {str(e)}")
        
        return False
    
    def get_proxy_hosts(self) -> List[Dict[str, Any]]:
        """
        NPM에 등록된 모든 프록시 호스트 목록을 가져옵니다.
        
        Returns:
            List[Dict[str, Any]]: 프록시 호스트 목록
        """
        url = f"{self.api_url}/nginx/proxy-hosts"
        try:
            response = self._make_request("GET", url)
            if response and response.status_code == 200:
                hosts = response.json()
                logger.info(f"{len(hosts)} 개의 프록시 호스트를 가져왔습니다")
                return hosts
            else:
                status = response.status_code if response else "알 수 없음"
                logger.error(f"프록시 호스트 목록 가져오기 실패: 상태 코드 {status}")
        except Exception as e:
            logger.error(f"프록시 호스트 목록 가져오기 중 예외 발생: {str(e)}")
        
        return []
    
    def create_proxy_host(self, host_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        새로운 프록시 호스트를 생성합니다.
        
        Args:
            host_data: 생성할 프록시 호스트 데이터
            
        Returns:
            Optional[Dict[str, Any]]: 생성된 프록시 호스트 정보 또는 None (실패 시)
        """
        url = f"{self.api_url}/nginx/proxy-hosts"
        logger.info(f"프록시 호스트 생성 요청: {json.dumps(host_data)}")
        try:
            response = self._make_request("POST", url, json=host_data)
            if response is not None:
                if response.status_code == 201:
                    created_host = response.json()
                    host_id = created_host.get('id')
                    logger.info(f"프록시 호스트 생성 성공: ID {host_id}")
                    return host_id # Return the ID as expected by the test
                else:
                    # response가 None이 아니고, status_code가 201이 아닌 경우 (오류 발생)
                    status = response.status_code
                    logger.error(f"프록시 호스트 생성 실패: 상태 코드 {status}")
                    logger.error(f"응답 헤더: {response.headers}")
                    try:
                        if response.text:
                            logger.error(f"응답 내용: {response.text}")
                            try:
                                error_data = response.json()
                                logger.error(f"응답 JSON: {json.dumps(error_data, ensure_ascii=False)}")
                                # 상세 오류 메시지 분석
                                if isinstance(error_data, dict):
                                    if 'error' in error_data and isinstance(error_data['error'], dict) and 'message' in error_data['error']:
                                        logger.error(f"API 오류 메시지: {error_data['error']['message']}")
                                    elif 'error' in error_data:
                                        logger.error(f"오류 메시지: {error_data['error']}") # Fallback for other error structures
                                    # For create_proxy_host, the detailed errors might be in error_data['error']['errors']
                                    if 'error' in error_data and isinstance(error_data.get('error'), dict) and 'errors' in error_data['error'] and isinstance(error_data['error']['errors'], list):
                                        for err_detail in error_data['error']['errors']:
                                            if isinstance(err_detail, dict) and 'field' in err_detail and 'message' in err_detail:
                                                logger.error(f"필드 '{err_detail['field']}': {err_detail['message']}")
                                    elif 'validation' in error_data: # Fallback for other structures
                                        for field, errors in error_data['validation'].items():
                                            logger.error(f"필드 '{field}' 검증 오류: {errors}")
                                elif isinstance(error_data, list):
                                    for item in error_data:
                                        if isinstance(item, dict) and 'message' in item:
                                            logger.error(f"검증 오류: {item['message']}")
                                        else:
                                            logger.error(f"오류 항목: {item}")
                            except json.JSONDecodeError:
                                logger.error("응답이 유효한 JSON 형식이 아닙니다")
                    except Exception as text_err:
                        logger.error(f"응답 내용 읽기 오류: {str(text_err)}")
                    
                    logger.error(f"요청 데이터: {json.dumps(host_data, ensure_ascii=False)}")
                    return None # 오류 발생 시 None 반환
            else:
                # response가 None인 경우 (예: _make_request에서 최대 재시도 후 None 반환)
                logger.error("프록시 호스트 생성 실패: API로부터 응답을 받지 못했습니다 (_make_request가 None 반환)")
                logger.error(f"요청 데이터: {json.dumps(host_data, ensure_ascii=False)}")
                return None
        except Exception as e:
            logger.error(f"프록시 호스트 생성 중 예외 발생: {str(e)}")
            import traceback
            logger.error(f"상세 오류: {traceback.format_exc()}")
        
        return None
    
    def update_proxy_host(self, host_id: int, host_data: Dict[str, Any]) -> bool:
        """
        기존 프록시 호스트를 업데이트합니다.
        
        Args:
            host_id: 업데이트할 프록시 호스트 ID
            host_data: 업데이트할 프록시 호스트 데이터
            
        Returns:
            bool: 업데이트 성공 여부
        """
        url = f"{self.api_url}/nginx/proxy-hosts/{host_id}"
        try:
            response = self._make_request("PUT", url, json=host_data)
            if response and response.status_code == 200:
                logger.info(f"프록시 호스트 업데이트 성공: ID {host_id}")
                return True
            else:
                status_code = response.status_code if response else "N/A"
                error_message = f"프록시 호스트 업데이트 실패: ID {host_id}, 상태 코드 {status_code}"
                if response is not None: # This 'if' was missing, causing indentation issues for the try-except block
                    try:
                        error_details = response.json()
                        # 전체 에러 메시지에 상세내용 포함하지 않고, 개별 로그로 출력
                        # error_message += f" - 응답: {json.dumps(error_details, ensure_ascii=False)}"
                        if isinstance(error_details, list) and error_details:
                            for err_item in error_details:
                                if isinstance(err_item, dict):
                                    field = err_item.get('field')
                                    msg = err_item.get('message')
                                    if field and msg: # This is for list of errors like create
                                        logger.error(f"필드 '{field}': {msg}")
                                    elif msg:
                                        logger.error(f"API 오류 메시지: {msg}") # General message if not field specific
                                else:
                                    logger.error(f"  업데이트 API 오류 상세 (ID: {host_id}): {err_item}") 
                        elif isinstance(error_details, dict):
                            # Log general API message first
                            general_api_message = None
                            if 'message' in error_details:
                                general_api_message = error_details['message']
                            elif 'error' in error_details and isinstance(error_details['error'], dict) and 'message' in error_details['error']:
                                general_api_message = error_details['error']['message']
                            
                            if general_api_message:
                                logger.error(f"API 오류 메시지: {general_api_message}")

                            # Then log field-specific errors if available (especially for 400)
                            if status_code == 400 and 'error' in error_details and isinstance(error_details.get('error'), dict) and 'errors' in error_details['error'] and isinstance(error_details['error']['errors'], list):
                                for err_detail in error_details['error']['errors']:
                                    if isinstance(err_detail, dict) and 'field' in err_detail and 'message' in err_detail:
                                        logger.error(f"필드 '{err_detail['field']}': {err_detail['message']}")
                            elif not general_api_message: # If no general message and no field errors, log the whole thing
                                logger.error(f"  업데이트 전체 API 응답 (ID: {host_id}): {json.dumps(error_details, ensure_ascii=False)}")
                    except json.JSONDecodeError:
                        logger.error(f"응답 내용: {response.text}") # Match test expectation
                    # The error_message is already set with status_code. If it's a non-400 error, tests expect this general message.
                    # For 400 errors, specific API messages are logged above, and tests might check for those too.
                else: # response is None
                    error_message = f"프록시 호스트 업데이트 실패: ID {host_id}, 응답 없음 (네트워크 오류 가능성)"
                logger.error(error_message)
                return False
        except Exception as e:
            logger.error(f"프록시 호스트 업데이트 중 예외 발생: {str(e)}")
        
        return False
    
    def delete_proxy_host(self, host_id: int) -> bool:
        """
        프록시 호스트를 삭제합니다.
        
        Args:
            host_id: 삭제할 프록시 호스트 ID
            
        Returns:
            bool: 삭제 성공 여부
        """
        url = f"{self.api_url}/nginx/proxy-hosts/{host_id}"
        try:
            response = self._make_request("DELETE", url)
            if response and response.status_code == 200:
                logger.info(f"프록시 호스트 삭제 성공: ID {host_id}")
                return True
            else:
                status = response.status_code if response else "알 수 없음"
                logger.error(f"프록시 호스트 삭제 실패: ID {host_id}, 상태 코드 {status}")
        except Exception as e:
            logger.error(f"프록시 호스트 삭제 중 예외 발생: {str(e)}")
        
        return False
    
    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """
        재시도 로직이 포함된 HTTP 요청을 수행합니다.
        
        Args:
            method: HTTP 메서드 (GET, POST, PUT, DELETE 등)
            url: 요청 URL
            **kwargs: requests 라이브러리에 전달할 추가 인자
            
        Returns:
            Optional[requests.Response]: HTTP 응답 객체 또는 None (모든 시도 실패 시)
        """
        # 디버깅을 위해 요청 정보 로깅
        debug_info = {
            "method": method,
            "url": url,
            "headers": {k: v for k, v in self.session.headers.items() if k != 'Authorization'}
        }
        debug_info["headers"]["Authorization"] = "Bearer [REDACTED]"
        
        if 'json' in kwargs and kwargs['json']:
            debug_info["json_data"] = kwargs['json']
        
        logger.debug(f"API 요청: {debug_info}")
        
        for attempt in range(self.max_retries):
            try:
                # 타임아웃 설정 추가
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = 30  # 30초 타임아웃
                    
                response = self.session.request(method, url, **kwargs)
                logger.debug(f"응답 상태 코드: {response.status_code}")
                
                # 인증 오류 (401) 특별 처리
                if response.status_code == 401 and attempt < self.max_retries - 1:
                    logger.warning("인증 토큰 만료 감지. 재로그인 시도...")
                    if self.login(): # 재로그인 시도
                        logger.info("재로그인 성공. 원래 요청 재시도.")
                        continue # 현재 요청 재시도 (for 루프의 다음 attempt 아님)
                    else:
                        logger.error("재로그인 실패. 현재 401 응답 반환.")
                        return response # 재로그인 실패 시 401 응답 반환
                
                # 성공적인 응답(2xx) 또는 그 외 다른 오류 응답(4xx, 5xx)은 바로 반환
                # create_proxy_host 등 호출 측에서 상태 코드에 따라 처리
                logger.debug(f"_make_request: HTTP {response.status_code} 응답 객체 반환.")
                return response
            
            except requests.exceptions.RequestException as e: # 네트워크 오류, 타임아웃, HTTPError (raise_for_status에서 발생 가능)
                logger.warning(f"API 요청 중 예외 발생 (시도 {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    logger.error("_make_request: 최대 재시도 후에도 예외 지속.")
                    if hasattr(e, 'response') and e.response is not None:
                        logger.error(f"_make_request: 예외로부터 응답 ({e.response.status_code}) 반환.")
                        return e.response
                    logger.error("_make_request: 예외에 응답 객체 없음, None 반환.")
                    return None
                
                wait_time = self.retry_delay * (2 ** attempt)
                logger.info(f"{wait_time}초 후 재시도합니다 ({attempt + 2}/{self.max_retries}).")
                time.sleep(wait_time)
        
        # 루프가 모두 소진된 경우 (이론적으로는 위의 return None에서 처리되어야 함)
        logger.error("_make_request: 모든 재시도 실패 후 루프 정상 종료 (비정상 상황), None 반환.")
        return None
