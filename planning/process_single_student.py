"""
단일 학번 처리를 위한 파이프라인
API에서 호출되어 특정 학번 하나만 처리합니다.
"""
import os
import sys
import json
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
PLANNING_DIR = BASE_DIR / "planning"
DATA_DIR = BASE_DIR / "data"
PLANS_DIR = DATA_DIR / "plans"


def main(student_id):
    """특정 학번에 대한 전체 파이프라인 실행"""
    print(f"\n[START] Processing student: {student_id}")
    start_time = time.time()
    
    try:
        # STEP 1: input.py 실행 (이미 input.json이 생성된 상태)
        print(f"\n[STEP 1/4] Processing user info...")
        result = subprocess.run(
            [sys.executable, str(PLANNING_DIR / "input.py")],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode != 0:
            print(f"[ERROR] Step 1 failed")
            print(result.stderr[:500])
            return False
        print(f"[OK] Step 1 completed")
        
        # STEP 2: softmax.py 실행 (student_id 전달)
        print(f"\n[STEP 2/4] Generating recommendations...")
        result = subprocess.run(
            [sys.executable, str(PLANNING_DIR / "softmax.py"), student_id],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=120
        )
        if result.returncode != 0:
            print(f"[ERROR] Step 2 failed")
            print(result.stderr[:500])
            return False
        print(f"[OK] Step 2 completed")
        
        # STEP 3: clustering (student_id 전달)
        print(f"\n[STEP 3/4] Clustering places...")
        sys.path.insert(0, str(PLANNING_DIR))
        from clustering import process_single_user
        process_single_user(student_id)
        print(f"[OK] Step 3 completed")
        
        # STEP 4: 최종 플랜 생성
        print(f"\n[STEP 4/4] Building final plans...")
        from run_pipeline import (
            load_place_data_for_schedule,
            load_sorted_by_review,
            build_popularity_schedule,
            generate_preference_scores,
            build_personalized_schedule,
            build_hybrid_schedule
        )
        import pandas as pd
        import csv
        
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
        food_budget_per_day = budget_per_day * 0.5
        
        place_data = load_place_data_for_schedule()
        
        # 3가지 플랜 생성
        sorted_data = load_sorted_by_review()
        popularity_days = build_popularity_schedule(template, place_data, sorted_data)
        
        preference_data = generate_preference_scores(student_id, user_info)
        personalized_days = build_personalized_schedule(template, place_data, preference_data)
        
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
        
        # users.csv에서 user_id 찾기
        users_csv = DATA_DIR / "users.csv"
        user_id = None
        if users_csv.exists():
            with open(users_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("student_id") == str(student_id):
                        user_id = row.get("user_id")
                        break
        
        # 저장
        output_file = PLANS_DIR / (f"{user_id}.json" if user_id else f"{student_id}_plan.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(full_schedule, f, ensure_ascii=False, indent=2)
        
        elapsed = time.time() - start_time
        print(f"\n[SUCCESS] Plan generated: {output_file}")
        print(f"[TIME] {elapsed:.2f} seconds")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_single_student.py <student_id>")
        sys.exit(1)
    
    student_id = sys.argv[1]
    success = main(student_id)
    sys.exit(0 if success else 1)

