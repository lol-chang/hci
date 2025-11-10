# 구글폼 연동 가이드

## 📋 API가 받는 JSON 형식

```json
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

## 🔗 구글폼 질문 구성

### 필수 질문들:
1. **이름** (단답형)
2. **학번** (단답형)
3. **예산** (단답형, 숫자만)
4. **카테고리 순위 4개** (객관식 또는 드롭다운)
   - 역사·문화 순위 (1, 2, 3, 4 중 선택)
   - 자연·휴양 순위 (1, 2, 3, 4 중 선택)
   - 미식 순위 (1, 2, 3, 4 중 선택)
   - 액티비티 순위 (1, 2, 3, 4 중 선택)
5. **키워드 5개** (단답형)
   - 역사 키워드
   - 자연 키워드
   - 음식 키워드
   - 액티비티 키워드
   - 숙소 키워드

## 🔧 Apps Script 설정

### 1. 구글폼에서 Apps Script 열기
1. 구글폼 편집 화면에서 우측 상단 점 3개 메뉴 클릭
2. **"스크립트 편집기"** 선택
3. 새 창에서 코드 작성

### 2. Apps Script 코드

```javascript
// ====== 설정 ======
const API_URL = 'https://your-server.com/survey/submit';  // ⚠️ 실제 서버 URL로 변경!

// ====== 폼 제출 시 자동 실행 ======
function onFormSubmit(e) {
  try {
    const formUrl = e.source.getEditUrl();
    const itemResponses = e.response.getItemResponses();
    
    // 폼 응답을 JSON으로 변환
    const data = {
      responses: {
        name: getAnswer(itemResponses, "이름"),
        studentID: getAnswer(itemResponses, "학번"),
        rank_category: {
          "역사·문화": getAnswer(itemResponses, "역사·문화 순위"),
          "자연·휴양": getAnswer(itemResponses, "자연·휴양 순위"),
          "미식": getAnswer(itemResponses, "미식 순위"),
          "액티비티": getAnswer(itemResponses, "액티비티 순위")
        },
        keyword_history: getAnswer(itemResponses, "역사 키워드"),
        keyword_nature: getAnswer(itemResponses, "자연 키워드"),
        keyword_food: getAnswer(itemResponses, "음식 키워드"),
        keyword_activity: getAnswer(itemResponses, "액티비티 키워드"),
        keyword_accomodation: getAnswer(itemResponses, "숙소 키워드"),
        budget: getAnswer(itemResponses, "예산")
      },
      timestamp: new Date().toISOString(),
      formUrl: formUrl
    };
    
    // API 서버로 전송
    const options = {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(data),
      muteHttpExceptions: true
    };
    
    const response = UrlFetchApp.fetch(API_URL, options);
    const responseCode = response.getResponseCode();
    const responseText = response.getContentText();
    
    // 로그 기록
    if (responseCode === 200) {
      Logger.log('✅ Success: ' + responseText);
    } else {
      Logger.log('❌ Error ' + responseCode + ': ' + responseText);
    }
    
  } catch (error) {
    Logger.log('❌ Exception: ' + error.toString());
  }
}

// ====== 답변 찾기 헬퍼 함수 ======
function getAnswer(itemResponses, questionTitle) {
  for (var i = 0; i < itemResponses.length; i++) {
    if (itemResponses[i].getItem().getTitle() === questionTitle) {
      return itemResponses[i].getResponse();
    }
  }
  return "";
}

// ====== 테스트 함수 (수동 실행용) ======
function testAPI() {
  const testData = {
    responses: {
      name: "테스트 사용자",
      studentID: "99999999",
      rank_category: {
        "역사·문화": "1",
        "자연·휴양": "2",
        "미식": "3",
        "액티비티": "4"
      },
      keyword_history: "전통",
      keyword_nature: "바다",
      keyword_food: "맛집",
      keyword_activity": "걷기",
      keyword_accomodation: "호텔",
      budget: "300000"
    },
    timestamp: new Date().toISOString(),
    formUrl: "test"
  };
  
  const options = {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(testData),
    muteHttpExceptions: true
  };
  
  const response = UrlFetchApp.fetch(API_URL, options);
  Logger.log('Response Code: ' + response.getResponseCode());
  Logger.log('Response: ' + response.getContentText());
}
```

### 3. 트리거 설정

1. Apps Script 편집기에서 **왼쪽 메뉴의 시계 아이콘(트리거)** 클릭
2. **"+ 트리거 추가"** 클릭
3. 설정:
   - **실행할 함수**: `onFormSubmit`
   - **실행할 배포**: `Head`
   - **이벤트 소스**: `From form`
   - **이벤트 유형**: `On form submit`
4. **저장** 클릭

### 4. 권한 승인

처음 실행 시 권한을 요청합니다:
1. "권한 검토" 클릭
2. 구글 계정 선택
3. "고급" → "안전하지 않은 페이지로 이동" 클릭
4. "허용" 클릭

## 🧪 테스트 방법

### 1. 수동 테스트
1. Apps Script 편집기에서 `testAPI` 함수 선택
2. **실행** 버튼 클릭
3. **실행 로그** 확인

### 2. 실제 폼 제출 테스트
1. 구글폼 작성
2. 제출
3. Apps Script 실행 로그 확인:
   - **실행** 탭에서 최근 실행 내역 확인
4. 서버 로그 확인

## 📝 구글폼 질문 예시

### 이름
```
질문: 이름을 입력해주세요
유형: 단답형
필수: O
```

### 학번
```
질문: 학번을 입력해주세요
유형: 단답형
필수: O
검증: 정규표현식 - 숫자 ([0-9]+)
```

### 예산
```
질문: 여행 예산을 입력해주세요 (원 단위)
유형: 단답형
필수: O
검증: 숫자
설명: 예) 300000
```

### 카테고리 순위
```
질문: 역사·문화 순위
유형: 객관식
필수: O
선택지: 1, 2, 3, 4

질문: 자연·휴양 순위
유형: 객관식
필수: O
선택지: 1, 2, 3, 4

질문: 미식 순위
유형: 객관식
필수: O
선택지: 1, 2, 3, 4

질문: 액티비티 순위
유형: 객관식
필수: O
선택지: 1, 2, 3, 4
```

### 키워드
```
질문: 역사 키워드
유형: 단답형
필수: O
설명: 선호하는 역사/문화 스타일 (예: 전통문화체험)

질문: 자연 키워드
유형: 단답형
필수: O
설명: 선호하는 자연 풍경 (예: 바다전망)

질문: 음식 키워드
유형: 단답형
필수: O
설명: 선호하는 음식 스타일 (예: 가성비가격)

질문: 액티비티 키워드
유형: 단답형
필수: O
설명: 선호하는 활동 (예: 사진명소)

질문: 숙소 키워드
유형: 단답형
필수: O
설명: 선호하는 숙소 스타일 (예: 깔끔한)
```

## 🔍 트러블슈팅

### 문제: API 호출이 안 됨
- **확인사항**:
  1. API_URL이 올바른지 확인
  2. 서버가 실행 중인지 확인
  3. 방화벽 설정 확인

### 문제: 답변이 빈 문자열로 옴
- **확인사항**:
  1. `getAnswer()` 함수의 질문 제목이 폼의 실제 질문 제목과 정확히 일치하는지 확인
  2. 대소문자, 공백, 특수문자 모두 일치해야 함

### 문제: 403 오류
- **해결방법**:
  1. Apps Script 권한 다시 승인
  2. 트리거 삭제 후 재생성

## 📊 모니터링

### Apps Script 로그 확인
```
Apps Script 편집기 → 실행 → 최근 실행 내역
```

### 서버 로그 확인
```bash
# 로컬 개발
터미널에서 실시간 로그 확인

# 프로덕션
sudo journalctl -u travel-api -f
```

## ✅ 체크리스트

- [ ] 구글폼 질문 작성 완료
- [ ] Apps Script 코드 작성
- [ ] API_URL 실제 서버 주소로 변경
- [ ] 트리거 설정 완료
- [ ] 권한 승인 완료
- [ ] 테스트 제출 성공
- [ ] 서버 로그에서 요청 확인
- [ ] 생성된 플랜 파일 확인 (data/plans/u00X.json)

