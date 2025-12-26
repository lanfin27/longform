"""
배경 제거 유틸리티

캐릭터 이미지에서 배경을 제거하고 투명 PNG로 저장

개선 사항 (v2):
- 다양한 rembg 모델 지원 (isnet-general-use, isnet-anime 등)
- alpha_matting으로 경계 품질 개선
- 캐릭터 내부 구멍 자동 보정
- 마스크 확장 옵션
"""
import os
from pathlib import Path
from PIL import Image
from io import BytesIO
from typing import Optional, Union, Literal
import hashlib
import base64

# 지원하는 배경 제거 모델
SUPPORTED_MODELS = [
    "isnet-general-use",   # 일반 용도, 정밀한 경계 (권장)
    "isnet-anime",         # 애니메이션/일러스트 특화
    "u2net",               # 기본 모델
    "u2net_human_seg",     # 사람 세그멘테이션 특화
    "silueta",             # 실루엣 추출
]

DEFAULT_MODEL = "isnet-general-use"


class BackgroundRemover:
    """배경 제거 클래스"""

    def __init__(self, cache_dir: str = "data/cache/nobg"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._rembg_available = self._check_rembg()

    def _check_rembg(self) -> bool:
        """rembg 라이브러리 사용 가능 여부 확인"""
        try:
            import rembg
            return True
        except ImportError:
            print("[BackgroundRemover] rembg 미설치. pip install rembg 실행 필요")
            return False

    def _get_cache_path(self, image_source: str) -> Path:
        """캐시 파일 경로 생성"""
        # URL/경로 해시로 고유 파일명 생성
        source_hash = hashlib.md5(image_source.encode()).hexdigest()[:12]
        return self.cache_dir / f"nobg_{source_hash}.png"

    def remove_background(
        self,
        image_source: Union[str, Image.Image],
        force: bool = False,
        model: str = DEFAULT_MODEL,
        alpha_matting: bool = True,
        fix_holes: bool = True,
        expand_mask: int = 0
    ) -> Optional[str]:
        """
        이미지에서 배경 제거

        Args:
            image_source: 이미지 URL, 파일 경로, 또는 PIL Image
            force: 캐시 무시하고 강제 재처리
            model: 사용할 모델 (isnet-general-use, isnet-anime, u2net 등)
            alpha_matting: 알파 매팅으로 경계 품질 개선
            fix_holes: 캐릭터 내부 구멍 메우기
            expand_mask: 마스크 확장 픽셀 수 (경계 보완)

        Returns:
            배경 제거된 이미지 파일 경로 (PNG)
        """

        # 이미지 로드
        if isinstance(image_source, str):
            # 캐시 확인 (모델과 옵션에 따라 다른 캐시)
            cache_key = f"{image_source}_{model}_{alpha_matting}_{fix_holes}_{expand_mask}"
            cache_path = self._get_cache_path(cache_key)
            if not force and cache_path.exists():
                print(f"[BackgroundRemover] 캐시 사용: {cache_path}")
                return str(cache_path)

            # URL 또는 파일 경로에서 로드
            image = self._load_image(image_source)
            if image is None:
                return None
        else:
            image = image_source
            cache_path = self._get_cache_path(str(id(image)))

        # 이미 투명 배경인지 확인
        if self._has_transparency(image):
            print("[BackgroundRemover] 이미 투명 배경 이미지")
            # 그래도 PNG로 저장 (캐시)
            image.save(str(cache_path), "PNG")
            return str(cache_path)

        # 배경 제거
        if self._rembg_available:
            result_image = self._remove_with_rembg(
                image,
                model=model,
                alpha_matting=alpha_matting,
                fix_holes=fix_holes,
                expand_mask=expand_mask
            )
        else:
            # rembg 없으면 간단한 방법으로 시도
            result_image = self._remove_simple(image)

        if result_image:
            result_image.save(str(cache_path), "PNG")
            print(f"[BackgroundRemover] 배경 제거 완료: {cache_path}")
            return str(cache_path)

        return None

    def _load_image(self, source: str) -> Optional[Image.Image]:
        """이미지 로드"""
        try:
            if source.startswith('http'):
                import requests
                response = requests.get(source, timeout=10)
                return Image.open(BytesIO(response.content))
            elif source.startswith('data:'):
                # Data URI 처리
                header, data = source.split(',', 1)
                image_data = base64.b64decode(data)
                return Image.open(BytesIO(image_data))
            else:
                path = Path(source)
                if path.exists():
                    return Image.open(path)
                else:
                    print(f"[BackgroundRemover] 파일 없음: {source}")
                    return None
        except Exception as e:
            print(f"[BackgroundRemover] 이미지 로드 실패: {e}")
            return None

    def _has_transparency(self, image: Image.Image) -> bool:
        """이미지에 투명 영역이 있는지 확인"""
        if image.mode == 'RGBA':
            # 알파 채널 확인
            alpha = image.split()[-1]
            # 완전 불투명(255)이 아닌 픽셀이 있는지
            extrema = alpha.getextrema()
            return extrema[0] < 255
        return False

    def _remove_with_rembg(
        self,
        image: Image.Image,
        model: str = DEFAULT_MODEL,
        alpha_matting: bool = True,
        fix_holes: bool = True,
        expand_mask: int = 0
    ) -> Optional[Image.Image]:
        """
        rembg로 고품질 배경 제거

        Args:
            image: 입력 이미지
            model: 사용할 모델 (isnet-general-use, isnet-anime, u2net 등)
            alpha_matting: 알파 매팅으로 경계 품질 개선
            fix_holes: 캐릭터 내부 구멍 메우기
            expand_mask: 마스크 확장 픽셀 수 (경계 보완)

        Returns:
            배경이 제거된 RGBA 이미지
        """
        try:
            from rembg import remove, new_session

            # RGBA로 변환
            if image.mode != 'RGBA':
                image = image.convert('RGBA')

            # 이미지를 바이트로 변환
            img_bytes = BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            # 세션 생성 (모델 지정)
            try:
                session = new_session(model)
                print(f"[BackgroundRemover] 모델 사용: {model}")
            except Exception as e:
                print(f"[BackgroundRemover] 모델 '{model}' 로드 실패, 기본값 사용: {e}")
                session = None

            # 배경 제거 옵션
            remove_kwargs = {
                "data": img_bytes.read(),
            }

            if session:
                remove_kwargs["session"] = session

            # alpha_matting 옵션 (경계 품질 개선)
            if alpha_matting:
                remove_kwargs["alpha_matting"] = True
                remove_kwargs["alpha_matting_foreground_threshold"] = 240
                remove_kwargs["alpha_matting_background_threshold"] = 10
                remove_kwargs["alpha_matting_erode_size"] = 10

            # 배경 제거 실행
            output = remove(**remove_kwargs)
            result = Image.open(BytesIO(output)).convert("RGBA")

            # 후처리: 내부 구멍 메우기
            if fix_holes:
                result = self._fix_foreground_holes(result)

            # 후처리: 마스크 확장
            if expand_mask > 0:
                result = self._expand_foreground_mask(result, expand_mask)

            return result

        except Exception as e:
            print(f"[BackgroundRemover] rembg 오류: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _fix_foreground_holes(
        self,
        image: Image.Image,
        min_hole_size: int = 500
    ) -> Image.Image:
        """
        전경(캐릭터) 내부의 작은 구멍(잘못 제거된 부분) 메우기

        rembg가 캐릭터 몸통/팔 사이 등을 잘못 투명하게 만드는 문제 해결
        """
        try:
            import numpy as np

            # OpenCV 사용 가능하면 사용, 아니면 간단한 방법
            try:
                import cv2
                return self._fix_holes_cv2(image, min_hole_size)
            except ImportError:
                return self._fix_holes_simple(image, min_hole_size)

        except Exception as e:
            print(f"[BackgroundRemover] 구멍 메우기 실패: {e}")
            return image

    def _fix_holes_cv2(self, image: Image.Image, min_hole_size: int) -> Image.Image:
        """OpenCV를 사용한 구멍 메우기"""
        import cv2
        import numpy as np

        img_array = np.array(image)
        alpha = img_array[:, :, 3]

        # 알파 채널 이진화
        _, binary = cv2.threshold(alpha, 127, 255, cv2.THRESH_BINARY)

        # 컨투어 찾기 (내부 구멍 포함)
        contours, hierarchy = cv2.findContours(
            binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
        )

        # 내부 구멍 중 작은 것만 메우기
        if hierarchy is not None:
            filled_count = 0
            for i, contour in enumerate(contours):
                # hierarchy[0][i][3] >= 0 이면 부모가 있음 = 내부 구멍
                if hierarchy[0][i][3] >= 0:
                    area = cv2.contourArea(contour)
                    if area < min_hole_size:
                        cv2.drawContours(binary, [contour], -1, 255, -1)
                        filled_count += 1

            if filled_count > 0:
                print(f"[BackgroundRemover] {filled_count}개 내부 구멍 메움")

        # 모폴로지 연산으로 경계 정리
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        # 새 알파 채널 적용
        img_array[:, :, 3] = binary

        return Image.fromarray(img_array, 'RGBA')

    def _fix_holes_simple(self, image: Image.Image, min_hole_size: int) -> Image.Image:
        """간단한 방법으로 구멍 메우기 (OpenCV 없이)"""
        import numpy as np
        from PIL import ImageFilter

        img_array = np.array(image)
        alpha = img_array[:, :, 3]

        # 알파 채널을 PIL Image로 변환
        alpha_img = Image.fromarray(alpha, 'L')

        # 팽창(dilation) 효과로 작은 구멍 메우기
        # MaxFilter는 주변 픽셀 중 최댓값 사용 -> 밝은 영역 확장
        alpha_dilated = alpha_img.filter(ImageFilter.MaxFilter(5))

        # 다시 원본 크기로 축소하면서 경계 부드럽게
        alpha_closed = alpha_dilated.filter(ImageFilter.MinFilter(3))

        # 새 알파 채널 적용
        img_array[:, :, 3] = np.array(alpha_closed)

        return Image.fromarray(img_array, 'RGBA')

    def _expand_foreground_mask(self, image: Image.Image, expand_pixels: int = 2) -> Image.Image:
        """전경 마스크를 약간 확장하여 경계 부분 보완"""
        try:
            import numpy as np

            img_array = np.array(image)
            alpha = img_array[:, :, 3]

            try:
                import cv2
                # OpenCV dilation
                kernel = np.ones((expand_pixels * 2 + 1, expand_pixels * 2 + 1), np.uint8)
                dilated = cv2.dilate(alpha, kernel, iterations=1)
                img_array[:, :, 3] = dilated
            except ImportError:
                # PIL 기반 확장
                from PIL import ImageFilter
                alpha_img = Image.fromarray(alpha, 'L')
                alpha_expanded = alpha_img.filter(ImageFilter.MaxFilter(expand_pixels * 2 + 1))
                img_array[:, :, 3] = np.array(alpha_expanded)

            return Image.fromarray(img_array, 'RGBA')

        except Exception as e:
            print(f"[BackgroundRemover] 마스크 확장 실패: {e}")
            return image

    def _remove_simple(self, image: Image.Image, tolerance: int = 30) -> Optional[Image.Image]:
        """
        간단한 배경 제거 (모서리 색상 기반)

        rembg가 없을 때 사용하는 대체 방법
        """
        try:
            image = image.convert('RGBA')
            data = list(image.getdata())

            # 모서리 4개 픽셀의 평균 색상을 배경색으로 가정
            width, height = image.size
            corners = [
                image.getpixel((0, 0)),
                image.getpixel((width-1, 0)),
                image.getpixel((0, height-1)),
                image.getpixel((width-1, height-1))
            ]

            # 가장 많이 나타나는 색상을 배경색으로
            from collections import Counter
            # RGB만 비교 (알파 제외)
            corner_rgb = [c[:3] for c in corners]
            bg_color = Counter(corner_rgb).most_common(1)[0][0]

            # 배경색과 유사한 픽셀을 투명하게
            new_data = []
            for item in data:
                r, g, b = item[:3]
                bg_r, bg_g, bg_b = bg_color

                # 색상 차이 계산
                diff = abs(r - bg_r) + abs(g - bg_g) + abs(b - bg_b)

                if diff < tolerance * 3:
                    # 배경으로 판단 -> 투명하게
                    new_data.append((r, g, b, 0))
                else:
                    # 전경 유지
                    a = item[3] if len(item) > 3 else 255
                    new_data.append((r, g, b, a))

            image.putdata(new_data)
            return image

        except Exception as e:
            print(f"[BackgroundRemover] 간단 배경 제거 오류: {e}")
            return None

    def get_transparent_path(self, original_path: str) -> str:
        """
        원본 이미지 경로에서 투명 배경 버전 경로 반환

        이미 처리된 캐시가 있으면 해당 경로, 없으면 처리 후 반환
        """
        if not original_path:
            return original_path

        cache_path = self._get_cache_path(original_path)

        if cache_path.exists():
            return str(cache_path)

        # 배경 제거 실행
        result = self.remove_background(original_path)
        return result if result else original_path


# 싱글톤
_remover: Optional[BackgroundRemover] = None


def get_background_remover() -> BackgroundRemover:
    """BackgroundRemover 싱글톤 인스턴스 반환"""
    global _remover
    if _remover is None:
        _remover = BackgroundRemover()
    return _remover


def ensure_transparent_background(
    image_path: str,
    model: str = DEFAULT_MODEL,
    fix_holes: bool = True
) -> str:
    """
    이미지의 투명 배경 버전 경로 반환

    Args:
        image_path: 원본 이미지 경로
        model: 사용할 모델 (isnet-general-use, isnet-anime 등)
        fix_holes: 내부 구멍 메우기 여부

    사용 예:
        transparent_path = ensure_transparent_background(char["image_path"])
        # 애니메이션 캐릭터용
        transparent_path = ensure_transparent_background(char["image_path"], model="isnet-anime")
    """
    if not image_path:
        return image_path

    remover = get_background_remover()
    result = remover.remove_background(
        image_path,
        model=model,
        fix_holes=fix_holes
    )
    return result if result else image_path


def remove_background_high_quality(
    image_path: str,
    model: str = "isnet-general-use",
    fix_holes: bool = True,
    expand_mask: int = 2
) -> str:
    """
    고품질 배경 제거 (캐릭터 내부 구멍 보정 포함)

    캐릭터 팔/몸통 사이 등이 잘못 투명해지는 문제 해결

    Args:
        image_path: 원본 이미지 경로
        model: 사용할 모델
        fix_holes: 내부 구멍 메우기
        expand_mask: 마스크 확장 픽셀 (경계 보완)

    Returns:
        배경 제거된 이미지 경로
    """
    if not image_path:
        return image_path

    remover = get_background_remover()
    result = remover.remove_background(
        image_path,
        model=model,
        alpha_matting=True,
        fix_holes=fix_holes,
        expand_mask=expand_mask
    )
    return result if result else image_path


# ============================================================
# 편의 함수 (스토리보드 UI용)
# ============================================================

def is_rembg_available() -> tuple:
    """
    rembg 사용 가능 여부 확인

    Returns:
        (available: bool, message: str)
    """
    try:
        import rembg
        return True, "✅ rembg 사용 가능"
    except ImportError:
        return False, "❌ rembg 미설치. 설치: pip install rembg --break-system-packages"


def has_transparency(image_path: str, threshold: float = 0.05) -> bool:
    """
    이미지에 투명 배경이 있는지 확인

    Args:
        image_path: 이미지 경로
        threshold: 투명 픽셀 비율 임계값 (기본 5%)

    Returns:
        True if 투명 배경 있음
    """
    try:
        with Image.open(image_path) as img:
            if img.mode != 'RGBA':
                return False

            alpha = img.split()[-1]
            alpha_data = list(alpha.getdata())

            transparent_pixels = sum(1 for a in alpha_data if a < 250)
            total_pixels = len(alpha_data)

            return (transparent_pixels / total_pixels) > threshold

    except Exception:
        return False


def remove_background_simple(
    input_path: str,
    output_path: str = None,
    force: bool = False
) -> str:
    """
    간단한 배경 제거 API

    Args:
        input_path: 입력 이미지 경로
        output_path: 출력 경로 (None이면 캐시 사용)
        force: 캐시 무시

    Returns:
        배경 제거된 이미지 경로
    """
    remover = get_background_remover()
    result = remover.remove_background(input_path, force=force)

    if result and output_path:
        import shutil
        shutil.copy2(result, output_path)
        return output_path

    return result if result else input_path


def remove_background_batch(
    image_paths: list,
    output_dir: str = None,
    force: bool = False,
    progress_callback=None
) -> list:
    """
    여러 이미지 배경 일괄 제거

    Args:
        image_paths: 이미지 경로 목록
        output_dir: 출력 디렉토리
        force: 캐시 무시
        progress_callback: (current, total, filename) 콜백

    Returns:
        출력 파일 경로 목록
    """
    results = []
    total = len(image_paths)
    remover = get_background_remover()

    for i, img_path in enumerate(image_paths):
        filename = Path(img_path).name

        if progress_callback:
            progress_callback(i + 1, total, filename)

        result = remover.remove_background(img_path, force=force)

        if result:
            if output_dir:
                import shutil
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                output_path = Path(output_dir) / f"{Path(img_path).stem}_nobg.png"
                shutil.copy2(result, output_path)
                results.append(str(output_path))
            else:
                results.append(result)

    return results


def install_rembg_ui(key_suffix: str = None):
    """
    Streamlit UI에서 rembg 설치 안내 및 버튼 제공

    Args:
        key_suffix: 고유 키 접미사 (중복 호출 시 필수)
                   예: "auto_match", "manual", "settings"
    """
    try:
        import streamlit as st
    except ImportError:
        print("Streamlit이 필요합니다")
        return

    import subprocess
    import sys
    import uuid

    # 고유 키 생성 (중복 방지)
    if key_suffix:
        unique_key = f"install_rembg_auto_{key_suffix}"
    else:
        # 폴백: UUID 사용 (권장하지 않음 - 매번 다른 키 생성)
        unique_key = f"install_rembg_auto_{uuid.uuid4().hex[:8]}"

    st.warning("⚠️ 배경 제거 기능을 사용하려면 rembg를 설치해야 합니다.")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📦 자동 설치", key=unique_key):
            with st.spinner("rembg 설치 중... (약 1-2분 소요)"):
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "rembg", "--break-system-packages"],
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if result.returncode == 0:
                    st.success("✅ 설치 완료! 페이지를 새로고침하세요.")
                    # 상태 리셋
                    global _remover
                    _remover = None
                    st.rerun()
                else:
                    st.error(f"설치 실패: {result.stderr[:200]}")
                    st.info("터미널에서 직접 설치를 시도하세요")

    with col2:
        st.code("pip install rembg", language="bash")
        st.caption("터미널에서 직접 실행")


def auto_install_rembg(progress_callback=None) -> tuple:
    """
    rembg 자동 설치 (백그라운드)

    Args:
        progress_callback: (step, total, message) 콜백

    Returns:
        (success: bool, message: str)
    """
    import subprocess
    import sys

    steps = [
        ("pip 업그레이드", [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]),
        ("rembg 설치", [sys.executable, "-m", "pip", "install", "rembg", "--break-system-packages"]),
    ]

    for i, (step_name, cmd) in enumerate(steps):
        if progress_callback:
            progress_callback(i + 1, len(steps), step_name)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode != 0 and "rembg" in step_name:
                return False, f"{step_name} 실패: {result.stderr[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"{step_name} 시간 초과"
        except Exception as e:
            return False, f"{step_name} 오류: {e}"

    # 설치 확인
    try:
        import importlib
        importlib.invalidate_caches()
        import rembg
        return True, "✅ rembg 설치 완료!"
    except ImportError:
        return False, "설치는 되었으나 import 실패. 앱을 재시작하세요."


def get_rembg_diagnostic() -> dict:
    """
    rembg 상세 진단 정보 반환

    Returns:
        {
            'available': bool,
            'message': str,
            'version': str or None,
            'models': list,
            'onnx_available': bool,
            'install_command': str
        }
    """
    result = {
        'available': False,
        'message': '',
        'version': None,
        'models': [],
        'onnx_available': False,
        'install_command': 'pip install rembg --break-system-packages'
    }

    # ONNX Runtime 확인
    try:
        import onnxruntime
        result['onnx_available'] = True
    except ImportError:
        result['onnx_available'] = False

    # rembg 확인
    try:
        import rembg
        result['available'] = True
        result['version'] = getattr(rembg, '__version__', 'unknown')
        result['message'] = f"✅ rembg v{result['version']} 사용 가능"
        result['models'] = SUPPORTED_MODELS
    except ImportError as e:
        result['message'] = f"❌ rembg 미설치: {e}"

    return result


def ensure_rembg_installed() -> bool:
    """
    rembg가 설치되어 있는지 확인하고, 없으면 설치 시도

    Returns:
        bool: 사용 가능 여부
    """
    try:
        import rembg
        return True
    except ImportError:
        pass

    # 자동 설치 시도
    success, msg = auto_install_rembg()
    if success:
        try:
            import importlib
            importlib.invalidate_caches()
            import rembg
            return True
        except ImportError:
            pass

    return False
