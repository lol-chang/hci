"""
여행 추천 시스템 통합 실행 파일

이 파일은 다음 네 단계를 순차적으로 실행합니다:
1. input.py - 설문 데이터 처리 및 사용자 정보 생성
2. softmax.py - 장소 추천 및 스코어링
3. clustering.py - 클러스터링 및 여행 일정 생성
4. schedule_builder.py - 템플릿 기반 최종 일정 생성 (예산 반영)

사용법:
    python planning/run_pipeline.py
"""

import os
import sys
import time
import json
import csv
import pandas as pd
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes import query as wq

# 현재 스크립트의 디렉토리 경로
PLANNING_DIR = Path(__file__).parent
GREEDY_DIR = PLANNING_DIR.parent / "greedy"
BASE_DIR = PLANNING_DIR.parent

# planning 디렉토리를 Python 경로에 추가
sys.path.insert(0, str(PLANNING_DIR))

# 카테고리 매핑
CATEGORY_TRANSLATE = {
    "Accommodation": "Accommodation",
    "카페": "Cafe",
    "음식점": "Restaurant",
    "관광지": "Attraction"
}


def print_step(step_number, title, description=""):
    """단계별 실행 상태 출력"""
    print("\n" + "="*70)
    print(f"[STEP {step_number}] {title}")
    if description:
        print(f"   {description}")
    print("="*70 + "\n")


def check_input_file():
    """input.json 파일 존재 여부 확인"""
    input_file = PLANNING_DIR / "input.json"
    if not input_file.exists():
        print(f"[ERROR] {input_file} 파일을 찾을 수 없습니다.")
        print("   설문 데이터(input.json)를 먼저 생성해주세요.")
        return False
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            student_id = data["responses"].get("studentID")
            if not student_id:
                print("[ERROR] input.json에 studentID가 없습니다.")
                return False
            print(f"[OK] 설문 데이터 확인 완료 (학번: {student_id})")
            return True
    except Exception as e:
        print(f"[ERROR] input.json 파일을 읽을 수 없습니다: {e}")
        return False


def run_step_1_input():
    """STEP 1: input.py 실행"""
    print_step(1, "사용자 정보 처리", "설문 데이터를 처리하고 여행 스타일 템플릿을 생성합니다.")
    
    try:
        # input.py 모듈 import 및 실행
        import input as input_module
        
        print("\n[OK] STEP 1 완료: 사용자 정보 처리 성공")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] STEP 1 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_step_2_softmax():
    """STEP 2: softmax.py 실행"""
    print_step(2, "장소 추천 생성", "Weaviate를 사용하여 사용자 맞춤 장소를 추천합니다.")
    
    try:
        # softmax.py 모듈 import 및 실행
        import softmax as softmax_module
        
        print("\n[OK] STEP 2 완료: 장소 추천 생성 성공")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] STEP 2 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_step_3_clustering():
    """STEP 3: clustering.py 실행"""
    print_step(3, "일정 클러스터링", "추천 장소들을 공간 클러스터링하여 일별 여행 계획을 생성합니다.")
    
    try:
        # clustering.py의 process_all_users 함수 호출
        from clustering import process_all_users
        
        process_all_users()
        
        print("\n[OK] STEP 3 완료: 일정 클러스터링 성공")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] STEP 3 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 일정 생성 헬퍼 함수들 ====================

def load_place_data_for_schedule():
    """장소 데이터 로드"""
    place_data = {}
    csv_files = {"Cafe": "cafe_fixed.csv", "Restaurant": "restaurants_fixed.csv",
                 "Attraction": "attractions_fixed.csv", "Accommodation": "accommodations_fixed.csv"}
    
    for category, filename in csv_files.items():
        filepath = PLANNING_DIR / "data_set" / filename
        if not filepath.exists():
            continue
        df = pd.read_csv(filepath)
        for _, row in df.iterrows():
            place_id = row["id"]
            lat = row["lat"] if category == "Accommodation" else row["latitude"]
            lng = row["lng"] if category == "Accommodation" else row["longitude"]
            desc = row.get("description", "")
            if pd.isna(desc):
                desc = ""
            place_data[place_id] = {
                "id": place_id, "name": row["name"], "category": category,
                "latitude": lat, "longitude": lng,
                "avg_price": row.get("avg_price", 0) if category in ["Cafe", "Restaurant"] else None,
                "description": desc
            }
    return place_data


def load_sorted_by_review():
    """리뷰 수로 정렬된 CSV 로드"""
    sorted_data = {}
    files = {"Cafe": "cafe_fixed_sorted.csv", "Restaurant": "restaurants_fixed_sorted.csv",
             "Attraction": "attractions_fixed_sorted.csv", "Accommodation": "accommodations_fixed_sorted.csv"}
    for category, filename in files.items():
        filepath = GREEDY_DIR / "sorting_review_dataset" / filename
        if filepath.exists():
            sorted_data[category] = pd.read_csv(filepath).to_dict('records')
    return sorted_data


def build_popularity_schedule(template, place_data, sorted_data):
    """인기도 기반 일정 (예산 무관)"""
    days, used_ids = {}, set()
    accommodation_id = sorted_data.get("Accommodation", [{}])[0].get("id") if sorted_data.get("Accommodation") else None
    for day_info in template["itinerary"]:
        day_schedule = []
        for slot in day_info["place_plan"]:
            cat, time = slot["category"], slot["time"]
            if cat == "Accommodation":
                if accommodation_id and accommodation_id in place_data:
                    info = place_data[accommodation_id]
                    day_schedule.append({"id": int(accommodation_id), "name": info["name"], "description": info["description"],
                                       "lat": float(info["latitude"]), "lng": float(info["longitude"]), "time": time, "category": cat})
                continue
            for cand in sorted_data.get(cat, []):
                pid = cand.get("id") if isinstance(cand, dict) else cand
                if pid in used_ids or pid not in place_data:
                    continue
                used_ids.add(pid)
                info = place_data[pid]
                day_schedule.append({"id": int(pid), "name": info["name"], "description": info["description"],
                                   "lat": float(info["latitude"]), "lng": float(info["longitude"]), "time": time, "category": cat})
                break
        days[f"day{day_info['day']}"] = day_schedule
    return days


def generate_preference_scores(student_id, user_info):
    """선호도 점수 생성"""
    print(f"\n[PREFERENCE] {student_id} 선호도 점수 계산 중...")
    load_dotenv()
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=os.getenv("WEAVIATE_CLUSTER_URL"),
        auth_credentials=AuthApiKey(os.getenv("WEAVIATE_API_KEY"))
    )
    collection = client.collections.get("Place")
    model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    like_keywords = eval(user_info["like_keywords"])
    dislike_keywords = eval(user_info["dislike_keywords"])
    user_like_vec = model.encode(" ".join(like_keywords), convert_to_numpy=True)
    user_dislike_vecs = [model.encode(kw, convert_to_numpy=True) for kw in dislike_keywords]
    results_by_cat = {}
    for korean_cat in ["Accommodation", "카페", "음식점", "관광지"]:
        results = collection.query.near_vector(near_vector=user_like_vec.tolist(), limit=4000, return_metadata=["distance"],
                                              include_vector=True, filters=wq.Filter.by_property("category").equal(korean_cat))
        scored, seen_ids = [], set()
        for obj in results.objects:
            pid = obj.properties.get("place_id")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            like_sim = 1 - obj.metadata.distance
            place_dislike_vec = obj.properties.get("dislike_embedding", [])
            max_dislike_sim = 0
            if place_dislike_vec and user_dislike_vecs:
                sims = [cosine_similarity([ud], [place_dislike_vec])[0][0] for ud in user_dislike_vecs if len(ud) > 0]
                max_dislike_sim = max(sims) if sims else 0
            scored.append({"id": pid, "preference_score": float(like_sim - 0.5 * max_dislike_sim)})
        scored.sort(key=lambda x: x["preference_score"], reverse=True)
        results_by_cat[CATEGORY_TRANSLATE[korean_cat]] = scored
    client.close()
    pref_dir = PLANNING_DIR / "pure_preference_only"
    os.makedirs(pref_dir, exist_ok=True)
    pref_file = pref_dir / f"{student_id}_recommendations_preference.json"
    with open(pref_file, "w", encoding="utf-8") as f:
        json.dump(results_by_cat, f, ensure_ascii=False, indent=2)
    print(f"[OK] 선호도 점수 저장: {pref_file}")
    return results_by_cat


def build_personalized_schedule(template, place_data, preference_data):
    """선호도 기반 일정 (예산 무관)"""
    days, used_ids = {}, set()
    accommodation_id = preference_data.get("Accommodation", [{}])[0].get("id") if preference_data.get("Accommodation") else None
    for day_info in template["itinerary"]:
        day_schedule = []
        for slot in day_info["place_plan"]:
            cat, time = slot["category"], slot["time"]
            if cat == "Accommodation":
                if accommodation_id and accommodation_id in place_data:
                    info = place_data[accommodation_id]
                    day_schedule.append({"id": int(accommodation_id), "name": info["name"], "description": info["description"],
                                       "lat": float(info["latitude"]), "lng": float(info["longitude"]), "time": time, "category": cat})
                continue
            for cand in preference_data.get(cat, []):
                pid = cand.get("id") if isinstance(cand, dict) else cand
                if pid in used_ids or pid not in place_data:
                    continue
                used_ids.add(pid)
                info = place_data[pid]
                day_schedule.append({"id": int(pid), "name": info["name"], "description": info["description"],
                                   "lat": float(info["latitude"]), "lng": float(info["longitude"]), "time": time, "category": cat})
                break
        days[f"day{day_info['day']}"] = day_schedule
    return days


def build_hybrid_schedule(template, place_data, cluster_data, budget_per_day):
    """Hybrid 일정 (예산 고려)"""
    days, used_ids = {}, set()
    accommodation_id = cluster_data.get("Accommodation")
    clusters = cluster_data["clusters"]
    for day_info in template["itinerary"]:
        day_num = day_info["day"]
        cluster = clusters[min(day_num - 1, len(clusters) - 1)]
        day_schedule, day_budget = [], budget_per_day
        for slot in day_info["place_plan"]:
            cat, time = slot["category"], slot["time"]
            if cat == "Accommodation":
                if accommodation_id and accommodation_id in place_data:
                    info = place_data[accommodation_id]
                    day_schedule.append({"id": int(accommodation_id), "name": info["name"], "description": info["description"],
                                       "lat": float(info["latitude"]), "lng": float(info["longitude"]), "time": time, "category": cat})
                continue
            for cand in cluster["categories"].get(cat, []):
                pid = cand.get("id") if isinstance(cand, dict) else cand
                if pid in used_ids or pid not in place_data:
                    continue
                info = place_data[pid]
                if cat in ["Cafe", "Restaurant"]:
                    price = info.get("avg_price", 0)
                    if pd.isna(price) or price == 0:
                        price = 5000
                    if price > day_budget:
                        continue
                    day_budget -= price
                used_ids.add(pid)
                day_schedule.append({"id": int(pid), "name": info["name"], "description": info["description"],
                                   "lat": float(info["latitude"]), "lng": float(info["longitude"]), "time": time, "category": cat})
                break
        days[f"day{day_num}"] = day_schedule
    return days


def run_step_4_schedule():
    """STEP 4: 3가지 여행 플랜 생성"""
    print_step(4, "최종 일정 생성", "3가지 여행 플랜(Popularity + Personalized + Hybrid)을 생성합니다.")
    
    try:
        # input.json에서 학번 추출
        with open(PLANNING_DIR / "input.json", "r", encoding="utf-8") as f:
            student_id = json.load(f)["responses"]["studentID"]
        
        # 파일 로드
        template_file = PLANNING_DIR / "user_templates" / f"{student_id}_template.json"
        cluster_file = PLANNING_DIR / "clustering_result_test" / f"{student_id}_daily_clusters.json"
        user_info_file = PLANNING_DIR / "user_info" / f"{student_id}_user_info.csv"
        
        with open(template_file, "r", encoding="utf-8") as f:
            template = json.load(f)
        with open(cluster_file, "r", encoding="utf-8") as f:
            cluster_data = json.load(f)
        user_info = pd.read_csv(user_info_file).iloc[0].to_dict()
        
        budget_per_day = template["budget_per_day"]
        # 숙소는 별도 예산(50%)으로 이미 처리됨
        # 음식/카페 예산 = 일일 예산의 50%
        food_budget_per_day = budget_per_day * 0.5
        
        place_data = load_place_data_for_schedule()
        
        # 3가지 플랜 생성
        print(f"\n[1/3] Popularity 플랜 생성 중...")
        sorted_data = load_sorted_by_review()
        popularity_days = build_popularity_schedule(template, place_data, sorted_data)
        
        print(f"\n[2/3] Personalized 플랜 생성 중...")
        preference_data = generate_preference_scores(student_id, user_info)
        personalized_days = build_personalized_schedule(template, place_data, preference_data)
        
        print(f"\n[3/3] Hybrid 플랜 생성 중...")
        print(f"   [예산] 일일 음식/카페 예산: {food_budget_per_day:,.0f}원 (총 예산의 50%)")
        hybrid_days = build_hybrid_schedule(template, place_data, cluster_data, food_budget_per_day)
        
        # 최종 JSON 구성
        full_schedule = {
            "studentId": str(student_id),
            "plan_order": ["hybrid", "popularity", "personalized"],
            "plans": {
                "popularity": {"label": "인기도", "days": popularity_days},
                "personalized": {"label": "개인화", "days": personalized_days},
                "hybrid": {"label": "인기도 + 개인화", "days": hybrid_days}
            }
        }
        
        # 저장
        users_csv = BASE_DIR / "data" / "users.csv"
        user_id = None
        if users_csv.exists():
            with open(users_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("student_id") == str(student_id):
                        user_id = row.get("user_id")
                        break
        
        output_dir = BASE_DIR / "data" / "plans"
        os.makedirs(output_dir, exist_ok=True)
        output_file = output_dir / (f"{user_id}.json" if user_id else f"{student_id}_plan.json")
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(full_schedule, f, ensure_ascii=False, indent=2)
        
        print(f"\n[SAVE] 전체 플랜 저장 완료: {output_file}")
        print("\n[OK] STEP 4 완료: 3가지 플랜 생성 성공")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] STEP 4 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def print_results():
    """최종 결과 파일 출력"""
    print("\n" + "="*70)
    print("*** 전체 파이프라인 실행 완료! ***")
    print("="*70)
    
    # 생성된 파일 확인
    print("\n[생성된 파일들]")
    
    # user_templates
    template_dir = PLANNING_DIR / "user_templates"
    if template_dir.exists():
        templates = list(template_dir.glob("*_template.json"))
        for t in templates:
            print(f"   + {t.relative_to(BASE_DIR)}")
    
    # user_info
    info_dir = PLANNING_DIR / "user_info"
    if info_dir.exists():
        infos = list(info_dir.glob("*_user_info.csv"))
        for i in infos:
            print(f"   + {i.relative_to(BASE_DIR)}")
    
    # softmax_result_test
    softmax_dir = PLANNING_DIR / "softmax_result_test"
    if softmax_dir.exists():
        softmax_results = list(softmax_dir.glob("*_recommendations_softmax.json"))
        for s in softmax_results:
            print(f"   + {s.relative_to(BASE_DIR)}")
    
    # clustering_result_test
    cluster_dir = PLANNING_DIR / "clustering_result_test"
    if cluster_dir.exists():
        cluster_results = list(cluster_dir.glob("*_daily_clusters.json"))
        for c in cluster_results:
            print(f"   + {c.relative_to(BASE_DIR)}")
    
    # pure_preference_only
    pref_dir = PLANNING_DIR / "pure_preference_only"
    if pref_dir.exists():
        pref_results = list(pref_dir.glob("*_recommendations_preference.json"))
        for p in pref_results:
            print(f"   + {p.relative_to(BASE_DIR)}")
    
    # final plans (최종 결과!)
    plans_dir = BASE_DIR / "data" / "plans"
    if plans_dir.exists():
        plan_results = list(plans_dir.glob("*.json"))
        for p in plan_results:
            if p.name.endswith("_plan.json") or p.stem.startswith("u"):
                print(f"   + {p.relative_to(BASE_DIR)} *** [최종 일정] ***")
    
    print("\n" + "="*70)


def main():
    """메인 실행 함수"""
    start_time = time.time()
    
    print("\n" + "="*70)
    print("   여행 추천 시스템 통합 파이프라인")
    print("="*70)
    
    # 입력 파일 확인
    if not check_input_file():
        sys.exit(1)
    
    # STEP 1: 사용자 정보 처리
    if not run_step_1_input():
        print("\n[STOP] 파이프라인 중단: STEP 1에서 오류 발생")
        sys.exit(1)
    
    time.sleep(1)  # 파일 I/O 안정화
    
    # STEP 2: 장소 추천
    if not run_step_2_softmax():
        print("\n[STOP] 파이프라인 중단: STEP 2에서 오류 발생")
        sys.exit(1)
    
    time.sleep(1)  # 파일 I/O 안정화
    
    # STEP 3: 클러스터링
    if not run_step_3_clustering():
        print("\n[STOP] 파이프라인 중단: STEP 3에서 오류 발생")
        sys.exit(1)
    
    time.sleep(1)  # 파일 I/O 안정화
    
    # STEP 4: 최종 일정 생성
    if not run_step_4_schedule():
        print("\n[STOP] 파이프라인 중단: STEP 4에서 오류 발생")
        sys.exit(1)
    
    # 결과 출력
    print_results()
    
    # 총 실행 시간
    elapsed_time = time.time() - start_time
    print(f"\n[총 실행 시간] {elapsed_time:.2f}초")
    print("\n*** 모든 작업이 성공적으로 완료되었습니다! ***\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[WARNING] 사용자에 의해 실행이 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] 예상치 못한 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

