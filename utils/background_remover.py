"""
배경 제거 유틸리티

캐릭터 이미지에서 배경을 제거하고 투명 PNG로 저장
"""
import os
from pathlib import Path
from PIL import Image
from io import BytesIO
from typing import Optional, Union
import hashlib
import base64


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
        force: bool = False
    ) -> Optional[str]:
        """
        이미지에서 배경 제거

        Args:
            image_source: 이미지 URL, 파일 경로, 또는 PIL Image
            force: 캐시 무시하고 강제 재처리

        Returns:
            배경 제거된 이미지 파일 경로 (PNG)
        """

        # 이미지 로드
        if isinstance(image_source, str):
            # 캐시 확인
            cache_path = self._get_cache_path(image_source)
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
            result_image = self._remove_with_rembg(image)
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

    def _remove_with_rembg(self, image: Image.Image) -> Optional[Image.Image]:
        """rembg로 배경 제거"""
        try:
            from rembg import remove

            # RGBA로 변환
            if image.mode != 'RGBA':
                image = image.convert('RGBA')

            # 배경 제거
            result = remove(image)
            return result

        except Exception as e:
            print(f"[BackgroundRemover] rembg 오류: {e}")
            return None

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


def ensure_transparent_background(image_path: str) -> str:
    """
    이미지의 투명 배경 버전 경로 반환

    사용 예:
        transparent_path = ensure_transparent_background(char["image_path"])
    """
    if not image_path:
        return image_path

    remover = get_background_remover()
    return remover.get_transparent_path(image_path)
