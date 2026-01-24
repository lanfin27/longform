# -*- coding: utf-8 -*-
"""
Google ImageFX (Imagen) API 클라이언트 v6.4

rohitaryal/imageFX-api Node.js 라이브러리 직접 사용
Python에서 Node.js 스크립트를 subprocess로 호출

v6.4 변경사항:
- 모델명 매핑 수정: IMAGEN_4 → IMAGEN_3_5 (Node.js 레이어에서 처리)
- @rohitaryal/imagefx-api v3.0.3에서 IMAGEN_3_5만 지원
- IMAGEN_3_5가 실제로 IMAGEN 4 (라이브러리 주석 참고)
- 모든 모델이 IMAGEN_3_5로 매핑됨

v6.3 변경사항:
- IMAGEN_4 모델 매핑 버그 수정 (IMAGEN_3 → IMAGEN_4)
- IMAGEN_3_1 모델 매핑 버그 수정
- 기본 모델을 IMAGEN_4로 변경

v6.2 변경사항:
- 네거티브 프롬프트 지원 추가 (_apply_negative_prompt 메서드)
- 프롬프트 끝에 "AVOID: [네거티브 요소]" 형식으로 추가

v6.1 변경사항:
- Node.js 메서드명 수정: generate() → generateImage()

⚠️ 사전 요구사항:
1. Node.js 설치 (https://nodejs.org)
2. npm install @rohitaryal/imagefx-api

쿠키 추출 방법:
1. Cookie Editor 확장 프로그램 설치
2. labs.google/fx/tools/image-fx 접속 (Google 로그인)
3. Cookie Editor → Export → Header String
4. 복사된 전체 쿠키 사용

참조: https://github.com/aspect1103/imagefx-api
"""

import subprocess
import json
import os
import re
import uuid
import shutil
import time
import threading
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# 쿠키 상태 관리
from utils.imagefx_cookie_manager import (
    is_auth_error,
    mark_cookie_expired,
    mark_cookie_valid
)


class ImagenModel(Enum):
    """
    지원되는 Imagen 모델

    v6.4 참고: @rohitaryal/imagefx-api v3.0.3에서 IMAGEN_3_5만 지원
    모든 모델은 Node.js 레이어에서 IMAGEN_3_5로 매핑됨
    (IMAGEN_3_5가 실제로 IMAGEN 4임)
    """
    IMAGEN_3_5 = "IMAGEN_3_5"  # 실제 API에 전달되는 유일한 모델
    IMAGEN_3 = "IMAGEN_3"      # → IMAGEN_3_5로 매핑됨
    IMAGEN_4 = "IMAGEN_4"      # → IMAGEN_3_5로 매핑됨
    IMAGEN_3_1 = "IMAGEN_3_1"  # → IMAGEN_3_5로 매핑됨
    DEFAULT = "IMAGEN_4"       # 기본값 (→ IMAGEN_3_5로 매핑됨)

    def __str__(self):
        """v6.4: 문자열 변환 시 value 반환"""
        return self.value

    def __repr__(self):
        """v6.4: repr도 value 반환"""
        return self.value


def ensure_string_value(value) -> str:
    """
    v6.4: 값을 문자열로 안전하게 변환

    Enum 객체가 전달되어도 자동으로 .value 추출
    - Enum → .value
    - hasattr(value, 'value') → .value
    - 그 외 → str()
    """
    if value is None:
        return "IMAGEN_4"

    # Enum 클래스 체크 (어떤 Enum이든)
    if isinstance(value, Enum):
        return str(value.value)

    # .value 속성이 있는 경우 (Enum-like 객체)
    if hasattr(value, 'value'):
        return str(value.value)

    # 이미 문자열인 경우
    if isinstance(value, str):
        return value

    # 그 외는 str() 변환
    return str(value)


class AspectRatio(Enum):
    """지원되는 이미지 비율"""
    SQUARE = "SQUARE"
    PORTRAIT = "PORTRAIT"
    LANDSCAPE = "LANDSCAPE"
    # 호환성 별칭
    PORTRAIT_16_9 = "PORTRAIT"
    LANDSCAPE_16_9 = "LANDSCAPE"


# UI 표시용 모델 정보
# v6.4: 실제로 모든 모델이 IMAGEN_3_5로 매핑됨 (라이브러리 제한)
IMAGEFX_MODELS = [
    {"value": "IMAGEN_4", "label": "Imagen 4 (권장)", "description": "최신 모델 (내부적으로 IMAGEN_3_5 사용)"},
    {"value": "IMAGEN_3_5", "label": "Imagen 3.5", "description": "고품질 (실제 API 모델)"},
]

# UI 표시용 비율 정보
IMAGEFX_ASPECT_RATIOS = [
    {"value": "LANDSCAPE", "label": "가로 (4:3)", "resolution": "1024x768", "width": 1024, "height": 768},
    {"value": "PORTRAIT", "label": "세로 (3:4)", "resolution": "768x1024", "width": 768, "height": 1024},
    {"value": "SQUARE", "label": "정사각형 (1:1)", "resolution": "1024x1024", "width": 1024, "height": 1024},
]


class ImageFXError(Exception):
    """ImageFX API 관련 오류"""
    pass


class ImageFXAuthError(ImageFXError):
    """인증 관련 오류"""
    pass


class ImageFXRateLimitError(ImageFXError):
    """Rate limit 관련 오류"""
    pass


class CookieExpiredError(ImageFXAuthError):
    """쿠키 만료 오류 - UI에서 갱신 팝업 표시용"""
    pass


@dataclass
class GeneratedImage:
    """생성된 이미지 데이터"""
    file_path: str
    media_id: str = ""
    prompt: str = ""
    seed: Optional[int] = None  # v1.1: 시드 값 추가

    def save(self, filepath: str) -> str:
        """이미지를 다른 경로로 복사"""
        dir_path = os.path.dirname(filepath)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        shutil.copy(self.file_path, filepath)
        return filepath

    def get_bytes(self) -> bytes:
        """이미지 바이트 데이터 반환"""
        with open(self.file_path, 'rb') as f:
            return f.read()

    def get_base64(self) -> str:
        """Base64 인코딩된 문자열 반환"""
        import base64
        return base64.b64encode(self.get_bytes()).decode('utf-8')


class ImageFXClient:
    """
    Google ImageFX API 클라이언트 v6.0

    rohitaryal/imageFX-api Node.js 라이브러리 사용
    Python에서 subprocess로 Node.js 스크립트 호출
    """

    def __init__(
        self,
        cookie: Optional[str] = None,
        access_token: Optional[str] = None,  # 호환성 (v5에서 마이그레이션용)
        authorization_token: Optional[str] = None,  # 호환성
        node_script_path: Optional[str] = None
    ):
        """
        Args:
            cookie: Google 계정 쿠키 (Cookie Editor에서 추출) - 필수
            access_token: 호환성 유지용 (v6에서는 cookie 사용)
            authorization_token: 호환성 유지용
            node_script_path: Node.js 스크립트 경로 (기본: utils/imagefx_node.js)
        """
        self.cookie = cookie.strip() if cookie else None
        self.auth_type = "cookie"

        if not self.cookie:
            raise ValueError(
                "cookie가 필수입니다.\n\n"
                "쿠키 추출 방법:\n"
                "1. Cookie Editor 확장 프로그램 설치\n"
                "2. labs.google/fx/tools/image-fx 접속 (Google 로그인)\n"
                "3. Cookie Editor → Export → Header String\n"
                "4. 복사된 전체 쿠키 사용"
            )

        # Node.js 스크립트 경로
        if node_script_path:
            self.node_script = node_script_path
        else:
            current_dir = Path(__file__).parent
            self.node_script = str(current_dir / "imagefx_node.js")

        # 프로젝트 루트 디렉토리
        self.project_root = str(Path(__file__).parent.parent)

        # Node.js 설치 확인
        self._check_node_installation()

        print(f"[ImageFX v6.3] 초기화 완료 (Node.js 래퍼 사용)")
        print(f"[ImageFX v6.3] 쿠키 길이: {len(self.cookie)}")
        print(f"[ImageFX v6.3] Node 스크립트: {self.node_script}")
        print(f"[ImageFX v6.3] ✅ 네거티브 프롬프트 지원 활성화")

    def _check_node_installation(self):
        """Node.js 설치 확인"""
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print(f"[ImageFX v6.3] Node.js 버전: {result.stdout.strip()}")
            else:
                raise Exception("Node.js 실행 실패")
        except FileNotFoundError:
            raise Exception(
                "Node.js가 설치되어 있지 않습니다.\n"
                "https://nodejs.org 에서 Node.js를 설치해주세요."
            )
        except Exception as e:
            raise Exception(f"Node.js 확인 실패: {e}")

    def _check_npm_package(self) -> bool:
        """npm 패키지 설치 확인"""
        # @rohitaryal/imagefx-api 패키지 확인
        rohitaryal_modules = Path(self.project_root) / "node_modules" / "@rohitaryal" / "imagefx-api"
        return rohitaryal_modules.exists()

    @classmethod
    def validate_credentials(
        cls,
        cookie: Optional[str] = None,
        access_token: Optional[str] = None,
        authorization_token: Optional[str] = None
    ) -> Tuple[bool, str, str]:
        """인증 정보 유효성 검사"""

        if cookie:
            cookie = cookie.strip()
            if len(cookie) < 100:
                return False, "쿠키가 너무 짧습니다.", ""

            # Google 인증 쿠키 확인
            has_session = "__Secure-next-auth.session-token" in cookie
            has_google = any(key in cookie for key in [
                "SID=", "__Secure-1PSID=", "__Secure-3PSID=",
                "SAPISID=", "__Secure-1PAPISID=", "__Secure-3PAPISID="
            ])

            if has_session or has_google:
                return True, "✅ Google 인증 쿠키가 확인되었습니다.", "cookie"
            else:
                return True, "⚠️ 쿠키가 있지만 필수 인증 쿠키가 없을 수 있습니다.", "cookie"

        # 호환성: access_token이 주어지면 경고
        if access_token or authorization_token:
            return False, "v6.0부터 쿠키 기반 인증을 사용합니다. Cookie Editor로 쿠키를 추출해주세요.", ""

        return False, "쿠키를 입력해주세요. (Cookie Editor → Export → Header String)", ""

    def has_valid_token(self) -> bool:
        """유효한 인증이 있는지 확인"""
        return bool(self.cookie) and len(self.cookie) > 100

    def get_auth_status(self) -> Dict[str, Any]:
        """인증 상태 반환"""
        return {
            "auth_type": self.auth_type,
            "has_cookie": bool(self.cookie),
            "cookie_length": len(self.cookie) if self.cookie else 0,
            "npm_package_installed": self._check_npm_package()
        }

    def _apply_negative_prompt(self, prompt: str, negative_prompt: str) -> str:
        """
        네거티브 프롬프트를 메인 프롬프트에 추가 (v6.2)

        ImageFX API는 네거티브 프롬프트를 네이티브로 지원하지 않으므로,
        프롬프트 끝에 AVOID/NO 문구로 추가합니다.

        Args:
            prompt: 원본 프롬프트
            negative_prompt: 네거티브 프롬프트 (피할 요소들)

        Returns:
            네거티브가 추가된 최종 프롬프트
        """
        if not negative_prompt or not negative_prompt.strip():
            return prompt

        negative = negative_prompt.strip()

        # 프롬프트 끝에 네거티브 추가
        # 형식: [원본 프롬프트]. AVOID: [네거티브 요소들]
        final_prompt = f"{prompt.rstrip('.')}. AVOID: {negative}"

        return final_prompt

    def generate_image(
        self,
        prompt: str,
        model: ImagenModel = ImagenModel.IMAGEN_3,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        num_images: int = 1,
        seed: Optional[int] = None,
        retry_count: int = 3,
        timeout: int = 180,
        negative_prompt: str = ""
    ) -> List[GeneratedImage]:
        """
        이미지 생성 (Node.js 래퍼 호출)

        Args:
            prompt: 이미지 설명 텍스트
            model: Imagen 모델
            aspect_ratio: 이미지 비율
            num_images: 생성할 이미지 수 (1-4)
            seed: 시드값 (None이면 랜덤)
            retry_count: 재시도 횟수
            timeout: 타임아웃 (초)
            negative_prompt: 네거티브 프롬프트 (이미지에 포함하지 않을 요소)

        Returns:
            List[GeneratedImage]: 생성된 이미지 리스트
        """
        if not prompt or not prompt.strip():
            raise ImageFXError("프롬프트가 비어있습니다.")

        # ⭐ v6.2: 네거티브 프롬프트를 메인 프롬프트에 추가
        final_prompt = self._apply_negative_prompt(prompt.strip(), negative_prompt)

        # npm 패키지 확인
        if not self._check_npm_package():
            raise ImageFXError(
                "@rohitaryal/imagefx-api npm 패키지가 설치되어 있지 않습니다.\n\n"
                f"설치 방법:\n"
                f"cd {self.project_root}\n"
                f"npm install @rohitaryal/imagefx-api"
            )

        # 출력 경로 생성
        output_dir = Path(self.project_root) / "data" / "images" / "imagefx"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{uuid.uuid4()}.png")

        # v6.4: 비율 값 추출 (Enum 안전 변환)
        aspect_value = ensure_string_value(aspect_ratio)

        # v6.4: 모델 값 추출 (Enum 안전 변환)
        model_value = ensure_string_value(model)

        # v6.5: 로그 최소화 (디버그 모드에서만 상세 출력)
        # print(f"[ImageFX] 생성 중... (모델: {model_value})")

        # Node.js 스크립트 호출 명령
        cmd = [
            "node", self.node_script,
            "--cookie", self.cookie,
            "--prompt", final_prompt,  # ⭐ 네거티브 포함된 최종 프롬프트 사용
            "--outputPath", output_path,
            "--model", model_value,
            "--aspectRatio", aspect_value,
            "--count", str(min(num_images, 4))
        ]

        if seed is not None:
            cmd.extend(["--seed", str(seed)])

        # 네거티브 프롬프트 전달 (라이브러리 지원 시 사용)
        if negative_prompt:
            cmd.extend(["--negativePrompt", negative_prompt])

        # v6.4: 방어적 코드 - 모든 cmd 인자가 문자열인지 검증
        for i, arg in enumerate(cmd):
            if isinstance(arg, Enum):
                cmd[i] = str(arg.value)
            elif not isinstance(arg, str):
                cmd[i] = str(arg)

        last_error = None

        for attempt in range(retry_count):
            try:
                # v6.5: 로그 최소화 - 재시도 시에만 로그 출력
                if attempt > 0:
                    print(f"[ImageFX] 재시도 {attempt + 1}/{retry_count}")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=self.project_root,
                    encoding='utf-8',
                    errors='replace'
                )

                # v6.5: 에러 시에만 상세 로그
                if result.returncode != 0 and result.stderr:
                    print(f"[ImageFX] stderr: {result.stderr[:200]}")

                # 결과 파싱
                if "===RESULT===" in result.stdout:
                    # JSON 결과 추출
                    parts = result.stdout.split("===RESULT===")
                    if len(parts) > 1:
                        json_str = parts[1].strip()
                        # 첫 번째 JSON 객체만 추출
                        match = re.search(r'\{.*\}', json_str)
                        if match:
                            try:
                                output = json.loads(match.group())
                                if output.get("success"):
                                    saved_path = output.get("path", output_path)
                                    if os.path.exists(saved_path):
                                        # v1.1: 시드 값 추출
                                        result_seed = output.get("seed")
                                        # 성공 시 쿠키 유효 상태로 표시
                                        mark_cookie_valid()
                                        return [GeneratedImage(
                                            file_path=saved_path,
                                            prompt=prompt,
                                            seed=result_seed  # v1.1: 시드 저장
                                        )]
                                else:
                                    error_msg = output.get("error", "Unknown error")
                                    # 인증 에러 감지
                                    if is_auth_error(error_msg):
                                        print(f"[ImageFX v6.3] Auth error detected - cookie expired")
                                        mark_cookie_expired(error_msg)
                                        raise CookieExpiredError(
                                            "ImageFX cookie has expired.\n"
                                            "Please enter a new cookie in the API Management page."
                                        )
                                    last_error = error_msg
                            except json.JSONDecodeError as e:
                                print(f"[ImageFX v6.3] JSON parse error: {e}")

                # 파일이 생성되었는지 직접 확인
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    print(f"[ImageFX v6.3] File directly verified: {output_path}")
                    mark_cookie_valid()
                    # v1.2: 시드가 없으면 전달된 시드 사용 (Node.js에서 생성된 시드)
                    fallback_seed = seed if seed else None
                    print(f"[ImageFX v6.5] 📌 Fallback 시드: {fallback_seed}")
                    return [GeneratedImage(
                        file_path=output_path,
                        prompt=prompt,
                        seed=fallback_seed
                    )]

                # 실패 원인 분석
                combined_output = result.stdout + result.stderr

                # 인증 에러 감지
                if is_auth_error(combined_output):
                    print(f"[ImageFX v6.3] Auth error detected in output - cookie expired")
                    mark_cookie_expired(combined_output[:500])
                    raise CookieExpiredError(
                        "ImageFX cookie has expired.\n"
                        "Please enter a new cookie in the API Management page."
                    )

                if "not found" in combined_output.lower():
                    last_error = "imagefx-api package not found. Run: npm install imagefx-api"
                elif "429" in combined_output or "rate" in combined_output.lower():
                    last_error = "Rate limit exceeded. Please try again later."
                elif not last_error:
                    last_error = combined_output[:500] if combined_output else "Unknown error"

            except CookieExpiredError:
                raise  # 쿠키 만료는 재시도하지 않고 즉시 전파

            except subprocess.TimeoutExpired:
                print(f"[ImageFX v6.3] Timeout ({timeout}s)")
                last_error = f"Timeout ({timeout}s)"

            except Exception as e:
                error_str = str(e)
                print(f"[ImageFX v6.3] Error: {e}")

                # 예외에서도 인증 에러 감지
                if is_auth_error(error_str):
                    print(f"[ImageFX v6.3] Auth error in exception - cookie expired")
                    mark_cookie_expired(error_str)
                    raise CookieExpiredError(
                        "ImageFX cookie has expired.\n"
                        "Please enter a new cookie in the API Management page."
                    )

                last_error = error_str

            # 재시도 대기
            if attempt < retry_count - 1:
                wait_time = 3 * (attempt + 1)
                print(f"[ImageFX v6.3] Retrying in {wait_time}s...")
                time.sleep(wait_time)

        raise ImageFXError(f"Image generation failed: {last_error}")

    def test_connection(self) -> Tuple[bool, str]:
        """연결 테스트"""
        if not self.has_valid_token():
            return False, "쿠키가 없거나 유효하지 않습니다."

        if not self._check_npm_package():
            return False, "imagefx-api npm 패키지가 설치되어 있지 않습니다."

        try:
            images = self.generate_image(
                prompt="A simple red circle on white background",
                model=ImagenModel.IMAGEN_3,
                aspect_ratio=AspectRatio.SQUARE,
                num_images=1,
                timeout=120
            )

            if images:
                return True, f"✅ 연결 성공! (인증: {self.auth_type})"
            else:
                return False, "이미지 생성 실패"

        except ImageFXError as e:
            return False, str(e)
        except Exception as e:
            return False, f"연결 오류: {e}"


def create_imagefx_client(
    cookie: Optional[str] = None,
    access_token: Optional[str] = None,
    authorization_token: Optional[str] = None
) -> ImageFXClient:
    """ImageFX 클라이언트 생성 헬퍼 함수"""

    # 호환성: access_token이 주어지면 무시하고 경고
    if (access_token or authorization_token) and not cookie:
        print("[ImageFX v6.3] 경고: access_token은 더 이상 지원되지 않습니다. cookie를 사용하세요.")
        raise ValueError(
            "v6.0부터 쿠키 기반 인증을 사용합니다.\n"
            "Cookie Editor → Export → Header String으로 쿠키를 추출해주세요."
        )

    is_valid, message, _ = ImageFXClient.validate_credentials(cookie=cookie)

    if not is_valid:
        raise ValueError(f"인증 정보 검증 실패: {message}")

    return ImageFXClient(cookie=cookie)


def get_aspect_ratio_for_size(width: int, height: int) -> AspectRatio:
    """이미지 크기에 맞는 AspectRatio 반환"""
    if height == 0:
        return AspectRatio.LANDSCAPE

    ratio = width / height

    if abs(ratio - 1.0) < 0.1:
        return AspectRatio.SQUARE
    elif ratio > 1:
        return AspectRatio.LANDSCAPE
    else:
        return AspectRatio.PORTRAIT


def install_npm_package(project_root: Optional[str] = None) -> Tuple[bool, str]:
    """@rohitaryal/imagefx-api npm 패키지 설치"""
    if project_root is None:
        project_root = str(Path(__file__).parent.parent)

    try:
        # npm install 실행
        result = subprocess.run(
            ["npm", "install", "@rohitaryal/imagefx-api"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=120
        )

        if result.returncode == 0:
            return True, "✅ @rohitaryal/imagefx-api 패키지 설치 완료!"
        else:
            return False, f"설치 실패: {result.stderr}"

    except FileNotFoundError:
        return False, "npm이 설치되어 있지 않습니다. Node.js를 먼저 설치해주세요."
    except Exception as e:
        return False, f"설치 오류: {e}"


def check_node_installation() -> Tuple[bool, str]:
    """Node.js 설치 확인"""
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return True, f"Node.js {result.stdout.strip()}"
        else:
            return False, "Node.js 실행 실패"
    except FileNotFoundError:
        return False, "Node.js가 설치되어 있지 않습니다."
    except Exception as e:
        return False, f"확인 오류: {e}"


# ============================================================
# ImageFXCache: 쿠키 및 설정 캐싱
# ============================================================
class ImageFXCache:
    """쿠키 및 설정 캐싱"""

    _cookie_cache: Optional[str] = None
    _cookie_loaded: bool = False
    _style_cache: Dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def get_cookie(cls, force_reload: bool = False) -> Optional[str]:
        """쿠키 캐시에서 가져오기 (1회만 로드)"""
        if cls._cookie_loaded and not force_reload:
            return cls._cookie_cache

        with cls._lock:
            if cls._cookie_loaded and not force_reload:
                return cls._cookie_cache

            try:
                from config.settings import load_imagefx_cookie
                cls._cookie_cache = load_imagefx_cookie()
                cls._cookie_loaded = True
                return cls._cookie_cache
            except Exception as e:
                print(f"[ImageFX-Cache] 쿠키 로드 실패: {e}")
                return None

    @classmethod
    def set_cookie(cls, cookie: str):
        """쿠키 캐시 설정"""
        with cls._lock:
            cls._cookie_cache = cookie
            cls._cookie_loaded = True


# ============================================================
# ImageFXBatchGenerator: 배치 이미지 생성 (워커 프로세스 재사용)
# ============================================================
class ImageFXBatchGenerator:
    """
    ImageFX 배치 이미지 생성기 v4.1

    Node.js 워커 프로세스를 1회만 시작하고 재사용하여 성능 최적화
    - 매번 subprocess 시작하는 대신 persistent worker 사용
    - 라이브러리 로드 1회만 수행
    """

    def __init__(
        self,
        max_workers: int = 1,  # 순차 처리 (병렬은 Rate Limit 문제)
        cookie: Optional[str] = None,
        api_delay: float = 2.0  # 요청 간 대기 시간
    ):
        self.cookie = cookie or ImageFXCache.get_cookie()
        self.api_delay = api_delay
        self.timeout_per_image = 120
        self.max_retries = 2

        self._project_root = str(Path(__file__).parent.parent)
        self._worker_script = str(Path(__file__).parent / "imagefx_worker.js")
        self._worker: Optional[subprocess.Popen] = None
        self._worker_initialized = False

        print(f"[ImageFX-Batch v4.1] 배치 생성기 초기화됨 (대기: {self.api_delay}초)")

    def _ensure_worker(self) -> bool:
        """워커 프로세스 확인/생성"""
        if self._worker is not None and self._worker.poll() is None:
            return True

        if not Path(self._worker_script).exists():
            print(f"[ImageFX-Batch] 워커 스크립트 없음: {self._worker_script}")
            return False

        try:
            self._worker = subprocess.Popen(
                ["node", self._worker_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self._project_root,
                encoding='utf-8',
                errors='replace',
                bufsize=1
            )

            time.sleep(0.5)

            if self._worker.poll() is not None:
                self._worker = None
                return False

            if self.cookie:
                init_request = json.dumps({"type": "init", "cookie": self.cookie}) + "\n"
                self._worker.stdin.write(init_request)
                self._worker.stdin.flush()

                response_line = self._worker.stdout.readline()
                if response_line:
                    response = json.loads(response_line.strip())
                    if response.get("success"):
                        self._worker_initialized = True
                        print(f"[ImageFX-Batch] 워커 초기화 완료")
                        return True

            return True

        except Exception as e:
            print(f"[ImageFX-Batch] 워커 시작 오류: {e}")
            self._worker = None
            return False

    def _generate_single(self, req: Dict) -> Dict:
        """단일 이미지 생성"""
        import queue

        scene_id = req.get("scene_id", "?")

        if not self._ensure_worker():
            return {"success": False, "error": "Worker not available", "scene_id": scene_id}

        try:
            if self._worker.poll() is not None:
                self._worker = None
                self._worker_initialized = False
                if not self._ensure_worker():
                    return {"success": False, "error": "Worker restart failed", "scene_id": scene_id}

            prompt = req.get("prompt", "")
            negative = req.get("negative_prompt", "")
            if negative:
                prompt = f"{prompt.rstrip('.')}. AVOID: {negative}"

            request = {
                "type": "generate",
                "prompt": prompt,
                "outputPath": req.get("output_path"),
                "model": req.get("model", "IMAGEN_4"),
                "aspectRatio": req.get("aspect_ratio", "LANDSCAPE"),
                "count": 1
            }

            seed = req.get("seed")
            if seed is not None:
                request["seed"] = seed

            request_json = json.dumps(request) + "\n"
            self._worker.stdin.write(request_json)
            self._worker.stdin.flush()

            # Windows 타임아웃 처리
            result_queue = queue.Queue()

            def read_response():
                try:
                    line = self._worker.stdout.readline()
                    result_queue.put(("ok", line))
                except Exception as e:
                    result_queue.put(("error", str(e)))

            read_thread = threading.Thread(target=read_response, daemon=True)
            read_thread.start()

            try:
                status, data = result_queue.get(timeout=self.timeout_per_image)
                if status == "ok":
                    response_line = data
                else:
                    self._cleanup_worker()
                    return {"success": False, "error": f"Worker error: {data}", "scene_id": scene_id}
            except queue.Empty:
                self._cleanup_worker()
                return {"success": False, "error": f"Timeout ({self.timeout_per_image}s)", "scene_id": scene_id}

            if not response_line:
                self._cleanup_worker()
                return {"success": False, "error": "No response", "scene_id": scene_id}

            response = json.loads(response_line.strip())
            response["scene_id"] = scene_id
            return response

        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON error: {e}", "scene_id": scene_id}
        except Exception as e:
            return {"success": False, "error": str(e), "scene_id": scene_id}

    def _cleanup_worker(self):
        """워커 프로세스 정리"""
        if self._worker is not None:
            try:
                if self._worker.poll() is None:
                    self._worker.kill()
                    self._worker.wait(timeout=2)
            except Exception:
                pass
            self._worker = None
            self._worker_initialized = False

    def generate_batch(
        self,
        requests: List[Dict],
        progress_callback: Optional[callable] = None
    ) -> List[Dict]:
        """
        배치 이미지 생성 (순차 처리, 워커 재사용)
        """
        total = len(requests)
        if total == 0:
            return []

        print(f"\n[ImageFX-Batch v4.1] ========== 배치 생성 시작 ==========")
        print(f"[ImageFX-Batch v4.1] 총 {total}개 이미지, 대기 {self.api_delay}초")

        start_time = time.time()
        results = []

        for i, req in enumerate(requests):
            scene_id = req.get("scene_id", i)

            if progress_callback:
                try:
                    progress_callback(i, total)
                except Exception:
                    pass

            result = self._generate_single(req)
            result["scene_id"] = scene_id
            results.append(result)

            if result.get("success"):
                print(f"[ImageFX-Batch] [{i+1}/{total}] 씬 {scene_id} 완료")
            else:
                print(f"[ImageFX-Batch] [{i+1}/{total}] 씬 {scene_id} 실패: {result.get('error', '')[:50]}")

            if i < total - 1:
                time.sleep(self.api_delay)

            if progress_callback:
                try:
                    progress_callback(i + 1, total)
                except Exception:
                    pass

        results.sort(key=lambda r: r.get("scene_id", 0) if isinstance(r.get("scene_id"), int) else 0)

        elapsed = time.time() - start_time
        success_count = sum(1 for r in results if r.get("success"))

        print(f"\n[ImageFX-Batch v4.1] ========== 배치 완료 ==========")
        print(f"[ImageFX-Batch v4.1] 성공: {success_count}/{total}")
        print(f"[ImageFX-Batch v4.1] 총 시간: {elapsed:.1f}초")
        if total > 0:
            print(f"[ImageFX-Batch v4.1] 이미지당 평균: {elapsed/total:.1f}초")

        return results

    def cleanup(self):
        """리소스 정리"""
        self._cleanup_worker()


# 모듈 테스트
if __name__ == "__main__":
    import sys

    cookie = os.environ.get("IMAGEFX_COOKIE", "")

    if not cookie:
        print("IMAGEFX_COOKIE 환경 변수를 설정해주세요.")
        print()
        print("쿠키 추출 방법:")
        print("1. Cookie Editor 확장 프로그램 설치")
        print("2. labs.google/fx/tools/image-fx 접속")
        print("3. Cookie Editor → Export → Header String")
        print("4. 환경 변수에 저장: set IMAGEFX_COOKIE=<쿠키값>")
        sys.exit(1)

    # Node.js 확인
    node_ok, node_msg = check_node_installation()
    print(f"Node.js: {node_msg}")
    if not node_ok:
        sys.exit(1)

    try:
        is_valid, message, _ = ImageFXClient.validate_credentials(cookie=cookie)
        print(f"인증 검증: {message}")

        if not is_valid:
            sys.exit(1)

        client = create_imagefx_client(cookie=cookie)

        # npm 패키지 확인
        if not client._check_npm_package():
            print("\nimagefx-api 패키지 설치 중...")
            ok, msg = install_npm_package()
            print(msg)
            if not ok:
                sys.exit(1)

        print("\n이미지 생성 테스트...")
        images = client.generate_image(
            prompt="A beautiful mountain landscape at sunset",
            model=ImagenModel.IMAGEN_3,
            aspect_ratio=AspectRatio.LANDSCAPE,
            num_images=1
        )

        if images:
            print(f"✅ 성공! 이미지 저장됨: {images[0].file_path}")
        else:
            print("이미지가 생성되지 않았습니다.")

    except ImageFXError as e:
        print(f"오류: {e}")
        sys.exit(1)
