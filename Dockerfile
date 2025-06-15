FROM python:3.11-slim

LABEL maintainer="EnvoyNPM"
LABEL description="Docker 컨테이너 - Nginx Proxy Manager 자동화 서비스"

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY envoy_npm/ ./envoy_npm/

# 실행 권한 설정
RUN chmod +x ./envoy_npm/main.py

# 환경변수 설정
ENV PYTHONUNBUFFERED=1

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 앱 실행
CMD ["python", "-m", "envoy_npm.main"]
