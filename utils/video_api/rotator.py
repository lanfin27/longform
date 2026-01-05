"""
Video API 로테이터
- 멀티 플랫폼/멀티 모델 지원
- 자동 최적 선택
- 비용 기반 필터링
"""
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Callable
from datetime import datetime
import logging

from .quota_manager import QuotaManager
from .cost_calculator import CostCalculator
from .models import VideoGenerationRequest, VideoGenerationResult, CostEstimate
from .config import (
    PLATFORM_CONFIGS, ALL_MODELS, RECOMMENDED_MODELS,
    get_api_key, VideoType
)
from .api_clients import get_client, CLIENT_MAP

logger = logging.getLogger(__name__)


class VideoAPIRotator:
    """
    Video API 자동 로테이터

    사용 예시:
        rotator = VideoAPIRotator()

        # 자동 최적 선택
        result = await rotator.generate_video(
            prompt="A cinematic scene...",
            image_path="path/to/image.jpg"
        )

        # 특정 모델 선택
        result = await rotator.generate_video(
            prompt="A cinematic scene...",
            platform="fal_ai",
            model_key="hailuo_std"
        )
    """

    def __init__(self):
        self.quota_manager = QuotaManager()
        self._clients: Dict[str, any] = {}

    def _get_client(self, platform: str):
        """플랫폼 클라이언트 인스턴스 반환 (캐싱)"""
        if platform not in self._clients:
            try:
                config = PLATFORM_CONFIGS.get(platform, {})
                env_key = config.get("env_key")

                if env_key and not get_api_key(env_key):
                    logger.warning(f"{platform} API 키가 설정되지 않음: {env_key}")
                    return None

                self._clients[platform] = get_client(platform)
            except Exception as e:
                logger.error(f"{platform} 클라이언트 초기화 실패: {e}")
                return None

        return self._clients.get(platform)

    def get_available_platforms(self) -> List[str]:
        """사용 가능한 플랫폼 목록"""
        available = []

        for platform, config in PLATFORM_CONFIGS.items():
            if platform not in CLIENT_MAP:
                continue

            env_key = config.get("env_key")
            if env_key and not get_api_key(env_key):
                continue

            available.append(platform)

        return available

    async def generate_video(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        image_url: Optional[str] = None,
        platform: Optional[str] = None,
        model_key: Optional[str] = None,
        duration: int = 5,
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
        max_cost_usd: Optional[float] = None,
        prefer_fast: bool = False,
        prefer_quality: bool = False,
        enable_audio: bool = False,
        save_locally: bool = False,
        output_dir: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> VideoGenerationResult:
        """
        영상 생성

        Args:
            prompt: 영상 생성 프롬프트
            image_path: 입력 이미지 경로 (I2V)
            image_url: 입력 이미지 URL (I2V)
            platform: 플랫폼 지정 (fal_ai, replicate, pixverse)
            model_key: 모델 키 지정
            duration: 영상 길이 (초)
            resolution: 해상도 ("480p", "720p", "1080p")
            aspect_ratio: 화면 비율 ("16:9", "9:16", "1:1")
            max_cost_usd: 최대 비용 제한
            prefer_fast: 빠른 생성 우선
            prefer_quality: 품질 우선
            enable_audio: 오디오 생성
            save_locally: 로컬 저장 여부
            output_dir: 저장 경로
            negative_prompt: 네거티브 프롬프트
            seed: 시드 값

        Returns:
            VideoGenerationResult: 생성 결과
        """
        # 요청 객체 생성
        request = VideoGenerationRequest(
            prompt=prompt,
            image_path=image_path,
            image_url=image_url,
            platform=platform,
            model_key=model_key,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            max_cost_usd=max_cost_usd,
            enable_audio=enable_audio,
            save_locally=save_locally,
            output_dir=output_dir,
            negative_prompt=negative_prompt,
            seed=seed,
        )

        # 비디오 타입 결정
        video_type = "i2v" if (image_path or image_url) else "t2v"

        # 플랫폼/모델이 지정된 경우
        if platform and model_key:
            return await self._generate_with_model(request, platform, model_key)

        # 자동 선택
        available_platforms = self.get_available_platforms()

        if not available_platforms:
            return VideoGenerationResult(
                success=False,
                api_used="none",
                error_message="사용 가능한 API가 없습니다. API 키를 확인하세요."
            )

        # 최적 모델 선택
        if prefer_quality:
            best_option = CostCalculator.get_best_quality_option(
                video_type=video_type,
                max_cost_usd=max_cost_usd,
                platforms=available_platforms
            )
        elif prefer_fast:
            best_option = CostCalculator.get_fastest_option(
                video_type=video_type,
                max_cost_usd=max_cost_usd,
                platforms=available_platforms
            )
        else:
            # 기본: 가성비 (가장 저렴한 것)
            best_option = CostCalculator.get_cheapest_option(
                video_type=video_type,
                platforms=available_platforms
            )

        if not best_option:
            return VideoGenerationResult(
                success=False,
                api_used="none",
                error_message="조건에 맞는 모델을 찾을 수 없습니다."
            )

        # 선택된 모델로 생성
        request.platform = best_option.platform
        request.model_key = best_option.model_key

        return await self._generate_with_model(
            request,
            best_option.platform,
            best_option.model_key
        )

    async def _generate_with_model(
        self,
        request: VideoGenerationRequest,
        platform: str,
        model_key: str
    ) -> VideoGenerationResult:
        """특정 모델로 영상 생성"""
        client = self._get_client(platform)

        if not client:
            return VideoGenerationResult(
                success=False,
                api_used=platform,
                error_message=f"{platform} 클라이언트를 초기화할 수 없습니다."
            )

        logger.info(f"영상 생성 시작: {platform}/{model_key}")

        try:
            async with client:
                result = await client.generate_video(request)

            if result.success:
                # 사용량 기록
                self.quota_manager.record_usage(
                    platform=platform,
                    model_key=model_key,
                    cost_usd=result.cost_usd,
                    credits=result.credits_used,
                    success=True,
                    prompt=request.prompt,
                    duration=request.duration,
                    resolution=request.resolution,
                    video_url=result.video_url,
                )

                logger.info(
                    f"영상 생성 성공: {platform}/{model_key} "
                    f"(${result.cost_usd:.4f}, {result.generation_time:.1f}초)"
                )
            else:
                # 실패 기록
                self.quota_manager.record_usage(
                    platform=platform,
                    model_key=model_key,
                    success=False,
                    prompt=request.prompt,
                    duration=request.duration,
                    resolution=request.resolution,
                    error_message=result.error_message,
                )

                logger.warning(f"영상 생성 실패: {platform}/{model_key} - {result.error_message}")

            return result

        except Exception as e:
            error_msg = str(e)
            logger.error(f"영상 생성 예외: {platform}/{model_key} - {error_msg}")

            # 예외 기록
            self.quota_manager.record_usage(
                platform=platform,
                model_key=model_key,
                success=False,
                prompt=request.prompt,
                duration=request.duration,
                resolution=request.resolution,
                error_message=error_msg,
            )

            return VideoGenerationResult(
                success=False,
                api_used=platform,
                error_message=error_msg
            )

    async def generate_with_fallback(
        self,
        request: VideoGenerationRequest,
        platforms: Optional[List[str]] = None
    ) -> VideoGenerationResult:
        """
        폴백 지원 영상 생성

        첫 번째 플랫폼 실패 시 다음 플랫폼으로 자동 전환
        """
        if platforms is None:
            platforms = self.get_available_platforms()

        if not platforms:
            return VideoGenerationResult(
                success=False,
                api_used="none",
                error_message="사용 가능한 플랫폼이 없습니다."
            )

        video_type = "i2v" if (request.image_path or request.image_url) else "t2v"
        last_error = None

        for platform in platforms:
            # 해당 플랫폼에서 사용 가능한 모델 찾기
            models = ALL_MODELS.get(platform, {})

            for model_key, model_config in models.items():
                # 비디오 타입 체크
                model_type = model_config.video_type
                if model_type == VideoType.IMAGE_TO_VIDEO and video_type == "t2v":
                    continue
                if model_type == VideoType.TEXT_TO_VIDEO and video_type == "i2v":
                    continue

                request.platform = platform
                request.model_key = model_key

                result = await self._generate_with_model(request, platform, model_key)

                if result.success:
                    return result

                last_error = result.error_message
                logger.warning(f"폴백: {platform}/{model_key} 실패, 다음 시도...")

        return VideoGenerationResult(
            success=False,
            api_used="none",
            error_message=f"모든 API 실패. 마지막 에러: {last_error}"
        )

    async def generate_batch(
        self,
        requests: List[Dict],
        max_concurrent: int = 2,
        progress_callback: Optional[Callable[[int, int, VideoGenerationResult], None]] = None
    ) -> List[VideoGenerationResult]:
        """
        배치 영상 생성

        Args:
            requests: 생성 요청 리스트 [{"prompt": ..., "image_path": ...}, ...]
            max_concurrent: 최대 동시 생성 수
            progress_callback: 진행상황 콜백 (current, total, result)

        Returns:
            List[VideoGenerationResult]: 결과 리스트
        """
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_with_semaphore(idx: int, req: Dict):
            async with semaphore:
                result = await self.generate_video(**req)

                if progress_callback:
                    progress_callback(idx + 1, len(requests), result)

                return result

        tasks = [
            generate_with_semaphore(i, req)
            for i, req in enumerate(requests)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 예외를 실패 결과로 변환
        processed_results = []
        for r in results:
            if isinstance(r, Exception):
                processed_results.append(VideoGenerationResult(
                    success=False,
                    api_used="none",
                    error_message=str(r)
                ))
            else:
                processed_results.append(r)

        return processed_results

    def get_cost_comparison(
        self,
        video_type: str = "i2v",
        duration: int = 5,
        resolution: str = "720p"
    ) -> List[CostEstimate]:
        """
        비용 비교표 생성

        Returns:
            모든 사용 가능한 모델의 비용 추정 리스트
        """
        available = self.get_available_platforms()

        return CostCalculator.estimate_all_options(
            video_type=video_type,
            duration=duration,
            resolution=resolution,
            platforms=available
        )

    def get_status_summary(self) -> Dict:
        """전체 상태 요약"""
        stats = self.quota_manager.get_usage_statistics()
        available_platforms = self.get_available_platforms()

        platform_status = []
        for platform in CLIENT_MAP.keys():
            config = PLATFORM_CONFIGS.get(platform, {})
            balance = self.quota_manager.get_platform_balance(platform)

            env_key = config.get("env_key")
            has_key = bool(get_api_key(env_key)) if env_key else True

            models = ALL_MODELS.get(platform, {})
            model_count = len(models)

            platform_status.append({
                "platform": platform,
                "display_name": balance.display_name,
                "balance_usd": balance.balance_usd,
                "credits_remaining": balance.credits_remaining,
                "total_spent_usd": balance.total_spent_usd,
                "total_videos": balance.total_videos_generated,
                "is_available": platform in available_platforms,
                "has_key": has_key,
                "model_count": model_count,
            })

        return {
            "today_videos": stats.today_videos,
            "today_cost_usd": stats.today_cost_usd,
            "month_videos": stats.month_videos,
            "month_cost_usd": stats.month_cost_usd,
            "total_videos": stats.total_videos,
            "total_cost_usd": stats.total_cost_usd,
            "available_platforms": len(available_platforms),
            "platforms": platform_status,
        }

    def get_recommended_models(self) -> Dict[str, Dict]:
        """추천 모델 목록 (사용 가능한 것만)"""
        available = self.get_available_platforms()
        result = {}

        for category, rec in RECOMMENDED_MODELS.items():
            if rec["platform"] in available:
                result[category] = rec

        return result


# 싱글톤 인스턴스
_rotator_instance: Optional[VideoAPIRotator] = None


def get_rotator() -> VideoAPIRotator:
    """싱글톤 로테이터 인스턴스 반환"""
    global _rotator_instance
    if _rotator_instance is None:
        _rotator_instance = VideoAPIRotator()
    return _rotator_instance


async def generate_video(
    prompt: str,
    image_path: Optional[str] = None,
    **kwargs
) -> VideoGenerationResult:
    """간편 영상 생성 함수"""
    rotator = get_rotator()
    return await rotator.generate_video(prompt=prompt, image_path=image_path, **kwargs)


def generate_video_sync(
    prompt: str,
    image_path: Optional[str] = None,
    **kwargs
) -> VideoGenerationResult:
    """동기식 영상 생성 함수 (Streamlit 등에서 사용)"""
    return asyncio.run(generate_video(prompt=prompt, image_path=image_path, **kwargs))
