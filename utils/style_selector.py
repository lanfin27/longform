"""
스타일 선택 UI 컴포넌트

다른 페이지에서 재사용 가능한 스타일 선택기
"""
import streamlit as st
from pathlib import Path
from typing import Optional, List, Tuple
from core.prompt.preset_manager import PromptPresetManager, StylePreset


def render_style_selector(
    preset_manager: PromptPresetManager,
    category: str = "styles",
    key_prefix: str = "style",
    show_preview: bool = True,
    show_prompt: bool = True,
    allow_custom: bool = True,
    default_index: int = 0
) -> Tuple[Optional[StylePreset], str]:
    """
    스타일 선택 UI 렌더링

    Args:
        preset_manager: 프리셋 매니저 인스턴스
        category: 카테고리 (styles, characters, backgrounds, negatives)
        key_prefix: Streamlit key 접두사
        show_preview: 예시 이미지 표시 여부
        show_prompt: 프롬프트 표시 여부
        allow_custom: 커스텀 프롬프트 입력 허용
        default_index: 기본 선택 인덱스

    Returns:
        (선택된 프리셋, 최종 프롬프트)
    """
    presets = preset_manager.get_presets_by_category(category)

    if not presets:
        st.warning(f"'{category}' 카테고리에 프리셋이 없습니다.")
        return None, ""

    # 프리셋 옵션
    options = ["(선택 안함)"] + [p.name for p in presets]
    if allow_custom:
        options.append("✨ 커스텀 입력")

    # 기본 인덱스 조정
    if default_index > 0 and default_index < len(options):
        idx = default_index
    else:
        idx = 0

    selected_name = st.selectbox(
        f"{category.capitalize()} 스타일",
        options,
        index=idx,
        key=f"{key_prefix}_select"
    )

    selected_preset = None
    final_prompt = ""

    if selected_name == "(선택 안함)":
        pass

    elif selected_name == "✨ 커스텀 입력":
        final_prompt = st.text_area(
            "커스텀 프롬프트",
            key=f"{key_prefix}_custom",
            height=100,
            placeholder="직접 프롬프트를 입력하세요..."
        )

    else:
        # 프리셋 찾기
        for p in presets:
            if p.name == selected_name:
                selected_preset = p
                break

        if selected_preset:
            final_prompt = selected_preset.prompt

            # 상세 정보 표시
            with st.expander(f"📋 {selected_preset.name} 상세", expanded=False):
                # 설명
                if selected_preset.description:
                    st.info(selected_preset.description)

                # 태그
                if selected_preset.tags:
                    st.caption(f"🏷️ {', '.join(selected_preset.tags)}")

                # 프롬프트
                if show_prompt:
                    st.markdown("**프롬프트:**")
                    st.code(selected_preset.prompt, language=None)

                # 예시 이미지
                if show_preview and selected_preset.example_images:
                    st.markdown("**예시 이미지:**")
                    cols = st.columns(min(3, len(selected_preset.example_images)))
                    for i, img_path in enumerate(selected_preset.example_images[:3]):
                        with cols[i]:
                            if Path(img_path).exists():
                                st.image(img_path, use_container_width=True)

    return selected_preset, final_prompt


def render_style_card(
    preset: StylePreset,
    key_prefix: str = "card",
    show_select_button: bool = True
) -> bool:
    """
    스타일 카드 UI 렌더링

    Args:
        preset: 스타일 프리셋
        key_prefix: Streamlit key 접두사
        show_select_button: 선택 버튼 표시 여부

    Returns:
        선택 버튼 클릭 여부
    """
    selected = False

    with st.container(border=True):
        # 헤더
        col_title, col_badge = st.columns([3, 1])
        with col_title:
            st.markdown(f"### {preset.name}")
        with col_badge:
            if preset.is_default:
                st.caption("🔒 기본")
            else:
                st.caption("✨ 커스텀")

        # 카테고리 & 태그
        st.caption(f"📁 {preset.category}")
        if preset.tags:
            st.caption(f"🏷️ {', '.join(preset.tags[:3])}")

        # 설명
        desc = preset.description[:100] + "..." if len(preset.description) > 100 else preset.description
        st.write(desc or "설명 없음")

        # 프롬프트 미리보기
        with st.expander("프롬프트 보기"):
            st.code(preset.prompt, language=None)

        # 예시 이미지
        if preset.example_images:
            if Path(preset.example_images[0]).exists():
                st.image(preset.example_images[0], width=200)

        # 선택 버튼
        if show_select_button:
            if st.button("선택", key=f"{key_prefix}_select_{preset.id}"):
                selected = True

    return selected


def render_multi_style_selector(
    preset_manager: PromptPresetManager,
    key_prefix: str = "multi",
    show_preview: bool = True,
    include_composition: bool = False
) -> Tuple[str, str]:
    """
    여러 카테고리의 스타일을 조합하는 UI

    Args:
        preset_manager: 프리셋 매니저 인스턴스
        key_prefix: Streamlit key 접두사
        show_preview: 예시 이미지 표시 여부
        include_composition: 구도 프리셋 포함 여부

    Returns:
        (조합된 positive 프롬프트, negative 프롬프트)
    """
    prompts = []

    # 스타일
    st.markdown("#### 🎨 스타일")
    _, style_prompt = render_style_selector(
        preset_manager, "styles", f"{key_prefix}_style",
        show_preview=show_preview, show_prompt=True, default_index=1
    )
    if style_prompt:
        prompts.append(style_prompt)

    # 캐릭터
    st.markdown("#### 👤 캐릭터 스타일")
    _, char_prompt = render_style_selector(
        preset_manager, "characters", f"{key_prefix}_char",
        show_preview=show_preview, show_prompt=True
    )
    if char_prompt:
        prompts.append(char_prompt)

    # 배경
    st.markdown("#### 🏞️ 배경")
    _, bg_prompt = render_style_selector(
        preset_manager, "backgrounds", f"{key_prefix}_bg",
        show_preview=show_preview, show_prompt=True
    )
    if bg_prompt:
        prompts.append(bg_prompt)

    # 구도 (선택사항)
    if include_composition:
        st.markdown("#### 📐 구도")
        _, comp_prompt = render_style_selector(
            preset_manager, "compositions", f"{key_prefix}_comp",
            show_preview=False, show_prompt=True
        )
        if comp_prompt:
            prompts.append(comp_prompt)

    # 네거티브
    st.markdown("#### 🚫 네거티브 프롬프트")
    neg_presets = preset_manager.get_presets_by_category("negatives")
    neg_options = [p.name for p in neg_presets]

    selected_negs = st.multiselect(
        "적용할 네거티브",
        neg_options,
        default=["텍스트 금지"] if "텍스트 금지" in neg_options else [],
        key=f"{key_prefix}_neg"
    )

    neg_prompts = []
    for neg_name in selected_negs:
        for p in neg_presets:
            if p.name == neg_name:
                neg_prompts.append(p.prompt)

    # 최종 프롬프트 조합
    combined_positive = ", ".join(prompts)
    combined_negative = ", ".join(neg_prompts)

    # 결과 표시
    st.divider()
    st.markdown("#### 📋 조합된 프롬프트")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Positive:**")
        st.text_area(
            "positive_result",
            combined_positive or "(프리셋을 선택하세요)",
            height=100,
            disabled=True,
            key=f"{key_prefix}_pos_result",
            label_visibility="collapsed"
        )
    with col2:
        st.markdown("**Negative:**")
        st.text_area(
            "negative_result",
            combined_negative or "(없음)",
            height=100,
            disabled=True,
            key=f"{key_prefix}_neg_result",
            label_visibility="collapsed"
        )

    return combined_positive, combined_negative


def render_quick_style_selector(
    preset_manager: PromptPresetManager,
    key_prefix: str = "quick"
) -> str:
    """
    간단한 스타일 선택기 (스타일만)

    Returns:
        선택된 스타일 프롬프트
    """
    presets = preset_manager.get_presets_by_category("styles")

    if not presets:
        return ""

    # 카드 형태로 표시
    cols = st.columns(4)

    selected_prompt = ""

    for i, preset in enumerate(presets[:8]):  # 최대 8개만 표시
        with cols[i % 4]:
            with st.container(border=True):
                st.markdown(f"**{preset.name}**")

                # 예시 이미지
                if preset.example_images and Path(preset.example_images[0]).exists():
                    st.image(preset.example_images[0], use_container_width=True)
                else:
                    st.caption(preset.description[:50] + "...")

                if st.button("선택", key=f"{key_prefix}_quick_{preset.id}", use_container_width=True):
                    st.session_state[f"{key_prefix}_selected_style"] = preset.prompt
                    selected_prompt = preset.prompt

    # 세션에서 선택된 스타일 가져오기
    if f"{key_prefix}_selected_style" in st.session_state:
        selected_prompt = st.session_state[f"{key_prefix}_selected_style"]

    if selected_prompt:
        st.success(f"선택된 스타일 프롬프트: {selected_prompt[:50]}...")

    return selected_prompt
