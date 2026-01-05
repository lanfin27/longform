"""
API 클라이언트 베이스 클래스
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pathlib import Path
import httpx
import asyncio
import logging
import aiofiles

from ..models import VideoGenerationRequest, VideoGenerationResult
from ..config import REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY

logger = logging.getLogger(__name__)


class BaseVideoAPIClient(ABC):
    """Video API 클라이언트 추상 베이스 클래스"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.client: Optional[httpx.AsyncClient] = None

    @property
    @abstractmethod
    def api_name(self) -> str:
        """API 이름"""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """API 베이스 URL"""
        pass

    @property
    @abstractmethod
    def credits_per_video(self) -> int:
        """영상당 소모 크레딧"""
        pass

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    def _get_headers(self) -> Dict[str, str]:
        """API 요청 헤더"""
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @abstractmethod
    async def generate_video(
        self,
        request: VideoGenerationRequest
    ) -> VideoGenerationResult:
        """
        영상 생성 (구현 필수)

        Args:
            request: 영상 생성 요청

        Returns:
            VideoGenerationResult: 생성 결과
        """
        pass

    async def _retry_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """재시도 로직이 포함된 HTTP 요청"""
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await self.client.request(
                    method, url,
                    headers=self._get_headers(),
                    **kwargs
                )
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(f"{self.api_name} 요청 실패 (시도 {attempt + 1}): {e}")

                # 429 Rate Limit - 대기 후 재시도
                if e.response.status_code == 429:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue

                # 4xx 클라이언트 에러 - 재시도 안함
                if 400 <= e.response.status_code < 500:
                    raise

            except httpx.RequestError as e:
                last_error = e
                logger.warning(f"{self.api_name} 연결 에러 (시도 {attempt + 1}): {e}")
                await asyncio.sleep(RETRY_DELAY)

        raise last_error

    async def download_video(
        self,
        video_url: str,
        output_path: Path
    ) -> Path:
        """생성된 영상 다운로드"""
        try:
            response = await self.client.get(video_url, timeout=120)
            response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(output_path, 'wb') as f:
                await f.write(response.content)

            logger.info(f"영상 다운로드 완료: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"영상 다운로드 실패: {e}")
            raise

    def _estimate_credits(self, request: VideoGenerationRequest) -> int:
        """요청에 따른 예상 크레딧 계산"""
        base_credits = self.credits_per_video

        # 해상도에 따른 배수
        resolution_multiplier = {
            "480p": 1,
            "720p": 1.5,
            "1080p": 2,
            "4k": 3
        }

        # 길이에 따른 배수 (5초 기준)
        duration_multiplier = request.duration / 5

        return int(
            base_credits *
            resolution_multiplier.get(request.resolution, 1) *
            duration_multiplier
        )

    def _create_success_result(
        self,
        video_url: str,
        request: VideoGenerationRequest,
        generation_time: float,
        metadata: Dict[str, Any] = None
    ) -> VideoGenerationResult:
        """성공 결과 생성 헬퍼"""
        return VideoGenerationResult(
            success=True,
            api_used=self.api_name,
            video_url=video_url,
            duration=request.duration,
            resolution=request.resolution,
            credits_used=self._estimate_credits(request),
            generation_time=generation_time,
            metadata=metadata or {}
        )

    def _create_error_result(
        self,
        error_message: str,
        generation_time: float = 0
    ) -> VideoGenerationResult:
        """에러 결과 생성 헬퍼"""
        return VideoGenerationResult(
            success=False,
            api_used=self.api_name,
            error_message=error_message,
            generation_time=generation_time
        )
