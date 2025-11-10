import os
import json
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes import query as wq


# ========== CONFIG ==========
CONFIG = {
    "USER_FILE": r"C:\Users\changjin\workspace\lab\pln\data_set\1000_user_info.csv",
    "OUTPUT_DIR": r"C:\Users\changjin\workspace\lab\pln\vector_embedding\pure_preference_only",
}

CATEGORY_FILES = {
    "Accommodation": "accommodations_fixed.csv",
    "카페": "cafe_fixed.csv",
    "음식점": "restaurants_fixed.csv",
    "관광지": "attractions_fixed.csv"
}

# 카테고리 한글 → 영어 변환 매핑
CATEGORY_TRANSLATE = {
    "Accommodation": "Accommodation",
    "카페": "Cafe",
    "음식점": "Restaurant",
    "관광지": "Attraction"
}


# ========== 1. 환경 변수 및 클라이언트 연결 ==========
print("🔐 환경 변수 로딩...")
load_dotenv()

api_key = os.getenv("WEAVIATE_API_KEY")
cluster_url = os.getenv("WEAVIATE_CLUSTER_URL")

client = weaviate.connect_to_weaviate_cloud(
    cluster_url=cluster_url,
    auth_credentials=AuthApiKey(api_key)
)
print("✅ Weaviate 연결 완료\n")

collection = client.collections.get("Place")


# ========== 2. 모델 로드 ==========
model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")


# ========== 3. 전체 장소 점수 매기기 (필터링 없음) ==========
def score_all_places(user_like_vec, user_dislike_vecs, category_name, alpha=1.0, beta=0.5):
    """
    전체 장소에 대해 선호도 점수만 매기는 함수
    - 필터링 없음 (dislike_threshold 사용 안 함)
    - Top-K 제한 없음 (모든 장소 포함)
    - 순수하게 점수만 계산
    """
    results = collection.query.near_vector(
        near_vector=user_like_vec.tolist(),
        limit=4000,  # Weaviate 최대 제한
        return_metadata=["distance"],
        include_vector=True,
        filters=wq.Filter.by_property("category").equal(category_name)
    )

    scored = []
    seen_place_ids = set()  # 중복 방지

    for obj in results.objects:
        pid = obj.properties.get("place_id")
        if pid in seen_place_ids:
            continue
        seen_place_ids.add(pid)

        # Like 유사도 계산
        like_sim = 1 - obj.metadata.distance

        # Dislike 유사도 계산
        place_dislike_vec = obj.properties.get("dislike_embedding", [])
        max_dislike_sim = 0
        if place_dislike_vec and user_dislike_vecs:
            sims = [
                cosine_similarity([ud], [place_dislike_vec])[0][0]
                for ud in user_dislike_vecs if len(ud) > 0
            ]
            max_dislike_sim = max(sims) if sims else 0

        # 최종 점수: Like - Dislike (순수 선호도만)
        # ✅ 필터링 없음, 음수도 그대로 유지
        preference_score = alpha * like_sim - beta * max_dislike_sim
        
        scored.append((pid, preference_score))

    # 점수 기준 내림차순 정렬 (높은 점수가 앞으로)
    scored.sort(key=lambda x: x[1], reverse=True)
    
    # ✅ Top-K 제한 없이 전체 반환
    return scored


# ========== 4. 결과를 JSON 형식으로 변환 ==========
def format_results(results_by_cat):
    """
    카테고리별 결과를 JSON 형식으로 변환
    """
    final_scores = {}
    
    for cat, scored_list in results_by_cat.items():
        if not scored_list:
            continue
        
        # ID와 점수 리스트로 변환
        cat_list = [
            {
                "id": pid,
                "preference_score": float(score)
            }
            for pid, score in scored_list
        ]
        
        # 영어 카테고리명으로 저장
        final_scores[CATEGORY_TRANSLATE[cat]] = cat_list
    
    return final_scores


# ========== 5. 모든 유저 처리 ==========
user_df = pd.read_csv(CONFIG["USER_FILE"])
os.makedirs(CONFIG["OUTPUT_DIR"], exist_ok=True)

print(f"\n{'='*70}")
print(f"🚀 전체 장소 선호도 점수 계산 시작 (필터링 없음)")
print(f"{'='*70}\n")

for idx, user in user_df.iterrows():
    user_id = user["user_id"]
    like_keywords = eval(user["like_keywords"])
    dislike_keywords = eval(user["dislike_keywords"])

    print(f"👤 Processing User {idx+1}/{len(user_df)} → {user_id}")
    print(f"   👍 like: {like_keywords}")
    print(f"   👎 dislike: {dislike_keywords}")

    # 유저 선호도 벡터 생성
    user_like_vec = model.encode(" ".join(like_keywords), convert_to_numpy=True)
    user_dislike_vecs = [model.encode(kw, convert_to_numpy=True) for kw in dislike_keywords]

    # 카테고리별 전체 장소 점수 계산
    results_by_cat = {}
    for cat in CATEGORY_FILES.keys():
        results = score_all_places(
            user_like_vec, 
            user_dislike_vecs,
            cat
        )
        results_by_cat[cat] = results
        
        # 점수 통계
        if results:
            scores = [score for _, score in results]
            print(f"   📊 {CATEGORY_TRANSLATE[cat]}: {len(results)}개")
            print(f"      - 점수 범위: {min(scores):.3f} ~ {max(scores):.3f}")
            print(f"      - 평균: {sum(scores)/len(scores):.3f}")

    # JSON 형식으로 변환
    final_results = format_results(results_by_cat)

    # 유저별 결과 저장
    out_path = os.path.join(CONFIG["OUTPUT_DIR"], f"{user_id}_recommendations_preference.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)

    print(f"✅ {user_id} 결과 저장 완료 → {out_path}\n")


# ========== 6. 연결 종료 ==========
client.close()
print(f"\n{'='*70}")
print("🔒 전체 유저 처리 완료 & 연결 종료")
print(f"{'='*70}")