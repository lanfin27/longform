"""
프로젝트-영상 계층 구조 관리 모듈 v2.0

⚠️ 핵심: 2단계 계층 구조
- 프로젝트(채널): data/projects/{project_name}/
- 영상: data/projects/{project_name}/videos/{video_name}/

⚠️ 하위 호환성:
- st.session_state.current_project_path는 영상 경로를 가리킴
- 기존 코드에서 project_path를 사용하던 것이 그대로 작동

사용법:
    from utils.project_manager import (
        ensure_project_selected,
        get_current_project,
        render_project_sidebar,
        # 새 함수들
        get_current_channel,
        get_current_video,
    )

    # 페이지 시작 시
    render_project_sidebar()
    if not ensure_project_selected():
        st.stop()

    # 현재 작업 경로 (= 영상 경로)
    project_path = get_current_project()
"""
import streamlit as st
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import PROJECTS_DIR
from config.constants import PROJECT_STATUS, WORKFLOW_STEPS


# ============================================================
# 세션 상태 초기화
# ============================================================

def init_session_state():
    """
    세션 상태 초기화 - 앱 시작 시 호출

    초기화되는 상태:
    - current_channel: 현재 채널(프로젝트) 이름
    - current_video: 현재 영상 이름
    - current_project_path: 현재 작업 경로 (영상 경로) - 하위 호환
    - current_project_id: 하위 호환용
    - current_project_name: 하위 호환용
    """
    if "current_channel" not in st.session_state:
        st.session_state.current_channel = None
    if "current_video" not in st.session_state:
        st.session_state.current_video = None
    if "current_project_id" not in st.session_state:
        st.session_state.current_project_id = None
    if "current_project_path" not in st.session_state:
        st.session_state.current_project_path = None
    if "current_project_name" not in st.session_state:
        st.session_state.current_project_name = None


# ============================================================
# 채널(프로젝트) 관리
# ============================================================

def list_channels() -> List[Dict]:
    """
    채널(프로젝트) 목록 반환

    Returns:
        채널 정보 딕셔너리 리스트
    """
    channels = []

    if not PROJECTS_DIR.exists():
        return channels

    for item in PROJECTS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith('.') and not item.name.startswith('_'):
            config_path = item / "project_config.json"

            channel_info = {
                "name": item.name,
                "path": str(item),
                "video_count": _count_videos(item),
                "is_new_structure": (item / "videos").exists()
            }

            # 설정 파일이 있으면 추가 정보 로드
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    # name은 폴더명으로 유지, 설정의 name은 display_name으로
                    display_name = config.pop("name", item.name)
                    channel_info["display_name"] = display_name
                    channel_info.update(config)
                except:
                    pass

            # 레거시 config.json도 확인
            elif (item / "config.json").exists():
                try:
                    with open(item / "config.json", "r", encoding="utf-8") as f:
                        config = json.load(f)
                    channel_info["display_name"] = config.get("name", item.name)
                    channel_info["is_legacy"] = True
                except:
                    pass

            channels.append(channel_info)

    return sorted(channels, key=lambda x: x["name"])


def create_channel(name: str, description: str = "") -> Dict:
    """
    새 채널(프로젝트) 생성

    Args:
        name: 채널 이름
        description: 채널 설명

    Returns:
        생성된 채널 정보
    """
    # 안전한 폴더명 생성
    safe_name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    channel_path = PROJECTS_DIR / safe_name

    channel_path.mkdir(parents=True, exist_ok=True)

    # videos 폴더 생성
    videos_path = channel_path / "videos"
    videos_path.mkdir(exist_ok=True)

    # 공유 폴더 생성
    (channel_path / "shared_characters").mkdir(exist_ok=True)
    (channel_path / "shared_styles").mkdir(exist_ok=True)

    # 프로젝트 설정 파일
    config = {
        "name": name,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "default_style": None,
        "default_tts_voice": None,
        "settings": {}
    }

    config_path = channel_path / "project_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"[ProjectManager] ✅ 채널 생성됨: {name}")

    return {
        "name": safe_name,
        "display_name": name,
        "path": str(channel_path),
        "config": config
    }


def get_channel_path(channel_name: str) -> Path:
    """채널 경로 반환"""
    return PROJECTS_DIR / channel_name


def get_channel_config(channel_name: str) -> Optional[Dict]:
    """채널 설정 로드"""
    config_path = PROJECTS_DIR / channel_name / "project_config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return None


def _count_videos(channel_path: Path) -> int:
    """채널 내 영상 수"""
    videos_path = channel_path / "videos"
    if not videos_path.exists():
        # 레거시 구조 (videos 폴더 없음)
        # 데이터가 있으면 1로 계산
        has_data = any([
            (channel_path / "script.txt").exists(),
            (channel_path / "script.srt").exists(),
            (channel_path / "analysis").exists(),
        ])
        return 1 if has_data else 0
    return len([d for d in videos_path.iterdir() if d.is_dir() and not d.name.startswith('.')])


# ============================================================
# 영상 관리
# ============================================================

def list_videos(channel_name: str) -> List[Dict]:
    """
    채널 내 영상 목록

    Args:
        channel_name: 채널 이름

    Returns:
        영상 정보 딕셔너리 리스트
    """
    channel_path = PROJECTS_DIR / channel_name
    videos_path = channel_path / "videos"

    videos = []

    # 새 구조 (videos 폴더 있음)
    if videos_path.exists():
        for item in videos_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                config_path = item / "video_config.json"

                video_info = {
                    "name": item.name,
                    "path": str(item),
                    "channel": channel_name
                }

                # 설정 파일이 있으면 추가 정보 로드
                if config_path.exists():
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            config = json.load(f)
                        video_info.update(config)
                    except:
                        pass

                # 상태 정보 계산
                video_info["status_info"] = _get_video_status(item)

                videos.append(video_info)

    # 레거시 구조 (videos 폴더 없음) - 채널 자체가 영상
    else:
        has_data = any([
            (channel_path / "script.txt").exists(),
            (channel_path / "script.srt").exists(),
            (channel_path / "analysis").exists(),
            (channel_path / "characters").exists(),
        ])

        if has_data:
            video_info = {
                "name": channel_name,
                "path": str(channel_path),
                "channel": channel_name,
                "is_legacy": True,
                "title": channel_name,
                "status_info": _get_video_status(channel_path)
            }

            # 레거시 config.json에서 제목 가져오기
            legacy_config = channel_path / "config.json"
            if legacy_config.exists():
                try:
                    with open(legacy_config, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    video_info["title"] = config.get("name", channel_name)
                except:
                    pass

            videos.append(video_info)

    return sorted(videos, key=lambda x: x.get("created_at", ""), reverse=True)


def create_video(channel_name: str, video_name: str, title: str = "") -> Dict:
    """
    새 영상 생성

    Args:
        channel_name: 채널 이름
        video_name: 영상 폴더명
        title: 영상 제목

    Returns:
        생성된 영상 정보
    """
    # 안전한 폴더명
    safe_name = video_name.replace(" ", "_").replace("/", "_").replace("\\", "_")

    # 채널 내 videos 폴더 확인
    channel_path = PROJECTS_DIR / channel_name
    videos_path = channel_path / "videos"
    videos_path.mkdir(parents=True, exist_ok=True)

    video_path = videos_path / safe_name
    video_path.mkdir(parents=True, exist_ok=True)

    # 하위 폴더 생성
    folders = [
        "analysis",
        "characters",
        "images/backgrounds",
        "images/composited",
        "images/content",
        "audio",
        "output",
        "research",
        "research/transcripts",
        "scripts",
        "prompts",
    ]

    for folder in folders:
        (video_path / folder).mkdir(parents=True, exist_ok=True)

    # 영상 설정 파일
    config = {
        "title": title or video_name,
        "description": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "status": "created",
        "current_step": 1,
        "settings": {},
        "statistics": {
            "total_scenes": 0,
            "total_characters": 0,
            "generated_images": 0,
            "generated_audio": 0
        }
    }

    config_path = video_path / "video_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"[ProjectManager] ✅ 영상 생성됨: {channel_name}/{safe_name}")

    return {
        "name": safe_name,
        "path": str(video_path),
        "channel": channel_name,
        "config": config
    }


def get_video_path(channel_name: str, video_name: str) -> Path:
    """영상 경로 반환"""
    channel_path = PROJECTS_DIR / channel_name

    # 레거시 구조 체크
    if video_name == channel_name and not (channel_path / "videos").exists():
        return channel_path

    return channel_path / "videos" / video_name


def get_video_config(channel_name: str, video_name: str) -> Optional[Dict]:
    """영상 설정 로드"""
    video_path = get_video_path(channel_name, video_name)

    # 새 구조
    config_path = video_path / "video_config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass

    # 레거시 구조
    config_path = video_path / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass

    return None


def _get_video_status(video_path: Path) -> Dict:
    """영상 진행 상태 계산"""
    status = {
        "has_script": (video_path / "script.txt").exists() or (video_path / "script.srt").exists(),
        "has_analysis": (video_path / "analysis" / "scenes.json").exists(),
        "has_characters": any((video_path / "characters").glob("*.png")) if (video_path / "characters").exists() else False,
        "has_images": any((video_path / "images").rglob("*.png")) if (video_path / "images").exists() else False,
        "has_audio": (any((video_path / "audio").glob("*.mp3")) or any((video_path / "audio").glob("*.wav"))) if (video_path / "audio").exists() else False,
        "has_output": any((video_path / "output").glob("*.*")) if (video_path / "output").exists() else False
    }

    # 진행률 계산
    steps = ["has_script", "has_analysis", "has_characters", "has_images", "has_audio", "has_output"]
    completed = sum(1 for s in steps if status.get(s))
    status["progress"] = int(completed / len(steps) * 100)

    return status


# ============================================================
# 현재 선택 관리 (하위 호환성 유지!)
# ============================================================

def set_current_selection(channel_name: str, video_name: str):
    """
    현재 채널/영상 선택 설정

    ⚠️ 핵심: current_project_path를 영상 경로로 설정하여 하위 호환성 유지
    """
    video_path = get_video_path(channel_name, video_name)

    st.session_state.current_channel = channel_name
    st.session_state.current_video = video_name

    # ⚠️ 하위 호환: current_project_path = video_path
    st.session_state.current_project_path = str(video_path)
    st.session_state.current_project_id = f"{channel_name}/{video_name}"
    st.session_state.current_project_name = video_name


def get_current_channel() -> Optional[str]:
    """현재 선택된 채널 이름"""
    init_session_state()
    return st.session_state.current_channel


def get_current_video() -> Optional[str]:
    """현재 선택된 영상 이름"""
    init_session_state()
    return st.session_state.current_video


# ============================================================
# 하위 호환성 함수들 (기존 코드와 동일하게 동작)
# ============================================================

def ensure_project_selected() -> bool:
    """
    프로젝트(영상) 선택 확인 - 모든 페이지 시작 시 호출

    Returns:
        bool: 프로젝트가 선택되었으면 True, 아니면 False
    """
    init_session_state()

    # 채널과 영상 둘 다 선택되어야 함
    if st.session_state.current_channel is None or st.session_state.current_video is None:
        st.warning("⚠️ 먼저 프로젝트와 영상을 선택해주세요.")
        st.info("👈 사이드바에서 채널과 영상을 선택하거나 새로 생성하세요.")
        return False

    return True


def get_current_project() -> Optional[Path]:
    """
    현재 선택된 프로젝트 경로 반환 (하위 호환)

    ⚠️ 실제로는 영상 경로를 반환함!

    Returns:
        Path 또는 None
    """
    init_session_state()

    if st.session_state.current_project_path:
        return Path(st.session_state.current_project_path)

    return None


def get_current_project_config() -> Optional[Dict]:
    """
    현재 프로젝트(영상)의 설정 반환 (하위 호환)

    Returns:
        dict 또는 None
    """
    channel = get_current_channel()
    video = get_current_video()

    if channel and video:
        return get_video_config(channel, video)

    return None


def set_current_project(project_id: str):
    """
    현재 프로젝트 설정 (하위 호환)

    ⚠️ 레거시 지원: project_id를 채널명으로 해석
    """
    channels = list_channels()

    for ch in channels:
        if ch["name"] == project_id:
            videos = list_videos(project_id)
            if videos:
                # 첫 번째 영상 선택
                set_current_selection(project_id, videos[0]["name"])
                return

    # 새 구조가 아니면 레거시로 처리
    project_path = PROJECTS_DIR / project_id
    if project_path.exists():
        st.session_state.current_channel = project_id
        st.session_state.current_video = project_id
        st.session_state.current_project_path = str(project_path)
        st.session_state.current_project_id = project_id
        st.session_state.current_project_name = project_id


def create_project(name: str, language: str = "ko") -> str:
    """
    새 프로젝트 생성 (하위 호환)

    ⚠️ 새 구조: 채널 + 첫 번째 영상 생성

    Args:
        name: 프로젝트 이름
        language: 언어

    Returns:
        생성된 프로젝트 ID
    """
    # 채널 생성
    channel_info = create_channel(name)
    channel_name = channel_info["name"]

    # 첫 번째 영상 생성 (채널명과 동일)
    video_info = create_video(channel_name, name)

    # 현재 선택으로 설정
    set_current_selection(channel_name, video_info["name"])

    return channel_name


def update_project_config(updates: Dict):
    """
    현재 프로젝트 설정 업데이트 (하위 호환)

    Args:
        updates: 업데이트할 키-값 딕셔너리
    """
    video_path = get_current_project()
    if not video_path:
        return

    # 새 구조
    config_path = video_path / "video_config.json"
    if not config_path.exists():
        # 레거시 구조
        config_path = video_path / "config.json"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        config.update(updates)
        config["updated_at"] = datetime.now().isoformat()

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)


def update_project_step(step: int):
    """
    프로젝트 현재 단계 업데이트 (하위 호환)

    Args:
        step: 단계 번호 (1-7)
    """
    update_project_config({"current_step": step})


def list_projects() -> List[Dict]:
    """
    프로젝트 목록 반환 (하위 호환)

    ⚠️ 새 구조에서는 모든 영상을 플랫 리스트로 반환

    Returns:
        프로젝트(영상) config 딕셔너리 리스트
    """
    projects = []

    for channel in list_channels():
        for video in list_videos(channel["name"]):
            # 하위 호환 형식으로 변환
            project_info = {
                "id": f"{channel['name']}/{video['name']}",
                "name": video.get("title", video["name"]),
                "channel": channel["name"],
                "video": video["name"],
                "created_at": video.get("created_at", ""),
                "current_step": video.get("current_step", 1),
                "status": video.get("status", "in_progress"),
                "path": video["path"]
            }
            projects.append(project_info)

    # 최신순 정렬
    return sorted(projects, key=lambda x: x.get("created_at", ""), reverse=True)


def delete_project(project_id: str) -> bool:
    """
    프로젝트 삭제 (하위 호환)

    Args:
        project_id: 프로젝트 ID (채널명/영상명 또는 채널명)

    Returns:
        성공 여부
    """
    if "/" in project_id:
        # 새 구조: 채널명/영상명
        channel_name, video_name = project_id.split("/", 1)
        video_path = get_video_path(channel_name, video_name)

        if video_path.exists():
            try:
                shutil.rmtree(video_path)

                # 현재 선택이었다면 초기화
                if (st.session_state.get("current_channel") == channel_name and
                    st.session_state.get("current_video") == video_name):
                    st.session_state.current_channel = None
                    st.session_state.current_video = None
                    st.session_state.current_project_id = None
                    st.session_state.current_project_path = None
                    st.session_state.current_project_name = None

                return True
            except Exception:
                return False
    else:
        # 레거시 구조: 채널명만
        channel_path = PROJECTS_DIR / project_id
        if channel_path.exists():
            try:
                shutil.rmtree(channel_path)

                if st.session_state.get("current_channel") == project_id:
                    st.session_state.current_channel = None
                    st.session_state.current_video = None
                    st.session_state.current_project_id = None
                    st.session_state.current_project_path = None
                    st.session_state.current_project_name = None

                return True
            except Exception:
                return False

    return False


# ============================================================
# 사이드바 UI (2단계 선택)
# ============================================================

def render_project_sidebar():
    """
    사이드바에 프로젝트/영상 선택 UI 렌더링

    2단계 선택:
    1. 채널(프로젝트) 선택
    2. 영상 선택
    """
    init_session_state()

    with st.sidebar:
        st.header("📁 프로젝트")

        # ============================================================
        # 1단계: 채널 선택
        # ============================================================

        channels = list_channels()
        channel_names = [ch["name"] for ch in channels]

        if not channel_names:
            st.info("프로젝트가 없습니다.")
            _render_create_channel_form()
            return

        # 채널 표시명 매핑 (폴더명 -> 표시명)
        channel_display_names = {ch["name"]: ch.get("display_name", ch["name"]) for ch in channels}

        # 현재 선택된 채널의 인덱스 찾기
        current_channel = st.session_state.current_channel
        current_index = 0
        if current_channel in channel_names:
            current_index = channel_names.index(current_channel)

        selected_channel = st.selectbox(
            "🎬 채널 선택",
            channel_names,
            index=current_index,
            format_func=lambda x: channel_display_names.get(x, x),
            key="channel_selector",
            help="유튜브 채널 또는 프로젝트 그룹"
        )

        # 채널 정보 표시
        channel_info = next((ch for ch in channels if ch["name"] == selected_channel), None)
        if channel_info:
            video_count = channel_info.get("video_count", 0)
            st.caption(f"📹 영상 {video_count}개")

        st.divider()

        # ============================================================
        # 2단계: 영상 선택
        # ============================================================

        videos = list_videos(selected_channel)
        video_names = [v["name"] for v in videos]

        if not video_names:
            st.info("영상이 없습니다.")
            _render_create_video_form(selected_channel)
        else:
            # 현재 선택된 영상의 인덱스 찾기
            current_video = st.session_state.current_video
            video_index = 0
            if current_video in video_names:
                video_index = video_names.index(current_video)

            # 영상 선택 드롭다운 (제목 표시)
            video_options = {v["name"]: v.get("title", v["name"]) for v in videos}

            selected_video = st.selectbox(
                "📹 영상 선택",
                video_names,
                index=video_index,
                format_func=lambda x: video_options.get(x, x),
                key="video_selector"
            )

            # 선택 변경 감지 및 적용
            if (selected_channel != st.session_state.current_channel or
                selected_video != st.session_state.current_video):
                set_current_selection(selected_channel, selected_video)
                st.rerun()

            # 영상 진행 상태 표시
            video_info = next((v for v in videos if v["name"] == selected_video), None)
            if video_info and "status_info" in video_info:
                _render_video_progress(video_info["status_info"])

        st.divider()

        # ============================================================
        # 새로 만들기 버튼
        # ============================================================

        col1, col2 = st.columns(2)

        with col1:
            if st.button("➕ 새 채널", key="btn_new_channel", use_container_width=True):
                st.session_state.show_create_channel = True

        with col2:
            if st.button("➕ 새 영상", key="btn_new_video", use_container_width=True):
                st.session_state.show_create_video = True

        # 생성 폼 표시
        if st.session_state.get("show_create_channel"):
            _render_create_channel_form()

        if st.session_state.get("show_create_video") and selected_channel:
            _render_create_video_form(selected_channel)


def _render_video_progress(status: Dict):
    """영상 진행 상태 표시"""
    progress = status.get("progress", 0)

    st.progress(progress / 100, text=f"진행률 {progress}%")

    # 단계별 상태 아이콘
    cols = st.columns(6)
    icons = ["📝", "🔍", "👤", "🖼️", "🔊", "📦"]
    keys = ["has_script", "has_analysis", "has_characters", "has_images", "has_audio", "has_output"]
    labels = ["스크립트", "분석", "캐릭터", "이미지", "오디오", "출력"]

    for col, icon, key, label in zip(cols, icons, keys, labels):
        with col:
            if status.get(key):
                st.markdown(f"{icon}✅", help=f"{label} 완료")
            else:
                st.markdown(f"{icon}⬜", help=f"{label} 미완료")


def _render_create_channel_form():
    """새 채널 생성 폼"""
    with st.expander("➕ 새 채널 생성", expanded=True):
        new_name = st.text_input(
            "채널 이름",
            placeholder="예: 세모지, 시니어채널",
            key="new_channel_name"
        )
        new_desc = st.text_input(
            "설명 (선택)",
            placeholder="채널 설명...",
            key="new_channel_desc"
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("생성", type="primary", key="create_channel_btn"):
                if new_name:
                    channel_info = create_channel(new_name, new_desc)
                    st.session_state.current_channel = channel_info["name"]
                    st.session_state.show_create_channel = False
                    st.success(f"✅ 채널 '{new_name}' 생성됨")
                    st.rerun()
                else:
                    st.error("이름을 입력하세요.")

        with col2:
            if st.button("취소", key="cancel_channel_btn"):
                st.session_state.show_create_channel = False
                st.rerun()


def _render_create_video_form(channel_name: str):
    """새 영상 생성 폼"""
    with st.expander(f"➕ 새 영상 생성 ({channel_name})", expanded=True):
        new_name = st.text_input(
            "영상 폴더명",
            placeholder="예: 사우디왕가이야기",
            key="new_video_name"
        )
        new_title = st.text_input(
            "영상 제목",
            placeholder="예: 사우디 왕가의 비밀",
            key="new_video_title"
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("생성", type="primary", key="create_video_btn"):
                if new_name:
                    video_info = create_video(channel_name, new_name, new_title)
                    set_current_selection(channel_name, video_info["name"])
                    st.session_state.show_create_video = False
                    st.success(f"✅ 영상 '{new_name}' 생성됨")
                    st.rerun()
                else:
                    st.error("이름을 입력하세요.")

        with col2:
            if st.button("취소", key="cancel_video_btn"):
                st.session_state.show_create_video = False
                st.rerun()


# ============================================================
# 기타 유틸리티 (하위 호환)
# ============================================================

def render_project_info():
    """
    현재 프로젝트 정보를 메인 영역에 표시 (하위 호환)
    """
    config = get_current_project_config()
    channel = get_current_channel()
    video = get_current_video()

    if config:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("채널", channel or "N/A")
        with col2:
            st.metric("영상", config.get("title", video) or "N/A")
        with col3:
            st.metric("현재 단계", f"{config.get('current_step', 1)}/7")
        with col4:
            status = config.get("status", "in_progress")
            st.metric("상태", PROJECT_STATUS.get(status, status))


def render_workflow_progress():
    """
    워크플로우 진행 상황 표시 (하위 호환)
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
