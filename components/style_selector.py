"""
스타일 선택기 컴포넌트

재사용 가능한 스타일 선택 위젯
- 실시간 동기화: StyleManager의 변경사항 자동 감지
"""
import streamlit as st
from pathlib import Path
from typing import Optional, List

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.style_manager import Style, StyleManager, get_style_manager, invalidate_style_cache


def style_selector(
    segment: str,
    key: str,
    project_path: str = None,
    show_preview: bool = True,
    columns: int = 2,
    label: str = None
) -> Optional[Style]:
    """
    스타일 선택 위젯

    Args:
        segment: 스타일 세그먼트 ("character", "background", "scene_composite")
        key: Streamlit 위젯 키
        project_path: 프로젝트 경로
        show_preview: 미리보기 표시 여부
        columns: 열 수 (그리드 레이아웃)
        label: 선택기 레이블 (None이면 세그먼트 기본값)

    Returns:
        선택된 Style 객체 또는 None
    """
    manager = get_style_manager(project_path)
    styles = manager.get_styles_by_segment(segment)

    if not styles:
        st.warning(f"'{segment}' 세그먼트에 스타일이 없습니다.")
        return None

    # 세그먼트 정보
    segment_info = manager.get_segment_info(segment)
    if label is None:
        label = segment_info.get("name", "스타일") if segment_info else "스타일"

    st.subheader(f"🎨 {label} 선택")

    # 기본 선택된 스타일 (세션 상태에서 복원)
    session_key = f"selected_style_{segment}_{key}"
    default_idx = 0

    if session_key in st.session_state:
        saved_id = st.session_state[session_key]
        for i, s in enumerate(styles):
            if s.id == saved_id:
                default_idx = i
                break
    else:
        # 기본 스타일 찾기
        for i, s in enumerate(styles):
            if s.is_default:
                default_idx = i
                break

    # 스타일 옵션 목록
    style_names = [f"{s.name_ko} ({s.name})" for s in styles]

    # selectbox 방식
    selected_idx = st.selectbox(
        "스타일",
        range(len(styles)),
        index=default_idx,
        format_func=lambda i: style_names[i],
        key=f"{key}_selectbox"
    )

    selected_style = styles[selected_idx]

    # 세션 상태에 저장
    st.session_state[session_key] = selected_style.id

    # 선택된 스타일 정보 표시
    with st.expander("스타일 상세", expanded=False):
        st.markdown(f"**{selected_style.name_ko}** ({selected_style.name})")

        if selected_style.description:
            st.caption(selected_style.description)

        col1, col2 = st.columns(2)
        with col1:
            st.text_area(
                "프롬프트 Prefix",
                selected_style.prompt_prefix,
                disabled=True,
                height=60,
                key=f"{key}_prefix"
            )
        with col2:
            st.text_area(
                "프롬프트 Suffix",
                selected_style.prompt_suffix,
                disabled=True,
                height=60,
                key=f"{key}_suffix"
            )

        if selected_style.negative_prompt:
            st.text_area(
                "Negative Prompt",
                selected_style.negative_prompt,
                disabled=True,
                height=60,
                key=f"{key}_negative"
            )

    return selected_style


def style_card_selector(
    segment: str,
    key: str,
    project_path: str = None,
    columns: int = 4
) -> Optional[Style]:
    """
    카드 형태의 스타일 선택 위젯

    Args:
        segment: 스타일 세그먼트
        key: Streamlit 위젯 키
        project_path: 프로젝트 경로
        columns: 열 수

    Returns:
        선택된 Style 객체 또는 None
    """
    manager = get_style_manager(project_path)
    styles = manager.get_styles_by_segment(segment)

    if not styles:
        st.warning(f"'{segment}' 세그먼트에 스타일이 없습니다.")
        return None

    # 세그먼트 정보
    segment_info = manager.get_segment_info(segment)
    label = segment_info.get("name", "스타일") if segment_info else "스타일"

    st.subheader(f"🎨 {label} 선택")

    # 기본 선택된 스타일
    session_key = f"selected_style_{segment}_{key}"
    if session_key not in st.session_state:
        default_style = manager.get_default_style(segment)
        st.session_state[session_key] = default_style.id if default_style else styles[0].id

    selected_id = st.session_state[session_key]

    # 카드 그리드
    cols = st.columns(columns)

    for i, style in enumerate(styles):
        with cols[i % columns]:
            is_selected = (style.id == selected_id)

            # 카드 스타일
            border_color = "#4CAF50" if is_selected else "#ddd"
            bg_color = "#e8f5e9" if is_selected else "#fff"

            card_html = f"""
            <div style="
                border: 2px solid {border_color};
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 10px;
                background: {bg_color};
                text-align: center;
            ">
                <div style="font-size: 24px; margin-bottom: 8px;">🎨</div>
                <div style="font-weight: bold;">{style.name_ko}</div>
                <div style="font-size: 12px; color: #666;">{style.name}</div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

            if st.button(
                "✓ 선택됨" if is_selected else "선택",
                key=f"{key}_card_{style.id}",
                use_container_width=True,
                type="primary" if is_selected else "secondary"
            ):
                st.session_state[session_key] = style.id
                st.rerun()

    # 선택된 스타일 반환
    return manager.get_style_by_id(selected_id)


def style_radio_selector(
    segment: str,
    key: str,
    project_path: str = None,
    horizontal: bool = True
) -> Optional[Style]:
    """
    라디오 버튼 형태의 간단한 스타일 선택

    Args:
        segment: 스타일 세그먼트
        key: Streamlit 위젯 키
        project_path: 프로젝트 경로
        horizontal: 가로 배치 여부

    Returns:
        선택된 Style 객체 또는 None
    """
    manager = get_style_manager(project_path)
    styles = manager.get_styles_by_segment(segment)

    if not styles:
        return None

    # 세그먼트 정보
    segment_info = manager.get_segment_info(segment)
    label = segment_info.get("name", "스타일") if segment_info else "스타일"

    # 기본값 찾기
    session_key = f"selected_style_{segment}_{key}"
    default_idx = 0

    if session_key in st.session_state:
        saved_id = st.session_state[session_key]
        for i, s in enumerate(styles):
            if s.id == saved_id:
                default_idx = i
                break
    else:
        for i, s in enumerate(styles):
            if s.is_default:
                default_idx = i
                break

    # 라디오 선택
    style_options = [s.name_ko for s in styles]

    selected_idx = st.radio(
        f"🎨 {label}",
        range(len(styles)),
        index=default_idx,
        format_func=lambda i: style_options[i],
        key=f"{key}_radio",
        horizontal=horizontal
    )

    selected_style = styles[selected_idx]
    st.session_state[session_key] = selected_style.id

    return selected_style


def get_selected_style(segment: str, key: str, project_path: str = None) -> Optional[Style]:
    """
    세션 상태에서 선택된 스타일 가져오기

    Args:
        segment: 스타일 세그먼트
        key: 위젯 키
        project_path: 프로젝트 경로

    Returns:
        선택된 Style 또는 기본 스타일
    """
    manager = get_style_manager(project_path)
    session_key = f"selected_style_{segment}_{key}"

    if session_key in st.session_state:
        style_id = st.session_state[session_key]
        style = manager.get_style_by_id(style_id)
        if style:
            return style

    return manager.get_default_style(segment)
