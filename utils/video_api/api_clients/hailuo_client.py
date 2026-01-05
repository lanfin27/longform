"""
Hailuo AI (MiniMax) Client via fal.ai
- 최고 품질 영상 생성 (품질 5/5, Veo 3 상위)
- Image-to-Video, Text-to-Video 지원
- 무료 크레딧: fal.ai $10 (FAL_KEY 공유)
- 2025년 9월 미국 저작권 소송 진행 중 - 상업적 사용 주의
"""

import base64
import time
from pathlib import Path
from typing import Optional
import logging

from .base_client import BaseVideoAPIClient
from ..models import VideoGenerationRequest, VideoGenerationResult
from ..config import get_api_key

logger = logging.getLogger(__name__)


class HailuoClient(BaseVideoAPIClient):
    """Hailuo AI (MiniMax) API Client via fal.ai"""

    # 모델 옵션
    MODELS = {
        "video-01": "fal-ai/minimax/video-01/image-to-video",
        "hailuo-02-standard": "fal-ai/minimax/hailuo-02/standard/image-to-video",
        "hailuo-02-t2v": "fal-ai/minimax/hailuo-02/standard/text-to-video",
    }

    # 해상도별 가격 ($/초)
    PRICING = {
        "768P": 0.045,
        "512P": 0.017
    }

    @property
    def api_name(self) -> str:
        return "hailuo_ai"

    @property
    def base_url(self) -> str:
        return "https://fal.run"

    @property
    def credits_per_video(self) -> int:
        return 27  # $0.27 per 6-second video (768P)

    def __init__(self, model: str = "hailuo-02-standard"):
        api_key = get_api_key("FAL_KEY")
        super().__init__(api_key)
        self.model = self.MODELS.get(model, self.MODELS["hailuo-02-standard"])

    def _get_headers(self):
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json"
        }

    async def generate_video(
        self,
        request: VideoGenerationRequest
    ) -> VideoGenerationResult:
        """Hailuo AI를 통한 영상 생성"""
        start_time = time.time()

        if not self.api_key:
            return self._create_error_result("FAL_KEY가 설정되지 않았습니다")

        try:
            # 이미지 URL 준비
            image_url = await self._prepare_image_url(request.image_path)

            # 해상도 결정
            resolution = self._get_resolution(request.resolution)

            # 요청 payload 구성
            payload = {
                "image_url": image_url,
                "prompt": request.prompt,
                "prompt_optimizer": True,  # 프롬프트 자동 최적화
                "duration": min(request.duration, 6),  # 최대 6초
                "resolution": resolution
            }

            logger.info(f"Hailuo AI 영상 생성 요청: {request.prompt[:50]}...")

            # 동기식 요청 (fal.ai가 완료까지 대기)
            response = await self._retry_request(
                "POST",
                f"{self.base_url}/{self.model}",
                json=payload
            )

            data = response.json()
            generation_time = time.time() - start_time

            video_url = data.get("video", {}).get("url")
            if not video_url:
                return self._create_error_result(
                    "영상 URL을 받지 못했습니다",
                    generation_time
                )

            return self._create_success_result(
                video_url=video_url,
                request=request,
                generation_time=generation_time,
                metadata={
                    "model": self.model,
                    "resolution": resolution
                }
            )

        except Exception as e:
            logger.error(f"Hailuo AI 영상 생성 실패: {e}")
            return self._create_error_result(
                str(e),
                time.time() - start_time
            )

    async def _prepare_image_url(self, image_path: str) -> str:
        """이미지 URL 준비"""
        path = Path(image_path)

        if not path.exists():
            # URL인 경우 그대로 반환
            return image_path

        # 로컬 파일 -> fal.ai storage 업로드
        return await self._upload_to_fal_storage(path)

    async def _upload_to_fal_storage(self, file_path: Path) -> str:
        """fal.ai storage에 이미지 업로드"""
        with open(file_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode()

        suffix = file_path.suffix.lower()
        mime_type = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp'
        }.get(suffix, 'image/png')

        response = await self.client.post(
            "https://fal.run/fal-ai/storage/upload/base64",
            headers=self._get_headers(),
            json={"data": file_data, "content_type": mime_type}
        )
        response.raise_for_status()
        return response.json()["url"]

    def _get_resolution(self, resolution: str) -> str:
        """해상도 매핑"""
        resolution_map = {
            "480p": "512P",
            "512p": "512P",
            "720p": "768P",
            "768p": "768P",
            "1080p": "768P"  # Hailuo 02 Standard 최대 768P
        }
        return resolution_map.get(resolution.lower(), "768P")

    def _estimate_credits(self, request: VideoGenerationRequest) -> int:
        """크레딧 추정 (센트 단위)"""
        resolution = self._get_resolution(request.resolution)
        price_per_sec = self.PRICING.get(resolution, 0.045)
        # 달러를 센트로 변환하여 반환
        return int(price_per_sec * request.duration * 100)
