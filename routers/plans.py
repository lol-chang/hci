# routers/plans.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import csv
import json

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[1]  # project_root
DATA_DIR = BASE_DIR / "data"
PLANS_DIR = DATA_DIR / "plans"
USERS_CSV = DATA_DIR / "users.csv"


class StudentRequest(BaseModel):
    student_id: str


@router.post("/by-student")
def get_plans_by_student(payload: StudentRequest):
    student_id = payload.student_id.strip()

    if not student_id:
        raise HTTPException(status_code=400, detail="학번이 비어 있습니다.")

    if not USERS_CSV.exists():
        raise HTTPException(status_code=404, detail="등록된 사용자가 없습니다. (users.csv 없음)")

    matched_user_id = None
    matched_name = None

    with open(USERS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("student_id") == student_id:
                matched_user_id = row.get("user_id")
                matched_name = row.get("name")
                break

    if not matched_user_id:
        raise HTTPException(status_code=404, detail="해당 학번의 사용자를 찾을 수 없습니다.")

    plan_path = PLANS_DIR / f"{matched_user_id}.json"
    if not plan_path.exists():
        raise HTTPException(status_code=404, detail="해당 사용자의 플랜 파일이 존재하지 않습니다.")

    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="플랜 JSON 파일이 손상되었습니다.")

    plans = raw.get("plans")
    if not plans:
        raise HTTPException(status_code=500, detail="플랜 구조가 올바르지 않습니다. (plans 누락)")

    # plan_order: UI에서 플랜1/2/3 매핑용
    plan_order = raw.get("plan_order")
    if not plan_order:
        # 없으면 기본 순서
        plan_order = ["popularity", "personalized", "hybrid"]

    # 응답에는 내부 타입명 그대로, UI에서만 플랜1/2/3으로 숨김
    return {
        "user_id": matched_user_id,
        "name": matched_name,
        "student_id": student_id,
        "plan_order": plan_order,
        "plans": plans
    }
