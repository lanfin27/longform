"""
Video API 데이터 모델
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import json


class VideoStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoQuality(str, Enum):
    LOW = "480p"
    MEDIUM = "720p"
    HIGH = "1080p"
    ULTRA = "4k"


@dataclass
class VideoGenerationRequest:
    """영상 생성 요청"""
    prompt: str

    # 이미지 입력 (I2V용)
    image_path: Optional[str] = None
    image_url: Optional[str] = None

    # 플랫폼 & 모델 선택
    platform: Optional[str] = None         # fal_ai, replicate, pixverse
    model_key: Optional[str] = None        # config.py의 모델 키

    # 영상 설정
    duration: int = 5
    resolution: str = "720p"
    aspect_ratio: str = "16:9"

    # 추가 옵션
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    enable_audio: bool = False

    # 레거시 호환
    preferred_api: Optional[str] = None
    allow_watermark: bool = True
    commercial_use: bool = False

    # 저장 옵션
    save_locally: bool = True
    output_dir: Optional[str] = None

    # 예산 제한
    max_cost_usd: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VideoGenerationResult:
    """영상 생성 결과"""
    success: bool
    api_used: str  # 레거시 호환

    # 성공 시
    video_url: Optional[str] = None
    local_path: Optional[str] = None

    # 사용 정보
    platform_used: Optional[str] = None
    model_used: Optional[str] = None
    model_display_name: Optional[str] = None

    # 비용 정보
    cost_usd: float = 0.0
    credits_used: int = 0

    # 메타데이터
    duration: float = 0
    resolution: str = ""
    generation_time: float = 0.0

    # 실패 시
    error_message: Optional[str] = None

    # 추가 정보
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CostEstimate:
    """비용 예측"""
    platform: str
    model_key: str
    model_display_name: str

    # 비용
    estimated_cost_usd: float = 0.0
    estimated_credits: int = 0

    # 설정
    resolution: str = "720p"
    duration: int = 5

    # 참고 정보
    speed_tier: str = "medium"
    quality_tier: int = 4
    legal_warning: Optional[str] = None
    estimated_time_seconds: Optional[float] = None  # 예상 생성 시간 (초)


@dataclass
class PlatformBalance:
    """플랫폼 잔액 정보"""
    platform: str
    display_name: str

    # 잔액 (USD 기반 플랫폼)
    balance_usd: Optional[float] = None

    # 잔액 (크레딧 기반 플랫폼)
    credits_remaining: Optional[int] = None
    credits_daily_limit: Optional[int] = None
    credits_used_today: int = 0

    # 사용량 통계
    total_spent_usd: float = 0.0
    total_videos_generated: int = 0

    # 상태
    is_available: bool = True
    last_updated: str = ""

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()


@dataclass
class UsageStatistics:
    """사용량 통계"""
    # 일일 통계
    today_videos: int = 0
    today_cost_usd: float = 0.0

    # 월간 통계
    month_videos: int = 0
    month_cost_usd: float = 0.0

    # 전체 통계
    total_videos: int = 0
    total_cost_usd: float = 0.0

    # 플랫폼별 통계
    by_platform: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # 모델별 통계
    by_model: Dict[str, Dict[str, float]] = field(default_factory=dict)


@dataclass
class APIQuotaStatus:
    """API 할당량 상태 (레거시 호환)"""
    api_name: str
    display_name: str
    total_credits: int
    used_credits: int
    remaining_credits: int
    daily_limit: Optional[int] = None
    monthly_limit: Optional[int] = None
    daily_used: int = 0
    monthly_used: int = 0
    last_reset: str = ""
    next_reset: Optional[str] = None
    is_available: bool = True
    error_count: int = 0
    last_error: Optional[str] = None

    def __post_init__(self):
        if not self.last_reset:
            self.last_reset = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "APIQuotaStatus":
        return cls(**data)


@dataclass
class UsageRecord:
    """사용 기록"""
    timestamp: str
    platform: str
    model_key: str
    model_display_name: str
    prompt: str
    duration: int
    resolution: str
    cost_usd: float
    credits_used: int
    success: bool
    error_message: Optional[str] = None
    video_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UsageRecord":
        return cls(**data)


@dataclass
class APIState:
    """전체 API 상태 저장"""
    last_updated: str
    quotas: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    total_videos_generated: int = 0
    total_credits_used: int = 0
    generation_history: List[Dict[str, Any]] = field(default_factory=list)

    # 새 필드
    platform_balances: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    usage_history: List[Dict[str, Any]] = field(default_factory=list)
    daily_stats: Dict[str, Dict[str, float]] = field(default_factory=dict)
    monthly_stats: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "APIState":
        return cls(**data)

    def get_quota(self, api_name: str) -> Optional[APIQuotaStatus]:
        """특정 API의 할당량 상태 반환"""
        quota_data = self.quotas.get(api_name)
        if quota_data:
            return APIQuotaStatus.from_dict(quota_data)
        return None

    def set_quota(self, api_name: str, quota: APIQuotaStatus):
        """API 할당량 상태 설정"""
        self.quotas[api_name] = quota.to_dict()

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "APIState":
        data = json.loads(json_str)
        return cls.from_dict(data)
