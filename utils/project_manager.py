"""
프로젝트 관리 모듈

⚠️ 핵심: 모든 페이지에서 session_state를 통해 프로젝트를 공유합니다.

사용법:
    from utils.project_manager import (
        ensure_project_selected,
        get_current_project,
        render_project_sidebar
    )

    # 페이지 시작 시
    render_project_sidebar()
    if not ensure_project_selected():
        st.stop()

    project_path = get_current_project()
"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import PROJECTS_DIR
from config.constants import PROJECT_STATUS, WORKFLOW_STEPS


def init_session_state():
    """
    세션 상태 초기화 - 앱 시작 시 호출

    초기화되는 상태:
    - current_project_id: 현재 프로젝트 ID
    - current_project_path: 현재 프로젝트 경로
    - current_project_name: 현재 프로젝트 이름
    """
    if "current_project_id" not in st.session_state:
        st.session_state.current_project_id = None
    if "current_project_path" not in st.session_state:
        st.session_state.current_project_path = None
    if "current_project_name" not in st.session_state:
        st.session_state.current_project_name = None


def ensure_project_selected() -> bool:
    """
    프로젝트 선택 확인 - 모든 페이지 시작 시 호출

    Returns:
        bool: 프로젝트가 선택되었으면 True, 아니면 False

    사용법:
        if not ensure_project_selected():
            st.stop()
    """
    init_session_state()

    if st.session_state.current_project_id is None:
        st.warning("⚠️ 먼저 프로젝트를 선택해주세요.")
        st.info("👈 사이드바에서 프로젝트를 선택하거나 새로 생성하세요.")
        return False

    return True


def get_current_project() -> Optional[Path]:
    """
    현재 선택된 프로젝트 경로 반환

    Returns:
        Path 또는 None
    """
    init_session_state()

    if st.session_state.current_project_path:
        return Path(st.session_state.current_project_path)

    return None


def get_current_project_config() -> Optional[Dict]:
    """
    현재 프로젝트의 config.json 내용 반환

    Returns:
        dict 또는 None
    """
    project_path = get_current_project()
    if project_path:
        config_path = project_path / "config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def set_current_project(project_id: str):
    """
    현재 프로젝트 설정

    Args:
        project_id: 프로젝트 ID (폴더명)
    """
    project_path = PROJECTS_DIR / project_id

    if project_path.exists():
        st.session_state.current_project_id = project_id
        st.session_state.current_project_path = str(project_path)

        config_path = project_path / "config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                st.session_state.current_project_name = config.get("name", project_id)
        else:
            st.session_state.current_project_name = project_id


def create_project(name: str, language: str = "ko") -> str:
    """
    새 프로젝트 생성 - 폴더 구조 자동 생성

    Args:
        name: 프로젝트 이름
        language: 언어 ("ko" 또는 "ja")

    Returns:
        생성된 프로젝트 ID
    """
    # 프로젝트 ID 생성 (타임스탬프 + 이름)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    project_id = f"{timestamp}_{safe_name}"
    project_path = PROJECTS_DIR / project_id

    # 폴더 구조 생성
    folders = [
        "research",
        "research/transcripts",
        "research/comments",
        "research/thumbnails",
        "scripts",
        "audio",
        "prompts",
        "images/thumbnail",
        "images/content",
        "export"
    ]

    for folder in folders:
        (project_path / folder).mkdir(parents=True, exist_ok=True)

    # config.json 생성
    config = {
        "id": project_id,
        "name": name,
        "language": language,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "current_step": 1,
        "status": "in_progress"
    }

    with open(project_path / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    # 현재 프로젝트로 설정
    set_current_project(project_id)

    return project_id


def update_project_config(updates: Dict):
    """
    현재 프로젝트 설정 업데이트

    Args:
        updates: 업데이트할 키-값 딕셔너리
    """
    project_path = get_current_project()
    if not project_path:
        return

    config_path = project_path / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        config.update(updates)
        config["updated_at"] = datetime.now().isoformat()

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)


def update_project_step(step: int):
    """
    프로젝트 현재 단계 업데이트

    Args:
        step: 단계 번호 (1-7)
    """
    update_project_config({"current_step": step})


def list_projects() -> List[Dict]:
    """
    프로젝트 목록 반환 (최신순)

    Returns:
        프로젝트 config 딕셔너리 리스트
    """
    projects = []

    if not PROJECTS_DIR.exists():
        return projects

    for project_dir in PROJECTS_DIR.iterdir():
        if project_dir.is_dir():
            config_path = project_dir / "config.json"
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                        projects.append(config)
                except (json.JSONDecodeError, IOError):
                    continue

    # 최신순 정렬
    return sorted(projects, key=lambda x: x.get("created_at", ""), reverse=True)


def delete_project(project_id: str) -> bool:
    """
    프로젝트 삭제

    Args:
        project_id: 프로젝트 ID

    Returns:
        성공 여부
    """
    import shutil

    project_path = PROJECTS_DIR / project_id
    if project_path.exists():
        try:
            shutil.rmtree(project_path)

            # 현재 프로젝트였다면 초기화
            if st.session_state.get("current_project_id") == project_id:
                st.session_state.current_project_id = None
                st.session_state.current_project_path = None
                st.session_state.current_project_name = None

            return True
        except Exception:
            return False
    return False


def render_project_sidebar():
    """
    사이드바에 프로젝트 선택 UI 렌더링 - 모든 페이지에서 호출

    기능:
    - 기존 프로젝트 선택
    - 새 프로젝트 생성
    - 현재 프로젝트 정보 표시
    """
    init_session_state()

    with st.sidebar:
        st.header("📁 프로젝트")

        # 프로젝트 목록
        projects = list_projects()

        if projects:
            # 프로젝트 선택 드롭다운
            project_options = {p["name"]: p["id"] for p in projects}
            project_names = list(project_options.keys())

            # 현재 선택된 프로젝트의 인덱스 찾기
            current_index = 0
            if st.session_state.current_project_name in project_names:
                current_index = project_names.index(st.session_state.current_project_name)

            selected_name = st.selectbox(
                "프로젝트 선택",
                project_names,
                index=current_index,
                key="project_selector"
            )

            if selected_name:
                selected_id = project_options[selected_name]
                if selected_id != st.session_state.current_project_id:
                    set_current_project(selected_id)
                    st.rerun()

            # 현재 프로젝트 정보
            config = get_current_project_config()
            if config:
                st.caption(f"언어: {config.get('language', 'ko').upper()}")
                st.caption(f"단계: {config.get('current_step', 1)}/7")

        else:
            st.info("프로젝트가 없습니다.")

        st.divider()

        # 새 프로젝트 생성
        with st.expander("➕ 새 프로젝트 생성"):
            new_name = st.text_input(
                "프로젝트 이름",
                placeholder="예: 1인창업 가이드",
                key="new_project_name"
            )
            new_lang = st.selectbox(
                "언어",
                ["한국어", "일본어"],
                key="new_project_lang"
            )

            if st.button("생성", type="primary", key="create_project_btn"):
                if new_name:
                    lang_code = "ko" if new_lang == "한국어" else "ja"
                    create_project(new_name, lang_code)
                    st.success(f"✅ '{new_name}' 프로젝트 생성됨")
                    st.rerun()
                else:
                    st.error("프로젝트 이름을 입력하세요.")


def render_project_info():
    """
    현재 프로젝트 정보를 메인 영역에 표시
    """
    config = get_current_project_config()
    if config:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("프로젝트", config.get("name", "N/A"))
        with col2:
            st.metric("언어", config.get("language", "ko").upper())
        with col3:
            st.metric("현재 단계", f"{config.get('current_step', 1)}/7")
        with col4:
            status = config.get("status", "in_progress")
            st.metric("상태", PROJECT_STATUS.get(status, status))


def render_workflow_progress():
    """
    워크플로우 진행 상황 표시
    """
    config = get_current_project_config()
    if not config:
        return

    current_step = config.get("current_step", 1)

    cols = st.columns(len(WORKFLOW_STEPS))
    for i, step in enumerate(WORKFLOW_STEPS):
        with cols[i]:
            if step["id"] < current_step:
                st.success(f"{step['icon']} {step['id']}")
            elif step["id"] == current_step:
                st.info(f"{step['icon']} {step['id']}")
            else:
                st.caption(f"{step['icon']} {step['id']}")
