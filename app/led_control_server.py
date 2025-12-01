# led_control_server.py
import RPi.GPIO as GPIO
from flask import Flask, request, jsonify
import time

# GPIO 핀 설정
RED_PIN = 4
BLUE_PIN = 17
GREEN_PIN = 27

# GPIO 초기화
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(RED_PIN, GPIO.OUT)
GPIO.setup(BLUE_PIN, GPIO.OUT)
GPIO.setup(GREEN_PIN, GPIO.OUT)

app = Flask(__name__)

def set_led_color(color):
    """지정된 색상에 따라 LED를 켜고 끕니다."""
    # 모든 LED를 끈다
    GPIO.output(RED_PIN, GPIO.LOW)
    GPIO.output(BLUE_PIN, GPIO.LOW)
    GPIO.output(GREEN_PIN, GPIO.LOW)
    
    if color == 'RED':
        GPIO.output(RED_PIN, GPIO.HIGH)
    elif color == 'BLUE':
        GPIO.output(BLUE_PIN, GPIO.HIGH)
    elif color == 'GREEN':
        GPIO.output(GREEN_PIN, GPIO.HIGH)
    elif color == 'OFF':
        pass # 모두 끈 상태 유지
    else:
        return False # 지원하지 않는 색상
    
    print(f"[LED] Set to {color}", flush=True)
    return True

@app.route('/control', methods=['POST'])
def control_led():
    """/control 엔드포인트에서 POST 요청을 받아 LED를 제어합니다."""
    data = request.json
    color = data.get('color', 'OFF').upper()
    
    if set_led_color(color):
        return jsonify({'status': 'success', 'color': color}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Invalid color specified'}), 400

@app.route('/health', methods=['GET'])
def health_check():
    """헬스 체크 엔드포인트"""
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    try:
        print("="*40, flush=True)
        print("  LED Control Server Starting...", flush=True)
        print("="*40, flush=True)
        print(f" - RED LED on GPIO {RED_PIN}", flush=True)
        print(f" - BLUE LED on GPIO {BLUE_PIN}", flush=True)
        print(f" - GREEN LED on GPIO {GREEN_PIN}", flush=True)
        print("="*40, flush=True)
        print("  Server ready on http://0.0.0.0:5002", flush=True)
        print("="*40, flush=True)
        
        # 서버 시작 시 모든 LED 끄기
        set_led_color('OFF')
        
        app.run(host='0.0.0.0', port=5002, debug=False)
        
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}", flush=True)
    finally:
        print("\n[INFO] Cleaning up GPIO...", flush=True)
        GPIO.cleanup()
