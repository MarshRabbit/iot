#!/usr/bin/env python3
import time
import sys

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except:
    print("Warning: RPi.GPIO not available - running in simulation mode")
    GPIO_AVAILABLE = False

SERVO_PIN = 18

class ServoController:
    def __init__(self, pin=SERVO_PIN):
        self.pin = pin
        self.pwm = None
        self.setup()
    
    def setup(self):
        """서보 모터 초기화"""
        if not GPIO_AVAILABLE:
            print("[SERVO] Running in simulation mode")
            return
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        self.pwm = GPIO.PWM(self.pin, 50)  # 50Hz
        self.pwm.start(0)
        print("[SERVO] Initialized")
    
    def set_angle(self, angle):
        """서보 각도 설정 (0-180도)"""
        if not GPIO_AVAILABLE:
            print(f"[SERVO SIMULATION] Setting angle to {angle}°")
            return True
        
        try:
            duty = 2 + (angle / 18)
            GPIO.output(self.pin, True)
            self.pwm.ChangeDutyCycle(duty)
            time.sleep(1)
            GPIO.output(self.pin, False)
            self.pwm.ChangeDutyCycle(0)
            return True
        except Exception as e:
            print(f"[SERVO ERROR] {e}")
            return False
    
    def open_window(self):
        """창문 열기"""
        print("[SERVO] Opening window...")
        result = self.set_angle(0)  # 0도
        if result:
            print("[SERVO] Window opened")
        return result
    
    def close_window(self):
        """창문 닫기"""
        print("[SERVO] Closing window...")
        result = self.set_angle(90)  # 90도
        if result:
            print("[SERVO] Window closed")
        return result
    
    def cleanup(self):
        """정리"""
        if self.pwm:
            self.pwm.stop()
        if GPIO_AVAILABLE:
            GPIO.cleanup()

# 명령줄에서 실행할 때
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pwm_servo.py [open|close|angle]")
        sys.exit(1)
    
    action = sys.argv[1].lower()
    servo = ServoController()
    
    try:
        if action == "open":
            servo.open_window()
        elif action == "close":
            servo.close_window()
        elif action.isdigit():
            angle = int(action)
            servo.set_angle(angle)
        else:
            print(f"Unknown action: {action}")
            sys.exit(1)
        
        print("Success!")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        servo.cleanup()
