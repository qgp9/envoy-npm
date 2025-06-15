# **EnvoyNPM: Docker 컨테이너 - Nginx Proxy Manager 자동화 서비스 스펙**

## 1. 개요 (Overview)

**EnvoyNPM**은 `CasaOS` 환경에서 Docker 컨테이너의 라이프사이클 이벤트(시작, 정지, 종료)를 모니터링하여, 컨테이너의 환경변수에 정의된 정보를 기반으로 `Nginx Proxy Manager (NPM)`에 리버스 프록시 호스트 설정을 자동으로 생성, 업데이트, 비활성화하는 파이썬 기반 서비스입니다.

**목표**: `CasaOS` 앱 스토어를 통해 배포된 앱들이 별도의 수동 설정 없이 자동으로 `NPM` 리버스 프록시를 통해 접근 가능하도록 하여, `CasaOS`의 편의성과 `NPM`의 관리 기능을 결합합니다.

---

## 2. 핵심 기능 (Core Functionality)

* Docker 컨테이너의 `start`, `stop`, `die` 이벤트를 실시간으로 감지합니다.
* 감지된 컨테이너에서 미리 정의된 환경변수(예: `NPM_HOST`, `NPM_PORT`)를 추출합니다.
* 추출된 정보를 바탕으로 `NPM`의 REST API를 호출하여 프록시 호스트를 생성하거나, 기존 호스트를 업데이트/비활성화합니다.
* `NPM`에 등록된 프록시 호스트가 `EnvoyNPM`에 의해 관리되는지 여부를 식별합니다.

---

## 3. 주요 구성 요소 (Key Components)

1.  **EnvoyNPM 서비스 컨테이너**:
    * 본 프로젝트의 결과물입니다. 파이썬으로 개발되며 Docker 컨테이너로 배포됩니다.
    * `CasaOS` 환경에서 Docker 소켓과 NPM API에 접근 가능한 상태로 실행됩니다.
2.  **Nginx Proxy Manager (NPM) 컨테이너**:
    * 기존에 `CasaOS`에 설치되어 실행 중인 NPM 인스턴스입니다.
    * EnvoyNPM이 접근할 수 있는 REST API 엔드포인트를 제공합니다.
3.  **Dockerized App 컨테이너**:
    * `CasaOS` 앱 스토어를 통해 설치된, `EnvoyNPM`이 프록시 설정을 자동화할 대상 앱 컨테이너들입니다.
    * 환경변수를 통해 프록시 설정 정보를 `EnvoyNPM`에게 전달합니다.

---

## 4. 기술 스택 및 배포 (Technical Stack & Deployment)

* **프로그래밍 언어**: Python 3.x
* **주요 라이브러리**:
    * `docker-py`: Docker API 연동 (이벤트 모니터링, 컨테이너 정보 조회)
    * `requests`: NPM REST API 호출
    * `logging`: 상세 로깅
* **배포 환경**: Docker 컨테이너 (OCI 이미지)
* **필수 접근 권한**:
    * **Docker 소켓**: `/var/run/docker.sock`을 `ro` (읽기 전용) 모드로 볼륨 마운트하여 Docker 데몬과 통신합니다.
    * **네트워크 접근**: NPM 컨테이너의 API 엔드포인트에 접근 가능해야 합니다 (같은 네트워크에 조인하거나, IP 주소/FQDN으로 접근 가능하도록 구성).

---

## 5. 설정 (Configuration)

### 5.1. `EnvoyNPM` 서비스 컨테이너의 환경변수 (EnvoyNPM 자체 설정)

`EnvoyNPM` 컨테이너를 배포할 때 다음 환경변수를 설정합니다.

* `NPM_API_URL`: **필수**. NPM API의 기본 URL (예: `http://your_npm_ip_or_hostname:81`).
* `NPM_API_EMAIL`: **필수**. NPM 관리자 계정 이메일 (API 인증용).
* `NPM_API_PASSWORD`: **필수**. NPM 관리자 계정 비밀번호 (API 인증용).
* `LOG_LEVEL`: (선택) 로깅 레벨 설정 (예: `INFO`, `DEBUG`, `WARNING`, `ERROR`). 기본값은 `INFO`.

### 5.2. 모니터링 대상 앱 컨테이너의 환경변수 (Proxy 설정 정보)

`CasaOS` 앱 스토어에서 앱을 설치할 때, 각 앱 컨테이너의 `environment` 섹션에 다음 환경변수를 추가합니다.

* `NPM_HOST`: **필수**. 이 컨테이너를 프록시할 도메인 이름 (예: `nextcloud.yourdomain.com`, `app.local`).
* `NPM_PORT`: **필수**. 이 컨테이너의 내부 웹 서비스 포트 (예: `80`, `8080`, `443`).
* `NPM_SSL`: (선택) SSL 적용 여부 (`true` / `false`). `EnvoyNPM`은 이 값을 NPM API의 `certificate_id` 및 `ssl_forced` 필드에 반영할 수 있도록 추후 확장 가능. **현재 스펙에서는 내부망용이므로 기본 `false` 처리 (SSL 제외).**
* `NPM_NETWORK`: (선택) 컨테이너가 속한 특정 Docker 네트워크 이름. IP 주소를 찾거나 감시 대상을 필터링하는 데 활용될 수 있습니다. (구현 시 고려)
* `NPM_ENABLE_WS`: (선택) 웹소켓 지원 여부 (`true` / `false`). NPM API의 `allow_web_sockets` 필드에 반영. 기본값 `false`.
* `NPM_ENABLE_HSTS`: (선택) HSTS(HTTP Strict Transport Security) 활성화 여부 (`true` / `false`). NPM API의 `hsts_enabled` 필드에 반영. 기본값 `false`.
* `NPM_ADVANCED_CONFIG`: (선택) NPM의 `advanced_config` 필드에 주입할 Nginx 설정 스니펫 문자열. 복잡한 특정 설정을 위해 사용.

---

## 6. 작동 로직 (Operational Logic)

### 6.1. 초기화 (Initialization)

* `EnvoyNPM` 서비스 시작 시, `NPM_API_URL`, `NPM_API_EMAIL`, `NPM_API_PASSWORD`를 사용하여 NPM API에 로그인하고 JWT 토큰을 획득합니다.
* NPM에 존재하는 모든 프록시 호스트 목록을 가져와 `EnvoyNPM`의 내부 캐시(`self.current_npm_hosts`)에 저장합니다. 이때 `meta` 필드를 파싱하여 `EnvoyNPM`이 관리하는 호스트인지 식별합니다.
* 현재 실행 중인 모든 Docker 컨테이너를 스캔하여, 각 컨테이너에 대해 `container start` 이벤트와 동일한 로직을 적용합니다.

### 6.2. Docker 이벤트 리스너 (Docker Event Listener)

* `docker-py`를 사용하여 `container start`, `container stop`, `container die` 이벤트를 지속적으로 모니터링합니다.

### 6.3. 컨테이너 시작 이벤트 처리 (`on_container_start`)

1.  **정보 추출**:
    * 시작된 컨테이너의 ID, 이름, 모든 환경변수를 가져옵니다.
    * `NPM_HOST`, `NPM_PORT` (필수) 및 기타 `NPM_` 접두사가 붙은 환경변수들을 파싱합니다.
    * 컨테이너의 내부 IP 주소를 확인합니다 (네트워크 구성에 따라 달라질 수 있으므로 신중하게 처리).
    * `NPM_HOST` 또는 `NPM_PORT`가 없으면 `WARNING` 로깅 후 처리 중단합니다.

2.  **프록시 호스트 존재 여부 확인**:
    * `NPM_HOST`로 지정된 도메인을 가진 프록시 호스트가 `self.current_npm_hosts` 캐시에 존재하는지 확인합니다.

3.  **관리 정책 적용 (핵심)**:

    * **A) `EnvoyNPM`이 관리하는 기존 호스트인 경우 (`meta.managed_by == "EnvoyNPM"`)**:
        * **A-1) 컨테이너 ID가 동일**: (컨테이너 재시작, 업데이트 등)
            * 해당 프록시 호스트의 `forward_host`, `forward_port` 및 기타 설정을 현재 컨테이너 정보로 **업데이트**합니다.
            * `enabled` 필드를 `1` (활성화)로 설정하고, `comments` 필드를 현재 상태에 맞춰 업데이트합니다.
            * `meta.container_id`를 최신 컨테이너 ID로 업데이트합니다.
        * **A-2) 컨테이너 ID가 다름**: (새 컨테이너가 동일 도메인 사용 - `CasaOS`에서 앱을 삭제하고 다시 설치한 경우 등)
            * **정책**: 기존 프록시 호스트의 `forward_host`, `forward_port` 및 `meta.container_id`를 새 컨테이너 정보로 **업데이트**합니다.
            * 로그에 "도메인 재사용 감지 및 업데이트" 메시지를 남깁니다.

    * **B) 수동으로 생성된 기존 호스트인 경우 (`meta.managed_by` 필드 없음 또는 다름)**:
        * **정책 (안전 우선)**: 해당 도메인에 대한 프록시 생성을 **스킵**하고 `WARNING` 레벨로 로깅합니다. `EnvoyNPM`은 수동으로 관리되는 호스트를 건드리지 않습니다. 사용자는 이 호스트를 `EnvoyNPM`이 관리하게 하려면 수동으로 삭제해야 합니다.
        * (선택적 고급 기능: 환경변수를 통해 수동 호스트 오버라이드/편입을 허용할 수 있으나, 초기 버전에서는 제외)

    * **C) 새로운 호스트인 경우**:
        * NPM API를 통해 새로운 프록시 호스트를 생성합니다.
        * **`meta` 필드 설정**: `{"managed_by": "EnvoyNPM", "container_id": "<현재 컨테이너 ID>", "created_at": "<현재 타임스탬프>"}`
        * **`comments` 필드 설정**: `"[EnvoyNPM Managed] Linked to: <컨테이너 이름> (<NPM_HOST>)"`
        * NPM API 스키마에 맞춰 `domain_names`, `forward_host`, `forward_port`, `forward_scheme` (http), `enabled: 1` 등 필요한 필드들을 채웁니다.

4.  **캐시 업데이트**: NPM API 호출 성공 후 `self.current_npm_hosts` 캐시를 최신 상태로 업데이트합니다.

### 6.4. 컨테이너 정지/종료 이벤트 처리 (`on_container_stop_or_die`)

1.  **정보 추출**: 종료된 컨테이너의 ID를 가져옵니다.
2.  **관련 호스트 확인**: `EnvoyNPM`이 관리 중인 컨테이너 캐시(`self.active_docker_containers`) 또는 NPM API 조회 및 `meta.container_id`를 통해 해당 컨테이너와 연결된 NPM 프록시 호스트가 있는지 확인합니다.
3.  **관리 정책 적용**:
    * **A) `EnvoyNPM`이 관리하는 호스트인 경우**:
        * **정책**: 해당 프록시 호스트의 `enabled` 필드를 `0` (비활성화)으로 업데이트합니다.
        * `comments` 필드를 `"[EnvoyNPM Managed] DISABLED: Container stopped/died (<NPM_HOST>)"` 등으로 업데이트하여 상태를 명확히 합니다.
        * (선택적 고급 기능: 일정 기간 후 자동 삭제, 또는 특정 도메인에 대한 재사용 감지 시 자동 재활성화 등의 로직은 추후 추가)
    * **B) 수동으로 생성된 호스트인 경우**:
        * **정책**: **절대 건드리지 않습니다.**

4.  **캐시 업데이트**: `self.active_docker_containers`에서 해당 컨테이너 정보를 제거하고, `self.current_npm_hosts` 캐시를 업데이트합니다.

---

## 7. 견고성 및 오류 처리 (Robustness & Error Handling)

* **API 재시도**: NPM API 호출 실패 시, 지수 백오프(exponential backoff)를 사용하여 여러 번 재시도합니다. 특정 횟수 이상 실패 시 치명적 오류로 로깅합니다.
* **로그 관리**: 모든 주요 작업, 오류, 경고에 대해 상세한 로깅을 수행합니다. `logging` 모듈을 적절히 사용하여 로그 레벨을 구분합니다.
* **예외 처리**: Docker API 및 `requests` 라이브러리에서 발생할 수 있는 모든 예외를 적절히 처리하여 서비스가 비정상적으로 종료되지 않도록 합니다.
* **멱등성(Idempotency)**: 프록시 호스트 생성/업데이트 로직은 여러 번 실행되어도 동일한 최종 상태를 보장하도록 설계합니다.

---

## 8. 향후 개선 사항 (Future Enhancements)

* **정기 동기화**: Docker 이벤트 누락 또는 NPM 설정이 수동으로 변경된 경우를 대비하여, 일정 시간마다 전체 컨테이너 및 NPM 호스트를 스캔하여 불일치를 해결하는 정기 동기화 로직 추가.
* **다중 도메인 지원**: 하나의 컨테이너에 `NPM_HOST_1`, `NPM_HOST_2` 등으로 여러 도메인을 설정할 수 있도록 확장.
* **고급 NPM 설정 지원**: `NPM_LOCATIONS`, `NPM_ACCESS_LISTS` 등 NPM API의 다양한 필드를 환경변수로 제어할 수 있도록 확장.
* **SSL 처리 개선**: `NPM_SSL=true` 일 경우 NPM의 `certificate_id`를 자동으로 선택하거나 새로 발급받는 로직 추가 (내부망 SSL 솔루션과 연동).
* **웹 UI/대시보드**: `EnvoyNPM` 자체의 상태, 감지된 컨테이너, 관리 중인 프록시 목록 등을 보여주는 간단한 웹 대시보드 추가.