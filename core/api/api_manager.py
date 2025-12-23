"""
API 관리 시스템 - .env 파일 자동 관리

기능:
1. API 키 관리 (.env 자동 저장/로드)
2. API 키 실제 검증 (API 호출)
3. API 사용량 추적
4. API 선택 및 설정
5. 비용 계산
"""
import json
import os
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
import threading


# .env 파일 관리
try:
    from dotenv import load_dotenv, set_key, dotenv_values
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


class APIProvider(Enum):
    """API 제공자"""
    ANTHROPIC = "anthropic"      # Claude
    GOOGLE = "google"            # Gemini
    TOGETHER = "together"        # Together.ai (FLUX)
    OPENAI = "openai"            # GPT, DALL-E, Whisper
    ELEVENLABS = "elevenlabs"    # TTS
    YOUTUBE = "youtube"          # YouTube Data API
    EDGE_TTS = "edge_tts"        # Microsoft Edge TTS (무료)


class APIFunction(Enum):
    """API 기능 분류"""
    TEXT_GENERATION = "text_generation"
    IMAGE_GENERATION = "image_generation"
    IMAGE_ANALYSIS = "image_analysis"
    TTS = "tts"
    STT = "stt"
    VIDEO_SEARCH = "video_search"
    TRANSCRIPT = "transcript"


@dataclass
class APIConfig:
    """API 설정"""
    provider: str
    name: str
    model_id: str
    function: str
    is_free: bool = False
    price_per_unit: float = 0.0
    unit_name: str = "request"
    max_requests_per_minute: int = 60
    max_output_tokens: int = 8192  # ⭐ 최대 출력 토큰 수
    description: str = ""
    is_enabled: bool = True


@dataclass
class APIUsageRecord:
    """API 사용 기록"""
    provider: str
    model_id: str
    function: str
    timestamp: str
    tokens_input: int = 0
    tokens_output: int = 0
    units_used: float = 0
    cost_estimate: float = 0.0
    duration_seconds: float = 0.0
    success: bool = True
    error_message: str = ""
    project_name: str = ""
    step_name: str = ""


@dataclass
class APIKeyValidationResult:
    """API 키 검증 결과"""
    valid: bool
    message: str
    details: str = ""
    provider: str = ""


class APIManager:
    """API 중앙 관리자"""

    # .env 파일 경로
    ENV_FILE = Path(__file__).parent.parent.parent / ".env"

    # API 키 환경변수 매핑
    API_KEY_ENV_VARS = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "together": "TOGETHER_API_KEY",
        "google": "GOOGLE_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
        "youtube": "YOUTUBE_API_KEY",
    }

    # 지원하는 API 및 모델 목록
    AVAILABLE_APIS = {
        # === 텍스트 생성 ===
        "claude-sonnet": APIConfig(
            provider="anthropic",
            name="Claude Sonnet 4",
            model_id="claude-sonnet-4-20250514",
            function="text_generation",
            price_per_unit=0.003,
            unit_name="1K tokens",
            description="빠르고 효율적인 분석 및 생성"
        ),
        "claude-opus": APIConfig(
            provider="anthropic",
            name="Claude Opus 4",
            model_id="claude-opus-4-20250514",
            function="text_generation",
            price_per_unit=0.015,
            unit_name="1K tokens",
            description="최고 품질의 분석 및 생성"
        ),
        "claude-haiku": APIConfig(
            provider="anthropic",
            name="Claude Haiku 3.5",
            model_id="claude-3-5-haiku-20241022",
            function="text_generation",
            price_per_unit=0.001,
            unit_name="1K tokens",
            description="빠르고 저렴한 간단한 작업"
        ),
        # ⭐ Gemini 모델들 (정확한 모델명과 출력 토큰 표시)
        "gemini-2.0-flash-exp": APIConfig(
            provider="google",
            name="Gemini 2.0 Flash Exp (64K출력) ⭐추천",
            model_id="gemini-2.0-flash-exp",
            function="text_generation",
            is_free=True,
            max_output_tokens=65536,  # ⭐ 64K 토큰!
            description="최신 실험 모델, 최대 65,536 토큰 출력 (긴 JSON에 최적)"
        ),
        "gemini-2.0-flash": APIConfig(
            provider="google",
            name="Gemini 2.0 Flash (8K출력)",
            model_id="gemini-2.0-flash",
            function="text_generation",
            is_free=True,
            max_output_tokens=8192,
            description="안정적인 Flash 모델, 8,192 토큰 출력"
        ),
        "gemini-1.5-flash": APIConfig(
            provider="google",
            name="Gemini 1.5 Flash (8K출력)",
            model_id="gemini-1.5-flash",
            function="text_generation",
            is_free=True,
            max_output_tokens=8192,
            description="이전 버전 Flash 모델, 8,192 토큰 출력"
        ),
        "gemini-1.5-pro": APIConfig(
            provider="google",
            name="Gemini 1.5 Pro (8K출력)",
            model_id="gemini-1.5-pro",
            function="text_generation",
            price_per_unit=0.00125,
            unit_name="1K tokens",
            max_output_tokens=8192,
            description="고품질 분석, 8,192 토큰 출력"
        ),
        "gpt-4o": APIConfig(
            provider="openai",
            name="GPT-4o",
            model_id="gpt-4o",
            function="text_generation",
            price_per_unit=0.005,
            unit_name="1K tokens",
            description="OpenAI 최신 모델"
        ),
        "gpt-4o-mini": APIConfig(
            provider="openai",
            name="GPT-4o Mini",
            model_id="gpt-4o-mini",
            function="text_generation",
            price_per_unit=0.00015,
            unit_name="1K tokens",
            description="저렴한 GPT-4"
        ),

        # === 이미지 생성 ===
        "flux-free": APIConfig(
            provider="together",
            name="FLUX.1 Schnell (Free)",
            model_id="black-forest-labs/FLUX.1-schnell-Free",
            function="image_generation",
            is_free=True,
            max_requests_per_minute=10,
            description="무료, 분당 10개 제한"
        ),
        "flux-schnell": APIConfig(
            provider="together",
            name="FLUX.1 Schnell",
            model_id="black-forest-labs/FLUX.1-schnell",
            function="image_generation",
            price_per_unit=0.003,
            unit_name="image",
            description="빠른 이미지 생성"
        ),
        "flux-dev": APIConfig(
            provider="together",
            name="FLUX.1 Dev",
            model_id="black-forest-labs/FLUX.1-dev",
            function="image_generation",
            price_per_unit=0.025,
            unit_name="image",
            description="고품질 이미지"
        ),
        "dall-e-3": APIConfig(
            provider="openai",
            name="DALL-E 3",
            model_id="dall-e-3",
            function="image_generation",
            price_per_unit=0.04,
            unit_name="image",
            description="텍스트 포함 이미지에 강함"
        ),
        "dall-e-2": APIConfig(
            provider="openai",
            name="DALL-E 2",
            model_id="dall-e-2",
            function="image_generation",
            price_per_unit=0.02,
            unit_name="image",
            description="저렴한 이미지 생성"
        ),
        "imagen-3": APIConfig(
            provider="google",
            name="Imagen 3",
            model_id="imagen-3.0-generate-001",
            function="image_generation",
            price_per_unit=0.02,
            unit_name="image",
            description="Vertex AI 필요"
        ),

        # === 이미지 분석 ===
        "claude-vision": APIConfig(
            provider="anthropic",
            name="Claude Vision",
            model_id="claude-sonnet-4-20250514",
            function="image_analysis",
            price_per_unit=0.003,
            unit_name="1K tokens",
            description="이미지 분석 및 프롬프트 생성"
        ),
        "gemini-vision": APIConfig(
            provider="google",
            name="Gemini Vision",
            model_id="gemini-2.0-flash-exp",
            function="image_analysis",
            is_free=True,
            description="무료 이미지 분석"
        ),
        "gpt-4-vision": APIConfig(
            provider="openai",
            name="GPT-4 Vision",
            model_id="gpt-4o",
            function="image_analysis",
            price_per_unit=0.005,
            unit_name="1K tokens",
            description="OpenAI 이미지 분석"
        ),

        # === TTS ===
        "edge-tts": APIConfig(
            provider="edge_tts",
            name="Edge TTS",
            model_id="edge-tts",
            function="tts",
            is_free=True,
            description="무료, 다양한 음성"
        ),
        "elevenlabs": APIConfig(
            provider="elevenlabs",
            name="ElevenLabs",
            model_id="eleven_multilingual_v2",
            function="tts",
            price_per_unit=0.00024,
            unit_name="character",
            description="고품질 음성, 음성 복제"
        ),
        "openai-tts": APIConfig(
            provider="openai",
            name="OpenAI TTS",
            model_id="tts-1",
            function="tts",
            price_per_unit=0.015,
            unit_name="1K characters",
            description="자연스러운 음성"
        ),

        # === YouTube ===
        "youtube-data": APIConfig(
            provider="youtube",
            name="YouTube Data API",
            model_id="youtube-data-v3",
            function="video_search",
            is_free=True,
            max_requests_per_minute=100,
            description="비디오 검색, 자막 추출"
        ),
    }

    # 기능별 기본 API
    DEFAULT_APIS = {
        "script_generation": "claude-sonnet",
        "scene_analysis": "claude-sonnet",
        "character_extraction": "claude-sonnet",
        "image_prompt_generation": "claude-haiku",
        "image_generation": "flux-free",
        "image_analysis": "claude-vision",
        "tts": "edge-tts",
        "video_search": "youtube-data",
    }

    def __init__(self):
        self.config_dir = Path("data/config")
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.usage_file = self.config_dir / "api_usage.json"
        self.settings_file = self.config_dir / "api_settings.json"

        self.usage_records: List[APIUsageRecord] = []
        self.settings: Dict = {}
        self._lock = threading.Lock()

        # .env 파일 초기화 및 로드
        self._ensure_env_file()
        self._load_env_file()

        self._load_settings()
        self._load_usage()

    def _ensure_env_file(self):
        """.env 파일이 없으면 생성"""
        if not self.ENV_FILE.exists():
            self.ENV_FILE.parent.mkdir(parents=True, exist_ok=True)

            content = """# Longform Project API Keys
# 이 파일은 자동으로 관리됩니다. 직접 편집해도 됩니다.
# API 키는 보안을 위해 Git에 커밋하지 마세요.

# === Anthropic (Claude) ===
ANTHROPIC_API_KEY=

# === OpenAI (GPT, DALL-E, Whisper) ===
OPENAI_API_KEY=

# === Together.ai (FLUX) ===
TOGETHER_API_KEY=

# === Google (Gemini, Imagen) ===
GOOGLE_API_KEY=

# === ElevenLabs (TTS) ===
ELEVENLABS_API_KEY=

# === YouTube Data API ===
YOUTUBE_API_KEY=
"""
            with open(self.ENV_FILE, "w", encoding="utf-8") as f:
                f.write(content)

    def _load_env_file(self):
        """.env 파일 로드"""
        if HAS_DOTENV and self.ENV_FILE.exists():
            load_dotenv(self.ENV_FILE, override=True)

    def _load_settings(self):
        """설정 로드"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    self.settings = json.load(f)
            except Exception:
                self.settings = {}

        if not self.settings:
            self.settings = {
                "selected_apis": self.DEFAULT_APIS.copy(),
                "api_keys": {},
                "enabled_providers": list(set(api.provider for api in self.AVAILABLE_APIS.values()))
            }
            self._save_settings()

    def _save_settings(self):
        """설정 저장"""
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    def _load_usage(self):
        """사용량 로드"""
        if self.usage_file.exists():
            try:
                with open(self.usage_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.usage_records = [APIUsageRecord(**r) for r in data]
            except Exception:
                self.usage_records = []

    def _save_usage(self):
        """사용량 저장"""
        with self._lock:
            with open(self.usage_file, "w", encoding="utf-8") as f:
                data = [asdict(r) for r in self.usage_records]
                json.dump(data, f, ensure_ascii=False, indent=2)

    # === API 키 관리 (개선됨) ===

    def get_api_key(self, provider: str) -> str:
        """
        API 키 가져오기

        우선순위:
        1. 환경변수
        2. .env 파일
        3. 설정 파일
        """
        env_var = self.API_KEY_ENV_VARS.get(provider)
        if not env_var:
            return ""

        # 1. 환경변수에서 확인
        key = os.environ.get(env_var, "")
        if key:
            return key

        # 2. .env 파일에서 직접 읽기 (환경변수로 로드 안 된 경우)
        if HAS_DOTENV and self.ENV_FILE.exists():
            env_values = dotenv_values(self.ENV_FILE)
            key = env_values.get(env_var, "")
            if key:
                return key

        # 3. 설정 파일에서 확인 (레거시)
        return self.settings.get("api_keys", {}).get(provider, "")

    def set_api_key(self, provider: str, api_key: str) -> bool:
        """
        API 키 저장

        저장 위치:
        1. .env 파일
        2. 현재 세션 환경변수
        3. 설정 파일 (백업)
        """
        env_var = self.API_KEY_ENV_VARS.get(provider)
        if not env_var:
            return False

        try:
            # 1. .env 파일에 저장
            if HAS_DOTENV:
                set_key(str(self.ENV_FILE), env_var, api_key or "")

            # 2. 현재 세션 환경변수에 설정
            if api_key:
                os.environ[env_var] = api_key
            elif env_var in os.environ:
                del os.environ[env_var]

            # 3. 설정 파일에도 저장 (백업)
            self.settings.setdefault("api_keys", {})[provider] = api_key
            self._save_settings()

            return True
        except Exception as e:
            print(f"API 키 저장 실패: {e}")
            return False

    def validate_api_key(self, provider: str) -> APIKeyValidationResult:
        """
        API 키 유효성 검증 (실제 API 호출)

        Returns:
            APIKeyValidationResult with valid, message, details
        """
        key = self.get_api_key(provider)

        if not key:
            return APIKeyValidationResult(
                valid=False,
                message="API 키가 설정되지 않았습니다.",
                details="API 관리 페이지에서 키를 입력하세요.",
                provider=provider
            )

        # 제공자별 검증
        validators = {
            "openai": self._validate_openai_key,
            "together": self._validate_together_key,
            "google": self._validate_google_key,
            "anthropic": self._validate_anthropic_key,
            "elevenlabs": self._validate_elevenlabs_key,
            "youtube": self._validate_youtube_key,
        }

        validator = validators.get(provider)
        if validator:
            return validator(key)

        # 기본: 형식만 확인
        return APIKeyValidationResult(
            valid=True,
            message="키가 설정되어 있습니다.",
            provider=provider
        )

    def _validate_openai_key(self, key: str) -> APIKeyValidationResult:
        """OpenAI API 키 검증"""
        try:
            response = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10
            )

            if response.status_code == 200:
                return APIKeyValidationResult(
                    valid=True,
                    message="유효한 API 키",
                    details="DALL-E 3, GPT-4o 사용 가능",
                    provider="openai"
                )
            elif response.status_code == 401:
                return APIKeyValidationResult(
                    valid=False,
                    message="잘못된 API 키",
                    details="키를 다시 확인하세요.",
                    provider="openai"
                )
            elif response.status_code == 429:
                return APIKeyValidationResult(
                    valid=True,
                    message="요청 한도 초과",
                    details="키는 유효하나 잠시 후 시도하세요.",
                    provider="openai"
                )
            else:
                return APIKeyValidationResult(
                    valid=False,
                    message=f"오류: {response.status_code}",
                    details=response.text[:200],
                    provider="openai"
                )
        except requests.exceptions.Timeout:
            return APIKeyValidationResult(
                valid=False,
                message="연결 시간 초과",
                details="네트워크를 확인하세요.",
                provider="openai"
            )
        except Exception as e:
            return APIKeyValidationResult(
                valid=False,
                message="연결 실패",
                details=str(e),
                provider="openai"
            )

    def _validate_together_key(self, key: str) -> APIKeyValidationResult:
        """Together.ai API 키 검증"""
        try:
            response = requests.get(
                "https://api.together.xyz/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10
            )

            if response.status_code == 200:
                return APIKeyValidationResult(
                    valid=True,
                    message="유효한 API 키",
                    details="FLUX 이미지 생성 사용 가능",
                    provider="together"
                )
            else:
                return APIKeyValidationResult(
                    valid=False,
                    message=f"오류: {response.status_code}",
                    details=response.text[:200],
                    provider="together"
                )
        except Exception as e:
            return APIKeyValidationResult(
                valid=False,
                message="연결 실패",
                details=str(e),
                provider="together"
            )

    def _validate_google_key(self, key: str) -> APIKeyValidationResult:
        """Google API 키 검증"""
        try:
            response = requests.get(
                f"https://generativelanguage.googleapis.com/v1/models?key={key}",
                timeout=10
            )

            if response.status_code == 200:
                return APIKeyValidationResult(
                    valid=True,
                    message="유효한 API 키",
                    details="Gemini 사용 가능. Imagen 3는 Vertex AI 필요.",
                    provider="google"
                )
            elif response.status_code == 400:
                return APIKeyValidationResult(
                    valid=False,
                    message="잘못된 API 키 형식",
                    details="Google AI Studio에서 키를 확인하세요.",
                    provider="google"
                )
            else:
                return APIKeyValidationResult(
                    valid=False,
                    message=f"오류: {response.status_code}",
                    details=response.text[:200],
                    provider="google"
                )
        except Exception as e:
            return APIKeyValidationResult(
                valid=False,
                message="연결 실패",
                details=str(e),
                provider="google"
            )

    def _validate_anthropic_key(self, key: str) -> APIKeyValidationResult:
        """Anthropic API 키 검증"""
        # 형식 검사
        if not key.startswith("sk-ant-"):
            return APIKeyValidationResult(
                valid=False,
                message="잘못된 API 키 형식",
                details="키는 'sk-ant-'로 시작해야 합니다.",
                provider="anthropic"
            )

        # 실제 API 호출로 검증
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}]
                },
                timeout=10
            )

            if response.status_code == 200:
                return APIKeyValidationResult(
                    valid=True,
                    message="유효한 API 키",
                    details="Claude 사용 가능",
                    provider="anthropic"
                )
            elif response.status_code == 401:
                return APIKeyValidationResult(
                    valid=False,
                    message="잘못된 API 키",
                    details="Anthropic Console에서 키를 확인하세요.",
                    provider="anthropic"
                )
            elif response.status_code == 529:  # Overloaded
                return APIKeyValidationResult(
                    valid=True,
                    message="API 과부하",
                    details="키는 유효하나 서버가 바쁩니다.",
                    provider="anthropic"
                )
            else:
                return APIKeyValidationResult(
                    valid=False,
                    message=f"오류: {response.status_code}",
                    details=response.text[:200],
                    provider="anthropic"
                )
        except Exception as e:
            # 형식이 맞으면 일단 유효한 것으로
            return APIKeyValidationResult(
                valid=True,
                message="형식 유효 (연결 확인 필요)",
                details=str(e),
                provider="anthropic"
            )

    def _validate_elevenlabs_key(self, key: str) -> APIKeyValidationResult:
        """ElevenLabs API 키 검증"""
        try:
            response = requests.get(
                "https://api.elevenlabs.io/v1/user",
                headers={"xi-api-key": key},
                timeout=10
            )

            if response.status_code == 200:
                user_data = response.json()
                char_limit = user_data.get("subscription", {}).get("character_limit", 0)
                char_used = user_data.get("subscription", {}).get("character_count", 0)
                return APIKeyValidationResult(
                    valid=True,
                    message="유효한 API 키",
                    details=f"남은 문자: {char_limit - char_used:,}",
                    provider="elevenlabs"
                )
            else:
                return APIKeyValidationResult(
                    valid=False,
                    message=f"오류: {response.status_code}",
                    details=response.text[:200],
                    provider="elevenlabs"
                )
        except Exception as e:
            return APIKeyValidationResult(
                valid=False,
                message="연결 실패",
                details=str(e),
                provider="elevenlabs"
            )

    def _validate_youtube_key(self, key: str) -> APIKeyValidationResult:
        """YouTube API 키 검증"""
        try:
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "key": key,
                    "part": "snippet",
                    "chart": "mostPopular",
                    "maxResults": 1
                },
                timeout=10
            )

            if response.status_code == 200:
                return APIKeyValidationResult(
                    valid=True,
                    message="유효한 API 키",
                    details="YouTube 검색 사용 가능",
                    provider="youtube"
                )
            elif response.status_code == 403:
                error_reason = response.json().get("error", {}).get("errors", [{}])[0].get("reason", "")
                if error_reason == "quotaExceeded":
                    return APIKeyValidationResult(
                        valid=True,
                        message="할당량 초과",
                        details="키는 유효하나 오늘 할당량을 초과했습니다.",
                        provider="youtube"
                    )
                return APIKeyValidationResult(
                    valid=False,
                    message="API 미활성화",
                    details="Google Cloud Console에서 YouTube Data API를 활성화하세요.",
                    provider="youtube"
                )
            else:
                return APIKeyValidationResult(
                    valid=False,
                    message=f"오류: {response.status_code}",
                    details=response.text[:200],
                    provider="youtube"
                )
        except Exception as e:
            return APIKeyValidationResult(
                valid=False,
                message="연결 실패",
                details=str(e),
                provider="youtube"
            )

    def has_api_key(self, provider: str) -> bool:
        """API 키 존재 여부 확인 (빠른 체크)"""
        return bool(self.get_api_key(provider))

    def get_all_api_key_status(self) -> Dict[str, bool]:
        """모든 API 키 상태"""
        return {
            provider: self.has_api_key(provider)
            for provider in self.API_KEY_ENV_VARS.keys()
        }

    # === API 선택 ===

    def get_available_apis_for_function(self, function: str) -> List[APIConfig]:
        """특정 기능에 사용 가능한 API 목록"""
        return [
            api for api in self.AVAILABLE_APIS.values()
            if api.function == function and api.is_enabled
        ]

    def get_selected_api(self, task: str) -> Optional[APIConfig]:
        """선택된 API 가져오기"""
        api_id = self.settings.get("selected_apis", {}).get(task)
        if api_id and api_id in self.AVAILABLE_APIS:
            return self.AVAILABLE_APIS[api_id]
        return None

    def set_selected_api(self, task: str, api_id: str):
        """API 선택"""
        if api_id in self.AVAILABLE_APIS:
            self.settings.setdefault("selected_apis", {})[task] = api_id
            self._save_settings()

    def get_api_by_id(self, api_id: str) -> Optional[APIConfig]:
        """ID로 API 가져오기"""
        return self.AVAILABLE_APIS.get(api_id)

    # === 사용량 추적 ===

    def record_usage(self,
                     provider: str,
                     model_id: str,
                     function: str,
                     tokens_input: int = 0,
                     tokens_output: int = 0,
                     units_used: float = 0,
                     duration_seconds: float = 0,
                     success: bool = True,
                     error_message: str = "",
                     project_name: str = "",
                     step_name: str = ""):
        """API 사용 기록"""

        api_config = None
        for api in self.AVAILABLE_APIS.values():
            if api.provider == provider and api.model_id == model_id:
                api_config = api
                break

        cost = 0.0
        if api_config and not api_config.is_free:
            if "token" in api_config.unit_name.lower():
                cost = (tokens_input + tokens_output) / 1000 * api_config.price_per_unit
            else:
                cost = units_used * api_config.price_per_unit

        record = APIUsageRecord(
            provider=provider,
            model_id=model_id,
            function=function,
            timestamp=datetime.now().isoformat(),
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            units_used=units_used,
            cost_estimate=cost,
            duration_seconds=duration_seconds,
            success=success,
            error_message=error_message,
            project_name=project_name,
            step_name=step_name
        )

        with self._lock:
            self.usage_records.append(record)

        self._save_usage()
        return record

    def get_usage_summary(self,
                          start_date: datetime = None,
                          end_date: datetime = None,
                          provider: str = None) -> Dict:
        """사용량 요약"""

        records = self.usage_records

        if start_date:
            records = [r for r in records
                      if datetime.fromisoformat(r.timestamp) >= start_date]
        if end_date:
            records = [r for r in records
                      if datetime.fromisoformat(r.timestamp) <= end_date]
        if provider:
            records = [r for r in records if r.provider == provider]

        summary = {
            "total_requests": len(records),
            "successful_requests": sum(1 for r in records if r.success),
            "failed_requests": sum(1 for r in records if not r.success),
            "total_cost": sum(r.cost_estimate for r in records),
            "total_tokens_input": sum(r.tokens_input for r in records),
            "total_tokens_output": sum(r.tokens_output for r in records),
            "total_duration": sum(r.duration_seconds for r in records),
            "by_provider": {},
            "by_function": {},
            "by_date": {},
        }

        for r in records:
            if r.provider not in summary["by_provider"]:
                summary["by_provider"][r.provider] = {"requests": 0, "cost": 0, "tokens": 0}
            summary["by_provider"][r.provider]["requests"] += 1
            summary["by_provider"][r.provider]["cost"] += r.cost_estimate
            summary["by_provider"][r.provider]["tokens"] += r.tokens_input + r.tokens_output

        for r in records:
            if r.function not in summary["by_function"]:
                summary["by_function"][r.function] = {"requests": 0, "cost": 0}
            summary["by_function"][r.function]["requests"] += 1
            summary["by_function"][r.function]["cost"] += r.cost_estimate

        for r in records:
            date = r.timestamp[:10]
            if date not in summary["by_date"]:
                summary["by_date"][date] = {"requests": 0, "cost": 0}
            summary["by_date"][date]["requests"] += 1
            summary["by_date"][date]["cost"] += r.cost_estimate

        return summary

    def get_recent_usage(self, limit: int = 100) -> List[APIUsageRecord]:
        """최근 사용 기록"""
        return sorted(self.usage_records, key=lambda r: r.timestamp, reverse=True)[:limit]

    def get_error_logs(self, limit: int = 50) -> List[APIUsageRecord]:
        """에러 로그"""
        errors = [r for r in self.usage_records if not r.success]
        return sorted(errors, key=lambda r: r.timestamp, reverse=True)[:limit]

    def clear_usage_history(self, before_date: datetime = None):
        """사용 기록 삭제"""
        if before_date:
            self.usage_records = [
                r for r in self.usage_records
                if datetime.fromisoformat(r.timestamp) >= before_date
            ]
        else:
            self.usage_records = []
        self._save_usage()


# 싱글톤 인스턴스
_api_manager = None

def get_api_manager() -> APIManager:
    """API 매니저 싱글톤"""
    global _api_manager
    if _api_manager is None:
        _api_manager = APIManager()
    return _api_manager
