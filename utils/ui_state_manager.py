"""
UI 상태 관리 유틸리티 v1.0

페이지 새로고침 시에도 사용자 상태를 유지하고
불필요한 rerun을 방지하는 유틸리티
"""

import streamlit as st
from typing import Any, Optional, Dict, List, Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PageState:
    """페이지 상태 저장"""

    # 현재 선택된 씬
    selected_scene: Optional[int] = None

    # 스크롤 위치 (씬 번호 기준)
    scroll_to_scene: Optional[int] = None

    # 확장된 expander 목록
    expanded_expanders: List[str] = field(default_factory=list)

    # 마지막 작업 결과
    last_action_result: Optional[Dict] = None

    # 탭 인덱스
    active_tab: int = 0

    # 페이지별 필터 상태
    filters: Dict[str, Any] = field(default_factory=dict)


class UIStateManager:
    """
    UI 상태 관리자

    페이지 새로고침 시에도 상태를 유지하고,
    불필요한 rerun을 방지
    """

    @staticmethod
    def init_page_state(page_name: str) -> PageState:
        """
        페이지 상태 초기화

        Args:
            page_name: 페이지 식별자

        Returns:
            PageState 객체
        """
        state_key = f"page_state_{page_name}"

        if state_key not in st.session_state:
            st.session_state[state_key] = PageState()

        return st.session_state[state_key]

    @staticmethod
    def save_scroll_position(page_name: str, scene_number: int):
        """스크롤 위치 저장"""
        state_key = f"page_state_{page_name}"

        if state_key in st.session_state:
            st.session_state[state_key].scroll_to_scene = scene_number

    @staticmethod
    def get_scroll_position(page_name: str) -> Optional[int]:
        """스크롤 위치 가져오기"""
        state_key = f"page_state_{page_name}"

        if state_key in st.session_state:
            return st.session_state[state_key].scroll_to_scene

        return None

    @staticmethod
    def clear_scroll_position(page_name: str):
        """스크롤 위치 초기화"""
        state_key = f"page_state_{page_name}"

        if state_key in st.session_state:
            st.session_state[state_key].scroll_to_scene = None

    @staticmethod
    def save_expander_state(page_name: str, expander_id: str, expanded: bool):
        """Expander 상태 저장"""
        state_key = f"page_state_{page_name}"

        if state_key in st.session_state:
            state = st.session_state[state_key]

            if expanded and expander_id not in state.expanded_expanders:
                state.expanded_expanders.append(expander_id)
            elif not expanded and expander_id in state.expanded_expanders:
                state.expanded_expanders.remove(expander_id)

    @staticmethod
    def is_expander_expanded(page_name: str, expander_id: str) -> bool:
        """Expander가 확장되어 있는지 확인"""
        state_key = f"page_state_{page_name}"

        if state_key in st.session_state:
            return expander_id in st.session_state[state_key].expanded_expanders

        return False

    @staticmethod
    def save_action_result(page_name: str, result: Dict):
        """작업 결과 저장"""
        state_key = f"page_state_{page_name}"

        if state_key in st.session_state:
            st.session_state[state_key].last_action_result = {
                **result,
                'timestamp': datetime.now().isoformat()
            }

    @staticmethod
    def get_and_clear_action_result(page_name: str) -> Optional[Dict]:
        """작업 결과 가져오고 초기화"""
        state_key = f"page_state_{page_name}"

        if state_key in st.session_state:
            result = st.session_state[state_key].last_action_result
            st.session_state[state_key].last_action_result = None
            return result

        return None

    @staticmethod
    def save_selected_scene(page_name: str, scene_num: int):
        """선택된 씬 저장"""
        state_key = f"page_state_{page_name}"

        if state_key in st.session_state:
            st.session_state[state_key].selected_scene = scene_num

    @staticmethod
    def get_selected_scene(page_name: str) -> Optional[int]:
        """선택된 씬 가져오기"""
        state_key = f"page_state_{page_name}"

        if state_key in st.session_state:
            return st.session_state[state_key].selected_scene

        return None


def prevent_rerun_decorator(func: Callable) -> Callable:
    """
    불필요한 rerun 방지 데코레이터

    함수 실행 후 결과를 session_state에 저장하고,
    다음 rerun에서 저장된 결과를 사용
    """
    def wrapper(*args, **kwargs):
        cache_key = f"_cache_{func.__name__}"

        # 이미 실행된 결과가 있으면 반환
        if cache_key in st.session_state:
            result = st.session_state[cache_key]
            del st.session_state[cache_key]  # 1회용
            return result

        # 실행 및 저장
        result = func(*args, **kwargs)
        st.session_state[cache_key] = result

        return result

    return wrapper


def smart_rerun(condition: bool = True, delay_ms: int = 0):
    """
    스마트 rerun - 조건부 및 지연 rerun

    Args:
        condition: rerun 실행 조건
        delay_ms: 지연 시간 (밀리초)
    """
    if not condition:
        return

    if delay_ms > 0:
        import time
        time.sleep(delay_ms / 1000)

    st.rerun()


def create_generation_callback(
    generation_func: Callable,
    result_key: str,
    **kwargs
) -> Callable:
    """
    이미지 생성용 콜백 함수 생성

    버튼 on_click에서 사용하여 rerun 전에 결과를 저장

    Args:
        generation_func: 실제 생성 함수
        result_key: 결과를 저장할 session_state 키
        **kwargs: 생성 함수에 전달할 인자

    Returns:
        콜백 함수
    """
    def callback():
        try:
            result = generation_func(**kwargs)
            st.session_state[result_key] = {
                'success': result.get('success', False) if isinstance(result, dict) else True,
                'result': result,
                'timestamp': datetime.now().isoformat(),
                'show': True  # 결과 표시 플래그
            }
        except Exception as e:
            st.session_state[result_key] = {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
                'show': True
            }

    return callback


def show_generation_result(
    result_key: str,
    success_message: str = "✅ 생성 완료!",
    clear_after_show: bool = False
) -> Optional[Dict]:
    """
    저장된 생성 결과 표시

    Args:
        result_key: 결과 키
        success_message: 성공 메시지
        clear_after_show: 표시 후 결과 삭제 여부

    Returns:
        결과 딕셔너리 또는 None
    """
    if result_key not in st.session_state:
        return None

    result_state = st.session_state[result_key]

    if not result_state.get('show'):
        return None

    if result_state.get('success'):
        st.success(success_message)
        result = result_state.get('result')

        # 이미지 경로가 있으면 표시
        if isinstance(result, dict):
            image_path = result.get('path') or result.get('image_path')
            if image_path:
                import os
                if os.path.exists(image_path):
                    st.image(image_path, use_container_width=True)
    else:
        error = result_state.get('error', '알 수 없는 오류')
        st.error(f"❌ 실패: {error}")

    if clear_after_show:
        del st.session_state[result_key]
    else:
        # show 플래그만 false로
        st.session_state[result_key]['show'] = False

    return result_state


def save_and_restore_scroll_js():
    """
    JavaScript로 스크롤 위치 저장/복원

    페이지에 한 번만 삽입하면 됨
    """
    scroll_js = """
    <script>
        // 페이지 로드 시 스크롤 복원
        (function() {
            const scrollPos = sessionStorage.getItem('longform_scroll_position');
            if (scrollPos) {
                setTimeout(function() {
                    window.scrollTo(0, parseInt(scrollPos));
                    sessionStorage.removeItem('longform_scroll_position');
                }, 100);
            }
        })();

        // Streamlit rerun 감지하여 스크롤 저장
        const observer = new MutationObserver(function(mutations) {
            sessionStorage.setItem('longform_scroll_position', window.scrollY);
        });

        // body 변경 감시
        observer.observe(document.body, { childList: true, subtree: true });
    </script>
    """

    st.markdown(scroll_js, unsafe_allow_html=True)


def scroll_to_scene(scene_num: int):
    """
    특정 씬으로 스크롤

    Args:
        scene_num: 스크롤할 씬 번호
    """
    scroll_js = f"""
    <script>
        setTimeout(function() {{
            const element = document.getElementById('scene-{scene_num}');
            if (element) {{
                element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }}
        }}, 200);
    </script>
    """

    st.markdown(scroll_js, unsafe_allow_html=True)


def create_scene_anchor(scene_num: int):
    """
    씬 앵커 생성 (스크롤 대상)

    Args:
        scene_num: 씬 번호
    """
    st.markdown(f'<div id="scene-{scene_num}"></div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# 편의 함수들
# ═══════════════════════════════════════════════════════════════

def init_generation_state(key_prefix: str, scene_num: int) -> Dict:
    """
    생성 상태 초기화 및 반환

    Args:
        key_prefix: 상태 키 접두사 (예: 'composite', 'background')
        scene_num: 씬 번호

    Returns:
        상태 딕셔너리
    """
    state_key = f"{key_prefix}_state_{scene_num}"

    if state_key not in st.session_state:
        st.session_state[state_key] = {
            'generating': False,
            'result': None,
            'error': None,
            'last_update': None
        }

    return st.session_state[state_key]


def update_generation_state(
    key_prefix: str,
    scene_num: int,
    generating: bool = None,
    result: Any = None,
    error: str = None
):
    """
    생성 상태 업데이트

    Args:
        key_prefix: 상태 키 접두사
        scene_num: 씬 번호
        generating: 생성 중 여부
        result: 생성 결과
        error: 에러 메시지
    """
    state_key = f"{key_prefix}_state_{scene_num}"

    if state_key not in st.session_state:
        st.session_state[state_key] = {}

    state = st.session_state[state_key]

    if generating is not None:
        state['generating'] = generating
    if result is not None:
        state['result'] = result
        state['last_update'] = datetime.now().isoformat()
    if error is not None:
        state['error'] = error


def get_generation_result(key_prefix: str, scene_num: int) -> Optional[Any]:
    """
    저장된 생성 결과 가져오기

    Args:
        key_prefix: 상태 키 접두사
        scene_num: 씬 번호

    Returns:
        생성 결과 또는 None
    """
    state_key = f"{key_prefix}_state_{scene_num}"

    if state_key in st.session_state:
        return st.session_state[state_key].get('result')

    return None
