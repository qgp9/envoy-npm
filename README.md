# EnvoyNPM

**EnvoyNPM**은 Docker 컨테이너의 라이프사이클 이벤트를 모니터링하여 Nginx Proxy Manager(NPM)에 자동으로 리버스 프록시 설정을 생성하는 서비스입니다.

## 개요

CasaOS 환경에서 Docker 컨테이너의 시작, 정지, 종료 이벤트를 감지하고, 컨테이너의 환경변수에 정의된 정보를 기반으로 Nginx Proxy Manager에 리버스 프록시 호스트 설정을 자동으로 관리합니다.

## 주요 기능

- Docker 컨테이너 이벤트 실시간 모니터링
- 환경변수 기반 프록시 설정 자동화
- NPM 프록시 호스트 생성, 업데이트, 비활성화 자동 관리

## 설치 및 실행

```bash
# Docker Compose로 실행
docker-compose up -d
```

## 환경변수 설정

### EnvoyNPM 서비스 컨테이너 설정
- `NPM_API_URL`: NPM API의 기본 URL (필수)
- `NPM_API_EMAIL`: NPM 관리자 계정 이메일 (필수)
- `NPM_API_PASSWORD`: NPM 관리자 계정 비밀번호 (필수)
- `LOG_LEVEL`: 로깅 레벨 설정 (선택, 기본값: INFO)

### 모니터링 대상 앱 컨테이너 설정
- `NPM_HOST`: 프록시할 도메인 이름 (필수)
- `NPM_PORT`: 내부 웹 서비스 포트 (필수)
- `NPM_SSL`: SSL 적용 여부 (선택, 기본값: false)
- `NPM_ENABLE_WS`: 웹소켓 지원 여부 (선택, 기본값: false)
- `NPM_ENABLE_HSTS`: HSTS 활성화 여부 (선택, 기본값: false)

## 상세 문서

자세한 내용은 [스펙 문서](docs/specs.md)를 참조하세요.

## 라이선스

MIT
