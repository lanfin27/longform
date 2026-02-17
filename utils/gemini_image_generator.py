# -*- coding: utf-8 -*-
"""
utils/gemini_image_generator.py
Gemini 이미지 생성 API 클라이언트 v3.1

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

v3.0 변경사항 (2026-01-25):
- 싱글톤 패턴 적용 (SDK 재초기화 방지)
- 레퍼런스 이미지 캐시 연동 (ReferenceImageCache)
- as_image() 오류 수정 (format 파라미터 호환성)
- 병렬 처리 지원 (generate_images_parallel)
- ThreadPoolExecutor 기반 비동기 처리

v3.1 변경사항 (2026-01-26):
- 병렬 처리 타이밍 측정 로그 추가
- 스레드별 시작/종료 시간 기록
- Gantt 차트 형태 시각화
- 병렬 효율 분석 (speedup, efficiency %)

작성: 2025-01
업데이트: 2026-01 - 새로운 모델명 및 API 방식 적용
업데이트: 2026-01-25 - 성능 최적화 (싱글톤, 캐시, 병렬처리)
업데이트: 2026-01-26 - 병렬 처리 검증 및 타이밍 분석 추가
"""

import os
import io
import base64
import threading
from pathlib import Path
from typing import List, Optional, Dict, Union
from dataclasses import dataclass
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    """
    Gemini 이미지 생성 클라이언트 (v3.0 - 싱글톤)

    싱글톤 패턴으로 SDK 재초기화 방지
    """

    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, api_key: str = None):
        """싱글톤 패턴 - SDK 재초기화 방지"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, api_key: str = None):
        """
        초기화 (이미 초기화된 경우 스킵)

        Args:
            api_key: Gemini API 키 (None이면 환경변수에서 로드)
        """
        # 이미 초기화된 경우 스킵
        if GeminiImageGenerator._initialized:
            return

        self.api_key = api_key or self._load_api_key()

        if not self.api_key:
            raise ValueError(
                "Gemini API 키가 설정되지 않았습니다. "
                ".env 파일에 GEMINI_API_KEY를 설정하세요."
            )

        # google-generativeai 라이브러리 초기화
        self._init_genai()
        GeminiImageGenerator._initialized = True
        print("[GeminiImage] ✅ 싱글톤 초기화 완료 (SDK 재사용 가능)")

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
                        # v3.0: format 파라미터 호환성 수정
                        try:
                            pil_image = part.as_image()
                            # PIL Image를 bytes로 변환
                            buffer = io.BytesIO()
                            # 일부 PIL 버전에서 format= 키워드 인자 오류 발생
                            # 위치 인자로 변경하여 호환성 확보
                            pil_image.save(buffer, "PNG")
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
        """
        이미지를 PIL Image로 로드 (새로운 API용)

        v3.0: ReferenceImageCache 연동으로 캐시 활용
        """

        try:
            pil_image = None

            # 파일 경로인 경우 - 캐시 활용
            if isinstance(image_source, str):
                try:
                    from utils.image_cache import load_reference_as_pil
                    pil_image = load_reference_as_pil(image_source, max_size=1024)
                    if pil_image:
                        return pil_image
                except ImportError:
                    pass

                # 캐시 폴백: 직접 로드
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
                    # v3.0: format 파라미터 호환성 수정
                    if hasattr(part, 'as_image'):
                        try:
                            pil_image = part.as_image()
                            buffer = io.BytesIO()
                            pil_image.save(buffer, "PNG")  # 위치 인자 사용
                            return buffer.getvalue()
                        except Exception as img_err:
                            print(f"[GeminiImage] as_image() 추출 실패: {img_err}")
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


# ═══════════════════════════════════════════════════════════════════════════════
# 병렬 처리 함수 (v3.1: 타이밍 분석 추가)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_images_parallel(
    requests: List[Dict],
    max_concurrent: int = 4,
    model_key: str = "gemini_nano_banana",
    on_complete: callable = None,
    on_error: callable = None
) -> List[Dict]:
    """
    여러 이미지를 병렬로 생성 (v3.1: 타이밍 분석 포함)

    Args:
        requests: 요청 목록 [{"scene_id": 1, "prompt": "...", "reference_images": [...], ...}, ...]
        max_concurrent: 최대 동시 실행 수 (기본: 4)
        model_key: 사용할 모델 키
        on_complete: 완료 시 콜백 (scene_id, result)
        on_error: 에러 시 콜백 (scene_id, error)

    Returns:
        결과 리스트 [{"scene_id": 1, "success": True, "image_data": bytes, ...}, ...]

    Usage:
        results = generate_images_parallel([
            {"scene_id": 45, "prompt": "...", "reference_images": ["/path/to/bg.png"]},
            {"scene_id": 47, "prompt": "...", "reference_images": ["/path/to/bg.png"]},
        ], max_concurrent=4)
    """
    import time
    import threading

    if not requests:
        return []

    # 싱글톤 인스턴스 가져오기
    generator = GeminiImageGenerator()

    results = []
    completed = 0
    total = len(requests)

    # v3.1: 타이밍 측정용 데이터
    timing_data = []
    timing_lock = threading.Lock()

    print(f"\n[GeminiImage] ═══════════════════════════════════════════════════")
    print(f"[GeminiImage] 🚀 병렬 이미지 생성 시작")
    print(f"[GeminiImage]    총 요청: {total}개")
    print(f"[GeminiImage]    동시 실행: {max_concurrent}개")
    print(f"[GeminiImage]    모델: {model_key}")
    print(f"[GeminiImage]    메인 스레드: {threading.current_thread().name}")
    print(f"[GeminiImage] ═══════════════════════════════════════════════════\n")

    start_time = time.time()

    # 레퍼런스 이미지 프리로드 (캐시 최적화)
    try:
        from utils.image_cache import preload_references
        all_refs = []
        for req in requests:
            refs = req.get("reference_images", [])
            if refs:
                all_refs.extend(refs)
        if all_refs:
            preload_references(all_refs)
    except ImportError:
        pass

    def process_single(req: Dict) -> Dict:
        """단일 이미지 생성 (v3.1: 타이밍 측정 추가)"""
        scene_id = req.get("scene_id", 0)
        prompt = req.get("prompt", "")
        reference_images = req.get("reference_images", [])
        reference_type = req.get("reference_type", "style")
        reference_strength = req.get("reference_strength", 0.7)
        aspect_ratio = req.get("aspect_ratio", "16:9")

        # v3.1: 시작 시간 및 스레드 정보 기록
        thread_name = threading.current_thread().name
        task_start = time.time()
        relative_start = task_start - start_time

        print(f"[GeminiImage] ▶ 씬 {scene_id} API 호출 시작 [{thread_name}] @ {relative_start:.2f}s")

        try:
            result = generator.generate_image(
                prompt=prompt,
                model_key=model_key,
                reference_images=reference_images,
                reference_type=reference_type,
                reference_strength=reference_strength,
                aspect_ratio=aspect_ratio
            )

            task_end = time.time()
            elapsed = task_end - task_start
            relative_end = task_end - start_time

            # v3.1: 타이밍 데이터 저장
            with timing_lock:
                timing_data.append({
                    "scene_id": scene_id,
                    "thread": thread_name,
                    "start": relative_start,
                    "end": relative_end,
                    "elapsed": elapsed,
                    "success": result.success
                })

            return {
                "scene_id": scene_id,
                "success": result.success,
                "image_data": result.image_data,
                "error": result.error,
                "elapsed_time": result.elapsed_time,
                "prompt": prompt,
                # v3.1: 타이밍 정보 추가
                "timing": {
                    "thread": thread_name,
                    "start": relative_start,
                    "end": relative_end,
                    "elapsed": elapsed
                }
            }

        except Exception as e:
            task_end = time.time()
            elapsed = task_end - task_start
            relative_end = task_end - start_time

            with timing_lock:
                timing_data.append({
                    "scene_id": scene_id,
                    "thread": thread_name,
                    "start": relative_start,
                    "end": relative_end,
                    "elapsed": elapsed,
                    "success": False
                })

            return {
                "scene_id": scene_id,
                "success": False,
                "image_data": None,
                "error": str(e),
                "elapsed_time": 0,
                "prompt": prompt
            }

    # ThreadPoolExecutor로 병렬 실행
    with ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix="GeminiWorker") as executor:
        # 작업 제출 (모든 작업 동시에!)
        future_to_req = {
            executor.submit(process_single, req): req
            for req in requests
        }

        # 완료되는 순서대로 처리
        for future in as_completed(future_to_req):
            req = future_to_req[future]
            scene_id = req.get("scene_id", 0)
            completed += 1

            try:
                result = future.result()
                results.append(result)

                timing_info = result.get("timing", {})
                thread_name = timing_info.get("thread", "?")
                elapsed = timing_info.get("elapsed", result.get("elapsed_time", 0))

                if result["success"]:
                    print(f"[GeminiImage] ✅ 씬 {scene_id} 완료 [{thread_name}] ({elapsed:.1f}초) [{completed}/{total}]")
                    if on_complete:
                        on_complete(scene_id, result)
                else:
                    print(f"[GeminiImage] ❌ 씬 {scene_id} 실패 [{thread_name}]: {result['error']} [{completed}/{total}]")
                    if on_error:
                        on_error(scene_id, result["error"])

            except Exception as e:
                error_result = {
                    "scene_id": scene_id,
                    "success": False,
                    "image_data": None,
                    "error": str(e),
                    "elapsed_time": 0,
                    "prompt": req.get("prompt", "")
                }
                results.append(error_result)
                print(f"[GeminiImage] ❌ 씬 {scene_id} 예외: {e} [{completed}/{total}]")
                if on_error:
                    on_error(scene_id, str(e))

    total_time = time.time() - start_time
    success_count = sum(1 for r in results if r["success"])

    # ═══════════════════════════════════════════════════════════════════════════
    # v3.1: 병렬 처리 타이밍 분석 및 Gantt 차트
    # ═══════════════════════════════════════════════════════════════════════════
    print(f"\n[GeminiImage] ═══════════════════════════════════════════════════")
    print(f"[GeminiImage] 📊 병렬 처리 타이밍 분석 (Gantt Chart)")
    print(f"[GeminiImage] ───────────────────────────────────────────────────")

    # 시작 시간순 정렬
    sorted_timing = sorted(timing_data, key=lambda x: x["start"])

    for info in sorted_timing:
        # Gantt 차트 바 생성 (40칸)
        bar_width = 40
        if total_time > 0:
            start_pos = int((info["start"] / total_time) * bar_width)
            end_pos = int((info["end"] / total_time) * bar_width)
        else:
            start_pos = 0
            end_pos = bar_width

        bar = "·" * start_pos + "█" * max(1, end_pos - start_pos) + "·" * (bar_width - end_pos)
        status = "✓" if info.get("success", True) else "✗"

        print(f"[GeminiImage]   씬{info['scene_id']:3d}: |{bar}| {info['elapsed']:.1f}s {status}")

    print(f"[GeminiImage] ───────────────────────────────────────────────────")

    # 병렬 효율 계산
    if timing_data:
        sequential_total = sum(d["elapsed"] for d in timing_data)
        actual_parallel = total_time
        speedup = sequential_total / actual_parallel if actual_parallel > 0 else 1
        efficiency = (speedup / len(timing_data)) * 100 if timing_data else 0

        print(f"[GeminiImage]   순차 예상 시간: {sequential_total:.1f}초")
        print(f"[GeminiImage]   실제 소요 시간: {actual_parallel:.1f}초")
        print(f"[GeminiImage]   속도 향상: {speedup:.2f}x")
        print(f"[GeminiImage]   병렬 효율: {efficiency:.1f}%")

        # 병렬 여부 판단
        if speedup > 1.5:
            print(f"[GeminiImage]   ✅ 병렬 처리 효과 확인됨!")
        elif speedup > 1.1:
            print(f"[GeminiImage]   ⚠️ 부분적 병렬 처리 (API Rate Limit 가능성)")
        else:
            print(f"[GeminiImage]   ❌ 병렬 처리 미작동 (순차 실행 의심)")

        # 동시 시작 검증
        if len(timing_data) >= 2:
            starts = [d["start"] for d in sorted_timing]
            start_diff = max(starts) - min(starts)
            if start_diff < 1.0:
                print(f"[GeminiImage]   ✅ 동시 시작 확인 (시작 간격: {start_diff:.2f}초)")
            else:
                print(f"[GeminiImage]   ⚠️ 시작 간격이 큼: {start_diff:.2f}초 (순차 의심)")

    print(f"[GeminiImage] ═══════════════════════════════════════════════════")
    print(f"[GeminiImage] ✅ 병렬 이미지 생성 완료")
    print(f"[GeminiImage]    성공: {success_count}/{total}개")
    print(f"[GeminiImage]    총 소요 시간: {total_time:.1f}초")
    print(f"[GeminiImage]    평균 시간/이미지: {total_time/total:.1f}초")
    print(f"[GeminiImage] ═══════════════════════════════════════════════════\n")

    # 캐시 통계 출력
    try:
        from utils.image_cache import get_reference_cache_stats
        stats = get_reference_cache_stats()
        print(f"[GeminiImage] 📊 캐시 통계: {stats}")
    except ImportError:
        pass

    return results


def reset_generator_singleton():
    """
    싱글톤 인스턴스 리셋 (테스트/디버깅용)

    주의: 일반적인 사용에서는 호출하지 마세요.
    """
    GeminiImageGenerator._instance = None
    GeminiImageGenerator._initialized = False
    print("[GeminiImage] ⚠️ 싱글톤 리셋됨")


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
