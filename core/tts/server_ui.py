"""
Chatterbox TTS 서버 관리 UI 컴포넌트

사용법:
    from core.tts.server_ui import render_server_control_sidebar

    # 사이드바에 서버 제어 UI 렌더링
    render_server_control_sidebar()
"""

import streamlit as st
import time
from typing import Optional

from core.tts.server_manager import get_server_manager, CHATTER_DIR
from core.tts.chatterbox_client import chatterbox_client

# ============================================================
# 캐싱된 상태 체크 함수들 (성능 최적화!)
# ============================================================

@st.cache_data(ttl=10, show_spinner=False)
def _check_server_connection_cached() -> bool:
    """서버 연결 확인 (캐시 10초, 1초 timeout)"""
    try:
        import requests
        r = requests.get("http://localhost:8100/health", timeout=1)
        return r.status_code == 200
    except Exception:
        return False


@st.cache_data(ttl=30, show_spinner=False)
def _get_api_status_cached() -> dict:
    """서버 상태 조회 (캐시 30초, 1초 timeout)"""
    try:
        import requests
        r = requests.get("http://localhost:8100/status", timeout=1)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {"loaded": False}


@st.cache_data(ttl=300, show_spinner=False)
def _check_dependencies_cached() -> dict:
    """의존성 확인 (캐시 5분 - 자주 바뀌지 않음)"""
    from pathlib import Path
    server_dir = Path(CHATTER_DIR)
    venv_python = server_dir / "venv" / "Scripts" / "python.exe"
    return {
        "server_dir_exists": server_dir.exists(),
        "venv_exists": venv_python.exists(),
        "installed": True  # 간소화 - subprocess 호출 제거!
    }


def render_server_control_sidebar():
    """
    사이드바에 서버 제어 UI 렌더링

    기존 '❌ 서버 미연결' 섹션을 대체
    """
    manager = get_server_manager()

    st.sidebar.divider()
    st.sidebar.subheader("🔊 Chatterbox TTS 서버")

    # 서버 연결 확인 (캐시된 빠른 버전 사용!)
    is_connected = _check_server_connection_cached()

    if is_connected:
        # ─────────────────────────────────────────────────
        # 서버 연결됨
        # ─────────────────────────────────────────────────
        st.sidebar.success("✅ 서버 연결됨")
        st.sidebar.caption(f"http://localhost:8100")

        # 모델 상태 (캐시된 빠른 버전 사용!)
        status = _get_api_status_cached()

        if status.get("loaded"):
            # 모델 로드됨
            st.sidebar.markdown("**🧠 모델 상태:** 로드됨")

            # VRAM 표시
            vram_used = status.get("vram_used_mb", 0)
            vram_total = status.get("vram_total_mb", 1)
            if vram_total and vram_total > 0:
                progress = min(vram_used / vram_total, 1.0)
                st.sidebar.progress(progress)
                st.sidebar.caption(f"VRAM: {vram_used:.0f} / {vram_total:.0f} MB ({progress*100:.0f}%)")

            # 언로드 버튼
            if st.sidebar.button("🧹 VRAM 해제", key="unload_btn", use_container_width=True):
                with st.spinner("언로드 중..."):
                    result = chatterbox_client.unload_model()
                if result.get("status") == "unloaded":
                    st.sidebar.success("해제 완료!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.sidebar.error(f"실패: {result}")
        else:
            # 모델 미로드
            st.sidebar.warning("⚠️ 모델 미로드")

            if st.sidebar.button("🚀 모델 로드", key="load_btn", type="primary", use_container_width=True):
                with st.spinner("모델 로딩 중... (1-3분 소요)"):
                    result = chatterbox_client.load_model(multilingual=True)
                if result.get("status") == "loaded":
                    st.sidebar.success("로드 완료!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.sidebar.error(f"실패: {result.get('error', result)}")

        st.sidebar.divider()

        # 서버 제어 버튼
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("🔄 새로고침", key="refresh_btn", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("🛑 서버 중지", key="stop_btn", use_container_width=True):
                with st.spinner("중지 중..."):
                    result = manager.stop_server()
                if result.get("success"):
                    st.sidebar.success(result["message"])
                    time.sleep(1)
                    st.rerun()
                else:
                    st.sidebar.error(result.get("message", "실패"))

    else:
        # ─────────────────────────────────────────────────
        # 서버 미연결
        # ─────────────────────────────────────────────────
        st.sidebar.error("❌ 서버 미연결")
        st.sidebar.caption("http://localhost:8100")

        # 의존성 확인 (캐시된 빠른 버전 사용!)
        deps = _check_dependencies_cached()

        if not deps.get("server_dir_exists"):
            st.sidebar.warning("서버 폴더가 없습니다")
            st.sidebar.code("C:\\Users\\KIMJAEHEON\\chatter")
            return False

        if not deps.get("venv_exists"):
            st.sidebar.warning("⚠️ 가상환경 미설정")
            st.sidebar.caption("수동으로 설정하세요")
            return False

        # 서버 시작 버튼 (비동기 - UI 블로킹 없음!)
        st.sidebar.markdown("---")

        if st.sidebar.button("🚀 서버 시작 (새 창)", key="start_server_btn", type="primary", use_container_width=True):
            # 비동기로 서버 시작 (새 콘솔 창에서)
            import subprocess
            subprocess.Popen(
                'start cmd /k "cd /d C:\\Users\\KIMJAEHEON\\chatter && call venv\\Scripts\\activate.bat && python run.py"',
                shell=True
            )
            st.sidebar.success("✅ 서버 시작 명령 전송!")
            st.sidebar.info("새 창에서 서버가 시작됩니다.")

        # 추가 버튼
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("📂 폴더", key="folder_btn", use_container_width=True):
                manager.open_server_folder()
        with col2:
            if st.button("🔄 새로고침", key="refresh2_btn", use_container_width=True):
                st.rerun()

        # 수동 시작 안내
        with st.sidebar.expander("📋 수동 시작 방법"):
            st.code("""cd C:\\Users\\KIMJAEHEON\\chatter
call venv\\Scripts\\activate.bat
python run.py""", language="batch")

    return is_connected


def render_server_status_badge() -> bool:
    """
    간단한 서버 상태 배지 반환 (캐시된 빠른 버전)
    """
    # 캐시된 빠른 버전 사용!
    is_connected = _check_server_connection_cached()

    if is_connected:
        st.sidebar.success("🔊 TTS 서버: 정상")
        return True
    else:
        st.sidebar.error("🔊 TTS 서버: 중지됨")
        return False


def render_server_quick_start():
    """
    서버 빠른 시작 버튼 (비동기 - UI 블로킹 없음!)
    """
    # 캐시된 빠른 버전 사용!
    if not _check_server_connection_cached():
        if st.sidebar.button("🚀 TTS 서버 시작", key="quick_start", type="primary"):
            # 비동기로 서버 시작
            import subprocess
            subprocess.Popen(
                'start cmd /k "cd /d C:\\Users\\KIMJAEHEON\\chatter && call venv\\Scripts\\activate.bat && python run.py"',
                shell=True
            )
            st.sidebar.success("✅ 서버 시작됨!")
            st.sidebar.info("새 창에서 서버가 시작됩니다.")
