"""
프로그레스 및 로그 UI 컴포넌트

Streamlit에서 사용할 프로그레스 바, 로그 표시 컴포넌트
"""
import streamlit as st
from typing import List, Optional, Callable
import time
from datetime import datetime

from core.api.progress_tracker import ProgressTracker, LogEntry, LogLevel


class StreamlitProgressUI:
    """Streamlit 프로그레스 UI"""

    def __init__(self, task_name: str, total_steps: int, show_logs: bool = True):
        self.task_name = task_name
        self.total_steps = total_steps
        self.show_logs = show_logs

        # UI 요소 생성
        self.header = st.empty()
        self.progress_bar = st.progress(0)
        self.status_text = st.empty()
        self.time_text = st.empty()

        if show_logs:
            self.log_expander = st.expander("📋 로그", expanded=False)
            self.log_container = self.log_expander.empty()

        self.logs: List[str] = []
        self.start_time = datetime.now()
        self.current_step = 0

    def update(self, step: int, step_name: str = ""):
        """진행 상황 업데이트"""
        self.current_step = step
        percent = step / self.total_steps if self.total_steps > 0 else 0

        self.progress_bar.progress(percent)
        self.status_text.text(f"진행: {step}/{self.total_steps} - {step_name}")

        # 시간 계산
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if step > 0:
            remaining = (elapsed / step) * (self.total_steps - step)
            self.time_text.caption(f"⏱️ 경과: {elapsed:.0f}초 | 남은 시간: {remaining:.0f}초")

    def log(self, message: str, level: str = "info"):
        """로그 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        level_icons = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌"
        }

        icon = level_icons.get(level, "📝")
        log_line = f"[{timestamp}] {icon} {message}"
        self.logs.append(log_line)

        if self.show_logs:
            self.log_container.code("\n".join(self.logs[-20:]))

    def info(self, message: str):
        self.log(message, "info")

    def success(self, message: str):
        self.log(message, "success")

    def warning(self, message: str):
        self.log(message, "warning")

    def error(self, message: str):
        self.log(message, "error")

    def complete(self, message: str = "완료!"):
        """완료 처리"""
        self.progress_bar.progress(1.0)
        self.status_text.text(f"✅ {message}")
        self.success(message)

        elapsed = (datetime.now() - self.start_time).total_seconds()
        self.time_text.caption(f"⏱️ 총 소요 시간: {elapsed:.1f}초")

    def fail(self, message: str):
        """실패 처리"""
        self.status_text.text(f"❌ 실패: {message}")
        self.error(message)


def render_api_selector(
    task: str,
    label: str,
    key_prefix: str,
    show_details: bool = True
) -> str:
    """
    API 선택 UI 렌더링

    Args:
        task: 태스크 이름 (script_generation, scene_analysis, etc.)
        label: 표시할 레이블
        key_prefix: Streamlit key 접두사
        show_details: 상세 설명 표시 여부

    Returns:
        선택된 API ID
    """
    from core.api.api_manager import get_api_manager

    api_manager = get_api_manager()

    # 기능 매핑
    task_functions = {
        "script_generation": "text_generation",
        "scene_analysis": "text_generation",
        "character_extraction": "text_generation",
        "image_prompt_generation": "text_generation",
        "image_generation": "image_generation",
        "image_analysis": "image_analysis",
        "tts": "tts",
        "video_search": "video_search",
    }

    function = task_functions.get(task, "text_generation")

    # 사용 가능한 API 목록
    available_apis = {
        api_id: api for api_id, api in api_manager.AVAILABLE_APIS.items()
        if api.function == function and api.is_enabled
    }

    if not available_apis:
        st.warning(f"'{function}' 기능에 사용 가능한 API가 없습니다.")
        return ""

    # 옵션 생성
    options = {}
    for api_id, api in available_apis.items():
        price_info = "무료" if api.is_free else f"${api.price_per_unit}/{api.unit_name}"
        options[f"{api.name} ({price_info})"] = api_id

    # 현재 선택된 API
    current_api_id = api_manager.settings.get("selected_apis", {}).get(task, "")
    default_idx = 0

    for i, (name, api_id) in enumerate(options.items()):
        if api_id == current_api_id:
            default_idx = i
            break

    # 선택 UI
    selected_name = st.selectbox(
        label,
        list(options.keys()),
        index=default_idx,
        key=f"{key_prefix}_api_select"
    )

    selected_api_id = options.get(selected_name, "")

    # 상세 정보
    if show_details and selected_api_id:
        api = available_apis.get(selected_api_id)
        if api:
            st.caption(f"📝 {api.description}")

    # 설정 저장
    if selected_api_id and selected_api_id != current_api_id:
        api_manager.set_selected_api(task, selected_api_id)

    return selected_api_id


def render_log_viewer(logs: List[LogEntry], title: str = "로그"):
    """로그 뷰어 렌더링"""

    with st.expander(f"📋 {title}", expanded=False):
        if not logs:
            st.info("로그가 없습니다.")
            return

        # 레벨 필터
        level_filter = st.multiselect(
            "레벨 필터",
            ["info", "success", "warning", "error"],
            default=["info", "success", "warning", "error"]
        )

        filtered_logs = [log for log in logs if log.level in level_filter]

        # 로그 표시
        level_colors = {
            "info": "blue",
            "success": "green",
            "warning": "orange",
            "error": "red"
        }

        for log in filtered_logs[-50:]:
            color = level_colors.get(log.level, "gray")
            st.markdown(f"<span style='color:{color}'>[{log.timestamp[11:19]}] {log.message}</span>",
                       unsafe_allow_html=True)

            if log.details:
                st.caption(log.details)


def create_progress_context(task_name: str, total_steps: int, show_logs: bool = True):
    """
    프로그레스 컨텍스트 매니저

    Usage:
        with create_progress_context("이미지 생성", 10) as progress:
            for i in range(10):
                progress.update(i+1, f"이미지 {i+1} 생성 중")
                progress.info(f"이미지 {i+1} 생성 완료")
    """
    return StreamlitProgressUI(task_name, total_steps, show_logs)


def render_api_status_badge(provider: str) -> bool:
    """API 상태 뱃지 렌더링"""
    from core.api.api_manager import get_api_manager

    api_manager = get_api_manager()
    is_valid = api_manager.validate_api_key(provider)

    if is_valid:
        st.success(f"✅ {provider.upper()}")
    else:
        st.warning(f"⚠️ {provider.upper()} (키 없음)")

    return is_valid


def render_usage_mini_dashboard():
    """미니 사용량 대시보드"""
    from core.api.api_manager import get_api_manager
    from datetime import timedelta

    api_manager = get_api_manager()

    # 오늘 사용량
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    summary = api_manager.get_usage_summary(start_date=today)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("오늘 요청", f"{summary['total_requests']}")

    with col2:
        st.metric("오늘 비용", f"${summary['total_cost']:.4f}")

    with col3:
        success_rate = (summary['successful_requests'] / max(summary['total_requests'], 1)) * 100
        st.metric("성공률", f"{success_rate:.1f}%")
