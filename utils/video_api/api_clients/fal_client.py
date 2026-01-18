"""
fal.ai 클라이언트 - 다중 모델 지원
"""

import base64
import time
from pathlib import Path
from typing import Optional, Dict, Any
import logging
import httpx

from .base_client import BaseVideoAPIClient
from ..config import FAL_MODELS, VideoModelConfig, get_api_key, PLATFORM_CONFIGS
from ..models import VideoGenerationRequest, VideoGenerationResult
from ..cost_calculator import CostCalculator

logger = logging.getLogger(__name__)


class FalAIClient(BaseVideoAPIClient):
    """fal.ai API 클라이언트 - 모든 모델 지원"""

    PLATFORM = "fal_ai"

    @property
    def api_name(self) -> str:
        return "fal_ai"

    @property
    def base_url(self) -> str:
        return "https://fal.run"

    @property
    def credits_per_video(self) -> int:
        return 10  # 기본값 (레거시 호환)

    def __init__(self):
        api_key = get_api_key("FAL_KEY")
        super().__init__(api_key)

    def get_available_models(self) -> Dict[str, VideoModelConfig]:
        """사용 가능한 모델 목록"""
        return FAL_MODELS

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json"
        }

    async def generate_video(
        self,
        request: VideoGenerationRequest
    ) -> VideoGenerationResult:
        """영상 생성 - 모델 자동/수동 선택"""

        start_time = time.time()

        if not self.api_key:
            return self._create_error_result("FAL_KEY가 설정되지 않았습니다")

        # 모델 선택
        model_key = request.model_key or self._select_default_model(request)
        model_config = FAL_MODELS.get(model_key)

        if not model_config:
            return self._create_error_result(f"지원하지 않는 모델: {model_key}")

        try:
            # 이미지 URL 준비 (I2V)
            image_url = None
            if request.image_path or request.image_url:
                image_url = await self._prepare_image_url(
                    request.image_path,
                    request.image_url
                )

            # 요청 payload 구성
            payload = self._build_payload(request, model_config, image_url)

            logger.info(f"fal.ai 영상 생성 요청: {model_config.display_name}")

            # API 호출 (동기식 - fal.ai가 완료까지 대기)
            response = await self._retry_request(
                "POST",
                f"{self.base_url}/{model_config.model_id}",
                json=payload
            )

            data = response.json()
            generation_time = time.time() - start_time

            # 결과 파싱
            video_url = self._extract_video_url(data)

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
                enable_audio=request.enable_audio,
            )

            # ⭐ v2.4: 확장된 프롬프트 추출 (최종 프롬프트 보기 기능)
            original_prompt = request.prompt
            final_prompt = self._extract_final_prompt(data, original_prompt)

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
                    "raw_response": data,
                    "model_id": model_config.model_id,
                    "original_prompt": original_prompt,
                    "final_prompt": final_prompt,
                    "prompt_expanded": final_prompt != original_prompt
                }
            )

            # 로컬 저장
            if request.save_locally and request.output_dir:
                try:
                    output_path = Path(request.output_dir) / f"fal_{model_key}_{int(time.time())}.mp4"
                    async with self:
                        result.local_path = str(
                            await self.download_video(video_url, output_path)
                        )
                except Exception as e:
                    logger.warning(f"영상 다운로드 실패: {e}")

            logger.info(f"fal.ai 영상 생성 완료: {generation_time:.1f}초")
            return result

        except httpx.HTTPStatusError as e:
            generation_time = time.time() - start_time

            # 403 Forbidden - 크레딧 부족
            if e.response.status_code == 403:
                logger.error(f"[fal.ai] 크레딧 부족 (403 Forbidden)")
                return self._create_error_result(
                    "fal.ai 크레딧이 부족합니다. https://fal.ai/dashboard 에서 크레딧을 충전하세요.",
                    generation_time
                )

            # 401 Unauthorized - API 키 오류
            if e.response.status_code == 401:
                logger.error(f"[fal.ai] API 키 오류 (401 Unauthorized)")
                return self._create_error_result(
                    "fal.ai API 키가 유효하지 않습니다. FAL_KEY 환경 변수를 확인하세요.",
                    generation_time
                )

            # 기타 HTTP 에러
            logger.error(f"fal.ai HTTP 에러: {e}")
            try:
                error_detail = e.response.json()
                error_msg = error_detail.get("detail", str(e))
            except:
                error_msg = str(e)

            return self._create_error_result(error_msg, generation_time)

        except Exception as e:
            logger.error(f"fal.ai 영상 생성 실패: {e}")
            return self._create_error_result(
                str(e),
                time.time() - start_time
            )

    def _select_default_model(self, request: VideoGenerationRequest) -> str:
        """기본 모델 선택 (비용 최적화)"""
        if request.image_path or request.image_url:
            return "wan_i2v"  # 가장 저렴한 I2V
        return "wan_t2v"  # 가장 저렴한 T2V

    def _build_payload(
        self,
        request: VideoGenerationRequest,
        model: VideoModelConfig,
        image_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """모델별 payload 구성"""

        payload: Dict[str, Any] = {
            "prompt": request.prompt,
        }

        # 이미지 URL (I2V 모델)
        if image_url:
            payload["image_url"] = image_url

        # 모델별 파라미터
        model_id = model.model_id.lower()

        if "wan" in model_id:
            # Wan 2.1 모델
            # ⭐ v2.3: resolution은 문자열이어야 함 ("480p", "720p") - 422 에러 수정
            # 기존: res_map = {"480p": 480, "720p": 720} → 숫자 반환 (❌)
            valid_resolutions = ["480p", "720p"]
            resolution = request.resolution if request.resolution in valid_resolutions else "480p"
            payload["resolution"] = resolution  # ✅ 문자열 그대로 전달
            payload["num_frames"] = 81  # ~5초 @ 16fps
            payload["num_inference_steps"] = 30
            payload["guidance_scale"] = 5.0

            if request.negative_prompt and model.supports_negative_prompt:
                payload["negative_prompt"] = request.negative_prompt

        elif "minimax" in model_id or "hailuo" in model_id:
            # Hailuo/MiniMax 모델
            payload["prompt_optimizer"] = True

        elif "kling" in model_id:
            # Kling 모델
            payload["duration"] = str(request.duration)
            if request.enable_audio and model.has_audio:
                payload["with_audio"] = True

        elif "hunyuan" in model_id:
            # HunyuanVideo 모델
            res_map = {"480p": 480, "544p": 544, "720p": 720}
            payload["height"] = res_map.get(request.resolution, 544)
            payload["width"] = int(res_map.get(request.resolution, 544) * 16 / 9)
            payload["num_inference_steps"] = 30

        elif "ltx" in model_id:
            # LTX Video 모델
            payload["num_frames"] = 121  # ~5초

        # 시드
        if request.seed and model.supports_seed:
            payload["seed"] = request.seed

        return payload

    def _extract_video_url(self, data: Dict[str, Any]) -> Optional[str]:
        """응답에서 영상 URL 추출"""
        # fal.ai 응답 구조에 따라 다양한 경로 시도
        if "video" in data:
            if isinstance(data["video"], dict):
                return data["video"].get("url")
            return data["video"]

        if "output" in data:
            output = data["output"]
            if isinstance(output, dict) and "video" in output:
                return output["video"].get("url") if isinstance(output["video"], dict) else output["video"]
            if isinstance(output, list) and output:
                return output[0]

        return None

    def _extract_final_prompt(self, data: Dict[str, Any], original_prompt: str) -> str:
        """
        ⭐ v2.4: 응답에서 최종 프롬프트 추출

        fal.ai는 prompt_expansion 기능을 제공하여 프롬프트를 자동 확장할 수 있음.
        확장된 프롬프트가 있으면 반환, 없으면 원본 반환.
        """
        # 다양한 경로에서 확장된 프롬프트 찾기
        possible_keys = [
            "expanded_prompt",
            "enhanced_prompt",
            "final_prompt",
            "processed_prompt",
            "prompt"
        ]

        for key in possible_keys:
            if key in data:
                expanded = data[key]
                if expanded and expanded != original_prompt:
                    return expanded

        # output 내부에서 찾기
        if "output" in data and isinstance(data["output"], dict):
            for key in possible_keys:
                if key in data["output"]:
                    expanded = data["output"][key]
                    if expanded and expanded != original_prompt:
                        return expanded

        return original_prompt

    async def _prepare_image_url(
        self,
        image_path: Optional[str],
        image_url: Optional[str]
    ) -> str:
        """이미지 URL 준비"""
        if image_url:
            return image_url

        if image_path:
            path = Path(image_path)
            if path.exists():
                # 로컬 파일은 base64로 변환
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
                # 경로가 실제로 URL일 수도 있음
                return image_path

        raise ValueError("이미지가 필요합니다")
