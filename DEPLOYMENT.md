# 🚀 여행 추천 시스템 배포 가이드

## 📋 사전 준비

### 1. 필수 환경 변수
`.env` 파일 생성 (`.env.example` 참고):
```bash
OPENAI_API_KEY=your_openai_api_key_here
WEAVIATE_API_KEY=your_weaviate_api_key_here
WEAVIATE_CLUSTER_URL=https://your-cluster.weaviate.network
```

### 2. Python 패키지 설치
```bash
pip install -r requirements.txt
```

## 🖥️ 로컬 실행

### 서버 시작
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### API 문서 확인
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📡 API 엔드포인트

### 1. 설문 제출 (구글폼 연동)
```http
POST /survey/submit
Content-Type: application/json

{
  "responses": {
    "name": "홍길동",
    "studentID": "20251234",
    "rank_category": {
      "역사·문화": "2",
      "자연·휴양": "4",
      "미식": "3",
      "액티비티": "1"
    },
    "keyword_history": "전통문화체험",
    "keyword_nature": "바다전망",
    "keyword_food": "가성비가격",
    "keyword_activity": "사진명소",
    "keyword_accomodation": "깔끔한",
    "budget": "300000"
  },
  "timestamp": "2025-11-10T10:00:00Z",
  "formUrl": "https://docs.google.com/forms/d/..."
}
```

**응답:**
```json
{
  "status": "processing",
  "message": "설문이 제출되었습니다. 여행 플랜을 생성 중입니다.",
  "user_id": "u003",
  "student_id": "20251234",
  "name": "홍길동",
  "plan_order": ["hybrid", "popularity", "personalized"],
  "estimated_time": "약 20-30초 소요됩니다."
}
```

### 2. 생성 상태 확인
```http
GET /survey/status/{student_id}
```

**응답 (처리 중):**
```json
{
  "status": "processing",
  "message": "플랜을 생성 중입니다. 잠시만 기다려주세요.",
  "user_id": "u003",
  "student_id": "20251234"
}
```

**응답 (완료):**
```json
{
  "status": "completed",
  "message": "플랜 생성이 완료되었습니다.",
  "user_id": "u003",
  "student_id": "20251234"
}
```

### 3. 여행 플랜 조회
```http
POST /plans/by-student
Content-Type: application/json

{
  "student_id": "20251234"
}
```

## ☁️ 클라우드 배포

### AWS EC2 배포

#### 1. EC2 인스턴스 생성
- **인스턴스 타입**: t3.medium 이상 (2 vCPU, 4GB RAM)
- **OS**: Ubuntu 22.04 LTS
- **보안 그룹**: 
  - 포트 22 (SSH)
  - 포트 8000 (HTTP)
  - 포트 443 (HTTPS, 옵션)

#### 2. 서버 설정
```bash
# 1. 서버 접속
ssh -i your-key.pem ubuntu@your-ec2-ip

# 2. Python 설치
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip git -y

# 3. 프로젝트 클론
git clone https://github.com/your-repo/travel-planner.git
cd travel-planner

# 4. 가상환경 생성
python3.11 -m venv venv
source venv/bin/activate

# 5. 패키지 설치
pip install -r requirements.txt

# 6. 환경 변수 설정
nano .env
# (OpenAI, Weaviate API 키 입력)

# 7. 데이터 디렉토리 생성
mkdir -p data/plans
mkdir -p planning/user_templates
mkdir -p planning/user_info
mkdir -p planning/clustering_result_test
mkdir -p planning/softmax_result_test
mkdir -p planning/pure_preference_only
```

#### 3. Systemd 서비스 등록 (백그라운드 실행)
```bash
sudo nano /etc/systemd/system/travel-api.service
```

```ini
[Unit]
Description=Travel Planner API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/travel-planner
Environment="PATH=/home/ubuntu/travel-planner/venv/bin"
ExecStart=/home/ubuntu/travel-planner/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 시작
sudo systemctl daemon-reload
sudo systemctl enable travel-api
sudo systemctl start travel-api

# 상태 확인
sudo systemctl status travel-api

# 로그 확인
sudo journalctl -u travel-api -f
```

#### 4. Nginx 리버스 프록시 (옵션)
```bash
# Nginx 설치
sudo apt install nginx -y

# 설정 파일
sudo nano /etc/nginx/sites-available/travel-api
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 지원 (옵션)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

```bash
# Nginx 활성화
sudo ln -s /etc/nginx/sites-available/travel-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Google Cloud Platform (GCP) 배포

#### Cloud Run 배포

**1. Dockerfile 생성**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**2. 배포 명령**
```bash
# Cloud Build & Deploy
gcloud run deploy travel-api \
  --source . \
  --platform managed \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --memory 2Gi \
  --timeout 300 \
  --set-env-vars OPENAI_API_KEY=xxx,WEAVIATE_API_KEY=xxx,WEAVIATE_CLUSTER_URL=xxx
```

## 🔗 구글폼 연동

### Apps Script 설정

1. 구글폼에서 **Apps Script** 열기
2. 다음 코드 추가:

```javascript
function onFormSubmit(e) {
  const formUrl = e.source.getEditUrl();
  const responses = e.response.getItemResponses();
  
  const data = {
    responses: {
      name: getAnswer(responses, "이름"),
      studentID: getAnswer(responses, "학번"),
      rank_category: {
        "역사·문화": getAnswer(responses, "역사·문화 순위"),
        "자연·휴양": getAnswer(responses, "자연·휴양 순위"),
        "미식": getAnswer(responses, "미식 순위"),
        "액티비티": getAnswer(responses, "액티비티 순위")
      },
      keyword_history: getAnswer(responses, "역사 키워드"),
      keyword_nature: getAnswer(responses, "자연 키워드"),
      keyword_food: getAnswer(responses, "음식 키워드"),
      keyword_activity: getAnswer(responses, "액티비티 키워드"),
      keyword_accomodation: getAnswer(responses, "숙소 키워드"),
      budget: getAnswer(responses, "예산")
    },
    timestamp: new Date().toISOString(),
    formUrl: formUrl
  };
  
  const options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(data),
    muteHttpExceptions: true
  };
  
  // API 서버 URL
  const apiUrl = 'https://your-server.com/survey/submit';
  const response = UrlFetchApp.fetch(apiUrl, options);
  
  Logger.log('Response: ' + response.getContentText());
}

function getAnswer(responses, questionTitle) {
  for (var i = 0; i < responses.length; i++) {
    if (responses[i].getItem().getTitle() === questionTitle) {
      return responses[i].getResponse();
    }
  }
  return "";
}
```

3. **트리거 설정**: `onFormSubmit` → 폼 제출 시 실행

## 📊 모니터링

### 로그 확인
```bash
# Systemd 로그
sudo journalctl -u travel-api -f

# 파일 로그 (옵션)
tail -f /var/log/travel-api/app.log
```

### 상태 확인 API
```bash
# Health Check
curl http://localhost:8000/

# 생성된 플랜 수 확인
wc -l data/users.csv
ls -l data/plans/
```

## 🔒 보안 권장사항

1. **.env 파일 보호**
   ```bash
   chmod 600 .env
   ```

2. **API 키 관리**: AWS Secrets Manager 또는 GCP Secret Manager 사용

3. **HTTPS 설정**: Let's Encrypt 인증서 사용
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

4. **방화벽 설정**
   ```bash
   sudo ufw allow 22
   sudo ufw allow 80
   sudo ufw allow 443
   sudo ufw enable
   ```

## 🐛 트러블슈팅

### 파이프라인 타임아웃
- `routers/survey.py`의 `timeout=300` 값 증가

### 메모리 부족
- EC2 인스턴스 크기 증가
- 또는 Swap 파일 설정

### Weaviate 연결 오류
- `.env` 파일의 `WEAVIATE_CLUSTER_URL` 확인
- API 키 유효성 확인

## 📞 지원

문제 발생 시:
1. 로그 확인: `sudo journalctl -u travel-api -f`
2. API 문서: http://your-server:8000/docs
3. 상태 확인: `systemctl status travel-api`

