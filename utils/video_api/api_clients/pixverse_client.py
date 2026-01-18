"""
PixVerse API 클라이언트 - 공식 API
- Image-to-Video, Text-to-Video 지원
- 무료 크레딧: 90 (가입) + 60/일
"""

import asyncio
import time
import uuid
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from .base_client import BaseVideoAPIClient
from ..config import PIXVERSE_MODELS, VideoModelConfig, get_api_key
from ..models import VideoGenerationRequest, VideoGenerationResult
from ..cost_calculator import CostCalculator

logger = logging.getLogger(__name__)


class PixVerseClient(BaseVideoAPIClient):
    """PixVerse API 클라이언트"""

    PLATFORM = "pixverse"

    # 상태 코드
    STATUS_SUCCESS = 1
    STATUS_PROCESSING = 5
    STATUS_MODERATION_FAILED = 7
    STATUS_FAILED = 8

    @property
    def api_name(self) -> str:
        return "pixverse"

    @property
    def base_url(self) -> str:
        return "https://app-api.pixverse.ai/openapi/v2"

    @property
    def credits_per_video(self) -> int:
        return 20

    def __init__(self):
        api_key = get_api_key("PIXVERSE_API_KEY")
        super().__init__(api_key)

    def get_available_models(self) -> Dict[str, VideoModelConfig]:
        """사용 가능한 모델 목록"""
        return PIXVERSE_MODELS

    def _get_headers(self, trace_id: Optional[str] = None) -> Dict[str, str]:
        """API 헤더 생성 - 매 요청마다 새 trace_id 필요"""
        return {
            "API-KEY": self.api_key,
            "Ai-trace-id": trace_id or str(uuid.uuid4()),
            "Content-Type": "application/json"
        }

    async def generate_video(
        self,
        request: VideoGenerationRequest
    ) -> VideoGenerationResult:
        """PixVerse를 통한 영상 생성"""
        start_time = time.time()

        if not self.api_key:
            return self._create_error_result("PIXVERSE_API_KEY가 설정되지 않았습니다")

        # 모델 선택
        model_key = request.model_key or self._select_default_model(request)
        model_config = PIXVERSE_MODELS.get(model_key)

        if not model_config:
            return self._create_error_result(f"지원하지 않는 모델: {model_key}")

        try:
            # 고유 trace_id 생성
            trace_id = str(uuid.uuid4())

            # I2V 또는 T2V
            if request.image_path or request.image_url:
                video_id = await self._generate_from_image(request, model_config, trace_id)
            else:
                video_id = await self._generate_from_text(request, model_config, trace_id)

            # 완료까지 폴링
            video_url = await self._poll_for_completion(video_id, start_time)

            generation_time = time.time() - start_time

            # 비용 계산
            cost_estimate = CostCalculator.estimate_cost(
                platform=self.PLATFORM,
                model_key=model_key,
                duration=request.duration,
                resolution=request.resolution,
            )

            # 결과 생성
            result = VideoGenerationResult(
                success=True,
                api_used=self.api_name,
                video_url=video_url,
                platform_used=self.PLATFORM,
                model_used=model_key,
                model_display_name=model_config.display_name,
                cost_usd=cost_estimate.estimated_cost_usd,
                credits_used=cost_estimate.estimated_credits,
                duration=request.duration,
                resolution=request.resolution,
                generation_time=generation_time,
                metadata={"video_id": video_id}
            )

            # 로컬 저장
            if request.save_locally and request.output_dir:
                try:
                    output_path = Path(request.output_dir) / f"pixverse_{model_key}_{int(time.time())}.mp4"
                    async with self:
                        result.local_path = str(
                            await self.download_video(video_url, output_path)
                        )
                except Exception as e:
                    logger.warning(f"영상 다운로드 실패: {e}")

            logger.info(f"PixVerse 영상 생성 완료: {generation_time:.1f}초")
            return result

        except Exception as e:
            logger.error(f"PixVerse 영상 생성 실패: {e}")
            return self._create_error_result(
                str(e),
                time.time() - start_time
            )

    async def _generate_from_image(
        self,
        request: VideoGenerationRequest,
        model: VideoModelConfig,
        trace_id: str
    ) -> int:
        """Image-to-Video 생성"""
        # 1. 이미지 업로드
        img_id = await self._upload_image(request.image_path, request.image_url, trace_id)

        # 2. duration 검증 - PixVerse는 모델별 지원 duration이 제한적
        # 요청 duration이 지원되지 않으면 기본값 사용
        valid_duration = request.duration
        if model.durations and valid_duration not in model.durations:
            valid_duration = model.default_duration
            logger.warning(
                f"PixVerse {model.model_id}: duration {request.duration}초 미지원, "
                f"{valid_duration}초로 변경 (지원: {model.durations})"
            )

        # 3. 영상 생성 요청 (타입 명시적 변환)
        payload = {
            "img_id": int(img_id),  # 반드시 정수
            "prompt": str(request.prompt) if request.prompt else "",
            "negative_prompt": str(request.negative_prompt) if request.negative_prompt else "",
            "duration": int(valid_duration),  # 반드시 정수
            "model": str(model.model_id),
            "motion_mode": "normal"
        }

        logger.debug(f"[PixVerse I2V] Payload: {payload}")

        logger.info(f"PixVerse I2V 영상 생성 요청: {model.display_name}")

        response = await self.client.post(
            f"{self.base_url}/video/img/generate",
            headers=self._get_headers(trace_id),
            json=payload
        )

        data = response.json()

        if data.get("ErrCode") != 0:
            self._handle_error(data)

        return data["Resp"]["video_id"]

    async def _generate_from_text(
        self,
        request: VideoGenerationRequest,
        model: VideoModelConfig,
        trace_id: str
    ) -> int:
        """Text-to-Video 생성"""
        # duration 검증 - PixVerse는 모델별 지원 duration이 제한적
        valid_duration = request.duration
        if model.durations and valid_duration not in model.durations:
            valid_duration = model.default_duration
            logger.warning(
                f"PixVerse {model.model_id}: duration {request.duration}초 미지원, "
                f"{valid_duration}초로 변경 (지원: {model.durations})"
            )

        # 타입 명시적 변환
        # PixVerse aspect_ratio 지원: "16:9", "9:16", "1:1", "4:3", "3:4"
        aspect_ratio = str(request.aspect_ratio) if request.aspect_ratio else "16:9"
        if aspect_ratio not in ["16:9", "9:16", "1:1", "4:3", "3:4"]:
            logger.warning(f"[PixVerse] 지원하지 않는 aspect_ratio: {aspect_ratio}, 16:9로 변경")
            aspect_ratio = "16:9"

        payload = {
            "prompt": str(request.prompt) if request.prompt else "",
            "negative_prompt": str(request.negative_prompt) if request.negative_prompt else "",
            "aspect_ratio": aspect_ratio,
            "duration": int(valid_duration),  # 반드시 정수
            "model": str(model.model_id),
            "quality": str(self._get_quality(request.resolution)),
            "motion_mode": "normal",
            "water_mark": False  # boolean
        }

        logger.debug(f"[PixVerse T2V] Payload: {payload}")

        logger.info(f"PixVerse T2V 영상 생성 요청: {model.display_name}")

        response = await self.client.post(
            f"{self.base_url}/video/text/generate",
            headers=self._get_headers(trace_id),
            json=payload
        )

        data = response.json()

        if data.get("ErrCode") != 0:
            self._handle_error(data)

        return data["Resp"]["video_id"]

    async def _upload_image(
        self,
        image_path: Optional[str],
        image_url: Optional[str],
        trace_id: str
    ) -> int:
        """이미지 업로드"""
        local_path = None

        if image_url:
            # URL에서 다운로드
            local_path = await self._download_image(image_url)
        elif image_path:
            path = Path(image_path)
            if path.exists():
                local_path = str(path)
            else:
                # URL일 수도 있음
                local_path = await self._download_image(image_path)

        if not local_path:
            raise ValueError("이미지가 필요합니다")

        with open(local_path, "rb") as f:
            file_content = f.read()

        path = Path(local_path)
        suffix = path.suffix.lower()
        content_type = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp'
        }.get(suffix, 'image/jpeg')

        files = {"image": (path.name, file_content, content_type)}
        headers = {
            "API-KEY": self.api_key,
            "Ai-trace-id": trace_id
        }

        response = await self.client.post(
            f"{self.base_url}/image/upload",
            headers=headers,
            files=files
        )

        data = response.json()

        if data.get("ErrCode") != 0:
            self._handle_error(data)

        return data["Resp"]["img_id"]

    async def _download_image(self, url: str) -> str:
        """URL에서 이미지 다운로드"""
        response = await self.client.get(url)
        response.raise_for_status()

        ext = url.split(".")[-1].split("?")[0][:4]
        if ext not in ["jpg", "jpeg", "png", "webp"]:
            ext = "jpg"

        temp_path = tempfile.mktemp(suffix=f".{ext}")

        with open(temp_path, "wb") as f:
            f.write(response.content)

        return temp_path

    async def _poll_for_completion(
        self,
        video_id: int,
        start_time: float,
        max_wait: int = 300,
        poll_interval: int = 5
    ) -> str:
        """완료까지 폴링"""

        while time.time() - start_time < max_wait:
            poll_trace_id = str(uuid.uuid4())

            response = await self.client.get(
                f"{self.base_url}/video/result/{video_id}",
                headers=self._get_headers(poll_trace_id)
            )

            data = response.json()

            if data.get("ErrCode") != 0:
                self._handle_error(data)

            resp = data.get("Resp", {})
            status = resp.get("status")

            if status == self.STATUS_SUCCESS:
                video_url = resp.get("url")
                if video_url:
                    return video_url
                raise Exception("영상 URL이 없습니다")

            elif status == self.STATUS_MODERATION_FAILED:
                raise Exception("PixVerse 콘텐츠 검열 실패 - 프롬프트 수정 필요")

            elif status == self.STATUS_FAILED:
                raise Exception("PixVerse 영상 생성 실패")

            await asyncio.sleep(poll_interval)

        raise Exception("PixVerse 영상 생성 타임아웃 (5분 초과)")

    def _handle_error(self, data: Dict[str, Any]):
        """에러 처리"""
        err_code = data.get("ErrCode", -1)
        err_msg = data.get("ErrMsg", "Unknown error")

        if err_code == 10001:
            raise Exception(f"PixVerse 크레딧 부족: {err_msg}")

        raise Exception(f"PixVerse API 오류 [{err_code}]: {err_msg}")

    def _get_quality(self, resolution: str) -> str:
        """해상도 -> quality 매핑"""
        quality_map = {
            "360p": "360p",
            "480p": "540p",
            "540p": "540p",
            "720p": "720p",
            "1080p": "1080p"
        }
        return quality_map.get(resolution.lower(), "720p")

    def _select_default_model(self, request: VideoGenerationRequest) -> str:
        """기본 모델 선택"""
        if request.image_path or request.image_url:
            return "v4.5"
        return "v5"
