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
