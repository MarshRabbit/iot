// 서버 주소
const SERVER_URL = 'http://192.168.0.146:5000';

// 졸음 감지를 위한 변수 (움직임이 없는 시간)
const DROWSY_TIMEOUT = 300; // 5분 (300초)
let lastMotionTime = null;

// 센서 데이터 가져오기
async function fetchSensorData() {
    try {
        const response = await fetch(`${SERVER_URL}/status`);
        const data = await response.json();
        
        // 센서 데이터
        const sensors = data.sensor_data;
        
        // 1. 온도
        if (sensors.temperature !== null) {
            document.getElementById('temperature').textContent = sensors.temperature.toFixed(1);
        } else {
            document.getElementById('temperature').textContent = '--';
        }
        
        // 2. CO2
        const co2Card = document.getElementById('co2-card');
        if (sensors.co2_level !== null) {
            const co2Value = sensors.co2_level.toFixed(0);
            document.getElementById('co2').textContent = co2Value;
            
            // 임계값 초과 시 경고
            if (sensors.co2_level > data.thresholds.co2_high) {
                co2Card.classList.add('alert');
            } else {
                co2Card.classList.remove('alert');
            }
        } else {
            document.getElementById('co2').textContent = '--';
        }
        
        // 3. 소음
        const noiseCard = document.getElementById('noise-card');
        if (sensors.noise_level !== null) {
            const noiseValue = sensors.noise_level.toFixed(1);
            document.getElementById('noise').textContent = noiseValue;
            
            // 임계값 초과 시 경고
            if (sensors.noise_level > data.thresholds.noise_high) {
                noiseCard.classList.add('alert');
            } else {
                noiseCard.classList.remove('alert');
            }
        } else {
            document.getElementById('noise').textContent = '--';
        }
        
        // 4. 졸음 감지 (움직임 기반)
        const drowsyCard = document.getElementById('drowsy-card');
        const drowsyStatus = document.getElementById('drowsy-status');
        const drowsyTime = document.getElementById('drowsy-time');
        
        if (sensors.motion_detected) {
            // 움직임 감지됨
            lastMotionTime = new Date(sensors.motion_timestamp);
            drowsyStatus.textContent = '졸음 감지 안됨';
            drowsyTime.textContent = '활동 중';
            drowsyCard.classList.remove('drowsy', 'alert');
        } else if (sensors.motion_timestamp) {
            // 마지막 움직임으로부터 시간 계산
            lastMotionTime = new Date(sensors.motion_timestamp);
            const now = new Date();
            const timeSinceMotion = Math.floor((now - lastMotionTime) / 1000); // 초 단위
            
            if (timeSinceMotion > DROWSY_TIMEOUT) {
                // 졸음 감지
                drowsyStatus.textContent = '졸음 감지됨';
                const minutes = Math.floor(timeSinceMotion / 60);
                drowsyTime.textContent = `${minutes}분간 움직임 없음`;
                drowsyCard.classList.add('drowsy', 'alert');
            } else {
                // 아직 정상
                drowsyStatus.textContent = '졸음 감지 안됨';
                const remainingTime = DROWSY_TIMEOUT - timeSinceMotion;
                const remainingMinutes = Math.floor(remainingTime / 60);
                drowsyTime.textContent = `${remainingMinutes}분 후 졸음 감지`;
                drowsyCard.classList.remove('drowsy', 'alert');
            }
        } else {
            // 데이터 없음
            drowsyStatus.textContent = '대기 중';
            drowsyTime.textContent = '-';
            drowsyCard.classList.remove('drowsy', 'alert');
        }
        
        // 제어 로그에서 액추에이터 상태 확인
        updateActuatorStatus();
        
        // 마지막 업데이트 시간
        document.getElementById('last-update').textContent = 
            '마지막 업데이트: ' + new Date().toLocaleTimeString('ko-KR');
        
        // 서버 연결 정상
        document.getElementById('server-status').style.color = '#4CAF50';
        
    } catch (error) {
        console.error('데이터 가져오기 실패:', error);
        document.getElementById('server-status').style.color = '#ff4444';
    }
}

// 액추에이터 상태 업데이트
async function updateActuatorStatus() {
    try {
        const response = await fetch(`${SERVER_URL}/logs/control?limit=20`);
        const data = await response.json();
        
        // 에어컨과 히터의 최신 상태 찾기
        let acStatus = 'OFF';
        let heaterStatus = 'OFF';
        
        if (data.logs && data.logs.length > 0) {
            // 최근 로그에서 각 장치의 최신 상태 찾기
            for (let log of data.logs) {
                const device = log[2]; // device
                const action = log[3]; // action
                
                if (device === 'airconditioner' && acStatus === 'OFF') {
                    acStatus = action;
                }
                if (device === 'heater' && heaterStatus === 'OFF') {
                    heaterStatus = action;
                }
                
                // 둘 다 찾았으면 중단
                if (acStatus !== 'OFF' && heaterStatus !== 'OFF') {
                    break;
                }
            }
        }
        
        // 5. 에어컨 상태
        const acCard = document.getElementById('ac-card');
        const acStatusElement = document.getElementById('ac-status');
        acStatusElement.textContent = acStatus;
        
        if (acStatus === 'ON') {
            acCard.classList.add('on');
        } else {
            acCard.classList.remove('on');
        }
        
        // 6. 히터 상태
        const heaterCard = document.getElementById('heater-card');
        const heaterStatusElement = document.getElementById('heater-status');
        heaterStatusElement.textContent = heaterStatus;
        
        if (heaterStatus === 'ON') {
            heaterCard.classList.add('on');
        } else {
            heaterCard.classList.remove('on');
        }
        
    } catch (error) {
        console.error('액추에이터 상태 가져오기 실패:', error);
    }
}

// 초기화
document.addEventListener('DOMContentLoaded', () => {
    fetchSensorData();
    
    // 2초마다 센서 데이터 업데이트
    setInterval(fetchSensorData, 2000);
});
