# GCP 배포 가이드

## 📋 사전 준비

1. GCP VM 인스턴스 생성 (Ubuntu 20.04 이상 권장)
2. 외부 IP 할당 받기
3. SSH 접속 설정

---

## 🔧 1. GCP VM 방화벽 규칙 추가

### 방법 1: GCP 콘솔에서 설정 (권장)

```
1. GCP Console 접속
   ↓
2. VPC Network → Firewall Rules
   ↓
3. "CREATE FIREWALL RULE" 클릭
   ↓
4. 설정:
   - Name: allow-fastapi-8000
   - Direction: Ingress
   - Targets: All instances in the network
   - Source IP ranges: 0.0.0.0/0
   - Protocols and ports: tcp:8000
   ↓
5. "CREATE" 클릭
```

### 방법 2: gcloud 명령어로 설정

```bash
gcloud compute firewall-rules create allow-fastapi-8000 \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:8000 \
    --source-ranges=0.0.0.0/0
```

---

## 📦 2. 서버 환경 설정

### 1) 필수 패키지 설치

```bash
# Python 3.10+ 설치 확인
python3 --version

# pip 업그레이드
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv

# Git 설치
sudo apt-get install -y git
```

### 2) 프로젝트 업로드

```bash
# 방법 1: Git clone
cd ~
git clone YOUR_REPOSITORY_URL backend
cd backend

# 방법 2: 파일 직접 업로드
# - FileZilla, SCP, rsync 등 사용
```

### 3) 가상환경 생성 및 패키지 설치

```bash
cd ~/backend

# 가상환경 생성
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 4) 환경변수 설정 (필요 시)

```bash
# .env 파일이 있다면 확인
nano .env

# Weaviate, OpenAI 등의 API 키 설정
# WEAVIATE_URL=http://localhost:8080
# OPENAI_API_KEY=sk-...
```

---

## 🚀 3. 서버 실행

### 방법 1: Systemd 서비스로 자동 실행 (권장)

#### 서비스 파일 생성

```bash
sudo nano /etc/systemd/system/travel-api.service
```

#### 아래 내용 붙여넣기

```ini
[Unit]
Description=Travel Plan API
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/backend
Environment="PATH=/home/YOUR_USERNAME/backend/venv/bin"
ExecStart=/home/YOUR_USERNAME/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**⚠️ 주의: `YOUR_USERNAME`을 실제 사용자명으로 변경!**

```bash
# 현재 사용자명 확인
whoami
```

#### 서비스 활성화 및 시작

```bash
# 서비스 파일 다시 읽기
sudo systemctl daemon-reload

# 서비스 시작
sudo systemctl start travel-api

# 부팅 시 자동 시작 설정
sudo systemctl enable travel-api

# 상태 확인
sudo systemctl status travel-api

# 로그 확인
sudo journalctl -u travel-api -f
```

#### 서비스 관리 명령어

```bash
# 재시작
sudo systemctl restart travel-api

# 중지
sudo systemctl stop travel-api

# 자동 시작 해제
sudo systemctl disable travel-api
```

---

### 방법 2: Screen으로 백그라운드 실행 (간단)

```bash
# Screen 설치
sudo apt-get install -y screen

# Screen 세션 시작
screen -S travel-api

# 가상환경 활성화 & 서버 실행
cd ~/backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000

# Ctrl+A, D 로 세션에서 빠져나오기 (서버는 백그라운드에서 계속 실행)

# Screen 세션 다시 접속
screen -r travel-api

# Screen 세션 종료
screen -X -S travel-api quit
```

---

## ✅ 4. 동작 확인

### 1) 서버 내부에서 테스트

```bash
# API 상태 확인
curl http://localhost:8000/

# Swagger 문서 확인 (브라우저에서)
# http://YOUR_EXTERNAL_IP:8000/docs
```

### 2) 외부에서 접속 테스트

```bash
# 로컬 PC에서
curl http://YOUR_EXTERNAL_IP:8000/

# 또는 브라우저에서
# http://YOUR_EXTERNAL_IP:8000/
```

### 3) 설문 제출 테스트

```bash
curl -X POST http://YOUR_EXTERNAL_IP:8000/survey/submit \
  -H "Content-Type: application/json" \
  -d '{
    "responses": {
      "name": "테스트",
      "studentID": "99999999",
      "rank_category": ["역사", "자연", "음식"],
      "keyword_history": ["궁궐", "박물관"],
      "keyword_nature": ["산", "바다"],
      "keyword_food": ["한식", "디저트"],
      "keyword_activity": ["카페", "전시"],
      "keyword_accomodation": ["호텔", "깨끗한"],
      "budget": 500000
    },
    "timestamp": "2025-11-10T12:00:00Z",
    "formUrl": "test"
  }'
```

---

## 🔍 5. 트러블슈팅

### 문제 1: 외부 접속 안 됨

```bash
# 방화벽 규칙 확인
gcloud compute firewall-rules list | grep 8000

# UFW 방화벽 확인 (Ubuntu)
sudo ufw status
sudo ufw allow 8000/tcp

# 서버 실행 확인
sudo netstat -nltp | grep 8000
```

### 문제 2: 서비스 시작 실패

```bash
# 로그 확인
sudo journalctl -u travel-api -n 50 --no-pager

# 수동으로 실행해보기 (에러 확인)
cd ~/backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 문제 3: 의존성 오류

```bash
# 가상환경에서 재설치
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### 문제 4: CORS 에러

- `main.py`에서 CORS 설정 확인
- `allow_origins=["*"]`로 설정되어 있는지 확인

---

## 🌐 6. 구글폼 연결

### Apps Script URL 설정

```javascript
// GCP VM의 외부 IP 주소로 변경
const API_URL = 'http://YOUR_EXTERNAL_IP:8000/survey/submit';
```

**예시:**
```javascript
const API_URL = 'http://34.64.123.456:8000/survey/submit';
```

---

## 📝 7. 보안 강화 (선택사항)

### HTTPS 설정 (Let's Encrypt)

```bash
# Nginx 설치
sudo apt-get install -y nginx certbot python3-certbot-nginx

# 도메인 연결 후 SSL 인증서 발급
sudo certbot --nginx -d yourdomain.com

# Nginx 프록시 설정
sudo nano /etc/nginx/sites-available/default
```

Nginx 설정 예시:
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📊 8. 모니터링

### 로그 확인

```bash
# 실시간 로그 보기
sudo journalctl -u travel-api -f

# 최근 100줄 보기
sudo journalctl -u travel-api -n 100

# 에러만 보기
sudo journalctl -u travel-api -p err
```

### 디스크 사용량 확인

```bash
# 전체 디스크 사용량
df -h

# 프로젝트 디렉토리 크기
du -sh ~/backend/*
```

---

## 🔄 9. 코드 업데이트

```bash
# 서비스 중지
sudo systemctl stop travel-api

# 코드 업데이트 (git 사용 시)
cd ~/backend
git pull

# 의존성 업데이트 (필요 시)
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 서비스 재시작
sudo systemctl start travel-api

# 상태 확인
sudo systemctl status travel-api
```

---

## 📌 Quick Reference

### 주요 URL
- **API 루트**: `http://YOUR_EXTERNAL_IP:8000/`
- **Swagger 문서**: `http://YOUR_EXTERNAL_IP:8000/docs`
- **설문 제출 엔드포인트**: `http://YOUR_EXTERNAL_IP:8000/survey/submit`
- **플랜 조회**: `http://YOUR_EXTERNAL_IP:8000/plans?student_id=202110862`

### 주요 명령어
```bash
# 서비스 상태
sudo systemctl status travel-api

# 서비스 재시작
sudo systemctl restart travel-api

# 로그 확인
sudo journalctl -u travel-api -f

# 포트 확인
sudo netstat -nltp | grep 8000
```

---

## ✅ 체크리스트

- [ ] GCP VM 인스턴스 생성
- [ ] 외부 IP 할당
- [ ] 방화벽 규칙 추가 (8000번 포트)
- [ ] Python 3.10+ 설치
- [ ] 프로젝트 파일 업로드
- [ ] 가상환경 생성 및 패키지 설치
- [ ] `.env` 파일 설정 (필요 시)
- [ ] Systemd 서비스 파일 생성
- [ ] 서비스 시작 및 자동 시작 설정
- [ ] 외부 접속 테스트
- [ ] 구글폼 Apps Script URL 업데이트
- [ ] 설문 제출 테스트

완료! 🎉

