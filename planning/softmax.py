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
    "USER_INFO_DIR": r"planning\user_info",  # ✅ 디렉토리로 변경
    "DATA_DIR": r"planning\data_set",
    "OUTPUT_DIR": r"planning\softmax_result_test",
    "TOP_K": 300,
    "GAMMA": 0.3   # 리뷰수 가중치
}

CATEGORY_FILES = {
    "Accommodation": "accommodations_fixed.csv",
    "카페": "cafe_fixed.csv",
    "음식점": "restaurants_fixed.csv",
    "관광지": "attractions_fixed.csv"
}

CATEGORY_TRANSLATE = {
    "Accommodation": "Accommodation",
    "카페": "Cafe",
    "음식점": "Restaurant",
    "관광지": "Attraction"
}


# ========== 1. 환경 변수 및 클라이언트 연결 ==========
print("[환경 변수] 로딩 중...")
load_dotenv()

api_key = os.getenv("WEAVIATE_API_KEY")
cluster_url = os.getenv("WEAVIATE_CLUSTER_URL")

client = weaviate.connect_to_weaviate_cloud(
    cluster_url=cluster_url,
    auth_credentials=AuthApiKey(api_key)
)
print("[OK] Weaviate 연결 완료\n")

collection = client.collections.get("Place")


# ========== 2. 모델 로드 ==========
model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")


# ========== 3. 추천 함수 ==========
def rerank_with_penalty(user_like_vec, user_dislike_vecs, category_name,
                        top_k=30, alpha=1.0, beta=0.5, dislike_threshold=0.75):
    results = collection.query.near_vector(
        near_vector=user_like_vec.tolist(),
        limit=4000,
        return_metadata=["distance"],
        include_vector=True,
        filters=wq.Filter.by_property("category").equal(category_name)
    )

    scored = []
    seen_place_ids = set()

    for obj in results.objects:
        pid = obj.properties.get("place_id")
        if pid in seen_place_ids:
            continue
        seen_place_ids.add(pid)

        like_sim = 1 - obj.metadata.distance
        place_dislike_vec = obj.properties.get("dislike_embedding", [])
        max_dislike_sim = 0

        if place_dislike_vec:
            sims = [
                cosine_similarity([ud], [place_dislike_vec])[0][0]
                for ud in user_dislike_vecs if len(ud) > 0
            ]
            max_dislike_sim = max(sims) if sims else 0

        if max_dislike_sim > dislike_threshold:
            continue

        sim_score = alpha * like_sim - beta * max_dislike_sim
        sim_score = max(0, sim_score)
        scored.append((obj, sim_score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# ========== 4. 리뷰수 기반 정규화 + 최종 스코어 ==========
def attach_review_scores_and_final(results_by_cat, data_dir, gamma=0.3):
    final_scores = {}

    for cat, scored_list in results_by_cat.items():
        if not scored_list:
            continue

        df = pd.read_csv(os.path.join(data_dir, CATEGORY_FILES[cat]))
        review_col = "review_count" if cat == "Accommodation" else "all_review_count"
        review_dict = dict(zip(df["id"], df[review_col]))

        enriched = []
        for obj, sim_score in scored_list:
            pid = obj.properties.get("place_id")
            rc = review_dict.get(pid, 0)
            if pd.isna(rc):
                rc = 0
            enriched.append((pid, sim_score, rc))

        counts = np.array([rc for _, _, rc in enriched], dtype=float)
        if counts.sum() > 0:
            counts = np.log1p(counts)
            exp_counts = np.exp(counts - counts.max())
            review_norms = exp_counts / exp_counts.sum()
        else:
            review_norms = np.ones(len(enriched)) / len(enriched)

        cat_list = []
        for (pid, sim_score, _), rn in zip(enriched, review_norms):
            final_score = (1 - gamma) * sim_score + gamma * rn
            cat_list.append({
                "id": pid,
                "final_score": float(final_score)
            })

        cat_list = sorted(cat_list, key=lambda x: x["final_score"], reverse=True)
        final_scores[CATEGORY_TRANSLATE[cat]] = cat_list

    return final_scores


# ========== 5. 특정 유저 처리 ==========
def process_student(target_student_id):
    """특정 student_id만 처리"""
    os.makedirs(CONFIG["OUTPUT_DIR"], exist_ok=True)
    
    # 해당 student_id의 CSV 파일 찾기
    csv_file = f"{target_student_id}_user_info.csv"
    csv_path = os.path.join(CONFIG["USER_INFO_DIR"], csv_file)
    
    if not os.path.exists(csv_path):
        print(f"[ERROR] User info file not found: {csv_path}")
        return False
    
    user_df = pd.read_csv(csv_path)
    
    for idx, user in user_df.iterrows():
        user_id = user["user_id"]
        student_id = user["student_id"]
        like_keywords = eval(user["like_keywords"])
        dislike_keywords = eval(user["dislike_keywords"])

        print(f"\n[USER] Processing User -> {student_id}")
        print("   [LIKE]", like_keywords)
        print("   [DISLIKE]", dislike_keywords)

        user_like_vec = model.encode(" ".join(like_keywords), convert_to_numpy=True)
        user_dislike_vecs = [model.encode(kw, convert_to_numpy=True) for kw in dislike_keywords]

        results_by_cat = {}
        for cat in CATEGORY_FILES.keys():
            results_by_cat[cat] = rerank_with_penalty(user_like_vec, user_dislike_vecs,
                                                      cat, top_k=CONFIG["TOP_K"])

        review_scores_by_cat = attach_review_scores_and_final(results_by_cat,
                                                              CONFIG["DATA_DIR"],
                                                              gamma=CONFIG["GAMMA"])

        out_path = os.path.join(CONFIG["OUTPUT_DIR"], f"{student_id}_recommendations_softmax.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(review_scores_by_cat, f, ensure_ascii=False, indent=2)

        print(f"[OK] {student_id} 결과 저장 완료 -> {out_path}")
    
    return True


if __name__ == "__main__":
    import sys
    
    # 커맨드라인 인자로 student_id 받기
    if len(sys.argv) > 1:
        target_student_id = sys.argv[1]
        print(f"[TARGET] Processing student_id: {target_student_id}")
        success = process_student(target_student_id)
    else:
        # 인자가 없으면 모든 파일 처리 (하위호환)
        print("[MODE] Processing all users")
        csv_files = [f for f in os.listdir(CONFIG["USER_INFO_DIR"]) if f.endswith("_user_info.csv")]
        success = True
        for csv_file in csv_files:
            student_id = csv_file.replace("_user_info.csv", "")
            if not process_student(student_id):
                success = False
    
    # 연결 종료
    client.close()
    print("\n[CLOSE] 처리 완료 & 연결 종료")
    
    sys.exit(0 if success else 1)
