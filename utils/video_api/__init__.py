"""
Video API 시스템

멀티 플랫폼/멀티 모델 영상 생성 API 통합 시스템
- fal.ai, Replicate, PixVerse 지원
- 모델별 비용 추정
- 사용량 추적 및 통계
"""

from .config import (
    VideoModelConfig,
    VideoType,
    SpeedTier,
    QualityTier,
    FAL_MODELS,
    REPLICATE_MODELS,
    PIXVERSE_MODELS,
    ALL_MODELS,
    PLATFORM_CONFIGS,
    RECOMMENDED_MODELS,
    get_api_key,
)

from .models import (
    VideoGenerationRequest,
    VideoGenerationResult,
    CostEstimate,
    PlatformBalance,
    UsageStatistics,
    UsageRecord,
    APIQuotaStatus,
    APIState,
)

from .cost_calculator import CostCalculator

from .quota_manager import QuotaManager

from .api_clients import (
    BaseVideoAPIClient,
    FalAIClient,
    ReplicateClient,
    PixVerseClient,
    get_client,
    CLIENT_MAP,
)

from .rotator import (
    VideoAPIRotator,
    get_rotator,
    generate_video,
    generate_video_sync,
)

__all__ = [
    # Config
    "VideoModelConfig",
    "VideoType",
    "SpeedTier",
    "QualityTier",
    "FAL_MODELS",
    "REPLICATE_MODELS",
    "PIXVERSE_MODELS",
    "ALL_MODELS",
    "PLATFORM_CONFIGS",
    "RECOMMENDED_MODELS",
    "get_api_key",
    # Models
    "VideoGenerationRequest",
    "VideoGenerationResult",
    "CostEstimate",
    "PlatformBalance",
    "UsageStatistics",
    "UsageRecord",
    "APIQuotaStatus",
    "APIState",
    # Cost Calculator
    "CostCalculator",
    # Quota Manager
    "QuotaManager",
    # Clients
    "BaseVideoAPIClient",
    "FalAIClient",
    "ReplicateClient",
    "PixVerseClient",
    "get_client",
    "CLIENT_MAP",
    # Rotator
    "VideoAPIRotator",
    "get_rotator",
    "generate_video",
    "generate_video_sync",
]
