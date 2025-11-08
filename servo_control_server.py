#!/usr/bin/env python3
from flask import Flask, request, jsonify
import time

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except:
    print("Warning: RPi.GPIO not available - running in simulation mode")
    GPIO_AVAILABLE = False

app = Flask(__name__)

SERVO_PIN = 18  # GPIO 18번 핀 (물리 핀 12번)

def setup_servo():
    """서보 모터 초기화"""
    if not GPIO_AVAILABLE:
        print("[SERVO] Running in simulation mode")
        return None
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SERVO_PIN, GPIO.OUT)
    pwm = GPIO.PWM(SERVO_PIN, 50)  # 50Hz
    pwm.start(0)
    print("[SERVO] GPIO initialized on pin", SERVO_PIN)
    return pwm

# 서보 초기화
pwm = setup_servo()

def set_angle(angle):
    """서보 각도 설정 (0-180도)"""
    if not GPIO_AVAILABLE:
        print(f"[SERVO SIMULATION] Setting angle to {angle}°")
        return True
    
    try:
        duty = 2 + (angle / 18)
        GPIO.output(SERVO_PIN, True)
        pwm.ChangeDutyCycle(duty)
        time.sleep(1)
        GPIO.output(SERVO_PIN, False)
        pwm.ChangeDutyCycle(0)
        print(f"[SERVO] Set angle to {angle}°")
        return True
    except Exception as e:
        print(f"[SERVO ERROR] {e}")
        return False

@app.route('/control', methods=['POST'])
def control_servo():
    """서보 제어 엔드포인트"""
    data = request.json
    action = data.get('action', '').lower()
    
    print(f"[REQUEST] Received action: {action}")
    
    try:
        if action == 'open':
            result = set_angle(0)  # 0도 - 창문 열기
            return jsonify({
                'status': 'success', 
                'action': 'open',
                'angle': 0,
                'gpio_available': GPIO_AVAILABLE
            }), 200
            
        elif action == 'close':
            result = set_angle(90)  # 90도 - 창문 닫기
            return jsonify({
                'status': 'success', 
                'action': 'close',
                'angle': 90,
                'gpio_available': GPIO_AVAILABLE
            }), 200
            
        elif action.isdigit():
            # 각도를 직접 지정
            angle = int(action)
            if 0 <= angle <= 180:
                result = set_angle(angle)
                return jsonify({
                    'status': 'success', 
                    'action': 'set_angle',
                    'angle': angle,
                    'gpio_available': GPIO_AVAILABLE
                }), 200
            else:
                return jsonify({
                    'status': 'error', 
                    'message': 'Angle must be between 0 and 180'
                }), 400
        else:
            return jsonify({
                'status': 'error', 
                'message': 'Invalid action. Use "open", "close", or angle (0-180)'
            }), 400
            
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': str(e)
        }), 500

@app.route('/status', methods=['GET'])
def status():
    """서보 상태 확인"""
    return jsonify({
        'service': 'Servo Control Server',
        'gpio_available': GPIO_AVAILABLE,
        'pin': SERVO_PIN,
        'status': 'running'
    }), 200

@app.route('/health', methods=['GET'])
def health():
    """헬스체크"""
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    try:
        print("=" * 60)
        print("        Servo Control Server Starting...")
        print("=" * 60)
        print(f"GPIO Available: {GPIO_AVAILABLE}")
        print(f"Servo Pin: {SERVO_PIN}")
        print(f"Server Port: 5001")
        print("=" * 60)
        
        app.run(host='0.0.0.0', port=5001, debug=False)
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        if pwm and GPIO_AVAILABLE:
            pwm.stop()
            GPIO.cleanup()
            print("GPIO cleaned up")
