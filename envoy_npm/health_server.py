"""
EnvoyNPM 헬스체크 HTTP 서버
"""

import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger("envoy_npm.health_server")


class HealthCheckHandler(BaseHTTPRequestHandler):
    """헬스체크 요청 핸들러"""
    
    def do_GET(self):
        """GET 요청 처리"""
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "not_found"}')
    
    def log_message(self, format, *args):
        """로깅 오버라이드"""
        logger.debug(f"헬스체크 요청: {format % args}")


def start_health_server(port=8080):
    """
    헬스체크 HTTP 서버를 시작합니다.
    
    Args:
        port: 서버 포트
    """
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"헬스체크 서버가 포트 {port}에서 시작되었습니다")
    
    # 별도 스레드에서 서버 실행
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    
    return server
