"""
Video API 설정 - 플랫폼별 모델 카탈로그
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from pathlib import Path
import os


# 프로젝트 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STATE_FILE = DATA_DIR / "video_api_state.json"


class VideoType(Enum):
    """영상 생성 유형"""
    TEXT_TO_VIDEO = "t2v"
    IMAGE_TO_VIDEO = "i2v"
    BOTH = "both"


class SpeedTier(Enum):
    """속도 등급"""
    FAST = "fast"       # < 1분
    MEDIUM = "medium"   # 1-3분
    SLOW = "slow"       # > 3분


class QualityTier(Enum):
    """품질 등급"""
    GOOD = 3
    GREAT = 4
    BEST = 5


@dataclass
class VideoModelConfig:
    """영상 모델 설정"""
    model_id: str                    # API에서 사용하는 모델 ID
    display_name: str                # UI 표시명
    platform: str                    # fal_ai, replicate, pixverse
    video_type: VideoType            # t2v, i2v, both

    # 해상도 옵션
    resolutions: List[str] = field(default_factory=lambda: ["720p"])
    default_resolution: str = "720p"

    # 길이 옵션
    durations: List[int] = field(default_factory=lambda: [5])
    default_duration: int = 5

    # 가격 (USD)
    price_per_second: Optional[float] = None    # 초당 가격
    price_per_video: Optional[float] = None     # 영상당 고정 가격
    credits_per_video: Optional[int] = None     # 크레딧 기반 (PixVerse)

    # 메타데이터
    speed: SpeedTier = SpeedTier.MEDIUM
    quality: QualityTier = QualityTier.GREAT
    has_audio: bool = False
    watermark: bool = False
    commercial_use: bool = True
    legal_warning: Optional[str] = None

    # 추가 파라미터
    supports_negative_prompt: bool = False
    supports_seed: bool = True
    max_prompt_length: int = 500


# ============================================================
# fal.ai 모델 카탈로그
# ============================================================

FAL_MODELS: Dict[str, VideoModelConfig] = {
    # === 가장 저렴 & 빠름 ===
    # ⭐ v2.3: 올바른 fal.ai 모델 경로로 수정 (404 에러 수정)
    "wan_i2v": VideoModelConfig(
        model_id="fal-ai/wan-i2v",  # ✅ 올바른 경로 (기존: fal-ai/wan/v2.1/image-to-video)
        display_name="Wan 2.1 I2V (가장 저렴)",
        platform="fal_ai",
        video_type=VideoType.IMAGE_TO_VIDEO,
        resolutions=["480p", "720p"],
        default_resolution="480p",
        durations=[5],
        default_duration=5,
        price_per_video=0.10,
        speed=SpeedTier.FAST,
        quality=QualityTier.GREAT,
        supports_negative_prompt=True,
    ),
    "wan_t2v": VideoModelConfig(
        model_id="fal-ai/wan-t2v",  # ✅ 올바른 경로 (기존: fal-ai/wan/v2.1/text-to-video)
        display_name="Wan 2.1 T2V (가장 저렴)",
        platform="fal_ai",
        video_type=VideoType.TEXT_TO_VIDEO,
        resolutions=["480p", "720p"],
        default_resolution="480p",
        durations=[5],
        default_duration=5,
        price_per_video=0.10,
        speed=SpeedTier.FAST,
        quality=QualityTier.GREAT,
    ),

    # === 고품질 ===
    "hailuo_std": VideoModelConfig(
        model_id="fal-ai/minimax/video-01/image-to-video",
        display_name="Hailuo Standard (768p)",
        platform="fal_ai",
        video_type=VideoType.IMAGE_TO_VIDEO,
        resolutions=["512p", "768p"],
        default_resolution="768p",
        durations=[6],
        default_duration=6,
        price_per_second=0.045,
        speed=SpeedTier.MEDIUM,
        quality=QualityTier.BEST,
        legal_warning="MiniMax 저작권 소송 진행 중 - 상업적 사용 주의",
    ),
    "kling_pro": VideoModelConfig(
        model_id="fal-ai/kling-video/v1.6/pro/image-to-video",
        display_name="Kling 1.6 Pro",
        platform="fal_ai",
        video_type=VideoType.IMAGE_TO_VIDEO,
        resolutions=["720p", "1080p"],
        default_resolution="1080p",
        durations=[5, 10],
        default_duration=5,
        price_per_second=0.07,
        speed=SpeedTier.MEDIUM,
        quality=QualityTier.BEST,
        has_audio=False,
    ),

    # === 최고 품질 ===
    "hunyuan": VideoModelConfig(
        model_id="fal-ai/hunyuan-video",
        display_name="HunyuanVideo (Tencent)",
        platform="fal_ai",
        video_type=VideoType.TEXT_TO_VIDEO,
        resolutions=["544p", "720p"],
        default_resolution="720p",
        durations=[5],
        default_duration=5,
        price_per_video=0.40,
        speed=SpeedTier.SLOW,
        quality=QualityTier.GREAT,
    ),
    "ltx": VideoModelConfig(
        model_id="fal-ai/ltx-video/image-to-video",
        display_name="LTX Video I2V",
        platform="fal_ai",
        video_type=VideoType.IMAGE_TO_VIDEO,
        resolutions=["480p", "720p"],
        default_resolution="720p",
        durations=[5],
        default_duration=5,
        price_per_video=0.05,
        speed=SpeedTier.FAST,
        quality=QualityTier.GOOD,
    ),
}


# ============================================================
# Replicate 모델 카탈로그
# ============================================================

REPLICATE_MODELS: Dict[str, VideoModelConfig] = {
    # === 가장 저렴 & 빠름 ===
    # ⭐ v2.3: 올바른 Replicate 모델 경로로 수정 (모델 not found 에러 수정)
    "wan_i2v": VideoModelConfig(
        model_id="wavespeedai/wan-2.1-i2v-480p",  # ✅ 수정됨 (기존: wavymulder/wan-2.1-i2v)
        display_name="Wan 2.1 I2V (가장 저렴)",
        platform="replicate",
        video_type=VideoType.IMAGE_TO_VIDEO,
        resolutions=["480p", "720p"],
        default_resolution="480p",
        durations=[5],
        default_duration=5,
        price_per_video=0.07,  # 가격 업데이트
        speed=SpeedTier.FAST,
        quality=QualityTier.GREAT,
    ),
    "wan_t2v": VideoModelConfig(
        model_id="wavespeedai/wan-2.1-t2v-480p",  # ✅ 수정됨 (기존: wavymulder/wan-2.1-t2v)
        display_name="Wan 2.1 T2V (가장 저렴)",
        platform="replicate",
        video_type=VideoType.TEXT_TO_VIDEO,
        resolutions=["480p", "720p"],
        default_resolution="480p",
        durations=[5],
        default_duration=5,
        price_per_video=0.07,  # 가격 업데이트
        speed=SpeedTier.FAST,
        quality=QualityTier.GREAT,
    ),

    # === 고품질 ===
    "minimax_i2v": VideoModelConfig(
        model_id="minimax/video-01",
        display_name="MiniMax Video-01",
        platform="replicate",
        video_type=VideoType.IMAGE_TO_VIDEO,
        resolutions=["720p"],
        default_resolution="720p",
        durations=[6],
        default_duration=6,
        price_per_video=0.35,
        speed=SpeedTier.MEDIUM,
        quality=QualityTier.BEST,
        legal_warning="MiniMax 저작권 소송 진행 중",
    ),
    "luma_ray": VideoModelConfig(
        model_id="luma/ray",
        display_name="Luma Ray",
        platform="replicate",
        video_type=VideoType.BOTH,
        resolutions=["540p", "720p"],
        default_resolution="720p",
        durations=[5],
        default_duration=5,
        price_per_video=0.50,
        speed=SpeedTier.MEDIUM,
        quality=QualityTier.BEST,
    ),
    "haiper": VideoModelConfig(
        model_id="haiper-ai/haiper-video-2-image-to-video",  # ✅ 수정됨 (기존: haiper-ai/haiper-video-2)
        display_name="Haiper Video 2",
        platform="replicate",
        video_type=VideoType.IMAGE_TO_VIDEO,  # I2V 전용으로 변경
        resolutions=["720p"],
        default_resolution="720p",
        durations=[4, 6],
        default_duration=4,
        price_per_video=0.10,
        speed=SpeedTier.FAST,
        quality=QualityTier.GREAT,
    ),
    "hunyuan": VideoModelConfig(
        model_id="tencent/hunyuan-video",
        display_name="HunyuanVideo",
        platform="replicate",
        video_type=VideoType.TEXT_TO_VIDEO,
        resolutions=["720p"],
        default_resolution="720p",
        durations=[5],
        default_duration=5,
        price_per_video=0.30,
        speed=SpeedTier.SLOW,
        quality=QualityTier.GREAT,
    ),
}


# ============================================================
# PixVerse 공식 API 모델 카탈로그
# ============================================================

PIXVERSE_MODELS: Dict[str, VideoModelConfig] = {
    "v4.5": VideoModelConfig(
        model_id="v4.5",
        display_name="PixVerse v4.5 (I2V)",
        platform="pixverse",
        video_type=VideoType.IMAGE_TO_VIDEO,
        resolutions=["720p"],
        default_resolution="720p",
        durations=[5],
        default_duration=5,
        credits_per_video=20,
        speed=SpeedTier.FAST,
        quality=QualityTier.GREAT,
        watermark=True,
    ),
    "v5": VideoModelConfig(
        model_id="v5",
        display_name="PixVerse v5 (T2V)",
        platform="pixverse",
        video_type=VideoType.TEXT_TO_VIDEO,
        resolutions=["540p", "720p", "1080p"],
        default_resolution="720p",
        durations=[5],
        default_duration=5,
        credits_per_video=25,
        speed=SpeedTier.MEDIUM,
        quality=QualityTier.GREAT,
        watermark=True,
    ),
}


# ============================================================
# 통합 카탈로그
# ============================================================

ALL_MODELS: Dict[str, Dict[str, VideoModelConfig]] = {
    "fal_ai": FAL_MODELS,
    "replicate": REPLICATE_MODELS,
    "pixverse": PIXVERSE_MODELS,
}


# ============================================================
# 플랫폼 설정
# ============================================================

PLATFORM_CONFIGS: Dict[str, Dict[str, Any]] = {
    "fal_ai": {
        "name": "fal_ai",
        "display_name": "fal.ai",
        "base_url": "https://fal.run",
        "auth_header": "Authorization",
        "auth_prefix": "Key ",
        "env_key": "FAL_KEY",
        "initial_credits_usd": 10.0,
        "supports_balance_check": False,
    },
    "replicate": {
        "name": "replicate",
        "display_name": "Replicate",
        "base_url": "https://api.replicate.com/v1",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "env_key": "REPLICATE_API_TOKEN",
        "initial_credits_usd": 0.0,
        "supports_balance_check": False,
    },
    "pixverse": {
        "name": "pixverse",
        "display_name": "PixVerse",
        "base_url": "https://app-api.pixverse.ai/openapi/v2",
        "auth_header": "API-KEY",
        "auth_prefix": "",
        "env_key": "PIXVERSE_API_KEY",
        "initial_credits": 90,
        "daily_credits": 60,
        "supports_balance_check": True,
    },
}


# ============================================================
# 추천 모델 (빠른 선택용)
# ============================================================

RECOMMENDED_MODELS: Dict[str, Dict[str, str]] = {
    "cheapest": {
        "fal_ai": "wan_i2v",
        "replicate": "wan_i2v",
        "pixverse": "v4.5",
    },
    "fastest": {
        "fal_ai": "wan_i2v",
        "replicate": "wan_i2v",
        "pixverse": "v4.5",
    },
    "best_quality": {
        "fal_ai": "hailuo_std",
        "replicate": "luma_ray",
        "pixverse": "v5",
    },
    "balanced": {
        "fal_ai": "wan_i2v",
        "replicate": "haiper",
        "pixverse": "v5",
    },
}


# ============================================================
# 기본 설정
# ============================================================

DEFAULT_VIDEO_DURATION = 5
DEFAULT_RESOLUTION = "720p"
DEFAULT_ASPECT_RATIO = "16:9"
REQUEST_TIMEOUT = 300  # 5분
MAX_RETRIES = 3
RETRY_DELAY = 5


# ============================================================
# 유틸리티 함수
# ============================================================

def get_api_key(env_key: str) -> Optional[str]:
    """환경변수에서 API 키 로드"""
    return os.getenv(env_key)


def has_api_key(env_key: str) -> bool:
    """API 키가 설정되어 있는지 확인"""
    key = os.getenv(env_key)
    return bool(key and len(key) > 0)


def get_available_platforms() -> List[str]:
    """API 키가 설정된 플랫폼 목록"""
    available = []
    for platform, config in PLATFORM_CONFIGS.items():
        if has_api_key(config["env_key"]):
            available.append(platform)
    return available


def get_model_config(platform: str, model_key: str) -> Optional[VideoModelConfig]:
    """특정 모델 설정 가져오기"""
    if platform in ALL_MODELS and model_key in ALL_MODELS[platform]:
        return ALL_MODELS[platform][model_key]
    return None


def get_models_by_type(video_type: str, platform: Optional[str] = None) -> Dict[str, Dict[str, VideoModelConfig]]:
    """비디오 유형별 모델 필터링"""
    result = {}

    platforms = [platform] if platform else ALL_MODELS.keys()

    for p in platforms:
        if p not in ALL_MODELS:
            continue

        result[p] = {}
        for key, model in ALL_MODELS[p].items():
            if video_type == "i2v" and model.video_type in [VideoType.IMAGE_TO_VIDEO, VideoType.BOTH]:
                result[p][key] = model
            elif video_type == "t2v" and model.video_type in [VideoType.TEXT_TO_VIDEO, VideoType.BOTH]:
                result[p][key] = model

    return result
