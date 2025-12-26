# -*- coding: utf-8 -*-
"""
Google ImageFX (Imagen) API 클라이언트 v6.1

rohitaryal/imageFX-api Node.js 라이브러리 직접 사용
Python에서 Node.js 스크립트를 subprocess로 호출

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
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ImagenModel(Enum):
    """지원되는 Imagen 모델"""
    IMAGEN_3_5 = "IMAGEN_3_5"
    IMAGEN_3 = "IMAGEN_3"
    IMAGEN_4 = "IMAGEN_3"  # 호환성
    IMAGEN_3_1 = "IMAGEN_3"
    DEFAULT = "IMAGEN_3"


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
    {"value": "IMAGEN_3_5", "label": "Imagen 3.5 (최신)", "description": "최신 모델"},
    {"value": "IMAGEN_3", "label": "Imagen 3", "description": "안정적"},
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


@dataclass
class GeneratedImage:
    """생성된 이미지 데이터"""
    file_path: str
    media_id: str = ""
    prompt: str = ""

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

        print(f"[ImageFX v6.1] 초기화 완료 (Node.js 래퍼 사용)")
        print(f"[ImageFX v6.1] 쿠키 길이: {len(self.cookie)}")
        print(f"[ImageFX v6.1] Node 스크립트: {self.node_script}")

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
                print(f"[ImageFX v6.1] Node.js 버전: {result.stdout.strip()}")
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

    def generate_image(
        self,
        prompt: str,
        model: ImagenModel = ImagenModel.IMAGEN_3,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        num_images: int = 1,
        seed: Optional[int] = None,
        retry_count: int = 3,
        timeout: int = 180
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

        Returns:
            List[GeneratedImage]: 생성된 이미지 리스트
        """
        if not prompt or not prompt.strip():
            raise ImageFXError("프롬프트가 비어있습니다.")

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

        # 비율 값 추출
        aspect_value = aspect_ratio.value if isinstance(aspect_ratio, AspectRatio) else aspect_ratio

        # 모델 값 추출
        model_value = model.value if isinstance(model, ImagenModel) else model

        print(f"\n[ImageFX v6.1] ========== 이미지 생성 ==========")
        print(f"[ImageFX v6.1] 프롬프트: {prompt[:60]}...")
        print(f"[ImageFX v6.1] 모델: {model_value}")
        print(f"[ImageFX v6.1] 비율: {aspect_value}")
        print(f"[ImageFX v6.1] 출력 경로: {output_path}")
        print(f"[ImageFX v6.1] ===================================")

        # Node.js 스크립트 호출 명령
        cmd = [
            "node", self.node_script,
            "--cookie", self.cookie,
            "--prompt", prompt.strip(),
            "--outputPath", output_path,
            "--model", model_value,
            "--aspectRatio", aspect_value,
            "--count", str(min(num_images, 4))
        ]

        if seed is not None:
            cmd.extend(["--seed", str(seed)])

        last_error = None

        for attempt in range(retry_count):
            try:
                print(f"[ImageFX v6.1] Node.js 스크립트 실행 중... (시도 {attempt + 1}/{retry_count})")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=self.project_root,
                    encoding='utf-8',
                    errors='replace'
                )

                print(f"[ImageFX v6.1] 종료 코드: {result.returncode}")
                print(f"[ImageFX v6.1] stdout:\n{result.stdout}")
                if result.stderr:
                    print(f"[ImageFX v6.1] stderr:\n{result.stderr}")

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
                                        print(f"[ImageFX v6.1] ✅ 성공! 이미지 저장됨: {saved_path}")
                                        return [GeneratedImage(
                                            file_path=saved_path,
                                            prompt=prompt
                                        )]
                                else:
                                    last_error = output.get("error", "알 수 없는 오류")
                            except json.JSONDecodeError as e:
                                print(f"[ImageFX v6.1] JSON 파싱 오류: {e}")

                # 파일이 생성되었는지 직접 확인
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    print(f"[ImageFX v6.1] ✅ 파일 직접 확인 성공: {output_path}")
                    return [GeneratedImage(
                        file_path=output_path,
                        prompt=prompt
                    )]

                # 실패 원인 분석
                combined_output = result.stdout + result.stderr
                if "찾을 수 없습니다" in combined_output or "not found" in combined_output.lower():
                    last_error = "imagefx-api 패키지를 찾을 수 없습니다. npm install imagefx-api 실행 필요"
                elif "401" in combined_output or "unauthorized" in combined_output.lower():
                    last_error = "인증 실패: 쿠키가 만료되었거나 유효하지 않습니다."
                elif "429" in combined_output or "rate" in combined_output.lower():
                    last_error = "요청 제한: 잠시 후 다시 시도하세요."
                elif not last_error:
                    last_error = combined_output[:500] if combined_output else "알 수 없는 오류"

            except subprocess.TimeoutExpired:
                print(f"[ImageFX v6.1] 타임아웃 ({timeout}초)")
                last_error = f"타임아웃 ({timeout}초)"

            except Exception as e:
                print(f"[ImageFX v6.1] 오류: {e}")
                last_error = str(e)

            # 재시도 대기
            if attempt < retry_count - 1:
                wait_time = 3 * (attempt + 1)
                print(f"[ImageFX v6.1] {wait_time}초 후 재시도...")
                time.sleep(wait_time)

        raise ImageFXError(f"이미지 생성 실패: {last_error}")

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
        print("[ImageFX v6.1] 경고: access_token은 더 이상 지원되지 않습니다. cookie를 사용하세요.")
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
