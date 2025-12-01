FROM python:3.9-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 설치 (I2C 지원)
RUN apt-get update && apt-get install -y \
    python3-smbus \
    i2c-tools \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# 애플리케이션 코드 복사
COPY central_server.py .
COPY pwm_servo.py .
COPY app/led_control_server.py .
COPY app/motor_control_server.py .
COPY templates/ ./templates/
COPY static/ ./static

# 포트 노출
EXPOSE 5000

# 데이터베이스 및 이미지 저장 볼륨
VOLUME ["/app/data"]

# 서버 실행
CMD ["python", "-u", "central_server.py"]
