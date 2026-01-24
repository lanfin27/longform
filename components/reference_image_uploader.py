# -*- coding: utf-8 -*-
"""
components/reference_image_uploader.py
레퍼런스 이미지 업로드 UI 컴포넌트

Gemini 이미지 생성 모델 전용 기능:
- 스타일 참조
- 캐릭터 참조
- 구도 참조

작성: 2025-01
"""

import streamlit as st
from PIL import Image
import io
from pathlib import Path
from typing import List, Optional, Dict


def render_reference_image_uploader(
    key_prefix: str = "ref",
    max_images: int = 5,
    show_only_for_gemini: bool = True,
    current_api: str = ""
) -> Dict:
    """
    레퍼런스 이미지 업로드 UI

    Args:
        key_prefix: 세션 상태 키 접두사
        max_images: 최대 이미지 개수
        show_only_for_gemini: Gemini 모델 선택 시에만 표시
        current_api: 현재 선택된 API 이름

    Returns:
        {
            "enabled": bool,
            "images": List[bytes],
            "reference_type": str,
            "reference_strength": float
        }
    """

    result = {
        "enabled": False,
        "images": [],
        "reference_type": "style",
        "reference_strength": 0.8
    }

    # 현재 선택된 API 확인
    if not current_api:
        current_api = st.session_state.get('selected_image_api', '')

    is_gemini = 'gemini' in current_api.lower()

    # Gemini가 아니면 숨김
    if show_only_for_gemini and not is_gemini:
        return result

    # 섹션 헤더
    st.markdown("---")
    st.markdown("### 📷 레퍼런스 이미지 (Gemini 전용)")

    # 안내 메시지
    st.info("""
        **Gemini 모델 전용 기능**

        레퍼런스 이미지를 업로드하면 스타일, 캐릭터, 구도를 참조하여
        일관된 이미지를 생성할 수 있습니다.
    """)

    # 레퍼런스 사용 여부
    use_reference = st.checkbox(
        "레퍼런스 이미지 사용",
        value=st.session_state.get(f"{key_prefix}_use_reference", False),
        key=f"{key_prefix}_use_reference"
    )

    if not use_reference:
        return result

    result["enabled"] = True

    # 레퍼런스 타입 선택
    col1, col2 = st.columns([2, 1])

    with col1:
        reference_type = st.radio(
            "레퍼런스 타입",
            options=["style", "character", "composition"],
            format_func=lambda x: {
                "style": "🎨 스타일 참조 (색감, 화풍, 분위기)",
                "character": "👤 캐릭터 참조 (외모, 의상, 특징)",
                "composition": "📐 구도 참조 (배치, 앵글, 프레이밍)"
            }[x],
            horizontal=True,
            key=f"{key_prefix}_reference_type"
        )
        result["reference_type"] = reference_type

    with col2:
        reference_strength = st.slider(
            "레퍼런스 강도",
            min_value=0.1,
            max_value=1.0,
            value=0.8,
            step=0.1,
            key=f"{key_prefix}_reference_strength",
            help="높을수록 레퍼런스 이미지에 더 가깝게 생성됩니다."
        )
        result["reference_strength"] = reference_strength

    st.markdown("---")

    # 이미지 업로드
    uploaded_files = st.file_uploader(
        f"레퍼런스 이미지 업로드 (최대 {max_images}개)",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"{key_prefix}_file_uploader"
    )

    if uploaded_files:
        # 최대 개수 제한
        files_to_process = uploaded_files[:max_images]

        if len(uploaded_files) > max_images:
            st.warning(f"최대 {max_images}개까지만 사용됩니다. ({len(uploaded_files)}개 업로드됨)")

        # 이미지 미리보기
        cols = st.columns(min(len(files_to_process), 5))

        for idx, file in enumerate(files_to_process):
            with cols[idx % 5]:
                # 이미지 로드
                image_bytes = file.read()
                file.seek(0)  # 파일 포인터 리셋

                try:
                    image = Image.open(io.BytesIO(image_bytes))

                    # 미리보기 (리사이즈)
                    preview = image.copy()
                    preview.thumbnail((150, 150))

                    st.image(preview, caption=f"참조 {idx + 1}", use_container_width=True)

                    # bytes 저장
                    result["images"].append(image_bytes)
                except Exception as e:
                    st.error(f"이미지 로드 실패: {e}")

        st.success(f"✅ {len(result['images'])}개 레퍼런스 이미지 준비됨")

    # 기존 저장된 레퍼런스 불러오기
    with st.expander("📂 저장된 레퍼런스 불러오기", expanded=False):
        saved_refs = get_saved_reference_images()

        if saved_refs:
            selected_saved = st.multiselect(
                "저장된 레퍼런스 선택",
                options=list(saved_refs.keys()),
                key=f"{key_prefix}_saved_refs"
            )

            if selected_saved:
                for ref_name in selected_saved:
                    ref_path = saved_refs[ref_name]
                    if Path(ref_path).exists():
                        with open(ref_path, 'rb') as f:
                            result["images"].append(f.read())

                st.info(f"저장된 레퍼런스 {len(selected_saved)}개 추가됨")
        else:
            st.caption("저장된 레퍼런스 이미지가 없습니다.")

    return result


def get_saved_reference_images() -> Dict[str, str]:
    """저장된 레퍼런스 이미지 목록 반환"""

    ref_dir = Path("data/reference_images")

    if not ref_dir.exists():
        return {}

    refs = {}

    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
        for img_path in ref_dir.glob(ext):
            refs[img_path.stem] = str(img_path)

    return refs


def save_reference_image(name: str, image_bytes: bytes) -> str:
    """레퍼런스 이미지 저장"""

    ref_dir = Path("data/reference_images")
    ref_dir.mkdir(parents=True, exist_ok=True)

    save_path = ref_dir / f"{name}.png"

    with open(save_path, 'wb') as f:
        f.write(image_bytes)

    return str(save_path)


def render_reference_image_compact(
    key_prefix: str = "ref_compact",
    current_api: str = ""
) -> Dict:
    """
    레퍼런스 이미지 컴팩트 UI (expander 내부용)

    Returns:
        {
            "enabled": bool,
            "images": List[bytes],
            "reference_type": str,
            "reference_strength": float
        }
    """

    result = {
        "enabled": False,
        "images": [],
        "reference_type": "style",
        "reference_strength": 0.8
    }

    # 현재 선택된 API 확인
    if not current_api:
        current_api = st.session_state.get('selected_image_api', '')

    is_gemini = 'gemini' in current_api.lower()

    if not is_gemini:
        return result

    # 레퍼런스 사용 여부
    use_reference = st.checkbox(
        "📷 레퍼런스 이미지 사용 (Gemini 전용)",
        value=False,
        key=f"{key_prefix}_use_ref",
        help="스타일, 캐릭터, 구도를 참조하여 일관된 이미지 생성"
    )

    if not use_reference:
        return result

    result["enabled"] = True

    col1, col2, col3 = st.columns([2, 1, 2])

    with col1:
        reference_type = st.selectbox(
            "참조 타입",
            options=["style", "character", "composition"],
            format_func=lambda x: {
                "style": "🎨 스타일",
                "character": "👤 캐릭터",
                "composition": "📐 구도"
            }[x],
            key=f"{key_prefix}_type"
        )
        result["reference_type"] = reference_type

    with col2:
        reference_strength = st.slider(
            "강도",
            min_value=0.1,
            max_value=1.0,
            value=0.8,
            step=0.1,
            key=f"{key_prefix}_strength"
        )
        result["reference_strength"] = reference_strength

    with col3:
        uploaded_files = st.file_uploader(
            "이미지",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key=f"{key_prefix}_upload",
            label_visibility="collapsed"
        )

        if uploaded_files:
            for file in uploaded_files[:3]:
                image_bytes = file.read()
                file.seek(0)
                result["images"].append(image_bytes)

            st.caption(f"{len(result['images'])}개 선택됨")

    return result


# 내보내기
__all__ = [
    'render_reference_image_uploader',
    'render_reference_image_compact',
    'get_saved_reference_images',
    'save_reference_image'
]
