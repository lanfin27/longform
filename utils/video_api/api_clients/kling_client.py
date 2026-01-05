"""
Kling AI Client via PiAPI
- 최고 품질 영상 생성 (품질 5/5)
- Image-to-Video 지원
- 무료 크레딧: 첫 가입 $10
"""

import asyncio
import base64
import time
from pathlib import Path
from typing import Optional
import logging

from .base_client import BaseVideoAPIClient
from ..models import VideoGenerationRequest, VideoGenerationResult
from ..config import get_api_key

logger = logging.getLogger(__name__)


class KlingClient(BaseVideoAPIClient):
    """Kling AI API Client via PiAPI"""

    @property
    def api_name(self) -> str:
        return "kling_ai"

    @property
    def base_url(self) -> str:
        return "https://api.piapi.ai"

    @property
    def credits_per_video(self) -> int:
        return 1  # $0.08 per video

    def __init__(self):
        api_key = get_api_key("PIAPI_KEY")
        super().__init__(api_key)

    def _get_headers(self):
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    async def generate_video(
        self,
        request: VideoGenerationRequest
    ) -> VideoGenerationResult:
        """Kling AI를 통한 영상 생성"""
        start_time = time.time()

        if not self.api_key:
            return self._create_error_result("PIAPI_KEY가 설정되지 않았습니다")

        try:
            # 이미지 URL 준비
            image_url = await self._prepare_image_url(request.image_path)

            # 영상 생성 태스크 생성
            task_id = await self._create_task(image_url, request)

            # 완료까지 폴링
            video_url = await self._poll_for_completion(task_id, start_time)

            generation_time = time.time() - start_time

            return self._create_success_result(
                video_url=video_url,
                request=request,
                generation_time=generation_time,
                metadata={"task_id": task_id}
            )

        except Exception as e:
            logger.error(f"Kling AI 영상 생성 실패: {e}")
            return self._create_error_result(
                str(e),
                time.time() - start_time
            )

    async def _create_task(self, image_url: str, request: VideoGenerationRequest) -> str:
        """영상 생성 태스크 생성"""
        payload = {
            "model": "kling",
            "task_type": "video_generation",
            "input": {
                "prompt": request.prompt,
                "negative_prompt": "",
                "cfg_scale": 0.5,
                "duration": request.duration,
                "aspect_ratio": request.aspect_ratio,
                "image_url": image_url,
                "mode": "std"  # std (저렴) vs pro (고품질)
            },
            "config": {
                "service_mode": "",
                "webhook_config": {"endpoint": "", "secret": ""}
            }
        }

        logger.info(f"Kling AI 영상 생성 요청: {request.prompt[:50]}...")

        response = await self._retry_request(
            "POST",
            f"{self.base_url}/api/v1/task",
            json=payload
        )

        data = response.json()

        if data.get("code") != 200:
            raise Exception(f"Kling API 오류: {data.get('message')}")

        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            raise Exception("태스크 ID를 받지 못했습니다")

        return task_id

    async def _poll_for_completion(
        self,
        task_id: str,
        start_time: float,
        max_wait: int = 300,
        poll_interval: int = 5
    ) -> str:
        """태스크 완료까지 폴링 (최대 5분)"""

        while time.time() - start_time < max_wait:
            response = await self.client.get(
                f"{self.base_url}/api/v1/task/{task_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") != 200:
                raise Exception(f"상태 확인 오류: {data.get('message')}")

            task_data = data.get("data", {})
            status = task_data.get("status")

            if status == "completed":
                # 워터마크 없는 버전 우선, 없으면 일반 버전
                output = task_data.get("output", {})
                works = output.get("works", [])

                if works:
                    video_data = works[0].get("video", {})
                    video_url = video_data.get("resource_without_watermark") or video_data.get("resource")
                    if video_url:
                        return video_url

                raise Exception("영상 출력이 없습니다")

            elif status == "failed":
                error = task_data.get("error", {})
                raise Exception(f"영상 생성 실패: {error.get('message', 'Unknown error')}")

            # pending 또는 processing 상태면 대기
            await asyncio.sleep(poll_interval)

        raise Exception("영상 생성 타임아웃 (5분 초과)")

    async def _prepare_image_url(self, image_path: str) -> str:
        """이미지 URL 준비 - URL이면 그대로, 로컬 파일이면 업로드"""
        path = Path(image_path)

        if not path.exists():
            # URL인 경우 그대로 반환
            return image_path

        # 로컬 파일은 fal.ai storage에 업로드
        fal_key = get_api_key("FAL_KEY")
        if fal_key:
            return await self._upload_to_fal_storage(path, fal_key)

        raise ValueError("로컬 이미지 업로드를 위해 FAL_KEY가 필요합니다")

    async def _upload_to_fal_storage(self, file_path: Path, fal_key: str) -> str:
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
            headers={
                "Authorization": f"Key {fal_key}",
                "Content-Type": "application/json"
            },
            json={"data": file_data, "content_type": mime_type}
        )
        response.raise_for_status()
        return response.json()["url"]
