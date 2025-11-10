# 📁 프로젝트 구조

## 핵심 파일 구조

```
backend/
├── main.py                          # FastAPI 메인 서버
├── requirements.txt                 # Python 패키지 의존성
├── .env                            # 환경 변수 (OpenAI, Weaviate API 키)
├── .env.example                    # 환경 변수 예시
│
├── routers/                        # API 라우터
│   ├── survey.py                   # 설문 제출 & 파이프라인 실행
│   └── plans.py                    # 여행 플랜 조회
│
├── planning/                       # 여행 플랜 생성 로직
│   ├── input.py                    # STEP 1: 사용자 정보 처리 & 템플릿 생성
│   ├── softmax.py                  # STEP 2: Weaviate 벡터 검색 & 장소 추천
│   ├── clustering.py               # STEP 3: 공간 클러스터링
│   ├── run_pipeline.py             # 전체 파이프라인 통합 (레거시)
│   ├── process_single_student.py   # 단일 학번 처리 (실제 사용)
│   │
│   ├── input.json                  # 구글폼 응답 임시 저장
│   │
│   ├── user_templates/             # 사용자별 템플릿
│   │   └── {student_id}_template.json
│   │
│   ├── user_info/                  # 사용자 정보 CSV
│   │   └── {student_id}_user_info.csv
│   │
│   ├── softmax_result_test/        # Weaviate 추천 결과
│   │   └── {student_id}_recommendations_softmax.json
│   │
│   ├── clustering_result_test/     # 클러스터링 결과
│   │   └── {student_id}_daily_clusters.json
│   │
│   ├── pure_preference_only/       # 개인화 플랜용 선호도 점수
│   │   └── {student_id}_recommendations_preference.json
│   │
│   └── data_set/                   # 기본 데이터셋
│       ├── accommodations_fixed.csv
│       ├── cafe_fixed.csv
│       ├── restaurants_fixed.csv
│       ├── attractions_fixed.csv
│       └── clustering_category_combine_with_hours_and_price.csv
│
├── greedy/                         # Greedy 알고리즘 (레거시)
│   ├── sorting_review_dataset/     # 리뷰 정렬 데이터
│   └── user_like_score.py          # 선호도 점수 계산
│
├── data/                           # 최종 결과 데이터
│   ├── users.csv                   # 등록된 사용자 목록
│   └── plans/                      # 생성된 여행 플랜
│       └── u{XXX}.json             # 사용자별 최종 플랜 (3가지)
│
└── docs/                           # 문서
    ├── DEPLOYMENT.md               # 배포 가이드
    ├── GOOGLE_FORM_SETUP.md        # 구글폼 연동 가이드
    └── PROJECT_STRUCTURE.md        # 이 파일
```

## 🔄 데이터 흐름

```
구글폼 제출
    ↓
POST /survey/submit
    ├─ input.json 생성
    ├─ users.csv 등록
    └─ 백그라운드: process_single_student.py
         ↓
       STEP 1: input.py
         → user_templates/{student_id}_template.json
         → user_info/{student_id}_user_info.csv
         ↓
       STEP 2: softmax.py {student_id}
         → softmax_result_test/{student_id}_recommendations_softmax.json
         ↓
       STEP 3: clustering.py {student_id}
         → clustering_result_test/{student_id}_daily_clusters.json
         ↓
       STEP 4: 3가지 플랜 생성
         → pure_preference_only/{student_id}_recommendations_preference.json
         → data/plans/u{XXX}.json ✅
```

## 📦 주요 의존성

```
fastapi           # 웹 프레임워크
uvicorn           # ASGI 서버
pandas            # 데이터 처리
scikit-learn      # 클러스터링 (BallTree)
sentence-transformers  # 텍스트 임베딩
weaviate-client   # 벡터 데이터베이스
python-dotenv     # 환경 변수
openai            # GPT API (키워드 번역)
```

## 🚀 실행 방법

### 로컬 개발
```bash
# 서버 실행
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# API 문서
http://localhost:8000/docs
```

### 프로덕션 배포
```bash
# requirements 설치
pip install -r requirements.txt

# .env 설정
cp .env.example .env
# (OpenAI, Weaviate API 키 입력)

# 서버 실행
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 📊 최종 출력 형식

### data/plans/u{XXX}.json
```json
{
  "studentId": "20251234",
  "plan_order": ["hybrid", "popularity", "personalized"],
  "plans": {
    "popularity": {
      "label": "인기도",
      "days": {
        "day1": [...],
        "day2": [...]
      }
    },
    "personalized": {
      "label": "개인화",
      "days": {
        "day1": [...],
        "day2": [...]
      }
    },
    "hybrid": {
      "label": "인기도 + 개인화",
      "days": {
        "day1": [...],
        "day2": [...]
      }
    }
  }
}
```

## 🔑 환경 변수

필수 환경 변수 (`.env`):
```
OPENAI_API_KEY=sk-...
WEAVIATE_API_KEY=...
WEAVIATE_CLUSTER_URL=https://...
```

## 📝 API 엔드포인트

### 설문 제출
```
POST /survey/submit
Body: SurveyInput (구글폼 응답)
Response: { user_id, student_id, status, plan_order }
```

### 상태 확인
```
GET /survey/status/{student_id}
Response: { status: "processing" | "completed", user_id }
```

### 플랜 조회
```
POST /plans/by-student
Body: { student_id: "20251234" }
Response: 전체 플랜 JSON
```

## 🎯 주요 기능

1. **3가지 플랜 생성**
   - Popularity: 리뷰 수 기반
   - Personalized: 개인 선호도 기반
   - Hybrid: 예산 + 클러스터링 (일일 75,000원)

2. **공간 클러스터링**
   - BallTree + Haversine 거리
   - 6km 반경 내 그룹화

3. **예산 관리**
   - 총 예산 50%: 숙소
   - 나머지 50%: 음식/카페 (일일 75,000원)

4. **백그라운드 처리**
   - 약 20-25초 소요
   - FastAPI BackgroundTasks 사용

## 🛠️ 개발 도구

- Python 3.11+
- FastAPI + Uvicorn
- Weaviate Cloud
- OpenAI API


