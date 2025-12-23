# -*- coding: utf-8 -*-
"""
통합 이미지 생성 API 매니저

지원 API:
- Together.ai FLUX (빠름, 무료 티어 있음)
- OpenAI DALL-E (고품질)
- Stability AI (안정적)
- Replicate (다양한 모델)
"""

import os
import time
import base64
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GenerationResult:
    """이미지 생성 결과"""
    success: bool
    image_data: Optional[bytes] = None  # 이미지 바이너리
    image_url: Optional[str] = None
    image_path: Optional[str] = None
    elapsed_time: float = 0
    error: Optional[str] = None


# API별 모델 옵션
API_MODELS = {
    "Together.ai FLUX": [
        ("black-forest-labs/FLUX.1-schnell-Free", "FLUX Schnell (무료, 빠름)"),
        ("black-forest-labs/FLUX.1-schnell", "FLUX Schnell (유료)"),
        ("black-forest-labs/FLUX.1.1-pro", "FLUX Pro (고품질)"),
    ],
    "OpenAI DALL-E": [
        ("dall-e-3", "DALL-E 3 (최신)"),
        ("dall-e-2", "DALL-E 2"),
    ],
    "Stability AI": [
        ("stable-diffusion-xl-1024-v1-0", "SDXL 1.0"),
        ("sd3-large", "Stable Diffusion 3 Large"),
    ],
    "Replicate SDXL": [
        ("stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b", "SDXL 기본"),
        ("bytedance/sdxl-lightning-4step:5599ed30703defd1d160a25a63321b4dec97101d98b4674bcc56e41f62f35637", "SDXL Lightning (초고속!)"),
    ]
}

# API별 예상 생성 시간 (초)
API_GENERATION_TIME = {
    "Together.ai FLUX": 5,
    "OpenAI DALL-E": 8,
    "Stability AI": 10,
    "Replicate SDXL": 8,  # Lightning은 3초
}


class ImageAPIManager:
    """통합 이미지 생성 API 매니저"""

    def __init__(self):
        # API 키 로드
        self.together_api_key = os.getenv("TOGETHER_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.stability_api_key = os.getenv("STABILITY_API_KEY")
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN")

        # Rate limit 추적
        self._last_call_time: Dict[str, float] = {}
        self._rate_limits = {
            "Together.ai FLUX": 6.0,       # Free 모델은 6초 간격
            "OpenAI DALL-E": 1.0,          # 1초 간격
            "Stability AI": 1.0,           # 1초 간격
            "Replicate SDXL": 0.5,         # 0.5초 간격
        }

    @staticmethod
    def get_available_apis() -> List[str]:
        """사용 가능한 API 목록"""
        return list(API_MODELS.keys())

    @staticmethod
    def get_models(api_provider: str) -> List[Tuple[str, str]]:
        """API별 모델 목록 (model_id, display_name)"""
        return API_MODELS.get(api_provider, [])

    @staticmethod
    def get_estimated_time(api_provider: str, model: str = "") -> int:
        """예상 생성 시간 (초)"""
        base_time = API_GENERATION_TIME.get(api_provider, 10)
        # Lightning 모델은 더 빠름
        if "lightning" in model.lower():
            return 3
        return base_time

    def check_api_key(self, api_provider: str) -> bool:
        """API 키 확인"""
        if api_provider == "Together.ai FLUX":
            return bool(self.together_api_key)
        elif api_provider == "OpenAI DALL-E":
            return bool(self.openai_api_key)
        elif api_provider == "Stability AI":
            return bool(self.stability_api_key)
        elif api_provider == "Replicate SDXL":
            return bool(self.replicate_api_token)
        return False

    def generate_image(
        self,
        prompt: str,
        api_provider: str = "Together.ai FLUX",
        model: str = None,
        width: int = 1024,
        height: int = 1024,
        negative_prompt: str = "",
        skip_rate_limit: bool = False
    ) -> GenerationResult:
        """
        이미지 생성 (통합 인터페이스)

        Args:
            prompt: 이미지 프롬프트
            api_provider: API 제공자 ("Together.ai FLUX", "OpenAI DALL-E", etc.)
            model: 모델 ID (None이면 기본 모델 사용)
            width: 이미지 너비
            height: 이미지 높이
            negative_prompt: 네거티브 프롬프트
            skip_rate_limit: Rate limit 대기 스킵 여부

        Returns:
            GenerationResult
        """
        start_time = time.time()

        # Rate limit 체크
        if not skip_rate_limit:
            self._wait_for_rate_limit(api_provider, model)

        try:
            if api_provider == "Together.ai FLUX":
                result = self._generate_together(prompt, model, width, height)
            elif api_provider == "OpenAI DALL-E":
                result = self._generate_openai(prompt, model, width, height)
            elif api_provider == "Stability AI":
                result = self._generate_stability(prompt, model, width, height, negative_prompt)
            elif api_provider == "Replicate SDXL":
                result = self._generate_replicate(prompt, model, width, height, negative_prompt)
            else:
                return GenerationResult(success=False, error=f"Unknown API: {api_provider}")

            elapsed = time.time() - start_time
            result.elapsed_time = elapsed

            print(f"[ImageAPI] {api_provider} 생성 완료: {elapsed:.1f}초")

            return result

        except Exception as e:
            elapsed = time.time() - start_time
            print(f"[ImageAPI] {api_provider} 오류: {e}")
            return GenerationResult(success=False, error=str(e), elapsed_time=elapsed)

    def _wait_for_rate_limit(self, api_provider: str, model: str = None):
        """Rate limit 대기"""
        # Free 모델이 아니면 rate limit 짧게
        min_interval = self._rate_limits.get(api_provider, 1.0)

        # Together Free 모델만 6초 대기
        if api_provider == "Together.ai FLUX" and model and "Free" not in model:
            min_interval = 1.0

        last_call = self._last_call_time.get(api_provider, 0)
        elapsed = time.time() - last_call

        if elapsed < min_interval:
            wait_time = min_interval - elapsed
            print(f"[RateLimit] {api_provider}: {wait_time:.1f}초 대기")
            time.sleep(wait_time)

        self._last_call_time[api_provider] = time.time()

    # ═══════════════════════════════════════════════════════
    # Together.ai FLUX
    # ═══════════════════════════════════════════════════════
    def _generate_together(
        self,
        prompt: str,
        model: str,
        width: int,
        height: int
    ) -> GenerationResult:
        """Together.ai FLUX 이미지 생성"""

        if not self.together_api_key:
            return GenerationResult(success=False, error="TOGETHER_API_KEY not set")

        try:
            from together import Together
            client = Together(api_key=self.together_api_key)

            model = model or "black-forest-labs/FLUX.1-schnell-Free"

            # Free 모델은 steps=4 고정
            steps = 4 if "Free" in model else 20

            response = client.images.generate(
                prompt=prompt,
                model=model,
                width=min(1792, max(64, width)),
                height=min(1792, max(64, height)),
                steps=steps,
                n=1,
                response_format="b64_json"
            )

            if response.data and response.data[0].b64_json:
                image_data = base64.b64decode(response.data[0].b64_json)
                return GenerationResult(success=True, image_data=image_data)

            return GenerationResult(success=False, error="No image data returned")

        except Exception as e:
            return GenerationResult(success=False, error=str(e))

    # ═══════════════════════════════════════════════════════
    # OpenAI DALL-E
    # ═══════════════════════════════════════════════════════
    def _generate_openai(
        self,
        prompt: str,
        model: str,
        width: int,
        height: int
    ) -> GenerationResult:
        """OpenAI DALL-E 이미지 생성"""

        if not self.openai_api_key:
            return GenerationResult(success=False, error="OPENAI_API_KEY not set")

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.openai_api_key)

            model = model or "dall-e-3"

            # DALL-E 3는 size 제한이 있음
            if width >= 1792 or height >= 1792:
                if width > height:
                    size = "1792x1024"
                else:
                    size = "1024x1792"
            else:
                size = "1024x1024"

            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                quality="standard",
                n=1,
                response_format="b64_json"
            )

            if response.data and response.data[0].b64_json:
                image_data = base64.b64decode(response.data[0].b64_json)
                return GenerationResult(success=True, image_data=image_data)

            return GenerationResult(success=False, error="No image data returned")

        except Exception as e:
            return GenerationResult(success=False, error=str(e))

    # ═══════════════════════════════════════════════════════
    # Stability AI
    # ═══════════════════════════════════════════════════════
    def _generate_stability(
        self,
        prompt: str,
        model: str,
        width: int,
        height: int,
        negative_prompt: str
    ) -> GenerationResult:
        """Stability AI 이미지 생성"""

        if not self.stability_api_key:
            return GenerationResult(success=False, error="STABILITY_API_KEY not set")

        try:
            engine_id = model or "stable-diffusion-xl-1024-v1-0"
            url = f"https://api.stability.ai/v1/generation/{engine_id}/text-to-image"

            headers = {
                "Authorization": f"Bearer {self.stability_api_key}",
                "Content-Type": "application/json"
            }

            # 크기 조정 (64의 배수로)
            width = (width // 64) * 64
            height = (height // 64) * 64
            width = max(512, min(1024, width))
            height = max(512, min(1024, height))

            body = {
                "text_prompts": [
                    {"text": prompt, "weight": 1.0}
                ],
                "cfg_scale": 7,
                "height": height,
                "width": width,
                "samples": 1,
                "steps": 30
            }

            if negative_prompt:
                body["text_prompts"].append({"text": negative_prompt, "weight": -1.0})

            response = requests.post(url, headers=headers, json=body, timeout=120)

            if response.status_code == 200:
                data = response.json()
                if data.get("artifacts"):
                    image_data = base64.b64decode(data["artifacts"][0]["base64"])
                    return GenerationResult(success=True, image_data=image_data)

            return GenerationResult(success=False, error=f"API Error: {response.status_code} - {response.text}")

        except Exception as e:
            return GenerationResult(success=False, error=str(e))

    # ═══════════════════════════════════════════════════════
    # Replicate
    # ═══════════════════════════════════════════════════════
    def _generate_replicate(
        self,
        prompt: str,
        model: str,
        width: int,
        height: int,
        negative_prompt: str
    ) -> GenerationResult:
        """Replicate 이미지 생성"""

        if not self.replicate_api_token:
            return GenerationResult(success=False, error="REPLICATE_API_TOKEN not set")

        try:
            import replicate

            model = model or "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b"

            input_params = {
                "prompt": prompt,
                "width": width,
                "height": height,
            }

            # Lightning 모델은 inference steps가 다름
            if "lightning" in model.lower():
                input_params["num_inference_steps"] = 4

            if negative_prompt:
                input_params["negative_prompt"] = negative_prompt

            output = replicate.run(model, input=input_params)

            if output:
                # output은 보통 URL 리스트
                image_url = output[0] if isinstance(output, list) else output

                # URL에서 이미지 다운로드
                response = requests.get(image_url, timeout=30)
                if response.status_code == 200:
                    return GenerationResult(success=True, image_data=response.content, image_url=image_url)

            return GenerationResult(success=False, error="No image generated")

        except Exception as e:
            return GenerationResult(success=False, error=str(e))

    def save_image(
        self,
        result: GenerationResult,
        output_path: str
    ) -> bool:
        """결과 이미지 저장"""

        if not result.success or not result.image_data:
            return False

        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "wb") as f:
                f.write(result.image_data)

            result.image_path = str(output_path)
            return True

        except Exception as e:
            print(f"[ImageAPI] 이미지 저장 실패: {e}")
            return False


# 싱글톤 인스턴스
_image_api_manager: Optional[ImageAPIManager] = None


def get_image_api_manager() -> ImageAPIManager:
    """이미지 API 매니저 싱글톤 반환"""
    global _image_api_manager
    if _image_api_manager is None:
        _image_api_manager = ImageAPIManager()
    return _image_api_manager
