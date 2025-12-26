# -*- coding: utf-8 -*-
"""
통합 이미지 생성 API 매니저

지원 API:
- Together.ai FLUX (빠름, 합리적 가격)
- OpenAI DALL-E (고품질)
- Stability AI (안정적)
- Replicate (다양한 모델)
- Google ImageFX (Imagen) (무료, Authorization 토큰 또는 쿠키 기반)
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
        ("black-forest-labs/FLUX.2-dev", "FLUX.2 Dev (권장, ~20원)"),
        ("black-forest-labs/FLUX.2-flex", "FLUX.2 Flex (~40원)"),
        ("black-forest-labs/FLUX.2-pro", "FLUX.2 Pro (고품질, ~40원)"),
    ],
    "Google ImageFX": [
        ("IMAGEN_4", "Imagen 4 (최신, 무료)"),
        ("IMAGEN_3_5", "Imagen 3.5 (무료)"),
        ("IMAGEN_3_1", "Imagen 3.1 (무료)"),
        ("IMAGEN_3", "Imagen 3.0 (무료)"),
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
    "Google ImageFX": 15,  # ImageFX는 상대적으로 느림
    "OpenAI DALL-E": 8,
    "Stability AI": 10,
    "Replicate SDXL": 8,  # Lightning은 3초
}

# 모델별 가격 정보 (USD/장)
MODEL_PRICING = {
    # Together.ai FLUX
    "black-forest-labs/FLUX.2-dev": {"price": 0.0154, "name": "FLUX.2 Dev", "api": "Together.ai"},
    "black-forest-labs/FLUX.2-flex": {"price": 0.03, "name": "FLUX.2 Flex", "api": "Together.ai"},
    "black-forest-labs/FLUX.2-pro": {"price": 0.03, "name": "FLUX.2 Pro", "api": "Together.ai"},
    "black-forest-labs/FLUX.1-schnell": {"price": 0.02, "name": "FLUX.1 Schnell", "api": "Together.ai"},
    "black-forest-labs/FLUX.1.1-pro": {"price": 0.04, "name": "FLUX 1.1 Pro", "api": "Together.ai"},
    # Google ImageFX (무료)
    "IMAGEN_4": {"price": 0.0, "name": "Imagen 4", "api": "Google ImageFX"},
    "IMAGEN_3_5": {"price": 0.0, "name": "Imagen 3.5", "api": "Google ImageFX"},
    "IMAGEN_3_1": {"price": 0.0, "name": "Imagen 3.1", "api": "Google ImageFX"},
    "IMAGEN_3": {"price": 0.0, "name": "Imagen 3.0", "api": "Google ImageFX"},
    # OpenAI DALL-E
    "dall-e-3": {"price": 0.04, "name": "DALL-E 3", "api": "OpenAI"},
    "dall-e-2": {"price": 0.02, "name": "DALL-E 2", "api": "OpenAI"},
    # Stability AI
    "stable-diffusion-xl-1024-v1-0": {"price": 0.002, "name": "SDXL 1.0", "api": "Stability AI"},
    "sd3-large": {"price": 0.035, "name": "SD3 Large", "api": "Stability AI"},
}


def get_model_info(model_id: str) -> dict:
    """모델 정보 반환"""
    return MODEL_PRICING.get(model_id, {
        "price": 0.0,
        "name": model_id.split("/")[-1] if "/" in model_id else model_id,
        "api": "Unknown"
    })


def log_image_generation_start(api_provider: str, model: str, width: int, height: int, prompt: str):
    """이미지 생성 시작 로그"""
    info = get_model_info(model)

    print("=" * 60)
    print(f"[이미지 생성] 🚀 시작")
    print(f"[이미지 생성] 📌 API: {api_provider}")
    print(f"[이미지 생성] 📌 모델: {model}")
    print(f"[이미지 생성] 📌 모델명: {info['name']}")
    if info['price'] > 0:
        print(f"[이미지 생성] 📌 예상 비용: ${info['price']:.4f}/장 (~{int(info['price'] * 1400)}원)")
    else:
        print(f"[이미지 생성] 📌 예상 비용: 무료")
    print(f"[이미지 생성] 📌 크기: {width}x{height}")
    print(f"[이미지 생성] 📌 프롬프트: {prompt[:80]}..." if len(prompt) > 80 else f"[이미지 생성] 📌 프롬프트: {prompt}")
    print("-" * 60)


def log_image_generation_success(elapsed: float, size: int, model: str):
    """이미지 생성 성공 로그"""
    info = get_model_info(model)

    print("-" * 60)
    print(f"[이미지 생성] ✅ 성공!")
    print(f"[이미지 생성]    ⏱️ 소요: {elapsed:.2f}초")
    print(f"[이미지 생성]    📦 크기: {size:,} bytes")
    if info['price'] > 0:
        print(f"[이미지 생성]    💰 비용: ${info['price']:.4f} (~{int(info['price'] * 1400)}원)")
    else:
        print(f"[이미지 생성]    💰 비용: 무료")
    print("=" * 60)


def log_image_generation_error(elapsed: float, error: str, model: str, api_provider: str):
    """이미지 생성 실패 로그"""
    print("-" * 60)
    print(f"[이미지 생성] ❌ 실패!")
    print(f"[이미지 생성]    ⏱️ 소요: {elapsed:.2f}초")
    print(f"[이미지 생성]    📌 API: {api_provider}")
    print(f"[이미지 생성]    📌 모델: {model}")
    print(f"[이미지 생성]    🚫 오류: {error}")
    print("=" * 60)


class ImageAPIManager:
    """통합 이미지 생성 API 매니저"""

    def __init__(self):
        # API 키 로드
        self.together_api_key = os.getenv("TOGETHER_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.stability_api_key = os.getenv("STABILITY_API_KEY")
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
        self.imagefx_cookie = os.getenv("IMAGEFX_COOKIE")

        # ImageFX Authorization 토큰 (권장 방식)
        self.imagefx_auth_token = self._load_imagefx_auth_token()

        # ImageFX 클라이언트 (지연 초기화)
        self._imagefx_client = None

        # Rate limit 추적
        self._last_call_time: Dict[str, float] = {}
        self._rate_limits = {
            "Together.ai FLUX": 1.0,       # FLUX.2 유료 모델 기준 1초 간격
            "Google ImageFX": 3.0,         # ImageFX는 3초 간격 권장
            "OpenAI DALL-E": 1.0,          # 1초 간격
            "Stability AI": 1.0,           # 1초 간격
            "Replicate SDXL": 0.5,         # 0.5초 간격
        }

    def _load_imagefx_auth_token(self) -> str:
        """ImageFX Authorization 토큰 로드 (환경변수 > 파일 순서)"""
        # 1. 환경 변수에서 먼저 확인
        env_token = os.getenv("IMAGEFX_AUTH_TOKEN", "").strip()
        if env_token:
            return env_token

        # 2. config/settings.py의 load 함수 사용
        try:
            from config.settings import load_imagefx_auth_token
            return load_imagefx_auth_token()
        except ImportError:
            pass

        return ""

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
        elif api_provider == "Google ImageFX":
            # v6.0: 쿠키만 필요
            return bool(self.imagefx_cookie)
        elif api_provider == "OpenAI DALL-E":
            return bool(self.openai_api_key)
        elif api_provider == "Stability AI":
            return bool(self.stability_api_key)
        elif api_provider == "Replicate SDXL":
            return bool(self.replicate_api_token)
        return False

    def set_imagefx_cookie(self, cookie: str) -> bool:
        """ImageFX 쿠키 설정"""
        try:
            from utils.imagefx_client import ImageFXClient
            is_valid, _, _ = ImageFXClient.validate_credentials(cookie=cookie)
            if is_valid:
                self.imagefx_cookie = cookie
                self._imagefx_client = None  # 재초기화 필요
                return True
        except ImportError:
            pass
        return False

    def set_imagefx_auth_token(self, token: str) -> bool:
        """ImageFX Authorization 토큰 설정 (권장 방식)"""
        try:
            from utils.imagefx_client import ImageFXClient
            is_valid, _, _ = ImageFXClient.validate_credentials(authorization_token=token)
            if is_valid:
                # Bearer 접두사 제거 후 저장
                clean_token = token.strip()
                if clean_token.lower().startswith("bearer "):
                    clean_token = clean_token[7:].strip()
                self.imagefx_auth_token = clean_token
                self._imagefx_client = None  # 재초기화 필요
                return True
        except ImportError:
            pass
        return False

    def reload_imagefx_credentials(self):
        """ImageFX 인증 정보 다시 로드"""
        self.imagefx_auth_token = self._load_imagefx_auth_token()
        self.imagefx_cookie = os.getenv("IMAGEFX_COOKIE")
        self._imagefx_client = None  # 재초기화 필요

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
            elif api_provider == "Google ImageFX":
                result = self._generate_imagefx(prompt, model, width, height)
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
        min_interval = self._rate_limits.get(api_provider, 1.0)

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

        model = model or "black-forest-labs/FLUX.2-dev"
        api_provider = "Together.ai FLUX"

        # 로그: 생성 시작
        log_image_generation_start(api_provider, model, width, height, prompt)
        start_time = time.time()

        try:
            from together import Together
            client = Together(api_key=self.together_api_key)

            # FLUX.2 모델은 기본 20 steps
            steps = 20

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
                # 로그: 성공
                elapsed = time.time() - start_time
                log_image_generation_success(elapsed, len(image_data), model)
                return GenerationResult(success=True, image_data=image_data)

            # 로그: 실패 (데이터 없음)
            elapsed = time.time() - start_time
            log_image_generation_error(elapsed, "No image data returned", model, api_provider)
            return GenerationResult(success=False, error="No image data returned")

        except Exception as e:
            # 로그: 실패 (예외)
            elapsed = time.time() - start_time
            log_image_generation_error(elapsed, str(e), model, api_provider)
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

        model = model or "dall-e-3"
        api_provider = "OpenAI DALL-E"

        # DALL-E 3는 size 제한이 있음
        if width >= 1792 or height >= 1792:
            if width > height:
                size = "1792x1024"
                actual_width, actual_height = 1792, 1024
            else:
                size = "1024x1792"
                actual_width, actual_height = 1024, 1792
        else:
            size = "1024x1024"
            actual_width, actual_height = 1024, 1024

        # 로그: 생성 시작
        log_image_generation_start(api_provider, model, actual_width, actual_height, prompt)
        start_time = time.time()

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.openai_api_key)

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
                # 로그: 성공
                elapsed = time.time() - start_time
                log_image_generation_success(elapsed, len(image_data), model)
                return GenerationResult(success=True, image_data=image_data)

            # 로그: 실패 (데이터 없음)
            elapsed = time.time() - start_time
            log_image_generation_error(elapsed, "No image data returned", model, api_provider)
            return GenerationResult(success=False, error="No image data returned")

        except Exception as e:
            # 로그: 실패 (예외)
            elapsed = time.time() - start_time
            log_image_generation_error(elapsed, str(e), model, api_provider)
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

        engine_id = model or "stable-diffusion-xl-1024-v1-0"
        api_provider = "Stability AI"

        # 크기 조정 (64의 배수로)
        width = (width // 64) * 64
        height = (height // 64) * 64
        width = max(512, min(1024, width))
        height = max(512, min(1024, height))

        # 로그: 생성 시작
        log_image_generation_start(api_provider, engine_id, width, height, prompt)
        start_time = time.time()

        try:
            url = f"https://api.stability.ai/v1/generation/{engine_id}/text-to-image"

            headers = {
                "Authorization": f"Bearer {self.stability_api_key}",
                "Content-Type": "application/json"
            }

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
                    # 로그: 성공
                    elapsed = time.time() - start_time
                    log_image_generation_success(elapsed, len(image_data), engine_id)
                    return GenerationResult(success=True, image_data=image_data)

            # 로그: 실패 (API 에러)
            elapsed = time.time() - start_time
            error_msg = f"API Error: {response.status_code} - {response.text}"
            log_image_generation_error(elapsed, error_msg, engine_id, api_provider)
            return GenerationResult(success=False, error=error_msg)

        except Exception as e:
            # 로그: 실패 (예외)
            elapsed = time.time() - start_time
            log_image_generation_error(elapsed, str(e), engine_id, api_provider)
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

        model = model or "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b"
        api_provider = "Replicate SDXL"

        # 로그: 생성 시작
        log_image_generation_start(api_provider, model, width, height, prompt)
        start_time = time.time()

        try:
            import replicate

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
                    # 로그: 성공
                    elapsed = time.time() - start_time
                    log_image_generation_success(elapsed, len(response.content), model)
                    return GenerationResult(success=True, image_data=response.content, image_url=image_url)

            # 로그: 실패 (이미지 없음)
            elapsed = time.time() - start_time
            log_image_generation_error(elapsed, "No image generated", model, api_provider)
            return GenerationResult(success=False, error="No image generated")

        except Exception as e:
            # 로그: 실패 (예외)
            elapsed = time.time() - start_time
            log_image_generation_error(elapsed, str(e), model, api_provider)
            return GenerationResult(success=False, error=str(e))

    # ═══════════════════════════════════════════════════════
    # Google ImageFX (Imagen)
    # ═══════════════════════════════════════════════════════
    def _generate_imagefx(
        self,
        prompt: str,
        model: str,
        width: int,
        height: int
    ) -> GenerationResult:
        """Google ImageFX (Imagen) 이미지 생성 (v6.0 - Node.js 래퍼)"""

        # v6.0: 쿠키만 필요
        if not self.imagefx_cookie:
            return GenerationResult(
                success=False,
                error="ImageFX 쿠키가 설정되지 않았습니다. "
                      "Cookie Editor → Export → Header String으로 쿠키를 추출해주세요."
            )

        model = model or "IMAGEN_4"
        api_provider = "Google ImageFX"

        # 로그: 생성 시작
        log_image_generation_start(api_provider, model, width, height, prompt)
        start_time = time.time()

        try:
            from utils.imagefx_client import (
                ImageFXClient,
                ImagenModel,
                AspectRatio,
                get_aspect_ratio_for_size,
                ImageFXError,
                create_imagefx_client
            )

            # 클라이언트 초기화 (v6.0: 쿠키 기반)
            if self._imagefx_client is None:
                self._imagefx_client = create_imagefx_client(
                    cookie=self.imagefx_cookie  # v6.0: 쿠키 기반 인증
                )

            # 모델 설정
            model_enum = ImagenModel[model] if model else ImagenModel.IMAGEN_4

            # 비율 설정 (크기 기반 자동 선택)
            aspect_ratio = get_aspect_ratio_for_size(width, height)

            print(f"[ImageFX v6.0] Node.js 래퍼 호출 중...")
            print(f"  비율: {aspect_ratio.value}")

            # 이미지 생성
            images = self._imagefx_client.generate_image(
                prompt=prompt,
                model=model_enum,
                aspect_ratio=aspect_ratio,
                num_images=1
            )

            if images and len(images) > 0:
                image_data = images[0].get_bytes()
                # 로그: 성공
                elapsed = time.time() - start_time
                log_image_generation_success(elapsed, len(image_data), model)
                return GenerationResult(success=True, image_data=image_data)

            # 로그: 실패 (이미지 없음)
            elapsed = time.time() - start_time
            log_image_generation_error(elapsed, "이미지가 생성되지 않았습니다.", model, api_provider)
            return GenerationResult(success=False, error="이미지가 생성되지 않았습니다.")

        except ImportError as e:
            elapsed = time.time() - start_time
            error_msg = f"ImageFX 클라이언트 모듈을 찾을 수 없습니다: {e}"
            log_image_generation_error(elapsed, error_msg, model, api_provider)
            return GenerationResult(success=False, error=error_msg)
        except Exception as e:
            elapsed = time.time() - start_time
            # 401 오류인 경우 힌트 제공
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                error_msg += " (Authorization 토큰이 만료되었거나 유효하지 않습니다)"
            log_image_generation_error(elapsed, error_msg, model, api_provider)
            return GenerationResult(success=False, error=error_msg)

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
