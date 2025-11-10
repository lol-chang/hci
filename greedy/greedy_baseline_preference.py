import json
import pandas as pd
from pathlib import Path
import time

# -----------------------------
# 경로 설정
# -----------------------------
BASE_DIR = Path(r"C:\Users\changjin\workspace\lab\pln")

TEMPLATE_DIR = BASE_DIR / "evaluation" / "100_plan_template"
PREF_DIR = BASE_DIR / "evaluation" / "100_place_preference"
OUTPUT_PATH = BASE_DIR / "evaluation" / "100_generated_plan" / "preference_summary.json"

# -----------------------------
# 선호도 데이터 로드
# -----------------------------
def load_preference_json(path):
    with open(path, "r", encoding="utf-8") as f:
        pref_data = json.load(f)

    # 각 카테고리별 preference_score 기준 내림차순 정렬
    sorted_pref = {}
    for cat, items in pref_data.items():
        sorted_pref[cat] = sorted(items, key=lambda x: x["preference_score"], reverse=True)
    return sorted_pref

# -----------------------------
# 일정 생성 함수
# -----------------------------
def generate_preference_itinerary(user_id, template, pref_data):
    start_time = time.perf_counter()
    itinerary = []
    used_ids = set()

    # ✅ 숙소는 유저 선호도 상위 1개 고정
    accommodation_id = str(pref_data["Accommodation"][0]["id"])

    for day_plan in template["itinerary"]:
        day_name = f"day{day_plan['day']}"
        is_peak = day_plan.get("season") == "peak"
        is_weekend = bool(day_plan.get("is_weekend", False))

        places = []

        for p in day_plan["place_plan"]:
            cat = p["category"]

            if cat == "Accommodation":
                places.append([accommodation_id, cat])
                continue

            # 카테고리별 preference 데이터 존재할 때만 선택
            if cat not in pref_data:
                continue

            for item in pref_data[cat]:
                pid = str(item["id"])
                if pid not in used_ids:
                    used_ids.add(pid)
                    places.append([pid, cat])
                    break

        itinerary.append([day_name, is_peak, is_weekend, places])

    elapsed = round((time.perf_counter() - start_time) * 1000, 2)  # ms 단위
    return [user_id, itinerary, elapsed]

# -----------------------------
# 실행부
# -----------------------------
def main():
    results = []

    for file in TEMPLATE_DIR.glob("U*_itinerary.json"):
        user_id = file.stem.split("_")[0]  # 예: U0045
        template_path = file
        pref_path = PREF_DIR / f"{user_id}_recommendations_preference.json"

        # 유저의 선호도 파일이 없으면 스킵
        if not pref_path.exists():
            print(f"⚠️ {user_id} 선호도 파일 없음, 건너뜀.")
            continue

        # 데이터 로드
        with open(template_path, "r", encoding="utf-8") as f:
            template = json.load(f)
        pref_data = load_preference_json(pref_path)

        # 그리디 생성
        result = generate_preference_itinerary(user_id, template, pref_data)
        results.append(result)
        print(f"✅ {user_id} preference 일정 생성 완료 ({len(template['itinerary'])}일차)")

    # 결과 저장
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 전체 {len(results)}개 유저 preference 일정 생성 완료 → {OUTPUT_PATH}")

# -----------------------------
# 실행
# -----------------------------
if __name__ == "__main__":
    main()
