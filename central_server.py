from flask import Flask, request, jsonify, render_template, send_from_directory
import sqlite3
import requests
from datetime import datetime
import threading
import time
import os


# BMP180 센서 초기화
try:
    from smbus2 import SMBus

    class BMP180:
        def __init__(self, address=0x77, bus=1):
            self.bus = SMBus(bus)
            self.address = address
            self.load_calibration()

        def load_calibration(self):
            """BMP180 캘리브레이션 데이터 읽기"""
            self.AC1 = self.read_int16(0xAA)
            self.AC2 = self.read_int16(0xAC)
            self.AC3 = self.read_int16(0xAE)
            self.AC4 = self.read_uint16(0xB0)
            self.AC5 = self.read_uint16(0xB2)
            self.AC6 = self.read_uint16(0xB4)
            self.B1 = self.read_int16(0xB6)
            self.B2 = self.read_int16(0xB8)
            self.MB = self.read_int16(0xBA)
            self.MC = self.read_int16(0xBC)
            self.MD = self.read_int16(0xBE)

        def read_int16(self, register):
            """16비트 signed int 읽기"""
            data = self.bus.read_i2c_block_data(self.address, register, 2)
            value = (data[0] << 8) + data[1]
            if value >= 0x8000:
                value = -((65535 - value) + 1)
            return value

        def read_uint16(self, register):
            """16비트 unsigned int 읽기"""
            data = self.bus.read_i2c_block_data(self.address, register, 2)
            return (data[0] << 8) + data[1]

        def read_raw_temp(self):
            """원시 온도 데이터 읽기"""
            self.bus.write_byte_data(self.address, 0xF4, 0x2E)
            time.sleep(0.05)
            data = self.bus.read_i2c_block_data(self.address, 0xF6, 2)
            return (data[0] << 8) + data[1]

        def read_raw_pressure(self):
            """원시 기압 데이터 읽기"""
            self.bus.write_byte_data(self.address, 0xF4, 0x34 + (3 << 6))
            time.sleep(0.06)
            data = self.bus.read_i2c_block_data(self.address, 0xF6, 3)
            return ((data[0] << 16) + (data[1] << 8) + data[2]) >> (8 - 3)

        def read_temperature(self):
            """온도 읽기 (°C)"""
            UT = self.read_raw_temp()
            X1 = ((UT - self.AC6) * self.AC5) >> 15
            X2 = (self.MC << 11) // (X1 + self.MD)
            B5 = X1 + X2
            temp = ((B5 + 8) >> 4) / 10.0
            return temp

        def read_pressure(self):
            """기압 읽기 (Pa)"""
            UT = self.read_raw_temp()
            UP = self.read_raw_pressure()

            X1 = ((UT - self.AC6) * self.AC5) >> 15
            X2 = (self.MC << 11) // (X1 + self.MD)
            B5 = X1 + X2

            B6 = B5 - 4000
            X1 = (self.B2 * ((B6 * B6) >> 12)) >> 11
            X2 = (self.AC2 * B6) >> 11
            X3 = X1 + X2
            B3 = (((self.AC1 * 4 + X3) << 3) + 2) // 4
            X1 = (self.AC3 * B6) >> 13
            X2 = (self.B1 * ((B6 * B6) >> 12)) >> 16
            X3 = ((X1 + X2) + 2) >> 2
            B4 = (self.AC4 * (X3 + 32768)) >> 15
            B7 = (UP - B3) * (50000 >> 3)

            if B7 < 0x80000000:
                p = (B7 * 2) // B4
            else:
                p = (B7 // B4) * 2

            X1 = (p >> 8) * (p >> 8)
            X1 = (X1 * 3038) >> 16
            X2 = (-7357 * p) >> 16
            p = p + ((X1 + X2 + 3791) >> 4)

            return p

    bmp_sensor = BMP180()
    SENSOR_AVAILABLE = True
    print("✓ BMP180 sensor initialized (smbus2)", flush=True)

except Exception as e:
    print(f"⚠️  BMP180 sensor not available: {e}", flush=True)
    print("   Running in server-only mode", flush=True)
    bmp_sensor = None
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
    'noise_level': None,
    'noise_timestamp': None
}

# 액추에이터 엔드포인트 (서보 추가)
ACTUATOR_ENDPOINTS = {
    'airconditioner': os.getenv('AC_ENDPOINT', 'http://192.168.0.101:5001/control'),
    'heater': os.getenv('HEATER_ENDPOINT', 'http://192.168.0.102:5001/control'),
    'ventilator': os.getenv('VENT_ENDPOINT', 'http://192.168.0.103:5001/control'),
    'light': os.getenv('LIGHT_ENDPOINT', 'http://192.168.0.104:5001/control'),
    'alarm': os.getenv('ALARM_ENDPOINT', 'http://192.168.0.105:5001/control'),
    'servo': os.getenv('SERVO_ENDPOINT', 'http://192.168.0.146:5001/control')  # 로컬 서보
}

THRESHOLDS = {
    'temp_high': float(os.getenv('TEMP_HIGH', '25.0')),
    'temp_low': float(os.getenv('TEMP_LOW', '18.0')),
    'humidity_high': float(os.getenv('HUMIDITY_HIGH', '70.0')),
    'co2_high': float(os.getenv('CO2_HIGH', '1000.0')),
    'noise_high': float(os.getenv('NOISE_HIGH', '70.0')),
    'motion_timeout': int(os.getenv('MOTION_TIMEOUT', '300'))
}

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
                  image_path TEXT)''')
    
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

def bmp180_reading_loop():
    """BMP180 센서를 주기적으로 읽어서 데이터 업데이트"""
    if not SENSOR_AVAILABLE:
        print("[BMP180] Sensor not available, skipping reading loop", flush=True)
        return
    
    print("[BMP180] Starting sensor reading loop...", flush=True)
    
    while True:
        try:
            temperature = bmp_sensor.read_temperature()
            pressure = bmp_sensor.read_pressure() / 100.0
            
            latest_sensor_data['temperature'] = temperature
            latest_sensor_data['pressure'] = pressure
            
            save_sensor_data('temperature', temperature, '°C')
            save_sensor_data('pressure', pressure, 'hPa')
            
            print(f"[BMP180] Temp: {temperature:.1f}°C, Pressure: {pressure:.1f}hPa", flush=True)
            
        except Exception as e:
            print(f"[BMP180 ERROR] {e}", flush=True)
        
        time.sleep(10)

# API 엔드포인트들 (동일)
@app.route('/sensor/co2', methods=['POST'])
def receive_co2():
    data = request.json
    co2_level = data.get('co2_level')
    
    latest_sensor_data['co2_level'] = co2_level
    save_sensor_data('co2', co2_level, 'ppm')
    
    print(f"[CO2] Received: {co2_level} ppm", flush=True)
    return jsonify({'status': 'success'}), 200

@app.route('/sensor/motion', methods=['POST'])
def receive_motion():
    data = request.json
    motion_detected = data.get('motion_detected', False)
    image_path = data.get('image_path', None)
    
    latest_sensor_data['motion_detected'] = motion_detected
    latest_sensor_data['motion_timestamp'] = datetime.now().isoformat()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT INTO motion_log (timestamp, detected, image_path)
                     VALUES (?, ?, ?)''',
                  (datetime.now().isoformat(), motion_detected, image_path))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] {e}", flush=True)
    
    print(f"[MOTION] Detected: {motion_detected}, Image: {image_path}", flush=True)
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

@app.route('/sensor/humidity', methods=['POST'])
def receive_humidity():
    data = request.json
    humidity = data.get('humidity')
    
    latest_sensor_data['humidity'] = humidity
    save_sensor_data('humidity', humidity, '%')
    
    print(f"[HUMIDITY] Received: {humidity}%", flush=True)
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

def decision_making_loop():
    """주기적으로 센서 데이터를 분석하고 제어 결정"""
    print("[DECISION] Starting decision making loop...", flush=True)
    
    previous_state = {
        'airconditioner': None,
        'heater': None,
        'ventilator': None,
        'light': None,
        'alarm': None,
        'servo': None
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
                        control_device('airconditioner', 'ON',
                                     f'Temperature too high: {temp:.1f}°C')
                        previous_state['airconditioner'] = 'ON'
                    
                    if previous_state['heater'] != 'OFF':
                        control_device('heater', 'OFF',
                                     f'Temperature too high: {temp:.1f}°C')
                        previous_state['heater'] = 'OFF'
                    
                elif temp < THRESHOLDS['temp_low']:
                    if previous_state['heater'] != 'ON':
                        control_device('heater', 'ON',
                                     f'Temperature too low: {temp:.1f}°C')
                        previous_state['heater'] = 'ON'
                    
                    if previous_state['airconditioner'] != 'OFF':
                        control_device('airconditioner', 'OFF',
                                     f'Temperature too low: {temp:.1f}°C')
                        previous_state['airconditioner'] = 'OFF'
                else:
                    if previous_state['airconditioner'] != 'OFF':
                        control_device('airconditioner', 'OFF',
                                     f'Temperature normal: {temp:.1f}°C')
                        previous_state['airconditioner'] = 'OFF'
                    
                    if previous_state['heater'] != 'OFF':
                        control_device('heater', 'OFF',
                                     f'Temperature normal: {temp:.1f}°C')
                        previous_state['heater'] = 'OFF'
            
            # 2. CO2 기반 환기 제어 + 서보 모터 (HTTP 요청으로 변경)
            if co2 is not None:
                if co2 > THRESHOLDS['co2_high']:
                    # 환풍기 ON
                    if previous_state['ventilator'] != 'ON':
                        control_device('ventilator', 'ON', 
                                     f'CO2 level too high: {co2:.0f} ppm')
                        previous_state['ventilator'] = 'ON'
                    
                    # 서보 모터 - 창문 열기 (HTTP 요청)
                    if previous_state['servo'] != 'OPEN':
                        print(f"[CO2] CO2 level high ({co2:.0f} ppm) - Opening window", flush=True)
                        control_device('servo', 'open', f'CO2 level too high: {co2:.0f} ppm')
                        previous_state['servo'] = 'OPEN'
                
                else:
                    # 환풍기 OFF
                    if previous_state['ventilator'] != 'OFF':
                        control_device('ventilator', 'OFF', 
                                     f'CO2 level normal: {co2:.0f} ppm')
                        previous_state['ventilator'] = 'OFF'
                    
                    # 서보 모터 - 창문 닫기 (HTTP 요청)
                    if previous_state['servo'] != 'CLOSE':
                        print(f"[CO2] CO2 level normal ({co2:.0f} ppm) - Closing window", flush=True)
                        control_device('servo', 'close', f'CO2 level normal: {co2:.0f} ppm')
                        previous_state['servo'] = 'CLOSE'
            
            # 3. 습도가 너무 높을 경우
            if humidity is not None and humidity > THRESHOLDS['humidity_high']:
                if previous_state['ventilator'] != 'ON':
                    control_device('ventilator', 'ON',
                                 f'Humidity too high: {humidity:.1f}%')
                    previous_state['ventilator'] = 'ON'
            
            # 4. 움직임 감지 - 조명 제어
            if motion:
                if previous_state['light'] != 'ON':
                    control_device('light', 'ON', 'Motion detected')
                    previous_state['light'] = 'ON'
            else:
                if motion_time:
                    try:
                        last_motion = datetime.fromisoformat(motion_time)
                        time_since_motion = (datetime.now() - last_motion).total_seconds()
                        
                        if time_since_motion > THRESHOLDS['motion_timeout']:
                            if previous_state['light'] != 'OFF':
                                control_device('light', 'OFF',
                                             f'No motion for {time_since_motion:.0f}s')
                                previous_state['light'] = 'OFF'
                    except:
                        pass
            
            # 5. 소음 감지 - 경고 알람
            if noise is not None:
                if noise > THRESHOLDS['noise_high']:
                    if previous_state['alarm'] != 'ON':
                        control_device('alarm', 'ON',
                                     f'Noise level too high: {noise:.0f} dB')
                        previous_state['alarm'] = 'ON'
                else:
                    if previous_state['alarm'] != 'OFF':
                        control_device('alarm', 'OFF',
                                     f'Noise level normal: {noise:.0f} dB')
                        previous_state['alarm'] = 'OFF'
        
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
    
    bmp_thread = threading.Thread(target=bmp180_reading_loop, daemon=True)
    bmp_thread.start()
    print("✓ BMP180 sensor thread started", flush=True)
    
    decision_thread = threading.Thread(target=decision_making_loop, daemon=True)
    decision_thread.start()
    print("✓ Decision making thread started", flush=True)
    
    print("=" * 60, flush=True)
    print("        Server ready on http://0.0.0.0:5000", flush=True)
    print("=" * 60, flush=True)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
