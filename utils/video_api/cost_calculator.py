"""
Video API 비용 계산기
"""

from typing import List, Optional
from .config import (
    ALL_MODELS, PLATFORM_CONFIGS,
    VideoModelConfig, VideoType, SpeedTier
)
from .models import CostEstimate


class CostCalculator:
    """영상 생성 비용 계산기"""

    # 속도 등급별 예상 생성 시간 (초)
    SPEED_TIME_MAP = {
        "fast": 60,      # 1분
        "medium": 180,   # 3분
        "slow": 300,     # 5분
    }

    @staticmethod
    def estimate_cost(
        platform: str,
        model_key: str,
        duration: int = 5,
        resolution: str = "720p",
        enable_audio: bool = False
    ) -> CostEstimate:
        """단일 모델 비용 추정"""

        if platform not in ALL_MODELS:
            raise ValueError(f"지원하지 않는 플랫폼: {platform}")

        if model_key not in ALL_MODELS[platform]:
            raise ValueError(f"지원하지 않는 모델: {platform}/{model_key}")

        model = ALL_MODELS[platform][model_key]

        # 비용 계산
        cost_usd = 0.0
        credits = 0

        if model.price_per_video:
            cost_usd = model.price_per_video
            # 해상도에 따른 가격 조정
            if resolution == "720p" and "480p" in model.resolutions and model.default_resolution == "480p":
                cost_usd *= 1.5  # 720p는 480p의 1.5배
            elif resolution == "1080p":
                cost_usd *= 2.0

        elif model.price_per_second:
            cost_usd = model.price_per_second * duration
            # 오디오 추가 시 2배
            if enable_audio and model.has_audio:
                cost_usd *= 2

        elif model.credits_per_video:
            credits = model.credits_per_video
            # 크레딧을 USD로 환산 (PixVerse: 대략 무료이므로 0)
            cost_usd = 0.0

        # 속도 등급에 따른 예상 생성 시간
        estimated_time = CostCalculator.SPEED_TIME_MAP.get(model.speed.value, 180)

        return CostEstimate(
            platform=platform,
            model_key=model_key,
            model_display_name=model.display_name,
            estimated_cost_usd=round(cost_usd, 4),
            estimated_credits=credits,
            resolution=resolution,
            duration=duration,
            speed_tier=model.speed.value,
            quality_tier=model.quality.value,
            legal_warning=model.legal_warning,
            estimated_time_seconds=estimated_time,
        )

    @staticmethod
    def estimate_all_options(
        video_type: str = "i2v",
        duration: int = 5,
        resolution: str = "720p",
        max_cost: Optional[float] = None,
        platforms: Optional[List[str]] = None,
    ) -> List[CostEstimate]:
        """모든 가능한 옵션의 비용 추정 (가격순 정렬)"""

        estimates = []

        target_platforms = platforms if platforms else list(ALL_MODELS.keys())

        for platform in target_platforms:
            if platform not in ALL_MODELS:
                continue

            for model_key, model in ALL_MODELS[platform].items():
                # 비디오 타입 필터
                if video_type == "i2v" and model.video_type == VideoType.TEXT_TO_VIDEO:
                    continue
                if video_type == "t2v" and model.video_type == VideoType.IMAGE_TO_VIDEO:
                    continue

                # 해상도 지원 확인
                if resolution in model.resolutions:
                    available_res = resolution
                else:
                    # 가장 가까운 해상도 선택
                    available_res = model.default_resolution

                # 길이 지원 확인
                if duration in model.durations:
                    available_dur = duration
                else:
                    available_dur = model.default_duration

                try:
                    estimate = CostCalculator.estimate_cost(
                        platform=platform,
                        model_key=model_key,
                        duration=available_dur,
                        resolution=available_res,
                    )

                    # 예산 필터
                    if max_cost and estimate.estimated_cost_usd > max_cost:
                        continue

                    estimates.append(estimate)
                except Exception:
                    continue

        # 가격순 정렬 (크레딧 기반은 맨 뒤로)
        estimates.sort(key=lambda x: (x.estimated_credits > 0, x.estimated_cost_usd))

        return estimates

    @staticmethod
    def get_cheapest_option(
        video_type: str = "i2v",
        duration: int = 5,
        min_quality: int = 3,
        platforms: Optional[List[str]] = None,
    ) -> Optional[CostEstimate]:
        """가장 저렴한 옵션 찾기"""

        estimates = CostCalculator.estimate_all_options(
            video_type=video_type,
            duration=duration,
            platforms=platforms,
        )

        for estimate in estimates:
            if estimate.quality_tier >= min_quality:
                return estimate

        return estimates[0] if estimates else None

    @staticmethod
    def get_fastest_option(
        video_type: str = "i2v",
        max_cost: Optional[float] = None,
        platforms: Optional[List[str]] = None,
    ) -> Optional[CostEstimate]:
        """가장 빠른 옵션 찾기"""

        estimates = CostCalculator.estimate_all_options(
            video_type=video_type,
            max_cost=max_cost,
            platforms=platforms,
        )

        # 속도순 정렬
        speed_order = {"fast": 0, "medium": 1, "slow": 2}
        estimates.sort(key=lambda x: speed_order.get(x.speed_tier, 2))

        return estimates[0] if estimates else None

    @staticmethod
    def get_best_quality_option(
        video_type: str = "i2v",
        max_cost: Optional[float] = None,
        platforms: Optional[List[str]] = None,
    ) -> Optional[CostEstimate]:
        """최고 품질 옵션 찾기"""

        estimates = CostCalculator.estimate_all_options(
            video_type=video_type,
            max_cost=max_cost,
            platforms=platforms,
        )

        # 품질순 정렬 (높은 것 먼저)
        estimates.sort(key=lambda x: -x.quality_tier)

        return estimates[0] if estimates else None

    @staticmethod
    def get_balanced_option(
        video_type: str = "i2v",
        max_cost: Optional[float] = None,
        platforms: Optional[List[str]] = None,
    ) -> Optional[CostEstimate]:
        """균형잡힌 옵션 찾기 (품질/가격 비율)"""

        estimates = CostCalculator.estimate_all_options(
            video_type=video_type,
            max_cost=max_cost,
            platforms=platforms,
        )

        if not estimates:
            return None

        # 품질/가격 점수 계산 (가격이 0이면 최고 점수)
        def score(e: CostEstimate) -> float:
            if e.estimated_cost_usd == 0:
                return e.quality_tier * 100  # 무료는 최고 점수
            return e.quality_tier / e.estimated_cost_usd

        estimates.sort(key=score, reverse=True)
        return estimates[0]

    @staticmethod
    def format_cost(estimate: CostEstimate) -> str:
        """비용을 포맷팅된 문자열로 반환"""
        if estimate.estimated_credits > 0:
            return f"{estimate.estimated_credits} 크레딧"
        elif estimate.estimated_cost_usd == 0:
            return "무료"
        else:
            return f"${estimate.estimated_cost_usd:.2f}"

    @staticmethod
    def format_speed(speed_tier: str) -> str:
        """속도를 이모지와 함께 반환"""
        speed_map = {
            "fast": "빠름",
            "medium": "보통",
            "slow": "느림"
        }
        return speed_map.get(speed_tier, speed_tier)

    @staticmethod
    def format_quality(quality_tier: int) -> str:
        """품질을 별표로 반환"""
        return "★" * quality_tier + "☆" * (5 - quality_tier)
