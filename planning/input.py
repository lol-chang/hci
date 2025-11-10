import os
import json
import csv
from dotenv import load_dotenv
from openai import OpenAI

# ----------------------------------------
# OpenAI 설정 (.env에서 키 불러오기)
# ----------------------------------------
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ----------------------------------------
# 경로 설정
# ----------------------------------------
BASE_DIR = "planning"
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
USER_TEMPLATE_DIR = os.path.join(BASE_DIR, "user_templates")
USER_INFO_DIR = os.path.join(BASE_DIR, "user_info")
os.makedirs(USER_TEMPLATE_DIR, exist_ok=True)
os.makedirs(USER_INFO_DIR, exist_ok=True)

# 설문 JSON 파일 경로
survey_file = os.path.join(BASE_DIR, "input.json")

# ----------------------------------------
# 템플릿 매핑
# ----------------------------------------
STYLE_MAP = {
    "역사·문화": "Cultural_template.json",
    "자연·휴양": "Healing_template.json",
    "미식": "Foodie_template.json",
    "액티비티": "Activity_template.json"
}

# 여행 스타일 영어 매핑
STYLE_ENGLISH = {
    "역사·문화": "Cultural",
    "자연·휴양": "Healing",
    "미식": "Foodie",
    "액티비티": "Activity"
}

# ----------------------------------------
# GPT 기반 키워드 번역 함수
# ----------------------------------------
def translate_keywords_to_english(keywords):
    """GPT를 이용해 한글 키워드를 영어로 3단어 이하로 번역 (번호 없이)"""
    if not keywords:
        return []

    prompt = (
        "다음 한글 여행 키워드들을 각각 영어로 자연스럽고 짧게 번역해 주세요. "
        "각 항목은 3단어 이하로 표현하고, 번호(1., -, • 등) 없이 쉼표(,)로 구분해 한 줄로 출력하세요.\n\n"
        f"입력 키워드: {keywords}\n"
        "출력 예시: Traditional culture experience, Sea view, Cost-effective price, Photo spot, Neat"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You translate Korean travel keywords into short English phrases without numbering."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()

        # 쉼표 기준 분리
        return [x.strip() for x in result.split(",") if x.strip()]
    except Exception as e:
        print(f"[WARNING] GPT 번역 오류: {e}")
        return keywords


# ----------------------------------------
# 1️⃣ 설문 결과 읽기
# ----------------------------------------
with open(survey_file, "r", encoding="utf-8") as f:
    survey_data = json.load(f)

responses = survey_data["responses"]
name = responses["name"]
student_id = responses["studentID"]
budget_total = int(responses.get("budget", 0))
budget_per_day = budget_total // 2  # ✅ 하루 예산 계산

# ----------------------------------------
# 2️⃣ 여행 스타일 결정
# ----------------------------------------
rank_category = responses["rank_category"]
best_style = min(rank_category, key=lambda k: int(rank_category[k]))
template_file = STYLE_MAP.get(best_style)
english_style = STYLE_ENGLISH.get(best_style, "Unknown")

if not template_file:
    raise ValueError(f"[ERROR] 알 수 없는 스타일: {best_style}")

template_path = os.path.join(TEMPLATE_DIR, template_file)

# ----------------------------------------
# 3️⃣ 템플릿 불러오기 + 예산 반영
# ----------------------------------------
with open(template_path, "r", encoding="utf-8") as f:
    template_data = json.load(f)

template_data["budget_per_day"] = budget_per_day

# ----------------------------------------
# 4️⃣ 유저 템플릿 저장 (학번 기반)
# ----------------------------------------
user_template_path = os.path.join(USER_TEMPLATE_DIR, f"{student_id}_template.json")
with open(user_template_path, "w", encoding="utf-8") as f:
    json.dump(template_data, f, ensure_ascii=False, indent=2)

print(f"[OK] {name}님의 여행 스타일: {english_style}")
print(f"[예산] 총 예산: {budget_total:,}원 -> 1일 예산: {budget_per_day:,}원")
print(f"[템플릿] 생성 완료: {user_template_path}")

# ----------------------------------------
# 5️⃣ CSV 저장 (user_info)
# ----------------------------------------
csv_file_path = os.path.join(USER_INFO_DIR, f"{student_id}_user_info.csv")

# like_keywords 자동 구성 및 번역
raw_keywords = [
    responses.get("keyword_history", ""),
    responses.get("keyword_nature", ""),
    responses.get("keyword_food", ""),
    responses.get("keyword_activity", ""),
    responses.get("keyword_accomodation", "")
]
raw_keywords = [kw for kw in raw_keywords if kw]
translated_keywords = translate_keywords_to_english(raw_keywords)

# CSV 행 구성
csv_row = {
    "user_id": "U0001",  # 고정 또는 자동 생성 가능
    "name": name,
    "student_id": student_id,
    "rotate": "['hybrid', 'popularity', 'personalized']",
    "travel_style": english_style,
    "budget": budget_total,  # ✅ 총 예산 저장
    "duration_days": 2,
    "like_keywords": str(translated_keywords),
    "dislike_keywords": "[]"
}

# CSV 저장
with open(csv_file_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=csv_row.keys())
    writer.writeheader()
    writer.writerow(csv_row)

print(f"[CSV] 저장 완료 -> {csv_file_path}")
print(f"[키워드] 번역 완료: {translated_keywords}")
