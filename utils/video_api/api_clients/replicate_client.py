"""
Replicate 클라이언트 - 다중 모델 지원
"""

import asyncio
import base64
import time
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from .base_client import BaseVideoAPIClient
from ..config import REPLICATE_MODELS, VideoModelConfig, get_api_key
from ..models import VideoGenerationRequest, VideoGenerationResult
from ..cost_calculator import CostCalculator

logger = logging.getLogger(__name__)


class ReplicateClient(BaseVideoAPIClient):
    """Replicate API 클라이언트 - 다중 모델 지원"""

    PLATFORM = "replicate"

    @property
    def api_name(self) -> str:
        return "replicate"

    @property
    def base_url(self) -> str:
        return "https://api.replicate.com/v1"

    @property
    def credits_per_video(self) -> int:
        return 1  # 레거시 호환

    def __init__(self):
        api_key = get_api_key("REPLICATE_API_TOKEN")
        super().__init__(api_key)

    def get_available_models(self) -> Dict[str, VideoModelConfig]:
        """사용 가능한 모델 목록"""
        return REPLICATE_MODELS

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Prefer": "wait"
        }

    async def generate_video(
        self,
        request: VideoGenerationRequest
    ) -> VideoGenerationResult:
        """영상 생성"""

        start_time = time.time()

        if not self.api_key:
            return self._create_error_result("REPLICATE_API_TOKEN이 설정되지 않았습니다")

        # 모델 선택
        model_key = request.model_key or self._select_default_model(request)
        model_config = REPLICATE_MODELS.get(model_key)

        if not model_config:
            return self._create_error_result(f"지원하지 않는 모델: {model_key}")

        try:
            # 이미지 URL 준비 (I2V)
            image_input = None
            if request.image_path or request.image_url:
                image_input = await self._prepare_image_input(
                    request.image_path,
                    request.image_url
                )

            # 1. Prediction 생성
            prediction_id = await self._create_prediction(
                request, model_config, image_input
            )

            # 2. 완료까지 폴링
            result_data = await self._poll_prediction(prediction_id, start_time)

            generation_time = time.time() - start_time

            # 3. 결과 파싱
            video_url = self._extract_video_url(result_data)

            if not video_url:
                return self._create_error_result(
                    "영상 URL을 받지 못했습니다",
                    generation_time
                )

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
                metadata={
                    "prediction_id": prediction_id,
                    "model_id": model_config.model_id
                }
            )

            # 로컬 저장
            if request.save_locally and request.output_dir:
                try:
                    output_path = Path(request.output_dir) / f"replicate_{model_key}_{int(time.time())}.mp4"
                    async with self:
                        result.local_path = str(
                            await self.download_video(video_url, output_path)
                        )
                except Exception as e:
                    logger.warning(f"영상 다운로드 실패: {e}")

            logger.info(f"Replicate 영상 생성 완료: {generation_time:.1f}초")
            return result

        except Exception as e:
            logger.error(f"Replicate 영상 생성 실패: {e}")
            return self._create_error_result(
                str(e),
                time.time() - start_time
            )

    async def _create_prediction(
        self,
        request: VideoGenerationRequest,
        model: VideoModelConfig,
        image_input: Optional[str] = None
    ) -> str:
        """Prediction 생성"""

        # 입력 파라미터 구성
        input_data = self._build_input(request, model, image_input)

        payload = {
            "version": model.model_id,
            "input": input_data
        }

        logger.info(f"Replicate 영상 생성 요청: {model.display_name}")

        response = await self._retry_request(
            "POST",
            f"{self.base_url}/predictions",
            json=payload
        )

        data = response.json()
        prediction_id = data.get("id")

        if not prediction_id:
            raise Exception("예측 ID를 받지 못했습니다")

        return prediction_id

    async def _poll_prediction(
        self,
        prediction_id: str,
        start_time: float,
        max_wait: int = 300,
        poll_interval: int = 5
    ) -> Dict[str, Any]:
        """Prediction 완료까지 폴링"""

        while time.time() - start_time < max_wait:
            response = await self.client.get(
                f"{self.base_url}/predictions/{prediction_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()

            status = data.get("status")

            if status == "succeeded":
                return data
            elif status == "failed":
                error = data.get("error", "Unknown error")
                raise Exception(f"생성 실패: {error}")
            elif status == "canceled":
                raise Exception("생성이 취소되었습니다")

            # starting, processing 상태면 대기
            await asyncio.sleep(poll_interval)

        raise Exception("생성 시간 초과 (5분)")

    def _build_input(
        self,
        request: VideoGenerationRequest,
        model: VideoModelConfig,
        image_input: Optional[str] = None
    ) -> Dict[str, Any]:
        """모델별 입력 파라미터 구성"""

        input_data: Dict[str, Any] = {
            "prompt": request.prompt,
        }

        # 이미지 (I2V)
        if image_input:
            input_data["image"] = image_input

        # 모델별 파라미터
        model_id = model.model_id.lower()

        if "wan" in model_id:
            # Wan 2.1 모델
            input_data["num_frames"] = request.duration * 16 + 1
            input_data["guidance_scale"] = 5.0
            input_data["num_inference_steps"] = 30

            if request.negative_prompt:
                input_data["negative_prompt"] = request.negative_prompt

        elif "minimax" in model_id or "video-01" in model_id:
            # MiniMax/Hailuo 모델
            input_data["prompt_optimizer"] = True

        elif "haiper" in model_id:
            # Haiper 모델
            input_data["duration"] = request.duration
            input_data["aspect_ratio"] = request.aspect_ratio

        elif "luma" in model_id or "ray" in model_id:
            # Luma Ray 모델
            input_data["aspect_ratio"] = request.aspect_ratio

        elif "hunyuan" in model_id:
            # HunyuanVideo 모델
            res_map = {"480p": 480, "720p": 720}
            input_data["height"] = res_map.get(request.resolution, 720)
            input_data["width"] = int(res_map.get(request.resolution, 720) * 16 / 9)

        # 시드
        if request.seed and model.supports_seed:
            input_data["seed"] = request.seed

        return input_data

    def _select_default_model(self, request: VideoGenerationRequest) -> str:
        """기본 모델 선택"""
        if request.image_path or request.image_url:
            return "wan_i2v"
        return "wan_t2v"

    def _extract_video_url(self, data: Dict[str, Any]) -> Optional[str]:
        """결과에서 영상 URL 추출"""
        output = data.get("output")

        if isinstance(output, list) and output:
            return output[0]
        elif isinstance(output, str):
            return output
        elif isinstance(output, dict):
            return output.get("video") or output.get("url")

        return None

    async def _prepare_image_input(
        self,
        image_path: Optional[str],
        image_url: Optional[str]
    ) -> str:
        """이미지 입력 준비"""
        if image_url:
            return image_url

        if image_path:
            path = Path(image_path)
            if path.exists():
                # Replicate는 base64 data URI 지원
                with open(path, "rb") as f:
                    file_data = base64.b64encode(f.read()).decode()

                suffix = path.suffix.lower()
                mime_type = {
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.webp': 'image/webp'
                }.get(suffix, 'image/png')

                return f"data:{mime_type};base64,{file_data}"
            else:
                # URL일 수도 있음
                return image_path

        raise ValueError("이미지가 필요합니다")
