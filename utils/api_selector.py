"""
API 선택 UI 컴포넌트

각 페이지에서 인라인으로 API를 선택할 수 있는 UI 컴포넌트들.

기능:
1. render_api_selector_inline: 인라인 API 선택 (가로)
2. render_api_selector_expander: 접이식 API 선택
3. render_api_selector_sidebar: 사이드바용 API 선택
4. render_api_status: API 상태 표시 (키 유효성, 남은 크레딧 등)
"""
import streamlit as st
from typing import Optional, Dict, List, Tuple
from core.api.api_manager import get_api_manager, APIConfig


def get_api_options_for_task(task: str) -> List[Tuple[str, APIConfig]]:
    """
    특정 작업에 사용 가능한 API 목록 반환

    Args:
        task: 작업 유형 (script_generation, image_generation, tts 등)

    Returns:
        List of (api_id, APIConfig) tuples
    """
    api_manager = get_api_manager()
    available = []

    function_map = {
        "script_generation": "text_generation",
        "scene_analysis": "text_generation",
        "prompt_generation": "text_generation",
        "image_generation": "image_generation",
        "tts": "tts",
        "stt": "stt"
    }

    target_function = function_map.get(task, task)

    for api_id, config in api_manager.AVAILABLE_APIS.items():
        if config.function == target_function:
            available.append((api_id, config))

    return available


def render_api_selector_inline(
    task: str,
    label: str = "AI 모델",
    key_prefix: str = "",
    show_details: bool = True,
    columns: int = 2
) -> str:
    """
    인라인 API 선택 UI (가로 레이아웃)

    Args:
        task: 작업 유형
        label: 라벨 텍스트
        key_prefix: 세션 키 프리픽스
        show_details: 상세 정보 표시 여부
        columns: 컬럼 수

    Returns:
        선택된 API ID
    """
    api_manager = get_api_manager()
    options = get_api_options_for_task(task)

    if not options:
        st.warning(f"'{task}' 작업에 사용 가능한 API가 없습니다.")
        return ""

    # 현재 선택된 API (selected_apis에서 가져옴)
    current_api = api_manager.settings.get("selected_apis", {}).get(task)
    current_idx = 0
    for i, (api_id, _) in enumerate(options):
        if api_id == current_api:
            current_idx = i
            break

    # 선택 UI
    cols = st.columns(columns)

    with cols[0]:
        selected_idx = st.selectbox(
            label,
            range(len(options)),
            index=current_idx,
            format_func=lambda i: f"{options[i][1].name} ({options[i][1].provider})",
            key=f"{key_prefix}_api_select"
        )

    selected_api_id, selected_config = options[selected_idx]

    if show_details and columns > 1:
        with cols[1]:
            # 가격 정보
            if selected_config.price_per_unit > 0:
                st.caption(f"💰 ${selected_config.price_per_unit:.4f}/{selected_config.unit_name}")
            else:
                st.caption("✅ 무료")

            # 설명
            if selected_config.description:
                st.caption(f"📝 {selected_config.description}")

    # 선택 저장
    api_manager.set_selected_api(task, selected_api_id)

    return selected_api_id


def render_api_selector_expander(
    task: str,
    label: str = "AI 설정",
    key_prefix: str = "",
    expanded: bool = False
) -> str:
    """
    접이식 API 선택 UI

    Args:
        task: 작업 유형
        label: 라벨 텍스트
        key_prefix: 세션 키 프리픽스
        expanded: 기본 펼침 상태

    Returns:
        선택된 API ID
    """
    api_manager = get_api_manager()
    options = get_api_options_for_task(task)

    if not options:
        st.warning(f"'{task}' 작업에 사용 가능한 API가 없습니다.")
        return ""

    current_api = api_manager.settings.get("selected_apis", {}).get(task)
    current_idx = 0
    for i, (api_id, _) in enumerate(options):
        if api_id == current_api:
            current_idx = i
            break

    with st.expander(f"⚙️ {label}", expanded=expanded):
        # API 선택
        selected_idx = st.selectbox(
            "모델 선택",
            range(len(options)),
            index=current_idx,
            format_func=lambda i: options[i][1].name,
            key=f"{key_prefix}_api_exp_select"
        )

        selected_api_id, selected_config = options[selected_idx]

        # 상세 정보
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**제공자:** {selected_config.provider}")
        with col2:
            if selected_config.price_per_unit > 0:
                st.markdown(f"**비용:** ${selected_config.price_per_unit:.4f}/{selected_config.unit_name}")
            else:
                st.markdown("**비용:** 무료")

        # 모델 설명
        if selected_config.description:
            st.caption(selected_config.description)

        # API 키 상태
        key_status = api_manager.validate_api_key(selected_config.provider)
        if key_status:
            st.success("✅ API 키 설정됨")
        else:
            st.warning(f"⚠️ {selected_config.provider.upper()}_API_KEY 설정 필요")

    api_manager.set_selected_api(task, selected_api_id)
    return selected_api_id


def render_api_selector_sidebar(
    task: str,
    label: str = "AI 모델",
    key_prefix: str = ""
) -> str:
    """
    사이드바용 API 선택 UI

    Args:
        task: 작업 유형
        label: 라벨 텍스트
        key_prefix: 세션 키 프리픽스

    Returns:
        선택된 API ID
    """
    api_manager = get_api_manager()
    options = get_api_options_for_task(task)

    if not options:
        st.sidebar.warning(f"'{task}'에 사용 가능한 API 없음")
        return ""

    current_api = api_manager.settings.get("selected_apis", {}).get(task)
    current_idx = 0
    for i, (api_id, _) in enumerate(options):
        if api_id == current_api:
            current_idx = i
            break

    selected_idx = st.sidebar.selectbox(
        label,
        range(len(options)),
        index=current_idx,
        format_func=lambda i: options[i][1].name,
        key=f"{key_prefix}_api_sidebar"
    )

    selected_api_id, selected_config = options[selected_idx]

    # 간단한 상태 표시
    if selected_config.price_per_unit > 0:
        st.sidebar.caption(f"💰 ${selected_config.price_per_unit:.4f}/{selected_config.unit_name}")
    else:
        st.sidebar.caption("✅ 무료")

    api_manager.set_selected_api(task, selected_api_id)
    return selected_api_id


def render_api_status(task: str = None, show_all: bool = False):
    """
    API 상태 표시

    Args:
        task: 특정 작업의 API 상태만 표시 (None이면 전체)
        show_all: 모든 API 상태 표시
    """
    api_manager = get_api_manager()

    if show_all:
        providers = ["anthropic", "google", "together", "openai", "elevenlabs"]
    elif task:
        options = get_api_options_for_task(task)
        providers = list(set(config.provider for _, config in options))
    else:
        providers = ["anthropic", "together"]  # 기본

    st.markdown("### 🔑 API 상태")

    cols = st.columns(len(providers))
    for i, provider in enumerate(providers):
        with cols[i]:
            has_key = api_manager.validate_api_key(provider)
            if has_key:
                st.success(f"✅ {provider.upper()}")
            else:
                st.error(f"❌ {provider.upper()}")


def render_quick_api_switch(
    task: str,
    key_prefix: str = ""
) -> str:
    """
    빠른 API 전환 (라디오 버튼 스타일)

    Args:
        task: 작업 유형
        key_prefix: 세션 키 프리픽스

    Returns:
        선택된 API ID
    """
    api_manager = get_api_manager()
    options = get_api_options_for_task(task)

    if not options:
        return ""

    current_api = api_manager.settings.get("selected_apis", {}).get(task)
    current_idx = 0
    for i, (api_id, _) in enumerate(options):
        if api_id == current_api:
            current_idx = i
            break

    # 라디오 버튼 형태
    option_labels = [f"{config.name}" for _, config in options]

    selected_idx = st.radio(
        "AI 선택",
        range(len(options)),
        index=current_idx,
        format_func=lambda i: option_labels[i],
        horizontal=True,
        key=f"{key_prefix}_api_radio"
    )

    selected_api_id, _ = options[selected_idx]
    api_manager.set_selected_api(task, selected_api_id)

    return selected_api_id


def render_api_cost_estimate(
    task: str,
    units: int = 1,
    key_prefix: str = ""
) -> float:
    """
    예상 비용 표시

    Args:
        task: 작업 유형
        units: 예상 사용량
        key_prefix: 세션 키 프리픽스

    Returns:
        예상 비용
    """
    api_manager = get_api_manager()
    current_api = api_manager.settings.get("selected_apis", {}).get(task)
    config = api_manager.AVAILABLE_APIS.get(current_api)

    if not config:
        return 0.0

    estimated_cost = config.price_per_unit * units

    if estimated_cost > 0:
        st.caption(f"💰 예상 비용: ${estimated_cost:.4f} ({units} {config.unit_name})")
    else:
        st.caption(f"✅ 무료 (예상 {units} {config.unit_name})")

    return estimated_cost
