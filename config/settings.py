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
# FLUX.2 모델 (합리적 가격) - 2024년 12월 기준
TOGETHER_DEFAULT_MODEL = "black-forest-labs/FLUX.2-dev"  # $0.0154/장 (~20원)
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

# === 이미지 생성 모델 목록 (FLUX.2 - 합리적 가격) ===
IMAGE_MODELS = [
    {"id": "black-forest-labs/FLUX.2-dev", "name": "FLUX.2 Dev (권장)", "price": 0.0154},  # ~20원/장
    {"id": "black-forest-labs/FLUX.2-flex", "name": "FLUX.2 Flex", "price": 0.03},  # ~40원/장
    {"id": "black-forest-labs/FLUX.2-pro", "name": "FLUX.2 Pro (고품질)", "price": 0.03},  # ~40원/장
]

# === 보안 저장소 경로 ===
SECRETS_DIR = DATA_DIR / ".secrets"
SECRETS_DIR.mkdir(parents=True, exist_ok=True)

# === Google ImageFX (Imagen) 설정 ===
# 쿠키는 환경변수 또는 보안 저장소 파일에서 로드
def _load_imagefx_cookie() -> str:
    """ImageFX 쿠키 로드 (환경변수 > 파일 순서)"""
    # 1. 환경변수에서 먼저 확인
    env_cookie = get_api_key("IMAGEFX_COOKIE")
    if env_cookie:
        return env_cookie

    # 2. 저장된 파일에서 확인
    cookie_file = SECRETS_DIR / "imagefx_cookie.txt"
    if cookie_file.exists():
        try:
            cookie_value = cookie_file.read_text(encoding="utf-8").strip()
            if cookie_value:
                return cookie_value
        except Exception:
            pass

    return None

IMAGEFX_COOKIE = _load_imagefx_cookie()

# ImageFX 모델 목록
IMAGEFX_MODELS = [
    {"id": "IMAGEN_4", "name": "Imagen 4 (최신)", "description": "가장 높은 품질", "price": 0},
    {"id": "IMAGEN_3_5", "name": "Imagen 3.5", "description": "빠른 생성", "price": 0},
    {"id": "IMAGEN_3_1", "name": "Imagen 3.1", "description": "안정적", "price": 0},
    {"id": "IMAGEN_3", "name": "Imagen 3.0", "description": "기본", "price": 0},
]

# ImageFX 비율 목록
IMAGEFX_ASPECT_RATIOS = [
    {"id": "LANDSCAPE_16_9", "name": "16:9 (가로)", "resolution": "1280x720", "width": 1280, "height": 720},
    {"id": "PORTRAIT_16_9", "name": "9:16 (세로)", "resolution": "720x1280", "width": 720, "height": 1280},
    {"id": "LANDSCAPE", "name": "4:3 (가로)", "resolution": "1024x768", "width": 1024, "height": 768},
    {"id": "PORTRAIT", "name": "3:4 (세로)", "resolution": "768x1024", "width": 768, "height": 1024},
    {"id": "SQUARE", "name": "1:1 (정사각형)", "resolution": "1024x1024", "width": 1024, "height": 1024},
]

# ImageFX 기본 설정
IMAGEFX_DEFAULT_MODEL = "IMAGEN_4"
IMAGEFX_DEFAULT_ASPECT_RATIO = "LANDSCAPE_16_9"
IMAGEFX_DEFAULT_NUM_IMAGES = 4
IMAGEFX_TIMEOUT = 120
IMAGEFX_RETRY_COUNT = 3

# ImageFX 쿠키 관련 설정 (NextAuth 지원)
# NextAuth 세션 토큰 (labs.google에서 사용) - 권장
IMAGEFX_REQUIRED_COOKIES = [
    "__Secure-next-auth.session-token",  # NextAuth 세션 (주요)
]

IMAGEFX_OPTIONAL_COOKIES = [
    "__Host-next-auth.csrf-token",       # CSRF 토큰
    "__Secure-next-auth.callback-url",   # 콜백 URL
]

# 대체 인증 (Google 계정 쿠키) - 일부 환경에서 사용
IMAGEFX_FALLBACK_COOKIES = [
    "__Secure-1PSID",
    "__Secure-3PSID",
]

# ImageFX Authorization 토큰 파일 경로
IMAGEFX_TOKEN_FILE = SECRETS_DIR / "imagefx_token.txt"


def save_imagefx_auth_token(token: str) -> bool:
    """ImageFX Authorization 토큰 저장"""
    try:
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        # Bearer 접두사 제거 후 저장
        clean_token = token.strip()
        if clean_token.lower().startswith("bearer "):
            clean_token = clean_token[7:].strip()
        IMAGEFX_TOKEN_FILE.write_text(clean_token, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[Settings] 토큰 저장 실패: {e}")
        return False


def load_imagefx_auth_token() -> str:
    """ImageFX Authorization 토큰 로드"""
    # 1. 환경 변수 먼저 확인
    env_token = os.getenv("IMAGEFX_AUTH_TOKEN", "").strip()
    if env_token:
        return env_token

    # 2. 파일에서 로드
    if IMAGEFX_TOKEN_FILE.exists():
        try:
            token = IMAGEFX_TOKEN_FILE.read_text(encoding="utf-8").strip()
            if token:
                return token
        except Exception:
            pass

    return ""


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
