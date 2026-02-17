# -*- coding: utf-8 -*-
"""
이미지 캐시 관리자 (v1.0)

MediaFileStorageError 해결:
- st.image(bytes) 대신 st.image(파일경로) 사용
- 썸네일 캐싱으로 성능 향상
"""

import os
import hashlib
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime
import streamlit as st
from PIL import Image
import io


class ImageCache:
    """이미지 캐시 관리자"""

    # 클래스 레벨 캐시
    _image_list_cache = {}
    _cache_time = {}

    # 캐시 만료 시간 (초)
    CACHE_EXPIRY = 30

    @classmethod
    def get_image_list(cls, folder_path: str, force_refresh: bool = False) -> List[str]:
        """
        폴더의 이미지 목록 가져오기 (캐싱)
        """

        folder_path = str(Path(folder_path).resolve())
        current_time = datetime.now().timestamp()

        # 캐시 확인
        if not force_refresh and folder_path in cls._image_list_cache:
            cached_time = cls._cache_time.get(folder_path, 0)

            if current_time - cached_time < cls.CACHE_EXPIRY:
                return cls._image_list_cache[folder_path]

        # 폴더 스캔
        if not os.path.exists(folder_path):
            return []

        image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
        images = []

        for file in os.listdir(folder_path):
            if Path(file).suffix.lower() in image_extensions:
                images.append(os.path.join(folder_path, file))

        images.sort(key=lambda x: os.path.basename(x))

        # 캐시 저장
        cls._image_list_cache[folder_path] = images
        cls._cache_time[folder_path] = current_time

        return images

    @classmethod
    def invalidate_folder_cache(cls, folder_path: str):
        """특정 폴더의 캐시 무효화"""
        folder_path = str(Path(folder_path).resolve())
        cls._image_list_cache.pop(folder_path, None)
        cls._cache_time.pop(folder_path, None)

    @classmethod
    @st.cache_data(ttl=300, show_spinner=False, max_entries=200)
    def get_thumbnail(_cls, image_path: str, max_size: Tuple[int, int] = (200, 200)) -> Optional[bytes]:
        """
        썸네일 생성 및 캐싱
        """

        try:
            if not os.path.exists(image_path):
                return None

            with Image.open(image_path) as img:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                if img.mode == 'RGBA':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background

                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                return buffer.getvalue()

        except Exception as e:
            print(f"[ImageCache] 썸네일 생성 오류: {e}", flush=True)
            return None

    @classmethod
    def display_image(cls, image_path: str, use_thumbnail: bool = True,
                      max_width: int = 300, caption: str = None):
        """
        이미지 표시 (최적화)

        MediaFileStorageError 방지:
        - 파일 경로 직접 사용
        - 썸네일 캐싱
        """

        if not os.path.exists(image_path):
            st.warning(f"이미지 없음: {os.path.basename(image_path)}")
            return

        if use_thumbnail:
            thumbnail = cls.get_thumbnail(image_path)
            if thumbnail:
                st.image(thumbnail, caption=caption, width=max_width)
            else:
                # 파일 경로 직접 사용 (안정적!)
                st.image(image_path, caption=caption, width=max_width)
        else:
            st.image(image_path, caption=caption, width=max_width)


# 세션 기반 헬퍼 함수
def get_session_images(folder_path: str, force_refresh: bool = False) -> List[str]:
    """세션 상태에 이미지 목록 캐싱"""

    cache_key = f"image_list_{hashlib.md5(folder_path.encode()).hexdigest()}"

    if force_refresh or cache_key not in st.session_state:
        images = ImageCache.get_image_list(folder_path, force_refresh)
        st.session_state[cache_key] = images
        st.session_state[f"{cache_key}_time"] = datetime.now().timestamp()
        return images

    # 캐시 유효성 검사
    cached_time = st.session_state.get(f"{cache_key}_time", 0)
    if datetime.now().timestamp() - cached_time > 30:
        images = ImageCache.get_image_list(folder_path, force_refresh=True)
        st.session_state[cache_key] = images
        st.session_state[f"{cache_key}_time"] = datetime.now().timestamp()
        return images

    return st.session_state[cache_key]


def refresh_session_images(folder_path: str):
    """세션 이미지 캐시 갱신"""
    cache_key = f"image_list_{hashlib.md5(folder_path.encode()).hexdigest()}"
    st.session_state.pop(cache_key, None)
    ImageCache.invalidate_folder_cache(folder_path)


def display_image_safe(image_path: str, width: int = 300, caption: str = None):
    """
    안전한 이미지 표시 (MediaFileStorageError 방지)

    bytes 대신 파일 경로를 직접 사용합니다.
    """
    if not image_path:
        st.info("이미지 없음")
        return

    if not os.path.exists(image_path):
        st.warning(f"이미지 파일을 찾을 수 없습니다: {os.path.basename(image_path)}")
        return

    try:
        st.image(image_path, caption=caption, width=width)
    except Exception as e:
        st.error(f"이미지 표시 오류: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 레퍼런스 이미지 캐시 (v2.0) - 병렬 이미지 생성 최적화용
# ═══════════════════════════════════════════════════════════════════════════════

import threading
from typing import Dict


class ReferenceImageCache:
    """
    레퍼런스 이미지 캐시 매니저 (싱글톤)

    병렬 이미지 생성 시 같은 레퍼런스 이미지를 반복 로드하는 것을 방지
    - bytes 캐시: API 전송용
    - PIL 캐시: 이미지 처리용

    사용 예:
        cache = ReferenceImageCache()
        img_bytes = cache.get("/path/to/image.png")
        pil_img = cache.get_as_pil("/path/to/image.png")
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return

        self._bytes_cache: Dict[str, bytes] = {}
        self._pil_cache: Dict[str, Image.Image] = {}
        self._max_bytes_size = 50  # 최대 50개 bytes 캐시
        self._max_pil_size = 20  # PIL 캐시는 메모리 더 사용하므로 20개로 제한
        self._hits = 0
        self._misses = 0
        self._initialized = True
        print("[RefImageCache] ✅ 레퍼런스 이미지 캐시 초기화 완료")

    def _get_cache_key(self, path: str) -> str:
        """파일 경로 + 수정시간으로 캐시 키 생성"""
        p = Path(path)
        if p.exists():
            try:
                mtime = p.stat().st_mtime
                return f"{path}:{mtime}"
            except Exception:
                pass
        return path

    def get(self, path: str) -> Optional[bytes]:
        """
        캐시에서 이미지 bytes 가져오기

        Args:
            path: 이미지 파일 경로

        Returns:
            이미지 bytes 또는 None (파일 없음)
        """
        if not path:
            return None

        key = self._get_cache_key(path)

        # 캐시 히트
        if key in self._bytes_cache:
            self._hits += 1
            print(f"[RefImageCache] ⚡ 캐시 히트: {Path(path).name} (총 {self._hits}회)")
            return self._bytes_cache[key]

        # 캐시 미스 - 파일에서 로드
        self._misses += 1

        try:
            p = Path(path)
            if not p.exists():
                print(f"[RefImageCache] ⚠️ 파일 없음: {path}")
                return None

            with open(path, 'rb') as f:
                data = f.read()

            # 캐시 크기 관리 (FIFO 방식)
            if len(self._bytes_cache) >= self._max_bytes_size:
                oldest_key = next(iter(self._bytes_cache))
                del self._bytes_cache[oldest_key]

            self._bytes_cache[key] = data
            print(f"[RefImageCache] 📁 캐시 미스, 로드: {Path(path).name} ({len(data):,} bytes)")

            return data

        except Exception as e:
            print(f"[RefImageCache] ❌ 로드 실패: {path} - {e}")
            return None

    def get_as_pil(self, path: str, max_size: int = 1024) -> Optional[Image.Image]:
        """
        캐시에서 PIL Image로 반환 (리사이즈 포함)

        Args:
            path: 이미지 파일 경로
            max_size: 최대 크기 (가로/세로 중 큰 쪽)

        Returns:
            PIL Image 또는 None
        """
        if not path:
            return None

        key = f"{self._get_cache_key(path)}:pil:{max_size}"

        # PIL 캐시 히트
        if key in self._pil_cache:
            self._hits += 1
            return self._pil_cache[key].copy()  # 복사본 반환 (원본 보존)

        # bytes 캐시에서 가져오기
        data = self.get(path)
        if not data:
            return None

        try:
            pil_image = Image.open(io.BytesIO(data))

            # RGB로 변환 (RGBA인 경우)
            if pil_image.mode == 'RGBA':
                pil_image = pil_image.convert('RGB')

            # 리사이즈
            if pil_image.width > max_size or pil_image.height > max_size:
                pil_image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            # PIL 캐시 크기 관리
            if len(self._pil_cache) >= self._max_pil_size:
                oldest_key = next(iter(self._pil_cache))
                del self._pil_cache[oldest_key]

            self._pil_cache[key] = pil_image
            return pil_image.copy()  # 복사본 반환

        except Exception as e:
            print(f"[RefImageCache] ❌ PIL 변환 실패: {path} - {e}")
            return None

    def preload(self, paths: list) -> int:
        """
        여러 이미지 미리 로드

        Args:
            paths: 이미지 경로 목록

        Returns:
            성공적으로 로드된 이미지 수
        """
        loaded = 0
        unique_paths = set(p for p in paths if p)

        for path in unique_paths:
            if self.get(path):
                loaded += 1

        print(f"[RefImageCache] 📦 프리로드 완료: {loaded}/{len(unique_paths)}개")
        return loaded

    def clear(self):
        """캐시 비우기"""
        self._bytes_cache.clear()
        self._pil_cache.clear()
        self._hits = 0
        self._misses = 0
        print("[RefImageCache] 🗑️ 캐시 초기화됨")

    def stats(self) -> Dict:
        """캐시 통계"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        bytes_size = sum(len(v) for v in self._bytes_cache.values())

        return {
            "bytes_cache_size": len(self._bytes_cache),
            "pil_cache_size": len(self._pil_cache),
            "max_bytes_size": self._max_bytes_size,
            "max_pil_size": self._max_pil_size,
            "memory_mb": bytes_size / 1024 / 1024,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%"
        }


# 전역 레퍼런스 이미지 캐시 인스턴스 (싱글톤)
_reference_cache: Optional[ReferenceImageCache] = None


def get_reference_cache() -> ReferenceImageCache:
    """전역 레퍼런스 이미지 캐시 인스턴스 가져오기"""
    global _reference_cache
    if _reference_cache is None:
        _reference_cache = ReferenceImageCache()
    return _reference_cache


def load_reference_with_cache(path: str) -> Optional[bytes]:
    """캐시를 활용한 레퍼런스 이미지 로드 (bytes)"""
    cache = get_reference_cache()
    return cache.get(path)


def load_reference_as_pil(path: str, max_size: int = 1024) -> Optional[Image.Image]:
    """캐시를 활용한 레퍼런스 이미지 로드 (PIL Image)"""
    cache = get_reference_cache()
    return cache.get_as_pil(path, max_size)


def preload_references(paths: list) -> int:
    """여러 레퍼런스 이미지 미리 로드"""
    cache = get_reference_cache()
    return cache.preload(paths)


def get_reference_cache_stats() -> Dict:
    """레퍼런스 캐시 통계 조회"""
    cache = get_reference_cache()
    return cache.stats()


def clear_reference_cache():
    """레퍼런스 이미지 캐시 초기화"""
    cache = get_reference_cache()
    cache.clear()
