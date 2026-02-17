"""
3.6단계: 캐릭터 관리

캐릭터 생성, 편집, 배치 생성 기능
"""
import streamlit as st
import json
import time
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    render_project_sidebar,
    update_project_step
)
from utils.api_helper import require_api_key, show_api_status_sidebar
from core.character.character_manager import CharacterManager, Character
from utils.progress_ui import render_api_selector, StreamlitProgressUI
from core.api.api_manager import get_api_manager
from utils.style_manager import get_style_manager, get_styles_by_segment, get_default_style
from components.style_selector import style_radio_selector, get_selected_style
from utils.pose_manager import PoseManager, get_pose_manager
from utils.scene_character_loader import (
    load_scenes_data,
    get_character_appearances,
    get_all_characters_from_scenes,
    build_character_scene_map,
    sync_character_appearance_scenes
)
from components.image_viewer import (
    render_lightbox_container,
    render_lightbox_image,
    clickable_image,
    # v3.0: Streamlit 네이티브 확대 기능 (JavaScript 의존성 제거)
    render_clickable_thumbnail,
    render_image_zoom_modal,
    render_zoomable_image,
    DIALOG_AVAILABLE
)

# 사용자 설정 (마지막 선택값 기억)
from utils.user_preferences import (
    get_last_image_api,
    set_last_image_api,
    get_last_image_model,
    set_last_image_model,
    get_last_concurrent_count,
    set_last_concurrent_count,
    # v3.40: 채널-영상별 배치 설정 저장
    get_character_batch_settings,
    save_character_batch_settings,
    get_character_batch_setting,
    update_character_batch_setting
)

# 대표 캐릭터 시스템
from utils.representative_character import (
    RepresentativeCharacter,
    RepresentativeCharacterManager,
    SceneCharacterAction,
    STYLE_PRESETS,
    BASE_IMAGE_TYPES,
    get_rep_char_manager
)

# v1.1: 시드 잠금 기능
from utils.imagefx_ui_components import (
    render_seed_lock_options,
    get_seed_for_generation,
    update_locked_seed_from_result
)

# v3.31: 유명인 일반화 필터
from utils.prominent_people_sanitizer import (
    sanitize_characters_batch,
    preview_character_sanitization,
    needs_sanitization_quick_check,
    get_recommended_model as get_sanitizer_recommended_model,
    get_available_sanitizer_models,
    get_sanitizer_models_for_ui,
    SANITIZE_PROMPT_TEMPLATE
)

# 대표 캐릭터 라이브러리 (다중 캐릭터 관리)
from utils.rep_char_library import (
    get_rep_char_library,
    get_selected_rep_char,
    get_selected_rep_char_id
)
from utils.character_action_generator import (
    CharacterActionGenerator,
    get_available_models as get_action_ai_models
)

# v3.35: 씬별 캐릭터 갤러리
try:
    from utils.character_gallery import CharacterGalleryManager, get_gallery_manager
    from components.scene_character_gallery import render_scene_character_gallery
    GALLERY_AVAILABLE = True
except ImportError as e:
    print(f"[캐릭터 관리] 갤러리 모듈 로드 실패: {e}")
    GALLERY_AVAILABLE = False

# 페이지 설정
st.set_page_config(
    page_title="캐릭터 관리",
    page_icon="👤",
    layout="wide"
)

render_project_sidebar()
show_api_status_sidebar()

if not ensure_project_selected():
    st.stop()

project_path = get_current_project()

# ═══════════════════════════════════════════════════════════════════════════════
# v3.40: 채널-영상 정보 추출 (배치 설정 저장용)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_channel_video_from_path(path: Path) -> tuple:
    """
    프로젝트 경로에서 채널과 영상 이름 추출

    경로 형식: data/projects/{timestamp}_{channel}/videos/{video_name}

    Returns:
        (channel, video) 튜플
    """
    try:
        parts = path.parts
        # videos 폴더 위치 찾기
        if 'videos' in parts:
            videos_idx = parts.index('videos')
            # channel: projects 바로 뒤 폴더에서 타임스탬프 제거
            if videos_idx >= 2:
                project_folder = parts[videos_idx - 1]  # e.g., "20251214_144057_시니어"
                # 타임스탬프 패턴 제거 (YYYYMMDD_HHMMSS_)
                if len(project_folder) > 16 and project_folder[8] == '_' and project_folder[15] == '_':
                    channel = project_folder[16:]  # "시니어"
                else:
                    channel = project_folder

            # video: videos 폴더 바로 뒤
            if videos_idx + 1 < len(parts):
                video = parts[videos_idx + 1]
            else:
                video = project_folder

            return channel, video
    except Exception as e:
        print(f"[캐릭터 관리] 경로 파싱 오류: {e}")

    # 폴백: 폴더 이름 사용
    return path.name, path.name

# 현재 채널-영상 정보
_current_channel, _current_video = _extract_channel_video_from_path(Path(project_path))
print(f"[캐릭터 관리] 채널: {_current_channel}, 영상: {_current_video}")

# 저장된 배치 설정 로드
_saved_batch_settings = get_character_batch_settings(_current_channel, _current_video)
if _saved_batch_settings:
    print(f"[캐릭터 관리] 저장된 설정 로드: {list(_saved_batch_settings.keys())}")


# ═══════════════════════════════════════════════════════════════════════════════
# v3.32: 캐릭터 속성 안전 접근 헬퍼 함수
# ═══════════════════════════════════════════════════════════════════════════════

def get_character_attr(char, attr_name: str, default: str = '') -> str:
    """
    Character 객체에서 속성을 안전하게 가져오기
    dict와 클래스 객체 모두 지원
    """
    if char is None:
        return default
    if isinstance(char, dict):
        return char.get(attr_name, default) or default
    else:
        return getattr(char, attr_name, default) or default


def get_character_name(char) -> str:
    """캐릭터 이름 안전하게 가져오기"""
    return get_character_attr(char, 'name', '')


def get_character_visual_prompt(char) -> str:
    """
    캐릭터 비주얼 프롬프트 안전하게 가져오기
    여러 가능한 속성명을 시도: character_prompt, description, appearance, visual_prompt
    """
    for attr in ['character_prompt', 'description', 'appearance', 'visual_prompt', 'prompt']:
        value = get_character_attr(char, attr, '')
        if value:
            return value
    return ''


# ═══════════════════════════════════════════════════════════════════════════════
# v3.36: 씬 데이터에서 캐릭터 추출 헬퍼 함수
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_characters_from_scenes(scenes_data: list) -> list:
    """
    씬 데이터에서 캐릭터 정보 추출

    다양한 필드명 지원:
    - characters, character_names, character_list
    - character_prompt_en, character_prompt_ko
    - 등장_캐릭터, 캐릭터

    Args:
        scenes_data: 씬 데이터 리스트 (scenes.json 내용)

    Returns:
        추출된 캐릭터 정보 리스트
    """
    # 캐릭터 이름 → 정보 매핑 (중복 제거용)
    character_map = {}

    for scene in scenes_data:
        scene_num = scene.get('scene_number', scene.get('scene_id', 0))
        if isinstance(scene_num, str) and scene_num.isdigit():
            scene_num = int(scene_num)

        # ─────────────────────────────────────────────────────────
        # 방법 1: characters 필드 (리스트)
        # ─────────────────────────────────────────────────────────
        characters = scene.get('characters', [])

        if isinstance(characters, list):
            for char in characters:
                if isinstance(char, str):
                    char_name = char.strip()
                    char_prompt = ''
                elif isinstance(char, dict):
                    char_name = char.get('name', '') or char.get('이름', '')
                    char_prompt = char.get('visual_prompt', '') or char.get('character_prompt', '')
                else:
                    continue

                if char_name and char_name.lower() not in ['n/a', 'none', '없음', '', 'null']:
                    if char_name not in character_map:
                        character_map[char_name] = {
                            'name': char_name,
                            'name_ko': char_name,
                            'role': '등장인물',
                            'description': '',
                            'visual_prompt': char_prompt,
                            'appearance_scenes': []
                        }
                    if scene_num and scene_num not in character_map[char_name]['appearance_scenes']:
                        character_map[char_name]['appearance_scenes'].append(scene_num)
                    if char_prompt and not character_map[char_name]['visual_prompt']:
                        character_map[char_name]['visual_prompt'] = char_prompt

        # ─────────────────────────────────────────────────────────
        # 방법 2: character_names 필드 (문자열 또는 리스트)
        # ─────────────────────────────────────────────────────────
        char_names = scene.get('character_names') or scene.get('character_list') or scene.get('등장_캐릭터')

        if char_names:
            if isinstance(char_names, str):
                names = [n.strip() for n in char_names.replace(';', ',').split(',')]
            elif isinstance(char_names, list):
                names = char_names
            else:
                names = []

            for name in names:
                if name and name.lower() not in ['n/a', 'none', '없음', '', 'null']:
                    if name not in character_map:
                        character_map[name] = {
                            'name': name,
                            'name_ko': name,
                            'role': '등장인물',
                            'description': '',
                            'visual_prompt': '',
                            'appearance_scenes': []
                        }
                    if scene_num and scene_num not in character_map[name]['appearance_scenes']:
                        character_map[name]['appearance_scenes'].append(scene_num)

        # ─────────────────────────────────────────────────────────
        # 방법 3: character_prompt에서 캐릭터 이름 추출 및 visual_prompt 업데이트
        # ─────────────────────────────────────────────────────────
        char_prompt = (
            scene.get('character_prompt_en') or
            scene.get('character_prompt_ko') or
            scene.get('character_prompt') or
            scene.get('캐릭터_프롬프트') or
            ''
        )

        if char_prompt and char_prompt.lower() not in ['n/a', 'none', '없음', '', 'null']:
            # 기존 캐릭터에 프롬프트 연결
            for char_name in character_map:
                if char_name.lower() in char_prompt.lower():
                    if not character_map[char_name]['visual_prompt']:
                        character_map[char_name]['visual_prompt'] = char_prompt

    # 결과 리스트 변환
    result = list(character_map.values())

    # appearance_scenes 정렬
    for char in result:
        char['appearance_scenes'] = sorted(char['appearance_scenes'])

    # 등장 횟수 순으로 정렬 (많이 등장하는 캐릭터 먼저)
    result.sort(key=lambda x: len(x.get('appearance_scenes', [])), reverse=True)

    print(f"[캐릭터 관리] 📊 씬 데이터에서 {len(result)}개 캐릭터 추출됨")

    for char in result[:5]:  # 상위 5개만 로그
        scenes_count = len(char.get('appearance_scenes', []))
        print(f"[캐릭터 관리]    - {char['name']}: {scenes_count}개 씬 등장")

    return result


# Lightbox 컨테이너 초기화 (페이지당 한 번)
render_lightbox_container()

# v3.0: Streamlit 네이티브 이미지 확대 모달 (JavaScript 미지원 시 사용)
if not DIALOG_AVAILABLE:
    render_image_zoom_modal()

st.title("👤 3.6단계: 캐릭터 관리")
st.caption("캐릭터 생성, 편집, 배치 이미지 생성")

st.divider()

# 캐릭터 매니저 초기화
manager = CharacterManager(str(project_path))

# ⭐ 성능 최적화: 초기화 키
_CHAR_INIT_KEY = f"char_mgmt_initialized_{project_path}"


# === 자동 동기화: 세션/분석 파일에서 캐릭터 자동 가져오기 ===
def auto_sync_characters():
    """세션 또는 분석 파일에서 캐릭터 자동 동기화"""

    # 분석 파일에서 캐릭터 데이터 로드
    analysis_chars = None
    analysis_path = project_path / "analysis" / "characters.json"
    if analysis_path.exists():
        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                analysis_chars = json.load(f)
            print(f"[캐릭터 관리] 분석 파일에서 {len(analysis_chars)}명 발견")
        except Exception as e:
            print(f"[캐릭터 관리] 분석 파일 로드 실패: {e}")

    # 세션에서 캐릭터 찾기 (분석 파일 없을 경우)
    if not analysis_chars:
        for key in ["characters", "scene_characters", "extracted_characters"]:
            if key in st.session_state and st.session_state[key]:
                analysis_chars = st.session_state[key]
                print(f"[캐릭터 관리] 세션 '{key}'에서 {len(analysis_chars)}명 발견")
                break

    if not analysis_chars:
        return

    existing = manager.get_all_characters()

    if not existing:
        # 캐릭터가 없으면 새로 가져오기
        imported = manager.import_from_analysis(analysis_chars)
        if imported > 0:
            print(f"[캐릭터 관리] {imported}명 자동 가져오기 완료")
    else:
        # 🔴 v3.12: 기존 캐릭터가 있으면 등장 씬 정보 동기화
        synced = manager.sync_appearance_scenes(analysis_chars)
        if synced > 0:
            print(f"[캐릭터 관리] {synced}명 등장 씬 동기화 완료")


# ⭐ 성능 최적화: 분석 파일 변경 감지 기반 동기화
# - 최초 방문 시: 무조건 동기화
# - 재방문 시: analysis/characters.json 수정 시간이 변경된 경우에만 재동기화
_CHAR_SYNC_MTIME_KEY = f"char_sync_mtime_{project_path}"
_analysis_path_for_sync = project_path / "analysis" / "characters.json"

_need_sync = False
if not st.session_state.get(_CHAR_INIT_KEY, False):
    # 최초 방문: 무조건 동기화
    _need_sync = True
elif _analysis_path_for_sync.exists():
    # 재방문: 분석 파일 수정 시간 비교
    _current_mtime = _analysis_path_for_sync.stat().st_mtime
    _last_mtime = st.session_state.get(_CHAR_SYNC_MTIME_KEY, 0)
    if _current_mtime > _last_mtime:
        _need_sync = True
        print(f"[캐릭터 관리] 🔄 분석 파일 변경 감지 (mtime: {_last_mtime} → {_current_mtime}), 재동기화")

if _need_sync:
    auto_sync_characters()

    # === 씬-캐릭터 등장 정보 자동 동기화 (Problem 56 수정) ===
    # 씬 데이터에서 캐릭터 등장 정보를 추출하여 appearance_scenes 업데이트
    try:
        synced_count = sync_character_appearance_scenes(str(project_path))
        if synced_count > 0:
            print(f"[캐릭터 관리] ✅ {synced_count}명 캐릭터 appearance_scenes 동기화 완료")
            # CharacterManager도 다시 로드하여 반영
            manager = CharacterManager(str(project_path))
    except Exception as e:
        print(f"[캐릭터 관리] ⚠️ 씬-캐릭터 동기화 오류: {e}")

    # ⭐ 초기화 완료 플래그 + 수정 시간 저장
    st.session_state[_CHAR_INIT_KEY] = True
    if _analysis_path_for_sync.exists():
        st.session_state[_CHAR_SYNC_MTIME_KEY] = _analysis_path_for_sync.stat().st_mtime

# === 씬 분석 데이터 로드 함수 (v2.0 - 최신 파일 자동 감지) ===
from datetime import datetime


# ⭐ 성능 최적화: 씬 데이터 캐싱 (내부 함수)
@st.cache_data(ttl=60, show_spinner=False)
def _cached_load_scene_data(project_path_str: str) -> tuple:
    """씬 데이터 로드 (캐싱 적용 - 내부 구현)"""
    from pathlib import Path
    project_path_obj = Path(project_path_str)

    analysis_paths = [
        project_path_obj / "analysis" / "scenes.json",
        project_path_obj / "analysis" / "scene_analysis.json",
        project_path_obj / "analysis" / "hybrid_v5_scenes.json",
        project_path_obj / "scenes.json",
        project_path_obj / "data" / "scenes.json",
    ]

    video_name = st.session_state.get("current_video")
    if video_name:
        analysis_paths.insert(0, project_path_obj / "videos" / video_name / "analysis" / "scenes.json")
        analysis_paths.insert(1, project_path_obj / "videos" / video_name / "analysis" / "scene_analysis.json")

    latest_file = None
    latest_mtime = 0

    for path in analysis_paths:
        if path.exists():
            mtime = path.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = path

    if not latest_file:
        return [], None, None

    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            raw_scenes = data
        elif isinstance(data, dict):
            raw_scenes = data.get('scenes', data.get('data', []))
        else:
            raw_scenes = []

        mtime_str = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S")

        scenes = []
        for i, scene in enumerate(raw_scenes):
            scene_id = scene.get("scene_id", scene.get("scene_number", scene.get("id", i + 1)))
            if isinstance(scene_id, str) and scene_id.isdigit():
                scene_id = int(scene_id)

            scene_data = {
                "scene_number": scene_id,
                "scene_id": scene_id,
                "title": scene.get("title", scene.get("name", f"씬 {scene_id}")),
                "mood": scene.get("mood", scene.get("분위기", "default")),
                "description": scene.get("description", scene.get("내용", "")),
                "script_text": scene.get("script_text", scene.get("narration", "")),
                "characters": scene.get("characters", [])
            }
            scenes.append(scene_data)

        return scenes, mtime_str, latest_file.name

    except Exception as e:
        print(f"[씬 로드] ❌ 씬 분석 로드 실패: {e}")
        return [], None, None


# ⭐ v3.60: 캐릭터 데이터 캐싱 (성능 최적화)
@st.cache_data(ttl=60, show_spinner=False)
def _cached_load_characters_from_analysis(project_path_str: str) -> tuple:
    """
    분석 파일에서 캐릭터 데이터 로드 (캐싱 적용)

    Returns:
        (캐릭터 리스트, 데이터 소스 문자열)
    """
    from pathlib import Path
    project_path_obj = Path(project_path_str)

    # 1. characters.json 파일에서 로드 시도
    analysis_path = project_path_obj / "analysis" / "characters.json"
    if analysis_path.exists():
        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                file_chars = json.load(f)
            if file_chars and isinstance(file_chars, list) and len(file_chars) > 0:
                # 최초 1회만 로그 출력
                if 'char_load_logged' not in st.session_state:
                    print(f"[캐릭터 관리] ✅ 파일에서 {len(file_chars)}개 캐릭터 로드: {analysis_path}")
                    st.session_state['char_load_logged'] = True
                return file_chars, f"📁 파일: {analysis_path.name}"
        except Exception as e:
            print(f"[캐릭터 관리] ❌ 파일 로드 실패: {e}")

    # 2. characters.json 없으면 scenes.json에서 캐릭터 추출
    scenes_path = project_path_obj / "analysis" / "scenes.json"
    if scenes_path.exists():
        try:
            with open(scenes_path, "r", encoding="utf-8") as f:
                scenes_data = json.load(f)

            # 씬 데이터에서 캐릭터 추출
            extracted = _extract_characters_from_scenes(scenes_data)
            if extracted:
                if 'char_load_logged' not in st.session_state:
                    print(f"[캐릭터 관리] ✅ 씬에서 {len(extracted)}개 캐릭터 추출")
                    st.session_state['char_load_logged'] = True
                return extracted, f"🎬 씬 데이터에서 추출 ({len(scenes_data) if isinstance(scenes_data, list) else len(scenes_data.get('scenes', []))}개 씬)"
        except Exception as e:
            print(f"[캐릭터 관리] ❌ 씬 데이터 로드 실패: {e}")

    return [], None


def load_scene_analysis_data(force_refresh: bool = False) -> tuple:
    """
    최신 씬 분석 결과 로드 (v2.0)
    ⭐ 성능 최적화: 캐싱된 함수 사용

    Returns:
        Tuple[List[Dict], str]: (씬 데이터 리스트, 파일 수정 시간 문자열)
    """
    # ⭐ 캐싱된 함수 사용
    if force_refresh:
        _cached_load_scene_data.clear()

    scenes, mtime_str, file_name = _cached_load_scene_data(str(project_path))

    # 세션에 파일 정보 저장 (UI 표시용)
    if mtime_str:
        st.session_state['scene_file_mtime'] = mtime_str
    if file_name:
        st.session_state['scene_file_name'] = file_name

    return scenes, mtime_str

# PoseManager 초기화
pose_manager = get_pose_manager()

# 탭 구성 (v3.35: 씬별 갤러리 탭 추가)
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📋 캐릭터 목록",
    "➕ 캐릭터 추가",
    "🎨 배치 생성",
    "🧍 포즈 설정",
    "📥 가져오기",
    "⭐ 대표 캐릭터",
    "🖼️ 씬별 갤러리"
])

# === 탭 1: 캐릭터 목록 ===
with tab1:
    st.subheader("📋 등록된 캐릭터")

    characters = manager.get_all_characters()

    if not characters:
        st.info("등록된 캐릭터가 없습니다. 씬 분석 결과에서 가져오거나 직접 추가하세요.")
    else:
        st.success(f"{len(characters)}명의 캐릭터가 등록되어 있습니다.")

        # ═══════════════════════════════════════════════════════════════
        # ⭐ 일괄 삭제 UI
        # ═══════════════════════════════════════════════════════════════
        st.markdown("#### 🗑️ 일괄 삭제")

        col_sel1, col_sel2, col_sel3, col_sel4 = st.columns([1, 1, 1, 2])

        with col_sel1:
            if st.button("✅ 전체 선택", key="select_all_del"):
                for char in characters:
                    st.session_state[f"del_char_{char.id}"] = True
                st.rerun()

        with col_sel2:
            if st.button("❎ 전체 해제", key="deselect_all_del"):
                for char in characters:
                    st.session_state[f"del_char_{char.id}"] = False
                st.rerun()

        with col_sel3:
            # 선택된 캐릭터 수 계산 (ID 기반)
            selected_del_count = sum(
                1 for char in characters
                if st.session_state.get(f"del_char_{char.id}", False)
            )

            # 디버그 로그
            selected_debug = [char.name for char in characters if st.session_state.get(f"del_char_{char.id}", False)]
            print(f"[캐릭터 삭제] 선택된 캐릭터: {selected_debug} (총 {selected_del_count}명)")

            if st.button(f"🗑️ 선택 삭제 ({selected_del_count}명)", key="delete_selected",
                        disabled=selected_del_count == 0, type="secondary"):
                st.session_state.show_bulk_delete_confirm = True
                print(f"[캐릭터 삭제] 삭제 확인 다이얼로그 표시")

        # 삭제 확인 다이얼로그
        if st.session_state.get("show_bulk_delete_confirm", False):
            # ID 기반으로 선택된 캐릭터 찾기
            selected_chars = [
                char for char in characters
                if st.session_state.get(f"del_char_{char.id}", False)
            ]
            selected_names = [char.name for char in selected_chars]
            selected_ids = [char.id for char in selected_chars]

            print(f"[캐릭터 삭제] 확인 다이얼로그 - 선택된 ID: {selected_ids}")
            print(f"[캐릭터 삭제] 확인 다이얼로그 - 선택된 이름: {selected_names}")

            st.warning(f"⚠️ 다음 {len(selected_names)}명의 캐릭터를 삭제하시겠습니까?")
            st.write(", ".join(selected_names))

            col_confirm, col_cancel = st.columns(2)

            with col_confirm:
                if st.button("🗑️ 삭제 확인", type="primary", key="confirm_bulk_delete"):
                    print(f"[캐릭터 삭제] ⚡ 삭제 실행 시작")

                    # ID 기반으로 삭제 (순서 무관)
                    deleted_count = 0
                    for char in selected_chars:
                        print(f"[캐릭터 삭제] 삭제 중: {char.name} (id={char.id})")

                        success = manager.delete_character(char.id)
                        if success:
                            deleted_count += 1
                            print(f"[캐릭터 삭제] ✅ '{char.name}' 삭제 성공")
                        else:
                            print(f"[캐릭터 삭제] ❌ '{char.name}' 삭제 실패")

                    # 상태 초기화 (ID 기반)
                    st.session_state.show_bulk_delete_confirm = False
                    for char in characters:
                        key = f"del_char_{char.id}"
                        if key in st.session_state:
                            del st.session_state[key]

                    print(f"[캐릭터 삭제] ✅ 총 {deleted_count}명 삭제 완료")
                    st.success(f"✅ {deleted_count}명의 캐릭터가 삭제되었습니다.")
                    st.rerun()

            with col_cancel:
                if st.button("❌ 취소", key="cancel_bulk_delete"):
                    st.session_state.show_bulk_delete_confirm = False
                    st.rerun()

        st.divider()

        # ═══════════════════════════════════════════════════════════════
        # 캐릭터 목록 (체크박스 + 상세)
        # ═══════════════════════════════════════════════════════════════
        for idx, char in enumerate(characters):
            col_check, col_expand = st.columns([0.1, 3.9])

            with col_check:
                # ⭐ ID 기반 키 사용으로 인덱스 변경 시에도 안정적
                st.checkbox(
                    "선택",
                    key=f"del_char_{char.id}",
                    label_visibility="collapsed"
                )

            with col_expand:
                with st.expander(f"👤 {char.name} ({char.name_en})", expanded=False):
                    col1, col2 = st.columns([2, 1])

                    with col1:
                        st.markdown(f"**역할:** {char.role}")
                        st.markdown(f"**국적/시대:** {char.nationality} / {char.era}")
                        st.markdown(f"**설명:** {char.description}")

                        # 외모 설명 (한국어) - 편집 가능
                        st.markdown("**외모 (한국어):**")
                        new_appearance = st.text_area(
                            "외모 설명",
                            value=char.appearance or "",
                            height=80,
                            key=f"appearance_{char.id}_{idx}",
                            label_visibility="collapsed"
                        )

                        # 캐릭터 프롬프트 (영어) - 편집 가능
                        st.markdown("**프롬프트 (영어):**")
                        st.caption("이미지 생성에 사용되는 영어 프롬프트입니다. 직접 수정할 수 있습니다.")
                        new_prompt = st.text_area(
                            "캐릭터 프롬프트",
                            value=char.character_prompt or "",
                            height=120,
                            key=f"prompt_{char.id}_{idx}",
                            label_visibility="collapsed"
                        )

                        # 프롬프트 작성 가이드
                        with st.expander("💡 프롬프트 작성 가이드"):
                            st.markdown("""
                            **좋은 프롬프트 예시:**
                            ```
                            Korean man, 47 years old, short neat black hair with gray at temples,
                            rectangular black-framed glasses, oval face with small monolid eyes,
                            clean-shaven, fair skin, medium build, wearing charcoal gray suit
                            with white shirt and burgundy tie, standing pose
                            ```

                            **포함할 내용:**
                            - 인종, 성별, 정확한 나이
                            - 헤어스타일 (길이, 색상, 스타일)
                            - 얼굴 특징 (얼굴형, 눈, 코, 피부톤)
                            - 체형 (키, 체격)
                            - 의상 (구체적인 색상과 스타일)
                            - 액세서리 (안경, 시계 등)
                            - 포즈

                            **제외할 내용:**
                            - 아트 스타일 (flat vector, illustration 등)
                            - 배경 설명
                            - 추상적 특성 (professional, trustworthy 등)
                            """)

                        # 저장 버튼
                        col_save, col_del = st.columns(2)
                        with col_save:
                            if st.button("💾 프롬프트 저장", key=f"save_{char.id}_{idx}", use_container_width=True):
                                manager.update_character(char.id, {
                                    "appearance": new_appearance,
                                    "character_prompt": new_prompt
                                })
                                st.success("✅ 저장됨!")
                                st.rerun()
                        with col_del:
                            if st.button("🗑️ 캐릭터 삭제", key=f"del_{char.id}_{idx}", type="secondary", use_container_width=True):
                                manager.delete_character(char.id)
                                st.rerun()

                    with col2:
                        # 🔴 v3.78: 이미지 선택 기능 추가
                        st.markdown("**생성된 이미지:**")

                        if char.generated_images:
                            # 현재 선택된 이미지 확인
                            selected_image = char.get_selected_image() if hasattr(char, 'get_selected_image') else None

                            # 자동 선택 토글 (기본값: True)
                            auto_select = getattr(char, 'auto_select_latest', True)
                            new_auto_select = st.checkbox(
                                "🔄 최신 이미지 자동 적용",
                                value=auto_select,
                                key=f"auto_select_{char.id}_{idx}",
                                help="새 이미지 생성 시 자동으로 적용합니다"
                            )
                            if new_auto_select != auto_select:
                                manager.set_auto_select_latest(char.id, new_auto_select)
                                st.rerun()

                            # 최신순으로 이미지 정렬 (역순)
                            images_to_show = list(reversed(char.generated_images[-5:]))  # 최근 5개만

                            for img_idx, img_path in enumerate(images_to_show):
                                if not Path(img_path).exists():
                                    continue

                                # 선택 상태 및 최신 여부 확인
                                is_selected = (selected_image and
                                               Path(selected_image).resolve() == Path(img_path).resolve())
                                is_latest = (img_idx == 0)  # 역순이므로 첫 번째가 최신

                                # 이미지 표시 컨테이너
                                img_col1, img_col2 = st.columns([3, 1])

                                with img_col1:
                                    # 라벨 생성
                                    labels = []
                                    if is_selected:
                                        labels.append("⭐ 적용중")
                                    if is_latest:
                                        labels.append("🆕 최신")
                                    label_str = " | ".join(labels) if labels else ""

                                    # 썸네일 표시
                                    caption = f"{char.name}"
                                    if label_str:
                                        caption = f"{label_str}"

                                    render_clickable_thumbnail(
                                        img_path,
                                        caption=caption,
                                        width=100,
                                        key=f"char_img_{char.id}_{idx}_{img_idx}"
                                    )

                                with img_col2:
                                    # 선택 버튼
                                    if is_selected:
                                        st.success("✅ 적용됨")
                                    else:
                                        if st.button(
                                            "적용",
                                            key=f"select_img_{char.id}_{idx}_{img_idx}",
                                            type="secondary",
                                            use_container_width=True
                                        ):
                                            manager.select_character_image(char.id, img_path)
                                            st.success(f"✅ 이미지 적용됨!")
                                            st.rerun()

                            # 현재 적용 이미지 요약
                            if selected_image:
                                st.caption(f"📌 적용: {Path(selected_image).name[:30]}...")
                        else:
                            st.info("이미지가 없습니다.")

# === 탭 2: 캐릭터 추가 ===
with tab2:
    st.subheader("➕ 새 캐릭터 추가")

    # 프롬프트 가이드
    with st.expander("💡 캐릭터 프롬프트 작성 가이드"):
        st.markdown("""
        **좋은 프롬프트 예시:**
        ```
        American man, 95 years old, short white hair receding at temples,
        round gold-framed glasses, oval wrinkled face with small eyes,
        clean-shaven, fair skin with age spots, slightly hunched posture,
        wearing navy blue suit with white dress shirt and red tie, sitting pose
        ```

        **반드시 포함할 내용:**
        - 인종/국적, 성별, **정확한 나이** (예: "95 years old")
        - 헤어스타일 (길이, 색상, 스타일)
        - 얼굴 특징 (얼굴형, 눈, 코, 피부톤, 주름 등)
        - 체형 (키, 체격, 자세)
        - 의상 (**구체적인 색상**: navy blue, charcoal gray 등)
        - 액세서리 (안경 프레임 스타일, 시계 등)
        - 포즈 (standing, sitting, walking)

        **제외할 내용 (별도로 적용됨):**
        - 아트 스타일 (flat vector, illustration 등)
        - 배경 설명
        - 추상적 특성 (professional, trustworthy, wise 등)
        """)

    with st.form("add_character_form"):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("캐릭터명 (한글)", placeholder="워렌 버핏")
            name_en = st.text_input("영문명", placeholder="Warren Buffett")
            role = st.selectbox("역할", ["주연", "조연", "배경 인물", "언급만"])

        with col2:
            nationality = st.text_input("국적", placeholder="미국")
            era = st.text_input("시대", placeholder="현대 (2020년대)")

        description = st.text_area("설명", placeholder="95세 남성, 세계적인 투자자...")
        appearance = st.text_area("외모 특징 (한국어)", placeholder="흰 머리, 둥근 금테 안경, 네이비 정장...")
        character_prompt = st.text_area(
            "캐릭터 프롬프트 (영문)",
            placeholder="American man, 95 years old, short white hair, round gold-framed glasses, oval wrinkled face, fair skin, wearing navy blue suit with white shirt and red tie, sitting pose",
            help="이미지 생성에 사용될 영문 프롬프트 - 위 가이드 참고",
            height=120
        )

        submitted = st.form_submit_button("➕ 캐릭터 추가", type="primary")

        if submitted and name:
            char_id = name_en.lower().replace(" ", "_") if name_en else f"char_{len(characters)}"
            char = Character(
                id=char_id,
                name=name,
                name_en=name_en,
                description=description,
                role=role,
                nationality=nationality,
                era=era,
                appearance=appearance,
                character_prompt=character_prompt
            )
            manager.add_character(char)
            st.success(f"'{name}' 캐릭터가 추가되었습니다!")
            st.rerun()

# === 탭 3: 배치 생성 (합성용) ===
with tab3:
    st.subheader("🎨 캐릭터 이미지 배치 생성")

    st.info("""
    **캐릭터 이미지란?**
    - 각 캐릭터의 전신 이미지를 단색 배경으로 생성합니다
    - 생성된 이미지는 '이미지 생성' 단계에서 배경과 합성됩니다
    - 포즈와 배경을 선택할 수 있습니다

    💡 **워크플로우:** 캐릭터 이미지 생성 → 배경 이미지 생성 → 합성
    """)

    # API 키 확인
    if not require_api_key("TOGETHER_API_KEY", "Together.ai API"):
        st.stop()

    characters = manager.get_all_characters()

    if not characters:
        st.warning("⚠️ 먼저 캐릭터를 추가하세요. '가져오기' 탭에서 씬 분석 결과를 가져올 수 있습니다.")
        st.stop()

    st.success(f"✅ {len(characters)}명의 캐릭터가 등록되어 있습니다.")

    # 생성 설정
    st.markdown("### ⚙️ 생성 설정")

    # 스타일 선택 (StyleManager 사용)
    style_manager = get_style_manager(str(project_path))

    # v3.40: 저장된 character_style을 session_state에 복원
    saved_character_style = _saved_batch_settings.get("character_style")
    style_session_key = "selected_style_character_char_batch"
    if saved_character_style and style_session_key not in st.session_state:
        st.session_state[style_session_key] = saved_character_style
        print(f"[캐릭터 관리] 저장된 스타일 복원: {saved_character_style}")

    selected_style = style_radio_selector(
        segment="character",
        key="char_batch",
        project_path=str(project_path),
        horizontal=True
    )

    # 스타일 프롬프트 미리보기
    if selected_style:
        with st.expander("선택된 스타일 상세"):
            st.markdown(f"**{selected_style.name_ko}** ({selected_style.name})")
            st.code(f"Prefix: {selected_style.prompt_prefix}", language=None)
            st.code(f"Suffix: {selected_style.prompt_suffix}", language=None)

    col1, col2 = st.columns(2)

    # v3.40: 채널-영상별 저장된 설정값 로드
    pose_options = ["standing", "standing_left", "standing_right", "portrait"]
    saved_pose = _saved_batch_settings.get("pose", "standing")
    pose_default_idx = pose_options.index(saved_pose) if saved_pose in pose_options else 0

    bg_options = ["solid_gray", "solid_white", "solid_blue"]
    saved_bg = _saved_batch_settings.get("background_type", "solid_gray")
    bg_default_idx = bg_options.index(saved_bg) if saved_bg in bg_options else 0

    with col1:
        st.markdown("#### 🧍 포즈")
        char_pose = st.selectbox(
            "기본 포즈",
            pose_options,
            index=pose_default_idx,
            format_func=lambda x: {
                "standing": "정면 서있기",
                "standing_left": "왼쪽 향해 서있기",
                "standing_right": "오른쪽 향해 서있기",
                "portrait": "상반신 초상화"
            }.get(x, x),
            key="char_pose_select"
        )

    with col2:
        st.markdown("#### 🖼️ 배경")
        char_background = st.selectbox(
            "배경 타입",
            bg_options,
            index=bg_default_idx,
            format_func=lambda x: {
                "solid_gray": "단색 회색 (합성 추천)",
                "solid_white": "단색 흰색",
                "solid_blue": "단색 파랑"
            }.get(x, x),
            key="char_bg_select"
        )

    # 이미지 크기 (v3.40: 저장된 값 로드)
    size_options = [1024, 768, 512]
    saved_width = _saved_batch_settings.get("width", 1024)
    saved_height = _saved_batch_settings.get("height", 1024)
    width_default_idx = size_options.index(saved_width) if saved_width in size_options else 0
    height_default_idx = size_options.index(saved_height) if saved_height in size_options else 0

    col_size1, col_size2 = st.columns(2)
    with col_size1:
        char_width = st.selectbox("너비", size_options, index=width_default_idx, key="char_width")
    with col_size2:
        char_height = st.selectbox("높이", size_options, index=height_default_idx, key="char_height")

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # ⭐ 새로 추가: API 선택 및 병렬 처리 설정
    # ═══════════════════════════════════════════════════════════════
    st.markdown("### 🔧 API 및 성능 설정")

    col_api1, col_api2 = st.columns(2)

    with col_api1:
        # API 제공자 선택
        api_options = ["Together.ai FLUX", "Google ImageFX", "OpenAI DALL-E", "Stability AI", "Replicate SDXL"]

        # v3.40: 채널-영상별 저장된 API 우선, 없으면 전역 설정
        saved_api_cv = _saved_batch_settings.get("image_api")
        saved_api = saved_api_cv or get_last_image_api()
        api_default_index = 0
        if saved_api and saved_api in api_options:
            api_default_index = api_options.index(saved_api)

        char_api_provider = st.selectbox(
            "🔧 이미지 생성 API",
            options=api_options,
            index=api_default_index,
            key="char_api_provider",
            help="⚡ 빠른 생성: Together.ai FLUX\n🆓 무료: Google ImageFX\n🎨 고품질: OpenAI DALL-E\n🚀 초고속: Replicate Lightning"
        )

        # 선택 변경 시 저장 (전역 + 채널-영상별)
        if char_api_provider != saved_api:
            set_last_image_api(char_api_provider)

    with col_api2:
        # API별 모델 옵션
        model_options_map = {
            "Together.ai FLUX": [
                ("black-forest-labs/FLUX.2-dev", "FLUX.2 Dev (권장, ~20원)"),
                ("black-forest-labs/FLUX.2-flex", "FLUX.2 Flex (~40원)"),
                ("black-forest-labs/FLUX.2-pro", "FLUX.2 Pro (고품질, ~40원)"),
            ],
            "Google ImageFX": [
                ("IMAGEN_4", "Imagen 4 (최신, 무료)"),
                ("IMAGEN_3_5", "Imagen 3.5 (무료)"),
                ("IMAGEN_3_1", "Imagen 3.1 (무료)"),
                ("IMAGEN_3", "Imagen 3.0 (무료)"),
            ],
            "OpenAI DALL-E": [
                ("dall-e-3", "DALL-E 3 (최신)"),
                ("dall-e-2", "DALL-E 2"),
            ],
            "Stability AI": [
                ("stable-diffusion-xl-1024-v1-0", "SDXL 1.0"),
            ],
            "Replicate SDXL": [
                ("stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b", "SDXL 기본"),
                ("bytedance/sdxl-lightning-4step:5599ed30703defd1d160a25a63321b4dec97101d98b4674bcc56e41f62f35637", "SDXL Lightning (초고속!)"),
            ]
        }

        options = model_options_map.get(char_api_provider, [("default", "기본")])
        model_ids = [o[0] for o in options]

        # 저장된 모델 로드
        saved_model = get_last_image_model()
        model_default_index = 0
        if saved_model and saved_model in model_ids:
            model_default_index = model_ids.index(saved_model)

        char_model = st.selectbox(
            "🤖 모델",
            options=model_ids,
            index=model_default_index,
            format_func=lambda x: next((o[1] for o in options if o[0] == x), x),
            key="char_model"
        )

        # 선택 변경 시 저장
        if char_model != saved_model:
            set_last_image_model(char_model)

    col_perf1, col_perf2 = st.columns(2)

    with col_perf1:
        # 저장된 동시 생성 수 로드
        saved_parallel = get_last_concurrent_count()

        char_parallel = st.slider(
            "⚡ 동시 생성 수",
            min_value=1,
            max_value=5,
            value=saved_parallel,
            key="char_parallel",
            help="높을수록 빠르지만 API Rate Limit에 주의하세요.\n무료 API는 1~2 추천"
        )

        # 선택 변경 시 저장
        if char_parallel != saved_parallel:
            set_last_concurrent_count(char_parallel)

    with col_perf2:
        # API 키 상태 확인
        api_key_status = "❓"
        if char_api_provider == "Together.ai FLUX":
            from config.settings import TOGETHER_API_KEY
            api_key_status = "✅ 설정됨" if TOGETHER_API_KEY else "❌ 미설정"
        elif char_api_provider == "Google ImageFX":
            from config.settings import load_imagefx_cookie
            imagefx_cookie = st.session_state.get("imagefx_cookie") or load_imagefx_cookie()
            api_key_status = "✅ 쿠키 설정됨" if imagefx_cookie else "❌ 쿠키 미설정"
        elif char_api_provider == "OpenAI DALL-E":
            openai_key = os.getenv("OPENAI_API_KEY")
            api_key_status = "✅ 설정됨" if openai_key else "❌ 미설정"
        elif char_api_provider == "Stability AI":
            stability_key = os.getenv("STABILITY_API_KEY")
            api_key_status = "✅ 설정됨" if stability_key else "❌ 미설정"
        elif char_api_provider == "Replicate SDXL":
            replicate_key = os.getenv("REPLICATE_API_TOKEN")
            api_key_status = "✅ 설정됨" if replicate_key else "❌ 미설정"

        st.markdown(f"**🔑 API 키 상태:** {api_key_status}")

    # ═══════════════════════════════════════════════════════════════
    # v3.40: 채널-영상별 설정 자동 저장
    # ═══════════════════════════════════════════════════════════════
    _current_settings = {
        "character_style": selected_style.id if selected_style else None,
        "pose": char_pose,
        "background_type": char_background,
        "width": char_width,
        "height": char_height,
        "image_api": char_api_provider,
        "image_model": char_model,
    }

    # 설정이 변경되었는지 확인 후 저장
    if _current_settings != _saved_batch_settings:
        save_character_batch_settings(_current_channel, _current_video, _current_settings)
        # 메모리 내 캐시 업데이트
        _saved_batch_settings.update(_current_settings)

    st.divider()

    # 캐릭터 선택
    st.markdown("### 👤 생성할 캐릭터 선택")

    # 주인공만 필터링 옵션
    show_main_only = st.checkbox("주연만 표시", value=False, key="show_main_only")

    if show_main_only:
        filtered_chars = [c for c in characters if c.role in ["주연", "주인공", "main"]]
    else:
        filtered_chars = characters

    # 전체 선택/해제
    col_all, col_none = st.columns(2)
    with col_all:
        if st.button("✅ 전체 선택", key="select_all_chars_btn"):
            st.session_state["select_all_chars"] = True
            st.rerun()
    with col_none:
        if st.button("❌ 전체 해제", key="deselect_all_chars_btn"):
            st.session_state["select_all_chars"] = False
            st.rerun()

    default_checked = st.session_state.get("select_all_chars", True)

    # 캐릭터 체크박스
    selected_chars = []
    cols = st.columns(3)
    for i, char in enumerate(filtered_chars):
        with cols[i % 3]:
            # 이미 생성된 이미지가 있는지 확인
            has_image = len(char.generated_images) > 0 if hasattr(char, 'generated_images') and char.generated_images else False
            has_prompt = bool(char.character_prompt)

            # 상태 아이콘
            if has_image:
                status = "✅"  # 이미지 있음
            elif has_prompt:
                status = "🟡"  # 프롬프트만 있음
            else:
                status = "❌"  # 프롬프트도 없음

            label = f"{status} {char.name}"

            # 기본값: 전체선택 상태이고 이미지가 없고 프롬프트가 있는 경우 체크
            default_val = default_checked and not has_image and has_prompt
            if st.checkbox(label, value=default_val, key=f"char_sel_{char.id}_{i}"):
                selected_chars.append(char)

    st.info(f"📊 선택된 캐릭터: {len(selected_chars)}명")

    # 프롬프트 없는 캐릭터 경고 (v3.32: 안전한 속성 접근)
    chars_without_prompt = [c for c in selected_chars if not get_character_visual_prompt(c)]
    if chars_without_prompt:
        st.warning(f"⚠️ {len(chars_without_prompt)}명의 캐릭터에 프롬프트가 없습니다: {', '.join([get_character_name(c) for c in chars_without_prompt])}")

    # ═══════════════════════════════════════════════════════════════
    # ⭐ 포즈별 씬 선택 UI
    # ═══════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("### 🧍 포즈별 씬 설정")

    # 포즈 모드 선택 (AI 자동 분석 옵션 추가)
    pose_mode = st.radio(
        "포즈 설정 방식",
        [
            "단일 포즈 (모든 씬에 동일)",
            "포즈별 씬 선택 (씬마다 다른 포즈)",
            "🤖 AI 자동 분석 (씬 내용 기반 추천)"
        ],
        horizontal=True,
        key="pose_mode"
    )

    from utils.character_scene_linker import POSE_OPTIONS, CharacterSceneLinker

    # === 선택된 캐릭터의 등장 씬 수집 (Problem 56 수정: 다중 소스 탐색) ===
    all_appearance_scenes = set()
    char_scenes_map = {}

    # 씬 데이터에서 캐릭터별 등장 정보 미리 빌드 (폴백용)
    scene_based_char_map = build_character_scene_map()

    for char in selected_chars:
        scenes = []

        # 1. CharacterManager에서 appearance_scenes 확인
        if hasattr(char, 'appearance_scenes') and char.appearance_scenes:
            scenes = char.appearance_scenes
        elif hasattr(char, 'scenes') and char.scenes:
            scenes = char.scenes

        # 2. 씬 데이터에서 폴백 조회 (appearance_scenes가 없는 경우)
        if not scenes:
            # 유연한 이름 매칭
            char_name_normalized = char.name.strip().lower().replace(" ", "")
            for scene_char_name, scene_ids in scene_based_char_map.items():
                scene_char_normalized = scene_char_name.strip().lower().replace(" ", "")
                if (char_name_normalized == scene_char_normalized or
                    char_name_normalized in scene_char_normalized or
                    scene_char_normalized in char_name_normalized):
                    scenes = scene_ids
                    print(f"[포즈 설정] '{char.name}' → 씬 데이터에서 {scenes} 발견")
                    break

        # 문자열/정수 변환
        scenes = [int(s) if isinstance(s, str) and s.isdigit() else s for s in scenes if s]
        scenes = [s for s in scenes if isinstance(s, int)]

        char_scenes_map[char.name] = scenes
        all_appearance_scenes.update(scenes)

    all_scenes = sorted(all_appearance_scenes)

    # 디버그 로그
    print(f"[포즈 설정] 선택된 캐릭터: {len(selected_chars)}명")
    print(f"[포즈 설정] 수집된 등장 씬: {all_scenes}")

    if pose_mode == "단일 포즈 (모든 씬에 동일)":
        # 기존 단일 포즈 선택
        pose_scene_mapping = {
            char_pose: {
                "name": next((p[1] for p in POSE_OPTIONS if p[0] == char_pose), char_pose),
                "scenes": all_scenes
            }
        }
        st.session_state.pose_scene_mapping = pose_scene_mapping
        st.caption(f"💡 모든 씬에 '{char_pose}' 포즈가 적용됩니다.")

    elif "AI 자동 분석" in pose_mode:
        # ═══════════════════════════════════════════════════════════════
        # AI 자동 포즈 분석 (Problem 56: 새 기능)
        # ═══════════════════════════════════════════════════════════════
        from utils.pose_analyzer import (
            analyze_character_poses,
            AVAILABLE_POSES,
            get_pose_info
        )

        st.markdown("#### 🤖 AI 자동 포즈 분석")

        if not all_scenes:
            st.warning("⚠️ 씬 데이터가 없습니다. 씬 분석을 먼저 실행해주세요.")
        else:
            # AI 모델 선택
            col1, col2 = st.columns([3, 1])

            with col1:
                model_options = {
                    "Gemini 2.5 Flash (무료, 추천)": "gemini-2.5-flash",
                    "Gemini 2.5 Flash Lite (무료, 초고속)": "gemini-2.5-flash-lite",
                    "Claude Sonnet 4 ($0.003/1K)": "claude-sonnet-4-20250514",
                    "Claude Haiku 3.5 ($0.001/1K)": "claude-3-5-haiku-latest",
                    "GPT-4o Mini ($0.00015/1K)": "gpt-4o-mini",
                }

                selected_model_label = st.selectbox(
                    "분석 AI 모델",
                    options=list(model_options.keys()),
                    index=0,
                    key="pose_analysis_model"
                )

                selected_model = model_options[selected_model_label]

            with col2:
                st.markdown("")
                st.markdown("")
                analyze_btn = st.button(
                    "🔍 AI 포즈 분석",
                    type="primary",
                    key="run_pose_analysis"
                )

            # 분석 실행
            if analyze_btn:
                # 씬 데이터 로드
                scenes_data = load_scenes_data(str(project_path))
                character_names = [char.name for char in selected_chars]

                progress = st.progress(0)
                status = st.empty()

                def update_progress(p):
                    progress.progress(p)

                def update_status(s):
                    status.text(s)

                with st.spinner("🤖 AI가 씬별 포즈를 분석하고 있습니다..."):
                    result = analyze_character_poses(
                        scenes=scenes_data,
                        characters=character_names,
                        model_id=selected_model,
                        progress_callback=update_progress,
                        status_callback=update_status
                    )

                progress.empty()
                status.empty()

                if result["success"]:
                    st.session_state.pose_analysis_result = result["pose_assignments"]
                    st.success(f"✅ 분석 완료! {len(result['pose_assignments'])}개 포즈 추천")
                else:
                    st.error(f"❌ 분석 실패: {result.get('error', '알 수 없는 오류')}")

            # 분석 결과 표시
            if "pose_analysis_result" in st.session_state and st.session_state.pose_analysis_result:
                st.markdown("---")
                st.markdown("#### 📊 AI 분석 결과")

                assignments = st.session_state.pose_analysis_result

                # 결과 테이블
                for i, assignment in enumerate(assignments):
                    scene_id = assignment.get("scene_id", 0)
                    char_name = assignment.get("character", "")
                    pose_id = assignment.get("pose", "standing")
                    reason = assignment.get("reason", "")

                    pose_info = AVAILABLE_POSES.get(pose_id, {"emoji": "🧍", "name": pose_id})
                    pose_emoji = pose_info.get("emoji", "🧍")
                    pose_name = pose_info.get("name", pose_id)

                    col1, col2, col3, col4 = st.columns([1, 2, 2, 3])

                    with col1:
                        st.write(f"**씬 {scene_id}**")

                    with col2:
                        st.write(f"👤 {char_name}")

                    with col3:
                        # 포즈 수정 가능
                        pose_options = list(AVAILABLE_POSES.keys())
                        current_idx = pose_options.index(pose_id) if pose_id in pose_options else 0

                        new_pose = st.selectbox(
                            "포즈",
                            options=pose_options,
                            index=current_idx,
                            format_func=lambda x: f"{AVAILABLE_POSES[x]['emoji']} {AVAILABLE_POSES[x]['name']}",
                            key=f"ai_pose_{scene_id}_{char_name}_{i}",
                            label_visibility="collapsed"
                        )

                        # 수정된 포즈 반영
                        assignment["pose"] = new_pose

                    with col4:
                        st.caption(reason if reason else "-")

                # 적용 버튼
                st.markdown("---")

                col1, col2 = st.columns(2)

                with col1:
                    if st.button("✅ 분석 결과 적용", type="primary", key="apply_ai_poses"):
                        # pose_scene_mapping 형식으로 변환
                        pose_scene_mapping = {}

                        for assignment in assignments:
                            pose_id = assignment.get("pose", "standing")
                            scene_id = assignment.get("scene_id", 0)

                            if pose_id not in pose_scene_mapping:
                                pose_info = AVAILABLE_POSES.get(pose_id, {})
                                pose_scene_mapping[pose_id] = {
                                    "name": pose_info.get("name", pose_id),
                                    "scenes": []
                                }

                            if scene_id not in pose_scene_mapping[pose_id]["scenes"]:
                                pose_scene_mapping[pose_id]["scenes"].append(scene_id)

                        st.session_state.pose_scene_mapping = pose_scene_mapping
                        st.success("✅ 포즈 설정이 적용되었습니다!")
                        st.rerun()

                with col2:
                    if st.button("🔄 다시 분석", key="reanalyze_poses"):
                        del st.session_state.pose_analysis_result
                        st.rerun()

    elif "포즈별 씬 선택" in pose_mode:
        # 포즈별 씬 선택 UI
        if not all_scenes:
            st.warning("""
            ⚠️ **선택된 캐릭터에 등장 씬 정보가 없습니다.**

            **해결 방법:**
            1. '씬 분석' 페이지에서 분석을 실행해주세요.
            2. 분석 완료 후 이 페이지를 새로고침하세요.
            """)

            # 디버깅 정보 표시
            with st.expander("🔧 디버깅 정보"):
                st.write("**선택된 캐릭터:**")
                for char in selected_chars:
                    app_scenes = getattr(char, 'appearance_scenes', [])
                    st.caption(f"  - {char.name}: appearance_scenes = {app_scenes}")

                st.write("**씬 데이터 상태:**")
                scenes_from_file = load_scenes_data(str(project_path))
                st.caption(f"  - 로드된 씬: {len(scenes_from_file)}개")

                if scenes_from_file:
                    all_chars_in_scenes = get_all_characters_from_scenes(scenes_from_file)
                    st.caption(f"  - 씬에 등장하는 캐릭터: {', '.join(all_chars_in_scenes[:5])}")
                else:
                    st.caption("  - ⚠️ 씬 분석 결과 없음")

                st.write("**프로젝트 경로:**")
                st.caption(f"  - {project_path}")
        else:
            st.info(f"""
            💡 **사용법**: 각 포즈별로 적용할 씬을 선택하세요.
            - 같은 캐릭터라도 씬에 따라 다른 포즈 이미지를 생성할 수 있습니다.
            - 선택하지 않은 포즈는 생성되지 않습니다.
            """)

            st.caption(f"**등장 씬:** {', '.join(map(str, all_scenes))}")

            pose_scene_mapping = {}

            for pose_key, pose_name, pose_desc in POSE_OPTIONS:
                with st.expander(f"🧍 {pose_name}", expanded=(pose_key == "standing_front")):
                    st.caption(pose_desc)

                    # 씬 선택 체크박스 그리드
                    num_cols = min(len(all_scenes), 8) if all_scenes else 1
                    cols = st.columns(num_cols)

                    selected_scenes = []

                    for i, scene_id in enumerate(all_scenes):
                        with cols[i % num_cols]:
                            # 기본값: 첫 번째 포즈에 모든 씬 선택
                            default_value = (pose_key == "standing_front")

                            if st.checkbox(
                                f"씬 {scene_id}",
                                value=st.session_state.get(f"pose_{pose_key}_scene_{scene_id}", default_value),
                                key=f"pose_{pose_key}_scene_{scene_id}"
                            ):
                                selected_scenes.append(scene_id)

                    pose_scene_mapping[pose_key] = {
                        "name": pose_name,
                        "scenes": selected_scenes
                    }

                    if selected_scenes:
                        st.success(f"✅ 씬 {selected_scenes}에 '{pose_name}' 적용")

            # 씬별 포즈 요약 표시
            st.markdown("#### 📋 씬별 포즈 요약")

            scene_pose_summary = {}
            for pose_key, pose_data in pose_scene_mapping.items():
                for scene_id in pose_data["scenes"]:
                    if scene_id not in scene_pose_summary:
                        scene_pose_summary[scene_id] = []
                    scene_pose_summary[scene_id].append(pose_data["name"])

            if scene_pose_summary:
                summary_cols = st.columns(min(len(all_scenes), 6))
                for i, scene_id in enumerate(all_scenes):
                    with summary_cols[i % len(summary_cols)]:
                        st.markdown(f"**씬 {scene_id}**")
                        poses = scene_pose_summary.get(scene_id, ["없음"])
                        for pose in poses:
                            st.caption(f"• {pose}")

            st.session_state.pose_scene_mapping = pose_scene_mapping

    st.divider()

    # 생성 버튼
    st.markdown("### 🚀 생성 실행")

    # ⭐ 예상 시간 (API + 병렬 처리 반영)
    total_chars = len(selected_chars)

    # API별 예상 시간 (FLUX.2 모델 기준)
    time_per_char_map = {
        "Together.ai FLUX": 8,  # FLUX.2 유료 모델 기준
        "Google ImageFX": 10,  # Imagen 모델 (무료)
        "OpenAI DALL-E": 10,
        "Stability AI": 12,
        "Replicate SDXL": 3 if "lightning" in char_model.lower() else 10
    }
    base_time = time_per_char_map.get(char_api_provider, 15)
    estimated_time = int((total_chars * base_time) / max(1, char_parallel))

    if total_chars > 0:
        minutes = estimated_time // 60
        seconds = estimated_time % 60
        time_str = f"{minutes}분 {seconds}초" if minutes > 0 else f"{seconds}초"
        st.info(f"⏱️ 예상 소요 시간: 약 **{time_str}** ({total_chars}명 × {base_time}초 ÷ {char_parallel} 병렬)")
    else:
        st.caption("생성할 캐릭터를 선택하세요")

    # v2.0: 시드 잠금 옵션 (캐릭터 이미지 배치 생성용)
    # ⭐ v2.1: style_segment="character"로 캐릭터 스타일 선택 UI 사용
    if char_api_provider == "Google ImageFX":
        with st.expander("🔒 이미지 일관성 유지 (시드 잠금)", expanded=False):
            char_seed_lock_enabled, char_locked_seed = render_seed_lock_options(key_prefix="char_batch_seed", style_segment="character")
            if char_parallel > 1 and char_seed_lock_enabled:
                st.warning("⚠️ 병렬 처리에서는 '첫 이미지 자동 잠금' 기능이 지원되지 않습니다. 수동으로 시드를 지정하거나, 동시 생성 수를 1로 설정하세요.")
    else:
        char_seed_lock_enabled = False
        char_locked_seed = None
        with st.expander("🔒 이미지 일관성 유지 (시드 잠금)", expanded=False):
            st.info("💡 시드 잠금 기능은 **Google ImageFX** API에서만 사용 가능합니다.")
            st.caption("다른 API는 현재 시드 파라미터를 지원하지 않습니다.")

    # ═══════════════════════════════════════════════════════════════
    # ⭐ v3.31: 유명인 일반화 필터 (Google ImageFX 오류 방지)
    # ═══════════════════════════════════════════════════════════════
    if char_api_provider == "Google ImageFX" and total_chars > 0:
        with st.expander("🛡️ 유명인 일반화 필터 (ImageFX 오류 방지)", expanded=False):
            st.markdown("""
            💡 **Google ImageFX 오류 방지 기능**

            실제 기업명/인물명이 포함된 캐릭터는 이미지 생성 시
            `PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER` 오류가 발생할 수 있습니다.

            이 필터를 적용하면 AI가 자동으로 일반화된 표현으로 변환합니다.
            - 삼성전자 임원 → 대형 전자회사의 임원
            - ZF 독일 임원 → 독일 자동차 부품회사의 임원
            """)

            use_anonymization_filter = st.checkbox(
                "🛡️ 유명인 일반화 필터 적용",
                value=st.session_state.get("use_char_anonymization_filter", True),
                key="char_anonymization_filter_checkbox",
                help="캐릭터 이미지 생성 전 AI가 기업명/인물명을 일반화합니다"
            )
            st.session_state["use_char_anonymization_filter"] = use_anonymization_filter

            if use_anonymization_filter:
                # ═══════════════════════════════════════════════════════════
                # ⚙️ 고급 설정 (AI 모델 및 프롬프트)
                # ═══════════════════════════════════════════════════════════
                with st.expander("⚙️ 고급 설정 (AI 모델 및 프롬프트)", expanded=False):
                    # --- AI 모델 선택 ---
                    st.markdown("##### 🤖 AI 모델 선택")
                    available_models = get_sanitizer_models_for_ui()
                    if available_models:
                        model_ids = [m["id"] for m in available_models]
                        default_model = get_sanitizer_recommended_model()
                        default_idx = model_ids.index(default_model) if default_model in model_ids else 0

                        def _format_model(mid):
                            for m in available_models:
                                if m["id"] == mid:
                                    label = m["name"]
                                    if m.get("recommended"):
                                        label += " (추천)"
                                    return label
                            return mid

                        sanitizer_model = st.selectbox(
                            "치환용 AI 모델",
                            options=model_ids,
                            index=default_idx,
                            format_func=_format_model,
                            key="char_sanitizer_model_select",
                            help="프롬프트에서 유명인 이름을 감지하고 치환하는 데 사용할 AI 모델"
                        )
                        st.session_state["char_sanitizer_model"] = sanitizer_model

                        for m in available_models:
                            if m["id"] == sanitizer_model:
                                if m.get("recommended"):
                                    st.caption(f"✨ 추천 모델 ({m['provider']})")
                                else:
                                    st.caption(f"ℹ️ {m['provider']}")
                                break
                    else:
                        st.warning("사용 가능한 AI 모델이 없습니다. API 키를 확인하세요.")
                        sanitizer_model = "gemini-2.5-flash"
                        st.session_state["char_sanitizer_model"] = sanitizer_model

                    st.divider()

                    # --- 프롬프트 설정 ---
                    st.markdown("##### 📝 일반화 프롬프트")
                    prompt_preset = st.radio(
                        "프롬프트 모드",
                        options=["기본 프롬프트", "사용자 정의"],
                        index=0 if st.session_state.get("char_sanitizer_prompt_mode", "기본 프롬프트") == "기본 프롬프트" else 1,
                        horizontal=True,
                        key="char_sanitizer_prompt_mode_radio"
                    )
                    st.session_state["char_sanitizer_prompt_mode"] = prompt_preset

                    if prompt_preset == "사용자 정의":
                        custom_prompt = st.text_area(
                            "일반화 프롬프트 (수정 가능)",
                            value=st.session_state.get("char_sanitizer_custom_prompt", SANITIZE_PROMPT_TEMPLATE),
                            height=250,
                            key="char_sanitizer_custom_prompt_area",
                            help="캐릭터 이름을 일반화하는 데 사용되는 AI 프롬프트입니다. {prompt} 변수가 입력 텍스트로 대체됩니다."
                        )
                        st.session_state["char_sanitizer_custom_prompt"] = custom_prompt
                    else:
                        with st.expander("📄 기본 프롬프트 미리보기", expanded=False):
                            st.code(SANITIZE_PROMPT_TEMPLATE, language="text")

                # 선택된 모델 가져오기
                sanitizer_model = st.session_state.get("char_sanitizer_model", get_sanitizer_recommended_model())

                # 빠른 위험도 체크 (v3.32 fix: 안전한 헬퍼 함수 사용)
                needs_check_count = sum(
                    1 for c in selected_chars
                    if needs_sanitization_quick_check(get_character_name(c)) or needs_sanitization_quick_check(get_character_visual_prompt(c))
                )

                if needs_check_count > 0:
                    st.warning(f"⚠️ {needs_check_count}명의 캐릭터에서 변환이 필요할 수 있습니다.")
                else:
                    st.success("✅ 모든 캐릭터가 안전해 보입니다. (API 호출 시 추가 검증)")

                # 사용자 정의 프롬프트 결정
                _custom_prompt_tpl = None
                if st.session_state.get("char_sanitizer_prompt_mode") == "사용자 정의":
                    _custom_prompt_tpl = st.session_state.get("char_sanitizer_custom_prompt")

                st.caption(f"🤖 사용 모델: **{sanitizer_model}**")

                # 미리보기 버튼
                if st.button("🔍 변환 미리보기", key="preview_char_anonymization"):
                    with st.spinner(f"AI({sanitizer_model}) 분석 중..."):
                        # 캐릭터 데이터 변환 (v3.32 fix: 안전한 헬퍼 함수 사용)
                        char_dicts = [{"name": get_character_name(c), "visual_prompt": get_character_visual_prompt(c)} for c in selected_chars]
                        previews = preview_character_sanitization(char_dicts, ai_model=sanitizer_model, prompt_template=_custom_prompt_tpl)

                        changed_count = sum(1 for p in previews if p["changed"])

                        if changed_count == 0:
                            st.success("✅ 모든 캐릭터가 이미 안전합니다. 변환이 필요하지 않습니다.")
                        else:
                            st.info(f"📋 **{changed_count}명** 캐릭터의 이름이 변환됩니다:")

                            for preview in previews:
                                if preview["changed"]:
                                    col1, col2, col3 = st.columns([2, 0.5, 2])
                                    with col1:
                                        st.code(preview["original_name"], language=None)
                                    with col2:
                                        st.markdown("→")
                                    with col3:
                                        st.code(preview["sanitized_name"], language=None)
                                    if preview.get("detected_names"):
                                        st.caption(f"  감지된 이름: {', '.join(preview['detected_names'])}")
                                else:
                                    st.text(f"✓ {preview['original_name']} (변경 없음)")
    else:
        use_anonymization_filter = False

    if st.button("🎨 캐릭터 이미지 배치 생성", type="primary", use_container_width=True, disabled=total_chars==0):
        from core.image.character_image_generator import CharacterImageGenerator, CharacterImageConfig
        from utils.image_storage import save_character_image

        # 출력 디렉토리
        output_dir = project_path / "images" / "characters"
        output_dir.mkdir(parents=True, exist_ok=True)

        api_manager = get_api_manager()

        # ═══════════════════════════════════════════════════════════════
        # ⭐ 향상된 프로그레스 UI
        # ═══════════════════════════════════════════════════════════════
        st.markdown("### 📊 생성 진행 상황")

        # 전체 프로그레스바
        overall_progress_bar = st.progress(0)
        overall_status = st.empty()

        st.divider()

        # 캐릭터별 상태 테이블
        st.markdown("**캐릭터별 상태**")
        status_container = st.container()

        # 상세 로그
        log_expander = st.expander("📋 상세 로그", expanded=False)
        log_area = log_expander.empty()

        # 이미지 미리보기 영역
        image_preview = st.empty()

        # 캐릭터별 상태 초기화
        char_statuses = {}
        for char in selected_chars:
            char_statuses[char.name] = {
                "status": "⏳ 대기",
                "time": "-"
            }

        generation_logs = []
        generation_start_time = time.time()

        def update_progress_ui():
            """프로그레스 UI 업데이트"""
            completed = sum(1 for s in char_statuses.values() if s["status"] in ["✅ 완료", "❌ 실패"])
            progress_pct = completed / total_chars if total_chars > 0 else 0

            overall_progress_bar.progress(progress_pct)

            elapsed = time.time() - generation_start_time
            remaining = (elapsed / max(completed, 1)) * (total_chars - completed) if completed > 0 else estimated_time

            overall_status.markdown(f"""
            **진행률:** {completed}/{total_chars} ({progress_pct*100:.0f}%)  |
            **경과 시간:** {elapsed:.1f}초  |
            **예상 남은 시간:** {remaining:.1f}초
            """)

            # 상태 테이블 업데이트
            with status_container:
                for name, status in char_statuses.items():
                    cols = st.columns([3, 1.5, 1.5])
                    cols[0].write(name)
                    cols[1].write(status["status"])
                    cols[2].write(status["time"])

            # 로그 업데이트
            log_area.code("\n".join(generation_logs[-15:]))

        def on_char_start(char_name: str):
            """캐릭터 생성 시작 콜백"""
            char_statuses[char_name]["status"] = "🔄 생성 중..."
            generation_logs.append(f"[{time.strftime('%H:%M:%S')}] {char_name} 생성 시작")

        def on_char_complete(char_name: str, elapsed: float, success: bool, error: str = None):
            """캐릭터 생성 완료 콜백"""
            if success:
                char_statuses[char_name]["status"] = "✅ 완료"
                char_statuses[char_name]["time"] = f"{elapsed:.1f}초"
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] {char_name} 완료 ({elapsed:.1f}초)")
            else:
                char_statuses[char_name]["status"] = "❌ 실패"
                char_statuses[char_name]["time"] = "-"
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] {char_name} 실패: {error}")

        success_count = 0
        fail_count = 0

        try:
            # 스타일 정보 가져오기
            style_prefix = selected_style.prompt_prefix if selected_style else ""
            style_suffix = selected_style.prompt_suffix if selected_style else ""
            style_name = selected_style.name if selected_style else "animation"

            # v2.0: 네거티브 프롬프트 (스타일에서 가져오기)
            negative_prompt = ""
            if selected_style and hasattr(selected_style, 'negative_prompt'):
                negative_prompt = selected_style.negative_prompt or ""

            # 설정 생성 (⭐ API 선택 + 병렬 처리 + 시드 잠금 적용)
            config = CharacterImageConfig(
                style=style_name,
                pose=char_pose,
                background=char_background,
                width=char_width,
                height=char_height,
                model=char_model,
                style_prefix=style_prefix,
                style_suffix=style_suffix,
                api_provider=char_api_provider,
                parallel_count=char_parallel,
                # v2.0: 시드 잠금 설정
                seed=char_locked_seed,
                negative_prompt=negative_prompt,
                seed_lock_enabled=char_seed_lock_enabled
            )

            generator = CharacterImageGenerator(str(project_path))

            generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 총 {total_chars}명 이미지 생성 시작")
            generation_logs.append(f"[{time.strftime('%H:%M:%S')}] API: {char_api_provider}, 병렬: {char_parallel}")
            generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 🔴 포즈: {char_pose}, 배경: {char_background}")
            # v2.0: 시드 잠금 로그
            if char_seed_lock_enabled:
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 🔒 시드 잠금: 활성화 (시드: {char_locked_seed if char_locked_seed else '자동'})")
            if negative_prompt:
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] ✅ 네거티브 프롬프트: {len(negative_prompt)}자")

            # 캐릭터 데이터를 딕셔너리 리스트로 변환
            char_dicts = []
            for char in selected_chars:
                char_dicts.append({
                    "id": char.id,
                    "name": char.name,
                    "name_en": char.name_en,
                    "visual_prompt": char.character_prompt,
                    "character_prompt": char.character_prompt
                })

            # ═══════════════════════════════════════════════════════════════
            # ⭐ v3.31: 유명인 일반화 필터 적용
            # ═══════════════════════════════════════════════════════════════
            if use_anonymization_filter:
                _sanitizer_model = st.session_state.get("char_sanitizer_model", get_sanitizer_recommended_model())
                _batch_custom_prompt = None
                if st.session_state.get("char_sanitizer_prompt_mode") == "사용자 정의":
                    _batch_custom_prompt = st.session_state.get("char_sanitizer_custom_prompt")
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 🛡️ 유명인 일반화 필터 적용 중... (모델: {_sanitizer_model})")

                with st.spinner(f"🛡️ AI({_sanitizer_model})가 캐릭터 이름을 분석하고 있습니다..."):
                    def on_sanitize_progress(current, total, char_name):
                        generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 🔍 분석 중: {char_name} ({current}/{total})")
                        log_area.code("\n".join(generation_logs[-15:]))

                    sanitized_chars, sanitize_results = sanitize_characters_batch(
                        char_dicts,
                        ai_model=_sanitizer_model,
                        on_progress=on_sanitize_progress,
                        prompt_template=_batch_custom_prompt
                    )

                    # 결과 로깅 및 매핑 생성
                    name_changed_count = sum(1 for r in sanitize_results if r.name_was_modified)
                    prompt_changed_count = sum(1 for r in sanitize_results if r.prompt_was_modified)

                    generation_logs.append(f"[{time.strftime('%H:%M:%S')}] ✅ 익명화 완료: 이름 {name_changed_count}명, 프롬프트 {prompt_changed_count}명 변환됨")

                    # 익명화 결과 표시
                    if name_changed_count > 0:
                        st.info(f"🛡️ **{name_changed_count}명**의 캐릭터 이름이 일반화되었습니다.")

                        # 변환 내역 표시
                        for orig_char, result in zip(char_dicts, sanitize_results):
                            if result.name_was_modified:
                                generation_logs.append(
                                    f"  - '{result.original_name}' → '{result.sanitized_name}' "
                                    f"(감지: {', '.join(result.name_detected_names) if result.name_detected_names else 'N/A'})"
                                )

                    # 익명화된 캐릭터 데이터 사용
                    char_dicts = sanitized_chars

                    # v2.0: 익명화된 프롬프트 적용 확인 로깅
                    for _ci, _cd in enumerate(char_dicts):
                        _anon_flag = _cd.get("_prompt_was_anonymized", False)
                        _vp_full = _cd.get("visual_prompt") or ""
                        generation_logs.append(
                            f"[{time.strftime('%H:%M:%S')}] [{_ci+1}] 익명화={_anon_flag}, "
                            f"visual_prompt ({len(_vp_full)}자): {_vp_full}"
                        )

                    # 상태 테이블도 업데이트 (원본 이름으로 표시하되, 익명화 정보 추가)
                    for orig_char, result in zip(selected_chars, sanitize_results):
                        original_name = orig_char.name
                        if result.name_was_modified:
                            char_statuses[original_name]["status"] = f"🛡️ → {result.sanitized_name[:15]}..."
                        else:
                            char_statuses[original_name]["status"] = "⏳ 대기"

                    log_area.code("\n".join(generation_logs[-15:]))

            # ═══════════════════════════════════════════════════════════════
            # ⭐ 포즈 모드에 따른 분기 처리
            # ═══════════════════════════════════════════════════════════════
            pose_mode = st.session_state.get("pose_mode", "")
            pose_analysis = st.session_state.get("pose_analysis_result", [])

            # ✅ 핵심 수정: AI 자동 분석 모드일 때만 ScenePoseGenerator 사용
            # "단일 포즈" 모드에서는 pose_analysis가 있어도 사용하지 않음!
            if pose_analysis and "AI 자동 분석" in pose_mode:
                # 씬별 포즈 이미지 생성 모드 (AI 분석 결과 사용)
                from utils.scene_pose_image_generator import ScenePoseImageGenerator

                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 🎭 AI 포즈 분석 결과 사용 - 씬별 이미지 생성")

                scene_pose_gen = ScenePoseImageGenerator(str(project_path))
                results = []

                for char_idx, char in enumerate(selected_chars):
                    # v3.31: 익명화된 데이터 사용 (해당 인덱스의 char_dicts 참조)
                    char_dict = char_dicts[char_idx]
                    original_char_name = char.name  # 원본 이름 (상태 표시용 + 포즈 매칭용)
                    char_name = char_dict.get("name", char.name)  # 익명화된 이름 (프롬프트용)
                    visual_prompt = char_dict.get("visual_prompt") or char_dict.get("character_prompt") or char.character_prompt

                    # v2.0: 포즈 매칭은 원본 이름 사용 (AI 분석 결과가 원본 이름 기준)
                    # 익명화된 이름으로 매칭하면 매칭 실패
                    match_name = original_char_name
                    # name_en도 매칭에 사용 (AI 분석이 영문 이름으로 저장했을 수 있음)
                    match_name_en = char.name_en if hasattr(char, 'name_en') else ""

                    # 해당 캐릭터의 포즈 할당 필터
                    char_pose_assignments = [
                        p for p in pose_analysis
                        if p.get("character", "").strip().lower().replace(" ", "") in match_name.strip().lower().replace(" ", "")
                        or match_name.strip().lower().replace(" ", "") in p.get("character", "").strip().lower().replace(" ", "")
                        or (match_name_en and (
                            p.get("character", "").strip().lower().replace(" ", "") in match_name_en.strip().lower().replace(" ", "")
                            or match_name_en.strip().lower().replace(" ", "") in p.get("character", "").strip().lower().replace(" ", "")
                        ))
                    ]

                    if not char_pose_assignments:
                        generation_logs.append(f"[{time.strftime('%H:%M:%S')}] ⚠️ {original_char_name}: 포즈 분석 결과 없음")
                        results.append({
                            "success": False,
                            "character_name": original_char_name,
                            "error": "포즈 분석 결과 없음"
                        })
                        on_char_complete(original_char_name, 0, False, "포즈 분석 결과 없음")
                        continue

                    unique_poses = list(set(p.get("pose", "standing") for p in char_pose_assignments))
                    generation_logs.append(f"[{time.strftime('%H:%M:%S')}] {original_char_name}: {len(unique_poses)}개 포즈 발견 ({', '.join(unique_poses)})")

                    on_char_start(original_char_name)
                    char_start_time = time.time()

                    # 진행률 콜백
                    def pose_progress(current, total, msg):
                        progress_pct = (char_idx / total_chars) + (current / total) / total_chars
                        overall_progress_bar.progress(min(progress_pct, 1.0))
                        overall_status.text(f"[{char_idx + 1}/{total_chars}] {msg}")
                        generation_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
                        log_area.code("\n".join(generation_logs[-15:]))

                    # 씬별 포즈 이미지 생성
                    pose_result = scene_pose_gen.generate_scene_pose_images(
                        character_name=char_name,
                        visual_prompt=visual_prompt,
                        pose_assignments=char_pose_assignments,
                        image_generator=generator,
                        config=config,
                        on_progress=pose_progress
                    )

                    char_elapsed = time.time() - char_start_time
                    images_generated = pose_result.get("images_generated", 0)

                    if images_generated > 0:
                        # 생성된 모든 이미지를 결과에 추가
                        for pose_id, img_path in pose_result.get("pose_images", {}).items():
                            if img_path:
                                results.append({
                                    "success": True,
                                    "character_name": original_char_name,
                                    "image_path": img_path,
                                    "pose": pose_id,
                                    "generation_time": char_elapsed / max(images_generated, 1)
                                })

                                # 이미지 미리보기
                                if Path(img_path).exists():
                                    image_preview.image(img_path, caption=f"{original_char_name} ({pose_id})", width=300)

                        generation_logs.append(f"[{time.strftime('%H:%M:%S')}] ✅ {original_char_name}: {images_generated}개 이미지 생성 완료 ({char_elapsed:.1f}초)")
                        on_char_complete(original_char_name, char_elapsed, True)
                    else:
                        results.append({
                            "success": False,
                            "character_name": original_char_name,
                            "error": "이미지 생성 실패"
                        })
                        generation_logs.append(f"[{time.strftime('%H:%M:%S')}] ❌ {original_char_name}: 이미지 생성 실패")
                        on_char_complete(original_char_name, char_elapsed, False, "이미지 생성 실패")

                    update_progress_ui()

            else:
                # ═══════════════════════════════════════════════════════════════
                # 기존 단일 포즈 배치 생성
                # ═══════════════════════════════════════════════════════════════
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 📷 단일 포즈 모드 - 모든 캐릭터에 '{char_pose}' 적용")

                # ⭐ 배치 생성 (콜백 포함)
                def on_batch_progress(current, total, result):
                    update_progress_ui()

                    # 이미지 미리보기
                    if result.get("success") and result.get("image_path"):
                        image_preview.image(result["image_path"], caption=result.get("character_name", ""), width=300)

                # v2.0: 시드 잠금 콜백 (첫 이미지 시드 자동 잠금 시 세션에 저장)
                def on_seed_locked(seed: int):
                    update_locked_seed_from_result(seed, key_prefix="char_batch_seed")
                    generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 🔒 첫 이미지 시드 자동 잠금: {seed}")

                results = generator.generate_batch(
                    characters=char_dicts,
                    config=config,
                    output_dir=output_dir,
                    on_progress=on_batch_progress,
                    on_start=on_char_start,
                    on_complete=on_char_complete,
                    on_seed_locked=on_seed_locked  # v2.0: 시드 잠금 콜백
                )

            # 결과 처리
            scene_linker = CharacterSceneLinker(project_path)
            linked_count = 0

            # 캐릭터 이름 → ID 맵핑 생성 (원본 이름 기준)
            char_name_to_id = {char.name: char.id for char in selected_chars}
            char_name_to_obj = {char.name: char for char in selected_chars}
            processed_chars = set()  # 이미 처리된 캐릭터 (성공)

            # v3.31: 익명화된 이름 → 원본 이름 매핑 생성
            anonymized_to_original = {}
            for i, char_dict in enumerate(char_dicts):
                if char_dict.get("_original_name"):
                    anonymized_to_original[char_dict.get("name", "")] = char_dict.get("_original_name")
                elif i < len(selected_chars):
                    anonymized_to_original[char_dict.get("name", "")] = selected_chars[i].name

            for result in results:
                result_char_name = result.get("character_name", "")
                # v3.31: 익명화된 이름을 원본 이름으로 변환
                char_name = anonymized_to_original.get(result_char_name, result_char_name)
                elapsed = result.get("generation_time", 0)

                # 캐릭터 객체 찾기
                char = char_name_to_obj.get(char_name)
                if not char:
                    # 부분 매칭 시도
                    for c in selected_chars:
                        if char_name.strip().lower() in c.name.strip().lower() or c.name.strip().lower() in char_name.strip().lower():
                            char = c
                            break

                if result.get("success"):
                    success_count += 1
                    if char:
                        processed_chars.add(char.name)

                        # 캐릭터에 이미지 경로 저장
                        manager.add_generated_image(char.id, result.get("image_path", ""))

                        # 이미지 스토리지에도 저장
                        save_character_image(char_name, result, project_path)

                        # 캐릭터 합성용 폴더에도 복사 (스토리보드 연동) - 첫 번째 이미지만
                        if char.name not in [c.name for c in selected_chars if char_name_to_id.get(c.name) and (project_path / "characters" / f"{char_name_to_id.get(c.name)}.png").exists()]:
                            try:
                                import shutil
                                characters_dir = project_path / "characters"
                                characters_dir.mkdir(parents=True, exist_ok=True)
                                src_path = Path(result.get("image_path", ""))
                                if src_path.exists():
                                    dst_path = characters_dir / f"{char.id}.png"
                                    shutil.copy2(src_path, dst_path)
                                    generation_logs.append(f"[{time.strftime('%H:%M:%S')}] {char.name} 이미지 → characters/ 폴더에 복사됨")
                            except Exception as copy_err:
                                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] {char.name} 복사 실패: {copy_err}")

                    # ⭐ 씬 자동 연결
                    result_pose = result.get("pose", char_pose)

                    # AI 분석 결과에서 이 포즈에 해당하는 씬 찾기
                    target_scenes = []
                    if pose_analysis:
                        for assignment in pose_analysis:
                            if (assignment.get("pose") == result_pose and
                                (assignment.get("character", "").strip().lower() in char_name.strip().lower() or
                                 char_name.strip().lower() in assignment.get("character", "").strip().lower())):
                                scene_id = assignment.get("scene_id")
                                if scene_id and scene_id not in target_scenes:
                                    target_scenes.append(scene_id)
                    else:
                        # 기존 pose_mapping 사용
                        pose_mapping = st.session_state.get("pose_scene_mapping", {})
                        for pose_key, pose_data in pose_mapping.items():
                            if result_pose == pose_key or pose_data.get("name") == result_pose:
                                target_scenes = pose_data.get("scenes", [])
                                break

                    # 씬 연결 시도 (Problem 62: 항상 시도, 실패 시 경고 표시)
                    # 캐릭터 등장 씬 정보가 없어도 linker가 씬 데이터에서 직접 검색 시도
                    link_result = scene_linker.link_character_image_to_scenes(
                        character_name=char_name,
                        image_path=result.get("image_path", ""),
                        pose=result_pose,
                        specific_scenes=target_scenes if target_scenes else None
                    )
                    if link_result.get("success"):
                        linked_count += len(link_result.get("linked_scenes", []))
                        generation_logs.append(
                            f"[{time.strftime('%H:%M:%S')}] {char_name} ({result_pose}) → 씬 {link_result.get('linked_scenes', [])}에 연결됨"
                        )
                    else:
                        # 연결 실패 경고 (Problem 62: 연결 실패 시 경고 표시)
                        generation_logs.append(
                            f"[{time.strftime('%H:%M:%S')}] ⚠️ {char_name}: 씬 연결 실패 - {link_result.get('error', '알 수 없는 오류')}"
                        )
                        print(f"[캐릭터 관리] ⚠️ {char_name}: 씬 연결 실패 - {link_result.get('error')}")

                    # 사용량 기록
                    provider_name_map = {"Together.ai FLUX": "together", "Google ImageFX": "imagefx"}
                    provider_name = provider_name_map.get(char_api_provider, char_api_provider.lower().replace(" ", "_"))
                    api_manager.record_usage(
                        provider=provider_name,
                        model_id=config.model,
                        function="image_generation",
                        units_used=1,
                        duration_seconds=elapsed,
                        success=True,
                        project_name=project_path.name,
                        step_name="character_compositing"
                    )
                else:
                    fail_count += 1

                    # 에러 기록
                    provider_name_map = {"Together.ai FLUX": "together", "Google ImageFX": "imagefx"}
                    provider_name = provider_name_map.get(char_api_provider, char_api_provider.lower().replace(" ", "_"))
                    api_manager.record_usage(
                        provider=provider_name,
                        model_id=config.model,
                        function="image_generation",
                        units_used=1,
                        duration_seconds=elapsed,
                        success=False,
                        error_message=result.get('error', 'Unknown'),
                        project_name=project_path.name,
                        step_name="character_compositing"
                    )

            # 씬 연결 결과 표시
            if linked_count > 0:
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 총 {linked_count}개 씬에 캐릭터 이미지 연결됨")

            # 완료 메시지
            overall_progress_bar.progress(1.0)
            if success_count > 0 and fail_count == 0:
                overall_status.success(f"✅ 캐릭터 이미지 생성 완료! 성공: {success_count}")
            elif success_count > 0:
                overall_status.warning(f"⚠️ 캐릭터 이미지 생성 완료! 성공: {success_count}, 실패: {fail_count}")
            else:
                overall_status.error(f"❌ 캐릭터 이미지 생성 실패: {fail_count}개")

            if success_count > 0:
                # 대표 이미지 자동 업데이트
                from utils.character_image_manager import CharacterImageManager
                img_mgr = CharacterImageManager(str(project_path))
                img_mgr.update_character_data_with_latest_images()
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 대표 이미지 자동 업데이트 완료")

                st.balloons()
                update_project_step(3)
                time.sleep(1)
                st.rerun()

        except Exception as e:
            overall_status.error(f"❌ 오류 발생: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

    # ================================================================
    # 생성된 이미지 갤러리 (개선: 전체 선택, 일괄 삭제, 대표 이미지)
    # ================================================================
    st.markdown("### 🖼️ 생성된 캐릭터 이미지 관리")

    from utils.character_image_manager import CharacterImageManager

    img_manager = CharacterImageManager(str(project_path))

    # 통계 표시
    stats = img_manager.get_statistics()

    stat_cols = st.columns(4)
    with stat_cols[0]:
        st.metric("총 이미지", f"{stats['total_images']}개")
    with stat_cols[1]:
        st.metric("캐릭터 수", f"{stats['total_characters']}명")
    with stat_cols[2]:
        st.metric("중복 캐릭터", f"{stats['duplicates']}개")
    with stat_cols[3]:
        st.metric("용량", f"{stats['total_size_mb']} MB")

    # 이미지 목록 가져오기
    all_char_images = img_manager.get_all_character_images()

    if not all_char_images:
        st.info("아직 생성된 캐릭터 이미지가 없습니다.")
    else:
        st.divider()

        # ============================================================
        # 전체 선택 및 일괄 작업 버튼
        # ============================================================
        action_cols = st.columns([2, 2, 2, 2])

        with action_cols[0]:
            select_all = st.checkbox(
                f"☑️ 전체 선택 ({len(all_char_images)}개)",
                key="char_img_select_all"
            )

        with action_cols[1]:
            delete_selected_btn = st.button(
                "🗑️ 선택 삭제",
                type="secondary",
                key="char_img_delete_selected"
            )

        with action_cols[2]:
            cleanup_btn = st.button(
                "🧹 중복 정리",
                help="각 캐릭터별 최신 1개만 유지",
                key="char_img_cleanup"
            )

        with action_cols[3]:
            refresh_btn = st.button(
                "🔄 새로고침",
                key="char_img_refresh"
            )

        # 선택 상태 초기화
        if "char_selected_images" not in st.session_state:
            st.session_state.char_selected_images = set()

        # 전체 선택 처리
        if select_all:
            st.session_state.char_selected_images = {img["filename"] for img in all_char_images}
        elif not select_all and "char_img_select_all" in st.session_state:
            # 체크 해제 시 선택 초기화
            if len(st.session_state.char_selected_images) == len(all_char_images):
                st.session_state.char_selected_images = set()

        # 삭제 확인 및 처리
        if delete_selected_btn:
            selected_files = list(st.session_state.char_selected_images)
            if selected_files:
                with st.spinner(f"{len(selected_files)}개 이미지 삭제 중..."):
                    result = img_manager.delete_images(selected_files)
                    if result["deleted"]:
                        st.success(f"✅ {len(result['deleted'])}개 이미지 삭제됨")
                        st.session_state.char_selected_images.clear()
                        img_manager.update_character_data_with_latest_images()
                        st.rerun()
                    if result["failed"]:
                        st.error(f"❌ {len(result['failed'])}개 삭제 실패")
            else:
                st.warning("삭제할 이미지를 선택해주세요.")

        # 중복 정리 처리
        if cleanup_btn:
            with st.spinner("중복 이미지 정리 중..."):
                result = img_manager.cleanup_duplicate_images(keep_count=1)
                if result["deleted"]:
                    st.success(f"✅ {len(result['deleted'])}개 중복 이미지 삭제됨")
                    st.rerun()
                else:
                    st.info("정리할 중복 이미지가 없습니다.")

        # 새로고침 처리
        if refresh_btn:
            st.rerun()

        # 선택된 이미지 수 표시
        selected_count = len(st.session_state.char_selected_images)
        if selected_count > 0:
            st.info(f"📌 {selected_count}개 이미지 선택됨")

        st.divider()

        # ============================================================
        # 캐릭터별 이미지 그리드
        # ============================================================
        char_groups = {}
        for img in all_char_images:
            char_name = img["character_name"]
            if char_name not in char_groups:
                char_groups[char_name] = []
            char_groups[char_name].append(img)

        for char_name, char_images in char_groups.items():
            with st.expander(f"👤 {char_name} ({len(char_images)}개 이미지)", expanded=False):
                # 이미지 그리드 (최대 6열, 작은 썸네일)
                num_cols = min(len(char_images), 6)
                img_cols = st.columns(num_cols)

                for i, img in enumerate(char_images):
                    with img_cols[i % num_cols]:
                        # 체크박스
                        is_selected = img["filename"] in st.session_state.char_selected_images
                        if st.checkbox(
                            "선택",
                            value=is_selected,
                            key=f"char_chk_{img['filename']}",
                            label_visibility="collapsed"
                        ):
                            st.session_state.char_selected_images.add(img["filename"])
                        else:
                            st.session_state.char_selected_images.discard(img["filename"])

                        # 이미지 표시 (작은 썸네일 - 클릭 시 확대)
                        # v3.0: Streamlit 네이티브 확대 기능 사용
                        try:
                            render_clickable_thumbnail(
                                img["path"],
                                caption=img.get("filename", ""),
                                width=100,
                                key=f"gallery_img_{img['filename']}"
                            )
                        except Exception:
                            st.error("❌")

                        # 대표 이미지 배지
                        if img["is_representative"]:
                            st.markdown("⭐ **대표 이미지**")

                        # 메타 정보
                        st.caption(f"📅 {img['created_at']}")
                        st.caption(f"📦 {img['size_bytes'] // 1024} KB")

                        # 개별 작업 버튼
                        btn_cols = st.columns(2)
                        with btn_cols[0]:
                            if not img["is_representative"]:
                                if st.button("⭐", key=f"char_rep_{img['filename']}", help="대표 이미지로 설정"):
                                    img_manager.set_representative_image(char_name, img["filename"])
                                    st.rerun()
                        with btn_cols[1]:
                            if st.button("🗑️", key=f"char_del_{img['filename']}", help="삭제"):
                                img_manager.delete_images([img["filename"]])
                                img_manager.update_character_data_with_latest_images()
                                st.rerun()

        st.info("💡 이제 '이미지 생성' 페이지에서 배경을 생성한 후 합성할 수 있습니다.")

# === 탭 4: 포즈 설정 (Problem 56) ===
with tab4:
    st.subheader("🧍 씬별 포즈 설정")

    st.info("""
    **포즈 설정 기능:**
    - 씬 분위기(mood)에 맞는 포즈 자동 추천
    - 랜덤 포즈 일괄 배정
    - 수동 포즈 지정
    """)

    # 씬 데이터 로드
    scenes_data = load_scene_analysis_data()

    if not scenes_data:
        st.warning("⚠️ 씬 분석 결과가 없습니다. 먼저 3.5단계에서 씬 분석을 실행하세요.")
        st.page_link("pages/3.5_🎬_씬_분석.py", label="🎬 3.5단계: 씬 분석으로 이동", icon="➡️")
    else:
        st.success(f"✅ {len(scenes_data)}개 씬 로드됨")

        # 포즈 템플릿 목록 표시
        with st.expander("📋 사용 가능한 포즈 목록", expanded=False):
            all_poses = pose_manager.get_all_poses()
            cols = st.columns(3)
            for i, pose in enumerate(all_poses):
                with cols[i % 3]:
                    st.markdown(f"**{pose.name_ko}** (`{pose.id}`)")
                    st.caption(pose.description)
                    st.caption(f"적합한 분위기: {', '.join(pose.suitable_moods[:3])}")

        st.divider()

        # === 랜덤 포즈 일괄 배정 ===
        st.markdown("### 🎲 랜덤 포즈 일괄 배정")

        col_opt1, col_opt2 = st.columns(2)

        with col_opt1:
            avoid_duplicates = st.checkbox(
                "연속 중복 방지",
                value=True,
                help="같은 포즈가 연속으로 배정되는 것을 방지합니다.",
                key="pose_avoid_dup"
            )

        with col_opt2:
            max_consecutive = st.slider(
                "최대 연속 허용 횟수",
                min_value=1,
                max_value=5,
                value=2,
                key="pose_max_consecutive",
                disabled=not avoid_duplicates
            )

        if st.button("🎲 분위기 기반 랜덤 포즈 배정", type="primary", use_container_width=True, key="assign_random_poses"):
            with st.spinner("포즈 배정 중..."):
                assignments = pose_manager.assign_random_poses_to_scenes(
                    scenes=scenes_data,
                    avoid_consecutive_duplicates=avoid_duplicates,
                    max_consecutive=max_consecutive
                )

                # 세션에 저장
                st.session_state.pose_assignments = assignments

                st.success(f"✅ {len(assignments)}개 씬에 포즈 배정 완료!")

        # 배정 결과 표시
        if "pose_assignments" in st.session_state and st.session_state.pose_assignments:
            assignments = st.session_state.pose_assignments

            st.divider()
            st.markdown("### 📊 씬별 포즈 배정 결과")

            # 통계 표시
            stats = pose_manager.get_mood_statistics(assignments)
            st.markdown("**포즈 사용 통계:**")
            stat_cols = st.columns(min(len(stats), 6))
            for i, (pose_id, count) in enumerate(stats.items()):
                pose = pose_manager.get_pose_by_id(pose_id)
                pose_name = pose.name_ko if pose else pose_id
                with stat_cols[i % len(stat_cols)]:
                    st.metric(pose_name, f"{count}회")

            st.divider()

            # 씬별 상세 (편집 가능)
            for i, assignment in enumerate(assignments):
                col_scene, col_mood, col_pose, col_action = st.columns([2, 1.5, 2, 1])

                with col_scene:
                    st.markdown(f"**씬 {assignment.scene_number}**: {assignment.scene_title[:20]}...")

                with col_mood:
                    st.caption(f"분위기: {assignment.mood}")

                with col_pose:
                    # 포즈 선택 드롭다운
                    pose_options = pose_manager.get_pose_options_for_dropdown()
                    current_idx = next(
                        (idx for idx, (_, pid) in enumerate(pose_options) if pid == assignment.assigned_pose_id),
                        0
                    )
                    selected = st.selectbox(
                        "포즈",
                        options=[p[1] for p in pose_options],
                        format_func=lambda x: next((p[0] for p in pose_options if p[1] == x), x),
                        index=current_idx,
                        key=f"pose_select_{i}",
                        label_visibility="collapsed"
                    )

                    # 변경 감지
                    if selected != assignment.assigned_pose_id:
                        st.session_state.pose_assignments[i].assigned_pose_id = selected
                        pose = pose_manager.get_pose_by_id(selected)
                        st.session_state.pose_assignments[i].assigned_pose_name = pose.name_ko if pose else selected
                        st.session_state.pose_assignments[i].is_manual = True

                with col_action:
                    if assignment.is_manual:
                        st.caption("✏️ 수동")
                    else:
                        st.caption("🎲 자동")

            st.divider()

            # 저장 버튼
            col_save, col_export = st.columns(2)

            with col_save:
                if st.button("💾 포즈 배정 저장", use_container_width=True, key="save_pose_assignments"):
                    # 프로젝트에 저장
                    output_path = pose_manager.export_assignments_to_json(
                        assignments,
                        project_path / "analysis" / "pose_assignments.json"
                    )
                    if output_path:
                        st.success(f"✅ 저장 완료: {output_path.name}")
                    else:
                        st.error("저장 실패")

            with col_export:
                # JSON 다운로드
                assignments_json = json.dumps(
                    [a.to_dict() for a in assignments],
                    ensure_ascii=False,
                    indent=2
                )
                st.download_button(
                    "📥 JSON 다운로드",
                    data=assignments_json,
                    file_name="pose_assignments.json",
                    mime="application/json",
                    use_container_width=True,
                    key="download_pose_json"
                )

        st.divider()

        # === 분위기별 추천 포즈 미리보기 ===
        st.markdown("### 💡 분위기별 추천 포즈")

        mood_options = list(pose_manager.mood_to_pose_mapping.keys())
        selected_mood = st.selectbox(
            "분위기 선택",
            options=mood_options,
            key="preview_mood"
        )

        if selected_mood:
            suitable_poses = pose_manager.get_suitable_poses_for_mood(selected_mood)
            st.markdown(f"**'{selected_mood}'에 적합한 포즈:**")

            pose_cols = st.columns(min(len(suitable_poses), 4))
            for i, pose in enumerate(suitable_poses):
                with pose_cols[i % len(pose_cols)]:
                    st.markdown(f"**{pose.name_ko}**")
                    st.caption(pose.description)
                    st.code(pose.prompt_modifier[:50] + "...", language=None)

# === 탭 5: 가져오기 ===
with tab5:
    st.subheader("📥 캐릭터 가져오기")

    # ═══════════════════════════════════════════════════════════════════
    # v3.36: 프로젝트 경로 확인 및 디버깅 정보
    # ═══════════════════════════════════════════════════════════════════

    # 프로젝트 경로 유효성 확인
    if project_path is None:
        st.error("❌ 프로젝트 경로가 설정되지 않았습니다.")
        st.info("👈 사이드바에서 프로젝트와 영상을 다시 선택해주세요.")

        with st.expander("🔍 디버그 정보"):
            st.write("**Session State 키:**")
            st.write(f"- current_channel: {st.session_state.get('current_channel', 'None')}")
            st.write(f"- current_video: {st.session_state.get('current_video', 'None')}")
            st.write(f"- current_project_path: {st.session_state.get('current_project_path', 'None')}")

        st.stop()

    st.caption(f"📂 프로젝트: `{project_path}`")

    st.info("""
    **캐릭터를 가져올 수 있는 방법:**
    - 🔄 씬 분석 결과에서 자동 가져오기
    - 📁 JSON 파일 업로드
    - 📊 CSV 파일 업로드
    - ✏️ JSON 직접 입력
    """)

    # 가져오기 방식 선택
    import_method = st.radio(
        "가져오기 방식",
        ["🔄 씬 분석 결과", "📁 JSON 파일", "📊 CSV 파일", "✏️ JSON 직접 입력"],
        horizontal=True,
        key="char_import_method"
    )

    characters_to_import = None

    # === 씬 분석 결과 ===
    if "씬 분석" in import_method:
        st.markdown("### 🔄 씬 분석 결과에서 가져오기")

        # ═══════════════════════════════════════════════════════════════
        # v3.60: 캐싱된 함수 사용 (성능 최적화)
        # v3.61: analysis_path 정의 추가 (버그 수정)
        # ═══════════════════════════════════════════════════════════════
        from pathlib import Path
        analysis_path = Path(project_path) / "analysis" / "characters.json"

        analysis_chars, data_source = _cached_load_characters_from_analysis(str(project_path))

        # 파일에서 못 찾으면 세션에서 로드 시도 (fallback)
        if not analysis_chars:
            session_keys = ["characters", "scene_characters", "extracted_characters"]
            for key in session_keys:
                if key in st.session_state and st.session_state[key]:
                    session_data = st.session_state[key]
                    if isinstance(session_data, list) and len(session_data) > 0:
                        analysis_chars = session_data
                        data_source = f"💾 세션: {key}"
                        break

        # 결과 표시
        if analysis_chars and len(analysis_chars) > 0:
            # visual_prompt 통계 계산
            chars_with_prompt = sum(1 for c in analysis_chars if c.get("visual_prompt") or c.get("character_prompt"))
            chars_without_prompt = len(analysis_chars) - chars_with_prompt

            st.success(f"📊 씬 분석에서 **{len(analysis_chars)}명**의 캐릭터가 발견되었습니다.")
            st.caption(f"📂 데이터 소스: {data_source}")

            if chars_without_prompt > 0:
                st.warning(f"⚠️ {chars_without_prompt}명의 캐릭터에 visual_prompt가 없습니다.")

                # Visual Prompt 일괄 생성 버튼
                st.markdown("---")
                st.markdown("##### 🎨 Visual Prompt 자동 생성")

                col_model, col_btn = st.columns([2, 1])

                with col_model:
                    from utils.ai_model_config import AVAILABLE_MODELS
                    model_options = {
                        "⚡ 빠름 (Haiku)": "claude-3-5-haiku-20241022",
                        "⚖️ 균형 (Sonnet)": "claude-sonnet-4-20250514"
                    }
                    selected_label = st.selectbox(
                        "AI 모델 선택",
                        options=list(model_options.keys()),
                        index=0,
                        key="visual_prompt_model",
                        help="Haiku가 빠르고 저렴합니다"
                    )
                    selected_model = model_options[selected_label]

                with col_btn:
                    st.write("")  # 정렬용 빈 공간
                    if st.button("🎨 Visual Prompt 생성", type="primary", key="gen_visual_prompts"):
                        from utils.character_visual_prompt import generate_character_visual_prompts

                        # 스크립트 컨텍스트 수집
                        context = ""
                        script_path = project_path / "scripts" / "full_script.txt"
                        if script_path.exists():
                            try:
                                context = script_path.read_text(encoding="utf-8")[:2000]
                            except:
                                pass

                        # visual_prompt가 없는 캐릭터만 추출
                        chars_to_process = [
                            c for c in analysis_chars
                            if not c.get('visual_prompt') and not c.get('character_prompt')
                        ]

                        with st.spinner(f"Visual Prompt 생성 중... ({len(chars_to_process)}명)"):
                            updated_chars = generate_character_visual_prompts(
                                chars_to_process,
                                context=context,
                                model=selected_model
                            )

                            # 원본 리스트에 결과 반영
                            result_map = {c['name']: c.get('visual_prompt', '') for c in updated_chars}
                            for char in analysis_chars:
                                name = char.get('name', '')
                                if name in result_map and result_map[name]:
                                    char['visual_prompt'] = result_map[name]

                            # 파일에 저장
                            try:
                                with open(analysis_path, "w", encoding="utf-8") as f:
                                    json.dump(analysis_chars, f, ensure_ascii=False, indent=2)
                                st.success(f"✅ {len(chars_to_process)}명의 visual_prompt 생성 완료!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"저장 실패: {e}")
                st.markdown("---")
            else:
                st.info(f"✅ 모든 캐릭터에 visual_prompt가 있습니다.")

            characters_to_import = analysis_chars

            # 캐릭터 미리보기
            st.markdown("#### 👤 발견된 캐릭터 목록")
            for i, char in enumerate(analysis_chars[:5]):  # 최대 5개 미리보기
                name = char.get('name', 'Unknown')
                name_en = char.get('name_en', '')
                has_prompt = bool(char.get('visual_prompt') or char.get('character_prompt'))
                prompt_status = "✅" if has_prompt else "⚠️"

                st.write(f"{i+1}. {prompt_status} **{name}** ({name_en})")
                if char.get('description'):
                    st.caption(f"   {char.get('description', '')[:80]}")
                if has_prompt:
                    prompt_preview = (char.get('visual_prompt') or char.get('character_prompt', ''))[:100]
                    st.caption(f"   🎨 `{prompt_preview}...`")

            if len(analysis_chars) > 5:
                st.caption(f"... 외 {len(analysis_chars) - 5}명 더 있음")
        else:
            st.warning("⚠️ 씬 분석 결과에서 캐릭터를 찾을 수 없습니다.")

            # v3.36: scenes.json에서 수동 추출 버튼
            scenes_path = project_path / "analysis" / "scenes.json"
            if scenes_path.exists():
                st.info("💡 씬 데이터에서 캐릭터를 수동으로 추출할 수 있습니다.")
                if st.button("🔄 씬 데이터에서 캐릭터 추출", key="manual_extract_chars"):
                    try:
                        with open(scenes_path, "r", encoding="utf-8") as f:
                            scenes_data = json.load(f)
                        extracted = _extract_characters_from_scenes(scenes_data)
                        if extracted:
                            # 파일로 저장
                            analysis_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(analysis_path, "w", encoding="utf-8") as f:
                                json.dump(extracted, f, ensure_ascii=False, indent=2)
                            st.success(f"✅ {len(extracted)}명의 캐릭터가 추출되어 저장되었습니다!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.warning("씬 데이터에서 캐릭터 정보를 찾을 수 없습니다.")
                    except Exception as e:
                        st.error(f"추출 실패: {e}")
            else:
                st.page_link("pages/3.5_🎬_씬_분석.py", label="🎬 3.5단계: 씬 분석으로 이동", icon="➡️")

            # 🔴 v3.36: 향상된 디버그 정보
            with st.expander("🔍 디버그 정보", expanded=False):
                st.write("**📁 파일 상태:**")

                # characters.json 확인
                st.write(f"- characters.json: {'✅ 존재' if analysis_path.exists() else '❌ 없음'}")
                if analysis_path.exists():
                    try:
                        with open(analysis_path, "r", encoding="utf-8") as f:
                            raw = json.load(f)
                        st.write(f"  - 내용: {len(raw) if isinstance(raw, list) else 'dict'}")
                        if raw:
                            st.json(raw[:2] if isinstance(raw, list) else raw)
                    except Exception as e:
                        st.write(f"  - 읽기 오류: {e}")

                # scenes.json 확인
                st.write(f"- scenes.json: {'✅ 존재' if scenes_path.exists() else '❌ 없음'}")
                if scenes_path.exists():
                    try:
                        with open(scenes_path, "r", encoding="utf-8") as f:
                            scenes_raw = json.load(f)
                        scene_count = len(scenes_raw) if isinstance(scenes_raw, list) else len(scenes_raw.get('scenes', []))
                        st.write(f"  - 씬 수: {scene_count}개")

                        # 샘플 씬의 캐릭터 필드 확인
                        sample_scenes = scenes_raw[:2] if isinstance(scenes_raw, list) else scenes_raw.get('scenes', [])[:2]
                        if sample_scenes:
                            st.write("  - **샘플 씬 캐릭터 필드:**")
                            for s in sample_scenes:
                                sid = s.get('scene_number', s.get('scene_id', '?'))
                                chars = s.get('characters', s.get('character_names', 'N/A'))
                                st.write(f"    - 씬 {sid}: {chars}")
                    except Exception as e:
                        st.write(f"  - 읽기 오류: {e}")

                st.write("**💾 세션 상태:**")
                for key in ["characters", "scene_characters", "extracted_characters"]:
                    if key in st.session_state:
                        val = st.session_state[key]
                        st.write(f"- {key}: {len(val) if isinstance(val, list) else type(val).__name__}")
                    else:
                        st.write(f"- {key}: 없음")

                st.write(f"**📂 프로젝트 경로:** `{project_path}`")

    # === JSON 파일 업로드 ===
    elif "JSON 파일" in import_method:
        st.markdown("### 📁 JSON 파일 업로드")

        st.caption("""
        **JSON 형식 예시:**
        ```json
        [
          {"name": "김철수", "name_en": "Kim Cheolsu", "role": "주연", "description": "...", "character_prompt": "..."},
          {"name": "이영희", "name_en": "Lee Younghee", ...}
        ]
        ```
        """)

        uploaded_json = st.file_uploader(
            "JSON 파일 선택",
            type=["json"],
            key="char_json_upload"
        )

        if uploaded_json:
            try:
                characters_to_import = json.load(uploaded_json)
                st.success(f"✅ {len(characters_to_import)}명의 캐릭터 로드됨")
            except Exception as e:
                st.error(f"JSON 파싱 실패: {e}")

    # === CSV 파일 업로드 ===
    elif "CSV 파일" in import_method:
        st.markdown("### 📊 CSV 파일 업로드")

        st.caption("""
        **CSV 컬럼:** name, name_en, role, description, appearance, character_prompt, nationality, era
        """)

        uploaded_csv = st.file_uploader(
            "CSV 파일 선택",
            type=["csv"],
            key="char_csv_upload"
        )

        if uploaded_csv:
            try:
                import pandas as pd
                import io

                df = pd.read_csv(io.BytesIO(uploaded_csv.read()))
                characters_to_import = df.to_dict('records')

                st.success(f"✅ {len(characters_to_import)}명의 캐릭터 로드됨")

                # 컬럼 매핑 확인
                st.write("**감지된 컬럼:**", list(df.columns))

                # 미리보기
                with st.expander("📋 데이터 미리보기"):
                    st.dataframe(df.head(5))

            except Exception as e:
                st.error(f"CSV 파싱 실패: {e}")

    # === JSON 직접 입력 ===
    elif "직접 입력" in import_method:
        st.markdown("### ✏️ JSON 직접 입력")

        json_text = st.text_area(
            "캐릭터 JSON 배열",
            height=300,
            placeholder='''[
  {
    "name": "김철수",
    "name_en": "Kim Cheolsu",
    "role": "주연",
    "description": "40대 세무사",
    "nationality": "한국",
    "era": "현대",
    "appearance": "검은 머리, 안경 착용",
    "character_prompt": "Korean man, 45 years old, short black hair, rectangular glasses, wearing a navy suit"
  }
]''',
            key="char_json_input"
        )

        if json_text:
            try:
                characters_to_import = json.loads(json_text)
                st.success(f"✅ JSON 파싱 성공: {len(characters_to_import)}명")
            except json.JSONDecodeError as e:
                st.error(f"JSON 파싱 실패: {e}")

    # === 가져오기 미리보기 및 실행 ===
    if characters_to_import and isinstance(characters_to_import, list) and len(characters_to_import) > 0:
        st.markdown("---")
        st.markdown("### 📋 가져올 캐릭터 미리보기")

        st.write(f"**총 {len(characters_to_import)}명의 캐릭터**")

        # 미리보기
        with st.expander("캐릭터 상세 보기", expanded=True):
            for i, char in enumerate(characters_to_import[:10]):
                st.markdown(f"**{i+1}. {char.get('name', '이름 없음')}** ({char.get('name_en', '')})")
                if char.get('description'):
                    st.caption(char.get('description')[:100])
                if char.get('character_prompt'):
                    st.code(char.get('character_prompt')[:150] + "...", language=None)
                st.markdown("---")

            if len(characters_to_import) > 10:
                st.caption(f"... 외 {len(characters_to_import) - 10}명 더 있음")

        # 가져오기 실행 버튼
        if st.button("📥 캐릭터 가져오기", type="primary", use_container_width=True, key="import_chars_btn"):
            imported = manager.import_from_analysis(characters_to_import)
            if imported > 0:
                st.success(f"✅ {imported}명의 캐릭터를 가져왔습니다!")
                st.balloons()
                time.sleep(1)
                st.rerun()
            else:
                st.info("모든 캐릭터가 이미 등록되어 있습니다.")

# === 탭 6: 대표 캐릭터 ===
with tab6:
    st.subheader("⭐ 대표 캐릭터")

    st.info("""
    **대표 캐릭터란?**

    채널이나 영상의 시그니처 캐릭터입니다.
    등장인물이 없는 설명형 콘텐츠(경제, 브랜드 소개 등)에서도
    일관된 캐릭터를 사용할 수 있습니다.
    """)

    # 라이브러리 -> 프로젝트 동기화 함수
    def sync_library_to_project(lib_char_id: str, rep_manager_instance=None):
        """라이브러리 캐릭터를 현재 프로젝트로 동기화"""
        lib_char_data = rep_library.get_character(lib_char_id)
        if not lib_char_data:
            return False

        try:
            from utils.representative_character import RepresentativeCharacter
            import uuid

            # RepresentativeCharacter 객체 생성
            synced_char = RepresentativeCharacter(
                id=lib_char_data.get("id", str(uuid.uuid4())),
                name=lib_char_data.get("name", "캐릭터"),
                description=lib_char_data.get("description", ""),
                base_prompt=lib_char_data.get("prompt", ""),
                negative_prompt=lib_char_data.get("negative_prompt", ""),
                style_preset=lib_char_data.get("style_preset", ""),
                style_suffix=lib_char_data.get("style_suffix", "")
            )

            # 기본 이미지 복사
            lib_base_images = lib_char_data.get("base_images", [])
            for img_info in lib_base_images:
                if isinstance(img_info, dict):
                    img_path = img_info.get("path", "")
                    img_type = img_info.get("type", "front")
                else:
                    img_path = str(img_info)
                    img_type = "front"

                if img_path and os.path.exists(img_path):
                    synced_char.base_images[img_type] = img_path

            # 프로젝트 매니저에 설정 (매니저 인스턴스가 있으면 사용, 없으면 새로 생성)
            if rep_manager_instance:
                rep_manager_instance.set_character(synced_char)
            else:
                _rep_manager = get_rep_char_manager(str(project_path))
                _rep_manager.set_character(synced_char)

            print(f"[RepChar] 라이브러리 캐릭터 '{lib_char_data.get('name')}' -> 프로젝트 동기화 완료")
            return True
        except Exception as e:
            print(f"[RepChar] 동기화 실패: {e}")
            return False

    # ============================================================
    # 📁 캐릭터 라이브러리 선택
    # ============================================================
    st.markdown("### 📁 캐릭터 라이브러리")

    rep_library = get_rep_char_library()
    all_characters = rep_library.get_all_characters()
    selected_lib_id = rep_library.get_selected_character_id()

    with st.container(border=True):
        if all_characters:
            # 캐릭터 선택 UI
            col_sel1, col_sel2, col_sel3 = st.columns([3, 1, 1])

            with col_sel1:
                # 드롭다운으로 선택
                char_options = {c["name"]: c["id"] for c in all_characters}
                char_names = ["➕ 새 캐릭터 정의..."] + list(char_options.keys())

                # 현재 선택된 캐릭터의 인덱스
                current_index = 0
                if selected_lib_id:
                    for i, c in enumerate(all_characters):
                        if c["id"] == selected_lib_id:
                            current_index = i + 1  # "새 캐릭터 정의" 옵션 때문에 +1
                            break

                selected_name = st.selectbox(
                    "저장된 대표 캐릭터 선택",
                    char_names,
                    index=current_index,
                    key="rep_char_library_select"
                )

                if selected_name == "➕ 새 캐릭터 정의...":
                    st.session_state["rep_char_mode"] = "create"
                    new_selected_id = None
                else:
                    new_selected_id = char_options.get(selected_name)
                    if new_selected_id and new_selected_id != selected_lib_id:
                        rep_library.select_character(new_selected_id)
                        # 프로젝트에 동기화
                        sync_library_to_project(new_selected_id)
                        st.rerun()

            with col_sel2:
                if selected_lib_id and st.button("📋 복제", use_container_width=True, key="rep_char_duplicate"):
                    new_id = rep_library.duplicate_character(selected_lib_id)
                    if new_id:
                        rep_library.select_character(new_id)
                        st.success("캐릭터가 복제되었습니다!")
                        time.sleep(0.5)
                        st.rerun()

            with col_sel3:
                if selected_lib_id:
                    if st.button("🗑️ 삭제", use_container_width=True, key="rep_char_lib_delete"):
                        if st.session_state.get("confirm_lib_delete") == selected_lib_id:
                            rep_library.delete_character(selected_lib_id)
                            st.warning("삭제되었습니다.")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.session_state["confirm_lib_delete"] = selected_lib_id
                            st.warning("다시 클릭하면 삭제됩니다.")

            # 캐릭터 카드 그리드 (썸네일 표시)
            if len(all_characters) > 1:
                st.markdown("---")
                st.caption("📌 저장된 캐릭터 목록 (클릭하여 선택)")

                cols = st.columns(min(len(all_characters), 6))

                for i, char in enumerate(all_characters):
                    with cols[i % 6]:
                        # 썸네일 (클릭 시 확대) - v3.0: 네이티브 방식
                        thumb_path = rep_library.get_thumbnail_path(char["id"])
                        if thumb_path and os.path.exists(thumb_path):
                            render_clickable_thumbnail(thumb_path, width=80, key=f"lib_thumb_{char['id']}")
                        else:
                            st.markdown("🎭", help="썸네일 없음")

                        # 이름 (선택된 캐릭터 강조)
                        if char["id"] == selected_lib_id:
                            st.markdown(f"**⭐ {char['name'][:10]}**")
                        else:
                            if st.button(char["name"][:10], key=f"select_lib_{char['id']}", use_container_width=True):
                                rep_library.select_character(char["id"])
                                # 프로젝트에 동기화
                                sync_library_to_project(char["id"])
                                st.rerun()

                        # 사용 횟수
                        st.caption(f"사용: {char.get('usage_count', 0)}회")

        else:
            st.info("저장된 대표 캐릭터가 없습니다. 아래에서 새 캐릭터를 정의해주세요.")
            st.session_state["rep_char_mode"] = "create"

            # 기존 프로젝트 캐릭터 마이그레이션 제안
            temp_manager = get_rep_char_manager(str(project_path))
            existing_project_char = temp_manager.get_character()
            if existing_project_char and existing_project_char.base_prompt:
                with st.container(border=True):
                    st.warning(f"💡 프로젝트에 기존 대표 캐릭터 '{existing_project_char.name}'이(가) 있습니다.")
                    if st.button("📥 라이브러리로 마이그레이션", key="migrate_char_btn"):
                        # 기존 캐릭터를 라이브러리로 마이그레이션
                        new_id = rep_library.migrate_from_old_format(
                            old_data={
                                "name": existing_project_char.name,
                                "description": existing_project_char.description,
                                "base_prompt": existing_project_char.base_prompt,
                                "negative_prompt": existing_project_char.negative_prompt,
                                "style_preset": existing_project_char.style_preset,
                                "base_images": existing_project_char.base_images
                            },
                            project_path=str(project_path)
                        )
                        if new_id:
                            rep_library.select_character(new_id)
                            st.success(f"✅ '{existing_project_char.name}'이(가) 라이브러리에 저장되었습니다!")
                            time.sleep(0.5)
                            st.rerun()

    st.markdown("---")

    # 매니저 초기화 (프로젝트별 씬 액션 관리용)
    rep_manager = get_rep_char_manager(str(project_path))

    # 라이브러리에서 선택된 캐릭터가 있으면 매니저에 동기화 (페이지 로드시 한번)
    if selected_lib_id:
        current_char = rep_manager.get_character()
        if not current_char or current_char.id != selected_lib_id:
            sync_library_to_project(selected_lib_id, rep_manager)

    # ============================================================
    # 1️⃣ 대표 캐릭터 정의
    # ============================================================
    st.markdown("### 1️⃣ 대표 캐릭터 정의")

    with st.container(border=True):
        existing_char = rep_manager.get_character()

        col_def1, col_def2 = st.columns([1, 1])

        with col_def1:
            rep_char_name = st.text_input(
                "캐릭터 이름",
                value=existing_char.name if existing_char else "",
                placeholder="예: 채널 MC 마루",
                key="rep_char_name"
            )

            rep_char_description = st.text_area(
                "캐릭터 설명 (간단히)",
                value=existing_char.description if existing_char else "",
                placeholder="예: 30대 남성, 경제 전문가, 안경 착용",
                height=80,
                key="rep_char_description"
            )

        with col_def2:
            # ✅ 수정: 스타일 관리에서 캐릭터 스타일 동적 로드
            character_styles = get_styles_by_segment("character")

            if not character_styles:
                st.warning("캐릭터 스타일이 없습니다. 스타일 관리에서 추가해주세요.")
                # 폴백: STYLE_PRESETS 사용
                style_options = {k: v["name"] for k, v in STYLE_PRESETS.items()}
                style_data_map = {k: v for k, v in STYLE_PRESETS.items()}
            else:
                # 스타일 관리에서 가져온 스타일 사용
                style_options = {
                    style.id: f"{style.name_ko} ({style.name})"
                    for style in character_styles
                }
                style_data_map = {
                    style.id: {
                        "name": f"{style.name_ko} ({style.name})",
                        "suffix": style.prompt_suffix,
                        "prefix": style.prompt_prefix,
                        "negative": style.negative_prompt
                    }
                    for style in character_styles
                }

            # 현재 선택된 스타일 인덱스 찾기
            current_style_idx = 0
            if existing_char and existing_char.style_preset in style_options:
                current_style_idx = list(style_options.keys()).index(existing_char.style_preset)
            else:
                # 기본 스타일 찾기
                for idx, style in enumerate(character_styles if character_styles else []):
                    if style.is_default:
                        current_style_idx = idx
                        break

            selected_style = st.selectbox(
                "🎨 스타일 프리셋 (스타일 관리에서 로드)",
                options=list(style_options.keys()),
                format_func=lambda x: style_options.get(x, x),
                index=current_style_idx,
                key="rep_char_style"
            )

            # 선택된 스타일 정보 표시
            selected_style_data = style_data_map.get(selected_style, {})
            suffix_preview = selected_style_data.get('suffix', '')[:50]
            st.caption(f"스타일 suffix: {suffix_preview}...")

            # 스타일 관리 페이지 링크
            if character_styles:
                st.caption("💡 스타일 추가/수정: [스타일 관리] 페이지")

        st.markdown("**📝 캐릭터 생성 프롬프트 (상세)**")

        with st.expander("💡 프롬프트 작성 가이드", expanded=False):
            st.markdown("""
            **좋은 캐릭터 프롬프트 예시:**

            ```
            A professional Korean male character in his 30s,
            wearing round black-framed glasses and a navy blue suit with white shirt,
            clean-cut short black hair neatly styled,
            friendly and trustworthy expression,
            upper body portrait, white background
            ```

            **포함하면 좋은 요소:**
            - 성별, 나이대
            - 의상 (색상, 스타일)
            - 헤어스타일
            - 특징적인 액세서리 (안경, 모자 등)
            - 기본 표정
            - 배경
            """)

        rep_char_prompt = st.text_area(
            "캐릭터 프롬프트",
            value=existing_char.base_prompt if existing_char else "",
            height=150,
            placeholder="A professional Korean male character in his 30s...",
            key="rep_char_prompt",
            label_visibility="collapsed"
        )

        rep_negative_prompt = st.text_input(
            "네거티브 프롬프트 (선택)",
            value=existing_char.negative_prompt if existing_char else "text, watermark, low quality, blurry, deformed",
            key="rep_char_negative"
        )

        col_save1, col_save2 = st.columns(2)

        with col_save1:
            # 새 캐릭터인지 기존 캐릭터 수정인지 판단
            is_new_char = st.session_state.get("rep_char_mode") == "create" or not selected_lib_id
            save_label = "💾 새 캐릭터 저장" if is_new_char else "💾 프롬프트 저장"

            if st.button(save_label, type="primary", use_container_width=True, key="save_rep_char"):
                if not rep_char_name or not rep_char_prompt:
                    st.error("캐릭터 이름과 프롬프트를 입력해주세요.")
                else:
                    import uuid

                    # 라이브러리에 저장/업데이트
                    if is_new_char:
                        # 새 캐릭터 생성
                        new_lib_id = rep_library.create_character(
                            name=rep_char_name,
                            description=rep_char_description,
                            prompt=rep_char_prompt,
                            negative_prompt=rep_negative_prompt,
                            style_preset=selected_style
                        )
                        rep_library.select_character(new_lib_id)
                        st.session_state["rep_char_mode"] = "view"
                        st.success(f"✅ 새 대표 캐릭터 '{rep_char_name}'이(가) 라이브러리에 저장되었습니다!")
                    else:
                        # 기존 캐릭터 업데이트
                        rep_library.update_character(
                            char_id=selected_lib_id,
                            name=rep_char_name,
                            description=rep_char_description,
                            prompt=rep_char_prompt,
                            negative_prompt=rep_negative_prompt,
                            style_preset=selected_style
                        )
                        st.success("✅ 대표 캐릭터가 업데이트되었습니다!")

                    # 프로젝트 매니저에도 동기화
                    character = RepresentativeCharacter(
                        id=selected_lib_id if selected_lib_id else str(uuid.uuid4()),
                        name=rep_char_name,
                        description=rep_char_description,
                        base_prompt=rep_char_prompt,
                        style_preset=selected_style,
                        negative_prompt=rep_negative_prompt
                    )
                    rep_manager.set_character(character)

                    time.sleep(0.5)
                    st.rerun()

        with col_save2:
            # 새 캐릭터 모드에서는 취소 버튼
            if is_new_char and all_characters:
                if st.button("취소", use_container_width=True, key="cancel_rep_char"):
                    st.session_state["rep_char_mode"] = "view"
                    st.rerun()
            elif existing_char and st.button("🗑️ 프로젝트에서 제거", use_container_width=True, key="delete_rep_char"):
                rep_manager.delete_character()
                st.warning("프로젝트에서 대표 캐릭터가 제거되었습니다. (라이브러리에는 유지됨)")
                time.sleep(0.5)
                st.rerun()

    # ============================================================
    # 2️⃣ 기본 이미지 생성
    # ============================================================
    st.markdown("---")
    st.markdown("### 2️⃣ 대표 캐릭터 기본 이미지 생성")

    rep_char = rep_manager.get_character()

    if not rep_char:
        st.warning("먼저 대표 캐릭터를 정의해주세요.")
    else:
        with st.container(border=True):
            col_img1, col_img2 = st.columns([1, 2])

            with col_img1:
                st.markdown("**생성된 기본 이미지:**")

                if rep_char.base_images:
                    img_cols = st.columns(2)
                    for idx, (img_type, img_path) in enumerate(rep_char.base_images.items()):
                        if os.path.exists(img_path):
                            with img_cols[idx % 2]:
                                # v3.0: 네이티브 확대 방식
                                render_clickable_thumbnail(
                                    img_path,
                                    caption=BASE_IMAGE_TYPES.get(img_type, {}).get("name", img_type),
                                    width=150,
                                    key=f"base_img_{img_type}"
                                )
                else:
                    st.info("아직 생성된 이미지가 없습니다.")

            with col_img2:
                st.markdown("**생성 옵션:**")

                selected_base_types = []
                base_type_cols = st.columns(3)

                for idx, (key, info) in enumerate(BASE_IMAGE_TYPES.items()):
                    with base_type_cols[idx % 3]:
                        if st.checkbox(info["name"], value=(key in ["front", "smile"]), key=f"base_img_{key}"):
                            selected_base_types.append(key)

                # API 선택
                from utils.image_api_manager import API_MODELS
                base_api_options = list(API_MODELS.keys())

                base_selected_api = st.selectbox(
                    "이미지 생성 API",
                    options=base_api_options,
                    index=0,
                    key="base_image_api"
                )

                # ===== 프롬프트 미리보기 =====
                if selected_base_types:
                    from utils.prompt_builder import PromptBuilder
                    from utils.representative_character import STYLE_PRESETS

                    st.markdown("---")

                    with st.expander("최종 프롬프트 미리보기 및 수정", expanded=False):
                        # 첫 번째 선택된 타입에 대한 예시 프롬프트 표시
                        example_type = selected_base_types[0]
                        example_name = BASE_IMAGE_TYPES[example_type]["name"]

                        st.caption(f"'{example_name}' 이미지 프롬프트 구조 (다른 옵션도 동일한 구조)")

                        # 프롬프트 빌더로 구성 요소 표시
                        builder = PromptBuilder()

                        # 1. 캐릭터 기본 프롬프트
                        if rep_char.base_prompt:
                            builder.add(
                                name="캐릭터 프롬프트",
                                content=rep_char.base_prompt,
                                source=f"대표 캐릭터 > {rep_char.name}",
                                order=0
                            )

                        # 2. 표정/포즈 프롬프트
                        pose_prompt = BASE_IMAGE_TYPES[example_type]["prompt_prefix"]
                        builder.add(
                            name="표정/포즈",
                            content=pose_prompt,
                            source=f"기본 이미지 옵션 > {example_name}",
                            order=1
                        )

                        # 3. 스타일 Suffix
                        if rep_char.style_preset and rep_char.style_preset in STYLE_PRESETS:
                            style_suffix = STYLE_PRESETS[rep_char.style_preset]["suffix"]
                            builder.add(
                                name="스타일 Suffix",
                                content=style_suffix,
                                source=f"스타일 프리셋 > {STYLE_PRESETS[rep_char.style_preset]['name']}",
                                order=2
                            )

                        # 4. 네거티브 프롬프트
                        if rep_char.negative_prompt:
                            builder.add_negative(
                                name="캐릭터 네거티브",
                                content=rep_char.negative_prompt,
                                source=f"대표 캐릭터 > {rep_char.name}"
                            )

                        if rep_char.style_preset and rep_char.style_preset in STYLE_PRESETS:
                            style_neg = STYLE_PRESETS[rep_char.style_preset].get("negative", "")
                            if style_neg:
                                builder.add_negative(
                                    name="스타일 네거티브",
                                    content=style_neg,
                                    source=f"스타일 프리셋 > {STYLE_PRESETS[rep_char.style_preset]['name']}"
                                )

                        build_result = builder.build()

                        # 구성 요소 테이블
                        for i, comp in enumerate(build_result.components, 1):
                            st.markdown(f"**{i}. {comp.name}** ({comp.source})")
                            st.code(comp.content, language=None)

                        st.info("위 요소들이 쉼표(,)로 연결되어 최종 프롬프트가 됩니다.")

                        st.markdown("---")
                        st.markdown("#### 최종 프롬프트 (수정 가능)")

                        # 세션 상태로 수정된 프롬프트 관리
                        if "base_img_edited_prompt" not in st.session_state:
                            st.session_state["base_img_edited_prompt"] = {}

                        edited_prompt = st.text_area(
                            f"'{example_name}' 프롬프트",
                            value=build_result.final_prompt,
                            height=100,
                            key="base_img_prompt_edit",
                            help="생성 전에 프롬프트를 직접 수정할 수 있습니다."
                        )
                        st.session_state["base_img_edited_prompt"]["main"] = edited_prompt

                        # 프롬프트 통계
                        col_s1, col_s2, col_s3 = st.columns(3)
                        with col_s1:
                            st.metric("문자 수", f"{len(edited_prompt):,}")
                        with col_s2:
                            st.metric("단어 수", f"{len(edited_prompt.split()):,}")
                        with col_s3:
                            approx_tokens = len(edited_prompt) // 4
                            token_status = "적정" if approx_tokens < 200 else "주의" if approx_tokens < 300 else "초과"
                            st.metric("예상 토큰", f"~{approx_tokens} ({token_status})")

                        # 네거티브 프롬프트
                        edited_negative = st.text_input(
                            "네거티브 프롬프트",
                            value=build_result.final_negative,
                            key="base_img_negative_edit"
                        )
                        st.session_state["base_img_edited_prompt"]["negative"] = edited_negative

                        st.caption("수정된 프롬프트는 첫 번째 옵션에만 적용됩니다. 나머지는 기본 프롬프트가 사용됩니다.")

                st.markdown("---")

                if st.button(
                    f"기본 이미지 생성 ({len(selected_base_types)}개)",
                    type="primary",
                    disabled=len(selected_base_types) == 0,
                    use_container_width=True,
                    key="gen_base_images"
                ):
                    from utils.image_api_manager import ImageAPIManager

                    api_manager = ImageAPIManager()
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    generated_count = 0

                    # 수정된 프롬프트 가져오기
                    edited_prompts = st.session_state.get("base_img_edited_prompt", {})

                    for idx, img_type in enumerate(selected_base_types):
                        status_text.text(f"생성 중: {BASE_IMAGE_TYPES[img_type]['name']}...")

                        # 첫 번째 옵션은 수정된 프롬프트 사용
                        if idx == 0 and edited_prompts.get("main"):
                            prompt = edited_prompts["main"]
                            negative = edited_prompts.get("negative", rep_manager.get_negative_prompt())
                        else:
                            prompt = rep_manager.get_base_image_prompt(img_type)
                            negative = rep_manager.get_negative_prompt()

                        result = api_manager.generate_image(
                            prompt=prompt,
                            api_provider=base_selected_api,
                            negative_prompt=negative
                        )

                        if result.success and result.image_data:
                            output_path = rep_manager.images_folder / f"base_{img_type}.png"
                            with open(output_path, "wb") as f:
                                f.write(result.image_data)

                            rep_manager.add_base_image(img_type, str(output_path))
                            generated_count += 1

                            # 라이브러리에도 이미지 추가
                            if selected_lib_id:
                                rep_library.add_base_image(selected_lib_id, str(output_path), img_type)

                        progress_bar.progress((idx + 1) / len(selected_base_types))

                    status_text.empty()
                    progress_bar.empty()
                    st.success(f"✅ {generated_count}개 기본 이미지 생성 완료!")
                    st.rerun()

    # ============================================================
    # 3️⃣ 씬별 액션 프롬프트 생성
    # ============================================================
    st.markdown("---")
    st.markdown("### 3️⃣ 씬별 캐릭터 액션 프롬프트 생성 (AI)")

    rep_char = rep_manager.get_character()

    if not rep_char:
        st.warning("먼저 대표 캐릭터를 정의해주세요.")
    else:
        # 씬 데이터 로드 (새로고침 지원 - v2.0)
        cache_key = f"scene_data_{project_path}"

        if st.session_state.get('force_refresh_scene_data', False) or cache_key not in st.session_state:
            scene_data, mtime_str = load_scene_analysis_data(force_refresh=True)
            st.session_state[cache_key] = scene_data
            st.session_state['force_refresh_scene_data'] = False
        else:
            scene_data = st.session_state.get(cache_key, [])
            mtime_str = st.session_state.get('scene_file_mtime', None)

        if not scene_data:
            st.warning("씬 분석 결과가 없습니다. 씬 분석을 먼저 진행해주세요.")
        else:
            with st.container(border=True):
                # 씬 정보 + 새로고침 버튼 (v2.0: 파일 정보 표시)
                col_info, col_refresh = st.columns([5, 1])

                with col_info:
                    file_name = st.session_state.get('scene_file_name', 'scenes.json')
                    file_mtime = st.session_state.get('scene_file_mtime', '')
                    info_text = f"📊 분석된 씬: **{len(scene_data)}개** ({file_name})"
                    if file_mtime:
                        info_text += f"\n🕐 수정: {file_mtime}"
                    st.info(info_text)

                with col_refresh:
                    if st.button("🔄", key="refresh_scene_data_btn", help="최신 씬 분석 결과 다시 불러오기"):
                        # ⭐ v2.0: 캐시 완전 삭제
                        if cache_key in st.session_state:
                            del st.session_state[cache_key]
                        st.session_state['force_refresh_scene_data'] = True
                        st.toast("씬 데이터 새로고침 중...")
                        st.rerun()

                col_ai1, col_ai2 = st.columns(2)

                with col_ai1:
                    ai_models = get_action_ai_models()
                    ai_model_options = {m["id"]: m["name"] for m in ai_models}

                    selected_ai_model = st.selectbox(
                        "🤖 AI 모델",
                        options=list(ai_model_options.keys()),
                        format_func=lambda x: ai_model_options[x],
                        key="action_ai_model"
                    )

                with col_ai2:
                    st.markdown("**생성 옵션:**")
                    opt_expression = st.checkbox("씬 내용 기반 표정 자동 결정", value=True, key="opt_expression")
                    opt_pose = st.checkbox("씬 내용 기반 포즈/제스처 자동 결정", value=True, key="opt_pose")
                    opt_mood = st.checkbox("씬 분위기 반영", value=True, key="opt_mood")
                    opt_props = st.checkbox("소품 추가 (차트, 노트북 등)", value=False, key="opt_props")

                # ============================================================
                # 📍 구간 선택 UI
                # ============================================================
                st.markdown("---")
                st.markdown("#### 📍 생성 구간 선택")

                total_scenes = len(scene_data)

                range_mode = st.radio(
                    "구간 선택 방식",
                    options=["전체", "구간 지정", "빠른 선택"],
                    horizontal=True,
                    key="action_range_mode"
                )

                if range_mode == "전체":
                    start_scene = 1
                    end_scene = total_scenes
                    st.caption(f"📌 전체 {total_scenes}개 씬에 대해 프롬프트를 생성합니다.")

                elif range_mode == "구간 지정":
                    col_start, col_end = st.columns(2)

                    with col_start:
                        start_scene = st.number_input(
                            "시작 씬",
                            min_value=1,
                            max_value=total_scenes,
                            value=1,
                            step=1,
                            key="action_start_scene_input"
                        )

                    with col_end:
                        end_scene = st.number_input(
                            "끝 씬",
                            min_value=1,
                            max_value=total_scenes,
                            value=min(50, total_scenes),
                            step=1,
                            key="action_end_scene_input"
                        )

                    if start_scene > end_scene:
                        st.error("❌ 시작 씬이 끝 씬보다 클 수 없습니다.")
                    else:
                        selected_count = end_scene - start_scene + 1
                        st.caption(f"📌 씬 {start_scene} ~ {end_scene} ({selected_count}개 씬) 선택됨")

                else:  # 빠른 선택
                    quick_options = {
                        "처음 50개": (1, min(50, total_scenes)),
                        "처음 25개 (테스트용)": (1, min(25, total_scenes)),
                        "처음 100개": (1, min(100, total_scenes)),
                    }

                    # 동적 옵션 추가
                    if total_scenes > 50:
                        quick_options["씬 51-100"] = (51, min(100, total_scenes))
                    if total_scenes > 100:
                        quick_options["씬 101-150"] = (101, min(150, total_scenes))
                    if total_scenes > 150:
                        quick_options["씬 151-200"] = (151, min(200, total_scenes))

                    quick_options["마지막 50개"] = (max(1, total_scenes - 49), total_scenes)

                    selected_quick = st.selectbox(
                        "빠른 구간 선택",
                        options=list(quick_options.keys()),
                        key="action_quick_range_select"
                    )

                    start_scene, end_scene = quick_options[selected_quick]
                    selected_count = end_scene - start_scene + 1
                    st.caption(f"📌 씬 {start_scene} ~ {end_scene} ({selected_count}개 씬) 선택됨")

                # 세션에 저장
                st.session_state['action_start_scene'] = start_scene
                st.session_state['action_end_scene'] = end_scene

                # ============================================================
                # ⚙️ 병합 옵션 (v2.0)
                # ============================================================
                existing_actions = rep_manager.get_scene_actions()
                if existing_actions:
                    st.markdown("---")
                    st.markdown("#### ⚙️ 기존 프롬프트 처리")

                    existing_count = len(existing_actions)
                    merge_option = st.radio(
                        f"기존에 생성된 프롬프트가 {existing_count}개 있습니다. 어떻게 처리할까요?",
                        options=[
                            "덮어쓰기",
                            "병합",
                            "선택 구간만 업데이트"
                        ],
                        format_func=lambda x: {
                            "덮어쓰기": f"🔄 덮어쓰기 (기존 {existing_count}개 삭제)",
                            "병합": f"➕ 병합 (기존 프롬프트 유지 + 새로 생성)",
                            "선택 구간만 업데이트": f"📝 선택 구간만 업데이트 (씬 {start_scene}~{end_scene} 교체)"
                        }[x],
                        horizontal=True,
                        key="action_merge_option"
                    )
                    st.session_state['action_merge_mode'] = merge_option
                else:
                    st.session_state['action_merge_mode'] = "덮어쓰기"

                st.markdown("---")

                # 버튼 텍스트에 구간 표시
                selected_count = end_scene - start_scene + 1
                button_text = f"🤖 AI로 씬별 액션 프롬프트 자동 생성 (씬 {start_scene}~{end_scene}, {selected_count}개)"

                if st.button(
                    button_text,
                    type="primary",
                    use_container_width=True,
                    key="gen_action_prompts"
                ):
                    generator = CharacterActionGenerator(model_id=selected_ai_model)

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def update_progress(current, total, message):
                        progress_bar.progress(current / total if total > 0 else 0)
                        status_text.text(message)

                    # ✅ 수정: 씬 데이터를 생성기에 맞는 형식으로 변환
                    # 버그 수정: script_text 필드 사용 (이전: script 필드 없어서 title만 전달됨)
                    # ✅ v2.0: 선택된 구간만 필터링
                    scenes_for_gen = [
                        {
                            "scene_num": s.get("scene_number", i + 1),
                            "script": (
                                s.get("script_text") or  # 씬 분석 데이터의 실제 필드
                                s.get("script") or
                                s.get("narration") or
                                s.get("description") or  # 설명도 포함
                                s.get("title", f"씬 {i + 1}")
                            )
                        }
                        for i, s in enumerate(scene_data)
                        if start_scene <= s.get("scene_number", i + 1) <= end_scene
                    ]

                    # 디버그: 실제 전달되는 씬 내용 확인
                    print(f"[ActionGenerator] 선택 범위: 씬 {start_scene}~{end_scene}, 총 {len(scenes_for_gen)}개")
                    print(f"[ActionGenerator] 씬 데이터 샘플: {scenes_for_gen[0] if scenes_for_gen else 'empty'}")

                    new_actions = generator.generate_batch_actions(
                        character_prompt=rep_char.base_prompt,
                        scenes=scenes_for_gen,
                        options={
                            "expression": opt_expression,
                            "pose": opt_pose,
                            "mood": opt_mood,
                            "props": opt_props
                        },
                        progress_callback=update_progress
                    )

                    # ⭐ v2.0: 병합 옵션에 따른 저장
                    merge_mode = st.session_state.get('action_merge_mode', '덮어쓰기')
                    existing_actions = rep_manager.get_scene_actions()

                    if merge_mode == "병합" and existing_actions:
                        # 기존 프롬프트와 병합 (새로 생성된 씬은 추가, 기존은 유지)
                        existing_scene_nums = {a.scene_num for a in existing_actions}
                        merged = list(existing_actions)

                        for new_action in new_actions:
                            if new_action.scene_num not in existing_scene_nums:
                                merged.append(new_action)

                        # scene_num으로 정렬
                        merged.sort(key=lambda x: x.scene_num)
                        rep_manager.set_scene_actions(merged)
                        final_count = len(merged)
                        result_msg = f"✅ 병합 완료! (기존 {len(existing_actions)}개 + 새로 {len(new_actions)}개 → 총 {final_count}개)"

                    elif merge_mode == "선택 구간만 업데이트" and existing_actions:
                        # 선택 구간만 교체 (나머지 유지)
                        kept = [a for a in existing_actions if not (start_scene <= a.scene_num <= end_scene)]
                        merged = kept + list(new_actions)

                        # scene_num으로 정렬
                        merged.sort(key=lambda x: x.scene_num)
                        rep_manager.set_scene_actions(merged)
                        final_count = len(merged)
                        result_msg = f"✅ 구간 업데이트 완료! 씬 {start_scene}~{end_scene} ({len(new_actions)}개) 교체됨 (총 {final_count}개)"

                    else:
                        # 덮어쓰기
                        rep_manager.set_scene_actions(new_actions)
                        result_msg = f"✅ 씬 {start_scene}~{end_scene} 범위 ({len(new_actions)}개) 액션 프롬프트 생성 완료!"

                    progress_bar.empty()
                    status_text.empty()
                    st.success(result_msg)
                    st.rerun()

                # 생성된 액션 표시
                st.markdown("---")
                st.markdown("**📋 생성된 씬별 액션 프롬프트:**")

                actions = rep_manager.get_scene_actions()

                if not actions:
                    st.info("아직 생성된 액션 프롬프트가 없습니다.")
                else:
                    show_count = st.selectbox(
                        "표시 개수",
                        options=[10, 20, 50, len(actions)],
                        format_func=lambda x: f"{x}개" if x != len(actions) else "전체",
                        key="action_show_count"
                    )

                    for action in actions[:show_count]:
                        with st.expander(
                            f"씬 {action.scene_num}: {action.scene_content[:40]}...",
                            expanded=False
                        ):
                            col_act1, col_act2 = st.columns([1, 1])

                            with col_act1:
                                st.markdown(f"**표정:** {action.expression}")
                                st.markdown(f"**포즈:** {action.pose}")
                                st.markdown(f"**분위기:** {action.mood}")

                                if action.props and action.props != ["none"]:
                                    st.markdown(f"**소품:** {', '.join(action.props)}")

                                st.markdown(f"**상태:** {action.generation_status}")

                            with col_act2:
                                st.markdown("**액션 프롬프트:**")
                                st.code(action.action_prompt, language=None)

    # ============================================================
    # 4️⃣ 씬별 캐릭터 이미지 일괄 생성
    # ============================================================
    st.markdown("---")
    st.markdown("### 4️⃣ 씬별 캐릭터 이미지 일괄 생성")

    rep_char = rep_manager.get_character()
    actions = rep_manager.get_scene_actions()

    if not rep_char:
        st.warning("대표 캐릭터를 먼저 정의해주세요.")
    elif not actions:
        st.warning("씬별 액션 프롬프트를 먼저 생성해주세요.")
    else:
        with st.container(border=True):
            stats = rep_manager.get_stats()

            st.info(f"""
            📊 **생성 현황**
            - 전체 씬: {stats['total_scenes']}개
            - 완료: {stats['completed']}개
            - 대기: {stats['pending']}개
            - 실패: {stats['failed']}개
            """)

            # 씬 선택
            col_sel1, col_sel2, col_sel3 = st.columns(3)

            with col_sel1:
                if st.button("✅ 전체 선택", key="batch_select_all"):
                    st.session_state["batch_selected_scenes"] = [a.scene_num for a in actions]

            with col_sel2:
                batch_range_start = st.number_input("시작", min_value=1, value=1, key="batch_range_start")
                batch_range_end = st.number_input("끝", min_value=1, value=min(20, len(actions)), key="batch_range_end")

                if st.button("범위 선택", key="batch_select_range"):
                    st.session_state["batch_selected_scenes"] = list(range(batch_range_start, batch_range_end + 1))

            with col_sel3:
                if st.button("⬜ 미생성만 선택", key="batch_select_pending"):
                    st.session_state["batch_selected_scenes"] = [
                        a.scene_num for a in actions if a.generation_status == "pending"
                    ]

            # v1.2: 자동 초기화 - 처음 로드 시 미생성 씬들로 초기화
            if "batch_selected_scenes" not in st.session_state:
                pending_scenes = [a.scene_num for a in actions if a.generation_status == "pending"]
                st.session_state["batch_selected_scenes"] = pending_scenes
                print(f"[캐릭터 일괄생성] 🔄 자동 초기화: 미생성 {len(pending_scenes)}개 씬 선택됨")

            selected_scenes = st.session_state.get("batch_selected_scenes", [])
            st.caption(f"선택됨: {len(selected_scenes)}개 씬")

            # API 선택
            from utils.image_api_manager import API_MODELS
            batch_api_options = list(API_MODELS.keys())

            # v1.1: 기본 API 설정 (Google ImageFX 우선)
            default_api_index = 0
            if "Google ImageFX" in batch_api_options:
                default_api_index = batch_api_options.index("Google ImageFX")

            batch_selected_api = st.selectbox(
                "이미지 생성 API",
                options=batch_api_options,
                index=default_api_index,
                key="batch_image_api"
            )

            # v1.2: Gemini 레퍼런스 이미지 업로더 (Gemini 모델 선택 시에만 표시)
            reference_config = {"enabled": False, "images": [], "reference_type": "style", "reference_strength": 0.8}
            if "Gemini" in batch_selected_api:
                from components.reference_image_uploader import render_reference_image_uploader
                reference_config = render_reference_image_uploader(
                    key_prefix="batch_char_ref",
                    max_images=5,
                    show_only_for_gemini=False,
                    current_api=batch_selected_api
                )

            # v1.1: 시드 잠금 옵션 (이미지 일관성 유지)
            # ⭐ v1.2: style_segment="character"로 캐릭터 스타일 선택 UI 사용
            st.markdown("---")

            # ImageFX API 선택 시에만 시드 잠금 활성화
            if batch_selected_api == "Google ImageFX":
                with st.expander("🔒 이미지 일관성 유지 (시드 잠금)", expanded=False):
                    seed_lock_enabled, locked_seed = render_seed_lock_options(key_prefix="batch_char_seed", style_segment="character")
            else:
                seed_lock_enabled = False
                locked_seed = None
                # ImageFX가 아닌 경우 안내 메시지
                with st.expander("🔒 이미지 일관성 유지 (시드 잠금)", expanded=False):
                    st.info("💡 시드 잠금 기능은 **Google ImageFX** API에서만 사용 가능합니다.")
                    st.caption("다른 API는 현재 시드 파라미터를 지원하지 않습니다.")

            # 프롬프트 미리보기 및 수정
            with st.expander("최종 프롬프트 미리보기 및 수정", expanded=False):
                from utils.prompt_builder import PromptBuilder
                from utils.representative_character import STYLE_PRESETS

                if actions:
                    # 첫 번째 씬에 대한 예시 프롬프트 빌드
                    sample_action = actions[0]

                    builder = PromptBuilder()

                    # 1. 캐릭터 기본 프롬프트
                    if rep_char.base_prompt:
                        builder.add(
                            name="캐릭터 프롬프트",
                            content=rep_char.base_prompt,
                            source=f"대표 캐릭터 > {rep_char.name}",
                            order=0
                        )

                    # 2. 씬별 액션 프롬프트
                    builder.add(
                        name="씬별 액션",
                        content=sample_action.action_prompt,
                        source=f"씬 {sample_action.scene_num} AI 생성 액션",
                        order=1
                    )

                    # 3. 스타일 Suffix
                    if rep_char.style_preset and rep_char.style_preset in STYLE_PRESETS:
                        style_suffix = STYLE_PRESETS[rep_char.style_preset]["suffix"]
                        builder.add(
                            name="스타일 Suffix",
                            content=style_suffix,
                            source=f"스타일 프리셋 > {STYLE_PRESETS[rep_char.style_preset]['name']}",
                            order=2
                        )

                    # 4. 네거티브 프롬프트
                    if rep_char.negative_prompt:
                        builder.add_negative(
                            name="캐릭터 네거티브",
                            content=rep_char.negative_prompt,
                            source=f"대표 캐릭터 > {rep_char.name}"
                        )

                    build_result = builder.build()

                    st.caption(f"씬 {sample_action.scene_num} 프롬프트 구조 예시")

                    # 구성 요소 표시
                    for i, comp in enumerate(build_result.components, 1):
                        st.markdown(f"**{i}. {comp.name}** ({comp.source})")
                        st.code(comp.content, language=None)

                    st.info("위 구조가 모든 씬에 동일하게 적용됩니다. 씬마다 '씬별 액션' 부분만 달라집니다.")

                    st.markdown("---")
                    st.markdown("#### 프롬프트 수정 (선택 씬에 적용)")

                    # 수정 모드 선택
                    edit_mode = st.radio(
                        "수정 범위",
                        ["기본 프롬프트 사용", "스타일 일괄 변경", "특정 씬 개별 수정"],
                        horizontal=True,
                        key="action_edit_mode"
                    )

                    if edit_mode == "스타일 일괄 변경":
                        col_e1, col_e2 = st.columns(2)
                        with col_e1:
                            edited_style_suffix = st.text_area(
                                "스타일 Suffix (모든 씬 적용)",
                                value=STYLE_PRESETS.get(rep_char.style_preset, {}).get("suffix", ""),
                                height=80,
                                key="action_style_suffix"
                            )
                        with col_e2:
                            edited_negative = st.text_area(
                                "네거티브 (모든 씬 적용)",
                                value=build_result.final_negative,
                                height=80,
                                key="action_negative"
                            )

                        st.session_state["action_batch_edits"] = {
                            "mode": "style",
                            "suffix": edited_style_suffix,
                            "negative": edited_negative
                        }

                    elif edit_mode == "특정 씬 개별 수정":
                        st.caption("선택한 씬 중 처음 3개의 프롬프트를 개별 수정할 수 있습니다.")

                        scene_edits = {}
                        for i, scene_num in enumerate(selected_scenes[:3]):
                            action = rep_manager.get_scene_action(scene_num)
                            if action:
                                default_prompt = rep_manager.build_full_prompt(action.action_prompt)
                                scene_edits[scene_num] = st.text_area(
                                    f"씬 {scene_num} 프롬프트",
                                    value=default_prompt,
                                    height=80,
                                    key=f"scene_edit_{scene_num}"
                                )

                        st.session_state["action_batch_edits"] = {
                            "mode": "individual",
                            "scenes": scene_edits
                        }

                    else:
                        st.session_state["action_batch_edits"] = {"mode": "default"}

            # 생성 버튼
            if st.button(
                f"씬 캐릭터 이미지 일괄 생성 ({len(selected_scenes)}개)",
                type="primary",
                disabled=len(selected_scenes) == 0,
                use_container_width=True,
                key="batch_gen_images"
            ):
                from utils.image_api_manager import ImageAPIManager
                from utils.representative_character import STYLE_PRESETS

                api_manager = ImageAPIManager()
                progress_bar = st.progress(0)
                status_text = st.empty()

                success_count = 0
                fail_count = 0

                # 수정된 프롬프트 가져오기
                batch_edits = st.session_state.get("action_batch_edits", {"mode": "default"})

                for idx, scene_num in enumerate(selected_scenes):
                    action = rep_manager.get_scene_action(scene_num)

                    if not action:
                        fail_count += 1
                        continue

                    status_text.text(f"씬 {scene_num} 이미지 생성 중...")

                    # 상태 업데이트
                    rep_manager.update_scene_action(scene_num, generation_status="generating")

                    try:
                        # 수정 모드에 따른 프롬프트 생성
                        if batch_edits.get("mode") == "individual" and scene_num in batch_edits.get("scenes", {}):
                            full_prompt = batch_edits["scenes"][scene_num]
                            negative = rep_manager.get_negative_prompt()
                        elif batch_edits.get("mode") == "style":
                            # 스타일만 변경
                            parts = [rep_char.base_prompt, action.action_prompt, batch_edits.get("suffix", "")]
                            full_prompt = ", ".join(p.strip().rstrip(',') for p in parts if p)
                            negative = batch_edits.get("negative", rep_manager.get_negative_prompt())
                        else:
                            # 기본 프롬프트 생성
                            full_prompt = rep_manager.build_full_prompt(action.action_prompt)
                            negative = rep_manager.get_negative_prompt()

                        # v1.1: 시드 가져오기
                        generation_seed = get_seed_for_generation(key_prefix="batch_char_seed")

                        # 이미지 생성 (v1.2: Gemini 레퍼런스 이미지 지원)
                        result = api_manager.generate_image(
                            prompt=full_prompt,
                            api_provider=batch_selected_api,
                            negative_prompt=negative,
                            seed=generation_seed,
                            reference_config=reference_config  # v1.2: Gemini 레퍼런스 전달
                        )

                        if result.success and result.image_data:
                            output_path = rep_manager.scene_images_folder / f"scene_{scene_num:03d}_character.png"
                            with open(output_path, "wb") as f:
                                f.write(result.image_data)

                            rep_manager.update_scene_action(
                                scene_num,
                                generated_image_path=str(output_path),
                                generation_status="completed"
                            )
                            success_count += 1

                            # v1.1: 첫 번째 성공 시 시드 자동 잠금 (auto/first_image 모드)
                            if result.seed and success_count == 1:
                                update_locked_seed_from_result(result.seed, key_prefix="batch_char_seed")
                        else:
                            rep_manager.update_scene_action(
                                scene_num,
                                generation_status="failed",
                                error_message=result.error or "이미지 생성 실패"
                            )
                            fail_count += 1

                    except Exception as e:
                        rep_manager.update_scene_action(
                            scene_num,
                            generation_status="failed",
                            error_message=str(e)
                        )
                        fail_count += 1

                    progress_bar.progress((idx + 1) / len(selected_scenes))

                progress_bar.empty()
                status_text.empty()
                st.success(f"✅ 완료: {success_count}개 성공, {fail_count}개 실패")
                st.rerun()

            # 생성된 이미지 미리보기
            st.markdown("---")
            st.markdown("**🖼️ 생성된 캐릭터 이미지:**")

            completed_actions = rep_manager.get_completed_actions()

            if not completed_actions:
                st.info("아직 생성된 이미지가 없습니다.")
            else:
                img_cols = st.columns(5)
                for idx, action in enumerate(completed_actions[:20]):
                    if action.generated_image_path and os.path.exists(action.generated_image_path):
                        with img_cols[idx % 5]:
                            # v3.0: 네이티브 확대 방식
                            render_clickable_thumbnail(
                                action.generated_image_path,
                                caption=f"씬 {action.scene_num}",
                                width=120,
                                key=f"action_img_{action.scene_num}_{idx}"
                            )

                if len(completed_actions) > 20:
                    st.caption(f"... 외 {len(completed_actions) - 20}개 더 있음")


# === 탭 7: 씬별 캐릭터 갤러리 ===
with tab7:
    st.subheader("🖼️ 씬별 캐릭터 이미지 갤러리")
    st.caption("씬 번호순으로 캐릭터 이미지를 확인하고 재생성할 수 있습니다")

    if not GALLERY_AVAILABLE:
        st.error("갤러리 모듈을 로드할 수 없습니다.")
        st.info("utils/character_gallery.py 및 components/scene_character_gallery.py 파일이 필요합니다.")
    else:
        # 갤러리 매니저 초기화
        gallery_manager = get_gallery_manager(str(project_path))

        # 갤러리 옵션
        gal_col1, gal_col2 = st.columns([3, 1])

        with gal_col1:
            view_mode = st.radio(
                "보기 모드",
                options=["🎬 씬별 보기", "📋 캐릭터별 보기"],
                horizontal=True,
                key="gallery_view_mode",
                index=0
            )

        with gal_col2:
            thumbnail_size = st.select_slider(
                "썸네일 크기",
                options=[100, 150, 200, 250],
                value=150,
                key="gallery_thumbnail_size"
            )

        st.divider()

        if view_mode == "🎬 씬별 보기":
            # 씬별 갤러리 데이터 로드
            try:
                with st.spinner("갤러리 데이터 로드 중..."):
                    scenes = gallery_manager.get_scenes_with_characters()

                if not scenes:
                    st.info("캐릭터 이미지가 있는 씬이 없습니다.")
                    st.caption("먼저 '배치 생성' 탭에서 캐릭터 이미지를 생성하세요.")
                else:
                    # 재생성 콜백 함수
                    def on_character_regenerate(char_name: str, pose: str, scene_num: int):
                        """캐릭터 재생성 콜백"""
                        st.session_state['regen_char_name'] = char_name
                        st.session_state['regen_pose'] = pose
                        st.session_state['regen_scene_num'] = scene_num
                        st.session_state['show_regen_dialog'] = True
                        st.rerun()

                    def on_character_delete(char_name: str, pose: str):
                        """캐릭터 삭제 콜백"""
                        st.warning(f"'{char_name}' ({pose}) 삭제 기능은 아직 구현되지 않았습니다.")

                    # 재생성 다이얼로그 처리
                    if st.session_state.get('show_regen_dialog'):
                        _render_regeneration_dialog()
                    else:
                        # 갤러리 렌더링
                        render_scene_character_gallery(
                            scenes=scenes,
                            project_path=str(project_path),
                            on_regenerate=on_character_regenerate,
                            on_delete=on_character_delete,
                            columns_per_row=4,
                            thumbnail_size=thumbnail_size
                        )

            except Exception as e:
                st.error(f"갤러리 로드 오류: {e}")
                import traceback
                st.code(traceback.format_exc())

        else:
            # 캐릭터별 보기 (기존 방식)
            st.info("캐릭터별 보기는 상단의 '📋 캐릭터 목록' 탭을 사용하세요.")
            st.caption("첫 번째 탭에서 캐릭터별로 그룹화된 목록을 확인할 수 있습니다.")


def _render_regeneration_dialog():
    """
    재생성 다이얼로그 렌더링 (v2.0)

    v2.0: Google ImageFX (Imagen 4)를 기본 API로 설정
          다양한 모델 선택 옵션 제공
    """
    char_name = st.session_state.get('regen_char_name', '')
    pose = st.session_state.get('regen_pose', 'standing')
    scene_num = st.session_state.get('regen_scene_num', 0)

    st.markdown("### 🔄 캐릭터 이미지 재생성")

    st.info(f"""
    **캐릭터**: {char_name}
    **포즈**: {pose}
    **씬**: {scene_num}
    """)

    # ========================================
    # v2.0: 이미지 생성 API 선택 (Google ImageFX 기본)
    # ========================================
    st.markdown("#### 🖼️ 이미지 생성 API 선택")

    # API 옵션 정의 (Google ImageFX를 첫 번째, 기본값으로)
    REGEN_API_OPTIONS = {
        "Google ImageFX": {
            "models": [
                ("IMAGEN_4", "Imagen 4 (최신, 무료)"),
                ("IMAGEN_3_5", "Imagen 3.5 (무료)"),
                ("IMAGEN_3_1", "Imagen 3.1 (무료)"),
                ("IMAGEN_3", "Imagen 3.0 (무료)"),
            ],
            "default_model": "IMAGEN_4",
            "icon": "🎨",
            "cost": "무료 (쿠키 필요)",
            "description": "Google의 최신 이미지 생성 모델"
        },
        "Together.ai FLUX": {
            "models": [
                ("black-forest-labs/FLUX.2-dev", "FLUX.2 Dev (권장, ~20원)"),
                ("black-forest-labs/FLUX.2-flex", "FLUX.2 Flex (~40원)"),
                ("black-forest-labs/FLUX.2-pro", "FLUX.2 Pro (고품질, ~40원)"),
            ],
            "default_model": "black-forest-labs/FLUX.2-dev",
            "icon": "🚀",
            "cost": "유료 (~20원/장)",
            "description": "빠른 속도의 고품질 이미지 생성"
        },
        "Gemini (Nano Banana)": {
            "models": [
                ("gemini_nano_banana", "Nano Banana (~15원, 레퍼런스 지원)"),
                ("gemini_nano_banana_pro", "Nano Banana Pro (~25원)"),
            ],
            "default_model": "gemini_nano_banana",
            "icon": "🍌",
            "cost": "유료 (~15원/장)",
            "description": "레퍼런스 이미지 지원, 캐릭터 일관성"
        },
        "OpenAI DALL-E": {
            "models": [
                ("dall-e-3", "DALL-E 3 (최신, ~60원)"),
                ("dall-e-2", "DALL-E 2 (~30원)"),
            ],
            "default_model": "dall-e-3",
            "icon": "🖼️",
            "cost": "유료 (~60원/장)",
            "description": "OpenAI의 프리미엄 이미지 생성"
        },
    }

    api_options = list(REGEN_API_OPTIONS.keys())

    # 기본값: Google ImageFX (첫 번째)
    default_api_idx = 0

    # API 선택
    selected_api = st.selectbox(
        "API 제공자",
        options=api_options,
        index=default_api_idx,
        format_func=lambda x: f"{REGEN_API_OPTIONS[x]['icon']} {x} ({REGEN_API_OPTIONS[x]['cost']})",
        key="regen_api_select"
    )

    api_config = REGEN_API_OPTIONS[selected_api]
    st.caption(f"📝 {api_config['description']}")

    # 모델 선택
    model_options = api_config["models"]
    model_ids = [m[0] for m in model_options]
    model_labels = [m[1] for m in model_options]

    default_model_idx = 0
    if api_config["default_model"] in model_ids:
        default_model_idx = model_ids.index(api_config["default_model"])

    selected_model_idx = st.selectbox(
        "모델",
        options=range(len(model_options)),
        index=default_model_idx,
        format_func=lambda x: model_labels[x],
        key="regen_model_select"
    )
    selected_model = model_ids[selected_model_idx]

    st.divider()

    # ========================================
    # 생성 옵션
    # ========================================
    st.markdown("#### ⚙️ 생성 옵션")

    col_opt1, col_opt2 = st.columns(2)

    with col_opt1:
        # 이미지 크기 (Google ImageFX는 aspect ratio만 지원)
        if selected_api == "Google ImageFX":
            aspect_options = ["1:1 (정사각형)", "16:9 (가로)", "9:16 (세로)", "4:3", "3:4"]
            aspect_ratio = st.selectbox(
                "비율",
                options=aspect_options,
                index=0,
                key="regen_aspect_ratio"
            )
        else:
            width = st.selectbox(
                "너비",
                [512, 768, 1024, 1408],
                index=2,  # 기본 1024
                key="regen_width"
            )

    with col_opt2:
        if selected_api != "Google ImageFX":
            height = st.selectbox(
                "높이",
                [512, 768, 1024, 1408],
                index=2,  # 기본 1024
                key="regen_height"
            )
        else:
            st.empty()

    # 동시 생성 수
    num_images = st.slider(
        "동시 생성 수",
        min_value=1,
        max_value=4,
        value=2,
        key="regen_num_images"
    )

    st.divider()

    # ========================================
    # 스타일 선택 (기존)
    # ========================================
    style_manager = get_style_manager()
    available_styles = style_manager.get_all_styles()
    style_names = [s['name'] for s in available_styles]

    current_style = st.session_state.get('batch_style', style_names[0] if style_names else '')

    selected_style = st.selectbox(
        "스타일",
        options=style_names,
        index=style_names.index(current_style) if current_style in style_names else 0,
        key="regen_style_select"
    )

    st.divider()

    # ========================================
    # 버튼
    # ========================================
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔄 재생성 시작", type="primary", use_container_width=True):
            # v2.0: 실제 재생성 실행
            _execute_character_regeneration(
                char_name=char_name,
                pose=pose,
                scene_num=scene_num,
                api=selected_api,
                model=selected_model,
                style=selected_style,
                num_images=num_images,
                aspect_ratio=aspect_ratio if selected_api == "Google ImageFX" else None,
                width=width if selected_api != "Google ImageFX" else 1024,
                height=height if selected_api != "Google ImageFX" else 1024
            )

    with col2:
        if st.button("❌ 취소", use_container_width=True):
            st.session_state['show_regen_dialog'] = False
            st.rerun()

    with col3:
        if st.button("📋 갤러리로", use_container_width=True):
            st.session_state['show_regen_dialog'] = False
            st.rerun()


def _execute_character_regeneration(
    char_name: str,
    pose: str,
    scene_num: int,
    api: str,
    model: str,
    style: str,
    num_images: int = 2,
    aspect_ratio: str = None,
    width: int = 1024,
    height: int = 1024
):
    """
    캐릭터 이미지 재생성 실행 (v2.0)

    Args:
        char_name: 캐릭터 이름
        pose: 포즈
        scene_num: 씬 번호
        api: API 제공자
        model: 모델 ID
        style: 스타일 이름
        num_images: 동시 생성 수
        aspect_ratio: 비율 (Google ImageFX용)
        width: 이미지 너비
        height: 이미지 높이
    """
    import traceback

    st.info(f"🔄 재생성 중... (API: {api}, 모델: {model})")

    # 프로젝트 경로 가져오기
    project = get_current_project()
    if not project:
        st.error("프로젝트가 선택되지 않았습니다.")
        return

    project_path = Path(project.get('path', ''))

    with st.spinner(f"'{char_name}' 캐릭터 이미지 생성 중..."):
        try:
            # 캐릭터 프롬프트 가져오기
            char_manager = CharacterManager(str(project_path))
            all_chars = char_manager.get_all_characters()

            target_char = None
            for c in all_chars:
                if get_character_name(c) == char_name:
                    target_char = c
                    break

            if not target_char:
                st.error(f"캐릭터 '{char_name}'를 찾을 수 없습니다.")
                return

            # 프롬프트 생성
            char_prompt = target_char.get('prompt_en', '') or target_char.get('description', '')

            if not char_prompt:
                st.error("캐릭터 프롬프트가 없습니다.")
                return

            # 스타일 추가
            style_manager = get_style_manager()
            style_data = style_manager.get_style_by_name(style)
            if style_data:
                style_prompt = style_data.get('prompt_suffix', '')
                if style_prompt:
                    char_prompt = f"{char_prompt}, {style_prompt}"

            # 포즈 추가
            if pose:
                char_prompt = f"{char_prompt}, {pose} pose"

            st.caption(f"📝 프롬프트: {char_prompt[:100]}...")

            # API별 이미지 생성
            generated_images = []

            if api == "Google ImageFX":
                # ImageFX API 호출
                generated_images = _generate_with_imagefx(
                    prompt=char_prompt,
                    model=model,
                    aspect_ratio=aspect_ratio,
                    num_images=num_images
                )
            elif "Together" in api or "FLUX" in api:
                # Together.ai FLUX API 호출
                generated_images = _generate_with_flux(
                    prompt=char_prompt,
                    model=model,
                    width=width,
                    height=height,
                    num_images=num_images
                )
            elif "Gemini" in api or "Banana" in api:
                # Gemini Nano Banana API 호출
                generated_images = _generate_with_gemini_banana(
                    prompt=char_prompt,
                    model=model,
                    width=width,
                    height=height,
                    num_images=num_images
                )
            elif "DALL-E" in api or "OpenAI" in api:
                # OpenAI DALL-E API 호출
                generated_images = _generate_with_dalle(
                    prompt=char_prompt,
                    model=model,
                    width=width,
                    height=height,
                    num_images=num_images
                )
            else:
                st.error(f"지원하지 않는 API: {api}")
                return

            if generated_images:
                # 이미지 저장
                saved_paths = _save_regenerated_images(
                    char_name=char_name,
                    scene_num=scene_num,
                    project_path=project_path,
                    images=generated_images
                )

                st.success(f"✅ {len(saved_paths)}개 이미지 생성 완료!")

                # 생성된 이미지 미리보기
                if saved_paths:
                    cols = st.columns(min(len(saved_paths), 4))
                    for i, path in enumerate(saved_paths[:4]):
                        with cols[i]:
                            st.image(path, use_container_width=True)

                # 다이얼로그 닫기
                st.session_state['show_regen_dialog'] = False
                time.sleep(1)
                st.rerun()
            else:
                st.error("이미지 생성 결과가 없습니다.")

        except Exception as e:
            st.error(f"❌ 재생성 오류: {str(e)}")
            st.code(traceback.format_exc())


def _generate_with_imagefx(
    prompt: str,
    model: str = "IMAGEN_4",
    aspect_ratio: str = "1:1 (정사각형)",
    num_images: int = 2
) -> list:
    """
    Google ImageFX API로 이미지 생성

    Returns:
        이미지 데이터 리스트 (bytes)
    """
    images = []

    try:
        from utils.imagefx_client import ImageFXClient, ImagenModel, AspectRatio
        from config.settings import load_imagefx_cookie

        # 쿠키 로드 (session_state > 파일 순서, 이미지 생성 탭과 동일)
        imagefx_cookie = st.session_state.get("imagefx_cookie", "") or load_imagefx_cookie()
        if not imagefx_cookie:
            st.error("❌ ImageFX 쿠키가 설정되지 않았습니다. API 관리 페이지에서 쿠키를 입력해주세요.")
            return images

        print(f"[캐릭터 ImageFX] 쿠키 로드됨 (길이: {len(imagefx_cookie)})")

        # aspect ratio 매핑 (UI 문자열 → AspectRatio enum)
        ar_map = {
            "1:1 (정사각형)": AspectRatio.SQUARE,
            "16:9 (가로)": AspectRatio.LANDSCAPE,
            "9:16 (세로)": AspectRatio.PORTRAIT,
            "4:3": AspectRatio.LANDSCAPE,
            "3:4": AspectRatio.PORTRAIT
        }
        ar = ar_map.get(aspect_ratio, AspectRatio.SQUARE)

        # ImageFX 클라이언트 초기화 (쿠키 전달)
        client = ImageFXClient(cookie=imagefx_cookie)

        # 모델 매핑 (문자열 → ImagenModel enum)
        model_enum_map = {
            "IMAGEN_4": ImagenModel.IMAGEN_4,
            "IMAGEN_3_5": ImagenModel.IMAGEN_3_5,
            "IMAGEN_3_1": ImagenModel.IMAGEN_3_1,
            "IMAGEN_3": ImagenModel.IMAGEN_3
        }
        imagefx_model = model_enum_map.get(model, ImagenModel.IMAGEN_4)

        # 이미지 생성 (1장씩 num_images번 호출)
        for i in range(num_images):
            result_list = client.generate_image(
                prompt=prompt,
                model=imagefx_model,
                aspect_ratio=ar,
                num_images=1
            )

            if result_list:
                for gen_img in result_list:
                    try:
                        img_bytes = gen_img.get_bytes()
                        if img_bytes:
                            images.append(img_bytes)
                            print(f"[ImageFX] ✅ 이미지 {i+1}/{num_images} 생성 완료")
                    except Exception as e:
                        print(f"[ImageFX] ⚠️ 이미지 {i+1} 바이트 변환 실패: {e}")
            else:
                print(f"[ImageFX] ⚠️ 이미지 {i+1} 생성 실패: 결과 없음")

    except ImportError:
        st.warning("ImageFX 클라이언트를 찾을 수 없습니다. 쿠키 설정을 확인하세요.")
    except Exception as e:
        st.error(f"ImageFX 오류: {str(e)}")
        import traceback
        traceback.print_exc()

    return images


def _generate_with_flux(
    prompt: str,
    model: str,
    width: int,
    height: int,
    num_images: int
) -> list:
    """Together.ai FLUX API로 이미지 생성"""
    images = []

    try:
        from utils.parallel_image_generator import generate_with_together_flux

        for i in range(num_images):
            result = generate_with_together_flux(
                prompt=prompt,
                model=model,
                width=width,
                height=height
            )

            if result:
                images.append(result)
                print(f"[FLUX] ✅ 이미지 {i+1}/{num_images} 생성 완료")

    except ImportError:
        st.warning("FLUX 생성기를 찾을 수 없습니다.")
    except Exception as e:
        st.error(f"FLUX 오류: {str(e)}")

    return images


def _generate_with_gemini_banana(
    prompt: str,
    model: str,
    width: int,
    height: int,
    num_images: int
) -> list:
    """Gemini Nano Banana API로 이미지 생성"""
    images = []

    try:
        from utils.gemini_image_generator import generate_with_gemini

        for i in range(num_images):
            result = generate_with_gemini(
                prompt=prompt,
                width=width,
                height=height
            )

            if result:
                images.append(result)
                print(f"[Gemini Banana] ✅ 이미지 {i+1}/{num_images} 생성 완료")

    except ImportError:
        st.warning("Gemini 생성기를 찾을 수 없습니다.")
    except Exception as e:
        st.error(f"Gemini 오류: {str(e)}")

    return images


def _generate_with_dalle(
    prompt: str,
    model: str,
    width: int,
    height: int,
    num_images: int
) -> list:
    """OpenAI DALL-E API로 이미지 생성"""
    images = []

    try:
        from openai import OpenAI

        client = OpenAI()

        # DALL-E 3는 한 번에 1개만 생성 가능
        for i in range(num_images):
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=f"{width}x{height}",
                quality="standard",
                n=1
            )

            if response.data:
                import requests
                img_url = response.data[0].url
                img_response = requests.get(img_url)
                if img_response.status_code == 200:
                    images.append(img_response.content)
                    print(f"[DALL-E] ✅ 이미지 {i+1}/{num_images} 생성 완료")

    except ImportError:
        st.warning("OpenAI 라이브러리를 찾을 수 없습니다.")
    except Exception as e:
        st.error(f"DALL-E 오류: {str(e)}")

    return images


def _save_regenerated_images(
    char_name: str,
    scene_num: int,
    project_path: Path,
    images: list
) -> list:
    """
    재생성된 이미지 저장

    Returns:
        저장된 이미지 경로 리스트
    """
    saved_paths = []

    # 저장 디렉토리
    char_dir = project_path / "images" / "characters"
    char_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time() * 1000)

    for idx, img_data in enumerate(images):
        try:
            # 파일명 생성
            safe_name = char_name.replace(' ', '_').replace('/', '_')
            filename = f"{safe_name}_scene{scene_num:03d}_{timestamp}_{idx}.png"
            filepath = char_dir / filename

            # 이미지 저장
            if isinstance(img_data, bytes):
                with open(filepath, 'wb') as f:
                    f.write(img_data)
            elif hasattr(img_data, 'save'):
                # PIL Image
                img_data.save(filepath, 'PNG')
            else:
                # base64 문자열일 수 있음
                import base64
                if isinstance(img_data, str):
                    img_bytes = base64.b64decode(img_data)
                    with open(filepath, 'wb') as f:
                        f.write(img_bytes)

            saved_paths.append(str(filepath))
            print(f"[저장] ✅ {filename}")

        except Exception as e:
            print(f"[저장] ❌ 이미지 {idx} 저장 실패: {e}")

    return saved_paths


# 다음 단계 안내
st.divider()
st.info("👉 캐릭터 설정이 완료되면 4단계 TTS 생성으로 이동하세요.")
st.page_link("pages/4_🎤_TTS_생성.py", label="🎤 4단계: TTS 생성", icon="➡️")
