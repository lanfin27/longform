# -*- coding: utf-8 -*-
"""
이미지 API 선택 컴포넌트 (v1.0)

기능:
- 탭별 API/모델 빠른 선택 UI
- SettingsManager와 동기화
- 생성 함수에서 사용할 설정 반환

사용법:
    from utils.image_api_selector import render_api_selector, get_current_api_settings

    # 탭 상단에 선택 UI 표시
    api_provider, model = render_api_selector(key_prefix="scene_gen")

    # 또는 저장된 설정 가져오기
    api_provider, model = get_current_api_settings()
"""

import streamlit as st
from typing import Tuple, Optional, List, Dict
from utils.settings_manager import get_setting, set_setting

# 페이지 식별자 (SettingsManager 키)
PAGE_ID = "image_generation"

# API 및 모델 정의
IMAGE_API_OPTIONS: Dict[str, dict] = {
    "Together.ai FLUX": {
        "models": [
            ("black-forest-labs/FLUX.2-dev", "FLUX.2 Dev (권장, ~20원)"),
            ("black-forest-labs/FLUX.2-flex", "FLUX.2 Flex (~40원)"),
            ("black-forest-labs/FLUX.2-pro", "FLUX.2 Pro (고품질, ~40원)"),
        ],
        "default_model": "black-forest-labs/FLUX.2-dev",
        "setting_key": "flux_model",
        "icon": "🚀",
        "cost": "유료 (~20원/장)"
    },
    "Google ImageFX": {
        "models": [
            ("IMAGEN_4", "Imagen 4 (최신, 무료)"),
            ("IMAGEN_3_5", "Imagen 3.5 (무료)"),
            ("IMAGEN_3_1", "Imagen 3.1 (무료)"),
            ("IMAGEN_3", "Imagen 3.0 (무료)"),
        ],
        "default_model": "IMAGEN_4",
        "setting_key": "imagefx_model",
        "icon": "🎨",
        "cost": "무료 (쿠키 필요)"
    },
    "OpenAI DALL-E": {
        "models": [
            ("dall-e-3", "DALL-E 3 (최신, ~60원)"),
            ("dall-e-2", "DALL-E 2 (~30원)"),
        ],
        "default_model": "dall-e-3",
        "setting_key": "dalle_model",
        "icon": "🖼️",
        "cost": "유료 (~60원/장)"
    },
    "Stability AI": {
        "models": [
            ("stable-diffusion-xl-1024-v1-0", "SDXL 1.0"),
            ("sd3-large", "SD3 Large"),
        ],
        "default_model": "stable-diffusion-xl-1024-v1-0",
        "setting_key": "stability_model",
        "icon": "🎭",
        "cost": "유료"
    },
    # v1.1: Gemini 이미지 생성 모델 추가 (레퍼런스 이미지 지원)
    "Gemini (Nano Banana)": {
        "models": [
            ("gemini_nano_banana", "Nano Banana (~15원, 레퍼런스 지원)"),
        ],
        "default_model": "gemini_nano_banana",
        "setting_key": "gemini_banana_model",
        "icon": "🍌",
        "cost": "유료 (~15원/장, 레퍼런스 지원)"
    },
    "Gemini (Nano Banana Pro)": {
        "models": [
            ("gemini_nano_banana_pro", "Nano Banana Pro (~25원, 레퍼런스 지원)"),
        ],
        "default_model": "gemini_nano_banana_pro",
        "setting_key": "gemini_banana_pro_model",
        "icon": "🍌",
        "cost": "유료 (~25원/장, 레퍼런스 지원)"
    },
}


def get_current_api_settings() -> Tuple[str, str]:
    """
    현재 저장된 API 설정 가져오기

    Returns:
        (api_provider, model) 튜플
    """
    # API 제공자 가져오기
    api_provider = get_setting(PAGE_ID, "api", "Together.ai FLUX")

    # 유효한 API인지 확인
    if api_provider not in IMAGE_API_OPTIONS:
        api_provider = "Together.ai FLUX"

    # 해당 API의 모델 설정 키
    api_config = IMAGE_API_OPTIONS[api_provider]
    model_setting_key = api_config["setting_key"]
    default_model = api_config["default_model"]

    # 모델 가져오기
    model = get_setting(PAGE_ID, model_setting_key, default_model)

    # 유효한 모델인지 확인
    valid_models = [m[0] for m in api_config["models"]]
    if model not in valid_models:
        model = default_model

    return api_provider, model


def save_api_settings(api_provider: str, model: str):
    """
    API 설정 저장하기

    Args:
        api_provider: API 제공자 이름
        model: 모델 ID
    """
    if api_provider not in IMAGE_API_OPTIONS:
        return

    # API 저장
    set_setting(PAGE_ID, "api", api_provider)

    # 모델 저장 (해당 API의 설정 키로)
    api_config = IMAGE_API_OPTIONS[api_provider]
    model_setting_key = api_config["setting_key"]
    set_setting(PAGE_ID, model_setting_key, model)


def render_api_selector(
    key_prefix: str = "img",
    show_in_expander: bool = True,
    expander_default_open: bool = False,
    show_save_button: bool = True,
    compact: bool = False,
) -> Tuple[str, str]:
    """
    API/모델 선택 UI 렌더링

    Args:
        key_prefix: 위젯 키 prefix (탭별로 고유하게)
        show_in_expander: expander 안에 표시할지
        expander_default_open: expander 기본 펼침 상태
        show_save_button: "기본값으로 저장" 버튼 표시
        compact: 컴팩트 모드 (1행 레이아웃)

    Returns:
        (api_provider, model) 튜플
    """
    # 세션 상태 초기화 (위젯 값 유지용)
    session_api_key = f"_{key_prefix}_api"
    session_model_key = f"_{key_prefix}_model"

    # 세션에 없으면 설정에서 로드
    if session_api_key not in st.session_state:
        saved_api, saved_model = get_current_api_settings()
        st.session_state[session_api_key] = saved_api
        st.session_state[session_model_key] = saved_model

    # 컨테이너 결정
    if show_in_expander:
        container = st.expander("🎨 이미지 생성 API 선택", expanded=expander_default_open)
    else:
        container = st.container()

    with container:
        if compact:
            # 컴팩트 모드: 1행
            cols = st.columns([2, 2, 1, 1] if show_save_button else [2, 2, 1])
        else:
            # 기본 모드
            cols = st.columns([2, 2, 1] if show_save_button else [2, 2])

        with cols[0]:
            # API 선택
            api_options = list(IMAGE_API_OPTIONS.keys())
            current_api = st.session_state.get(session_api_key, "Together.ai FLUX")

            try:
                api_idx = api_options.index(current_api)
            except ValueError:
                api_idx = 0

            def api_format(x):
                cfg = IMAGE_API_OPTIONS.get(x, {})
                icon = cfg.get("icon", "")
                return f"{icon} {x}"

            selected_api = st.selectbox(
                "API",
                api_options,
                index=api_idx,
                format_func=api_format,
                key=f"{key_prefix}_api_select",
                label_visibility="collapsed" if compact else "visible"
            )

            # API 변경 감지
            if selected_api != st.session_state.get(session_api_key):
                st.session_state[session_api_key] = selected_api
                # 모델 초기화 (API 변경 시)
                api_config = IMAGE_API_OPTIONS[selected_api]
                st.session_state[session_model_key] = api_config["default_model"]

        with cols[1]:
            # 모델 선택
            api_config = IMAGE_API_OPTIONS[selected_api]
            models = api_config["models"]
            model_ids = [m[0] for m in models]
            model_names = [m[1] for m in models]

            current_model = st.session_state.get(session_model_key)

            try:
                if current_model in model_ids:
                    model_idx = model_ids.index(current_model)
                else:
                    model_idx = 0
            except ValueError:
                model_idx = 0

            selected_model_name = st.selectbox(
                "모델",
                model_names,
                index=model_idx,
                key=f"{key_prefix}_model_select",
                label_visibility="collapsed" if compact else "visible"
            )

            selected_model = model_ids[model_names.index(selected_model_name)]

            # 모델 변경 감지
            if selected_model != st.session_state.get(session_model_key):
                st.session_state[session_model_key] = selected_model

        if show_save_button:
            with cols[2]:
                st.write("")  # 정렬용
                if st.button("💾 기본값 저장", key=f"{key_prefix}_save_default", use_container_width=True):
                    save_api_settings(selected_api, selected_model)
                    st.toast("기본값으로 저장되었습니다!", icon="✅")

        # 비용 정보 표시
        if not compact:
            cost_info = api_config.get("cost", "")
            if cost_info:
                st.caption(f"💰 {cost_info}")

    return selected_api, selected_model


def render_api_info_banner(api_provider: str, model: str):
    """
    현재 선택된 API 정보를 배너로 표시

    Args:
        api_provider: API 제공자
        model: 모델 ID
    """
    if api_provider not in IMAGE_API_OPTIONS:
        return

    api_config = IMAGE_API_OPTIONS[api_provider]
    icon = api_config.get("icon", "🎨")
    cost = api_config.get("cost", "")

    # 모델 표시 이름 찾기
    model_display = model
    for m_id, m_name in api_config["models"]:
        if m_id == model:
            model_display = m_name
            break

    st.info(f"{icon} **API:** {api_provider} | **모델:** {model_display} | {cost}")


def get_model_display_name(api_provider: str, model: str) -> str:
    """
    모델 표시 이름 가져오기

    Args:
        api_provider: API 제공자
        model: 모델 ID

    Returns:
        표시용 모델 이름
    """
    if api_provider not in IMAGE_API_OPTIONS:
        return model

    api_config = IMAGE_API_OPTIONS[api_provider]
    for m_id, m_name in api_config["models"]:
        if m_id == model:
            return m_name

    return model
