import requests
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
    bmp_sensor = None
    SENSOR_AVAILABLE = False

# 중앙 서버의 주소
CENTRAL_SERVER_URL = os.getenv('CENTRAL_SERVER_URL', 'http://127.0.0.1:5000')
ENVIRONMENT_ENDPOINT = f"{CENTRAL_SERVER_URL}/sensor/environment"
SEND_INTERVAL = 1  # 10초마다 데이터 전송

def send_sensor_data():
    """센서 데이터를 중앙 서버로 전송"""
    if not SENSOR_AVAILABLE:
        print("[ERROR] Sensor not available, cannot send data.", flush=True)
        return

    try:
        temperature = bmp_sensor.read_temperature()
        pressure = bmp_sensor.read_pressure() / 100.0  # hPa 단위로 변환

        payload = {
            'temperature': temperature,
            'pressure': pressure,
        }

        response = requests.post(ENVIRONMENT_ENDPOINT, json=payload, timeout=5)

        if response.status_code == 200:
            print(f"✓ Sent to server: Temp={temperature:.1f}°C, Pressure={pressure:.1f}hPa", flush=True)
        else:
            print(f"✗ Failed to send data. Status: {response.status_code}, Body: {response.text}", flush=True)

    except Exception as e:
        print(f"[ERROR] An error occurred while sending data: {e}", flush=True)

if __name__ == "__main__":
    if not SENSOR_AVAILABLE:
        print("Exiting: Sensor is not available.", flush=True)
        exit()

    print("=" * 40, flush=True)
    print("      Temperature & Pressure Sensor      ", flush=True)
    print("=" * 40, flush=True)
    print(f"Central Server URL: {CENTRAL_SERVER_URL}", flush=True)
    print(f"Sending data every {SEND_INTERVAL} seconds...", flush=True)
    print("=" * 40, flush=True)

    while True:
        send_sensor_data()
        time.sleep(SEND_INTERVAL)
