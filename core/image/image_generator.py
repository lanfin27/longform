"""
통합 이미지 생성기

지원 API:
- Together.ai (FLUX)
- OpenAI (DALL-E 3, DALL-E 2)
- Google (Imagen 3 via Vertex AI)
- Google ImageFX (Imagen via Cookie)
"""
import os
import base64
import time
import requests
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, field


@dataclass
class ImageConfig:
    """이미지 생성 설정"""
    provider: str = "together"
    model: str = "black-forest-labs/FLUX.1-schnell-Free"
    width: int = 1024
    height: int = 1024
    steps: int = 4
    num_inference_steps: int = 4  # alias for steps
    negative_prompt: str = ""
    style_preset: str = ""
    seed: int = None

    def __post_init__(self):
        # steps와 num_inference_steps 동기화
        if self.num_inference_steps != 4:
            self.steps = self.num_inference_steps


@dataclass
class ImageResult:
    """이미지 생성 결과"""
    success: bool
    image_path: str = ""
    path: str = ""  # alias for image_path
    prompt: str = ""
    model: str = ""
    provider: str = ""
    error: str = ""
    generation_time: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        # path와 image_path 동기화
        if self.image_path and not self.path:
            self.path = self.image_path
        elif self.path and not self.image_path:
            self.image_path = self.path

    def get(self, key: str, default=None):
        """딕셔너리 스타일 접근 지원"""
        return getattr(self, key, default)


class ImageGenerator:
    """통합 이미지 생성기"""

    # 제공자별 모델 목록
    MODELS = {
        "together": {
            "FLUX.2 Dev": "black-forest-labs/FLUX.2-dev",
            "FLUX.2 Flex": "black-forest-labs/FLUX.2-flex",
            "FLUX.2 Pro": "black-forest-labs/FLUX.2-pro",
        },
        "imagefx": {
            "Imagen 4": "IMAGEN_4",
            "Imagen 3.5": "IMAGEN_3_5",
            "Imagen 3.1": "IMAGEN_3_1",
            "Imagen 3.0": "IMAGEN_3",
        },
        "openai": {
            "DALL-E 3": "dall-e-3",
            "DALL-E 2": "dall-e-2",
        },
        "google": {
            "Imagen 3": "imagen-3.0-generate-001",
        }
    }

    def __init__(self, config: ImageConfig = None):
        self.config = config or ImageConfig()
        self._clients = {}
        self._init_clients()

    def _init_clients(self):
        """클라이언트 초기화"""
        # Together.ai
        together_key = os.environ.get("TOGETHER_API_KEY")
        if together_key:
            try:
                from together import Together
                self._clients["together"] = Together(api_key=together_key)
            except ImportError:
                # SDK 없이 직접 API 호출
                self._clients["together_key"] = together_key
            except Exception as e:
                print(f"Together init failed: {e}")

        # OpenAI
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import OpenAI
                self._clients["openai"] = OpenAI(api_key=openai_key)
            except ImportError:
                self._clients["openai_key"] = openai_key
            except Exception as e:
                print(f"OpenAI init failed: {e}")

        # Google
        google_key = os.environ.get("GOOGLE_API_KEY")
        if google_key:
            self._clients["google_key"] = google_key

        # Google ImageFX (Cookie-based)
        imagefx_cookie = os.environ.get("IMAGEFX_COOKIE")
        if imagefx_cookie:
            self._clients["imagefx_cookie"] = imagefx_cookie

    def generate(
        self,
        prompt: str,
        output_path: str = None,
        config: ImageConfig = None
    ) -> ImageResult:
        """
        이미지 생성

        Args:
            prompt: 이미지 생성 프롬프트
            output_path: 저장 경로 (없으면 임시 경로 사용)
            config: 이미지 설정 (없으면 기본 설정 사용)

        Returns:
            ImageResult: 생성 결과
        """
        cfg = config or self.config
        start_time = time.time()

        # === 디버깅: generate() 진입점에서 프롬프트 확인 ===
        print("\n" + "=" * 60)
        print("[ImageGenerator.generate] 호출됨")
        print(f"받은 프롬프트 (앞 200자): {prompt[:200] if len(prompt) > 200 else prompt}")
        print(f"프롬프트 전체 길이: {len(prompt)} 문자")
        print(f"Provider: {cfg.provider}")
        print(f"Model: {cfg.model}")
        print("=" * 60)

        # 출력 경로 설정
        if not output_path:
            output_dir = Path("temp/images")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"generated_{int(time.time())}.png")

        try:
            if cfg.provider == "together":
                result = self._generate_together(prompt, output_path, cfg)
            elif cfg.provider == "imagefx":
                result = self._generate_imagefx(prompt, output_path, cfg)
            elif cfg.provider == "openai":
                result = self._generate_openai(prompt, output_path, cfg)
            elif cfg.provider == "google":
                result = self._generate_google(prompt, output_path, cfg)
            else:
                return ImageResult(
                    success=False,
                    error=f"Unknown provider: {cfg.provider}"
                )

            result.generation_time = time.time() - start_time
            return result

        except Exception as e:
            import traceback
            print(f"[ImageGenerator.generate] 예외 발생: {str(e)}")
            return ImageResult(
                success=False,
                prompt=prompt,
                provider=cfg.provider,
                model=cfg.model,
                error=str(e),
                generation_time=time.time() - start_time,
                metadata={"traceback": traceback.format_exc()}
            )

    def generate_image(
        self,
        prompt: str,
        config: ImageConfig = None
    ) -> ImageResult:
        """
        이미지 생성 (경로 자동 생성)

        Args:
            prompt: 이미지 생성 프롬프트
            config: 이미지 설정

        Returns:
            ImageResult: 생성 결과
        """
        return self.generate(prompt, None, config)

    def _generate_together(
        self,
        prompt: str,
        output_path: str,
        config: ImageConfig
    ) -> ImageResult:
        """Together.ai (FLUX) 이미지 생성"""

        # === 디버깅: 받은 프롬프트 확인 ===
        print("\n" + "=" * 60)
        print("[ImageGenerator._generate_together] 호출됨")
        print(f"받은 프롬프트 (앞 300자): {prompt[:300] if len(prompt) > 300 else prompt}")
        print(f"프롬프트 전체 길이: {len(prompt)} 문자")
        print(f"모델: {config.model}")
        print(f"크기: {config.width}x{config.height}")
        print("=" * 60)

        client = self._clients.get("together")
        api_key = self._clients.get("together_key") or os.environ.get("TOGETHER_API_KEY")

        # 크기 제한 (FLUX는 최대 1440)
        width = min(config.width, 1440)
        height = min(config.height, 1440)

        if client:
            # SDK 사용
            try:
                print(f"[ImageGenerator] SDK 호출 - prompt 전달 중...")
                response = client.images.generate(
                    model=config.model,
                    prompt=prompt,
                    width=width,
                    height=height,
                    steps=config.steps,
                    n=1,
                    response_format="b64_json"
                )
                image_data = base64.b64decode(response.data[0].b64_json)
                print(f"[ImageGenerator] SDK 성공 - 이미지 데이터 수신")
            except Exception as e:
                print(f"[ImageGenerator] SDK 오류: {str(e)}")
                return ImageResult(
                    success=False,
                    prompt=prompt,
                    model=config.model,
                    provider="together",
                    error=f"Together SDK error: {str(e)}"
                )
        elif api_key:
            # 직접 API 호출
            try:
                payload = {
                    "model": config.model,
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "steps": config.steps if config.steps else 4,
                    "n": 1,
                    "response_format": "b64_json"
                }

                # 네거티브 프롬프트 추가
                if config.negative_prompt:
                    payload["negative_prompt"] = config.negative_prompt

                print(f"[ImageGenerator] API 호출 - payload prompt 길이: {len(payload['prompt'])} 문자")

                response = requests.post(
                    "https://api.together.xyz/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=120
                )

                print(f"[ImageGenerator] API 응답 상태: {response.status_code}")

                if response.status_code != 200:
                    error_text = response.text
                    print(f"[ImageGenerator] API 오류: {error_text[:500]}")
                    return ImageResult(
                        success=False,
                        prompt=prompt,
                        model=config.model,
                        provider="together",
                        error=f"API error {response.status_code}: {error_text}"
                    )

                data = response.json()
                image_data = base64.b64decode(data["data"][0]["b64_json"])
                print(f"[ImageGenerator] API 성공 - 이미지 데이터 수신")

            except Exception as e:
                print(f"[ImageGenerator] API 예외: {str(e)}")
                import traceback
                return ImageResult(
                    success=False,
                    prompt=prompt,
                    model=config.model,
                    provider="together",
                    error=f"Together API error: {str(e)}",
                    metadata={"traceback": traceback.format_exc()}
                )
        else:
            return ImageResult(
                success=False,
                error="TOGETHER_API_KEY not set"
            )

        # 파일 저장
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(image_data)

        return ImageResult(
            success=True,
            image_path=output_path,
            path=output_path,
            prompt=prompt,
            model=config.model,
            provider="together"
        )

    def _generate_openai(
        self,
        prompt: str,
        output_path: str,
        config: ImageConfig
    ) -> ImageResult:
        """OpenAI (DALL-E) 이미지 생성"""

        # === 디버깅: 받은 프롬프트 확인 ===
        print("\n" + "=" * 60)
        print("[ImageGenerator._generate_openai] 호출됨")
        print(f"받은 프롬프트 (앞 300자): {prompt[:300] if len(prompt) > 300 else prompt}")
        print(f"프롬프트 전체 길이: {len(prompt)} 문자")
        print(f"모델: {config.model}")
        print("=" * 60)

        client = self._clients.get("openai")
        api_key = self._clients.get("openai_key") or os.environ.get("OPENAI_API_KEY")

        if not client and not api_key:
            return ImageResult(
                success=False,
                error="OPENAI_API_KEY not set"
            )

        # DALL-E 크기 변환
        if config.model == "dall-e-3":
            # DALL-E 3: 1024x1024, 1792x1024, 1024x1792
            if config.width >= 1792 or config.height >= 1792:
                if config.width > config.height:
                    size = "1792x1024"
                else:
                    size = "1024x1792"
            else:
                size = "1024x1024"
        else:
            # DALL-E 2: 256x256, 512x512, 1024x1024
            if config.width <= 256:
                size = "256x256"
            elif config.width <= 512:
                size = "512x512"
            else:
                size = "1024x1024"

        try:
            if client:
                # SDK 사용
                print(f"[ImageGenerator] OpenAI SDK 호출 - prompt 전달 중...")
                response = client.images.generate(
                    model=config.model,
                    prompt=prompt,
                    size=size,
                    quality="standard",
                    n=1,
                    response_format="b64_json"
                )
                image_data = base64.b64decode(response.data[0].b64_json)
                print(f"[ImageGenerator] OpenAI SDK 성공")
            else:
                # 직접 API 호출
                print(f"[ImageGenerator] OpenAI API 호출 - prompt 길이: {len(prompt)} 문자")
                response = requests.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": config.model,
                        "prompt": prompt,
                        "size": size,
                        "quality": "standard",
                        "n": 1,
                        "response_format": "b64_json"
                    },
                    timeout=120
                )

                print(f"[ImageGenerator] OpenAI API 응답 상태: {response.status_code}")

                if response.status_code != 200:
                    error_text = response.text
                    print(f"[ImageGenerator] OpenAI API 오류: {error_text[:500]}")
                    return ImageResult(
                        success=False,
                        prompt=prompt,
                        model=config.model,
                        provider="openai",
                        error=f"API error {response.status_code}: {error_text}"
                    )

                data = response.json()
                image_data = base64.b64decode(data["data"][0]["b64_json"])
                print(f"[ImageGenerator] OpenAI API 성공 - 이미지 데이터 수신")

        except Exception as e:
            return ImageResult(
                success=False,
                prompt=prompt,
                model=config.model,
                provider="openai",
                error=f"OpenAI error: {str(e)}"
            )

        # 파일 저장
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(image_data)

        return ImageResult(
            success=True,
            image_path=output_path,
            path=output_path,
            prompt=prompt,
            model=config.model,
            provider="openai"
        )

    def _generate_google(
        self,
        prompt: str,
        output_path: str,
        config: ImageConfig
    ) -> ImageResult:
        """Google (Imagen 3) 이미지 생성"""

        api_key = self._clients.get("google_key") or os.environ.get("GOOGLE_API_KEY")

        if not api_key:
            return ImageResult(
                success=False,
                error="GOOGLE_API_KEY not set"
            )

        # aspect ratio 계산
        if config.width > config.height:
            aspect_ratio = "16:9"
        elif config.width < config.height:
            aspect_ratio = "9:16"
        else:
            aspect_ratio = "1:1"

        try:
            # Imagen 3 API 호출 (Generative AI API)
            # 참고: Imagen 3은 현재 Vertex AI를 통해서만 사용 가능하거나
            # google-generativeai SDK의 ImageGenerationModel을 통해 사용

            # 방법 1: google-generativeai SDK 사용 시도
            try:
                import google.generativeai as genai

                genai.configure(api_key=api_key)

                # Imagen 모델 사용
                imagen = genai.ImageGenerationModel(config.model)

                response = imagen.generate_images(
                    prompt=prompt,
                    number_of_images=1,
                    aspect_ratio=aspect_ratio
                )

                # 이미지 저장
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                response.images[0].save(output_path)

                return ImageResult(
                    success=True,
                    image_path=output_path,
                    path=output_path,
                    prompt=prompt,
                    model=config.model,
                    provider="google"
                )

            except ImportError:
                pass  # SDK 없으면 REST API 시도
            except AttributeError:
                pass  # ImageGenerationModel이 없으면 REST API 시도
            except Exception as sdk_error:
                # SDK 오류면 REST API 시도
                pass

            # 방법 2: REST API 직접 호출 (Vertex AI 또는 Generative Language API)
            # Imagen 3는 현재 Vertex AI에서만 지원됨
            # 대안으로 에러 메시지 반환

            return ImageResult(
                success=False,
                prompt=prompt,
                model=config.model,
                provider="google",
                error="Imagen 3는 현재 Vertex AI를 통해서만 사용 가능합니다. "
                      "google-cloud-aiplatform 패키지 설치 및 GCP 프로젝트 설정이 필요합니다. "
                      "대안으로 FLUX 또는 DALL-E를 사용해주세요."
            )

        except Exception as e:
            return ImageResult(
                success=False,
                prompt=prompt,
                model=config.model,
                provider="google",
                error=f"Google Imagen error: {str(e)}"
            )

    def _generate_imagefx(
        self,
        prompt: str,
        output_path: str,
        config: ImageConfig
    ) -> ImageResult:
        """Google ImageFX (Imagen) 이미지 생성 - 쿠키 기반"""

        # === 디버깅: 받은 프롬프트 확인 ===
        print("\n" + "=" * 60)
        print("[ImageGenerator._generate_imagefx] 호출됨")
        print(f"받은 프롬프트 (앞 300자): {prompt[:300] if len(prompt) > 300 else prompt}")
        print(f"프롬프트 전체 길이: {len(prompt)} 문자")
        print(f"모델: {config.model}")
        print("=" * 60)

        cookie = self._clients.get("imagefx_cookie") or os.environ.get("IMAGEFX_COOKIE")

        if not cookie:
            return ImageResult(
                success=False,
                prompt=prompt,
                model=config.model,
                provider="imagefx",
                error="IMAGEFX_COOKIE가 설정되지 않았습니다. "
                      "labs.google에서 쿠키를 추출해주세요."
            )

        try:
            from utils.imagefx_client import (
                ImageFXClient,
                ImagenModel,
                get_aspect_ratio_for_size
            )

            client = ImageFXClient(cookie)

            # 모델 설정
            try:
                model_enum = ImagenModel[config.model] if config.model else ImagenModel.IMAGEN_4
            except KeyError:
                model_enum = ImagenModel.IMAGEN_4

            # 비율 설정 (크기 기반 자동 선택)
            aspect_ratio = get_aspect_ratio_for_size(config.width, config.height)

            print(f"[ImageFX] 이미지 생성 시작")
            print(f"  모델: {model_enum.value}")
            print(f"  비율: {aspect_ratio.value}")

            # 이미지 생성
            images = client.generate_image(
                prompt=prompt,
                model=model_enum,
                aspect_ratio=aspect_ratio,
                num_images=1
            )

            if not images:
                return ImageResult(
                    success=False,
                    prompt=prompt,
                    model=config.model,
                    provider="imagefx",
                    error="이미지가 생성되지 않았습니다."
                )

            # 이미지 저장
            image_data = images[0].get_bytes()
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(image_data)

            print(f"[ImageFX] ✅ 이미지 저장 완료: {output_path}")

            return ImageResult(
                success=True,
                image_path=output_path,
                path=output_path,
                prompt=prompt,
                model=config.model,
                provider="imagefx"
            )

        except ImportError:
            return ImageResult(
                success=False,
                prompt=prompt,
                model=config.model,
                provider="imagefx",
                error="ImageFX 클라이언트 모듈을 찾을 수 없습니다. "
                      "utils/imagefx_client.py 파일을 확인해주세요."
            )
        except Exception as e:
            import traceback
            print(f"[ImageFX] ❌ 오류: {str(e)}")
            return ImageResult(
                success=False,
                prompt=prompt,
                model=config.model,
                provider="imagefx",
                error=f"ImageFX error: {str(e)}",
                metadata={"traceback": traceback.format_exc()}
            )

    def generate_batch(
        self,
        prompts: List[str],
        output_dir: str,
        config: ImageConfig = None,
        on_progress=None
    ) -> List[ImageResult]:
        """
        배치 이미지 생성

        Args:
            prompts: 프롬프트 리스트
            output_dir: 출력 디렉토리
            config: 이미지 설정
            on_progress: 진행 콜백 (current, total, result)

        Returns:
            List[ImageResult]: 결과 리스트
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results = []
        total = len(prompts)
        cfg = config or self.config

        for i, prompt in enumerate(prompts):
            # 파일명 생성
            filename = f"image_{i+1:03d}.png"
            file_path = output_path / filename

            # 이미지 생성
            result = self.generate(prompt, str(file_path), cfg)
            results.append(result)

            # 콜백 호출
            if on_progress:
                on_progress(i + 1, total, result)

            # Rate limit 대기 (무료 모델인 경우)
            if "Free" in cfg.model or cfg.provider == "together":
                if i < total - 1:  # 마지막이 아닌 경우에만 대기
                    time.sleep(6)  # Together Free는 분당 10개 제한

        return results

    @classmethod
    def get_available_models(cls, provider: str = None) -> Dict:
        """사용 가능한 모델 목록"""
        if provider:
            return cls.MODELS.get(provider, {})
        return cls.MODELS

    @classmethod
    def get_default_config(cls, provider: str = "together") -> ImageConfig:
        """기본 설정 반환"""
        if provider == "together":
            return ImageConfig(
                provider="together",
                model="black-forest-labs/FLUX.2-dev",
                width=1024,
                height=1024
            )
        elif provider == "imagefx":
            return ImageConfig(
                provider="imagefx",
                model="IMAGEN_4",
                width=1280,
                height=720
            )
        elif provider == "openai":
            return ImageConfig(
                provider="openai",
                model="dall-e-3",
                width=1024,
                height=1024
            )
        elif provider == "google":
            return ImageConfig(
                provider="google",
                model="imagen-3.0-generate-001",
                width=1024,
                height=1024
            )
        return ImageConfig()

    @staticmethod
    def check_api_key(provider: str) -> bool:
        """API 키 확인"""
        if provider == "together":
            return bool(os.environ.get("TOGETHER_API_KEY"))
        elif provider == "imagefx":
            return bool(os.environ.get("IMAGEFX_COOKIE"))
        elif provider == "openai":
            return bool(os.environ.get("OPENAI_API_KEY"))
        elif provider == "google":
            return bool(os.environ.get("GOOGLE_API_KEY"))
        return False
