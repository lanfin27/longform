"""
Replicate 클라이언트 - 다중 모델 지원
"""

import asyncio
import base64
import time
from pathlib import Path
from typing import Optional, Dict, Any
import logging

import httpx

from .base_client import BaseVideoAPIClient
from ..config import REPLICATE_MODELS, VideoModelConfig, get_api_key, REQUEST_TIMEOUT
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

        # ⭐ HTTP 클라이언트 초기화 확인
        if not self.client:
            self.client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
            logger.debug("[Replicate] HTTP 클라이언트 초기화")

        try:
            # 이미지 URL 준비 (I2V)
            image_input = None
            if request.image_path or request.image_url:
                image_input = await self._prepare_image_input(
                    request.image_path,
                    request.image_url
                )
                logger.info(f"[Replicate] 이미지 준비 완료")

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

    async def _get_model_version(self, model_id: str) -> str:
        """모델의 최신 버전 해시 가져오기

        Args:
            model_id: 모델 식별자 (owner/name 형식)

        Returns:
            버전 해시 문자열
        """
        url = f"{self.base_url}/models/{model_id}"

        logger.info(f"[Replicate] 모델 정보 조회: {model_id}")

        response = await self.client.get(url, headers=self._get_headers())

        if response.status_code == 404:
            raise Exception(f"모델을 찾을 수 없습니다: {model_id}")

        response.raise_for_status()

        data = response.json()
        latest_version = data.get("latest_version", {}).get("id")

        if not latest_version:
            raise Exception(f"모델 버전을 찾을 수 없습니다: {model_id}")

        logger.info(f"[Replicate] 버전 해시: {latest_version[:20]}...")
        return latest_version

    async def _create_prediction(
        self,
        request: VideoGenerationRequest,
        model: VideoModelConfig,
        image_input: Optional[str] = None
    ) -> str:
        """Prediction 생성

        Replicate API는 /v1/predictions 엔드포인트에 버전 해시를 사용해야 합니다.
        커뮤니티 모델은 먼저 버전 해시를 조회한 후 호출합니다.
        """

        # 입력 파라미터 구성
        input_data = self._build_input(request, model, image_input)

        model_id = model.model_id

        # ✅ 항상 /v1/predictions 엔드포인트 사용 (올바른 방식)
        url = f"{self.base_url}/predictions"

        # 버전 해시 결정
        if model_id.startswith("sha256:") or len(model_id) == 64:
            # 이미 버전 해시인 경우
            version_hash = model_id
            logger.info(f"[Replicate] 버전 해시 직접 사용")
        elif "/" in model_id:
            # owner/name 형식인 경우 버전 해시 조회
            version_hash = await self._get_model_version(model_id)
        else:
            raise Exception(f"유효하지 않은 모델 ID: {model_id}")

        payload = {
            "version": version_hash,
            "input": input_data
        }

        logger.info(f"[Replicate] 영상 생성 요청: {model.display_name}")

        logger.info(f"[Replicate] 영상 생성 요청: {model.display_name}")
        logger.debug(f"[Replicate] 입력 파라미터: {list(input_data.keys())}")

        try:
            response = await self._retry_request(
                "POST",
                url,
                json=payload
            )

            data = response.json()
            prediction_id = data.get("id")

            if not prediction_id:
                logger.error(f"[Replicate] 응답에 ID 없음: {data}")
                raise Exception("예측 ID를 받지 못했습니다")

            logger.info(f"[Replicate] Prediction 생성됨: {prediction_id}")
            return prediction_id

        except Exception as e:
            # 상세 에러 로깅
            logger.error(f"[Replicate] Prediction 생성 실패: {e}")
            if hasattr(e, 'response'):
                try:
                    error_detail = e.response.json()
                    logger.error(f"[Replicate] 에러 상세: {error_detail}")
                except:
                    logger.error(f"[Replicate] 응답 텍스트: {e.response.text[:500]}")
            raise

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

        if "wan-2.2" in model_id or "wan-video" in model_id:
            # ⭐ v2.4: Wan 2.2 I2V Fast 모델 (속도 최적화)
            input_data["num_frames"] = request.duration * 16 + 1
            input_data["guide_scale"] = 5.0  # wan-2.2는 guide_scale 사용
            input_data["steps"] = 4  # 빠른 추론 (기본값)
            input_data["shift"] = 5.0

            if request.negative_prompt:
                input_data["negative_prompt"] = request.negative_prompt

        elif "wan" in model_id:
            # Wan 2.1 모델
            input_data["num_frames"] = request.duration * 16 + 1
            input_data["guidance_scale"] = 5.0
            input_data["num_inference_steps"] = 30

            if request.negative_prompt:
                input_data["negative_prompt"] = request.negative_prompt

        elif "seedance" in model_id:
            # ⭐ v2.4: ByteDance Seedance 1 Lite 모델
            input_data["duration"] = request.duration
            # 해상도 매핑
            res_height = {"480p": 480, "720p": 720, "1080p": 1080}.get(request.resolution, 720)
            input_data["resolution"] = f"{int(res_height * 16 / 9)}x{res_height}"

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
        """
        이미지 입력 준비 - Replicate API용 최적화

        Wan I2V 모델 권장사항:
        - 형식: JPEG 또는 PNG (WebP 지원 불확실)
        - 최대 해상도: 1280x720 권장
        - RGB 모드 필수
        """
        from PIL import Image
        import io

        MAX_SIZE = 1280  # 최대 크기

        def process_image(img: Image.Image) -> str:
            """이미지 처리 및 Base64 인코딩"""
            original_size = img.size
            logger.info(f"[Replicate] 원본 이미지 크기: {original_size[0]}x{original_size[1]}")

            # 크기 조정 필요 여부 확인
            if max(img.size) > MAX_SIZE:
                ratio = MAX_SIZE / max(img.size)
                new_width = int(img.size[0] * ratio)
                new_height = int(img.size[1] * ratio)
                # 짝수로 맞추기 (비디오 인코딩 호환성)
                new_width = new_width - (new_width % 2)
                new_height = new_height - (new_height % 2)
                img = img.resize((new_width, new_height), Image.LANCZOS)
                logger.info(f"[Replicate] 리사이즈: {new_width}x{new_height}")

            # RGBA -> RGB 변환 (투명도 제거)
            if img.mode in ('RGBA', 'LA', 'P'):
                # 흰색 배경에 합성
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
                logger.info(f"[Replicate] RGB 변환 완료")
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # JPEG로 인코딩 (더 작은 용량, 호환성 좋음)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=95, optimize=True)
            buffer.seek(0)

            file_data = base64.b64encode(buffer.read()).decode()
            data_uri = f"data:image/jpeg;base64,{file_data}"

            logger.info(f"[Replicate] Base64 인코딩 완료: {len(data_uri)} 문자")
            return data_uri

        # HTTP URL인 경우 - 다운로드 후 처리
        if image_url and image_url.startswith('http'):
            try:
                import httpx
                logger.info(f"[Replicate] 이미지 URL 다운로드: {image_url[:80]}...")
                async with httpx.AsyncClient() as client:
                    response = await client.get(image_url, timeout=30)
                    response.raise_for_status()
                    img = Image.open(io.BytesIO(response.content))
                    return process_image(img)
            except Exception as e:
                logger.warning(f"[Replicate] 이미지 다운로드 실패, URL 직접 사용: {e}")
                return image_url

        # 로컬 파일인 경우
        if image_path:
            path = Path(image_path)
            if path.exists():
                try:
                    img = Image.open(path)
                    return process_image(img)
                except Exception as e:
                    logger.error(f"[Replicate] 이미지 로드 실패: {e}")
                    # 폴백: 단순 Base64 인코딩
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
                # 경로가 URL일 수도 있음
                if image_path.startswith('http'):
                    return image_path
                raise ValueError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        raise ValueError("이미지가 필요합니다 (image_path 또는 image_url)")
