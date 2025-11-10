import os
import json
import pandas as pd
import numpy as np
from sklearn.neighbors import BallTree
import logging
from joblib import Parallel, delayed
import time

CONFIG = {
    "USER_INFO_FILE": r"planning\user_info\202110862_user_info.csv",
    "USER_PREF_DIR": r"planning\softmax_result_test",
    "PLACE_FILE": r"planning\data_set\clustering_category_combine_with_hours_and_price.csv",
    "OUTPUT_DIR": r"planning\clustering_result_test",
    "LOG_DIR": r"planning\clustering_result_test\log",
    "PLACES_PER_CATEGORY": 10,
    "MIN_PLACES_PER_CATEGORY": 10,
    "MAX_CLUSTER_RADIUS_KM": 6,
    "PREFERENCE_WEIGHT": 0.7,
    "DISTANCE_WEIGHT": 0.3,
    "USE_PARALLEL": True,
    "N_JOBS": 4,
    "PARALLEL_BACKEND": "threading",
}

CLUSTER_CATEGORIES = ["Cafe", "Restaurant", "Attraction"]
logger = None


def haversine_vectorized(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c


def setup_logging(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "clustering_v4_studentid.log")

    global logger
    logger = logging.getLogger("clustering_v4_studentid")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(message)s"))
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(fh)
    logger.addHandler(ch)
    return log_file


def log_print(msg):
    if logger:
        logger.info(msg)
    else:
        print(msg)


def load_place_locations(place_file):
    df = pd.read_csv(place_file)
    for col in ["offpeak_weekday_price_avg", "offpeak_weekend_price_avg", "avg_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    loc_dict = {}
    for _, r in df.iterrows():
        loc_dict[r["id"]] = {
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "name": r["name"],
            "category": r["category"],
            "avg_price": r.get("avg_price", np.nan),
            "offpeak_weekend_price": r.get("offpeak_weekend_price_avg", np.nan)
        }
    log_print(f"[OK] 장소 {len(loc_dict)}개 로드 완료")
    return loc_dict


def load_all_user_preferences(user_pref_dir, user_df):
    prefs_cache = {}
    for _, row in user_df.iterrows():
        user_id = row["user_id"]
        student_id = row["student_id"]
        pref_file = os.path.join(user_pref_dir, f"{student_id}_recommendations_softmax.json")
        if os.path.exists(pref_file):
            with open(pref_file, "r", encoding="utf-8") as f:
                prefs_cache[user_id] = json.load(f)
        else:
            log_print(f"[WARNING] {pref_file} 파일 없음")
    log_print(f"[OK] {len(prefs_cache)}명 선호도 캐싱 완료")
    return prefs_cache


def build_spatial_indices(df):
    indices = {}
    for cat in CLUSTER_CATEGORIES:
        cat_df = df[df["category"] == cat].copy()
        if len(cat_df) > 0:
            coords = np.radians(cat_df[["latitude", "longitude"]].values)
            indices[cat] = {
                "tree": BallTree(coords, metric="haversine"),
                "df": cat_df.reset_index(drop=True)
            }
    return indices


def extract_all_user_places(user_prefs, location_dict):
    rows = []
    for cat, places in user_prefs.items():
        if cat not in CLUSTER_CATEGORIES:
            continue
        for p in places:
            pid = p["id"]
            if pid not in location_dict:
                continue
            loc = location_dict[pid]
            rows.append({
                "id": pid,
                "name": loc["name"],
                "category": cat,
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "final_score": p["final_score"]
            })
    return pd.DataFrame(rows)


def find_nearest_places(seed_loc, spatial_index, n, max_radius_km, used_ids):
    if not spatial_index:
        return pd.DataFrame()
    tree = spatial_index["tree"]
    df = spatial_index["df"]
    seed_radians = np.radians([[seed_loc[0], seed_loc[1]]])
    indices = tree.query_radius(seed_radians, r=max_radius_km/6371)[0]
    if len(indices) == 0:
        return pd.DataFrame()

    sub = df.iloc[indices].copy()
    sub = sub[~sub["id"].isin(used_ids)]
    sub["distance"] = haversine_vectorized(seed_loc[0], seed_loc[1], sub["latitude"].values, sub["longitude"].values)
    sub["distance_score"] = 1 - (sub["distance"] / max_radius_km)
    sub["combined_score"] = (
        CONFIG["PREFERENCE_WEIGHT"] * sub["final_score"] +
        CONFIG["DISTANCE_WEIGHT"] * sub["distance_score"]
    )
    return sub.nlargest(n, "combined_score")


def greedy_clustering_optimized(df, spatial_indices, n_clusters, budget):
    clusters = []
    used_ids = set()
    used_seed_ids = set()
    budget_per_day = budget / n_clusters if budget else np.inf
    for i in range(n_clusters):
        seed_candidates = df[~df["id"].isin(used_seed_ids)].copy()
        if len(seed_candidates) == 0:
            seed_candidates = df.copy()
        top_candidates = seed_candidates.nlargest(min(20, len(seed_candidates)), "final_score")
        valid_seeds = []
        for _, s in top_candidates.iterrows():
            seed_loc = (s["latitude"], s["longitude"])
            total_score = 0
            valid = True
            for cat in CLUSTER_CATEGORIES:
                if cat not in spatial_indices:
                    valid = False
                    break
                found = find_nearest_places(seed_loc, spatial_indices[cat],
                                            CONFIG["PLACES_PER_CATEGORY"],
                                            CONFIG["MAX_CLUSTER_RADIUS_KM"],
                                            used_ids)
                if len(found) < CONFIG["MIN_PLACES_PER_CATEGORY"]:
                    valid = False
                    break
                total_score += found["final_score"].sum()
            if valid:
                valid_seeds.append((s, total_score))
        seed = max(valid_seeds, key=lambda x: x[1])[0] if valid_seeds else seed_candidates.iloc[0]
        used_ids.add(seed["id"])
        used_seed_ids.add(seed["id"])
        seed_loc = (seed["latitude"], seed["longitude"])
        cluster = {
            "cluster_id": i,
            "seed_category": seed["category"],
            "seed_place": {"id": int(seed["id"]), "name": seed["name"], "final_score": round(float(seed["final_score"]), 4)},
            "center_lat": seed_loc[0],
            "center_lng": seed_loc[1],
            "categories": {}
        }
        for cat in CLUSTER_CATEGORIES:
            if cat not in spatial_indices:
                continue
            found = find_nearest_places(seed_loc, spatial_indices[cat],
                                        CONFIG["PLACES_PER_CATEGORY"],
                                        CONFIG["MAX_CLUSTER_RADIUS_KM"],
                                        used_ids)
            cat_places = []
            for _, p in found.iterrows():
                used_ids.add(p["id"])
                cat_places.append({"id": int(p["id"]), "name": p["name"], "final_score": round(float(p["final_score"]), 4)})
            cluster["categories"][cat] = cat_places
        clusters.append(cluster)
    return clusters


def select_best_accommodation(user_prefs, clusters, location_dict, budget, duration_days):
    if duration_days <= 1:
        return None, None
    accs = user_prefs.get("Accommodation", [])
    total_acc_budget = budget * 0.5
    candidates = []
    for acc in accs:
        aid = acc["id"]
        if aid not in location_dict:
            continue
        loc = location_dict[aid]
        price = loc.get("offpeak_weekend_price", loc.get("avg_price", np.nan))
        if pd.isna(price):
            continue
        total_cost = price * (duration_days - 1)
        if total_cost > total_acc_budget:
            continue
        coords = np.array([[c["center_lat"], c["center_lng"]] for c in clusters])
        mean = coords.mean(axis=0)
        dist = haversine_vectorized(loc["latitude"], loc["longitude"], mean[0], mean[1])
        score = CONFIG["PREFERENCE_WEIGHT"] * acc["final_score"] + (1 - CONFIG["PREFERENCE_WEIGHT"]) * (1 / (1 + dist))
        candidates.append({"id": aid, "name": loc["name"], "score": score})
    if not candidates:
        return None, None
    best = max(candidates, key=lambda x: x["score"])
    return best["id"], best["score"]


def process_user(user_id, user_info, prefs_cache, location_dict, output_dir):
    if user_id not in prefs_cache:
        log_print(f"[WARNING] {user_id} 캐시 없음")
        return
    user_prefs = prefs_cache[user_id]
    df = extract_all_user_places(user_prefs, location_dict)
    spatial_indices = build_spatial_indices(df)
    clusters = greedy_clustering_optimized(df, spatial_indices, user_info["duration_days"], user_info["budget"])
    accommodation_id, accommodation_score = select_best_accommodation(
        user_prefs, clusters, location_dict, user_info["budget"], user_info["duration_days"]
    )
    result = {
        "user_id": user_id,
        "student_id": user_info["student_id"],  # ✅ 추가됨
        "name": user_info["name"],
        "rotate": eval(user_info["rotate"]),
        "travel_style": user_info["travel_style"],
        "budget": user_info["budget"],
        "duration_days": user_info["duration_days"],
        "like_keywords": eval(user_info["like_keywords"]),
        "dislike_keywords": eval(user_info["dislike_keywords"]),
        "Accommodation": accommodation_id,
        "accommodation_score": accommodation_score,
        "clusters": clusters
    }
    os.makedirs(output_dir, exist_ok=True)
    student_id = user_info["student_id"]  # ✅ 파일명 변경
    out_file = os.path.join(output_dir, f"{student_id}_daily_clusters.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log_print(f"[SAVE] {student_id} 저장 완료 -> {out_file}")


def process_single_user(target_student_id):
    """특정 student_id만 처리"""
    log_file = setup_logging(CONFIG["LOG_DIR"])
    log_print(f"[LOG] 로그 파일: {log_file}")
    location_dict = load_place_locations(CONFIG["PLACE_FILE"])
    
    # 특정 student_id의 CSV 파일만 처리
    user_info_dir = r"planning\user_info"
    csv_file = f"{target_student_id}_user_info.csv"
    csv_path = os.path.join(user_info_dir, csv_file)
    
    if not os.path.exists(csv_path):
        log_print(f"[ERROR] User info file not found: {csv_path}")
        return False
    
    log_print(f"[PROCESSING] {csv_file}")
    
    user_df = pd.read_csv(csv_path)
    prefs_cache = load_all_user_preferences(CONFIG["USER_PREF_DIR"], user_df)
    
    for _, row in user_df.iterrows():
        user_id = row["user_id"]
        user_info = {
            "name": row["name"],
            "student_id": row["student_id"],
            "rotate": row["rotate"],
            "travel_style": row["travel_style"],
            "budget": row["budget"],
            "duration_days": int(row["duration_days"]),
            "like_keywords": row["like_keywords"],
            "dislike_keywords": row["dislike_keywords"]
        }
        process_user(user_id, user_info, prefs_cache, location_dict, CONFIG["OUTPUT_DIR"])
    
    return True


def process_all_users():
    """모든 user_info CSV 파일 처리 (하위호환)"""
    log_file = setup_logging(CONFIG["LOG_DIR"])
    log_print(f"[LOG] 로그 파일: {log_file}")
    location_dict = load_place_locations(CONFIG["PLACE_FILE"])
    
    user_info_dir = r"planning\user_info"
    csv_files = [f for f in os.listdir(user_info_dir) if f.endswith("_user_info.csv")]
    
    if not csv_files:
        log_print("[WARNING] No user_info CSV files found")
        return
    
    for csv_file in csv_files:
        csv_path = os.path.join(user_info_dir, csv_file)
        log_print(f"[PROCESSING] {csv_file}")
        
        user_df = pd.read_csv(csv_path)
        prefs_cache = load_all_user_preferences(CONFIG["USER_PREF_DIR"], user_df)
        
        for _, row in user_df.iterrows():
            user_id = row["user_id"]
            user_info = {
                "name": row["name"],
                "student_id": row["student_id"],
                "rotate": row["rotate"],
                "travel_style": row["travel_style"],
                "budget": row["budget"],
                "duration_days": int(row["duration_days"]),
                "like_keywords": row["like_keywords"],
                "dislike_keywords": row["dislike_keywords"]
            }
            process_user(user_id, user_info, prefs_cache, location_dict, CONFIG["OUTPUT_DIR"])


if __name__ == "__main__":
    import sys
    
    # 커맨드라인 인자로 student_id 받기
    if len(sys.argv) > 1:
        target_student_id = sys.argv[1]
        log_print(f"[TARGET] Processing student_id: {target_student_id}")
        process_single_user(target_student_id)
    else:
        # 인자가 없으면 모든 파일 처리
        process_all_users()
