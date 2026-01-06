# -*- coding: utf-8 -*-
"""
메모리 관리자 (v1.0)

기능:
- 세션 상태 정리
- 이미지 데이터 메모리 해제
- 페이지네이션 지원
- 가비지 컬렉션 최적화
"""

import gc
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
import time

# Streamlit 세션 스테이트
try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False
    st = None


# ============================================================
# 세션 상태 정리
# ============================================================

# 이미지 관련 세션 키 패턴
IMAGE_SESSION_PATTERNS = [
    "composite_result_",
    "bg_result_",
    "char_image_",
    "generated_image_",
    "batch_image_",
    "_image_bytes_",
    "_preview_image_",
]

# 청소 대상에서 제외할 중요 키
PROTECTED_KEYS = {
    "project_path",
    "scenes",
    "characters",
    "styles",
    "settings",
    "imagefx_cookie",
    "imagefx_auth_token",
    "api_keys",
}


def cleanup_session_images(
    max_age_minutes: int = 30,
    force: bool = False,
    exclude_scene_ids: List[int] = None
) -> int:
    """
    세션의 이미지 데이터 정리

    Args:
        max_age_minutes: 이 시간보다 오래된 이미지 데이터 삭제 (force=False일 때)
        force: True면 모든 이미지 데이터 삭제
        exclude_scene_ids: 제외할 씬 ID 목록

    Returns:
        정리된 항목 수
    """
    if not _HAS_STREAMLIT:
        return 0

    if exclude_scene_ids is None:
        exclude_scene_ids = []

    cleaned_count = 0
    keys_to_remove = []

    for key in list(st.session_state.keys()):
        # 보호된 키는 건너뛰기
        if key in PROTECTED_KEYS:
            continue

        # 이미지 관련 키인지 확인
        is_image_key = any(pattern in key for pattern in IMAGE_SESSION_PATTERNS)
        if not is_image_key:
            continue

        # 제외할 씬 확인
        should_exclude = False
        for scene_id in exclude_scene_ids:
            if f"_{scene_id}" in key or f"_{scene_id:03d}" in key:
                should_exclude = True
                break

        if should_exclude:
            continue

        # 강제 삭제 또는 조건부 삭제
        if force:
            keys_to_remove.append(key)
        else:
            # 타임스탬프 기반 삭제 (캐시된 경우)
            value = st.session_state.get(key)
            if isinstance(value, dict) and "_timestamp" in value:
                age = time.time() - value["_timestamp"]
                if age > max_age_minutes * 60:
                    keys_to_remove.append(key)

    # 키 삭제
    for key in keys_to_remove:
        try:
            del st.session_state[key]
            cleaned_count += 1
        except Exception:
            pass

    # 가비지 컬렉션
    if cleaned_count > 0:
        gc.collect()
        print(f"[MemoryManager] 세션 정리 완료: {cleaned_count}개 항목 삭제")

    return cleaned_count


def cleanup_batch_results(batch_prefix: str = "batch_") -> int:
    """
    일괄 처리 결과 정리

    Args:
        batch_prefix: 배치 결과 키 접두사

    Returns:
        정리된 항목 수
    """
    if not _HAS_STREAMLIT:
        return 0

    cleaned_count = 0
    keys_to_remove = []

    for key in list(st.session_state.keys()):
        if key.startswith(batch_prefix):
            keys_to_remove.append(key)

    for key in keys_to_remove:
        try:
            del st.session_state[key]
            cleaned_count += 1
        except Exception:
            pass

    if cleaned_count > 0:
        gc.collect()
        print(f"[MemoryManager] 배치 결과 정리: {cleaned_count}개 항목 삭제")

    return cleaned_count


def get_session_memory_stats() -> Dict[str, Any]:
    """
    세션 메모리 사용 통계

    Returns:
        {
            "total_keys": 총 키 수,
            "image_keys": 이미지 관련 키 수,
            "estimated_size_mb": 추정 메모리 크기 (MB)
        }
    """
    if not _HAS_STREAMLIT:
        return {"total_keys": 0, "image_keys": 0, "estimated_size_mb": 0}

    total_keys = len(st.session_state)
    image_keys = 0
    estimated_size = 0

    for key in st.session_state.keys():
        is_image_key = any(pattern in key for pattern in IMAGE_SESSION_PATTERNS)
        if is_image_key:
            image_keys += 1

        # 대략적인 크기 추정
        value = st.session_state.get(key)
        if isinstance(value, bytes):
            estimated_size += len(value)
        elif isinstance(value, str):
            estimated_size += len(value.encode('utf-8', errors='ignore'))
        elif isinstance(value, (list, dict)):
            # 간단한 추정
            estimated_size += len(str(value))

    return {
        "total_keys": total_keys,
        "image_keys": image_keys,
        "estimated_size_mb": estimated_size / (1024 * 1024)
    }


# ============================================================
# 이미지 표시 유틸리티
# ============================================================

def get_paginated_images(
    images: List[Dict],
    page: int,
    per_page: int = 20
) -> tuple:
    """
    이미지 목록 페이지네이션

    Args:
        images: 전체 이미지 목록
        page: 현재 페이지 (1부터 시작)
        per_page: 페이지당 이미지 수

    Returns:
        (paginated_images, total_pages)
    """
    total = len(images)
    total_pages = max(1, (total + per_page - 1) // per_page)

    # 페이지 범위 검증
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = start + per_page

    return images[start:end], total_pages


def load_image_thumbnail(
    image_path: str,
    max_size: tuple = (200, 200),
    cache_key: str = None
) -> Optional[bytes]:
    """
    이미지 썸네일 로드 (메모리 효율적)

    Args:
        image_path: 이미지 파일 경로
        max_size: 최대 크기 (width, height)
        cache_key: 캐시 키 (옵션)

    Returns:
        썸네일 이미지 바이트 또는 None
    """
    if not os.path.exists(image_path):
        return None

    try:
        from PIL import Image
        import io

        # 캐시 확인
        if cache_key and _HAS_STREAMLIT:
            cached = st.session_state.get(f"_thumb_{cache_key}")
            if cached:
                return cached

        # 이미지 로드 및 리사이즈
        with Image.open(image_path) as img:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # 바이트로 변환
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            thumb_bytes = buffer.getvalue()

        # 캐시 저장
        if cache_key and _HAS_STREAMLIT:
            st.session_state[f"_thumb_{cache_key}"] = thumb_bytes

        return thumb_bytes

    except Exception as e:
        print(f"[MemoryManager] 썸네일 로드 실패: {e}")
        return None


def display_image_efficiently(
    image_path: str,
    use_container_width: bool = True,
    max_display_size: tuple = None,
    key: str = None
):
    """
    메모리 효율적 이미지 표시

    파일 경로를 직접 사용하여 메모리 사용 최소화

    Args:
        image_path: 이미지 파일 경로
        use_container_width: 컨테이너 너비에 맞춤
        max_display_size: 최대 표시 크기 (리사이즈)
        key: 위젯 키
    """
    if not _HAS_STREAMLIT:
        return

    if not os.path.exists(image_path):
        st.warning(f"이미지 파일 없음: {image_path}")
        return

    try:
        # 파일 크기 확인
        file_size = os.path.getsize(image_path)
        file_size_mb = file_size / (1024 * 1024)

        # 5MB 이상이면 썸네일 사용
        if file_size_mb > 5 and max_display_size:
            thumb_bytes = load_image_thumbnail(image_path, max_display_size, key)
            if thumb_bytes:
                st.image(thumb_bytes, use_container_width=use_container_width)
                st.caption(f"📏 원본: {file_size_mb:.1f}MB (썸네일 표시)")
                return

        # 일반 표시
        st.image(image_path, use_container_width=use_container_width)

    except Exception as e:
        st.error(f"이미지 표시 오류: {e}")


# ============================================================
# 가비지 컬렉션 유틸리티
# ============================================================

def force_gc():
    """강제 가비지 컬렉션"""
    collected = gc.collect()
    print(f"[MemoryManager] GC 실행: {collected}개 객체 수집됨")
    return collected


def optimize_memory_for_batch():
    """
    일괄 처리 전 메모리 최적화

    - 불필요한 세션 데이터 정리
    - 가비지 컬렉션 실행
    """
    # 오래된 이미지 데이터 정리
    cleanup_session_images(max_age_minutes=10, force=False)

    # GC 실행
    force_gc()

    print("[MemoryManager] 배치 처리 전 메모리 최적화 완료")


def cleanup_after_batch():
    """
    일괄 처리 후 정리

    - 배치 결과 정리 (선택적)
    - GC 실행
    """
    force_gc()
    print("[MemoryManager] 배치 처리 후 정리 완료")


# ============================================================
# Streamlit UI 헬퍼
# ============================================================

def render_memory_status():
    """
    메모리 상태 표시 UI
    """
    if not _HAS_STREAMLIT:
        return

    stats = get_session_memory_stats()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("세션 키", f"{stats['total_keys']}개")

    with col2:
        st.metric("이미지 데이터", f"{stats['image_keys']}개")

    with col3:
        st.metric("추정 메모리", f"{stats['estimated_size_mb']:.1f}MB")


def render_cleanup_button():
    """
    정리 버튼 UI
    """
    if not _HAS_STREAMLIT:
        return

    if st.button("🧹 메모리 정리", key="memory_cleanup_btn"):
        cleaned = cleanup_session_images(force=True)
        force_gc()
        st.success(f"✅ {cleaned}개 항목 정리됨")
        st.rerun()


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    print("=== 메모리 관리자 테스트 ===")

    # 가비지 컬렉션 테스트
    collected = force_gc()
    print(f"GC 결과: {collected}개 수집")

    print("\n✅ 테스트 완료")
