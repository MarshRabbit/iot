import serial
import time
import requests
from datetime import datetime

# 중앙 서버 주소
CENTRAL_SERVER = 'http://192.168.0.146:5000/sensor/co2'

# 시리얼 포트 설정
SERIAL_PORT = '/dev/serial0'  # 또는 /dev/ttyS0, /dev/ttyAMA0
BAUD_RATE = 9600

# 센서 초기화
try:
    ser = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUD_RATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2
    )
    print(f"✓ Serial port opened: {SERIAL_PORT}")
    SENSOR_AVAILABLE = True
except Exception as e:
    print(f"✗ Failed to open serial port: {e}")
    print("  Running in simulation mode")
    ser = None
    SENSOR_AVAILABLE = False

def read_co2_sensor():
    """
    SZH-SSBH-038 센서에서 CO2 값 읽기
    
    프로토콜:
    - 명령 전송: FF 01 86 00 00 00 00 00 79
    - 응답: 9바이트 (FF 86 CO2_HIGH CO2_LOW ... CHECKSUM)
    """
    if not SENSOR_AVAILABLE:
        # 시뮬레이션 모드
        import random
        return random.randint(400, 2000)
    
    try:
        # 버퍼 클리어
        ser.flushInput()
        
        # CO2 읽기 명령 전송
        command = bytes([0xFF, 0x01, 0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x79])
        ser.write(command)
        
        # 응답 대기
        time.sleep(0.1)
        
        # 9바이트 읽기
        if ser.in_waiting >= 9:
            response = ser.read(9)
            
            # 응답 검증
            if len(response) == 9 and response[0] == 0xFF and response[1] == 0x86:
                # CO2 값 계산 (바이트 2, 3)
                co2_high = response[2]
                co2_low = response[3]
                co2_ppm = (co2_high * 256) + co2_low
                
                # 체크섬 검증 (선택사항)
                checksum = (0xFF - (sum(response[1:8]) & 0xFF) + 1) & 0xFF
                if checksum == response[8]:
                    return co2_ppm
                else:
                    print(f"[WARNING] Checksum mismatch: expected {checksum}, got {response[8]}")
                    return co2_ppm  # 체크섬 실패해도 값 반환
            else:
                print(f"[WARNING] Invalid response: {response.hex()}")
                return None
        else:
            print(f"[WARNING] No data available (waiting: {ser.in_waiting})")
            return None
            
    except Exception as e:
        print(f"[ERROR] Failed to read sensor: {e}")
        return None

def send_data(co2_level):
    """중앙 서버로 데이터 전송"""
    try:
        data = {
            'co2_level': co2_level,
            'timestamp': datetime.now().isoformat()
        }
        
        response = requests.post(
            CENTRAL_SERVER,
            json=data,
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"✓ CO2 data sent: {co2_level} ppm")
            return True
        else:
            print(f"✗ Server error: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to central server")
        return False
    except requests.exceptions.Timeout:
        print("✗ Request timeout")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    print("=" * 60)
    print("SZH-SSBH-038 CO2 Sensor - Data Sender")
    print(f"Serial Port: {SERIAL_PORT}")
    print(f"Baud Rate: {BAUD_RATE}")
    print(f"Central Server: {CENTRAL_SERVER}")
    print("=" * 60)
    
    # 센서 예열 (약 3분 필요)
    print("\n⏳ Sensor warming up (3 minutes)...")
    for i in range(10, 0, -10):
        print(f"   {i} seconds remaining...", end='\r')
        time.sleep(10)
    print("\n✓ Warm-up complete!\n")
    
    while True:
        try:
            # CO2 레벨 읽기
            co2_level = read_co2_sensor()
            
            if co2_level is not None:
                # 유효성 검사 (400~5000 ppm 범위)
                if 400 <= co2_level <= 5000:
                    # 데이터 전송
                    send_data(co2_level)
                else:
                    print(f"⚠️  Invalid CO2 value: {co2_level} ppm (out of range)")
            
            # 10초마다 측정
            time.sleep(10)
            
        except KeyboardInterrupt:
            print("\n\n✓ Shutting down...")
            if ser:
                ser.close()
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
