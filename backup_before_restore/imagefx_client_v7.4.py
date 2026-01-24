# -*- coding: utf-8 -*-
"""
Google ImageFX (Imagen) API 클라이언트 v7.4

rohitaryal/imageFX-api Node.js 라이브러리 직접 사용
Python에서 Node.js 스크립트를 subprocess로 호출

v7.4 변경사항 (순차 처리로 롤백 - 안정화):
- ⚠️ 병렬 처리 완전 제거! (v3.x → v4.0)
- 병렬 처리가 Rate Limit으로 12개 이후 전부 실패
- 순차 처리가 오히려 더 빠르고 안정적
- ImageFXBatchGenerator v4.0: 순차 처리 전용
- 요청 간 3초 대기로 Rate Limit 자연 회피
- 단일 워커 사용 (복잡한 워커 풀 제거)
- ThreadPoolExecutor, concurrent.futures 완전 제거

v7.3 변경사항 (12개 이후 멈춤 버그 수정 - 폐기됨):
- ImageFXBatchGenerator v3.1: 병렬 처리 (Rate Limit 문제로 폐기)

v7.1 변경사항 (속도 최적화):
- Persistent Worker 사용: Node.js 프로세스 1회만 시작, 재사용
- 워커 초기화 1회만: ImageFX 라이브러리 로드 및 쿠키 설정
- 시드 전달 완벽 지원: Python → Worker → Node.js
- 폴백: 워커 실패 시 기존 subprocess 방식 사용

v7.0 변경사항:
- 싱글톤 패턴: ImageFXClient 인스턴스 1개만
- 쿠키/Node.js 버전 캐싱
- 요청 카운트 추적

v6.3 변경사항:
- IMAGEN_4 모델 매핑 버그 수정 (IMAGEN_3 → IMAGEN_4)
- IMAGEN_3_1 모델 매핑 버그 수정
- 기본 모델을 IMAGEN_4로 변경

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
    """지원되는 Imagen 모델"""
    IMAGEN_3_5 = "IMAGEN_3_5"
    IMAGEN_3 = "IMAGEN_3"
    IMAGEN_4 = "IMAGEN_4"  # v6.3: 정확한 모델 값 사용
    IMAGEN_3_1 = "IMAGEN_3_1"
    DEFAULT = "IMAGEN_4"  # v6.3: 기본값을 IMAGEN_4로 변경

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
IMAGEFX_MODELS = [
    {"value": "IMAGEN_4", "label": "Imagen 4 (최신)", "description": "최신 모델, 한글 텍스트 없음"},
    {"value": "IMAGEN_3_5", "label": "Imagen 3.5", "description": "고품질"},
    {"value": "IMAGEN_3_1", "label": "Imagen 3.1", "description": "안정적"},
    {"value": "IMAGEN_3", "label": "Imagen 3", "description": "기본"},
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

    @property
    def path(self) -> str:
        """file_path 별칭 (하위 호환성)"""
        return self.file_path

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
    Google ImageFX API 클라이언트 v7.0 (싱글톤 + 워커 재사용)

    v7.0 최적화:
    - 싱글톤 패턴: 인스턴스 1개만 생성
    - 초기화 1회만: Node.js 버전 체크, 쿠키 로드 등
    - 워커 프로세스 재사용: 매번 새 프로세스 시작 안함
    - 시드 전달 지원
    """

    # ═══════════════════════════════════════════════════════════════
    # 싱글톤 + 캐싱 변수
    # ═══════════════════════════════════════════════════════════════
    _instance: Optional['ImageFXClient'] = None
    _initialized: bool = False
    _cookie_cache: Optional[str] = None
    _node_version_cache: Optional[str] = None
    _worker_process: Optional[subprocess.Popen] = None
    _worker_initialized: bool = False
    _request_count: int = 0
    _lock = None  # threading.Lock()

    def __new__(cls, *args, **kwargs):
        """싱글톤 패턴: 인스턴스 1개만 생성"""
        if cls._lock is None:
            import threading
            cls._lock = threading.Lock()

        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        cookie: Optional[str] = None,
        access_token: Optional[str] = None,  # 호환성 (v5에서 마이그레이션용)
        authorization_token: Optional[str] = None,  # 호환성
        node_script_path: Optional[str] = None
    ):
        """
        v7.0: 이미 초기화되었으면 스킵 (싱글톤)

        Args:
            cookie: Google 계정 쿠키 (Cookie Editor에서 추출) - 필수
            access_token: 호환성 유지용 (v6에서는 cookie 사용)
            authorization_token: 호환성 유지용
            node_script_path: Node.js 스크립트 경로 (기본: utils/imagefx_node.js)
        """
        # ═══════════════════════════════════════════════════════════════
        # 이미 초기화되었으면 스킵! (핵심 최적화)
        # ═══════════════════════════════════════════════════════════════
        if ImageFXClient._initialized:
            # 쿠키가 변경된 경우만 업데이트
            if cookie and cookie.strip() != ImageFXClient._cookie_cache:
                ImageFXClient._cookie_cache = cookie.strip()
                ImageFXClient._worker_initialized = False  # 워커 재초기화 필요
                print(f"[ImageFX v7.0] ⚡ 쿠키 변경 감지 - 워커 재초기화 필요")
            return

        # ═══════════════════════════════════════════════════════════════
        # 최초 1회만 실행되는 초기화
        # ═══════════════════════════════════════════════════════════════
        print(f"[ImageFX v7.0] ========== 초기화 시작 (1회만) ==========")

        # 쿠키 설정
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

        # 쿠키 캐싱
        ImageFXClient._cookie_cache = self.cookie
        print(f"[ImageFX v7.0] ✅ 쿠키 캐시됨 (길이: {len(self.cookie)})")

        # Node.js 스크립트 경로
        if node_script_path:
            self.node_script = node_script_path
        else:
            current_dir = Path(__file__).parent
            self.node_script = str(current_dir / "imagefx_node.js")

        # 프로젝트 루트 디렉토리
        self.project_root = str(Path(__file__).parent.parent)

        # Node.js 설치 확인 (1회만)
        self._check_node_installation_once()

        print(f"[ImageFX v7.0] Node 스크립트: {self.node_script}")
        print(f"[ImageFX v7.0] ✅ 네거티브 프롬프트 지원 활성화")
        print(f"[ImageFX v7.0] ========== 초기화 완료 ==========")

        # 초기화 완료 표시
        ImageFXClient._initialized = True

    def _check_node_installation_once(self):
        """Node.js 설치 확인 (1회만, 캐싱)"""
        # 이미 확인했으면 스킵
        if ImageFXClient._node_version_cache:
            print(f"[ImageFX v7.0] ⚡ Node.js 버전 (캐시): {ImageFXClient._node_version_cache}")
            return

        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                ImageFXClient._node_version_cache = result.stdout.strip()
                print(f"[ImageFX v7.0] Node.js 버전: {ImageFXClient._node_version_cache}")
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

    def _map_error_reason(self, error_reason: str, default_msg: str) -> str:
        """
        Google API 에러 reason을 사용자 친화적 메시지로 변환

        v6.4: 에러 reason 매핑 추가
        """
        error_mappings = {
            # 안전성 관련 에러
            "PUBLIC_ERROR_UNSAFE_GENERATION": (
                "프롬프트가 안전성 필터에 의해 차단되었습니다.\n"
                "• 민감한 키워드(인물명, 민족 등)를 피하세요.\n"
                "• 프롬프트를 수정한 후 다시 시도해주세요."
            ),
            "SAFETY_FILTER_TRIGGERED": (
                "안전성 필터가 트리거되었습니다. 프롬프트를 수정해주세요."
            ),
            "CONTENT_POLICY_VIOLATION": (
                "콘텐츠 정책 위반입니다. 프롬프트 내용을 확인해주세요."
            ),

            # 인증 관련 에러
            "UNAUTHENTICATED": "인증이 만료되었습니다. 쿠키를 갱신해주세요.",
            "PERMISSION_DENIED": "권한이 없습니다. 쿠키를 확인해주세요.",

            # Rate Limit 에러
            "RATE_LIMIT_EXCEEDED": "요청 한도 초과. 잠시 후 다시 시도해주세요.",
            "QUOTA_EXCEEDED": "일일 할당량 초과. 내일 다시 시도해주세요.",
            "RESOURCE_EXHAUSTED": "리소스 한도 초과. 잠시 후 다시 시도해주세요.",

            # 일반 에러
            "INVALID_ARGUMENT": "잘못된 요청입니다. 프롬프트를 확인해주세요.",
            "INTERNAL": "서버 내부 오류. 잠시 후 다시 시도해주세요.",
        }

        return error_mappings.get(error_reason, default_msg)

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

        print(f"[ImageFX v6.3] 네거티브 프롬프트 적용됨 ({len(negative)}자)")

        return final_prompt

    def _generate_with_worker(
        self,
        prompt: str,
        model_value: str,
        aspect_value: str,
        seed: Optional[int],
        negative_prompt: str,
        timeout: int,
        cookie: str
    ) -> Optional[List[GeneratedImage]]:
        """
        v7.1: Persistent Worker를 사용한 이미지 생성

        Node.js 프로세스를 재사용하여 초기화 오버헤드 제거
        """
        # 워커 스크립트 경로
        worker_script = str(Path(__file__).parent / "imagefx_worker.js")
        project_root = getattr(self, 'project_root', str(Path(__file__).parent.parent))

        if not Path(worker_script).exists():
            print(f"[ImageFX v7.1] ⚠️ 워커 스크립트 없음: {worker_script}")
            return None

        # 워커 프로세스 시작 (없거나 종료된 경우)
        if ImageFXClient._worker_process is None or ImageFXClient._worker_process.poll() is not None:
            print(f"[ImageFX v7.1] 🚀 워커 프로세스 시작...")
            try:
                ImageFXClient._worker_process = subprocess.Popen(
                    ["node", worker_script],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=project_root,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1
                )
                time.sleep(0.5)  # 시작 대기

                if ImageFXClient._worker_process.poll() is not None:
                    stderr = ImageFXClient._worker_process.stderr.read() if ImageFXClient._worker_process.stderr else ""
                    print(f"[ImageFX v7.1] ❌ 워커 시작 실패: {stderr[:200]}")
                    ImageFXClient._worker_process = None
                    return None

                ImageFXClient._worker_initialized = False
                print(f"[ImageFX v7.1] ✅ 워커 프로세스 시작됨 (PID: {ImageFXClient._worker_process.pid})")
            except Exception as e:
                print(f"[ImageFX v7.1] ❌ 워커 시작 오류: {e}")
                return None

        # 워커 초기화 (쿠키 설정 - 1회만)
        if not ImageFXClient._worker_initialized:
            print(f"[ImageFX v7.1] 🔧 워커 초기화 중...")
            init_request = json.dumps({"type": "init", "cookie": cookie}) + "\n"
            try:
                ImageFXClient._worker_process.stdin.write(init_request)
                ImageFXClient._worker_process.stdin.flush()

                # 응답 읽기
                response_line = ImageFXClient._worker_process.stdout.readline()
                if response_line:
                    init_response = json.loads(response_line.strip())
                    if init_response.get("success"):
                        ImageFXClient._worker_initialized = True
                        print(f"[ImageFX v7.1] ✅ 워커 초기화 완료")
                    else:
                        print(f"[ImageFX v7.1] ❌ 워커 초기화 실패: {init_response.get('error')}")
                        return None
            except Exception as e:
                print(f"[ImageFX v7.1] ❌ 워커 초기화 오류: {e}")
                return None

        # 이미지 생성 요청
        output_dir = Path(project_root) / "data" / "images" / "imagefx"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{uuid.uuid4()}.png")

        # 네거티브 적용
        final_prompt = self._apply_negative_prompt(prompt.strip(), negative_prompt)

        generate_request = {
            "type": "generate",
            "prompt": final_prompt,
            "outputPath": output_path,
            "model": model_value,
            "aspectRatio": aspect_value,
            "count": 1
        }

        if seed is not None:
            generate_request["seed"] = seed
            print(f"[ImageFX v7.1] ✅ 시드 {seed} → 워커로 전달")

        if negative_prompt:
            generate_request["negativePrompt"] = negative_prompt

        try:
            request_json = json.dumps(generate_request) + "\n"
            ImageFXClient._worker_process.stdin.write(request_json)
            ImageFXClient._worker_process.stdin.flush()

            # 응답 대기
            response_line = ImageFXClient._worker_process.stdout.readline()
            if not response_line:
                print(f"[ImageFX v7.1] ⚠️ 워커 응답 없음")
                return None

            response = json.loads(response_line.strip())

            if response.get("success"):
                saved_path = response.get("path", output_path)
                result_seed = response.get("seed")

                if os.path.exists(saved_path):
                    print(f"[ImageFX v7.1] ✅ 워커 생성 성공: {saved_path}")
                    if result_seed:
                        print(f"[ImageFX v7.1] 🔑 시드: {result_seed}")

                    # 쿠키 유효 표시
                    mark_cookie_valid()

                    return [GeneratedImage(
                        file_path=saved_path,
                        prompt=prompt,
                        seed=result_seed
                    )]
                else:
                    print(f"[ImageFX v7.1] ⚠️ 파일 없음: {saved_path}")
                    return None
            else:
                error_msg = response.get("error", "Unknown error")
                error_reason = response.get("errorReason")

                # 인증 에러 감지
                if is_auth_error(error_msg):
                    mark_cookie_expired(error_msg)
                    raise CookieExpiredError(
                        "ImageFX cookie has expired.\n"
                        "Please enter a new cookie in the API Management page."
                    )

                print(f"[ImageFX v7.1] ❌ 워커 생성 실패: {error_msg}")
                if error_reason:
                    print(f"[ImageFX v7.1] 에러 상세: {error_reason}")
                return None

        except CookieExpiredError:
            raise
        except json.JSONDecodeError as e:
            print(f"[ImageFX v7.1] ❌ JSON 파싱 오류: {e}")
            return None
        except Exception as e:
            print(f"[ImageFX v7.1] ❌ 워커 요청 오류: {e}")
            return None

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
        이미지 생성 (v7.1: Persistent Worker 사용)

        v7.1: 워커 프로세스 재사용으로 초기화 1회만
        v7.0: 싱글톤 + 요청 카운트 + 시드 로깅 개선

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

        # v7.0: 요청 카운트 증가
        ImageFXClient._request_count += 1
        request_num = ImageFXClient._request_count

        # v6.4: 모델/비율 값 추출 (Enum 안전 변환)
        model_value = ensure_string_value(model)
        aspect_value = ensure_string_value(aspect_ratio)

        # v7.1: 개선된 로깅 (요청 번호, 시드 상태)
        print(f"\n[ImageFX v7.1] ========== 요청 #{request_num} ==========")
        print(f"[ImageFX v7.1] 프롬프트: {prompt[:50]}...")
        print(f"[ImageFX v7.1] 모델: {model_value}, 비율: {aspect_value}")

        # v7.1: 시드 상태 명확히 로깅
        if seed is not None:
            print(f"[ImageFX v7.1] 🔒 잠긴 시드 전달: {seed}")
        else:
            print(f"[ImageFX v7.1] 🎲 시드 미지정 (Node.js에서 랜덤 생성)")

        print(f"[ImageFX v7.1] ========================================")

        # v7.1: 캐시된 쿠키 사용 (싱글톤 지원)
        cookie_to_use = ImageFXClient._cookie_cache or getattr(self, 'cookie', None)
        if not cookie_to_use:
            raise ImageFXError("쿠키가 설정되지 않았습니다.")

        # ═══════════════════════════════════════════════════════════════
        # v7.1: Persistent Worker 사용 (핵심 최적화!)
        # ═══════════════════════════════════════════════════════════════
        try:
            result = self._generate_with_worker(
                prompt=prompt,
                model_value=model_value,
                aspect_value=aspect_value,
                seed=seed,
                negative_prompt=negative_prompt,
                timeout=timeout,
                cookie=cookie_to_use
            )
            if result:
                return result
        except Exception as e:
            print(f"[ImageFX v7.1] ⚠️ 워커 실패, 폴백 사용: {e}")

        # ═══════════════════════════════════════════════════════════════
        # 폴백: 기존 subprocess 방식
        # ═══════════════════════════════════════════════════════════════
        print(f"[ImageFX v7.1] 📦 폴백: subprocess 방식 사용")

        # ⭐ v6.2: 네거티브 프롬프트를 메인 프롬프트에 추가
        final_prompt = self._apply_negative_prompt(prompt.strip(), negative_prompt)

        # npm 패키지 확인 (캐시된 project_root 사용)
        project_root = getattr(self, 'project_root', str(Path(__file__).parent.parent))
        node_script = getattr(self, 'node_script', str(Path(__file__).parent / "imagefx_node.js"))

        if not self._check_npm_package():
            raise ImageFXError(
                "@rohitaryal/imagefx-api npm 패키지가 설치되어 있지 않습니다.\n\n"
                f"설치 방법:\n"
                f"cd {project_root}\n"
                f"npm install @rohitaryal/imagefx-api"
            )

        # 출력 경로 생성
        output_dir = Path(project_root) / "data" / "images" / "imagefx"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"{uuid.uuid4()}.png")

        # Node.js 스크립트 호출 명령 (model_value, aspect_value, cookie_to_use는 이미 설정됨)
        cmd = [
            "node", node_script,
            "--cookie", cookie_to_use,  # v7.0: 캐시된 쿠키 사용
            "--prompt", final_prompt,  # ⭐ 네거티브 포함된 최종 프롬프트 사용
            "--outputPath", output_path,
            "--model", model_value,
            "--aspectRatio", aspect_value,
            "--count", str(min(num_images, 4))
        ]

        # v7.0: 시드 전달 (잠긴 시드가 있으면 전달)
        if seed is not None:
            cmd.extend(["--seed", str(seed)])
            print(f"[ImageFX v7.0] ✅ 시드 {seed} Node.js에 전달됨")

        # ⭐ 네거티브 프롬프트도 별도로 전달 (라이브러리 지원 시 사용)
        if negative_prompt:
            cmd.extend(["--negativePrompt", negative_prompt])

        # ⭐ v6.4: 방어적 코드 - 모든 cmd 인자가 문자열인지 검증
        for i, arg in enumerate(cmd):
            if isinstance(arg, Enum):
                print(f"[ImageFX v6.4] ⚠️ Enum 객체 감지! cmd[{i}] = {arg} (타입: {type(arg)})")
                cmd[i] = str(arg.value)
            elif not isinstance(arg, str):
                print(f"[ImageFX v6.4] ⚠️ 비문자열 감지! cmd[{i}] = {arg} (타입: {type(arg)})")
                cmd[i] = str(arg)

        last_error = None

        for attempt in range(retry_count):
            try:
                print(f"[ImageFX v6.3] Node.js 스크립트 실행 중... (시도 {attempt + 1}/{retry_count})")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=self.project_root,
                    encoding='utf-8',
                    errors='replace'
                )

                print(f"[ImageFX v6.3] 종료 코드: {result.returncode}")
                print(f"[ImageFX v6.3] stdout:\n{result.stdout}")
                if result.stderr:
                    print(f"[ImageFX v6.3] stderr:\n{result.stderr}")

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
                                        if result_seed is not None:
                                            print(f"[ImageFX v6.5] 🔑 시드: {result_seed}")
                                        print(f"[ImageFX v6.3] Success! Image saved: {saved_path}")
                                        # 성공 시 쿠키 유효 상태로 표시
                                        mark_cookie_valid()
                                        return [GeneratedImage(
                                            file_path=saved_path,
                                            prompt=prompt,
                                            seed=result_seed  # v1.1: 시드 저장
                                        )]
                                else:
                                    error_msg = output.get("error", "Unknown error")
                                    error_reason = output.get("errorReason")
                                    error_code = output.get("errorCode")

                                    # v6.4: 에러 reason에 따른 상세 메시지 매핑
                                    if error_reason:
                                        print(f"[ImageFX v6.4] 에러 reason: {error_reason}")
                                        error_msg = self._map_error_reason(error_reason, error_msg)

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

                # v6.4: last_error가 이미 설정된 경우 덮어쓰지 않음
                if not last_error:
                    if "not found" in combined_output.lower():
                        last_error = "imagefx-api package not found. Run: npm install imagefx-api"
                    elif "429" in combined_output or "rate limit" in combined_output.lower():
                        # v6.4: "rate" 대신 "rate limit"으로 더 정확히 매칭
                        last_error = "Rate limit exceeded. Please try again later."
                    elif "UNSAFE" in combined_output or "unsafe" in combined_output.lower():
                        # v6.4: 안전성 에러 감지
                        last_error = self._map_error_reason("PUBLIC_ERROR_UNSAFE_GENERATION", "프롬프트 안전성 문제")
                    else:
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


# ═══════════════════════════════════════════════════════════════════════════════
# ⚡ 최적화된 ImageFX Worker Manager v1.0
# ═══════════════════════════════════════════════════════════════════════════════
#
# 주요 최적화:
# 1. 싱글톤 패턴 - 워커 프로세스 1회만 시작
# 2. Persistent Worker - Node.js 프로세스 재사용
# 3. 쿠키/스타일 캐싱 - 반복 로드 방지
# 4. 병렬 처리 지원 - 동시 생성
# ═══════════════════════════════════════════════════════════════════════════════

import threading
import atexit
from concurrent.futures import ThreadPoolExecutor, as_completed


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

            # 쿠키 로드 시도
            try:
                from utils.imagefx_cookie_manager import get_imagefx_cookie
                cls._cookie_cache = get_imagefx_cookie()
                cls._cookie_loaded = True
                if cls._cookie_cache:
                    print(f"[ImageFX-Cache] ✅ 쿠키 캐시됨 (길이: {len(cls._cookie_cache)})")
                return cls._cookie_cache
            except Exception as e:
                print(f"[ImageFX-Cache] ⚠️ 쿠키 로드 실패: {e}")
                return None

    @classmethod
    def set_cookie(cls, cookie: str):
        """쿠키 캐시 설정"""
        with cls._lock:
            cls._cookie_cache = cookie
            cls._cookie_loaded = True
            print(f"[ImageFX-Cache] ✅ 쿠키 업데이트됨 (길이: {len(cookie)})")

    @classmethod
    def get_style(cls, style_id: str, segment: str = "background") -> Optional[Dict]:
        """스타일 캐시에서 가져오기"""
        key = f"{style_id}_{segment}"
        if key in cls._style_cache:
            return cls._style_cache[key]

        # 스타일 로드 시도
        try:
            from utils.style_manager import load_style
            style = load_style(style_id, segment)
            if style:
                cls._style_cache[key] = style
                print(f"[ImageFX-Cache] ✅ 스타일 캐시됨: {key}")
            return style
        except Exception as e:
            print(f"[ImageFX-Cache] ⚠️ 스타일 로드 실패 ({key}): {e}")
            return None

    @classmethod
    def clear(cls):
        """캐시 초기화"""
        with cls._lock:
            cls._cookie_cache = None
            cls._cookie_loaded = False
            cls._style_cache.clear()
            print("[ImageFX-Cache] 캐시 초기화됨")


class ImageFXWorkerManager:
    """
    Persistent Worker 관리자 (싱글톤)

    Node.js 워커 프로세스를 1회만 시작하고 재사용
    """

    _instance: Optional['ImageFXWorkerManager'] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._process: Optional[subprocess.Popen] = None
        self._worker_lock = threading.Lock()
        self._request_count = 0
        self._cookie: Optional[str] = None
        self._project_root = str(Path(__file__).parent.parent)
        self._worker_script = str(Path(__file__).parent / "imagefx_worker.js")
        self._initialized = True

        # 종료 시 워커 정리
        atexit.register(self._cleanup)

        print("[ImageFX-WorkerManager] ✅ 매니저 초기화됨")

    def _start_worker(self) -> bool:
        """워커 프로세스 시작"""
        if self._process is not None and self._process.poll() is None:
            return True  # 이미 실행 중

        try:
            self._process = subprocess.Popen(
                ["node", self._worker_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self._project_root,
                encoding='utf-8',
                errors='replace',
                bufsize=1  # Line buffered
            )

            # 워커 시작 확인 (ping)
            time.sleep(0.5)
            if self._process.poll() is not None:
                stderr = self._process.stderr.read() if self._process.stderr else ""
                print(f"[ImageFX-WorkerManager] ❌ 워커 시작 실패: {stderr[:500]}")
                return False

            print("[ImageFX-WorkerManager] ✅ 워커 프로세스 시작됨")
            return True

        except Exception as e:
            print(f"[ImageFX-WorkerManager] ❌ 워커 시작 오류: {e}")
            return False

    def _send_request(self, request: Dict, timeout: int = 180) -> Dict:
        """워커에 요청 전송"""
        with self._worker_lock:
            if not self._start_worker():
                return {"success": False, "error": "Worker process failed to start"}

            try:
                # 요청 전송
                request_json = json.dumps(request) + "\n"
                self._process.stdin.write(request_json)
                self._process.stdin.flush()

                # 응답 대기 (타임아웃 처리)
                import select
                import sys

                # Windows에서는 select가 파이프에서 작동하지 않으므로
                # 단순히 readline 사용 (블로킹)
                if sys.platform == 'win32':
                    response_line = self._process.stdout.readline()
                else:
                    # Unix 계열에서는 select 사용 가능
                    ready, _, _ = select.select([self._process.stdout], [], [], timeout)
                    if not ready:
                        return {"success": False, "error": f"Timeout ({timeout}s)"}
                    response_line = self._process.stdout.readline()

                if not response_line:
                    return {"success": False, "error": "No response from worker"}

                return json.loads(response_line.strip())

            except json.JSONDecodeError as e:
                return {"success": False, "error": f"JSON parse error: {e}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def initialize(self, cookie: str) -> bool:
        """워커 초기화 (쿠키 설정)"""
        if self._cookie == cookie:
            print("[ImageFX-WorkerManager] ⚡ 이미 초기화됨 - 스킵")
            return True

        response = self._send_request({
            "type": "init",
            "cookie": cookie
        })

        if response.get("success"):
            self._cookie = cookie
            ImageFXCache.set_cookie(cookie)
            print("[ImageFX-WorkerManager] ✅ 워커 초기화 완료")
            return True
        else:
            print(f"[ImageFX-WorkerManager] ❌ 초기화 실패: {response.get('error')}")
            return False

    def generate_image(
        self,
        prompt: str,
        output_path: Optional[str] = None,
        model: str = "IMAGEN_4",
        aspect_ratio: str = "LANDSCAPE",
        seed: Optional[int] = None,
        negative_prompt: str = "",
        timeout: int = 180
    ) -> Dict:
        """이미지 생성 (워커 사용)"""

        # 출력 경로 생성
        if not output_path:
            output_dir = Path(self._project_root) / "data" / "images" / "imagefx"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"{uuid.uuid4()}.png")

        # 네거티브 프롬프트 적용
        final_prompt = prompt
        if negative_prompt:
            final_prompt = f"{prompt.rstrip('.')}. AVOID: {negative_prompt}"

        # 모델/비율 값 추출
        model_value = ensure_string_value(model)
        aspect_value = ensure_string_value(aspect_ratio)

        self._request_count += 1

        response = self._send_request({
            "type": "generate",
            "prompt": final_prompt,
            "outputPath": output_path,
            "model": model_value,
            "aspectRatio": aspect_value,
            "seed": seed,
            "negativePrompt": negative_prompt,
            "count": 1
        }, timeout=timeout)

        return response

    def get_status(self) -> Dict:
        """워커 상태 조회"""
        return self._send_request({"type": "status"})

    def _cleanup(self):
        """워커 프로세스 정리"""
        if self._process is not None and self._process.poll() is None:
            try:
                self._send_request({"type": "shutdown"})
                self._process.wait(timeout=5)
            except:
                self._process.kill()
            print(f"[ImageFX-WorkerManager] 워커 종료됨 (총 요청: {self._request_count}개)")

    @classmethod
    def get_instance(cls) -> 'ImageFXWorkerManager':
        """싱글톤 인스턴스 반환"""
        return cls()


class ImageFXBatchGenerator:
    """
    ImageFX 순차 이미지 생성기 v4.0 (안정 버전)

    ⚠️ v4.0: 병렬 처리 완전 제거, 순차 처리로 롤백
    - 병렬 처리(v3.x)가 Rate Limit으로 12개 이후 전부 실패
    - 순차 처리가 오히려 더 빠르고 안정적
    - 요청 간 3초 대기로 Rate Limit 자연 회피

    특징:
    - 하나씩 순차적으로 생성 (병렬 처리 없음)
    - 요청 간 충분한 대기 시간 (Rate Limit 방지)
    - 실패 시 자동 재시도
    - 안정적으로 전체 완료
    """

    def __init__(
        self,
        max_workers: int = 1,  # v4.0: 무시됨 (순차 처리)
        cookie: Optional[str] = None,
        api_delay: float = 3.0  # v4.0: 요청 간 대기 시간 증가
    ):
        """
        Args:
            max_workers: 무시됨 (하위 호환성 유지용)
            cookie: ImageFX 쿠키
            api_delay: 요청 간 대기 시간 (초) - 기본 3초
        """
        self.cookie = cookie or ImageFXCache.get_cookie()
        self.api_delay = api_delay

        # v4.0: 순차 처리 설정
        self.timeout_per_image = 120  # 이미지당 최대 120초 (여유 있게)
        self.max_retries = 3  # 실패 시 최대 3회 재시도
        self.retry_delay = 10.0  # 재시도 전 대기 시간 (초) - Rate Limit 회복용

        # 프로젝트 설정
        self._project_root = str(Path(__file__).parent.parent)
        self._worker_script = str(Path(__file__).parent / "imagefx_worker.js")

        # 단일 워커 (순차 처리용)
        self._worker: Optional[subprocess.Popen] = None
        self._worker_initialized = False

        print(f"[ImageFX-Sequential v4.0] ✅ 순차 생성기 초기화됨")
        print(f"[ImageFX-Sequential v4.0]    요청 간 대기: {self.api_delay}초")
        print(f"[ImageFX-Sequential v4.0]    타임아웃: {self.timeout_per_image}초")
        print(f"[ImageFX-Sequential v4.0]    최대 재시도: {self.max_retries}회")

    def _ensure_worker(self) -> bool:
        """워커 프로세스 확인/생성 (단일 워커)"""
        # 기존 워커가 살아있으면 재사용
        if self._worker is not None and self._worker.poll() is None:
            return True

        # 워커 스크립트 확인
        if not Path(self._worker_script).exists():
            print(f"[ImageFX-Sequential v4.0] ⚠️ 워커 스크립트 없음: {self._worker_script}")
            return False

        try:
            print(f"[ImageFX-Sequential v4.0] 🚀 워커 프로세스 시작...")
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
                stderr = self._worker.stderr.read() if self._worker.stderr else ""
                print(f"[ImageFX-Sequential v4.0] ❌ 워커 시작 실패: {stderr[:200]}")
                self._worker = None
                return False

            # 쿠키 초기화
            if self.cookie:
                init_request = json.dumps({"type": "init", "cookie": self.cookie}) + "\n"
                self._worker.stdin.write(init_request)
                self._worker.stdin.flush()

                response_line = self._worker.stdout.readline()
                if response_line:
                    response = json.loads(response_line.strip())
                    if response.get("success"):
                        self._worker_initialized = True
                        print(f"[ImageFX-Sequential v4.0] ✅ 워커 초기화 완료")
                        return True
                    else:
                        print(f"[ImageFX-Sequential v4.0] ❌ 워커 초기화 실패: {response.get('error')}")
                        self._worker.kill()
                        self._worker = None
                        return False

            return True

        except Exception as e:
            print(f"[ImageFX-Sequential v4.0] ❌ 워커 시작 오류: {e}")
            self._worker = None
            return False

    def _generate_single(self, req: Dict) -> Dict:
        """
        v4.0: 단일 이미지 생성 (순차 처리, 타임아웃 포함)
        """
        import sys
        import queue

        scene_id = req.get("scene_id", "?")
        start_time = time.time()

        # 워커 확인
        if not self._ensure_worker():
            return {"success": False, "error": "Worker not available", "scene_id": scene_id}

        try:
            # 워커 상태 확인
            if self._worker.poll() is not None:
                print(f"[ImageFX-Sequential v4.0] ⚠️ 워커 종료됨 - 재시작 필요")
                self._worker = None
                self._worker_initialized = False
                if not self._ensure_worker():
                    return {"success": False, "error": "Worker restart failed", "scene_id": scene_id}

            # 요청 구성
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

            # 요청 전송
            request_json = json.dumps(request) + "\n"
            self._worker.stdin.write(request_json)
            self._worker.stdin.flush()

            # 응답 대기 (타임아웃 포함)
            response_line = None

            if sys.platform == 'win32':
                # Windows: 별도 스레드로 타임아웃 구현
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
                        # 워커 오류 - 워커 종료
                        print(f"[ImageFX-Sequential v4.0] ❌ 워커 오류: {data}")
                        self._cleanup_worker()
                        return {"success": False, "error": f"Worker error: {data}", "scene_id": scene_id}
                except queue.Empty:
                    elapsed = time.time() - start_time
                    print(f"[ImageFX-Sequential v4.0] ⏰ 타임아웃 ({elapsed:.1f}초)")
                    # 타임아웃 시 워커 종료 (다음 요청에서 재시작)
                    self._cleanup_worker()
                    return {"success": False, "error": f"Timeout ({self.timeout_per_image}s)", "scene_id": scene_id}
            else:
                # Unix: select 사용
                import select
                ready, _, _ = select.select([self._worker.stdout], [], [], self.timeout_per_image)
                if not ready:
                    elapsed = time.time() - start_time
                    print(f"[ImageFX-Sequential v4.0] ⏰ 타임아웃 ({elapsed:.1f}초)")
                    self._cleanup_worker()
                    return {"success": False, "error": f"Timeout ({self.timeout_per_image}s)", "scene_id": scene_id}
                response_line = self._worker.stdout.readline()

            if not response_line:
                print(f"[ImageFX-Sequential v4.0] ⚠️ 응답 없음")
                self._cleanup_worker()
                return {"success": False, "error": "No response", "scene_id": scene_id}

            response = json.loads(response_line.strip())
            response["scene_id"] = scene_id
            return response

        except json.JSONDecodeError as e:
            print(f"[ImageFX-Sequential v4.0] ❌ JSON 오류: {e}")
            return {"success": False, "error": f"JSON error: {e}", "scene_id": scene_id}
        except Exception as e:
            print(f"[ImageFX-Sequential v4.0] ❌ 예외: {e}")
            import traceback
            traceback.print_exc()
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
        v4.0: 순차 이미지 생성 (병렬 처리 없음)

        Args:
            requests: 요청 리스트 [{"prompt": "...", "model": "...", "scene_id": ...}, ...]
            progress_callback: 진행률 콜백 (completed, total)

        Returns:
            결과 리스트 [{"success": True, "path": "...", "scene_id": ...}, ...]
        """
        total = len(requests)

        if total == 0:
            return []

        print(f"\n[ImageFX-Sequential v4.0] ========== 순차 이미지 생성 시작 ==========")
        print(f"[ImageFX-Sequential v4.0] 총 {total}개 이미지")
        print(f"[ImageFX-Sequential v4.0] 요청 간 대기: {self.api_delay}초")
        print(f"[ImageFX-Sequential v4.0] 예상 소요 시간: 약 {total * (self.api_delay + 8):.0f}초")

        start_time = time.time()
        results = []
        failed_items = []  # (index, request) 튜플 저장

        # ═══════════════════════════════════════════════════════════════
        # v4.0: 순차 처리 - 하나씩 차례대로 생성
        # ═══════════════════════════════════════════════════════════════
        for i, req in enumerate(requests):
            index = i + 1
            scene_id = req.get("scene_id", i)

            print(f"\n[ImageFX-Sequential v4.0] [{index}/{total}] scene {scene_id} 생성 중...")

            # 진행률 콜백
            if progress_callback:
                try:
                    progress_callback(i, total)
                except Exception:
                    pass

            # 이미지 생성
            result = self._generate_single(req)
            result["scene_id"] = scene_id

            if result.get("success"):
                print(f"[ImageFX-Sequential v4.0] ✅ [{index}/{total}] scene {scene_id} 완료")
                results.append(result)
            else:
                error_msg = result.get("error", "Unknown")[:50]
                print(f"[ImageFX-Sequential v4.0] ❌ [{index}/{total}] scene {scene_id} 실패: {error_msg}")
                results.append(result)
                failed_items.append((i, req))

            # 다음 요청 전 대기 (마지막 제외)
            if i < total - 1:
                print(f"[ImageFX-Sequential v4.0] 💤 {self.api_delay}초 대기...")
                time.sleep(self.api_delay)

            # 진행률 콜백 (완료 후)
            if progress_callback:
                try:
                    progress_callback(index, total)
                except Exception:
                    pass

        # ═══════════════════════════════════════════════════════════════
        # v4.0: 실패 항목 재시도 (순차적으로)
        # ═══════════════════════════════════════════════════════════════
        if failed_items and self.max_retries > 0:
            print(f"\n[ImageFX-Sequential v4.0] 🔄 실패 항목 재시도: {len(failed_items)}개")

            for retry in range(self.max_retries):
                if not failed_items:
                    break

                print(f"[ImageFX-Sequential v4.0] 재시도 {retry+1}/{self.max_retries}")
                print(f"[ImageFX-Sequential v4.0] 💤 Rate Limit 회복 대기 {self.retry_delay}초...")
                time.sleep(self.retry_delay)

                still_failed = []

                for orig_idx, req in failed_items:
                    scene_id = req.get("scene_id", orig_idx)
                    print(f"[ImageFX-Sequential v4.0] 🔄 scene {scene_id} 재시도...")

                    result = self._generate_single(req)
                    result["scene_id"] = scene_id

                    if result.get("success"):
                        print(f"[ImageFX-Sequential v4.0] ✅ scene {scene_id} 재시도 성공!")
                        results[orig_idx] = result
                    else:
                        print(f"[ImageFX-Sequential v4.0] ❌ scene {scene_id} 재시도 실패")
                        still_failed.append((orig_idx, req))

                    # 재시도 간에도 대기
                    time.sleep(self.api_delay)

                failed_items = still_failed

        # 결과 정렬 (scene_id 순)
        results.sort(key=lambda r: r.get("scene_id", 0) if isinstance(r.get("scene_id"), int) else 0)

        # 완료 요약
        elapsed = time.time() - start_time
        success_count = sum(1 for r in results if r.get("success"))

        print(f"\n[ImageFX-Sequential v4.0] ========== 생성 완료 ==========")
        print(f"[ImageFX-Sequential v4.0] ✅ 성공: {success_count}/{total}")
        print(f"[ImageFX-Sequential v4.0] ❌ 실패: {total - success_count}/{total}")
        print(f"[ImageFX-Sequential v4.0] ⏱️ 총 시간: {elapsed:.1f}초")
        if total > 0:
            print(f"[ImageFX-Sequential v4.0] 📊 이미지당 평균: {elapsed/total:.1f}초")

        return results

    def cleanup(self):
        """리소스 정리"""
        self._cleanup_worker()
        print(f"[ImageFX-Sequential v4.0] ✅ 리소스 정리 완료")


def get_optimized_imagefx_client(cookie: Optional[str] = None) -> ImageFXWorkerManager:
    """
    최적화된 ImageFX 클라이언트 반환 (권장)

    싱글톤 워커 매니저를 사용하여 프로세스 재사용
    """
    cookie = cookie or ImageFXCache.get_cookie()

    manager = ImageFXWorkerManager.get_instance()

    if cookie:
        manager.initialize(cookie)

    return manager


def generate_image_optimized(
    prompt: str,
    cookie: Optional[str] = None,
    model: str = "IMAGEN_4",
    aspect_ratio: str = "LANDSCAPE",
    seed: Optional[int] = None,
    negative_prompt: str = "",
    timeout: int = 180
) -> Optional[GeneratedImage]:
    """
    최적화된 단일 이미지 생성 함수

    기존 ImageFXClient.generate_image()를 대체하는 편의 함수
    """
    manager = get_optimized_imagefx_client(cookie)

    result = manager.generate_image(
        prompt=prompt,
        model=model,
        aspect_ratio=aspect_ratio,
        seed=seed,
        negative_prompt=negative_prompt,
        timeout=timeout
    )

    if result.get("success"):
        return GeneratedImage(
            file_path=result.get("path", ""),
            prompt=prompt,
            seed=result.get("seed")
        )
    else:
        raise ImageFXError(f"Image generation failed: {result.get('error')}")


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
