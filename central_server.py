from flask import Flask, request, jsonify, render_template, send_from_directory
import sqlite3
import requests
from datetime import datetime
import threading
import time
import os


# BMP180 sensor is removed, as this server will now receive data from other sensors.
SENSOR_AVAILABLE = False
app = Flask(__name__)

DB_PATH = '/app/data/iot_system.db'

latest_sensor_data = {
    'temperature': None,
    'humidity': None,
    'pressure': None,
    'co2_level': None,
    'motion_detected': False,
    'motion_timestamp': None,
    'is_drowsy_alert': False,
    'idle_duration': 0.0,
    'noise_level': None,
    'noise_timestamp': None,
    'led_state': 'OFF' # LED 상태 추가
}

# 액추에이터 엔드포인트 (모터 추가)
ACTUATOR_ENDPOINTS = {
    'airconditioner': os.getenv('AC_ENDPOINT', 'http://192.168.0.101:5001/control'),
    'heater': os.getenv('HEATER_ENDPOINT', 'http://192.168.0.102:5001/control'),
    'ventilator': os.getenv('VENT_ENDPOINT', 'http://192.168.0.103:5001/control'),
    'light': os.getenv('LIGHT_ENDPOINT', 'http://192.168.0.104:5001/control'),
    'alarm': os.getenv('ALARM_ENDPOINT', 'http://192.168.0.105:5001/control'),
    'led': os.getenv('LED_ENDPOINT', 'http://led-controller:5002/control'),
    'motor': os.getenv('MOTOR_ENDPOINT', 'http://motor-controller:5003/control')
}

THRESHOLDS = {
    'temp_high': float(os.getenv('TEMP_HIGH', '28.0')),
    'temp_low': float(os.getenv('TEMP_LOW', '18.0')),
    'humidity_high': float(os.getenv('HUMIDITY_HIGH', '70.0')),
    'co2_high': float(os.getenv('CO2_HIGH', '1000.0')),
    'noise_high': float(os.getenv('NOISE_HIGH', '70.0')),
    'motion_timeout': int(os.getenv('MOTION_TIMEOUT', '300'))
}

co2_high_start_time = None
co2_normal_start_time = None

def init_db():
    """데이터베이스 초기화"""
    os.makedirs('/app/data', exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS sensor_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  sensor_type TEXT,
                  value REAL,
                  unit TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS motion_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  detected BOOLEAN,
                  is_drowsy_alert BOOLEAN,
                  idle_duration REAL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS noise_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  noise_level REAL,
                  duration REAL)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS control_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT,
                  device TEXT,
                  action TEXT,
                  reason TEXT)''')
    
    conn.commit()
    conn.close()
    print("✓ Database initialized", flush=True)

def save_sensor_data(sensor_type, value, unit):
    """센서 데이터를 DB에 저장"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO sensor_data (timestamp, sensor_type, value, unit)
                     VALUES (?, ?, ?, ?)''',
                  (datetime.now().isoformat(), sensor_type, value, unit))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] {e}", flush=True)

def save_control_log(device, action, reason):
    """제어 로그 저장"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO control_log (timestamp, device, action, reason)
                     VALUES (?, ?, ?, ?)''',
                  (datetime.now().isoformat(), device, action, reason))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] {e}", flush=True)



# API 엔드포인트들 (동일)
@app.route('/sensor/environment', methods=['POST'])
def receive_environment():
    data = request.json
    temperature = data.get('temperature')
    pressure = data.get('pressure')
    humidity = data.get('humidity')

    if temperature is not None:
        latest_sensor_data['temperature'] = temperature
        save_sensor_data('temperature', temperature, '°C')
        print(f"[ENV] Received Temperature: {temperature}°C", flush=True)

    if pressure is not None:
        latest_sensor_data['pressure'] = pressure
        save_sensor_data('pressure', pressure, 'hPa')
        print(f"[ENV] Received Pressure: {pressure}hPa", flush=True)

    if humidity is not None:
        latest_sensor_data['humidity'] = humidity
        save_sensor_data('humidity', humidity, '%')
        print(f"[ENV] Received Humidity: {humidity}%", flush=True)

    return jsonify({'status': 'success'}), 200


@app.route('/sensor/co2', methods=['POST'])
def receive_co2():
    data = request.json
    co2_level = float(data.get('co2_level'))
    
    latest_sensor_data['co2_level'] = co2_level
    save_sensor_data('co2', co2_level, 'ppm')
    
    print(f"[CO2] Received: {co2_level} ppm", flush=True)
    return jsonify({'status': 'success'}), 200

@app.route('/sensor/motion', methods=['POST'])
def receive_motion():
    data = request.json
    motion_detected = data.get('motion_detected', False)
    is_drowsy_alert = data.get('is_drowsy_alert', False)
    idle_duration = data.get('idle_duration', 0)
    
    # Update latest sensor data cache
    latest_sensor_data['motion_detected'] = motion_detected
    latest_sensor_data['is_drowsy_alert'] = is_drowsy_alert
    latest_sensor_data['idle_duration'] = idle_duration
    latest_sensor_data['motion_timestamp'] = datetime.now().isoformat()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO motion_log (timestamp, detected, is_drowsy_alert, idle_duration)
                     VALUES (?, ?, ?, ?)''',
                  (datetime.now().isoformat(), motion_detected, is_drowsy_alert, idle_duration))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] {e}", flush=True)
    
    print(f"[MOTION] Detected: {motion_detected}, Drowsy Alert: {is_drowsy_alert}, Idle: {idle_duration}s", flush=True)
    return jsonify({'status': 'success'}), 200

@app.route('/sensor/noise', methods=['POST'])
def receive_noise():
    data = request.json
    noise_level = data.get('noise_level')
    duration = data.get('duration', 0)
    
    latest_sensor_data['noise_level'] = noise_level
    latest_sensor_data['noise_timestamp'] = datetime.now().isoformat()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO noise_log (timestamp, noise_level, duration)
                     VALUES (?, ?, ?)''',
                  (datetime.now().isoformat(), noise_level, duration))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] {e}", flush=True)
    
    print(f"[NOISE] Level: {noise_level} dB, Duration: {duration}s", flush=True)
    return jsonify({'status': 'success'}), 200



def control_device(device, action, reason):
    """액추에이터 제어 명령 전송"""
    if device not in ACTUATOR_ENDPOINTS:
        print(f"[WARNING] Unknown device: {device}", flush=True)
        return False
    
    try:
        response = requests.post(
            ACTUATOR_ENDPOINTS[device],
            json={'action': action},
            timeout=5
        )
        
        save_control_log(device, action, reason)
        print(f"[CONTROL] {device} → {action} (Reason: {reason})", flush=True)
        return True
        
    except requests.exceptions.Timeout:
        print(f"[WARNING] Timeout controlling {device}", flush=True)
        return False
    except requests.exceptions.ConnectionError:
        print(f"[WARNING] Cannot connect to {device}", flush=True)
        return False
    except Exception as e:
        print(f"[ERROR] Failed to control {device}: {e}", flush=True)
        return False

def control_led(color, reason):
    """LED 제어를 위해 led_controller에 HTTP 요청을 전송"""
    global latest_sensor_data
    
    if latest_sensor_data['led_state'] == color:
        return False # 상태 변경이 없으면 요청 안함
        
    try:
        response = requests.post(
            ACTUATOR_ENDPOINTS['led'],
            json={'color': color},
            timeout=5
        )
        if response.status_code == 200:
            latest_sensor_data['led_state'] = color
            print(f"[LED CONTROL] LED set to {color} (Reason: {reason})", flush=True)
            save_control_log('led', color, reason)
            return True
        else:
            print(f"[LED ERROR] Failed to set LED color. Status: {response.status_code}", flush=True)
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"[LED ERROR] Cannot connect to led-controller: {e}", flush=True)
        return False

def decision_making_loop():
    """주기적으로 센서 데이터를 분석하고 제어 결정"""
    global co2_high_start_time, co2_normal_start_time
    print("[DECISION] Starting decision making loop...", flush=True)
    
    previous_state = {
        'airconditioner': None,
        'heater': None,
        'ventilator': None,
        'light': None,
        'alarm': None,
        'motor': None,
        'led': None
    }
    
    while True:
        try:
            temp = latest_sensor_data['temperature']
            humidity = latest_sensor_data['humidity']
            co2 = latest_sensor_data['co2_level']
            motion = latest_sensor_data['motion_detected']
            motion_time = latest_sensor_data['motion_timestamp']
            noise = latest_sensor_data['noise_level']
            
            # 1. 온도 기반 냉난방 제어
            if temp is not None:
                if temp > THRESHOLDS['temp_high']:
                    if previous_state['airconditioner'] != 'ON':
                        control_device('airconditioner', 'ON', f'Temperature too high: {temp:.1f}°C')
                        previous_state['airconditioner'] = 'ON'
                    if previous_state['heater'] != 'OFF':
                        control_device('heater', 'OFF', f'Temperature too high: {temp:.1f}°C')
                        previous_state['heater'] = 'OFF'
                elif temp < THRESHOLDS['temp_low']:
                    if previous_state['heater'] != 'ON':
                        control_device('heater', 'ON', f'Temperature too low: {temp:.1f}°C')
                        previous_state['heater'] = 'ON'
                    if previous_state['airconditioner'] != 'OFF':
                        control_device('airconditioner', 'OFF', f'Temperature too low: {temp:.1f}°C')
                        previous_state['airconditioner'] = 'OFF'
                else:
                    if previous_state['airconditioner'] != 'OFF':
                        control_device('airconditioner', 'OFF', f'Temperature normal: {temp:.1f}°C')
                        previous_state['airconditioner'] = 'OFF'
                    if previous_state['heater'] != 'OFF':
                        control_device('heater', 'OFF', f'Temperature normal: {temp:.1f}°C')
                        previous_state['heater'] = 'OFF'

            # 2. CO2 기반 환기 및 모터 제어 (5초 지연)
            if co2 is not None:
                if co2 > THRESHOLDS['co2_high']:
                    co2_normal_start_time = None
                    if co2_high_start_time is None:
                        co2_high_start_time = time.time()
                    
                    if (time.time() - co2_high_start_time) >= 5:
                        if previous_state['ventilator'] != 'ON':
                            control_device('ventilator', 'ON', f'CO2 high for >=5s: {co2:.0f} ppm')
                            previous_state['ventilator'] = 'ON'
                        if previous_state['motor'] != 'open':
                            control_device('motor', 'open', f'CO2 high for >=5s: {co2:.0f} ppm')
                            previous_state['motor'] = 'open'
                else:
                    co2_high_start_time = None
                    if co2_normal_start_time is None:
                        co2_normal_start_time = time.time()

                    if (time.time() - co2_normal_start_time) >= 5:
                        if previous_state['ventilator'] != 'OFF':
                            control_device('ventilator', 'OFF', f'CO2 normal for >=5s: {co2:.0f} ppm')
                            previous_state['ventilator'] = 'OFF'
                        if previous_state['motor'] != 'close':
                            control_device('motor', 'close', f'CO2 normal for >=5s: {co2:.0f} ppm')
                            previous_state['motor'] = 'close'

            # 3. 습도 기반 환기 제어
            if humidity is not None and humidity > THRESHOLDS['humidity_high']:
                if previous_state['ventilator'] != 'ON':
                    control_device('ventilator', 'ON', f'Humidity too high: {humidity:.1f}%')
                    previous_state['ventilator'] = 'ON'

            # 4. 움직임 감지 조명 제어
            if motion:
                if previous_state['light'] != 'ON':
                    control_device('light', 'ON', 'Motion detected')
                    previous_state['light'] = 'ON'
            elif motion_time:
                try:
                    last_motion = datetime.fromisoformat(motion_time)
                    if (datetime.now() - last_motion).total_seconds() > THRESHOLDS['motion_timeout']:
                        if previous_state['light'] != 'OFF':
                            control_device('light', 'OFF', f'No motion for {THRESHOLDS["motion_timeout"]}s')
                            previous_state['light'] = 'OFF'
                except Exception:
                    pass

            # 5. 소음 기반 알람 제어
            if noise is not None:
                if noise > THRESHOLDS['noise_high']:
                    if previous_state['alarm'] != 'ON':
                        control_device('alarm', 'ON', f'Noise level too high: {noise:.0f} dB')
                        previous_state['alarm'] = 'ON'
                else:
                    if previous_state['alarm'] != 'OFF':
                        control_device('alarm', 'OFF', f'Noise level normal: {noise:.0f} dB')
                        previous_state['alarm'] = 'OFF'

            # 6. LED 상태 결정 로직 (우선순위 기반)
            desired_led_color = 'OFF'
            led_reason = 'All systems normal'
            
            if temp is not None:
                if temp > THRESHOLDS['temp_high']:
                    desired_led_color = 'BLUE'
                    led_reason = f'Temperature too high: {temp:.1f}°C'
                elif temp < THRESHOLDS['temp_low']:
                    desired_led_color = 'RED'
                    led_reason = f'Temperature too low: {temp:.1f}°C'
                elif noise is not None and noise > THRESHOLDS['noise_high']:
                    desired_led_color = 'GREEN'
                    led_reason = f'Noise level too high: {noise:.0f} dB'
            
            if previous_state['led'] != desired_led_color:
                control_led(desired_led_color, led_reason)
                previous_state['led'] = desired_led_color

        except Exception as e:
            print(f"[DECISION ERROR] {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        time.sleep(5)

@app.route('/thresholds', methods=['GET', 'POST'])
def manage_thresholds():
    if request.method == 'GET':
        return jsonify(THRESHOLDS), 200
    
    data = request.json
    for key, value in data.items():
        if key in THRESHOLDS:
            THRESHOLDS[key] = value
            print(f"[CONFIG] Updated {key} = {value}", flush=True)
    
    return jsonify({'status': 'success', 'thresholds': THRESHOLDS}), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/logs/<log_type>', methods=['GET'])
def get_logs(log_type):
    limit = request.args.get('limit', 50, type=int)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if log_type == 'motion':
        c.execute('SELECT * FROM motion_log ORDER BY timestamp DESC LIMIT ?', (limit,))
    elif log_type == 'noise':
        c.execute('SELECT * FROM noise_log ORDER BY timestamp DESC LIMIT ?', (limit,))
    elif log_type == 'control':
        c.execute('SELECT * FROM control_log ORDER BY timestamp DESC LIMIT ?', (limit,))
    elif log_type == 'sensor':
        c.execute('SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT ?', (limit,))
    else:
        conn.close()
        return jsonify({'error': 'Invalid log type'}), 400
    
    logs = c.fetchall()
    conn.close()
    
    return jsonify({'logs': logs}), 200

@app.route('/')
def home():
    """메인 페이지 - 대시보드"""
    return render_template('dashboard.html')

@app.route('/dashboard')
def dashboard_page():
    """대시보드 페이지"""
    return render_template('dashboard.html')

@app.route('/static/<path:path>')
def send_static(path):
    """정적 파일 제공"""
    return send_from_directory('static', path)


@app.route('/status', methods=['GET'])
def get_status():
    """현재 상태 API"""
    return jsonify({
        'sensor_data': latest_sensor_data,
        'thresholds': THRESHOLDS,
        'actuator_endpoints': ACTUATOR_ENDPOINTS,
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/api/info', methods=['GET'])
def api_info():
    """서버 정보 API"""
    return jsonify({
        'service': 'IoT Central Server',
        'status': 'running',
        'sensor_available': SENSOR_AVAILABLE,
        'version': '1.0.0'
    }), 200

if __name__ == '__main__':
    print("=" * 60, flush=True)
    print("        IoT Central Server Starting...", flush=True)
    print("=" * 60, flush=True)
    
    print(f"Sensor Available: {SENSOR_AVAILABLE}", flush=True)
    print(f"Database Path: {DB_PATH}", flush=True)
    print(f"Thresholds: {THRESHOLDS}", flush=True)
    print("=" * 60, flush=True)
    
    init_db()
    
    decision_thread = threading.Thread(target=decision_making_loop)
    decision_thread.start()
    print("✓ Decision making thread started", flush=True)
        
    print("=" * 60, flush=True)
    print("        Server ready on http://0.0.0.0:5000", flush=True)
    print("=" * 60, flush=True)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
