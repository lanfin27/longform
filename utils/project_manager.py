"""
프로젝트-영상 계층 구조 관리 모듈 v2.4

⚠️ 핵심: 2단계 계층 구조
- 프로젝트(채널): data/projects/{project_name}/
- 영상: data/projects/{project_name}/videos/{video_name}/

⚠️ 하위 호환성:
- st.session_state.current_project_path는 영상 경로를 가리킴
- 기존 코드에서 project_path를 사용하던 것이 그대로 작동

v2.4 업데이트:
- LAST_SESSION_FILE 경로 수정: 상대 경로 → 절대 경로 (DATA_DIR 기반)
- 마지막 세션 복원 안정성 개선

v2.3 업데이트:
- 마지막 작업 채널/영상 자동 저장 및 복원
- save_last_session() / load_last_session() 함수 추가
- 앱 시작 시 마지막 세션 자동 복원

v2.2 업데이트:
- 영상 변경 시 영상별 세션 데이터 자동 초기화
- check_video_changed() 함수 추가
- clear_video_session_data() 함수 추가

사용법:
    from utils.project_manager import (
        ensure_project_selected,
        get_current_project,
        render_project_sidebar,
        # 새 함수들
        get_current_channel,
        get_current_video,
        check_video_changed,          # v2.2
        clear_video_session_data,     # v2.2
        save_last_session,            # v2.3
        load_last_session,            # v2.3
    )

    # 페이지 시작 시
    render_project_sidebar()
    if not ensure_project_selected():
        st.stop()

    # 현재 작업 경로 (= 영상 경로)
    project_path = get_current_project()

    # 영상 변경 감지 (v2.2)
    if check_video_changed():
        st.info("영상이 변경되었습니다. 데이터를 다시 로드합니다.")
"""
import streamlit as st
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import PROJECTS_DIR, DATA_DIR
from config.constants import PROJECT_STATUS, WORKFLOW_STEPS


# ============================================================
# 마지막 세션 저장/복원 (v2.3)
# ============================================================

LAST_SESSION_FILE = DATA_DIR / ".last_session.json"


def save_last_session(channel: str, video: str) -> bool:
    """
    마지막 작업 세션 정보 저장

    Args:
        channel: 채널명 (예: "경제맥락")
        video: 영상명 (예: "환율급등")

    Returns:
        저장 성공 여부
    """
    if not channel or not video:
        return False

    try:
        LAST_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

        session_data = {
            "last_channel": channel,
            "last_video": video,
            "last_updated": datetime.now().isoformat()
        }

        with open(LAST_SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

        print(f"[ProjectManager] 💾 마지막 세션 저장: {channel}/{video}")
        return True

    except Exception as e:
        print(f"[ProjectManager] ⚠️ 마지막 세션 저장 실패: {e}")
        return False


def load_last_session() -> Tuple[Optional[str], Optional[str]]:
    """
    마지막 작업 세션 정보 로드

    Returns:
        (channel, video) 튜플. 없거나 오류 시 (None, None)
    """
    if not LAST_SESSION_FILE.exists():
        return None, None

    try:
        with open(LAST_SESSION_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        channel = data.get("last_channel")
        video = data.get("last_video")

        if channel and video:
            print(f"[ProjectManager] 📂 마지막 세션 로드: {channel}/{video}")
            return channel, video

        return None, None

    except Exception as e:
        print(f"[ProjectManager] ⚠️ 마지막 세션 로드 실패: {e}")
        return None, None


def _validate_project_exists(channel: str, video: str) -> bool:
    """프로젝트(채널/영상)가 실제로 존재하는지 확인"""
    if not channel or not video:
        return False

    video_path = PROJECTS_DIR / channel / "videos" / video
    return video_path.exists()


# ============================================================
# 캐싱된 로드 함수
# ============================================================

@st.cache_data(ttl=300, show_spinner=False, max_entries=50)
def _load_channel_config_cached(config_path_str: str, _mtime: float) -> Optional[Dict]:
    """채널 설정 로드 (캐싱) - mtime으로 자동 무효화"""
    try:
        with open(config_path_str, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


@st.cache_data(ttl=60, show_spinner=False, max_entries=20)
def _list_channels_cached(_projects_dir_mtime: float) -> List[Dict]:
    """
    채널 목록 조회 (캐싱) - projects 폴더 변경 시 무효화

    Note: 60초 TTL로 자주 갱신되어 새 채널/영상 반영
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
                "video_count": _count_videos_impl(item),
                "is_new_structure": (item / "videos").exists()
            }

            # 설정 파일이 있으면 추가 정보 로드
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
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


def _count_videos_impl(channel_path: Path) -> int:
    """채널 내 영상 수 (내부 구현)"""
    videos_path = channel_path / "videos"
    if not videos_path.exists():
        has_data = any([
            (channel_path / "script.txt").exists(),
            (channel_path / "script.srt").exists(),
            (channel_path / "analysis").exists(),
        ])
        return 1 if has_data else 0
    return len([d for d in videos_path.iterdir() if d.is_dir() and not d.name.startswith('.')])


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

    v2.3: 마지막 세션 자동 복원 추가
    """
    # ⭐ v2.3: 마지막 세션 복원 (최초 1회만)
    _restore_last_session = False
    if "_last_session_restored" not in st.session_state:
        st.session_state._last_session_restored = False
        _restore_last_session = True

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

    # 삭제 다이얼로그 상태 (v2.1)
    if "show_delete_channel_dialog" not in st.session_state:
        st.session_state.show_delete_channel_dialog = False
    if "show_delete_video_dialog" not in st.session_state:
        st.session_state.show_delete_video_dialog = False

    # ⭐ v2.3: 마지막 세션 복원 수행
    if _restore_last_session and not st.session_state._last_session_restored:
        last_channel, last_video = load_last_session()

        if last_channel and last_video:
            if _validate_project_exists(last_channel, last_video):
                st.session_state.current_channel = last_channel
                st.session_state.current_video = last_video
                st.session_state.current_project_id = f"{last_channel}/{last_video}"

                video_path = PROJECTS_DIR / last_channel / "videos" / last_video
                st.session_state.current_project_path = str(video_path)
                st.session_state.current_project_name = last_video

                print(f"[ProjectManager] ✅ 마지막 세션 복원 완료: {last_channel}/{last_video}")
            else:
                print(f"[ProjectManager] ⚠️ 마지막 세션 프로젝트 없음, 복원 스킵: {last_channel}/{last_video}")

        st.session_state._last_session_restored = True


# ============================================================
# 채널(프로젝트) 관리
# ============================================================

def list_channels() -> List[Dict]:
    """
    채널(프로젝트) 목록 반환 (캐싱 적용)

    Returns:
        채널 정보 딕셔너리 리스트
    """
    if not PROJECTS_DIR.exists():
        return []

    # PROJECTS_DIR의 수정 시간으로 캐시 무효화
    try:
        mtime = PROJECTS_DIR.stat().st_mtime
    except:
        mtime = 0

    return _list_channels_cached(_projects_dir_mtime=mtime)


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
    """채널 설정 로드 (캐싱 적용)"""
    config_path = PROJECTS_DIR / channel_name / "project_config.json"
    if config_path.exists():
        try:
            mtime = config_path.stat().st_mtime
            return _load_channel_config_cached(str(config_path), _mtime=mtime)
        except:
            pass
    return None


def _count_videos(channel_path: Path) -> int:
    """채널 내 영상 수 (래퍼 함수)"""
    return _count_videos_impl(channel_path)


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
    ⚠️ v2.2: 영상 변경 시 영상별 세션 데이터 자동 초기화
    ⚠️ v2.3: 마지막 세션 자동 저장 추가
    """
    # 영상 변경 감지
    old_video = st.session_state.get("current_video")
    old_channel = st.session_state.get("current_channel")

    video_changed = (old_channel != channel_name or old_video != video_name)

    if video_changed and (old_video is not None or old_channel is not None):
        # 영상이 변경되었으면 영상별 세션 데이터 초기화
        _clear_video_specific_session_data()
        print(f"[ProjectManager] 🔄 영상 변경 감지: {old_channel}/{old_video} → {channel_name}/{video_name}")
        print(f"[ProjectManager] ✅ 영상별 세션 데이터 초기화 완료")

    video_path = get_video_path(channel_name, video_name)

    st.session_state.current_channel = channel_name
    st.session_state.current_video = video_name

    # ⚠️ 하위 호환: current_project_path = video_path
    st.session_state.current_project_path = str(video_path)
    st.session_state.current_project_id = f"{channel_name}/{video_name}"
    st.session_state.current_project_name = video_name

    # 영상 변경 플래그 설정 (페이지에서 참조 가능)
    if video_changed:
        st.session_state._video_just_changed = True

    # ⭐ v2.3: 마지막 세션 저장 (변경되었을 때만)
    if video_changed or not LAST_SESSION_FILE.exists():
        save_last_session(channel_name, video_name)


def _clear_video_specific_session_data():
    """
    영상 변경 시 초기화해야 할 세션 데이터 클리어

    ⚠️ 영상별로 분리되어야 하는 데이터만 초기화
    ⚠️ 설정, 스타일, API 키 등 공유 데이터는 유지
    """
    # 씬 캐시 클리어 (scene_character_loader)
    try:
        from utils.scene_character_loader import clear_scene_cache
        clear_scene_cache()  # 모든 씬 캐시 클리어
        print("[ProjectManager] 씬 캐시 클리어 완료")
    except ImportError:
        pass
    except Exception as e:
        print(f"[ProjectManager] 씬 캐시 클리어 실패: {e}")

    # v2.3: 갤러리 이미지 캐시 클리어 (영상별 이미지 분리)
    try:
        # st.cache_data 캐시 무효화를 위해 플래그 설정
        st.session_state._gallery_cache_needs_clear = True
        print("[ProjectManager] 갤러리 캐시 클리어 플래그 설정")
    except Exception as e:
        print(f"[ProjectManager] 갤러리 캐시 클리어 플래그 설정 실패: {e}")

    # 영상별 데이터 키 목록 (직접 매칭)
    VIDEO_SPECIFIC_KEYS = [
        # 씬 데이터
        "scenes",
        "filtered_scenes",
        "scene_data",
        "analysis_result",
        "analysis_scenes",

        # 이미지 데이터
        "images",
        "backgrounds",
        "characters",
        "composites",
        "generated_images",
        "gallery_images",

        # 스토리보드
        "storyboard_data",
        "storyboard_scenes",

        # 파이프라인 상태
        "pipeline_state",

        # 캐릭터 관련
        "rep_char_manager",
        "batch_selected_scenes",

        # 프롬프트 관련
        "scene_prompts",
        "image_prompts",
    ]

    # 영상별 데이터 키 패턴 (부분 매칭)
    VIDEO_SPECIFIC_PATTERNS = [
        "scene_",        # scene_1, scene_data_*, 등
        "image_",        # image_data_*, 등
        "background_",   # background_*, 등
        "character_",    # character_*, 등
        "composite_",    # composite_*, 등
        "prompt_",       # prompt_*, 등
        "_scenes",       # filtered_scenes, 등
        "_images",       # gallery_images, 등
    ]

    # 유지해야 할 키 패턴 (설정, 스타일, API 등)
    KEEP_PATTERNS = [
        "setting",
        "config",
        "style",
        "template",
        "api_",
        "cookie",
        "seed_lock",     # 시드 잠금은 사용자 선택에 따라
        "show_",         # UI 상태 (다이얼로그 등)
        "current_",      # 현재 선택 상태
    ]

    cleared_count = 0
    cleared_keys = []

    # 직접 매칭 키 삭제
    for key in VIDEO_SPECIFIC_KEYS:
        if key in st.session_state:
            del st.session_state[key]
            cleared_count += 1
            cleared_keys.append(key)

    # 패턴 매칭 키 삭제
    keys_to_delete = []
    for key in list(st.session_state.keys()):
        # 유지해야 할 키인지 확인
        if any(keep in key.lower() for keep in KEEP_PATTERNS):
            continue

        # 삭제해야 할 패턴인지 확인
        if any(pattern in key.lower() for pattern in VIDEO_SPECIFIC_PATTERNS):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        if key in st.session_state:
            del st.session_state[key]
            cleared_count += 1
            if len(cleared_keys) < 20:  # 로그용으로 처음 20개만
                cleared_keys.append(key)

    if cleared_count > 0:
        print(f"[ProjectManager] 초기화된 세션 키: {cleared_count}개")
        print(f"[ProjectManager] 예시: {cleared_keys[:10]}...")


def get_current_channel() -> Optional[str]:
    """현재 선택된 채널 이름"""
    init_session_state()
    return st.session_state.current_channel


def get_current_video() -> Optional[str]:
    """현재 선택된 영상 이름"""
    init_session_state()
    return st.session_state.current_video


# ============================================================
# 영상 변경 감지 및 데이터 관리 (v2.2)
# ============================================================

def check_video_changed() -> bool:
    """
    영상이 방금 변경되었는지 확인

    사용법:
        if check_video_changed():
            st.info("영상이 변경되었습니다.")
            # 데이터 다시 로드...

    Returns:
        True if video just changed, False otherwise

    Note:
        이 함수를 호출하면 플래그가 자동으로 리셋됨
    """
    if st.session_state.get("_video_just_changed", False):
        st.session_state._video_just_changed = False
        return True
    return False


def clear_video_session_data():
    """
    수동으로 영상별 세션 데이터 초기화

    사용법:
        from utils.project_manager import clear_video_session_data
        clear_video_session_data()

    Note:
        영상 선택이 변경되면 자동으로 호출됨.
        강제로 데이터를 다시 로드해야 할 때 사용.
    """
    _clear_video_specific_session_data()


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
# 삭제 기능 (v2.1)
# ============================================================

def get_folder_size(path: Path) -> int:
    """
    폴더 크기 계산 (바이트)

    Args:
        path: 폴더 경로

    Returns:
        총 크기 (바이트)
    """
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    except Exception:
        pass
    return total


def format_size(size_bytes: int) -> str:
    """바이트를 읽기 쉬운 형식으로 변환"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_video_info_for_delete(channel_name: str, video_name: str) -> Dict:
    """
    영상 삭제 전 정보 조회

    Args:
        channel_name: 채널명
        video_name: 영상명

    Returns:
        {
            "exists": bool,
            "path": str,
            "size": int,
            "size_formatted": str,
            "file_count": int,
            "folder_count": int
        }
    """
    video_path = get_video_path(channel_name, video_name)

    if not video_path.exists():
        return {"exists": False}

    # 파일/폴더 수 계산
    file_count = 0
    folder_count = 0
    for item in video_path.rglob("*"):
        if item.is_file():
            file_count += 1
        elif item.is_dir():
            folder_count += 1

    size = get_folder_size(video_path)

    return {
        "exists": True,
        "path": str(video_path),
        "size": size,
        "size_formatted": format_size(size),
        "file_count": file_count,
        "folder_count": folder_count
    }


def get_channel_info_for_delete(channel_name: str) -> Dict:
    """
    채널 삭제 전 정보 조회

    Args:
        channel_name: 채널명

    Returns:
        {
            "exists": bool,
            "path": str,
            "size": int,
            "size_formatted": str,
            "video_count": int,
            "videos": List[str]
        }
    """
    channel_path = PROJECTS_DIR / channel_name

    if not channel_path.exists():
        return {"exists": False}

    # 영상 목록
    videos_dir = channel_path / "videos"
    video_names = []
    if videos_dir.exists():
        video_names = [d.name for d in videos_dir.iterdir() if d.is_dir()]

    size = get_folder_size(channel_path)

    return {
        "exists": True,
        "path": str(channel_path),
        "size": size,
        "size_formatted": format_size(size),
        "video_count": len(video_names),
        "videos": video_names
    }


def _clear_project_caches():
    """프로젝트 관련 캐시 모두 클리어"""
    # Streamlit 캐시 클리어
    try:
        _load_channel_config_cached.clear()
    except Exception:
        pass

    try:
        _list_channels_cached.clear()
    except Exception:
        pass

    try:
        _list_videos_cached.clear()
    except Exception:
        pass


def _clear_session_state_for_channel(channel_name: str):
    """채널 삭제 시 세션 상태 정리"""
    if st.session_state.get("current_channel") == channel_name:
        st.session_state.current_channel = None
        st.session_state.current_video = None
        st.session_state.current_project_id = None
        st.session_state.current_project_path = None
        st.session_state.current_project_name = None


def _clear_session_state_for_video(channel_name: str, video_name: str):
    """영상 삭제 시 세션 상태 정리"""
    if (st.session_state.get("current_channel") == channel_name and
        st.session_state.get("current_video") == video_name):
        st.session_state.current_channel = channel_name  # 채널은 유지
        st.session_state.current_video = None
        st.session_state.current_project_id = None
        st.session_state.current_project_path = None
        st.session_state.current_project_name = None


def delete_video(channel_name: str, video_name: str, move_to_trash: bool = True) -> Dict:
    """
    영상 삭제

    Args:
        channel_name: 채널명
        video_name: 영상명
        move_to_trash: True면 휴지통으로 이동, False면 완전 삭제

    Returns:
        {
            "success": bool,
            "message": str,
            "trash_path": str (휴지통 이동 시)
        }
    """
    video_path = get_video_path(channel_name, video_name)

    if not video_path.exists():
        return {
            "success": False,
            "message": f"영상을 찾을 수 없습니다: {video_name}"
        }

    try:
        if move_to_trash:
            # 휴지통 폴더 생성
            trash_dir = PROJECTS_DIR / "_trash"
            trash_dir.mkdir(exist_ok=True)

            # 고유 이름 생성 (타임스탬프 포함)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trash_name = f"{channel_name}_{video_name}_{timestamp}"
            trash_path = trash_dir / trash_name

            # 이동
            shutil.move(str(video_path), str(trash_path))

            # 세션 상태 정리
            _clear_session_state_for_video(channel_name, video_name)

            # 캐시 클리어
            _clear_project_caches()

            return {
                "success": True,
                "message": f"영상이 휴지통으로 이동되었습니다: {video_name}",
                "trash_path": str(trash_path)
            }
        else:
            # 완전 삭제
            shutil.rmtree(video_path)

            # 세션 상태 정리
            _clear_session_state_for_video(channel_name, video_name)

            # 캐시 클리어
            _clear_project_caches()

            return {
                "success": True,
                "message": f"영상이 완전히 삭제되었습니다: {video_name}"
            }

    except PermissionError:
        return {
            "success": False,
            "message": "권한 오류: 일부 파일이 사용 중입니다. 파일을 닫고 다시 시도하세요."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"삭제 실패: {str(e)}"
        }


def delete_channel(channel_name: str, move_to_trash: bool = True) -> Dict:
    """
    채널(프로젝트) 전체 삭제

    Args:
        channel_name: 채널명
        move_to_trash: True면 휴지통으로 이동, False면 완전 삭제

    Returns:
        {
            "success": bool,
            "message": str,
            "trash_path": str (휴지통 이동 시),
            "deleted_videos": int
        }
    """
    channel_path = PROJECTS_DIR / channel_name

    if not channel_path.exists():
        return {
            "success": False,
            "message": f"채널을 찾을 수 없습니다: {channel_name}"
        }

    # 영상 수 확인
    videos_dir = channel_path / "videos"
    video_count = 0
    if videos_dir.exists():
        video_count = len([d for d in videos_dir.iterdir() if d.is_dir()])

    try:
        if move_to_trash:
            # 휴지통 폴더 생성
            trash_dir = PROJECTS_DIR / "_trash"
            trash_dir.mkdir(exist_ok=True)

            # 고유 이름 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trash_name = f"channel_{channel_name}_{timestamp}"
            trash_path = trash_dir / trash_name

            # 이동
            shutil.move(str(channel_path), str(trash_path))

            # 세션 상태 정리
            _clear_session_state_for_channel(channel_name)

            # 캐시 클리어
            _clear_project_caches()

            return {
                "success": True,
                "message": f"채널이 휴지통으로 이동되었습니다: {channel_name}",
                "trash_path": str(trash_path),
                "deleted_videos": video_count
            }
        else:
            # 완전 삭제
            shutil.rmtree(channel_path)

            # 세션 상태 정리
            _clear_session_state_for_channel(channel_name)

            # 캐시 클리어
            _clear_project_caches()

            return {
                "success": True,
                "message": f"채널이 완전히 삭제되었습니다: {channel_name}",
                "deleted_videos": video_count
            }

    except PermissionError:
        return {
            "success": False,
            "message": "권한 오류: 일부 파일이 사용 중입니다. 파일을 닫고 다시 시도하세요."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"삭제 실패: {str(e)}"
        }


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

        # 채널 선택 + 삭제 버튼
        ch_col1, ch_col2 = st.columns([5, 1])

        with ch_col1:
            selected_channel = st.selectbox(
                "🎬 채널 선택",
                channel_names,
                index=current_index,
                format_func=lambda x: channel_display_names.get(x, x),
                key="channel_selector",
                help="유튜브 채널 또는 프로젝트 그룹"
            )

        with ch_col2:
            st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
            if st.button("🗑️", key="btn_delete_channel", help="채널 삭제"):
                st.session_state.show_delete_channel_dialog = True

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

            # 영상 선택 드롭다운 (제목 표시) + 삭제 버튼
            video_options = {v["name"]: v.get("title", v["name"]) for v in videos}

            vid_col1, vid_col2 = st.columns([5, 1])

            with vid_col1:
                selected_video = st.selectbox(
                    "📹 영상 선택",
                    video_names,
                    index=video_index,
                    format_func=lambda x: video_options.get(x, x),
                    key="video_selector"
                )

            with vid_col2:
                st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
                if st.button("🗑️", key="btn_delete_video", help="영상 삭제"):
                    st.session_state.show_delete_video_dialog = True

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

        # ============================================================
        # 삭제 다이얼로그 (v2.1)
        # ============================================================

        # 채널 삭제 다이얼로그
        if st.session_state.get("show_delete_channel_dialog") and selected_channel:
            _render_delete_channel_dialog(selected_channel)

        # 영상 삭제 다이얼로그
        if st.session_state.get("show_delete_video_dialog") and selected_channel and video_names:
            selected_video_for_delete = st.session_state.get("current_video") or (video_names[0] if video_names else None)
            if selected_video_for_delete:
                _render_delete_video_dialog(selected_channel, selected_video_for_delete)

        # ============================================================
        # 🚀 외부 도구 섹션 (v3.20)
        # ============================================================
        _render_external_tools_sidebar()


def _render_external_tools_sidebar():
    """사이드바에 외부 도구 섹션 렌더링"""
    import time
    from utils.external_launcher import (
        EXTERNAL_PROJECTS,
        get_project_status,
        launch_project,
        open_folder,
        open_in_browser
    )

    st.divider()
    st.markdown("### 🚀 외부 도구")

    for project_id, project in EXTERNAL_PROJECTS.items():
        status = get_project_status(project_id)

        # 상태 아이콘
        if project["type"] == "streamlit":
            status_icon = "🟢" if status.get("running") else "⚪"
        else:
            status_icon = "📦"

        # 프로젝트 버튼
        col1, col2 = st.columns([4, 1])

        with col1:
            btn_label = f"{project['icon']} {project['name']} {status_icon}"

            if st.button(
                btn_label,
                key=f"ext_launch_{project_id}",
                use_container_width=True,
                help=project.get("description", "")
            ):
                if project["type"] == "streamlit":
                    if status.get("running"):
                        # 이미 실행 중 → 브라우저 열기
                        open_in_browser(status["url"])
                        st.toast(f"✅ {project['name']} 열림")
                    else:
                        # 실행 시작
                        with st.spinner(f"{project['name']} 시작 중..."):
                            result = launch_project(project_id)

                        if result.get("success"):
                            st.toast(f"✅ {result['message']}")
                            time.sleep(2)
                            if result.get("url"):
                                open_in_browser(result["url"])
                            st.rerun()
                        elif result.get("already_running"):
                            open_in_browser(result["url"])
                            st.toast(f"✅ {project['name']} 열림")
                        else:
                            st.error(f"❌ {result['message']}")
                else:
                    # 브라우저 확장 프로그램 등
                    result = launch_project(project_id)
                    if result.get("success"):
                        st.toast(f"✅ {result['message']}")
                    else:
                        st.error(f"❌ {result['message']}")

        with col2:
            if st.button(
                "📂",
                key=f"ext_folder_{project_id}",
                help="폴더 열기"
            ):
                if open_folder(project["path"]):
                    st.toast("📂 폴더 열림")


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


def _render_delete_video_dialog(channel_name: str, video_name: str):
    """영상 삭제 확인 다이얼로그"""
    with st.expander("🗑️ 영상 삭제", expanded=True):
        # 영상 정보 조회
        info = get_video_info_for_delete(channel_name, video_name)

        if not info.get("exists"):
            st.error("영상을 찾을 수 없습니다.")
            if st.button("닫기", key="close_delete_video_dialog"):
                st.session_state.show_delete_video_dialog = False
                st.rerun()
            return

        # 경고 메시지
        st.warning(f"**'{video_name}'** 영상을 삭제하시겠습니까?")

        # 삭제될 내용 표시
        st.markdown(f"""
        **삭제될 내용:**
        - 📁 파일 수: **{info['file_count']}개**
        - 📂 폴더 수: **{info['folder_count']}개**
        - 💾 용량: **{info['size_formatted']}**
        """)

        # 삭제 옵션
        move_to_trash = st.checkbox(
            "휴지통으로 이동 (복구 가능)",
            value=True,
            key="delete_video_to_trash"
        )

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            if st.button("🗑️ 삭제", type="primary", key="confirm_delete_video"):
                result = delete_video(channel_name, video_name, move_to_trash)

                if result["success"]:
                    st.success(result["message"])
                    st.session_state.show_delete_video_dialog = False
                    st.rerun()
                else:
                    st.error(result["message"])

        with col2:
            if st.button("취소", key="cancel_delete_video"):
                st.session_state.show_delete_video_dialog = False
                st.rerun()


def _render_delete_channel_dialog(channel_name: str):
    """채널 삭제 확인 다이얼로그"""
    with st.expander("🗑️ 채널 삭제", expanded=True):
        # 채널 정보 조회
        info = get_channel_info_for_delete(channel_name)

        if not info.get("exists"):
            st.error("채널을 찾을 수 없습니다.")
            if st.button("닫기", key="close_delete_channel_dialog"):
                st.session_state.show_delete_channel_dialog = False
                st.rerun()
            return

        # 경고 메시지
        if info["video_count"] > 0:
            st.error(f"⚠️ **주의:** 채널 **'{channel_name}'**에 **{info['video_count']}개**의 영상이 있습니다!")
        else:
            st.warning(f"**'{channel_name}'** 채널을 삭제하시겠습니까?")

        # 삭제될 내용 표시
        st.markdown(f"""
        **삭제될 내용:**
        - 📹 영상 수: **{info['video_count']}개**
        - 💾 총 용량: **{info['size_formatted']}**
        """)

        # 영상 목록 표시
        if info["videos"]:
            with st.expander(f"포함된 영상 목록 ({len(info['videos'])}개)"):
                for v in info["videos"]:
                    st.text(f"• {v}")

        # 삭제 옵션
        move_to_trash = st.checkbox(
            "휴지통으로 이동 (복구 가능)",
            value=True,
            key="delete_channel_to_trash"
        )

        # 확인 입력 (영상이 있는 경우)
        confirm_text = ""
        if info["video_count"] > 0:
            st.markdown("---")
            st.markdown(f"삭제를 확인하려면 채널 이름 **`{channel_name}`**을 입력하세요:")
            confirm_text = st.text_input(
                "채널 이름 입력",
                key="confirm_channel_name",
                label_visibility="collapsed"
            )

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            # 확인 필요 여부 체크
            can_delete = (info["video_count"] == 0) or (confirm_text == channel_name)
            btn_disabled = not can_delete

            if st.button("🗑️ 삭제", type="primary", key="confirm_delete_channel", disabled=btn_disabled):
                result = delete_channel(channel_name, move_to_trash)

                if result["success"]:
                    st.success(result["message"])
                    if result.get("deleted_videos", 0) > 0:
                        st.info(f"삭제된 영상: {result['deleted_videos']}개")
                    st.session_state.show_delete_channel_dialog = False
                    st.rerun()
                else:
                    st.error(result["message"])

        with col2:
            if st.button("취소", key="cancel_delete_channel"):
                st.session_state.show_delete_channel_dialog = False
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
