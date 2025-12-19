"""
AI Longform YouTube Tool - Settings

환경 변수 로드 및 앱 설정
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# === 경로 설정 ===
ROOT_DIR = Path(__file__).parent.parent
ENV_PATH = ROOT_DIR / ".env"
DATA_DIR = ROOT_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
CACHE_DIR = DATA_DIR / "cache"

# .env 로드 (파일이 있을 때만)
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()  # 시스템 환경변수에서 시도

# 폴더 자동 생성
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# === API Key 유틸리티 ===
def get_api_key(key_name: str) -> str:
    """
    환경변수에서 API 키 가져오기

    빈 문자열이나 공백만 있는 경우 None 반환
    """
    value = os.getenv(key_name, "").strip()
    return value if value else None


# === API Keys ===
YOUTUBE_API_KEY = get_api_key("YOUTUBE_API_KEY")
ANTHROPIC_API_KEY = get_api_key("ANTHROPIC_API_KEY")
TOGETHER_API_KEY = get_api_key("TOGETHER_API_KEY")
GEMINI_API_KEY = get_api_key("GEMINI_API_KEY")
# Google API Key (GEMINI_API_KEY의 별칭으로도 사용)
GOOGLE_API_KEY = get_api_key("GOOGLE_API_KEY") or GEMINI_API_KEY


# === API 키 상태 확인 함수 ===
def check_api_keys() -> dict:
    """
    모든 API 키 상태 확인

    Returns:
        {"YOUTUBE_API_KEY": True/False, ...}
    """
    return {
        "YOUTUBE_API_KEY": bool(YOUTUBE_API_KEY),
        "ANTHROPIC_API_KEY": bool(ANTHROPIC_API_KEY),
        "TOGETHER_API_KEY": bool(TOGETHER_API_KEY),
        "GEMINI_API_KEY": bool(GEMINI_API_KEY),
        "GOOGLE_API_KEY": bool(GOOGLE_API_KEY)
    }


def get_missing_keys(required_keys: list = None) -> list:
    """
    설정되지 않은 API 키 목록

    Args:
        required_keys: 확인할 키 목록 (None이면 필수 키만)

    Returns:
        누락된 키 이름 리스트
    """
    if required_keys is None:
        required_keys = ["YOUTUBE_API_KEY", "ANTHROPIC_API_KEY", "TOGETHER_API_KEY"]

    status = check_api_keys()
    return [key for key in required_keys if not status.get(key, False)]


# === app.py 호환성을 위한 별칭 ===
def validate_api_keys() -> dict:
    """
    API 키 유효성 검증 (check_api_keys의 별칭)

    Returns:
        {"YOUTUBE_API_KEY": True/False, ...}
    """
    return check_api_keys()


def get_missing_api_keys() -> list:
    """
    설정되지 않은 필수 API 키 목록 (get_missing_keys의 별칭)

    Returns:
        누락된 키 이름 리스트
    """
    return get_missing_keys()


def is_env_file_exists() -> bool:
    """
    .env 파일 존재 여부 확인
    """
    return ENV_PATH.exists()


# === YouTube API 설정 ===
YOUTUBE_DAILY_QUOTA = 10000
YOUTUBE_SEARCH_COST = 100
YOUTUBE_VIDEO_COST = 1
YOUTUBE_CHANNEL_COST = 1
YOUTUBE_COMMENT_COST = 1

# === Claude API 설정 ===
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 8000

# === Together.ai 설정 ===
TOGETHER_DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell-Free"
# FLUX 모델 제한: width/height 64~1792
TOGETHER_IMAGE_WIDTH = 1792  # max 1792
TOGETHER_IMAGE_HEIGHT = 1024  # 16:9 비율에 가까움

# === TTS 설정 ===
TTS_DEFAULT_RATE = "-10%"
TTS_DEFAULT_SILENCE_MS = 1500

# === 세그먼트 그룹화 설정 ===
DEFAULT_SEGMENTS_PER_GROUP = 4
MIN_GROUP_DURATION_SEC = 8.0
MAX_GROUP_DURATION_SEC = 25.0

# === 스크립트 설정 ===
DEFAULT_SCRIPT_LENGTH_MINUTES = 15
WORDS_PER_MINUTE = 250

# === 언어 설정 ===
SUPPORTED_LANGUAGES = {
    "ko": "한국어",
    "ja": "일본어"
}

# === TTS 음성 목록 ===
TTS_VOICES = {
    "ko": [
        {"id": "ko-KR-SunHiNeural", "name": "선희 (여성)", "gender": "female"},
        {"id": "ko-KR-InJoonNeural", "name": "인준 (남성)", "gender": "male"},
        {"id": "ko-KR-HyunsuNeural", "name": "현수 (남성)", "gender": "male"},
    ],
    "ja": [
        {"id": "ja-JP-NanamiNeural", "name": "나나미 (여성)", "gender": "female"},
        {"id": "ja-JP-KeitaNeural", "name": "케이타 (남성)", "gender": "male"},
        {"id": "ja-JP-AoiNeural", "name": "아오이 (여성)", "gender": "female"},
    ]
}

# === 이미지 생성 모델 목록 ===
IMAGE_MODELS = [
    {"id": "black-forest-labs/FLUX.1-schnell-Free", "name": "FLUX Free", "price": 0},
    {"id": "black-forest-labs/FLUX.1-schnell", "name": "FLUX Schnell", "price": 0.003},
    {"id": "black-forest-labs/FLUX.1.1-pro", "name": "FLUX Pro", "price": 0.04},
]

# === 씬 분석 설정 ===
SCENE_MIN_DURATION = 5  # 최소 씬 길이 (초)
SCENE_MAX_DURATION = 15  # 최대 씬 길이 (초)
SCENE_TARGET_CHARS = 100  # 씬당 목표 글자 수

# === 캐릭터 설정 ===
CHARACTER_IMAGE_SIZE = (1024, 1024)  # 캐릭터 이미지 기본 크기
CHARACTER_BATCH_DELAY = 6  # 캐릭터 배치 생성 시 대기 시간 (초)

# === 프리셋 설정 ===
PRESET_GLOBAL_PATH = DATA_DIR / "presets"
PRESET_GLOBAL_PATH.mkdir(parents=True, exist_ok=True)

# === 콘텐츠 유형 ===
CONTENT_TYPES = [
    "브랜드 역사",
    "인물 스토리",
    "상식/교양",
    "뉴스/시사",
    "기타"
]
