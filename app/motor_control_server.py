from flask import Flask, request, jsonify
import RPi.GPIO as GPIO
import time
import threading

# === 설정 영역 ===
IN1 = 6
IN2 = 13
IN3 = 19
IN4 = 26
STEP_SLEEP = 0.002
TARGET_REVOLUTIONS = 2
CYCLES_PER_REVOLUTION = 512
control_pins = [IN1, IN2, IN3, IN4]

# 8스텝 시퀀스 (Half-Step)
half_step_seq = [
    [1, 0, 0, 0], [1, 1, 0, 0], [0, 1, 0, 0], [0, 1, 1, 0],
    [0, 0, 1, 0], [0, 0, 1, 1], [0, 0, 0, 1], [1, 0, 0, 1]
]

# --- Flask 앱 설정 ---
app = Flask(__name__)

# 모터 동작 상태 및 잠금
motor_is_busy = False
motor_lock = threading.Lock()

def setup_gpio():
    """GPIO 초기화"""
    GPIO.setmode(GPIO.BCM)
    for pin in control_pins:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, 0)
    print("✓ GPIO for motor initialized")

def rotate(direction):
    """지정된 방향으로 모터를 회전시킵니다."""
    global motor_is_busy
    with motor_lock:
        if motor_is_busy:
            print("[MOTOR] Motor is busy. Ignoring new command.")
            return
        motor_is_busy = True

    try:
        print(f"[MOTOR] Rotating {direction} for {TARGET_REVOLUTIONS} turns...")
        
        # 방향에 따라 시퀀스 순서 결정 (매 반복마다 새로 생성해야 함)
        step_range = list(range(8)) if direction == 'right' else list(range(7, -1, -1))
        
        for i in range(TARGET_REVOLUTIONS):
            for _ in range(CYCLES_PER_REVOLUTION):
                for step in step_range:
                    for pin_idx, pin_val in enumerate(half_step_seq[step]):
                        GPIO.output(control_pins[pin_idx], pin_val)
                    time.sleep(STEP_SLEEP)
        
        GPIO.output(control_pins, 0) # 코일 끄기
        print(f"[MOTOR] Rotation {direction} finished.")

    finally:
        with motor_lock:
            motor_is_busy = False

@app.route('/control', methods=['POST'])
def control_motor():
    """모터 제어 엔드포인트. action: 'open' 또는 'close'"""
    data = request.json
    action = data.get('action')

    if action not in ['open', 'close']:
        return jsonify({'status': 'error', 'message': "Invalid action. Use 'open' or 'close'."}), 400

    if motor_is_busy:
        return jsonify({'status': 'busy', 'message': 'Motor is currently operating.'}), 503

    direction = 'right' if action == 'open' else 'left'
    
    # 백그라운드에서 모터 회전 실행
    thread = threading.Thread(target=rotate, args=(direction,))
    thread.start()
    
    return jsonify({'status': 'success', 'action': action}), 200

@app.route('/health', methods=['GET'])
def health_check():
    """헬스 체크 엔드포인트"""
    return jsonify({'status': 'ok'}), 200

def cleanup_gpio():
    print("\n[INFO] Cleaning up motor GPIO...", flush=True)
    GPIO.cleanup()

if __name__ == "__main__":
    setup_gpio()
    try:
        print("="*40, flush=True)
        print("  Motor Control Server Starting...", flush=True)
        print("="*40, flush=True)
        print("  - Actions: 'open', 'close'", flush=True)
        print("  - Endpoint: /control", flush=True)
        print("="*40, flush=True)
        print("  Server ready on http://0.0.0.0:5003", flush=True)
        print("="*40, flush=True)
        
        app.run(host='0.0.0.0', port=5003, debug=False)
        
    except Exception as e:
        print(f"[ERROR] Failed to start motor server: {e}", flush=True)
    finally:
        cleanup_gpio()