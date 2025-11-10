from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from routers import survey, plans
from pathlib import Path

app = FastAPI(
    title="Travel Plan Generator",
    description="설문 기반 3가지 여행 플랜 생성 API",
    version="0.1.0"
)

# CORS 설정 (구글폼에서 API 호출 가능하도록)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인 허용 (프로덕션에서는 특정 도메인만 허용 권장)
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# 디렉토리 설정
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PLANS_DIR = DATA_DIR / "plans"
STATIC_DIR = BASE_DIR / "static"

DATA_DIR.mkdir(exist_ok=True)
PLANS_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)  # index.html 넣어둘 곳

# 라우터 등록
app.include_router(survey.router, prefix="/survey", tags=["Survey"])
app.include_router(plans.router, prefix="/plans", tags=["Plans"])

# 정적 파일 서빙: /static/* → static 디렉토리
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# 1) 루트에서 바로 프론트 보여주고 싶으면:
@app.get("/", include_in_schema=False)
def serve_front():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    # index.html 없을 때만 상태 확인용 메시지
    return {"message": "Travel Plan API is running. Put index.html in /static to enable UI."}


# 2) 혹시 API 루트는 JSON, 프론트는 /viewer 로 쓰고 싶으면 이거 쓰면 됨:
# @app.get("/", tags=["Health"])
# def read_root():
#     return {"message": "Travel Plan API is running"}
#
# @app.get("/viewer", include_in_schema=False)
# def serve_front():
#     return FileResponse(STATIC_DIR / "index.html")
