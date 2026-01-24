# -*- coding: utf-8 -*-
"""
utils/gemini_image_generator.py
Gemini 이미지 생성 API 클라이언트 v2.1

지원 모델 (2026-01 업데이트):
- gemini-2.5-flash-image (Nano Banana) ← 이전: gemini-2.0-flash-exp-image-generation
- gemini-3-pro-image-preview (Nano Banana Pro) ← 이전: gemini-2.0-flash-preview-image-generation

특징:
- 새로운 genai.Client() API 사용
- 레퍼런스 이미지 인식 (스타일/캐릭터/구도 참조)
- 텍스트 + 이미지 멀티모달 입력
- 한국어 프롬프트 지원

v2.1 변경사항:
- SDK 버전 호환성 처리 (새 SDK 1.0+ / 이전 SDK 0.x 모두 지원)
- ImportError 방지를 위한 동적 import 로직

작성: 2025-01
업데이트: 2026-01 - 새로운 모델명 및 API 방식 적용
"""

import os
import io
import base64
from pathlib import Path
from typing import List, Optional, Dict, Union
from dataclasses import dataclass
from PIL import Image

# dotenv 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# Gemini 이미지 생성 모델 정의 (2026-01 업데이트)
GEMINI_IMAGE_MODELS = {
    "gemini_nano_banana": {
        "model_id": "gemini-2.5-flash-image",  # 새 모델명
        "display_name": "Gemini Nano Banana",
        "description": "빠른 이미지 생성, 레퍼런스 인식",
        "supports_reference": True,
        "cost_per_image": "~15원",
        "max_references": 5
    },
    "gemini_nano_banana_pro": {
        "model_id": "gemini-3-pro-image-preview",  # 새 모델명
        "display_name": "Gemini Nano Banana Pro",
        "description": "고품질 이미지 생성, 레퍼런스 인식",
        "supports_reference": True,
        "cost_per_image": "~25원",
        "max_references": 5
    }
}

# 이전 모델명 호환성 매핑
LEGACY_MODEL_MAPPING = {
    "gemini-2.0-flash-exp-image-generation": "gemini-2.5-flash-image",
    "gemini-2.0-flash-preview-image-generation": "gemini-3-pro-image-preview",
}

# 지원되는 가로세로 비율
SUPPORTED_ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]


@dataclass
class GeminiGenerationResult:
    """Gemini 이미지 생성 결과"""
    success: bool
    image_data: Optional[bytes] = None
    model: str = ""
    prompt: str = ""
    error: Optional[str] = None
    elapsed_time: float = 0


class GeminiImageGenerator:
    """Gemini 이미지 생성 클라이언트"""

    def __init__(self, api_key: str = None):
        """
        초기화

        Args:
            api_key: Gemini API 키 (None이면 환경변수에서 로드)
        """
        self.api_key = api_key or self._load_api_key()

        if not self.api_key:
            raise ValueError(
                "Gemini API 키가 설정되지 않았습니다. "
                ".env 파일에 GEMINI_API_KEY를 설정하세요."
            )

        # google-generativeai 라이브러리 초기화
        self._init_genai()

    def _load_api_key(self) -> str:
        """환경변수에서 API 키 로드"""
        # 환경변수에서 로드
        api_key = os.getenv("GEMINI_API_KEY", "")

        if not api_key:
            # streamlit session_state에서 시도
            try:
                import streamlit as st
                api_key = st.session_state.get('gemini_api_key', '')
            except:
                pass

        return api_key

    def _init_genai(self):
        """google-generativeai 라이브러리 초기화 (SDK 버전 자동 감지)"""
        self._new_sdk = False
        self._client = None
        self._types = None
        self._genai = None
        self._model = None  # 이전 SDK용 모델 객체

        # 방법 1: 새 SDK (1.0+) 시도
        try:
            from google import genai
            from google.genai import types

            # 새로운 Client API 사용
            self._client = genai.Client(api_key=self.api_key)
            self._types = types
            self._genai = genai
            self._new_sdk = True

            print("[GeminiImage] ✅ 새 SDK (google.genai) 초기화 완료")
            return

        except ImportError:
            print("[GeminiImage] ⚠️ 새 SDK import 실패, 이전 SDK 시도...")

        # 방법 2: 이전 SDK (0.x) 사용
        try:
            import google.generativeai as genai

            # 이전 SDK 설정
            genai.configure(api_key=self.api_key)
            self._genai = genai
            self._new_sdk = False

            print("[GeminiImage] ✅ 이전 SDK (google.generativeai) 초기화 완료")
            return

        except ImportError:
            pass

        # 둘 다 실패
        raise ImportError(
            "google-generativeai 패키지가 필요합니다.\n"
            "pip install --upgrade google-generativeai 로 설치하세요."
        )

    def generate_image(
        self,
        prompt: str,
        model_key: str = "gemini_nano_banana",
        reference_images: List[Union[str, bytes, Image.Image]] = None,
        reference_type: str = "style",
        reference_strength: float = 0.8,
        width: int = 1024,
        height: int = 1024,
        negative_prompt: str = None,
        aspect_ratio: str = None
    ) -> GeminiGenerationResult:
        """
        Gemini로 이미지 생성 (새로운 Client API 사용)

        Args:
            prompt: 이미지 생성 프롬프트
            model_key: 모델 키 (gemini_nano_banana, gemini_nano_banana_pro)
            reference_images: 레퍼런스 이미지 목록 (경로, bytes, PIL Image)
            reference_type: 레퍼런스 타입 (style, character, composition)
            reference_strength: 레퍼런스 강도 (0.0 ~ 1.0)
            width: 출력 이미지 너비
            height: 출력 이미지 높이
            negative_prompt: 네거티브 프롬프트
            aspect_ratio: 가로세로 비율 (예: "16:9", "1:1")

        Returns:
            GeminiGenerationResult
        """
        import time
        start_time = time.time()

        try:
            # 모델 설정 확인
            model_config = GEMINI_IMAGE_MODELS.get(model_key)
            if not model_config:
                return GeminiGenerationResult(
                    success=False,
                    error=f"알 수 없는 모델: {model_key}",
                    model=model_key,
                    prompt=prompt
                )

            model_id = model_config["model_id"]

            # 이전 모델명 호환성 체크
            if model_id in LEGACY_MODEL_MAPPING:
                old_model_id = model_id
                model_id = LEGACY_MODEL_MAPPING[model_id]
                print(f"[GeminiImage] ⚠️ 모델명 변환: {old_model_id} → {model_id}")

            print(f"[GeminiImage] 🚀 이미지 생성 시작 (새로운 API)")
            print(f"[GeminiImage]    모델: {model_id}")
            print(f"[GeminiImage]    프롬프트: {prompt[:60]}...")
            if reference_images:
                print(f"[GeminiImage]    레퍼런스: {len(reference_images)}개 ({reference_type}, {reference_strength*100:.0f}%)")

            # 프롬프트 구성
            full_prompt = self._build_prompt(
                prompt=prompt,
                reference_type=reference_type,
                reference_strength=reference_strength,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                has_reference=bool(reference_images)
            )

            # 입력 콘텐츠 구성
            contents = []

            # 레퍼런스 이미지 추가 (PIL Image 형태로)
            if reference_images:
                max_refs = model_config.get("max_references", 5)
                for ref_img in reference_images[:max_refs]:
                    pil_image = self._load_image_as_pil(ref_img)
                    if pil_image:
                        contents.append(pil_image)
                        print(f"[GeminiImage]    레퍼런스 이미지 추가됨")

            # 텍스트 프롬프트 추가
            contents.append(full_prompt)

            # 가로세로 비율 계산
            if not aspect_ratio:
                ratio = width / height
                if abs(ratio - 16/9) < 0.1:
                    aspect_ratio = "16:9"
                elif abs(ratio - 9/16) < 0.1:
                    aspect_ratio = "9:16"
                elif abs(ratio - 1) < 0.1:
                    aspect_ratio = "1:1"
                else:
                    aspect_ratio = "16:9"  # 기본값

            # 지원되지 않는 비율이면 16:9로 변경
            if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
                print(f"[GeminiImage] ⚠️ 지원되지 않는 비율 {aspect_ratio}, 16:9로 변경")
                aspect_ratio = "16:9"

            print(f"[GeminiImage]    가로세로 비율: {aspect_ratio}")
            print(f"[GeminiImage]    SDK 버전: {'새 SDK' if self._new_sdk else '이전 SDK'}")

            # SDK 버전에 따라 다른 API 사용
            image_data = None
            text_response = ""

            if self._new_sdk:
                # ══════════════════════════════════════════════════════════
                # 새 SDK (1.0+): genai.Client API 사용
                # ══════════════════════════════════════════════════════════
                response = self._client.models.generate_content(
                    model=model_id,
                    contents=contents,
                    config=self._types.GenerateContentConfig(
                        response_modalities=['TEXT', 'IMAGE'],
                        image_config=self._types.ImageConfig(
                            aspect_ratio=aspect_ratio
                        )
                    )
                )

                # 응답에서 이미지 추출 (새로운 방식)
                for part in response.parts:
                    if part.text is not None:
                        text_response = part.text
                        print(f"[GeminiImage]    텍스트 응답: {text_response[:100]}...")

                    elif part.inline_data is not None:
                        # 새로운 API: part.as_image()로 이미지 추출
                        try:
                            pil_image = part.as_image()
                            # PIL Image를 bytes로 변환
                            buffer = io.BytesIO()
                            pil_image.save(buffer, format="PNG")
                            image_data = buffer.getvalue()
                            print(f"[GeminiImage] ✅ 이미지 추출 성공 (part.as_image())")
                        except Exception as img_err:
                            print(f"[GeminiImage] ⚠️ as_image() 실패, 직접 추출 시도: {img_err}")
                            # 폴백: 직접 데이터 추출
                            if hasattr(part.inline_data, 'data'):
                                image_data = part.inline_data.data

            else:
                # ══════════════════════════════════════════════════════════
                # 이전 SDK (0.x): google.generativeai 사용
                # ⚠️ 중요: 이전 SDK는 Nano Banana 이미지 생성을 지원하지 않습니다!
                # ══════════════════════════════════════════════════════════
                print(f"[GeminiImage] ❌ 이전 SDK는 Nano Banana 이미지 생성을 지원하지 않습니다!")
                print(f"[GeminiImage] 💡 해결방법: pip install google-genai --upgrade 실행 후 재시작")
                print(f"[GeminiImage] 📝 이전 SDK(google.generativeai)는 텍스트 전용 모델만 지원합니다.")

                return GeminiGenerationResult(
                    success=False,
                    error=(
                        "이전 버전의 Gemini SDK가 설치되어 있습니다. "
                        "Nano Banana 이미지 생성을 위해 새 SDK가 필요합니다.\n"
                        "터미널에서 'pip install google-genai --upgrade' 실행 후 앱을 재시작하세요."
                    ),
                    model=model_id,
                    prompt=prompt,
                    elapsed_time=time.time() - start_time
                )

            elapsed = time.time() - start_time

            if image_data:
                print(f"[GeminiImage] ✅ 성공! ({elapsed:.1f}초, {len(image_data):,} bytes)")
                return GeminiGenerationResult(
                    success=True,
                    image_data=image_data,
                    model=model_id,
                    prompt=prompt,
                    elapsed_time=elapsed
                )
            else:
                error_msg = "이미지 생성 실패: 응답에 이미지가 없습니다."
                if text_response:
                    error_msg += f" (응답: {text_response[:200]})"

                print(f"[GeminiImage] ❌ 실패: {error_msg}")
                return GeminiGenerationResult(
                    success=False,
                    error=error_msg,
                    model=model_id,
                    prompt=prompt,
                    elapsed_time=elapsed
                )

        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            print(f"[GeminiImage] ❌ 예외 발생: {error_msg}")

            import traceback
            traceback.print_exc()

            return GeminiGenerationResult(
                success=False,
                error=error_msg,
                model=model_key,
                prompt=prompt,
                elapsed_time=elapsed
            )

    def _build_prompt(
        self,
        prompt: str,
        reference_type: str,
        reference_strength: float,
        negative_prompt: str,
        width: int,
        height: int,
        has_reference: bool
    ) -> str:
        """프롬프트 구성"""

        parts = []

        # 레퍼런스 지시문
        if has_reference:
            reference_instructions = {
                "style": f"참조 이미지의 스타일(색감, 화풍, 분위기)을 {int(reference_strength * 100)}% 반영하여",
                "character": f"참조 이미지의 캐릭터(외모, 의상, 특징)를 {int(reference_strength * 100)}% 유지하여",
                "composition": f"참조 이미지의 구도(배치, 앵글, 프레이밍)를 {int(reference_strength * 100)}% 참고하여"
            }
            ref_instruction = reference_instructions.get(reference_type, "")
            if ref_instruction:
                parts.append(ref_instruction)

        # 메인 프롬프트
        parts.append(f"다음 이미지를 생성해주세요: {prompt}")

        # 크기 지시 (16:9, 1:1, 9:16 등)
        aspect = width / height
        if abs(aspect - 16/9) < 0.1:
            parts.append("가로 방향(16:9) 이미지로 생성해주세요.")
        elif abs(aspect - 9/16) < 0.1:
            parts.append("세로 방향(9:16) 이미지로 생성해주세요.")
        elif abs(aspect - 1) < 0.1:
            parts.append("정사각형(1:1) 이미지로 생성해주세요.")

        # 네거티브 프롬프트
        if negative_prompt:
            parts.append(f"다음 요소는 피해주세요: {negative_prompt}")

        return " ".join(parts)

    def _load_image_as_pil(self, image_source: Union[str, bytes, Image.Image]) -> Optional[Image.Image]:
        """이미지를 PIL Image로 로드 (새로운 API용)"""

        try:
            pil_image = None

            # 파일 경로인 경우
            if isinstance(image_source, str):
                path = Path(image_source)
                if path.exists():
                    pil_image = Image.open(path)

            # bytes인 경우
            elif isinstance(image_source, bytes):
                pil_image = Image.open(io.BytesIO(image_source))

            # PIL Image인 경우
            elif isinstance(image_source, Image.Image):
                pil_image = image_source

            if pil_image:
                # RGB로 변환 (RGBA인 경우)
                if pil_image.mode == 'RGBA':
                    pil_image = pil_image.convert('RGB')

                # 너무 큰 이미지는 리사이즈
                max_size = 1024
                if pil_image.width > max_size or pil_image.height > max_size:
                    pil_image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

                return pil_image

            return None

        except Exception as e:
            print(f"[GeminiImage] 이미지 로드 실패: {e}")
            return None

    def _prepare_image(self, image_source: Union[str, bytes, Image.Image]):
        """이미지를 Gemini API 형식으로 변환 (레거시 호환용)"""

        try:
            image_bytes = None

            # 파일 경로인 경우
            if isinstance(image_source, str):
                path = Path(image_source)
                if path.exists():
                    with open(path, 'rb') as f:
                        image_bytes = f.read()

            # bytes인 경우
            elif isinstance(image_source, bytes):
                image_bytes = image_source

            # PIL Image인 경우
            elif isinstance(image_source, Image.Image):
                buffer = io.BytesIO()
                image_source.save(buffer, format="PNG")
                image_bytes = buffer.getvalue()

            if image_bytes:
                # PIL로 검증 및 필요시 리사이즈
                img = Image.open(io.BytesIO(image_bytes))

                # 너무 큰 이미지는 리사이즈
                max_size = 1024
                if img.width > max_size or img.height > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    image_bytes = buffer.getvalue()

                # Gemini Part 형식으로 반환
                return {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(image_bytes).decode()
                    }
                }

            return None

        except Exception as e:
            print(f"[GeminiImage] 이미지 준비 실패: {e}")
            return None

    def _extract_image_from_response(self, response) -> Optional[bytes]:
        """응답에서 이미지 데이터 추출 (레거시 호환용)

        Note: 새로운 API에서는 generate_image() 내에서 직접 part.as_image()를 사용합니다.
        이 메서드는 이전 버전과의 호환성을 위해 유지됩니다.
        """

        try:
            # 새로운 API: parts에서 직접 추출
            if hasattr(response, 'parts'):
                for part in response.parts:
                    # 새로운 방식: as_image() 메서드 사용
                    if hasattr(part, 'as_image'):
                        try:
                            pil_image = part.as_image()
                            buffer = io.BytesIO()
                            pil_image.save(buffer, format="PNG")
                            return buffer.getvalue()
                        except:
                            pass

                    # 폴백: inline_data에서 직접 추출
                    if hasattr(part, 'inline_data') and part.inline_data:
                        if hasattr(part.inline_data, 'mime_type'):
                            if part.inline_data.mime_type.startswith('image/'):
                                return part.inline_data.data

            # candidates에서 찾기 (이전 API 호환)
            if hasattr(response, 'candidates'):
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if hasattr(part, 'inline_data') and part.inline_data:
                                    if hasattr(part.inline_data, 'mime_type'):
                                        if part.inline_data.mime_type.startswith('image/'):
                                            return part.inline_data.data

            return None

        except Exception as e:
            print(f"[GeminiImage] 이미지 추출 실패: {e}")
            return None


def check_gemini_api_key() -> bool:
    """Gemini API 키 설정 여부 확인"""
    api_key = os.getenv("GEMINI_API_KEY", "")
    return bool(api_key)


def get_gemini_models() -> Dict:
    """사용 가능한 Gemini 모델 목록 반환"""
    return GEMINI_IMAGE_MODELS.copy()


# 테스트 코드
if __name__ == "__main__":
    print("=" * 50)
    print("Gemini Nano Banana 이미지 생성기 테스트")
    print("=" * 50)
    print()
    print("Gemini API 키 확인:", "✅ 설정됨" if check_gemini_api_key() else "❌ 미설정")
    print()
    print("사용 가능한 모델:")
    for key, config in GEMINI_IMAGE_MODELS.items():
        print(f"  - {key}: {config['model_id']}")
        print(f"    ({config['display_name']}, {config['cost_per_image']})")
    print()
    print("지원되는 가로세로 비율:", ", ".join(SUPPORTED_ASPECT_RATIOS))
    print()

    # API 키가 있으면 간단한 테스트
    if check_gemini_api_key():
        print("테스트 이미지 생성 시도...")
        try:
            generator = GeminiImageGenerator()
            result = generator.generate_image(
                prompt="A beautiful sunset over mountains, digital art style",
                model_key="gemini_nano_banana",
                aspect_ratio="16:9"
            )
            if result.success:
                print(f"✅ 테스트 성공! ({result.elapsed_time:.1f}초)")
            else:
                print(f"❌ 테스트 실패: {result.error}")
        except Exception as e:
            print(f"❌ 테스트 예외: {e}")
