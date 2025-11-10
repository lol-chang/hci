import json
import pandas as pd
from pathlib import Path
import time

# -----------------------------
# 경로 설정
# -----------------------------
BASE_DIR = Path(r"C:\Users\changjin\workspace\lab\pln")
TEMPLATE_DIR = BASE_DIR / "evaluation" / "100_plan_template"

ACCOM_PATH = BASE_DIR / "greedy" / "sorting_review_dataset" / "accommodations_fixed_sorted.csv"
ATTR_PATH = BASE_DIR / "greedy" / "sorting_review_dataset" / "attractions_fixed_sorted.csv"
CAFE_PATH = BASE_DIR / "greedy" / "sorting_review_dataset" / "cafe_fixed_sorted.csv"
REST_PATH = BASE_DIR / "greedy" / "sorting_review_dataset" / "restaurants_fixed_sorted.csv"

OUTPUT_PATH = BASE_DIR / "evaluation" / "100_generated_plan" / "review_summary.json"

# -----------------------------
# CSV 로드 및 정렬 함수
# -----------------------------
def load_sorted_csv(path):
    df = pd.read_csv(path)
    df = df.sort_values(by="all_review_count", ascending=False)
    return df.reset_index(drop=True)

# -----------------------------
# 일정 생성 함수
# -----------------------------
def generate_itinerary(user_id, template, accom_df, attr_df, cafe_df, rest_df):
    start_time = time.perf_counter()
    itinerary = []
    used_ids = set()

    # ✅ 유저의 숙소는 고정 (가장 리뷰 많은 1개)
    accommodation_id = str(accom_df.iloc[0]["id"])

    for day_plan in template["itinerary"]:
        day_name = f"day{day_plan['day']}"
        is_peak = day_plan.get("season") == "peak"
        is_weekend = bool(day_plan.get("is_weekend", False))

        places = []
        for p in day_plan["place_plan"]:
            cat = p["category"]

            # 숙소는 항상 동일한 ID
            if cat == "Accommodation":
                places.append([accommodation_id, cat])
                continue

            # 나머지 카테고리는 리뷰 많은 순서대로
            if cat == "Attraction":
                df = attr_df
            elif cat == "Cafe":
                df = cafe_df
            elif cat == "Restaurant":
                df = rest_df
            else:
                continue

            for _, row in df.iterrows():
                pid = str(row["id"])
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
    accom_df = load_sorted_csv(ACCOM_PATH)
    attr_df = load_sorted_csv(ATTR_PATH)
    cafe_df = load_sorted_csv(CAFE_PATH)
    rest_df = load_sorted_csv(REST_PATH)

    results = []

    for file in TEMPLATE_DIR.glob("U*_itinerary.json"):
        user_id = file.stem.split("_")[0]  # 예: U0045
        with open(file, "r", encoding="utf-8") as f:
            template = json.load(f)

        result = generate_itinerary(user_id, template, accom_df, attr_df, cafe_df, rest_df)
        results.append(result)
        print(f"✅ {user_id} 일정 생성 완료 ({len(template['itinerary'])}일차)")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 전체 {len(results)}개 유저 일정 생성 완료 → {OUTPUT_PATH}")

# -----------------------------
# 실행
# -----------------------------
if __name__ == "__main__":
    main()
