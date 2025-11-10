# routers/survey.py
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json
import csv
import os
import sys
import subprocess
from datetime import datetime
from typing import Dict, Optional

router = APIRouter()

# 경로 설정
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
PLANS_DIR = DATA_DIR / "plans"
USERS_CSV = DATA_DIR / "users.csv"
PLANNING_DIR = BASE_DIR / "planning"
INPUT_JSON = PLANNING_DIR / "input.json"

DATA_DIR.mkdir(exist_ok=True)
PLANS_DIR.mkdir(exist_ok=True)
PLANNING_DIR.mkdir(exist_ok=True)


# 구글폼 응답 형식에 맞춘 Pydantic 모델
class SurveyResponse(BaseModel):
    name: str
    studentID: str
    rank_category: Dict[str, str]  # {"역사·문화": "1", ...}
    keyword_history: str
    keyword_nature: str
    keyword_food: str
    keyword_activity: str
    keyword_accomodation: str
    budget: str


class SurveyInput(BaseModel):
    responses: SurveyResponse
    timestamp: Optional[str] = None
    formUrl: Optional[str] = None


def run_pipeline_for_student(student_id: str):
    """
    백그라운드에서 파이프라인 실행 (특정 학번만 처리)
    """
    try:
        print(f"\n[PIPELINE START] {student_id} - Plan generation started")
        
        # Python 실행 파일 경로
        python_exe = sys.executable
        
        # process_single_student.py 실행 (student_id 전달)
        result = subprocess.run(
            [python_exe, str(PLANNING_DIR / "process_single_student.py"), student_id],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',  # 인코딩 오류 무시
            timeout=300  # 5분 타임아웃
        )
        
        if result.returncode == 0:
            print(f"[PIPELINE SUCCESS] {student_id} - Plan generated successfully")
            # 출력은 영어로만 (인코딩 문제 방지)
        else:
            print(f"[PIPELINE ERROR] {student_id} - Failed with return code {result.returncode}")
            # stderr 출력 시 인코딩 안전하게 처리
            if result.stderr:
                try:
                    error_msg = result.stderr[-500:] if len(result.stderr) > 500 else result.stderr
                    # ASCII 범위 외 문자 제거
                    error_msg = error_msg.encode('ascii', errors='ignore').decode('ascii')
                    print(f"STDERR: {error_msg}")
                except:
                    print("STDERR: (encoding error, message omitted)")
            
    except subprocess.TimeoutExpired:
        print(f"[PIPELINE TIMEOUT] {student_id} - Exceeded 5 minutes")
    except Exception as e:
        print(f"[PIPELINE ERROR] {student_id} - Exception: {str(e)}")
        # traceback 출력 시 인코딩 오류 방지
        try:
            import traceback
            import io
            buf = io.StringIO()
            traceback.print_exc(file=buf)
            tb = buf.getvalue()
            # ASCII만 출력
            tb_safe = tb.encode('ascii', errors='ignore').decode('ascii')
            print(tb_safe)
        except:
            print("(traceback omitted due to encoding error)")


def generate_user_id():
    """
    user_id 생성: u + 3자리 숫자 (u001, u002, ...)
    """
    if not USERS_CSV.exists():
        return "u001"
    
    with open(USERS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_ids = [row["user_id"] for row in reader]
    
    # 마지막 번호 찾기
    max_num = 0
    for uid in existing_ids:
        if uid.startswith("u") and uid[1:].isdigit():
            max_num = max(max_num, int(uid[1:]))
    
    return f"u{max_num + 1:03d}"


@router.post("/submit")
def submit_survey(payload: SurveyInput, background_tasks: BackgroundTasks):
    """
    구글폼 설문 제출 → 파이프라인 실행
    """
    try:
        responses = payload.responses
        student_id = responses.studentID.strip()
        name = responses.name.strip()
        
        # 1. 중복 체크
        if USERS_CSV.exists():
            with open(USERS_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("student_id") == student_id:
                        raise HTTPException(
                            status_code=400, 
                            detail=f"이미 제출된 학번입니다: {student_id}"
                        )
        
        # 2. user_id 생성
        user_id = generate_user_id()
        
        # 3. plan_order 결정 (랜덤 로테이션)
        import random
        plan_order = ["hybrid", "popularity", "personalized"]
        random.shuffle(plan_order)
        
        # 4. input.json 생성 (파이프라인 입력용)
        input_data = {
            "responses": {
                "name": name,
                "studentID": student_id,
                "rank_category": responses.rank_category,
                "keyword_history": responses.keyword_history,
                "keyword_nature": responses.keyword_nature,
                "keyword_food": responses.keyword_food,
                "keyword_activity": responses.keyword_activity,
                "keyword_accomodation": responses.keyword_accomodation,
                "budget": responses.budget
            },
            "timestamp": payload.timestamp or datetime.utcnow().isoformat(),
            "formUrl": payload.formUrl or ""
        }
        
        with open(INPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(input_data, f, ensure_ascii=False, indent=2)
        
        print(f"[INPUT JSON] {student_id} input.json 생성 완료")
        
        # 5. users.csv에 임시 등록 (파이프라인 완료 후 플랜이 생성됨)
        write_header = not USERS_CSV.exists()
        with open(USERS_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["user_id", "name", "student_id", "rotate", "created_at"])
            writer.writerow([
                user_id,
                name,
                student_id,
                json.dumps(plan_order, ensure_ascii=False),
                datetime.utcnow().isoformat()
            ])
        
        print(f"[USER REGISTERED] {user_id} ({name} / {student_id})")
        
        # 6. 백그라운드에서 파이프라인 실행
        background_tasks.add_task(run_pipeline_for_student, student_id)
        
        # 7. 즉시 응답 (백그라운드 작업은 계속 실행됨)
        return {
            "status": "processing",
            "message": f"설문이 제출되었습니다. 여행 플랜을 생성 중입니다.",
            "user_id": user_id,
            "student_id": student_id,
            "name": name,
            "plan_order": plan_order,
            "estimated_time": "약 20-30초 소요됩니다."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] 설문 제출 오류: {e}")
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")


@router.get("/status/{student_id}")
def check_status(student_id: str):
    """
    플랜 생성 상태 확인
    """
    try:
        # users.csv에서 user_id 찾기
        if not USERS_CSV.exists():
            raise HTTPException(status_code=404, detail="등록된 사용자가 없습니다.")
        
        user_id = None
        with open(USERS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("student_id") == student_id:
                    user_id = row.get("user_id")
                    break
        
        if not user_id:
            raise HTTPException(status_code=404, detail="해당 학번을 찾을 수 없습니다.")
        
        # 플랜 파일 존재 여부 확인
        plan_file = PLANS_DIR / f"{user_id}.json"
        
        if plan_file.exists():
            return {
                "status": "completed",
                "message": "플랜 생성이 완료되었습니다.",
                "user_id": user_id,
                "student_id": student_id
            }
        else:
            return {
                "status": "processing",
                "message": "플랜을 생성 중입니다. 잠시만 기다려주세요.",
                "user_id": user_id,
                "student_id": student_id
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")
