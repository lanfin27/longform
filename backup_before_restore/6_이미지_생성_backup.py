# -*- coding: utf-8 -*-
"""
6단계: 이미지 생성 (리팩토링) - v2.0

탭 구조:
- 🎬 씬별 생성: 개별 씬 선택 → 배경 → 캐릭터 배치 → 합성 → 편집 → 저장
- 🚀 일괄 생성: 전체 씬 자동 생성
- 🖼️ 갤러리: 생성된 이미지 관리
- ⚙️ 설정: 스타일 및 API 설정

v2.0: 메모리 관리 및 텍스트 차단 강화
- memory_manager 통합
- prompt_sanitizer 통합
"""
import gc
import streamlit as st
from pathlib import Path
import sys
import os
import time
import json
from typing import List, Dict, Optional
from datetime import datetime

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    render_project_sidebar,
    update_project_step
)
from utils.data_loader import (
    load_image_prompts,
    load_segment_groups,
    get_content_images_dir,
    list_content_images,
    save_image_generation_log,
    load_scenes,
    get_scene_images_dir,
    list_scene_images
)
from config.settings import TOGETHER_API_KEY, IMAGE_MODELS
from utils.api_helper import require_api_key, show_api_status_sidebar
from utils.progress_ui import render_api_selector, StreamlitProgressUI
from core.api.api_manager import get_api_manager
from utils.style_manager import get_style_manager, check_and_clear_stale_style_cache, invalidate_style_cache, get_styles_by_segment as _fresh_get_styles
from components.style_selector import style_radio_selector, get_selected_style
from utils.prominent_people_sanitizer import (
    ProminentPeopleSanitizer,
    sanitize_prompt_for_imagefx,
    get_available_sanitizer_models,
    get_recommended_model,
    check_prominent_people_error
)
from utils.imagefx_ui_components import (
    show_cookie_status_banner,
    show_cookie_renewal_modal,
    show_cookie_expired_error_in_result,
    render_seed_lock_options,
    get_seed_for_generation,
    update_locked_seed_from_result,
    render_image_with_seed_info
)
from utils.imagefx_client import CookieExpiredError, ImageFXBatchGenerator
from utils.character_image_selector import (
    get_character_image_for_scene_from_session,
    check_characters_have_scene_poses
)
from components.image_viewer import (
    render_lightbox_container,
    render_lightbox_image,
    clickable_image,
    render_image_card_with_prompt
)
# 확대 + 프롬프트 뷰어 (st.dialog 기반)
from utils.image_viewer import (
    render_clickable_image,
    render_image_card_with_zoom,
    ImagePromptManager
)
from utils.scene_image_manager import (
    get_scene_image_manager,
    update_scene_background,
    update_scene_composite,
    sync_scene_images
)
from utils.settings_manager import (
    get_setting,
    set_setting,
    persistent_selectbox,
    persistent_radio,
    persistent_checkbox,
    persistent_number_input,
    render_settings_management_ui
)
from utils.scene_selector import (
    parse_scene_range_input,
    format_selected_scenes,
    generate_preset_ranges,
    apply_range_to_selection,
    get_selection_stats
)

# v2.0: 메모리 관리 및 프롬프트 정제
from utils.memory_manager import (
    cleanup_session_images,
    optimize_memory_for_batch,
    cleanup_after_batch,
    get_session_memory_stats,
    force_gc,
    get_paginated_images  # v2.2: 갤러리 페이지네이션
)
from utils.prompt_sanitizer import (
    sanitize_scene_prompt,
    enhance_prompt_for_no_text,
    get_text_blocking_negative
)

# 이미지 프롬프트 메타데이터 관리
from utils.image_prompt_metadata import (
    save_image_with_prompt,
    get_image_prompt_info,
    render_prompt_info_expander
)

# 프롬프트 선택적 다운로드 (v1.0)
try:
    from utils.prompt_download import (
        get_latest_image_per_scene,
        get_scenes_with_images,
        collect_prompts_for_selected_scenes,
        get_prompt_stats,
        generate_prompts_excel,
        generate_prompts_zip,
        format_timestamp,
        generate_prompts_excel_with_highlight,
        collect_prompts_with_korean_recommendation
    )
    PROMPT_DOWNLOAD_AVAILABLE = True
except ImportError:
    PROMPT_DOWNLOAD_AVAILABLE = False

# 한글 프롬프트 씬 선택기 (v1.1 - 분석 기준 선택 지원)
try:
    from utils.korean_scene_selector import (
        select_korean_scenes_by_ratio,
        select_korean_scenes_by_interval,
        select_korean_scenes_hybrid,
        recommend_korean_scenes_with_ai,
        extract_selected_scene_numbers,
        get_korean_selection_stats
    )
    KOREAN_SCENE_SELECTOR_AVAILABLE = True
except ImportError:
    KOREAN_SCENE_SELECTOR_AVAILABLE = False

# v1.2: 한글 씬 상태 관리 (수동 추가/제거 지원)
from utils.korean_scene_state import (
    init_korean_scene_state,
    get_all_selected_korean_scenes,
    get_auto_selected_scenes,
    get_manual_added_scenes,
    set_auto_selected_scenes,
    add_manual_scene,
    remove_manual_scene,
    is_korean_scene_selected,
    get_selection_source,
    get_selection_stats as get_korean_scene_stats,
    sync_with_legacy_state,
    update_legacy_state,
    clear_korean_scene_selection
)

# ⭐ v1.5: AIPromptManager 통합
try:
    from utils.ai_prompt_manager import AIPromptManager, get_prompt_manager
    PROMPT_MANAGER_AVAILABLE = True
except ImportError:
    PROMPT_MANAGER_AVAILABLE = False


def _count_scenes_with_korean_prompt(scenes: list) -> int:
    """한글프롬프트가 있는 씬 개수 계산"""
    count = 0
    for scene in scenes:
        korean_prompt = (
            scene.get('한글프롬프트') or
            scene.get('korean_prompt') or
            scene.get('image_prompt_ko') or
            scene.get('prompt_ko') or
            scene.get('image_prompt_korean_text') or
            scene.get('prompts', {}).get('image_prompt_korean_text') or
            ''
        )
        if korean_prompt and str(korean_prompt).strip():
            count += 1
    return count


# 프롬프트 미리보기 및 결과 추적 (v2.0)
from utils.prompt_builder import (
    PromptBuilder,
    build_scene_previews,
    render_multi_scene_prompt_preview,
    ScenePromptPreview,
    get_generation_tracker,
    clear_generation_tracker,
    render_generation_results,
    GenerationResultTracker
)

# 씬-캐릭터 통합 로더 (Problem 56 수정)
from utils.scene_character_loader import load_scenes_data, clear_scene_cache

# ✅ 이미지 API 선택기 (탭별 모델 선택 + 설정 버그 수정)
from utils.image_api_selector import (
    render_api_selector,
    get_current_api_settings,
    render_api_info_banner,
    get_model_display_name,
    IMAGE_API_OPTIONS
)

# ✅ 대표 캐릭터 시스템 import (캐릭터 합성 옵션 분리용)
from utils.representative_character import (
    RepresentativeCharacterManager,
    get_rep_char_manager
)


# ===================================================================
# 헬퍼 함수: 캐릭터 이름 추출 (v2.1)
# ===================================================================
def extract_character_names(characters: list) -> List[str]:
    """캐릭터 리스트에서 이름만 추출

    characters가 문자열 리스트 또는 딕셔너리 리스트일 수 있음:
    - ["발표자", "화자"] → 그대로 반환
    - [{"name": "발표자"}, {"name": "화자"}] → ["발표자", "화자"]

    Args:
        characters: 캐릭터 리스트 (문자열 또는 딕셔너리)

    Returns:
        캐릭터 이름 문자열 리스트
    """
    if not characters:
        return []

    names = []
    for c in characters:
        if isinstance(c, dict):
            name = c.get("name", "")
            if name:
                names.append(str(name))
        elif c:
            names.append(str(c))
    return names


def format_character_names(characters: list, max_count: int = 3) -> str:
    """캐릭터 리스트를 포맷된 문자열로 변환

    Args:
        characters: 캐릭터 리스트 (문자열 또는 딕셔너리)
        max_count: 최대 표시 개수

    Returns:
        "이름1, 이름2, 이름3..." 형태의 문자열
    """
    names = extract_character_names(characters)
    if not names:
        return ""

    display_names = names[:max_count]
    result = ", ".join(display_names)

    if len(names) > max_count:
        result += "..."

    return result


# 페이지 설정
st.set_page_config(
    page_title="이미지 생성",
    page_icon="🎨",
    layout="wide"
)

# ===================================================================
# CSS 스타일
# ===================================================================
st.markdown("""
<style>
/* 씬 카드 */
.scene-card {
    background: white;
    border: 2px solid #e0e0e0;
    border-radius: 12px;
    padding: 10px;
    margin-bottom: 10px;
    transition: all 0.2s ease;
}
.scene-card:hover {
    border-color: #667eea;
}
.scene-card.selected {
    border-color: #667eea;
    background: linear-gradient(135deg, rgba(102,126,234,0.1) 0%, rgba(118,75,162,0.1) 100%);
}

/* 갤러리 */
.gallery-item {
    position: relative;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 10px;
}
.gallery-overlay {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    background: rgba(0,0,0,0.7);
    color: white;
    padding: 5px 10px;
    font-size: 12px;
}

/* 단계 표시 */
.step-indicator {
    display: flex;
    margin-bottom: 20px;
}
.step {
    flex: 1;
    text-align: center;
    padding: 10px;
    background: #e0e0e0;
    margin: 0 2px;
    border-radius: 8px;
    font-size: 12px;
}
.step.active {
    background: #667eea;
    color: white;
}
.step.completed {
    background: #4CAF50;
    color: white;
}
</style>
""", unsafe_allow_html=True)

# ===================================================================
# 사이드바 및 프로젝트 설정
# ===================================================================
render_project_sidebar()
show_api_status_sidebar()

if not ensure_project_selected():
    st.stop()

# Lightbox 컨테이너 초기화 (페이지당 한 번)
render_lightbox_container()

project_path = get_current_project()

# ===================================================================
# 스타일 캐시 동기화 (v2.2)
# ===================================================================
# 스타일 관리 페이지에서 변경된 내용이 있으면 자동으로 감지하여 새로고침
# v2.2: 세션 키 클리어 + 페이지 재실행으로 변경사항 즉시 반영
if check_and_clear_stale_style_cache("image_generation", clear_keys=True):
    st.toast("🎨 스타일이 업데이트되었습니다! 페이지를 새로고침합니다...", icon="✨")
    # 짧은 대기 후 rerun으로 변경사항 즉시 반영
    import time as _time
    _time.sleep(0.3)
    st.rerun()

# ===================================================================
# 유틸리티 함수
# ===================================================================

# ⭐ 성능 최적화: 초기화 키 생성
def _get_image_gen_init_key():
    """이미지 생성 페이지 초기화 키"""
    return f"image_gen_initialized_{project_path}"


def sync_all_data():
    """페이지 로드 시 모든 데이터 동기화 (⭐ 초기화 최적화 적용)"""

    # ⭐ 성능 최적화: 이미 초기화된 경우 스킵
    init_key = _get_image_gen_init_key()
    if st.session_state.get(init_key, False):
        return

    # 씬 데이터 로드 (통합 로더 사용 - Problem 56 수정)
    scenes = load_scenes_data(str(project_path))
    if scenes:
        st.session_state["scenes"] = scenes

    # 캐릭터 데이터 로드
    try:
        from core.character.character_manager import CharacterManager
        manager = CharacterManager(str(project_path))
        all_chars = manager.get_all_characters()
        if all_chars:
            chars_dict = []
            for c in all_chars:
                char_data = {
                    "id": c.id,
                    "name": c.name,
                    "name_en": c.name_en,
                    "description": c.description,
                    "role": c.role,
                    "character_prompt": c.character_prompt,
                    "generated_images": c.generated_images if c.generated_images else []
                }
                if c.generated_images:
                    char_data["image_path"] = c.generated_images[-1]
                    char_data["image_url"] = c.generated_images[-1]
                chars_dict.append(char_data)
            st.session_state["characters"] = chars_dict
    except Exception as e:
        pass

    # 배경 이미지 로드 (캐싱 적용)
    bg_json = project_path / "images" / "backgrounds" / "backgrounds.json"
    if bg_json.exists():
        try:
            bg_mtime = bg_json.stat().st_mtime
            bg_data = _load_backgrounds_json_cached(str(bg_json), _mtime=bg_mtime)
            if bg_data:
                st.session_state["background_images"] = {str(k): v for k, v in bg_data.items()}
        except:
            pass

    # 합성 이미지 로드 (캐싱 적용)
    comp_json = project_path / "images" / "composited" / "composited.json"
    if comp_json.exists():
        try:
            comp_mtime = comp_json.stat().st_mtime
            comp_data = _load_composited_json_cached(str(comp_json), _mtime=comp_mtime)
            if comp_data:
                st.session_state["composited_images"] = comp_data
        except:
            pass

    # ✅ SceneImageManager 초기화 및 자동 동기화 (캐싱 최적화)
    # 캐시가 유효하면 파일 시스템 조회 없이 즉시 반환
    if "scene_images_synced" not in st.session_state:
        try:
            manager = get_scene_image_manager(str(project_path))
            if manager:
                # ✅ 캐싱된 동기화 사용 (60초간 유효)
                manager.sync_all_scenes_cached(force=False)
                st.session_state["scene_images_synced"] = True
        except Exception as e:
            print(f"[SceneImageManager] 초기화 중 오류: {e}")

    # ⭐ 성능 최적화: 초기화 완료 플래그 설정
    st.session_state[init_key] = True


# ⭐ 성능 최적화: 배경/합성 메타데이터 캐싱
@st.cache_data(ttl=300, show_spinner=False, max_entries=50)
def _load_backgrounds_json_cached(json_path_str: str, _mtime: float) -> Optional[Dict]:
    """배경 이미지 메타데이터 로드 (캐싱 적용) - mtime으로 자동 무효화"""
    try:
        with open(json_path_str, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


@st.cache_data(ttl=300, show_spinner=False, max_entries=50)
def _load_composited_json_cached(json_path_str: str, _mtime: float) -> Optional[Dict]:
    """합성 이미지 메타데이터 로드 (캐싱 적용) - mtime으로 자동 무효화"""
    try:
        with open(json_path_str, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


# ⭐ 성능 최적화: 씬 데이터 캐싱
@st.cache_data(ttl=60, show_spinner=False)
def _cached_load_scenes(project_path_str: str) -> List[Dict]:
    """씬 데이터 로드 (캐싱 적용)"""
    return load_scenes_data(project_path_str)


def get_scenes() -> List[Dict]:
    """
    씬 목록 가져오기

    통합 로더를 사용하여 프로젝트 파일에서 로드
    (Problem 56 수정: 프로젝트 간 데이터 혼동 방지)
    ⭐ 성능 최적화: 캐싱 적용
    """
    return _cached_load_scenes(str(project_path))


def get_scene_by_id(scene_id: int) -> Optional[Dict]:
    """씬 ID로 씬 정보 가져오기"""
    scenes = get_scenes()
    for scene in scenes:
        if scene.get("scene_id") == scene_id:
            return scene
    return None


def force_refresh_styles():
    """
    스타일 캐시 강제 새로고침 (v2.3)

    스타일 관리 페이지에서 수정한 내용이 반영되지 않을 때 호출
    """
    import os
    from pathlib import Path

    # 스타일 파일 경로
    styles_path = Path(__file__).parent.parent / "data" / "styles.json"

    # 파일 수정 시간 강제 업데이트 (세션 캐시 무효화)
    if styles_path.exists():
        current_mtime = os.path.getmtime(styles_path)
        st.session_state["_style_file_mtime_seen_image_generation"] = 0  # 강제 무효화
        print(f"[스타일 새로고침] 파일 mtime: {current_mtime}")

    # 캐시 무효화 트리거
    invalidate_style_cache()

    # 스타일 관련 세션 키 클리어
    keys_to_clear = [k for k in st.session_state.keys() if any(p in k.lower() for p in [
        'batch_style', 'selected_style', 'bg_style', 'composite_style'
    ])]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

    print(f"[스타일 새로고침] 클리어된 키: {len(keys_to_clear)}개")


# ⭐ 성능 최적화: 갤러리 이미지 목록 캐싱 (TTL 30초)
@st.cache_data(ttl=30, show_spinner=False)
def _cached_get_gallery_images(project_path_str: str) -> List[Dict]:
    """
    모든 생성된 이미지 목록 (캐싱 적용)

    v2.1: 글로벌 폴더(data/images/imagefx 등) 포함
    """
    images = []
    project_path_obj = Path(project_path_str)

    def scan_folder(folder: Path, img_type: str):
        """폴더 내 이미지 스캔"""
        if not folder or not folder.exists():
            return
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
            for f in folder.glob(ext):
                try:
                    images.append({
                        "path": str(f),
                        "filename": f.name,
                        "type": img_type,
                        "scene_id": extract_scene_id(f.name),
                        "created": f.stat().st_mtime
                    })
                except:
                    pass

    # 프로젝트 폴더 이미지
    scan_folder(project_path_obj / "images" / "composited", "composited")
    scan_folder(project_path_obj / "images" / "scenes", "scene")
    scan_folder(project_path_obj / "images" / "backgrounds", "background")

    # ⭐ v2.1: 글로벌 폴더 이미지 (ImageFX 등)
    global_images_dir = Path(__file__).parent.parent / "data" / "images"
    if global_images_dir.exists():
        scan_folder(global_images_dir / "imagefx", "imagefx")
        scan_folder(global_images_dir / "generated", "generated")
        scan_folder(global_images_dir / "backgrounds", "global_background")

    # ⭐ 씬 번호순 정렬 (1, 2, 3, 4... 순서)
    def _sort_key(x):
        scene_id = x.get("scene_id", "?")
        if scene_id.isdigit():
            return (0, int(scene_id))  # 숫자인 경우: 숫자순 정렬
        return (1, scene_id)  # 숫자가 아닌 경우: 뒤로 배치

    images.sort(key=_sort_key)
    return images


def get_all_gallery_images() -> List[Dict]:
    """모든 생성된 이미지 목록 (⭐ 캐싱된 함수 사용)"""
    return _cached_get_gallery_images(str(project_path))


def clear_gallery_cache():
    """
    갤러리 이미지 캐시 강제 무효화 (v2.2)

    이미지 삭제/추가 후 개수가 갱신되지 않을 때 호출
    """
    _cached_get_gallery_images.clear()
    print("[갤러리 캐시] 캐시 무효화됨")


def extract_scene_id(filename: str) -> str:
    """파일명에서 씬 ID 추출"""
    import re
    match = re.search(r'scene[_\-]?(\d+)', filename, re.IGNORECASE)
    if match:
        return match.group(1)
    return "?"


def save_to_storyboard(scene_id: int, image_path: str):
    """이미지를 스토리보드에 저장"""
    if "storyboard_images" not in st.session_state:
        st.session_state["storyboard_images"] = {}

    st.session_state["storyboard_images"][str(scene_id)] = image_path


def delete_image(image_path: str) -> bool:
    """이미지 삭제"""
    try:
        if os.path.exists(image_path):
            os.remove(image_path)
        return True
    except Exception as e:
        st.error(f"삭제 실패: {e}")
        return False


def get_background_for_scene(scene_id: int) -> Optional[Dict]:
    """씬의 배경 이미지 가져오기"""
    bg_images = st.session_state.get("background_images", {})
    return bg_images.get(str(scene_id))


def _get_scene_preview_text(scene: Dict, max_len: int = 100) -> str:
    """씬의 미리보기 텍스트 생성 (툴팁용)"""
    # script_text를 우선으로 확인 (씬 분석 결과의 표준 필드)
    text = (
        scene.get("script_text", "") or
        scene.get("narration", "") or
        scene.get("description", "") or
        scene.get("text", "")
    )
    if not text:
        return "텍스트 없음"
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def get_composited_for_scene(scene_id: int) -> Optional[str]:
    """
    씬의 합성 이미지 가져오기

    v3.14: 파일 유효성 검사 추가 (빈 파일/손상된 파일 제외)
    """
    comp_dir = project_path / "images" / "composited"
    if comp_dir.exists():
        # 최신 합성 이미지 찾기
        pattern = f"scene_{scene_id:03d}_*"
        files = sorted(comp_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)

        for file_path in files:
            # v3.14: 파일 유효성 검사
            try:
                # 파일 크기 체크 (최소 1KB 이상이어야 유효한 이미지)
                if file_path.stat().st_size < 1024:
                    continue

                # 이미지 파일 유효성 체크
                if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                    from PIL import Image
                    with Image.open(file_path) as img:
                        img.verify()  # 이미지 유효성 검증
                    return str(file_path)

            except Exception:
                # 손상된 파일 무시
                continue

    return None


# ===================================================================
# 캐릭터 합성 옵션 헬퍼 함수 (씬별 캐릭터 vs 대표 캐릭터)
# ===================================================================

def get_scene_characters_status() -> Dict:
    """
    씬별 캐릭터 상태 확인

    Returns:
        {"total": 씬 수, "available": 이미지 있는 씬 수}
    """
    scenes = get_scenes()
    if not scenes:
        return {"total": 0, "available": 0}

    total_with_characters = 0
    available_images = 0
    all_characters = st.session_state.get("characters", [])

    for scene in scenes:
        scene_characters = scene.get("characters", [])
        if scene_characters:
            total_with_characters += 1

            # 캐릭터 이미지 존재 확인
            has_image = False
            for char_name in scene_characters:
                char_info = next((c for c in all_characters if c.get("name") == char_name), None)
                if char_info:
                    char_image = char_info.get("image_path") or char_info.get("image_url")
                    if char_image and os.path.exists(char_image):
                        has_image = True
                        break
            if has_image:
                available_images += 1

    return {
        "total": total_with_characters,
        "available": available_images
    }


def get_representative_character_status() -> Dict:
    """
    대표 캐릭터 상태 확인

    Returns:
        {"defined": 정의 여부, "name": 이름, "action_images": 액션 이미지 수}
    """
    try:
        manager = get_rep_char_manager(str(project_path))
        character = manager.get_character()

        if not character:
            return {"defined": False, "name": "", "action_images": 0}

        # 액션 이미지 수 확인
        action_images_dir = project_path / "images" / "character_scenes"
        if not action_images_dir.exists():
            action_images_dir = project_path / "images" / "representative_character"

        action_count = 0
        if action_images_dir.exists():
            action_count = len(list(action_images_dir.glob("scene_*.png")))

        return {
            "defined": True,
            "name": character.name,
            "action_images": action_count
        }
    except Exception as e:
        print(f"[RepChar Status] 오류: {e}")
        return {"defined": False, "name": "", "action_images": 0}


def get_representative_character_image_for_scene(scene_id: int) -> Optional[str]:
    """
    특정 씬의 대표 캐릭터 액션 이미지 경로 가져오기

    Args:
        scene_id: 씬 ID

    Returns:
        이미지 경로 또는 None
    """
    # 1. RepresentativeCharacterManager에서 먼저 조회 (캐릭터 관리에서 생성한 이미지)
    try:
        from utils.representative_character import get_rep_char_manager
        rep_manager = get_rep_char_manager(str(project_path))

        # scene_actions에서 해당 씬 찾기
        action = rep_manager.get_scene_action(scene_id)
        if action and action.generated_image_path:
            if os.path.exists(action.generated_image_path):
                print(f"[RepCharImage] ✅ 씬 {scene_id} 이미지 발견 (Manager): {action.generated_image_path}")
                return action.generated_image_path
            else:
                print(f"[RepCharImage] ⚠️ 씬 {scene_id} 이미지 경로 있으나 파일 없음: {action.generated_image_path}")
        else:
            print(f"[RepCharImage] ℹ️ 씬 {scene_id} Manager에 액션 이미지 없음")

    except Exception as e:
        print(f"[RepCharImage] Manager 조회 실패: {e}")

    # 2. 폴백: 하드코딩된 경로 패턴으로 검색
    possible_paths = [
        # 캐릭터 관리에서 생성하는 패턴
        project_path / "images" / "character_scenes" / f"scene_{scene_id:03d}_character.png",
        project_path / "images" / "character_scenes" / f"scene_{scene_id:03d}.png",
        project_path / "images" / "character_scenes" / f"scene_{scene_id}.png",
        # 기존 패턴
        project_path / "images" / "representative_character" / f"scene_{scene_id:03d}_action.png",
        project_path / "images" / "representative_character" / f"scene_{scene_id:03d}.png",
    ]

    for path in possible_paths:
        if path.exists():
            print(f"[RepCharImage] ✅ 씬 {scene_id} 이미지 발견 (경로 패턴): {path}")
            return str(path)

    print(f"[RepCharImage] ❌ 씬 {scene_id} 이미지 없음")
    return None


def render_character_composite_options() -> str:
    """
    캐릭터 합성 옵션 UI 렌더링

    Returns:
        선택된 모드 ("none", "scene_character", "representative_character")
    """
    st.markdown("##### 🎭 캐릭터 합성 옵션")

    with st.container(border=True):
        # v1.0: 설정 영속성 - persistent_radio 사용
        composite_mode = persistent_radio(
            "캐릭터 합성 모드",
            options=["none", "scene_character", "representative_character"],
            page="image_generation",
            setting_key="character_composite_mode",
            format_func=lambda x: {
                "none": "❌ 합성 안 함 (배경만)",
                "scene_character": "👥 씬별 캐릭터 합성",
                "representative_character": "⭐ 대표 캐릭터 합성"
            }[x],
            horizontal=False,
            label_visibility="collapsed"
        )

        # 모드별 상태 표시
        if composite_mode == "none":
            st.caption("배경 이미지만 생성합니다. 캐릭터 합성 없음.")

        elif composite_mode == "scene_character":
            st.caption("📍 **씬 분석에서 식별된 캐릭터** 이미지를 사용합니다.")

            scene_chars = get_scene_characters_status()
            if scene_chars["available"] > 0:
                st.success(f"✅ {scene_chars['available']}/{scene_chars['total']} 씬에 캐릭터 이미지 있음")
            elif scene_chars["total"] > 0:
                st.warning(f"⚠️ 캐릭터 있는 씬 {scene_chars['total']}개, 이미지 생성 필요")
            else:
                st.warning("⚠️ 씬별 캐릭터가 없습니다.")

        elif composite_mode == "representative_character":
            st.caption("📍 **대표 캐릭터**의 씬별 포즈/표정 이미지를 사용합니다.")

            rep_status = get_representative_character_status()
            if rep_status["defined"]:
                st.success(f"✅ 대표 캐릭터: {rep_status['name']}")
                if rep_status["action_images"] > 0:
                    st.success(f"✅ {rep_status['action_images']}개 씬 액션 이미지 있음")
                else:
                    st.warning("⚠️ 씬별 액션 이미지가 없습니다. 캐릭터 관리에서 생성하세요.")
            else:
                st.error("❌ 대표 캐릭터가 정의되지 않았습니다.")
                st.caption("캐릭터 관리 → 대표 캐릭터 탭에서 먼저 정의해주세요.")

    return composite_mode


# ===================================================================
# 탭 1: 씬별 생성
# ===================================================================

def render_scene_editor_tab():
    """🎬 씬별 이미지 생성 탭"""
    st.markdown("## 🎬 씬별 이미지 생성")

    scenes = get_scenes()

    if not scenes:
        st.warning("⚠️ 씬이 없습니다. 먼저 '씬 분석' 단계를 실행하세요.")
        st.page_link("pages/3.5_🎬_씬_분석.py", label="🎬 씬 분석으로 이동", icon="➡️")
        return

    st.success(f"✅ {len(scenes)}개의 씬이 로드되었습니다.")

    # ✅ v2.0: API/모델 선택 UI (탭 상단에 배치)
    scene_api_provider, scene_model = render_api_selector(
        key_prefix="scene_gen",
        show_in_expander=True,
        expander_default_open=False,
        show_save_button=True
    )

    # === 이미지 동기화 버튼 ===
    col_sync, col_space = st.columns([1, 4])
    with col_sync:
        if st.button("🔄 이미지 새로고침", key="sync_scene_images", help="파일 시스템의 최신 이미지를 씬 데이터에 반영합니다"):
            # ✅ 캐시 무효화 후 강제 동기화
            from utils.scene_image_manager import invalidate_scene_image_cache, clear_image_path_cache
            invalidate_scene_image_cache(str(project_path))
            clear_image_path_cache()
            updated = sync_scene_images(str(project_path))
            if updated > 0:
                st.success(f"✅ {updated}개 이미지 경로 동기화됨")
                st.rerun()
            else:
                st.info("모든 이미지가 최신 상태입니다")

    # === 씬 선택 그리드 ===
    st.markdown("### 1️⃣ 씬 선택")

    selected_scene_id = st.session_state.get("editing_scene_id")
    storyboard = st.session_state.get("storyboard_images", {})

    # 그리드 표시
    cols = st.columns(min(4, len(scenes)))
    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", i + 1)

        with cols[i % 4]:
            # 씬 이미지 (합성 > 배경 > 플레이스홀더)
            comp_img = get_composited_for_scene(scene_id)
            bg_data = get_background_for_scene(scene_id)

            if comp_img and os.path.exists(comp_img):
                render_lightbox_image(comp_img, key=f"scene_sel_comp_{scene_id}_idx{i}")
                st.caption("✅ 합성완료")
            elif bg_data:
                bg_path = bg_data.get("path") or bg_data.get("url")
                if bg_path and os.path.exists(bg_path):
                    render_lightbox_image(bg_path, key=f"scene_sel_bg_{scene_id}_idx{i}")
                    st.caption("🏞️ 배경만")
                else:
                    st.markdown("""
                    <div style="background: #f0f0f0; height: 100px; display: flex;
                                align-items: center; justify-content: center; border-radius: 8px;">
                        🖼️ 이미지 없음
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background: #f0f0f0; height: 100px; display: flex;
                            align-items: center; justify-content: center; border-radius: 8px;">
                    🖼️ 이미지 없음
                </div>
                """, unsafe_allow_html=True)

            # 씬 정보
            st.markdown(f"**씬 {scene_id}**")
            chars = scene.get("characters", [])
            if chars:
                st.caption(f"👤 {format_character_names(chars, 3)}")

            # 선택 버튼 (인덱스 추가로 키 고유성 보장)
            is_selected = scene_id == selected_scene_id
            btn_type = "primary" if is_selected else "secondary"
            if st.button(
                "✏️ 편집 중" if is_selected else "선택",
                key=f"select_scene_{scene_id}_idx{i}",
                type=btn_type,
                use_container_width=True
            ):
                st.session_state["editing_scene_id"] = scene_id
                st.rerun()

    st.markdown("---")

    # === 선택된 씬 편집 ===
    if selected_scene_id:
        render_scene_detail_editor(selected_scene_id)
    else:
        st.info("👆 위에서 편집할 씬을 선택하세요.")


def render_scene_detail_editor(scene_id: int):
    """선택된 씬 상세 편집"""
    scene = get_scene_by_id(scene_id)

    if not scene:
        st.error("씬을 찾을 수 없습니다.")
        return

    st.markdown(f"### 2️⃣ 씬 {scene_id} 편집")

    # 씬 정보 표시
    with st.expander("📋 씬 정보", expanded=False):
        # script_text 우선 사용
        script_text = (
            scene.get('script_text', '') or
            scene.get('narration', '') or
            scene.get('description', '') or
            scene.get('text', '')
        )
        if script_text:
            st.markdown(f"**스크립트:** {script_text[:300]}{'...' if len(script_text) > 300 else ''}")

        st.markdown(f"**캐릭터:** {format_character_names(scene.get('characters', []))}")

        # 연출 가이드가 있으면 표시
        if scene.get('direction_guide'):
            st.markdown(f"**연출 가이드:** {scene.get('direction_guide')}")

    # 편집 단계 탭
    step_tabs = st.tabs([
        "🏞️ 배경",
        "🎭 캐릭터 배치",
        "🔄 합성",
        "✏️ 편집",
        "📝 프롬프트",
        "💾 저장"
    ])

    # --- 단계 1: 배경 ---
    with step_tabs[0]:
        render_background_step(scene_id, scene)

    # --- 단계 2: 캐릭터 배치 ---
    with step_tabs[1]:
        render_character_placement_step(scene_id, scene)

    # --- 단계 3: 합성 ---
    with step_tabs[2]:
        render_composite_step(scene_id, scene)

    # --- 단계 4: 편집 ---
    with step_tabs[3]:
        render_edit_step(scene_id, scene)

    # --- 단계 5: 프롬프트 ---
    with step_tabs[4]:
        render_prompts_tab(scene_id, scene)

    # --- 단계 6: 저장 ---
    with step_tabs[5]:
        render_save_step(scene_id, scene)


def render_prompts_tab(scene_id: int, scene: Dict):
    """프롬프트 탭 - 이미지/비디오 프롬프트 표시 및 복사"""
    st.markdown("#### 📝 AI 프롬프트")

    # 프롬프트 서브탭
    prompt_tabs = st.tabs(["🖼️ 이미지", "🇰🇷 한글텍스트", "🎬 비디오", "🎭 캐릭터", "📥 다운로드"])

    # --- 이미지 프롬프트 ---
    with prompt_tabs[0]:
        st.markdown("##### 배경 이미지 프롬프트")
        st.caption("씬 배경 생성용 (캐릭터 제외, 텍스트 없음)")

        # 영어 프롬프트 우선
        image_prompt = (
            scene.get("image_prompt_en", "") or
            scene.get("image_prompt_ko", "") or
            scene.get("prompts", {}).get("image_prompt_en", "") or
            "(프롬프트 없음 - 씬 분석을 다시 실행하세요)"
        )

        edited_img_prompt = st.text_area(
            "Image Prompt (EN)",
            value=image_prompt,
            height=120,
            key=f"img_prompt_edit_{scene_id}"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("📋 복사", key=f"copy_img_{scene_id}"):
                st.code(edited_img_prompt, language=None)
                st.success("위 텍스트를 복사하세요")

        with col2:
            if scene.get("image_prompt_ko"):
                with st.expander("🇰🇷 한국어 프롬프트"):
                    st.text(scene.get("image_prompt_ko"))

    # --- 🇰🇷 한글 텍스트 포함 프롬프트 (v2.0 신규) ---
    with prompt_tabs[1]:
        st.markdown("##### 한글 텍스트 포함 이미지 프롬프트")
        st.caption("나레이션 핵심 메시지를 한글 텍스트로 포함한 프롬프트 (외부 AI 이미지 생성기용)")

        korean_text_prompt = (
            scene.get("image_prompt_korean_text", "") or
            scene.get("prompts", {}).get("image_prompt_korean_text", "") or
            ""
        )

        if korean_text_prompt:
            edited_korean_prompt = st.text_area(
                "Korean Text Prompt",
                value=korean_text_prompt,
                height=150,
                key=f"korean_prompt_edit_{scene_id}"
            )

            col1, col2 = st.columns(2)
            with col1:
                if st.button("📋 복사", key=f"copy_korean_{scene_id}"):
                    st.code(edited_korean_prompt, language=None)
                    st.success("위 텍스트를 복사하세요")

            with col2:
                st.download_button(
                    label="📄 TXT 다운로드",
                    data=edited_korean_prompt,
                    file_name=f"scene_{scene_id:03d}_korean.txt",
                    mime="text/plain",
                    key=f"dl_korean_prompt_{scene_id}"
                )

            # 한글 텍스트 추출 표시
            import re
            korean_matches = re.findall(r'reading\s*"([^"]+)"', korean_text_prompt)
            if korean_matches:
                st.info(f"🔤 포함된 한글 텍스트: {' / '.join(korean_matches)}")
        else:
            st.warning("⚠️ 한글 텍스트 프롬프트가 없습니다. 씬 재분석이 필요합니다.")
            st.caption("씬 분석 페이지에서 다시 분석하면 `image_prompt_korean_text` 필드가 생성됩니다.")

    # --- 비디오 프롬프트 ---
    with prompt_tabs[2]:
        st.markdown("##### 비디오 프롬프트 (Image to Video)")
        st.caption("Runway, Pika, Kling 등 AI 비디오 생성용")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**🎭 캐릭터만 움직임**")
            st.caption("립싱크, 표정 연기에 적합")

            video_char = (
                scene.get("video_prompt_character", "") or
                scene.get("prompts", {}).get("video_prompt_character", "") or
                "Subtle facial expressions, gentle eye blinks, slight head movement, mouth moving as speaking"
            )

            edited_video_char = st.text_area(
                "Character Animation",
                value=video_char,
                height=100,
                key=f"video_char_{scene_id}",
                label_visibility="collapsed"
            )

            if st.button("📋 복사", key=f"copy_vchar_{scene_id}"):
                st.code(edited_video_char, language=None)

        with col2:
            st.markdown("**🎬 전체 움직임**")
            st.caption("시네마틱 연출에 적합")

            video_full = (
                scene.get("video_prompt_full", "") or
                scene.get("prompts", {}).get("video_prompt_full", "") or
                "Camera slowly zooms in, subtle character movements, ambient background motion"
            )

            edited_video_full = st.text_area(
                "Full Scene Animation",
                value=video_full,
                height=100,
                key=f"video_full_{scene_id}",
                label_visibility="collapsed"
            )

            if st.button("📋 복사", key=f"copy_vfull_{scene_id}"):
                st.code(edited_video_full, language=None)

        # AI 비디오 서비스 가이드
        with st.expander("💡 AI 비디오 생성 서비스 가이드"):
            st.markdown("""
**권장 서비스:**
- **Runway Gen-3 Alpha**: 가장 자연스러운 움직임, 립싱크 지원
- **Pika Labs**: 빠른 생성, 스타일라이즈 효과
- **Kling AI**: 긴 영상 생성 가능 (최대 10초)
- **Luma Dream Machine**: 고품질 시네마틱
- **D-ID / HeyGen**: 전문 립싱크

**프롬프트 팁:**
- **캐릭터만**: 4초 이내, 미세한 움직임 권장
- **전체 씬**: 카메라 움직임은 천천히
- **립싱크**: 별도 서비스 사용 추천 (D-ID, HeyGen)
""")

    # --- 캐릭터 프롬프트 ---
    with prompt_tabs[3]:
        st.markdown("##### 캐릭터 이미지 프롬프트")
        st.caption("캐릭터 단독 이미지 생성용")

        scene_chars = scene.get("characters", [])
        all_characters = st.session_state.get("characters", [])

        if scene_chars:
            for char_name in scene_chars:
                char_info = next((c for c in all_characters if c.get("name") == char_name), None)

                if char_info:
                    with st.expander(f"👤 {char_name}", expanded=True):
                        visual_prompt = char_info.get("visual_prompt", "") or char_info.get("character_prompt", "")

                        if visual_prompt:
                            st.text_area(
                                "Visual Prompt",
                                value=visual_prompt,
                                height=80,
                                key=f"char_visual_{scene_id}_{char_name}",
                                label_visibility="collapsed"
                            )
                            if st.button("📋 복사", key=f"copy_char_{scene_id}_{char_name}"):
                                st.code(visual_prompt, language=None)
                        else:
                            st.warning("visual_prompt가 없습니다. 캐릭터 관리 페이지에서 설정하세요.")

                        # 캐릭터 이미지 미리보기 (클릭 시 확대)
                        char_img = char_info.get("image_path") or char_info.get("image_url")
                        if char_img and os.path.exists(char_img):
                            clickable_image(char_img, width=150, key=f"char_preview_{scene_id}_{char_name}")
                else:
                    st.info(f"'{char_name}' 캐릭터 정보를 찾을 수 없습니다.")
        else:
            st.info("이 씬에 등장하는 캐릭터가 없습니다.")

    # --- 📥 다운로드 탭 (v2.0 신규) ---
    with prompt_tabs[4]:
        st.markdown("##### 📥 프롬프트 다운로드")
        st.caption("개별 프롬프트 TXT 파일 또는 엑셀 일괄 다운로드")

        # 프롬프트 수집
        image_prompt_en = scene.get("image_prompt_en", "") or scene.get("prompts", {}).get("image_prompt_en", "")
        korean_text_prompt = scene.get("image_prompt_korean_text", "") or scene.get("prompts", {}).get("image_prompt_korean_text", "")

        # 스타일 정보 가져오기 (있다면)
        style_prefix = st.session_state.get("selected_style_prefix", "")
        style_suffix = st.session_state.get("selected_style_suffix", "")

        # 최종 프롬프트 생성
        if style_prefix or style_suffix:
            final_en = f"{style_prefix}, {image_prompt_en}, {style_suffix}".strip(", ")
            final_korean = f"{style_prefix}, {korean_text_prompt}, {style_suffix}".strip(", ") if korean_text_prompt else ""
        else:
            final_en = image_prompt_en
            final_korean = korean_text_prompt

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**원본 (텍스트 없음)**")
            if image_prompt_en:
                st.download_button(
                    label="📄 원본 프롬프트 다운로드",
                    data=final_en,
                    file_name=f"scene_{scene_id:03d}_original.txt",
                    mime="text/plain",
                    key=f"dl_original_{scene_id}"
                )
            else:
                st.warning("원본 프롬프트 없음")

        with col2:
            st.markdown("**한글 텍스트 포함**")
            if korean_text_prompt:
                st.download_button(
                    label="📄 한글 프롬프트 다운로드",
                    data=final_korean,
                    file_name=f"scene_{scene_id:03d}_korean.txt",
                    mime="text/plain",
                    key=f"dl_korean_final_{scene_id}"
                )
            else:
                st.warning("한글 프롬프트 없음")

        # 프롬프트 미리보기
        with st.expander("👀 다운로드될 내용 미리보기"):
            st.markdown("**원본 최종 프롬프트:**")
            st.code(final_en[:500] + "..." if len(final_en) > 500 else final_en, language=None)

            if final_korean:
                st.markdown("**한글 최종 프롬프트:**")
                st.code(final_korean[:500] + "..." if len(final_korean) > 500 else final_korean, language=None)


def render_background_step(scene_id: int, scene: Dict):
    """배경 설정 단계"""
    st.markdown("#### 🏞️ 배경 이미지")

    bg_source = st.radio(
        "배경 소스",
        options=["🤖 AI 생성", "📤 업로드", "📁 기존 선택"],
        horizontal=True,
        key=f"bg_source_{scene_id}"
    )

    if bg_source == "🤖 AI 생성":
        # AI 생성 설정
        col1, col2 = st.columns([3, 1])

        with col1:
            # 프롬프트 우선순위: image_prompt_en > image_prompt_ko > prompts.image_prompt_en > background_prompt > description
            prompts_data = scene.get("prompts", {})
            default_prompt = (
                scene.get("image_prompt_en", "") or
                scene.get("image_prompt_ko", "") or
                prompts_data.get("image_prompt_en", "") or
                prompts_data.get("image_prompt_ko", "") or
                scene.get("background_prompt", "") or
                scene.get("description", "")
            )

            # 프롬프트 소스 표시
            prompt_source = "씬 분석 결과" if scene.get("image_prompt_en") or prompts_data.get("image_prompt_en") else "기본값"
            if default_prompt:
                st.caption(f"📝 프롬프트 소스: {prompt_source}")
            else:
                st.warning("⚠️ 씬 분석에서 이미지 프롬프트가 생성되지 않았습니다. 씬 분석을 다시 실행하거나 직접 입력하세요.")

            prompt = st.text_area(
                "배경 프롬프트 (편집 가능)",
                value=default_prompt,
                height=100,
                key=f"bg_prompt_{scene_id}",
                help="씬 분석에서 생성된 프롬프트입니다. 필요시 직접 수정할 수 있습니다."
            )

        with col2:
            # StyleManager에서 배경 스타일 목록 로드
            from utils.style_manager import get_styles_by_segment
            bg_styles = get_styles_by_segment("background")
            style_ids = [s.id for s in bg_styles]
            style_names = {s.id: s.name_ko for s in bg_styles}

            style = st.selectbox(
                "배경 스타일",
                options=style_ids,
                format_func=lambda x: style_names.get(x, x),
                key=f"bg_style_{scene_id}",
                help="스타일 관리 페이지에서 등록된 배경 스타일"
            )

            # 스타일 프롬프트 미리보기
            sel_style = next((s for s in bg_styles if s.id == style), None)
            if sel_style and sel_style.prompt_prefix:
                with st.expander("📝 스타일", expanded=False):
                    st.code(sel_style.prompt_prefix[:150] + "..." if len(sel_style.prompt_prefix) > 150 else sel_style.prompt_prefix, language=None)

            width = st.selectbox("너비", [1280, 1024], key=f"bg_width_{scene_id}")
            height = st.selectbox("높이", [720, 576], key=f"bg_height_{scene_id}")

        if st.button("🎨 배경 생성", type="primary", key=f"gen_bg_{scene_id}"):
            # v2.0: 세션에서 선택된 API/모델 가져오기
            selected_api = st.session_state.get("_scene_gen_api")
            selected_model = st.session_state.get("_scene_gen_model")
            generate_background_image(
                scene_id, prompt, style, width, height,
                api_provider=selected_api,
                model=selected_model
            )

    elif bg_source == "📤 업로드":
        uploaded = st.file_uploader(
            "배경 이미지 업로드",
            type=["png", "jpg", "jpeg"],
            key=f"bg_upload_{scene_id}"
        )

        if uploaded:
            st.image(uploaded, use_container_width=True)

            if st.button("✅ 이 배경 사용", key=f"use_uploaded_bg_{scene_id}"):
                save_uploaded_background(scene_id, uploaded)

    else:
        # 기존 배경 선택
        bg_dir = project_path / "images" / "backgrounds"
        if bg_dir.exists():
            bg_files = list(bg_dir.glob("*.png"))
            if bg_files:
                selected_bg = st.selectbox(
                    "기존 배경 선택",
                    options=[f.name for f in bg_files],
                    key=f"existing_bg_{scene_id}"
                )
                if selected_bg:
                    bg_path = bg_dir / selected_bg
                    st.image(str(bg_path), use_container_width=True)

                    if st.button("✅ 이 배경 사용", key=f"use_existing_bg_{scene_id}"):
                        set_background_for_scene(scene_id, str(bg_path))
            else:
                st.info("기존 배경 이미지가 없습니다.")
        else:
            st.info("배경 이미지 폴더가 없습니다.")

    # 현재 배경 표시
    st.markdown("---")
    st.markdown("**현재 설정된 배경:**")
    current_bg = get_background_for_scene(scene_id)
    if current_bg:
        bg_path = current_bg.get("path") or current_bg.get("url")
        if bg_path and os.path.exists(bg_path):
            st.image(bg_path, use_container_width=True)
            st.success("✅ 배경 설정됨")
        else:
            st.warning("배경 파일을 찾을 수 없습니다.")
    else:
        st.info("아직 배경이 설정되지 않았습니다.")


def render_character_placement_step(scene_id: int, scene: Dict):
    """캐릭터 배치 단계 - 드래그 편집기 포함"""
    st.markdown("#### 🎭 캐릭터 배치")

    scene_characters = scene.get("characters", [])

    if not scene_characters:
        st.info("이 씬에 등장하는 캐릭터가 없습니다.")
        return

    # 캐릭터 이름 추출 (딕셔너리 또는 문자열 지원)
    scene_char_names = extract_character_names(scene_characters)
    st.markdown(f"**등장 캐릭터:** {', '.join(scene_char_names)}")

    # 프로젝트 캐릭터 목록
    all_characters = st.session_state.get("characters", [])

    # 캐릭터별 위치 설정
    char_positions = st.session_state.get(f"char_positions_{scene_id}", {})

    # 배경 이미지 확인
    current_bg = get_background_for_scene(scene_id)

    # 편집 모드 선택
    edit_mode = st.radio(
        "편집 모드",
        options=["🖱️ 드래그 편집기", "🎚️ 슬라이더"],
        horizontal=True,
        key=f"edit_mode_{scene_id}"
    )

    if edit_mode == "🖱️ 드래그 편집기":
        # 드래그 편집기 모드
        if not current_bg:
            st.warning("⚠️ 드래그 편집기를 사용하려면 먼저 '배경' 탭에서 배경 이미지를 설정하세요.")
            st.info("슬라이더 모드로 전환하면 배경 없이도 위치를 설정할 수 있습니다.")
        else:
            bg_path = current_bg.get("path") or current_bg.get("url")

            if bg_path and os.path.exists(bg_path):
                st.success("🎮 **드래그 편집기** - 캐릭터를 드래그하여 위치 조정, 모서리를 드래그하여 크기 조정")

                # 캐릭터 레이어 구성
                char_layers = []
                for char_name in scene_characters:
                    char_info = next((c for c in all_characters if c.get("name") == char_name), None)

                    if char_info:
                        char_image = char_info.get("image_url") or char_info.get("image_path")
                        if char_image and os.path.exists(char_image):
                            pos = char_positions.get(char_name, {"x": 0.5, "y": 0.7, "scale": 1.0})
                            char_layers.append({
                                "id": char_info.get("id", char_name),
                                "name": char_name,
                                "image_url": char_image,
                                "x": pos.get("x", 0.5),
                                "y": pos.get("y", 0.7),
                                "width": 0.25 * pos.get("scale", 1.0),
                                "height": 0.4 * pos.get("scale", 1.0),
                                "z_index": 1
                            })

                if char_layers:
                    try:
                        from components.post_composite_editor import post_composite_editor
                        post_composite_editor(
                            background_url=bg_path,
                            character_layers=char_layers,
                            canvas_width=800,
                            canvas_height=450,
                            editor_id=f"placement_{scene_id}"
                        )

                        st.info("💡 **위치 저장** 버튼을 클릭하면 설정한 위치가 저장됩니다. '합성' 탭에서 합성을 실행하세요.")

                    except ImportError as e:
                        st.warning(f"드래그 편집기를 로드할 수 없습니다: {e}")
                        st.info("슬라이더 모드로 전환하세요.")
                else:
                    st.warning("배치할 캐릭터 이미지가 없습니다. 캐릭터 관리에서 먼저 캐릭터 이미지를 생성하세요.")
            else:
                st.warning("배경 이미지 파일을 찾을 수 없습니다.")

    else:
        # 슬라이더 모드
        st.info("🎚️ **슬라이더 모드** - 각 캐릭터의 위치와 크기를 숫자로 조정합니다.")

        for char_name in scene_characters:
            # 캐릭터 정보 찾기
            char_info = next((c for c in all_characters if c.get("name") == char_name), None)

            with st.expander(f"🎭 {char_name}", expanded=True):
                if char_info:
                    col1, col2 = st.columns([1, 3])

                    with col1:
                        # 캐릭터 이미지 (클릭 시 확대)
                        char_image = char_info.get("image_url") or char_info.get("image_path")
                        if char_image and os.path.exists(char_image):
                            clickable_image(char_image, width=120, key=f"slider_char_{scene_id}_{char_name}")
                        else:
                            st.markdown("👤 이미지 없음")

                    with col2:
                        # 위치 설정
                        pos = char_positions.get(char_name, {"x": 0.5, "y": 0.7, "scale": 1.0})

                        col_x, col_y, col_s = st.columns(3)

                        with col_x:
                            pos["x"] = st.slider(
                                "X 위치 (0=왼쪽, 1=오른쪽)",
                                0.0, 1.0, pos.get("x", 0.5), 0.05,
                                key=f"pos_x_{scene_id}_{char_name}"
                            )

                        with col_y:
                            pos["y"] = st.slider(
                                "Y 위치 (0=위, 1=아래)",
                                0.0, 1.0, pos.get("y", 0.7), 0.05,
                                key=f"pos_y_{scene_id}_{char_name}"
                            )

                        with col_s:
                            pos["scale"] = st.slider(
                                "크기 배율",
                                0.3, 2.0, pos.get("scale", 1.0), 0.1,
                                key=f"scale_{scene_id}_{char_name}"
                            )

                        char_positions[char_name] = pos
                else:
                    st.warning(f"'{char_name}' 캐릭터 정보를 찾을 수 없습니다.")
                    st.info("캐릭터 관리에서 먼저 캐릭터를 등록하세요.")

        # 위치 저장
        st.session_state[f"char_positions_{scene_id}"] = char_positions

        # 미리보기 버튼
        if st.button("👁️ 배치 미리보기 생성", key=f"preview_placement_{scene_id}"):
            if current_bg:
                with st.spinner("미리보기 생성 중..."):
                    preview = _generate_placement_preview(scene_id, scene, char_positions)
                    if preview:
                        st.image(preview, caption="배치 미리보기", use_container_width=True)
            else:
                st.warning("배경 이미지가 없어 미리보기를 생성할 수 없습니다.")


def _generate_placement_preview(scene_id: int, scene: Dict, char_positions: Dict) -> Optional[str]:
    """캐릭터 배치 미리보기 이미지 생성"""
    try:
        from PIL import Image, ImageDraw

        current_bg = get_background_for_scene(scene_id)
        if not current_bg:
            return None

        bg_path = current_bg.get("path") or current_bg.get("url")
        if not bg_path or not os.path.exists(bg_path):
            return None

        background = Image.open(bg_path).convert("RGBA")
        all_characters = st.session_state.get("characters", [])

        for char_name in scene.get("characters", []):
            char_info = next((c for c in all_characters if c.get("name") == char_name), None)

            if char_info:
                char_image_path = char_info.get("image_path") or char_info.get("image_url")

                if char_image_path and os.path.exists(char_image_path):
                    char_img = Image.open(char_image_path).convert("RGBA")

                    # 위치 및 크기 계산
                    pos = char_positions.get(char_name, {"x": 0.5, "y": 0.7, "scale": 1.0})

                    scale = pos.get("scale", 1.0)
                    new_height = int(background.height * 0.4 * scale)
                    aspect = char_img.width / char_img.height
                    new_width = int(new_height * aspect)

                    char_img = char_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                    x = int(pos.get("x", 0.5) * background.width - new_width / 2)
                    y = int(pos.get("y", 0.7) * background.height - new_height / 2)

                    # 반투명 합성 (미리보기용)
                    background.paste(char_img, (x, y), char_img)

        # 임시 저장
        preview_dir = project_path / "images" / "temp"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = preview_dir / f"preview_{scene_id}_{int(time.time())}.png"
        background.save(preview_path, "PNG")

        return str(preview_path)

    except Exception as e:
        st.error(f"미리보기 생성 실패: {e}")
        return None


def _sync_drag_editor_positions(scene_id: int) -> Dict:
    """
    드래그 편집기의 위치 데이터를 session_state에 동기화

    URL 파라미터에서 드래그 편집기가 저장한 위치 데이터를 읽어
    session_state에 저장합니다.
    """
    import base64

    editor_id = f"placement_{scene_id}"
    sync_key = f"editor_sync_{editor_id}"

    # URL 파라미터에서 위치 데이터 읽기
    query_params = st.query_params

    if sync_key in query_params:
        try:
            encoded = query_params[sync_key]
            # URL-safe base64 디코딩 + UTF-8
            decoded = base64.b64decode(encoded).decode('utf-8')
            positions_list = json.loads(decoded)

            # 위치 데이터를 session_state 형식으로 변환
            char_positions = {}
            for pos in positions_list:
                name = pos.get("name") or pos.get("id")
                if name:
                    # 드래그 편집기 형식을 session_state 형식으로 변환
                    # - x, y: 중심 비율 (0~1) - 동일
                    # - width: 캔버스 대비 너비 비율 (0~1) -> scale로 변환
                    # - flip_x, z_index: 동일

                    width = pos.get("width", 0.25)
                    scale = pos.get("scale", width / 0.25)  # 기본 0.25 대비 배율

                    char_positions[name] = {
                        "x": pos.get("x", 0.5),
                        "y": pos.get("y", 0.7),
                        "scale": scale,
                        "width": width,  # 원본 width도 저장
                        "height": pos.get("height", 0.4),  # 원본 height도 저장
                        "flip_x": pos.get("flip_x", False),
                        "z_index": pos.get("z_index", 1)
                    }

            # session_state에 저장
            if char_positions:
                st.session_state[f"char_positions_{scene_id}"] = char_positions
                print(f"[Sync] 씬 {scene_id}: {len(char_positions)}개 캐릭터 위치 동기화됨")
                return char_positions

        except Exception as e:
            print(f"[Sync] 위치 동기화 오류: {e}")

    return st.session_state.get(f"char_positions_{scene_id}", {})


def render_composite_step(scene_id: int, scene: Dict):
    """합성 단계"""
    st.markdown("#### 🔄 이미지 합성")

    # 🔄 드래그 편집기에서 저장한 위치 동기화
    synced_positions = _sync_drag_editor_positions(scene_id)

    # 현재 배경 확인
    current_bg = get_background_for_scene(scene_id)

    if not current_bg:
        st.warning("⚠️ 먼저 '배경' 단계에서 배경 이미지를 설정하세요.")
        return

    bg_path = current_bg.get("path") or current_bg.get("url")

    if not bg_path or not os.path.exists(bg_path):
        st.error("배경 이미지 파일을 찾을 수 없습니다.")
        return

    st.markdown("**배경 이미지:** (클릭하여 확대)")
    render_lightbox_image(bg_path, key=f"composite_bg_{scene_id}")

    # 현재 캐릭터 위치 정보 표시 (동기화된 데이터 사용)
    char_positions = st.session_state.get(f"char_positions_{scene_id}", {})
    if char_positions:
        st.success(f"✅ {len(char_positions)}개 캐릭터 위치 설정됨")
        with st.expander("📍 위치 정보 확인", expanded=True):
            for name, pos in char_positions.items():
                flip_str = " 🔄반전" if pos.get("flip_x") else ""
                scale = pos.get("scale", 1.0)
                st.caption(f"• **{name}**: X={pos.get('x', 0.5)*100:.0f}%, Y={pos.get('y', 0.7)*100:.0f}%, 크기={scale:.1f}x{flip_str}")
    else:
        # 기본 위치 자동 설정
        scene_characters = scene.get("characters", [])
        if scene_characters:
            st.info(f"📍 {len(scene_characters)}개 캐릭터가 기본 위치로 배치됩니다. 위치 조정은 '캐릭터 배치' 탭에서 가능합니다.")

    # 합성 옵션
    col1, col2 = st.columns(2)

    with col1:
        remove_bg = st.checkbox(
            "캐릭터 배경 제거 (rembg)",
            value=True,
            key=f"remove_bg_{scene_id}",
            help="캐릭터 이미지의 배경을 투명하게 만듭니다. rembg 라이브러리 필요."
        )

    with col2:
        output_format = st.selectbox(
            "출력 형식",
            options=["PNG", "JPEG"],
            key=f"output_format_{scene_id}"
        )

    # 캐릭터 포즈 설정 (씬별 포즈 지원)
    all_characters = st.session_state.get("characters", [])
    any_has_scene_poses, _ = check_characters_have_scene_poses(all_characters)

    if any_has_scene_poses:
        st.markdown("##### 🎭 캐릭터 포즈 설정")
        pose_mode = st.radio(
            "포즈 적용 방식",
            options=[
                "🎭 씬별 다른 포즈 (AI 분석 결과 적용)",
                "🎯 단일 포즈 (모든 씬에 동일)"
            ],
            key=f"pose_mode_{scene_id}",
            help="캐릭터 관리에서 씬별 포즈를 설정한 경우 '씬별 다른 포즈'를 선택하세요.",
            horizontal=True
        )
        use_scene_pose = "씬별" in pose_mode

        # 씬별 포즈 미리보기
        if use_scene_pose:
            scene_chars = scene.get("characters", [])
            for char_name in scene_chars:
                char_info = next((c for c in all_characters if c.get("name") == char_name), None)
                if char_info:
                    scene_poses = char_info.get("scene_poses", {})
                    pose_info = scene_poses.get(str(scene_id), {})
                    pose_name = pose_info.get("pose")
                    if pose_name:
                        st.caption(f"• **{char_name}**: {pose_name} 포즈")
    else:
        use_scene_pose = False

    st.session_state[f"use_scene_pose_{scene_id}"] = use_scene_pose

    # 합성 실행
    if st.button("🎨 합성 실행", type="primary", use_container_width=True, key=f"composite_{scene_id}"):
        with st.spinner("합성 중..."):
            result = execute_composite(scene_id, scene, remove_bg, use_scene_pose)

            if result:
                st.session_state[f"composite_result_{scene_id}"] = result
                st.success("✅ 합성 완료!")
                st.rerun()

    # 합성 결과 표시
    result = st.session_state.get(f"composite_result_{scene_id}")
    if result and os.path.exists(result):
        st.markdown("---")
        st.markdown("**합성 결과:**")
        # 확대 + 프롬프트 기능 포함
        render_clickable_image(
            image_path=result,
            scene_id=scene_id,
            scene=scene,
            key_prefix=f"composite_result_{scene_id}"
        )


def render_edit_step(scene_id: int, scene: Dict):
    """편집 단계 (드래그 에디터)"""
    st.markdown("#### ✏️ 합성 후 편집")

    result = st.session_state.get(f"composite_result_{scene_id}")

    if not result or not os.path.exists(result):
        st.info("먼저 '합성' 단계에서 이미지를 합성하세요.")
        return

    # 편집 모드 선택
    edit_view = st.radio(
        "편집 보기",
        options=["📸 합성 결과", "🎮 드래그 편집기"],
        horizontal=True,
        key=f"edit_view_{scene_id}"
    )

    if edit_view == "📸 합성 결과":
        st.markdown("**현재 합성 결과:**")
        # 확대 + 프롬프트 기능 포함
        render_clickable_image(
            image_path=result,
            scene_id=scene_id,
            scene=scene,
            key_prefix=f"edit_result_{scene_id}"
        )

        st.info("💡 캐릭터 위치를 수정하려면 '드래그 편집기' 모드로 전환하세요.")

    else:
        # 드래그 편집기 모드
        st.success("🎮 **드래그 편집기** - 캐릭터를 드래그하여 위치/크기 조정 후 재합성하세요.")

        try:
            from components.post_composite_editor import post_composite_editor

            current_bg = get_background_for_scene(scene_id)
            bg_url = current_bg.get("url") or current_bg.get("path") if current_bg else ""

            char_positions = st.session_state.get(f"char_positions_{scene_id}", {})
            all_characters = st.session_state.get("characters", [])

            char_layers = []
            for char_name, pos in char_positions.items():
                char_info = next((c for c in all_characters if c.get("name") == char_name), None)
                if char_info:
                    char_image = char_info.get("image_url") or char_info.get("image_path")
                    if char_image and os.path.exists(char_image):
                        char_layers.append({
                            "id": char_info.get("id", char_name),
                            "name": char_name,
                            "image_url": char_image,
                            "x": pos.get("x", 0.5),
                            "y": pos.get("y", 0.7),
                            "width": 0.25 * pos.get("scale", 1.0),
                            "height": 0.4 * pos.get("scale", 1.0),
                            "z_index": 1
                        })

            if char_layers and bg_url:
                post_composite_editor(
                    background_url=bg_url,
                    character_layers=char_layers,
                    canvas_width=800,
                    canvas_height=450,
                    editor_id=f"editor_scene_{scene_id}"
                )

                st.markdown("---")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔄 재합성 실행", type="primary", use_container_width=True, key=f"recomposite_{scene_id}"):
                        with st.spinner("재합성 중..."):
                            use_scene_pose = st.session_state.get(f"use_scene_pose_{scene_id}", False)
                            new_result = execute_composite(scene_id, scene, remove_bg=True, use_scene_pose=use_scene_pose)
                            if new_result:
                                st.session_state[f"composite_result_{scene_id}"] = new_result
                                st.success("재합성 완료!")
                                st.rerun()

                with col2:
                    st.info("💡 위치 저장 후 재합성을 클릭하세요.")

            else:
                if not char_layers:
                    st.warning("편집할 캐릭터가 없습니다.")
                if not bg_url:
                    st.warning("배경 이미지가 없습니다.")

        except ImportError:
            st.warning("드래그 편집기 컴포넌트를 사용할 수 없습니다.")
            render_clickable_image(
                image_path=result,
                scene_id=scene_id,
                scene=scene,
                key_prefix=f"edit_fallback_{scene_id}"
            )


def render_save_step(scene_id: int, scene: Dict):
    """저장 단계"""
    st.markdown("#### 💾 저장 및 적용")

    result = st.session_state.get(f"composite_result_{scene_id}")

    if not result or not os.path.exists(result):
        st.info("먼저 이미지를 합성하세요.")
        return

    # 확대 + 프롬프트 기능 포함
    render_clickable_image(
        image_path=result,
        scene_id=scene_id,
        scene=scene,
        key_prefix=f"save_result_{scene_id}"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        with open(result, "rb") as f:
            st.download_button(
                "💾 다운로드",
                data=f.read(),
                file_name=f"scene_{scene_id:03d}.png",
                mime="image/png",
                use_container_width=True,
                key=f"dl_composite_result_{scene_id}"
            )

    with col2:
        if st.button("📋 스토리보드에 적용", type="primary", use_container_width=True, key=f"apply_{scene_id}"):
            save_to_storyboard(scene_id, result)
            st.success("✅ 스토리보드에 적용되었습니다!")

    with col3:
        if st.button("🔄 처음부터", use_container_width=True, key=f"reset_{scene_id}"):
            # 편집 상태 초기화
            st.session_state.pop(f"composite_result_{scene_id}", None)
            st.session_state.pop(f"char_positions_{scene_id}", None)
            st.rerun()

    st.markdown("---")
    st.success("✅ 이 씬의 이미지 작업이 완료되었습니다!")

    # 다음 씬으로 이동
    scenes = get_scenes()
    current_idx = next((i for i, s in enumerate(scenes) if s.get("scene_id") == scene_id), -1)

    if current_idx >= 0 and current_idx < len(scenes) - 1:
        next_scene = scenes[current_idx + 1]
        if st.button(f"➡️ 다음 씬 ({next_scene.get('scene_id')}) 편집", key=f"next_scene_{scene_id}"):
            st.session_state["editing_scene_id"] = next_scene.get("scene_id")
            st.rerun()


# ===================================================================
# 탭 2: 일괄 생성
# ===================================================================

def render_batch_generation_tab():
    """🚀 일괄 생성 탭"""
    st.markdown("## 🚀 일괄 이미지 생성")

    scenes = get_scenes()

    if not scenes:
        st.warning("씬이 없습니다. 먼저 씬 분석을 실행하세요.")
        return

    # ✅ v2.0: API/모델 선택 UI (탭 상단에 배치)
    batch_api_provider, batch_model = render_api_selector(
        key_prefix="batch_gen",
        show_in_expander=True,
        expander_default_open=False,
        show_save_button=True
    )

    # 현재 선택된 API 정보 배너 표시
    render_api_info_banner(batch_api_provider, batch_model)

    # 서브탭 구성
    batch_tabs = st.tabs(["🎨 배경+합성 일괄 생성", "🔄 합성만 일괄 실행"])

    with batch_tabs[0]:
        _render_batch_background_and_composite(scenes)

    with batch_tabs[1]:
        _render_batch_composite_only(scenes)


def _render_imagefx_cookie_settings():
    """Google ImageFX 인증 설정 UI (Authorization 토큰 권장)"""
    from config.settings import load_imagefx_cookie, SECRETS_DIR, save_imagefx_auth_token, load_imagefx_auth_token

    # 현재 인증 상태 확인 (동적 로드)
    current_token = st.session_state.get("imagefx_auth_token", "") or load_imagefx_auth_token()
    current_cookie = st.session_state.get("imagefx_cookie") or load_imagefx_cookie()
    has_auth = bool(current_token) or bool(current_cookie)

    with st.expander("🔑 Google ImageFX 인증 설정", expanded=not has_auth):
        st.warning("""
        ⚠️ **주의사항**
        - ImageFX는 비공식 API입니다
        - **Authorization 토큰**이 필요합니다 (쿠키만으로는 부족)
        - 토큰은 일정 시간 후 만료됩니다
        """)

        # 현재 인증 상태 표시
        if current_token:
            preview = current_token[:30] + "..." if len(current_token) > 30 else current_token
            st.success(f"✅ Authorization 토큰 설정됨: `{preview}`")
        elif current_cookie:
            st.warning("⚠️ 쿠키만 설정됨 - Authorization 토큰 사용을 권장합니다")
        else:
            st.error("❌ 인증 정보가 설정되지 않았습니다")

        # Authorization 토큰 입력
        st.markdown("""
        ### Authorization 토큰 추출 방법
        1. [labs.google/fx/tools/image-fx](https://labs.google/fx/tools/image-fx) 접속 후 **로그인**
        2. `F12` → **Network** 탭 열기
        3. 이미지 생성 후 `runImageFx` 요청 찾기
        4. **Request Headers**에서 `Authorization:` 값 복사
        """)

        token_input = st.text_area(
            "Authorization 토큰",
            value="",
            height=80,
            placeholder="Bearer ya29.a0ARrdaM8xYz... 또는 토큰 값만",
            key="imagefx_token_input_page6"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔑 토큰 저장", key="save_imagefx_token_page6"):
                if token_input.strip():
                    if save_imagefx_auth_token(token_input.strip()):
                        st.session_state["imagefx_auth_token"] = token_input.strip()
                        st.success("✅ 토큰이 저장되었습니다!")
                        st.rerun()
                    else:
                        st.error("토큰 저장 실패")
                else:
                    st.warning("토큰을 입력해주세요")

        with col2:
            if st.button("✅ 토큰 테스트", key="test_imagefx_token_page6"):
                test_token = token_input.strip() or current_token
                if test_token:
                    from utils.imagefx_client import ImageFXClient, ImagenModel, AspectRatio
                    is_valid, message, _ = ImageFXClient.validate_credentials(authorization_token=test_token)

                    if not is_valid:
                        st.error(f"❌ {message}")
                    else:
                        st.info(f"✓ {message}")
                        with st.spinner("API 테스트 중... (최대 60초)"):
                            try:
                                client = ImageFXClient(authorization_token=test_token)
                                images = client.generate_image(
                                    prompt="A simple red circle on white background",
                                    model=ImagenModel.IMAGEN_4,
                                    aspect_ratio=AspectRatio.SQUARE,
                                    num_images=1,
                                    timeout=60
                                )
                                if images:
                                    st.success("✅ 토큰이 유효합니다!")
                                else:
                                    st.error("❌ 이미지 생성 실패")
                            except Exception as e:
                                st.error(f"❌ 테스트 실패: {e}")
                else:
                    st.warning("테스트할 토큰이 없습니다")


def _render_batch_background_and_composite(scenes: List[Dict]):
    """배경 생성 + 합성 일괄 실행"""
    st.info("💡 여러 씬의 배경과 합성 이미지를 한 번에 생성합니다.")

    # ============================================================
    # 씬 선택 (범위 선택 기능 추가)
    # ============================================================
    total_scenes = len(scenes)
    st.markdown(f"### 🎬 생성할 씬 선택 ({total_scenes}개)")

    # 완료된 씬 목록 생성
    completed_scene_ids = set()
    scene_id_list = []
    for scene in scenes:
        scene_id = scene.get("scene_id")
        scene_id_list.append(scene_id)
        if get_composited_for_scene(scene_id) is not None:
            completed_scene_ids.add(scene_id)

    # ============================================================
    # 빠른 선택 섹션
    # ============================================================
    with st.container(border=True):
        st.markdown("#### ⚡ 빠른 선택")

        # 1행: 기본 버튼들
        btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

        with btn_col1:
            if st.button("✅ 전체 선택", key="batch_select_all", use_container_width=True):
                for scene in scenes:
                    st.session_state[f"batch_select_{scene.get('scene_id')}"] = True
                st.rerun()

        with btn_col2:
            if st.button("❌ 전체 해제", key="batch_deselect_all", use_container_width=True):
                for scene in scenes:
                    st.session_state[f"batch_select_{scene.get('scene_id')}"] = False
                st.rerun()

        with btn_col3:
            if st.button("⬜ 미완료만", key="batch_select_incomplete", use_container_width=True):
                for scene in scenes:
                    scene_id = scene.get("scene_id")
                    has_image = get_composited_for_scene(scene_id) is not None
                    st.session_state[f"batch_select_{scene_id}"] = not has_image
                st.rerun()

        with btn_col4:
            if st.button("🔄 선택 반전", key="batch_invert_selection", use_container_width=True):
                for scene in scenes:
                    scene_id = scene.get("scene_id")
                    current = st.session_state.get(f"batch_select_{scene_id}", False)
                    st.session_state[f"batch_select_{scene_id}"] = not current
                st.rerun()

        st.markdown("---")

        # 2행: 범위 선택
        st.markdown("**📍 범위 선택**")

        range_col1, range_col2, range_col3, range_col4, range_col5 = st.columns([1.5, 0.5, 1.5, 1.5, 1.5])

        with range_col1:
            range_start = st.number_input(
                "시작",
                min_value=1,
                max_value=total_scenes,
                value=1,
                key="batch_range_start",
                label_visibility="collapsed"
            )

        with range_col2:
            st.markdown("<div style='text-align: center; padding-top: 8px; font-weight: bold;'>~</div>", unsafe_allow_html=True)

        with range_col3:
            range_end = st.number_input(
                "끝",
                min_value=1,
                max_value=total_scenes,
                value=min(10, total_scenes),
                key="batch_range_end",
                label_visibility="collapsed"
            )

        with range_col4:
            range_mode = st.selectbox(
                "모드",
                options=["새로 선택", "추가", "제외"],
                key="batch_range_mode",
                label_visibility="collapsed"
            )

        with range_col5:
            if st.button(
                f"✅ 범위 적용",
                key="batch_apply_range",
                use_container_width=True
            ):
                # 범위 유효성 검사
                if range_start <= range_end:
                    for scene in scenes:
                        scene_id = scene.get("scene_id")
                        in_range = range_start <= scene_id <= range_end

                        if range_mode == "새로 선택":
                            st.session_state[f"batch_select_{scene_id}"] = in_range
                        elif range_mode == "추가":
                            if in_range:
                                st.session_state[f"batch_select_{scene_id}"] = True
                        elif range_mode == "제외":
                            if in_range:
                                st.session_state[f"batch_select_{scene_id}"] = False

                    st.toast(f"씬 {range_start}~{range_end} {range_mode} 완료!")
                    st.rerun()
                else:
                    st.error("시작 번호가 끝 번호보다 작아야 합니다.")

        st.caption(f"({range_end - range_start + 1}개 씬)")

        st.markdown("---")

        # 3행: 직접 입력
        st.markdown("**🔢 직접 입력** (예: `1-10, 15, 20-30`)")

        input_col1, input_col2 = st.columns([4, 1])

        with input_col1:
            custom_input = st.text_input(
                "씬 번호 입력",
                placeholder="1-10, 15, 20-30, 50 또는 1~10, 15, 20~30",
                key="batch_custom_scene_input",
                label_visibility="collapsed"
            )

        with input_col2:
            if st.button("✅ 적용", key="batch_apply_custom", use_container_width=True):
                if custom_input:
                    parsed_scenes = parse_scene_range_input(custom_input, total_scenes)

                    if parsed_scenes:
                        # 모두 해제 후 파싱된 씬만 선택
                        for scene in scenes:
                            scene_id = scene.get("scene_id")
                            st.session_state[f"batch_select_{scene_id}"] = scene_id in parsed_scenes
                        st.toast(f"{len(parsed_scenes)}개 씬 선택됨!")
                        st.rerun()
                    else:
                        st.error("올바른 형식으로 입력해주세요. 예: 1-10, 15, 20-30")

        st.markdown("---")

        # 4행: 프리셋 버튼
        st.markdown("**📊 프리셋**")

        presets = generate_preset_ranges(total_scenes, chunk_size=10)

        # 프리셋 버튼 그리드 (한 줄에 6개)
        cols_per_row = 6

        for row_start in range(0, len(presets), cols_per_row):
            row_presets = presets[row_start:row_start + cols_per_row]
            preset_cols = st.columns(cols_per_row)

            for idx, (p_start, p_end) in enumerate(row_presets):
                with preset_cols[idx]:
                    label = f"{p_start}~{p_end}"

                    if st.button(label, key=f"batch_preset_{p_start}_{p_end}", use_container_width=True):
                        for scene in scenes:
                            scene_id = scene.get("scene_id")
                            st.session_state[f"batch_select_{scene_id}"] = p_start <= scene_id <= p_end
                        st.rerun()

        # 특수 프리셋 (전반부/후반부)
        mid_point = total_scenes // 2

        st.markdown("")
        half_col1, half_col2, half_col3 = st.columns(3)

        with half_col1:
            if st.button(f"📍 전반부 (1~{mid_point})", key="batch_preset_first_half", use_container_width=True):
                for scene in scenes:
                    scene_id = scene.get("scene_id")
                    st.session_state[f"batch_select_{scene_id}"] = scene_id <= mid_point
                st.rerun()

        with half_col2:
            if st.button(f"📍 후반부 ({mid_point+1}~{total_scenes})", key="batch_preset_second_half", use_container_width=True):
                for scene in scenes:
                    scene_id = scene.get("scene_id")
                    st.session_state[f"batch_select_{scene_id}"] = scene_id > mid_point
                st.rerun()

        with half_col3:
            odd_even_col1, odd_even_col2 = st.columns([2, 1])

            with odd_even_col1:
                odd_even = st.selectbox(
                    "홀수/짝수",
                    options=["홀수 씬만", "짝수 씬만"],
                    key="batch_odd_even_select",
                    label_visibility="collapsed"
                )

            with odd_even_col2:
                if st.button("적용", key="batch_apply_odd_even"):
                    for scene in scenes:
                        scene_id = scene.get("scene_id")
                        if odd_even == "홀수 씬만":
                            st.session_state[f"batch_select_{scene_id}"] = scene_id % 2 == 1
                        else:
                            st.session_state[f"batch_select_{scene_id}"] = scene_id % 2 == 0
                    st.rerun()

    # ============================================================
    # 선택 현황 표시
    # ============================================================
    selected_scenes = []
    for scene in scenes:
        scene_id = scene.get("scene_id")
        if st.session_state.get(f"batch_select_{scene_id}", False):
            selected_scenes.append(scene_id)

    selected_count = len(selected_scenes)
    selected_summary = format_selected_scenes(selected_scenes) if selected_scenes else "없음"

    # 완료/미완료 통계
    selected_completed = len([s for s in selected_scenes if s in completed_scene_ids])
    selected_incomplete = selected_count - selected_completed

    if selected_count > 0:
        st.success(f"✅ **{selected_count}개** 씬 선택됨: {selected_summary}")
        if selected_completed > 0 or selected_incomplete > 0:
            st.caption(f"(완료: {selected_completed}개, 미완료: {selected_incomplete}개)")
    else:
        st.warning("⚠️ 선택된 씬이 없습니다.")

    # ============================================================
    # 개별 체크박스 (기존 UI - Expander로 축소)
    # ============================================================
    with st.expander("📋 개별 씬 선택 (체크박스)", expanded=False):
        # 선택 UI 모드
        view_mode = st.radio(
            "표시 모드",
            options=["컴팩트", "텍스트 포함"],
            horizontal=True,
            key="batch_view_mode"
        )

        if view_mode == "컴팩트":
            # 컴팩트 모드
            cols_count = 6
            for row_start in range(0, len(scenes), cols_count):
                row_scenes = scenes[row_start:row_start + cols_count]
                cols = st.columns(cols_count)

                for col_idx, scene in enumerate(row_scenes):
                    scene_id = scene.get("scene_id")
                    unique_idx = row_start + col_idx  # 고유 인덱스
                    with cols[col_idx]:
                        has_image = get_composited_for_scene(scene_id) is not None
                        status_icon = "✅" if has_image else "⬜"

                        is_selected = st.checkbox(
                            f"{status_icon} 씬 {scene_id}",
                            value=st.session_state.get(f"batch_select_{scene_id}", False),
                            key=f"batch_cb_{scene_id}_compact_idx{unique_idx}",
                            help=_get_scene_preview_text(scene)
                        )

                        if is_selected:
                            st.session_state[f"batch_select_{scene_id}"] = True
                        else:
                            st.session_state[f"batch_select_{scene_id}"] = False
        else:
            # 텍스트 포함 모드
            for i, scene in enumerate(scenes):
                scene_id = scene.get("scene_id")
                has_image = get_composited_for_scene(scene_id) is not None
                status_icon = "✅" if has_image else "⬜"

                scene_text = (
                    scene.get("script_text", "") or
                    scene.get("narration", "") or
                    scene.get("description", "") or
                    scene.get("text", "")
                )

                col1, col2 = st.columns([1, 10])

                with col1:
                    is_selected = st.checkbox(
                        f"선택",
                        value=st.session_state.get(f"batch_select_{scene_id}", False),
                        key=f"batch_cb_{scene_id}_text_idx{i}",
                        label_visibility="collapsed"
                    )

                    if is_selected:
                        st.session_state[f"batch_select_{scene_id}"] = True
                    else:
                        st.session_state[f"batch_select_{scene_id}"] = False

                with col2:
                    chars = scene.get("characters", [])
                    char_str = f" 👤 {format_character_names(chars, 2)}" if chars else ""

                    with st.expander(f"{status_icon} **씬 {scene_id}**{char_str}", expanded=False):
                        st.markdown(f"**내용:**")
                        st.text(scene_text if scene_text else "(텍스트 없음)")

                        if scene.get("background_prompt"):
                            st.markdown(f"**배경 프롬프트:** {scene.get('background_prompt')[:100]}...")

    st.markdown("---")

    # ============================================================
    # 생성 옵션 (스타일 모드 선택 추가)
    # ============================================================
    st.markdown("### 생성 옵션")

    # 스타일 모드 선택
    from utils.style_manager import (
        get_styles_by_segment,
        get_scene_composite_styles,
        get_scene_composite_style_by_name,
        build_scene_composite_prompt
    )

    with st.container(border=True):
        st.markdown("#### 🎨 스타일 모드 선택")

        # v1.0: 설정 영속성 - persistent_radio 사용
        style_mode = persistent_radio(
            "이미지 생성 모드",
            options=[
                "🖼️ 배경만 생성 (배경 스타일 사용)",
                "🎬 씬 합성 생성 (배경 + 캐릭터 통합 스타일)"
            ],
            page="image_generation",
            setting_key="style_mode",
            horizontal=False
        )

        # 모드 설명
        if "배경만" in style_mode:
            st.caption("💡 배경 이미지만 생성합니다. 캐릭터는 별도로 합성됩니다.")
        else:
            st.caption("💡 배경과 캐릭터가 함께 포함된 완성 이미지를 생성합니다. (합성 불필요)")

    st.markdown("")

    # ============================================================
    # 모드별 옵션 표시
    # ============================================================

    if "배경만" in style_mode:
        # ======== 배경만 생성 모드 (기존) ========
        col1, col2, col3 = st.columns(3)

        with col1:
            # 스타일 선택 + 새로고침 버튼
            style_col1, style_col2 = st.columns([4, 1])

            with style_col1:
                bg_styles = get_styles_by_segment("background")

                style_options = [(s.id, s.name_ko) for s in bg_styles]
                style_ids = [s[0] for s in style_options]
                style_names = {s[0]: s[1] for s in style_options}

                style = st.selectbox(
                    "배경 스타일",
                    options=style_ids,
                    format_func=lambda x: style_names.get(x, x),
                    key="batch_style",
                    help="스타일 관리 페이지에서 등록된 배경 스타일"
                )

            with style_col2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔄", key="refresh_bg_styles", help="스타일 새로고침 (스타일 관리에서 수정한 내용 반영)"):
                    force_refresh_styles()
                    st.toast("✅ 스타일 새로고침 완료!")
                    st.rerun()

            # 선택된 스타일 프롬프트 미리보기
            selected_style = next((s for s in bg_styles if s.id == style), None)
            if selected_style and (selected_style.prompt_prefix or selected_style.prompt_suffix or selected_style.negative_prompt):
                with st.expander("📝 스타일 프롬프트 미리보기", expanded=False):
                    if selected_style.prompt_prefix:
                        st.caption("**Prefix:**")
                        st.code(selected_style.prompt_prefix[:200] + "..." if len(selected_style.prompt_prefix) > 200 else selected_style.prompt_prefix, language=None)
                    if selected_style.prompt_suffix:
                        st.caption("**Suffix:**")
                        st.code(selected_style.prompt_suffix[:200] + "..." if len(selected_style.prompt_suffix) > 200 else selected_style.prompt_suffix, language=None)
                    if selected_style.negative_prompt:
                        st.caption("**🚫 Negative Prompt:**")
                        st.code(selected_style.negative_prompt[:300] + "..." if len(selected_style.negative_prompt) > 300 else selected_style.negative_prompt, language=None)

        with col2:
            generate_background = st.checkbox("배경 생성", value=True, key="batch_gen_bg")

        with col3:
            remove_bg = st.checkbox("캐릭터 배경 제거", value=True, key="batch_remove_bg")

        # ✅ 수정: 캐릭터 합성 옵션 분리 (3가지 모드)
        st.markdown("---")
        character_composite_mode = render_character_composite_options()

        # 합성 모드에 따른 변수 설정
        generate_composite = character_composite_mode != "none"

        # 씬별 포즈 사용 여부 (씬별 캐릭터 모드일 때만 표시)
        batch_use_scene_pose = False
        if character_composite_mode == "scene_character":
            all_characters = st.session_state.get("characters", [])
            any_has_scene_poses, _ = check_characters_have_scene_poses(all_characters)
            if any_has_scene_poses:
                batch_use_scene_pose = st.checkbox("씬별 포즈 적용", value=True, key="batch_use_scene_pose",
                                                   help="캐릭터 관리에서 설정한 씬별 포즈를 적용합니다.")

        # 씬 합성 모드용 변수 초기화 (사용하지 않음)
        composite_style = None
        apply_negative = True

    else:
        # ======== 씬 합성 생성 모드 (NEW!) ========
        col1, col2 = st.columns([2, 1])

        with col1:
            # 씬 합성 스타일 선택 + 새로고침 버튼
            style_col1, style_col2 = st.columns([4, 1])

            with style_col1:
                scene_styles = get_scene_composite_styles()

                if not scene_styles:
                    st.warning("⚠️ 씬 합성 스타일이 없습니다. 스타일 관리 페이지에서 추가해주세요.")
                    composite_style_id = None
                else:
                    scene_style_options = [(s.id, s.name_ko) for s in scene_styles]
                    scene_style_ids = [s[0] for s in scene_style_options]
                    scene_style_names = {s[0]: s[1] for s in scene_style_options}

                    composite_style_id = st.selectbox(
                        "🎬 씬 합성 스타일",
                        options=scene_style_ids,
                        format_func=lambda x: scene_style_names.get(x, x),
                        key="batch_composite_style",
                        help="스타일 관리 페이지에서 등록된 씬 합성 스타일"
                    )

                    composite_style = next((s for s in scene_styles if s.id == composite_style_id), None)

            with style_col2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔄", key="refresh_composite_styles", help="스타일 새로고침 (스타일 관리에서 수정한 내용 반영)"):
                    force_refresh_styles()
                    st.toast("✅ 스타일 새로고침 완료!")
                    st.rerun()

        with col2:
            apply_negative = st.checkbox(
                "네거티브 프롬프트 적용",
                value=True,
                key="batch_apply_negative"
            )

        # 선택된 씬 합성 스타일 상세 표시
        if composite_style_id and scene_styles:
            composite_style = next((s for s in scene_styles if s.id == composite_style_id), None)

            if composite_style:
                st.markdown("---")
                st.markdown("**📋 프롬프트 구조:**")
                st.code("[Prefix] + [씬 이미지 프롬프트] + [Suffix]\nNegative: [스타일 Negative 프롬프트]", language=None)

                # 스타일 프롬프트 미리보기
                with st.expander("🎨 씬 합성 스타일 프롬프트 미리보기", expanded=False):
                    st.markdown("**Prefix:**")
                    st.code(composite_style.prompt_prefix[:300] + "..." if len(composite_style.prompt_prefix) > 300 else composite_style.prompt_prefix or "(없음)", language=None)

                    st.markdown("**Suffix:**")
                    st.code(composite_style.prompt_suffix[:300] + "..." if len(composite_style.prompt_suffix) > 300 else composite_style.prompt_suffix or "(없음)", language=None)

                    st.markdown("**Negative:**")
                    st.code(composite_style.negative_prompt[:200] + "..." if len(composite_style.negative_prompt) > 200 else composite_style.negative_prompt or "(없음)", language=None)

                # 예시 프롬프트 (씬 1 기준)
                with st.expander("👁️ 완성 프롬프트 예시 (씬 1 기준)", expanded=False):
                    if scenes:
                        scene_1 = scenes[0]
                        prompts_data = scene_1.get("prompts", {})
                        scene_prompt = (
                            scene_1.get("image_prompt_en", "") or
                            prompts_data.get("image_prompt_en", "") or
                            scene_1.get("background_prompt", "")
                        )

                        if scene_prompt:
                            example_result = build_scene_composite_prompt(
                                scene_prompt=scene_prompt,
                                style=composite_style,
                                include_negative=apply_negative
                            )

                            st.markdown("**✅ Positive Prompt:**")
                            st.code(example_result["positive"][:500] + "..." if len(example_result["positive"]) > 500 else example_result["positive"], language=None)

                            if example_result["negative"]:
                                st.markdown("**❌ Negative Prompt:**")
                                st.code(example_result["negative"], language=None)
                        else:
                            st.info("씬 1에 이미지 프롬프트가 없습니다.")
                    else:
                        st.info("씬 데이터가 없습니다.")

        # 배경만 모드 변수 초기화 (사용하지 않음)
        style = None
        generate_background = True  # 씬 합성에서는 항상 생성
        generate_composite = False  # 씬 합성에서는 합성 불필요
        remove_bg = False
        batch_use_scene_pose = False

    st.markdown("---")

    # ============================================================
    # 시드 잠금 옵션 (이미지 일관성 유지)
    # ============================================================
    batch_api_provider = st.session_state.get("_batch_gen_api", "")
    if batch_api_provider == "Google ImageFX":
        with st.expander("🔒 이미지 일관성 유지 (시드 잠금)", expanded=False):
            batch_seed_lock_enabled, batch_locked_seed = render_seed_lock_options(key_prefix="batch_seed")
    else:
        batch_seed_lock_enabled = False
        batch_locked_seed = None
        # ImageFX가 아닌 경우 안내 메시지
        with st.expander("🔒 이미지 일관성 유지 (시드 잠금)", expanded=False):
            st.info("💡 시드 잠금 기능은 **Google ImageFX** API에서만 사용 가능합니다.")
            st.caption("Together.ai FLUX는 현재 시드 파라미터를 지원하지 않습니다.")

    st.markdown("---")

    # ============================================================
    # 프롬프트 미리보기 및 수정 섹션
    # ============================================================
    if selected_scenes and scenes:
        with st.expander("최종 프롬프트 미리보기 및 수정", expanded=False):
            from utils.prompt_builder import PromptBuilder

            # 첫 번째 선택 씬에 대한 예시
            first_scene_id = selected_scenes[0]
            first_scene = get_scene_by_id(first_scene_id)

            if first_scene:
                prompts_data = first_scene.get("prompts", {})
                scene_prompt = (
                    first_scene.get("image_prompt_en", "") or
                    prompts_data.get("image_prompt_en", "") or
                    first_scene.get("image_prompt_ko", "") or
                    first_scene.get("background_prompt", "") or
                    first_scene.get("description", "")
                )

                st.caption(f"씬 {first_scene_id} 프롬프트 구조 예시")

                builder = PromptBuilder()

                if "배경만" in style_mode:
                    # 배경만 생성 모드
                    selected_bg_style = next((s for s in get_styles_by_segment("background") if s.id == style), None) if style else None

                    if selected_bg_style and selected_bg_style.prompt_prefix:
                        builder.add(
                            name="스타일 Prefix",
                            content=selected_bg_style.prompt_prefix,
                            source=f"배경 스타일 > {selected_bg_style.name_ko}",
                            order=0
                        )

                    builder.add(
                        name="씬 이미지 프롬프트",
                        content=scene_prompt,
                        source=f"씬 분석 > 씬 {first_scene_id}",
                        order=1
                    )

                    if selected_bg_style and selected_bg_style.prompt_suffix:
                        builder.add(
                            name="스타일 Suffix",
                            content=selected_bg_style.prompt_suffix,
                            source=f"배경 스타일 > {selected_bg_style.name_ko}",
                            order=2
                        )

                    if selected_bg_style and selected_bg_style.negative_prompt:
                        builder.add_negative(
                            name="스타일 네거티브",
                            content=selected_bg_style.negative_prompt,
                            source=f"배경 스타일 > {selected_bg_style.name_ko}"
                        )

                else:
                    # 씬 합성 생성 모드
                    if composite_style:
                        if composite_style.prompt_prefix:
                            builder.add(
                                name="씬 합성 Prefix",
                                content=composite_style.prompt_prefix,
                                source=f"씬 합성 스타일 > {composite_style.name_ko}",
                                order=0
                            )

                        builder.add(
                            name="씬 이미지 프롬프트",
                            content=scene_prompt,
                            source=f"씬 분석 > 씬 {first_scene_id}",
                            order=1
                        )

                        if composite_style.prompt_suffix:
                            builder.add(
                                name="씬 합성 Suffix",
                                content=composite_style.prompt_suffix,
                                source=f"씬 합성 스타일 > {composite_style.name_ko}",
                                order=2
                            )

                        if apply_negative and composite_style.negative_prompt:
                            builder.add_negative(
                                name="씬 합성 네거티브",
                                content=composite_style.negative_prompt,
                                source=f"씬 합성 스타일 > {composite_style.name_ko}"
                            )

                build_result = builder.build()

                # 구성 요소 표시
                for i, comp in enumerate(build_result.components, 1):
                    st.markdown(f"**{i}. {comp.name}** ({comp.source})")
                    st.code(comp.content, language=None)

                st.info("위 구조가 모든 씬에 동일하게 적용됩니다. 씬마다 '씬 이미지 프롬프트' 부분만 달라집니다.")

                st.markdown("---")
                st.markdown("#### 프롬프트 수정 (일괄 적용)")

                # 수정 모드 선택
                prompt_edit_mode = st.radio(
                    "수정 범위",
                    ["기본 프롬프트 사용", "스타일 일괄 변경"],
                    horizontal=True,
                    key="batch_prompt_edit_mode"
                )

                if prompt_edit_mode == "스타일 일괄 변경":
                    col_pe1, col_pe2 = st.columns(2)

                    with col_pe1:
                        if "배경만" in style_mode:
                            default_prefix = next((s.prompt_prefix for s in get_styles_by_segment("background") if s.id == style), "") if style else ""
                        else:
                            default_prefix = composite_style.prompt_prefix if composite_style else ""

                        edited_prefix = st.text_area(
                            "스타일 Prefix (모든 씬 적용)",
                            value=default_prefix,
                            height=80,
                            key="batch_edited_prefix"
                        )

                    with col_pe2:
                        if "배경만" in style_mode:
                            default_suffix = next((s.prompt_suffix for s in get_styles_by_segment("background") if s.id == style), "") if style else ""
                        else:
                            default_suffix = composite_style.prompt_suffix if composite_style else ""

                        edited_suffix = st.text_area(
                            "스타일 Suffix (모든 씬 적용)",
                            value=default_suffix,
                            height=80,
                            key="batch_edited_suffix"
                        )

                    edited_negative = st.text_input(
                        "네거티브 프롬프트 (모든 씬 적용)",
                        value=build_result.final_negative,
                        key="batch_edited_negative"
                    )

                    # 예시 최종 프롬프트 표시
                    example_final = ", ".join(filter(None, [edited_prefix.strip(), scene_prompt, edited_suffix.strip()]))
                    st.markdown(f"**예시 최종 프롬프트 (씬 {first_scene_id}):**")
                    st.code(example_final[:500] + "..." if len(example_final) > 500 else example_final, language=None)

                    # 프롬프트 통계
                    col_s1, col_s2, col_s3 = st.columns(3)
                    with col_s1:
                        st.metric("문자 수", f"{len(example_final):,}")
                    with col_s2:
                        st.metric("단어 수", f"{len(example_final.split()):,}")
                    with col_s3:
                        approx_tokens = len(example_final) // 4
                        token_status = "적정" if approx_tokens < 200 else "주의" if approx_tokens < 300 else "초과"
                        st.metric("예상 토큰", f"~{approx_tokens} ({token_status})")

                    st.session_state["batch_prompt_edits"] = {
                        "mode": "style",
                        "prefix": edited_prefix.strip(),
                        "suffix": edited_suffix.strip(),
                        "negative": edited_negative.strip()
                    }
                else:
                    st.session_state["batch_prompt_edits"] = {"mode": "default"}

    st.markdown("---")

    # ============================================================
    # 🔍 선택된 씬 프롬프트 미리보기 (v2.0)
    # ============================================================
    if selected_scenes and scenes:
        with st.expander("🔍 선택된 씬별 최종 프롬프트 미리보기", expanded=False):
            # 스타일 정보 가져오기
            batch_edits = st.session_state.get("batch_prompt_edits", {"mode": "default"})

            if batch_edits.get("mode") == "style":
                preview_prefix = batch_edits.get("prefix", "")
                preview_suffix = batch_edits.get("suffix", "")
                preview_negative = batch_edits.get("negative", "")
                preview_style_name = "사용자 수정"
            elif "배경만" in style_mode:
                selected_bg_style = next((s for s in get_styles_by_segment("background") if s.id == style), None) if style else None
                preview_prefix = selected_bg_style.prompt_prefix if selected_bg_style else ""
                preview_suffix = selected_bg_style.prompt_suffix if selected_bg_style else ""
                preview_negative = selected_bg_style.negative_prompt if selected_bg_style else ""
                preview_style_name = selected_bg_style.name_ko if selected_bg_style else "기본"
            else:
                preview_prefix = composite_style.prompt_prefix if composite_style else ""
                preview_suffix = composite_style.prompt_suffix if composite_style else ""
                preview_negative = composite_style.negative_prompt if (composite_style and apply_negative) else ""
                preview_style_name = composite_style.name_ko if composite_style else "기본"

            # 프롬프트 미리보기 생성
            scene_previews = build_scene_previews(
                scenes=scenes,
                selected_scene_ids=selected_scenes,
                style_prefix=preview_prefix,
                style_suffix=preview_suffix,
                negative_prompt=preview_negative,
                style_name=preview_style_name,
                prompt_key="image_prompt_en"
            )

            # 미리보기 UI 렌더링
            render_multi_scene_prompt_preview(
                scene_previews=scene_previews,
                max_display=5,
                key_prefix="batch_preview"
            )

    st.markdown("---")

    # 생성 버튼
    if st.button(
        f"씬 일괄 생성 ({len(selected_scenes)}개)",
        type="primary",
        use_container_width=True,
        disabled=len(selected_scenes) == 0
    ):
        # v2.0: 배치 시작 전 메모리 최적화
        optimize_memory_for_batch()

        progress = st.progress(0)
        status = st.empty()

        success_count = 0
        error_count = 0
        first_image_processed = False  # 첫 이미지 처리 여부 (시드 잠금용)
        batch_start_time = time.time()  # v3.0: 배치 시작 시간 기록
        batch_results = []  # v3.1: 상세 결과 저장용 리스트

        # ============================================================
        # v3.0: ImageFX 병렬 배치 생성 (4배 속도 향상)
        # ============================================================
        batch_api = st.session_state.get("_batch_gen_api")
        batch_model = st.session_state.get("_batch_gen_model")
        use_parallel_imagefx = (
            batch_api == "Google ImageFX" and
            len(selected_scenes) > 1 and
            "배경만" in style_mode and
            generate_background
        )

        if use_parallel_imagefx:
            # ========== ImageFX 병렬 배치 생성 모드 ==========
            status.text("🚀 ImageFX 병렬 배치 생성 준비 중...")
            print(f"\n[일괄생성 v3.0] ========== ImageFX 병렬 배치 시작 ==========")
            print(f"[일괄생성 v3.0] 씬 수: {len(selected_scenes)}개, 워커: 4개 병렬")

            from utils.style_manager import get_style_by_id, get_styles_by_segment
            from config.settings import load_imagefx_cookie

            # 쿠키 로드
            imagefx_cookie = st.session_state.get("imagefx_cookie", "") or load_imagefx_cookie()
            if not imagefx_cookie:
                st.error("❌ ImageFX 쿠키가 설정되지 않았습니다.")
            else:
                # 스타일 로드 (한 번만)
                style_obj = None
                bg_styles = get_styles_by_segment("background")
                for s in bg_styles:
                    if s.id == style or s.name_ko == style or s.name == style:
                        style_obj = s
                        break
                if not style_obj:
                    style_obj = get_style_by_id(style)

                style_prefix = style_obj.prompt_prefix.strip() if style_obj and style_obj.prompt_prefix else ""
                style_suffix = style_obj.prompt_suffix.strip() if style_obj and style_obj.prompt_suffix else ""
                negative_prompt_base = style_obj.negative_prompt.strip() if style_obj and style_obj.negative_prompt else ""

                print(f"[일괄생성 v3.0] 스타일: {style_obj.name_ko if style_obj else '기본'}")

                # 배치 요청 수집
                batch_requests = []
                scene_map = {}  # scene_id -> scene 매핑
                batch_edits = st.session_state.get("batch_prompt_edits", {"mode": "default"})
                current_seed = get_seed_for_generation(key_prefix="batch_seed")

                # v3.1: get_current_project()는 Path 객체를 반환함 (dict가 아님!)
                current_project = get_current_project()
                if current_project is None:
                    st.error("❌ 프로젝트가 선택되지 않았습니다.")
                    st.stop()
                project_path = Path(current_project) if not isinstance(current_project, Path) else current_project
                bg_dir = project_path / "images" / "backgrounds"
                bg_dir.mkdir(parents=True, exist_ok=True)

                for scene_id in selected_scenes:
                    scene = get_scene_by_id(scene_id)
                    if not scene:
                        continue

                    prompts_data = scene.get("prompts", {})
                    prompt = (
                        scene.get("image_prompt_en", "") or
                        prompts_data.get("image_prompt_en", "") or
                        scene.get("image_prompt_ko", "") or
                        scene.get("background_prompt", "") or
                        scene.get("description", "")
                    )

                    if not prompt:
                        continue

                    # 프롬프트 조합
                    if batch_edits.get("mode") == "style":
                        edited_prefix = batch_edits.get("prefix", "")
                        edited_suffix = batch_edits.get("suffix", "")
                        edited_negative = batch_edits.get("negative", "")
                        scene_prompt = f"{prompt.strip()}, background scene, no characters, wide shot"
                        full_prompt = ", ".join(filter(None, [edited_prefix, scene_prompt, edited_suffix]))
                        final_negative = edited_negative
                    else:
                        scene_prompt = f"{prompt.strip()}, background scene, no characters, wide shot"
                        parts = []
                        if style_prefix:
                            parts.append(style_prefix.rstrip(",").strip())
                        parts.append(scene_prompt)
                        if style_suffix:
                            parts.append(style_suffix.lstrip(",").strip())
                        full_prompt = ", ".join(filter(None, parts))
                        final_negative = negative_prompt_base

                    # 출력 경로
                    timestamp = int(time.time() * 1000) + scene_id  # 유니크 타임스탬프
                    output_path = str(bg_dir / f"bg_scene_{scene_id:03d}_{timestamp}.png")

                    batch_requests.append({
                        "scene_id": scene_id,
                        "prompt": full_prompt,
                        "negative_prompt": final_negative,
                        "output_path": output_path,
                        "model": batch_model or "IMAGEN_4",
                        "aspect_ratio": "LANDSCAPE",
                        "seed": current_seed
                    })
                    scene_map[scene_id] = {
                        "scene": scene,
                        "original_prompt": prompt,
                        "full_prompt": full_prompt,
                        "negative_prompt": final_negative,
                        "style_prefix": style_prefix if batch_edits.get("mode") != "style" else batch_edits.get("prefix", ""),
                        "style_suffix": style_suffix if batch_edits.get("mode") != "style" else batch_edits.get("suffix", "")
                    }

                print(f"[일괄생성 v3.0] 배치 요청 수집 완료: {len(batch_requests)}개")

                if batch_requests:
                    # ImageFX 배치 생성기로 병렬 생성
                    batch_generator = ImageFXBatchGenerator(
                        max_workers=4,
                        cookie=imagefx_cookie,
                        api_delay=0.5
                    )

                    def update_progress(completed, total):
                        progress.progress(completed / total * 0.8)  # 80%까지 생성, 나머지 20%는 후처리
                        status.text(f"🖼️ 이미지 생성 중... ({completed}/{total})")

                    try:
                        results = batch_generator.generate_batch(
                            requests=batch_requests,
                            progress_callback=update_progress
                        )

                        # 결과 처리
                        status.text("📝 결과 저장 및 후처리 중...")
                        progress.progress(0.85)

                        for result in results:
                            scene_id = result.get("scene_id")
                            if scene_id not in scene_map:
                                continue

                            scene_info = scene_map[scene_id]

                            if result.get("success"):
                                filepath = result.get("path")
                                used_seed = result.get("seed")
                                model_name = f"Imagen {(batch_model or 'IMAGEN_4').replace('IMAGEN_', '').replace('_', '.')}"

                                # 메타데이터 저장
                                save_image_with_prompt(
                                    image_path=filepath,
                                    original_prompt=scene_info["original_prompt"],
                                    final_prompt=scene_info["full_prompt"],
                                    negative_prompt=scene_info["negative_prompt"],
                                    style_id=style_obj.id if style_obj else "",
                                    style_name=style_obj.name_ko if style_obj else style,
                                    style_prefix=scene_info["style_prefix"],
                                    style_suffix=scene_info["style_suffix"],
                                    api_provider="Google ImageFX",
                                    model=batch_model or "IMAGEN_4",
                                    model_name=model_name,
                                    width=1280,
                                    height=720,
                                    scene_id=scene_id,
                                    extra_info={"seed": used_seed} if used_seed else None
                                )

                                # 씬 데이터 업데이트
                                set_background_for_scene(scene_id, filepath)
                                update_scene_background(scene_id, filepath, str(project_path))

                                # 시드 잠금 업데이트 (첫 이미지만)
                                if used_seed and not first_image_processed:
                                    from utils.imagefx_ui_components import update_locked_seed_from_result
                                    update_locked_seed_from_result(used_seed, key_prefix="batch_seed")
                                    first_image_processed = True

                                success_count += 1
                                print(f"[일괄생성 v3.0] ✅ 씬 {scene_id} 저장 완료")

                                # v3.1: 상세 결과 저장
                                batch_results.append({
                                    "success": True,
                                    "scene_id": scene_id,
                                    "path": filepath,
                                    "seed": used_seed,
                                    "original_prompt": scene_info["original_prompt"],
                                    "final_prompt": scene_info["full_prompt"],
                                    "negative_prompt": scene_info["negative_prompt"],
                                    "style_id": style_obj.id if style_obj else "",
                                    "style_name": style_obj.name_ko if style_obj else style,
                                    "style_prefix": scene_info["style_prefix"],
                                    "style_suffix": scene_info["style_suffix"],
                                    "api_name": "Google ImageFX",
                                    "model": batch_model or "IMAGEN_4",
                                    "model_name": model_name,
                                    "cost": "무료"
                                })

                                # 합성 처리
                                if generate_composite:
                                    scene = scene_info["scene"]
                                    if character_composite_mode == "scene_character":
                                        execute_composite(scene_id, scene, remove_bg, batch_use_scene_pose)
                                    elif character_composite_mode == "representative_character":
                                        execute_representative_character_composite(scene_id, scene, remove_bg)
                            else:
                                error_msg = result.get("error", "알 수 없는 오류")
                                st.error(f"씬 {scene_id} 생성 실패: {error_msg}")
                                error_count += 1
                                # v3.1: 실패 결과도 저장
                                batch_results.append({
                                    "success": False,
                                    "scene_id": scene_id,
                                    "error": error_msg
                                })

                    except Exception as e:
                        st.error(f"배치 생성 오류: {e}")
                        import traceback
                        print(f"[일괄생성 v3.0] 오류: {traceback.format_exc()}")
                    finally:
                        batch_generator.cleanup()

                # 소요 시간 계산
                batch_elapsed = time.time() - batch_start_time
                print(f"[일괄생성 v3.0] ========== 배치 완료 ==========")
                print(f"[일괄생성 v3.0] ⏱️ 총 소요 시간: {batch_elapsed:.1f}초")
                if success_count > 0:
                    print(f"[일괄생성 v3.0] 📊 이미지당 평균: {batch_elapsed/success_count:.1f}초")

        else:
            # ========== 기존 순차 처리 모드 (다른 API 또는 씬합성 모드) ==========
            for i, scene_id in enumerate(selected_scenes):
                status.text(f"씬 {scene_id} 처리 중... ({i+1}/{len(selected_scenes)})")
                progress.progress((i + 1) / len(selected_scenes))

                scene = get_scene_by_id(scene_id)
                if not scene:
                    error_count += 1
                    continue

                try:
                    # 프롬프트 가져오기 (공통)
                    prompts_data = scene.get("prompts", {})
                    prompt = (
                        scene.get("image_prompt_en", "") or
                        prompts_data.get("image_prompt_en", "") or
                        scene.get("image_prompt_ko", "") or
                        scene.get("background_prompt", "") or
                        scene.get("description", "")
                    )

                    if not prompt:
                        st.warning(f"⚠️ 씬 {scene_id}: 이미지 프롬프트가 없습니다.")
                        continue

                    # 수정된 프롬프트 적용
                    batch_edits = st.session_state.get("batch_prompt_edits", {"mode": "default"})

                    if batch_edits.get("mode") == "style":
                        # 스타일 일괄 변경 모드
                        edited_prefix = batch_edits.get("prefix", "")
                        edited_suffix = batch_edits.get("suffix", "")
                        edited_negative = batch_edits.get("negative", "")

                        # 최종 프롬프트 조합
                        final_prompt = ", ".join(filter(None, [edited_prefix, prompt, edited_suffix]))
                        use_edited_style = True
                    else:
                        final_prompt = prompt  # 기본 스타일 사용
                        edited_negative = None
                        use_edited_style = False

                    # ======== 모드별 분기 처리 ========
                    # v6.3: 시드 잠금 기능 - 현재 시드 가져오기
                    current_seed = get_seed_for_generation(key_prefix="batch_seed")
                    if current_seed:
                        print(f"[일괄생성] 시드 잠금 활성화: {current_seed}", flush=True)

                    if "배경만" in style_mode:
                        # 배경만 생성 모드 (기존 로직)
                        if generate_background:
                            if use_edited_style:
                                # 수정된 프롬프트로 직접 생성
                                print(f"[일괄생성-배경(수정)] 씬 {scene_id}: {final_prompt[:100]}...")
                                generate_background_image_with_prompt(
                                    scene_id, final_prompt, edited_negative, 1280, 720,
                                    api_provider=batch_api, model=batch_model,
                                    seed=current_seed,  # ⭐ 시드 전달
                                    seed_key_prefix="batch_seed"  # v6.5: 시드 자동 잠금
                                )
                            else:
                                print(f"[일괄생성-배경] 씬 {scene_id}: {prompt[:100]}...")
                                generate_background_image(
                                    scene_id, prompt, style, 1280, 720,
                                    api_provider=batch_api, model=batch_model,
                                    seed=current_seed,  # ⭐ 시드 전달
                                    seed_key_prefix="batch_seed"  # v6.5: 시드 자동 잠금
                                )
                            time.sleep(1)  # API 속도 제한

                        # 합성 (모드에 따라 분기)
                        if generate_composite:
                            if character_composite_mode == "scene_character":
                                # 씬별 캐릭터 합성 (기존 로직)
                                execute_composite(scene_id, scene, remove_bg, batch_use_scene_pose)
                            elif character_composite_mode == "representative_character":
                                # 대표 캐릭터 합성 (NEW!)
                                execute_representative_character_composite(scene_id, scene, remove_bg)

                    else:
                        # 씬 합성 생성 모드 (NEW!)
                        if composite_style:
                            if use_edited_style:
                                # 수정된 프롬프트로 직접 생성
                                print(f"[일괄생성-씬합성(수정)] 씬 {scene_id}: {final_prompt[:100]}...")
                                generate_scene_composite_image_with_prompt(
                                    scene_id=scene_id,
                                    final_prompt=final_prompt,
                                    negative_prompt=edited_negative,
                                    width=1280,
                                    height=720,
                                    seed=current_seed,  # ⭐ 시드 전달
                                    seed_key_prefix="batch_seed"  # v6.5: 시드 자동 잠금
                                )
                            else:
                                print(f"[일괄생성-씬합성] 씬 {scene_id}: {prompt[:100]}...")
                                generate_scene_composite_image(
                                    scene_id=scene_id,
                                    scene_prompt=prompt,
                                    composite_style=composite_style,
                                    apply_negative=apply_negative,
                                    width=1280,
                                    height=720,
                                    seed=current_seed,  # ⭐ 시드 전달
                                    seed_key_prefix="batch_seed"  # v6.5: 시드 자동 잠금
                                )
                            time.sleep(1)  # API 속도 제한
                        else:
                            st.warning(f"⚠️ 씬 {scene_id}: 씬 합성 스타일이 선택되지 않았습니다.")
                            continue

                    success_count += 1

                except Exception as e:
                    st.error(f"씬 {scene_id} 처리 실패: {e}")
                    error_count += 1

                # 메모리 정리 (Out of Memory 방지)
                gc.collect()

        progress.progress(1.0)
        status.empty()

        # v2.0: 배치 완료 후 메모리 정리
        cleanup_after_batch()

        # ============================================================
        # 📊 생성 결과 요약 (v3.1: 상세 결과 UI 복원)
        # ============================================================
        batch_elapsed = time.time() - batch_start_time
        st.markdown("## 📊 생성 결과")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("✅ 성공", f"{success_count}개")
        with col2:
            st.metric("❌ 실패", f"{error_count}개")
        with col3:
            st.metric("📋 총 처리", f"{len(selected_scenes)}개")
        with col4:
            st.metric("⏱️ 소요 시간", f"{batch_elapsed:.1f}초")

        if success_count > 0:
            st.success(f"✅ {success_count}개 씬 처리 완료!")

            # v3.1: 각 씬별 상세 결과 표시
            if batch_results:
                st.markdown("### 🎬 씬별 상세 결과")

                for i, result in enumerate(batch_results):
                    scene_id = result.get("scene_id", "?")

                    if result.get("success"):
                        # 성공한 씬 상세 정보
                        filepath = result.get("path", "")
                        prompt_length = len(result.get("final_prompt", ""))

                        with st.expander(f"🎬 씬 {scene_id} 프롬프트 ({prompt_length}자)", expanded=(i == 0)):
                            # 생성된 이미지 미리보기
                            if filepath and os.path.exists(filepath):
                                st.image(filepath, caption=f"씬 {scene_id} 생성 이미지", use_container_width=True)

                            # 프롬프트 상세 정보
                            with st.expander("🎨 생성에 사용된 프롬프트", expanded=True):
                                # API/모델/비용 정보
                                api_col1, api_col2, api_col3 = st.columns(3)
                                with api_col1:
                                    st.markdown(f"**API**\n\n{result.get('api_name', 'Google ImageFX')}")
                                with api_col2:
                                    st.markdown(f"**모델**\n\n{result.get('model_name', 'Imagen 4')}")
                                with api_col3:
                                    st.markdown(f"**예상 비용**\n\n{result.get('cost', '무료')}")

                                st.divider()

                                # 원본 프롬프트 (씬 분석)
                                original_prompt = result.get("original_prompt", "")
                                if original_prompt:
                                    st.markdown("**원본 (씬 분석):**")
                                    st.code(original_prompt, language=None)

                                # 스타일 정보
                                style_name = result.get("style_name", "")
                                style_id = result.get("style_id", "")
                                if style_name:
                                    st.markdown(f"**스타일:** {style_name}")
                                if style_id:
                                    st.caption(f"스타일ID: {style_id}")

                                # 스타일 Prefix
                                style_prefix = result.get("style_prefix", "")
                                if style_prefix:
                                    st.markdown("**스타일 Prefix:**")
                                    st.code(style_prefix, language=None)

                                # 스타일 Suffix
                                style_suffix = result.get("style_suffix", "")
                                if style_suffix:
                                    st.markdown("**스타일 Suffix:**")
                                    st.code(style_suffix, language=None)

                                # 최종 프롬프트
                                final_prompt = result.get("final_prompt", "")
                                if final_prompt:
                                    st.markdown("**최종 프롬프트:**")
                                    st.code(final_prompt, language=None)

                                # 네거티브 프롬프트
                                negative_prompt = result.get("negative_prompt", "")
                                if negative_prompt:
                                    st.markdown("**네거티브 프롬프트:**")
                                    st.code(negative_prompt, language=None)

                            # 시드 정보
                            used_seed = result.get("seed")
                            if used_seed:
                                seed_col1, seed_col2 = st.columns([3, 1])
                                with seed_col1:
                                    st.info(f"🔑 **시드:** `{used_seed:,}`")
                                with seed_col2:
                                    import streamlit.components.v1 as components
                                    seed_copy_html = f"""
                                    <button onclick="navigator.clipboard.writeText('{used_seed}').then(function(){{
                                        this.innerHTML='✅ 복사됨!';
                                        setTimeout(function(){{document.getElementById('seed_copy_btn_{scene_id}').innerHTML='📋 시드 복사';}}, 1500);
                                    }}.bind(this))" id="seed_copy_btn_{scene_id}" style="
                                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                        color: white; border: none; border-radius: 6px;
                                        padding: 8px 16px; cursor: pointer; font-size: 13px;
                                    ">📋 시드 복사</button>
                                    """
                                    components.html(seed_copy_html, height=45)

                            # 저장 경로
                            if filepath:
                                st.success(f"배경 생성 완료: {os.path.basename(filepath)}")

                    else:
                        # 실패한 씬
                        error_msg = result.get("error", "알 수 없는 오류")
                        with st.expander(f"❌ 씬 {scene_id} 생성 실패", expanded=False):
                            st.error(f"오류: {error_msg}")

            else:
                # batch_results가 없는 경우 (순차 처리 모드)
                st.info("""
💡 **생성된 이미지의 프롬프트 확인 방법:**
- 갤러리 탭에서 이미지를 클릭하면 프롬프트 상세 정보를 볼 수 있습니다.
- 각 이미지와 함께 `.json` 메타데이터 파일이 저장되어 있습니다.
                """)

                # 처리된 씬 목록
                with st.expander("📋 처리된 씬 목록", expanded=False):
                    processed_ids = ", ".join(map(str, selected_scenes[:50]))
                    if len(selected_scenes) > 50:
                        processed_ids += f"... 외 {len(selected_scenes) - 50}개"
                    st.write(f"**처리된 씬 ID:** {processed_ids}")

        if error_count > 0:
            st.warning(f"⚠️ {error_count}개 씬 처리 실패 - 위의 오류 메시지를 확인하세요.")


# ===================================================================
# 일괄 합성 UI 헬퍼 함수들
# ===================================================================

def _render_external_upload_section():
    """외부 캐릭터/배경 업로드 섹션"""
    st.markdown("#### 🧑‍🎨 외부 캐릭터 업로드")
    st.caption("프로젝트 캐릭터 외에 외부 이미지를 임시 캐릭터로 사용할 수 있습니다.")

    # 외부 캐릭터 초기화
    if "external_characters" not in st.session_state:
        st.session_state["external_characters"] = []

    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_char = st.file_uploader(
            "캐릭터 이미지 업로드",
            type=["png", "jpg", "jpeg", "webp"],
            key="upload_external_char",
            help="투명 배경(PNG)을 권장합니다."
        )

    with col2:
        char_name = st.text_input(
            "캐릭터 이름",
            placeholder="예: 외부캐릭터1",
            key="external_char_name"
        )

    if uploaded_char and char_name:
        if st.button("➕ 캐릭터 추가", key="add_external_char"):
            # 업로드된 파일 저장
            from PIL import Image
            import io

            upload_dir = project_path / "images" / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)

            # 파일 저장
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ext_char_{timestamp}_{char_name}.png"
            save_path = upload_dir / filename

            img = Image.open(uploaded_char)
            img.save(str(save_path), "PNG")

            # 외부 캐릭터 목록에 추가
            ext_char = {
                "id": f"ext_{timestamp}",
                "name": char_name,
                "image_path": str(save_path),
                "is_external": True
            }
            st.session_state["external_characters"].append(ext_char)
            st.success(f"✅ '{char_name}' 캐릭터가 추가되었습니다.")
            st.rerun()

    # 현재 외부 캐릭터 목록
    ext_chars = st.session_state.get("external_characters", [])
    if ext_chars:
        st.markdown("**등록된 외부 캐릭터:**")
        cols = st.columns(min(4, len(ext_chars)))
        for i, char in enumerate(ext_chars):
            with cols[i % 4]:
                if os.path.exists(char.get("image_path", "")):
                    clickable_image(char["image_path"], width=80, key=f"ext_char_{char.get('id', i)}")
                st.caption(char["name"])
                if st.button("❌", key=f"del_ext_{char['id']}"):
                    st.session_state["external_characters"].remove(char)
                    st.rerun()

    st.markdown("---")
    st.markdown("#### 🖼️ 씬별 배경 교체")
    st.caption("특정 씬의 배경을 외부 이미지로 교체할 수 있습니다.")

    scenes = get_scenes()
    if scenes:
        col1, col2 = st.columns([1, 2])

        with col1:
            scene_options = [f"씬 {s.get('scene_id')}" for s in scenes]
            selected_scene = st.selectbox(
                "대상 씬",
                options=scene_options,
                key="bg_replace_scene"
            )

        with col2:
            uploaded_bg = st.file_uploader(
                "배경 이미지",
                type=["png", "jpg", "jpeg", "webp"],
                key="upload_external_bg"
            )

        if uploaded_bg and selected_scene:
            if st.button("🔄 배경 교체", key="replace_bg_btn"):
                scene_id = int(selected_scene.replace("씬 ", ""))

                # 배경 저장
                from PIL import Image

                bg_dir = project_path / "images" / "backgrounds"
                bg_dir.mkdir(parents=True, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"bg_scene{scene_id}_{timestamp}.png"
                save_path = bg_dir / filename

                img = Image.open(uploaded_bg)
                img.save(str(save_path), "PNG")

                # 배경 데이터 업데이트
                bg_data = st.session_state.get("background_images", {})
                bg_data[str(scene_id)] = {
                    "path": str(save_path),
                    "prompt": f"외부 업로드 배경 ({timestamp})",
                    "uploaded": True
                }
                st.session_state["background_images"] = bg_data

                # JSON 저장
                bg_json = project_path / "images" / "backgrounds" / "backgrounds.json"
                with open(bg_json, "w", encoding="utf-8") as f:
                    json.dump(bg_data, f, ensure_ascii=False, indent=2)

                st.success(f"✅ 씬 {scene_id}의 배경이 교체되었습니다.")
                st.rerun()


def _render_scene_preview_cards(scenes: List[Dict], all_characters: List[Dict]) -> List[int]:
    """씬별 프리뷰 카드 렌더링"""
    selected_scene_ids = []

    # 외부 캐릭터 포함
    ext_chars = st.session_state.get("external_characters", [])
    all_chars_combined = all_characters + ext_chars

    # 2열 그리드
    cols_per_row = 2
    for row_start in range(0, len(scenes), cols_per_row):
        cols = st.columns(cols_per_row)

        for col_idx, scene in enumerate(scenes[row_start:row_start + cols_per_row]):
            scene_id = scene.get("scene_id")
            scene_idx = row_start + col_idx  # 고유 인덱스
            scene_chars = scene.get("characters", [])
            has_composite = get_composited_for_scene(scene_id) is not None

            with cols[col_idx]:
                # 카드 컨테이너
                with st.container():
                    # 헤더: 선택 체크박스 + 씬 제목
                    header_col1, header_col2 = st.columns([1, 5])
                    with header_col1:
                        is_selected = st.checkbox(
                            "선택",
                            value=st.session_state.get(f"comp_select_{scene_id}", False),
                            key=f"preview_cb_{scene_id}_idx{scene_idx}",
                            label_visibility="collapsed"
                        )
                        if is_selected:
                            selected_scene_ids.append(scene_id)

                    with header_col2:
                        status_icon = "✅" if has_composite else "⬜"
                        st.markdown(f"**{status_icon} 씬 {scene_id}**")

                    # 배경 프리뷰 (클릭 시 확대)
                    bg_data = get_background_for_scene(scene_id)
                    if bg_data:
                        bg_path = bg_data.get("path") or bg_data.get("url")
                        if bg_path and os.path.exists(bg_path):
                            render_lightbox_image(bg_path, key=f"batch_bg_{scene_id}_idx{scene_idx}")
                        else:
                            st.info("🖼️ 배경 파일 없음")
                    else:
                        st.info("🖼️ 배경 없음")

                    # 캐릭터 썸네일
                    st.markdown("**캐릭터:**")

                    # 씬에 할당된 캐릭터 (커스텀 가능)
                    custom_chars_key = f"scene_chars_custom_{scene_id}"
                    if custom_chars_key not in st.session_state:
                        st.session_state[custom_chars_key] = extract_character_names(scene_chars)

                    current_chars = st.session_state[custom_chars_key]

                    if current_chars:
                        char_cols = st.columns(min(4, len(current_chars) + 1))
                        for i, char_name in enumerate(current_chars):
                            char_info = next(
                                (c for c in all_chars_combined if c.get("name") == char_name),
                                None
                            )
                            with char_cols[i % 4]:
                                if char_info:
                                    char_img = char_info.get("image_path") or char_info.get("image_url")
                                    if char_img and os.path.exists(char_img):
                                        clickable_image(char_img, width=60, key=f"batch_char_{scene_id}_{char_name}_idx{scene_idx}")
                                    else:
                                        st.markdown("👤")
                                    st.caption(char_name[:8])

                                    # 제거 버튼
                                    if st.button("❌", key=f"rm_char_{scene_id}_{char_name}_idx{scene_idx}"):
                                        st.session_state[custom_chars_key].remove(char_name)
                                        st.rerun()
                                else:
                                    st.markdown(f"❓ {char_name}")
                    else:
                        st.caption("캐릭터 없음")

                    # 캐릭터 추가 드롭다운
                    available_chars = [
                        c.get("name") for c in all_chars_combined
                        if c.get("name") not in current_chars
                    ]
                    if available_chars:
                        with st.expander("➕ 캐릭터 추가", expanded=False):
                            add_char = st.selectbox(
                                "추가할 캐릭터",
                                options=["선택..."] + available_chars,
                                key=f"add_char_select_{scene_id}_idx{scene_idx}"
                            )
                            if add_char != "선택..." and st.button("추가", key=f"add_char_btn_{scene_id}_idx{scene_idx}"):
                                st.session_state[custom_chars_key].append(add_char)
                                st.rerun()

                    st.markdown("---")

    return selected_scene_ids


def _render_scene_list_view(scenes: List[Dict], all_characters: List[Dict]) -> List[int]:
    """기존 리스트 뷰 렌더링 (리팩토링)"""
    selected_scene_ids = []
    ext_chars = st.session_state.get("external_characters", [])
    all_chars_combined = all_characters + ext_chars

    for scene_idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id")
        scene_chars = scene.get("characters", [])
        has_composite = get_composited_for_scene(scene_id) is not None

        col1, col2, col3 = st.columns([1, 4, 3])

        with col1:
            is_selected = st.checkbox(
                "선택",
                value=st.session_state.get(f"comp_select_{scene_id}", False),
                key=f"list_cb_{scene_id}_idx{scene_idx}",
                label_visibility="collapsed"
            )
            if is_selected:
                selected_scene_ids.append(scene_id)

        with col2:
            status_icon = "✅" if has_composite else "⬜"
            st.markdown(f"{status_icon} **씬 {scene_id}**")

            # 커스텀 캐릭터 목록
            custom_chars_key = f"scene_chars_custom_{scene_id}"
            if custom_chars_key not in st.session_state:
                st.session_state[custom_chars_key] = extract_character_names(scene_chars)

            current_chars = st.session_state[custom_chars_key]

            if current_chars:
                chars_with_img = []
                chars_without_img = []
                for char_name in current_chars:
                    char_info = next((c for c in all_chars_combined if c.get("name") == char_name), None)
                    if char_info:
                        char_img = char_info.get("image_path") or char_info.get("image_url")
                        if char_img and os.path.exists(char_img):
                            chars_with_img.append(char_name)
                        else:
                            chars_without_img.append(char_name)
                    else:
                        chars_without_img.append(char_name)

                if chars_with_img:
                    st.caption(f"👤 {', '.join(chars_with_img)}")
                if chars_without_img:
                    st.caption(f"⚠️ 이미지 없음: {', '.join(chars_without_img)}")
            else:
                st.caption("👤 캐릭터 없음 (배경만 복사됨)")

        with col3:
            pos_data = st.session_state.get(f"char_positions_{scene_id}", {})
            if pos_data:
                st.success(f"📍 위치 설정됨 ({len(pos_data)}개)")
            else:
                if current_chars:
                    st.info("📍 기본 위치 사용")
                else:
                    st.caption("-")

    return selected_scene_ids


def _render_batch_composite_only(scenes: List[Dict]):
    """배경이 있는 씬만 일괄 합성 (강화된 UI)"""
    st.info("💡 이미 배경이 설정된 씬들의 캐릭터 합성만 일괄 실행합니다.")

    # 외부 업로드 섹션
    with st.expander("📤 외부 이미지 업로드", expanded=False):
        _render_external_upload_section()

    st.markdown("---")

    # 배경이 있는 씬만 필터링
    scenes_with_bg = []
    scenes_without_bg = []

    for scene in scenes:
        scene_id = scene.get("scene_id")
        bg_data = get_background_for_scene(scene_id)
        if bg_data:
            bg_path = bg_data.get("path") or bg_data.get("url")
            if bg_path and os.path.exists(bg_path):
                scenes_with_bg.append(scene)
            else:
                scenes_without_bg.append(scene)
        else:
            scenes_without_bg.append(scene)

    if not scenes_with_bg:
        st.warning("⚠️ 배경이 설정된 씬이 없습니다. 먼저 '씬별 생성' 탭에서 배경을 생성하세요.")
        return

    st.success(f"✅ 배경이 설정된 씬: {len(scenes_with_bg)}개")
    if scenes_without_bg:
        st.caption(f"⚠️ 배경 없는 씬 {len(scenes_without_bg)}개는 제외됩니다: {[s.get('scene_id') for s in scenes_without_bg]}")

    st.markdown("---")

    # 표시 모드 선택
    view_mode = st.radio(
        "표시 모드",
        options=["📋 리스트", "🖼️ 프리뷰 카드"],
        horizontal=True,
        key="comp_view_mode"
    )

    # 씬 선택 버튼
    st.markdown("### 합성할 씬 선택")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✅ 전체 선택", key="comp_select_all"):
            for scene in scenes_with_bg:
                st.session_state[f"comp_select_{scene.get('scene_id')}"] = True
            st.rerun()
    with col2:
        if st.button("❌ 전체 해제", key="comp_deselect_all"):
            for scene in scenes_with_bg:
                st.session_state[f"comp_select_{scene.get('scene_id')}"] = False
            st.rerun()
    with col3:
        if st.button("🔄 미합성만 선택", key="comp_select_uncomposited"):
            for scene in scenes_with_bg:
                scene_id = scene.get("scene_id")
                has_composite = get_composited_for_scene(scene_id) is not None
                st.session_state[f"comp_select_{scene_id}"] = not has_composite
            st.rerun()

    # 씬 목록 렌더링
    selected_scene_ids = []
    all_characters = st.session_state.get("characters", [])

    if view_mode == "🖼️ 프리뷰 카드":
        # 프리뷰 카드 모드
        selected_scene_ids = _render_scene_preview_cards(scenes_with_bg, all_characters)
    else:
        # 기존 리스트 모드
        selected_scene_ids = _render_scene_list_view(scenes_with_bg, all_characters)

    st.markdown("---")
    st.markdown(f"**선택된 씬:** {len(selected_scene_ids)}개")

    # 합성 옵션
    st.markdown("### 합성 옵션")

    col1, col2, col3 = st.columns(3)

    with col1:
        remove_bg = st.checkbox(
            "캐릭터 배경 제거",
            value=True,
            key="comp_only_remove_bg",
            help="캐릭터 이미지의 배경을 투명하게 만듭니다."
        )

    with col2:
        overwrite_existing = st.checkbox(
            "기존 합성 덮어쓰기",
            value=False,
            key="comp_overwrite",
            help="이미 합성된 씬도 다시 합성합니다."
        )

    with col3:
        use_default_positions = st.checkbox(
            "미설정 씬은 기본 위치 사용",
            value=True,
            key="comp_use_default",
            help="위치가 설정되지 않은 씬은 캐릭터를 기본 위치에 배치합니다."
        )

    # 씬별 포즈 옵션
    all_characters = st.session_state.get("characters", [])
    any_has_scene_poses, _ = check_characters_have_scene_poses(all_characters)
    if any_has_scene_poses:
        comp_use_scene_pose = st.checkbox(
            "씬별 포즈 적용",
            value=True,
            key="comp_only_use_scene_pose",
            help="캐릭터 관리에서 설정한 씬별 포즈를 적용합니다."
        )
    else:
        comp_use_scene_pose = False

    st.markdown("---")

    # 일괄 합성 실행
    if st.button(
        f"🔄 {len(selected_scene_ids)}개 씬 일괄 합성",
        type="primary",
        use_container_width=True,
        disabled=len(selected_scene_ids) == 0
    ):
        # v2.0: 배치 시작 전 메모리 최적화
        optimize_memory_for_batch()

        progress = st.progress(0)
        status = st.empty()

        success_count = 0
        skip_count = 0
        error_count = 0
        results_log = []

        for i, scene_id in enumerate(selected_scene_ids):
            status.text(f"씬 {scene_id} 합성 중... ({i+1}/{len(selected_scene_ids)})")
            progress.progress((i + 1) / len(selected_scene_ids))

            scene = get_scene_by_id(scene_id)
            if not scene:
                error_count += 1
                results_log.append(f"❌ 씬 {scene_id}: 씬 정보 없음")
                continue

            # 이미 합성된 씬 건너뛰기 (옵션에 따라)
            if not overwrite_existing:
                existing = get_composited_for_scene(scene_id)
                if existing:
                    skip_count += 1
                    results_log.append(f"⏭️ 씬 {scene_id}: 이미 합성됨 (건너뜀)")
                    continue

            try:
                # 합성 실행
                result = execute_composite(scene_id, scene, remove_bg, comp_use_scene_pose)

                if result:
                    success_count += 1
                    results_log.append(f"✅ 씬 {scene_id}: 합성 완료")
                    st.session_state[f"composite_result_{scene_id}"] = result
                else:
                    error_count += 1
                    results_log.append(f"❌ 씬 {scene_id}: 합성 실패")

            except Exception as e:
                error_count += 1
                results_log.append(f"❌ 씬 {scene_id}: {str(e)[:50]}")

            # v2.0: 각 씬 처리 후 메모리 정리
            gc.collect()

        progress.progress(1.0)
        status.empty()

        # v2.0: 배치 완료 후 메모리 정리
        cleanup_after_batch()

        # 결과 요약
        st.markdown("### 📊 처리 결과")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("✅ 성공", f"{success_count}개")
        with col2:
            st.metric("⏭️ 건너뜀", f"{skip_count}개")
        with col3:
            st.metric("❌ 실패", f"{error_count}개")

        # 상세 로그
        with st.expander("📋 상세 로그", expanded=False):
            for log in results_log:
                st.text(log)

        if success_count > 0:
            st.success(f"✅ {success_count}개 씬 합성 완료!")
            st.balloons()


# ===================================================================
# 탭 3: 갤러리
# ===================================================================

def render_gallery_tab():
    """🖼️ 갤러리 탭"""
    st.markdown("## 🖼️ 이미지 갤러리")

    # ===== 프로젝트 경로 안전하게 가져오기 =====
    project_path = st.session_state.get("project_path", "")
    if not project_path:
        project_path = get_current_project()

    if not project_path:
        st.warning("⚠️ 프로젝트를 먼저 선택해주세요.")
        st.info("👈 좌측 사이드바에서 채널과 영상을 선택하세요.")
        return

    # Path 객체로 변환
    if isinstance(project_path, str):
        project_path = Path(project_path)

    # 필터
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        scenes = get_scenes()
        scene_options = ["전체"] + [f"씬 {s.get('scene_id')}" for s in scenes]
        filter_scene = st.selectbox("씬 필터", options=scene_options, key="gallery_filter_scene")

    with col2:
        filter_type = st.selectbox(
            "유형 필터",
            options=["전체", "합성", "배경", "씬"],
            key="gallery_filter_type"
        )

    with col3:
        sort_option = st.selectbox(
            "정렬",
            options=["최신순", "오래된순", "씬 번호순"],
            key="gallery_sort"
        )

    with col4:
        if st.button("🔄 새로고침", key="refresh_gallery"):
            st.session_state["gallery_page"] = 1  # v2.2: 페이지 리셋
            st.rerun()

    # v2.2: 필터 변경 감지 → 페이지 리셋
    current_filters = f"{filter_scene}_{filter_type}_{sort_option}"
    if st.session_state.get("_gallery_last_filters") != current_filters:
        st.session_state["_gallery_last_filters"] = current_filters
        st.session_state["gallery_page"] = 1

    # 이미지 목록 가져오기
    images = get_all_gallery_images()

    # ============================================================
    # 🆕 중복 분석 및 최신 이미지 추출
    # ============================================================
    from utils.image_gallery_manager import ImageGalleryManager

    gallery_manager = ImageGalleryManager(str(project_path))
    all_scanned = gallery_manager.scan_all_images()
    analysis = gallery_manager.analyze_duplicates(all_scanned)
    latest_images = gallery_manager.get_latest_images_list(all_scanned)

    # 중복 통계 표시
    if analysis["duplicates_count"] > 0:
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        with stat_col1:
            st.metric("총 이미지", f"{analysis['total_images']}개")
        with stat_col2:
            st.metric("씬 수", f"{analysis['total_scenes']}개")
        with stat_col3:
            st.metric("중복", f"{analysis['duplicates_count']}개", delta=f"-{analysis['savings_percent']:.0f}%", delta_color="inverse")
        with stat_col4:
            st.metric("절약 가능", f"{analysis['duplicates_size_mb']:.1f}MB")

    # 필터 적용
    if filter_scene != "전체":
        scene_num = filter_scene.replace("씬 ", "")
        images = [img for img in images if img.get("scene_id") == scene_num]

    if filter_type != "전체":
        type_map = {"합성": "composited", "배경": "background", "씬": "scene"}
        images = [img for img in images if img.get("type") == type_map.get(filter_type)]

    # 정렬
    if sort_option == "오래된순":
        images.sort(key=lambda x: x["created"])
    elif sort_option == "씬 번호순":
        images.sort(key=lambda x: int(x.get("scene_id", 0)) if x.get("scene_id", "?").isdigit() else 999)

    # ============================================================
    # 📥 프롬프트 선택적 다운로드 섹션 (v4.0 - 범위 선택 및 최신 메타데이터 지원)
    # ============================================================
    with st.expander("📥 프롬프트 다운로드", expanded=False):
        st.caption("씬별 이미지 프롬프트를 선택적으로 다운로드합니다.")

        scenes = get_scenes()
        if not scenes:
            st.warning("씬 데이터가 없습니다.")
        elif not PROMPT_DOWNLOAD_AVAILABLE:
            st.warning("프롬프트 다운로드 모듈을 불러올 수 없습니다.")
        else:
            try:
                import pandas as pd
                from io import BytesIO

                # 스타일 정보
                style_prefix = st.session_state.get("selected_style_prefix", "")
                style_suffix = st.session_state.get("selected_style_suffix", "")

                # 이미지 폴더 경로
                project_path = st.session_state.get("project_path", "")
                backgrounds_folder = Path(project_path) / "images" / "backgrounds" if project_path else None

                # 최신 이미지 정보 로드
                latest_images = {}
                scenes_with_images = set()
                if backgrounds_folder and backgrounds_folder.exists():
                    latest_images = get_latest_image_per_scene(backgrounds_folder)

                # ⭐ v4.1: 모든 이미지 폴더 스캔 (backgrounds, scenes, composited)
                if project_path:
                    from utils.prompt_download import get_all_scenes_with_images
                    scenes_with_images = get_all_scenes_with_images(Path(project_path))
                else:
                    scenes_with_images = set(latest_images.keys())

                # ========== 다운로드 범위 선택 ==========
                st.markdown("##### 📊 다운로드 범위 선택")

                download_mode = st.radio(
                    "범위 선택",
                    options=["전체", "범위 선택", "이미지 있는 씬만", "개별 선택"],
                    horizontal=True,
                    key="prompt_download_mode",
                    label_visibility="collapsed"
                )

                selected_scenes = []

                if download_mode == "전체":
                    selected_scenes = list(range(1, len(scenes) + 1))
                    st.caption(f"전체 {len(scenes)}개 씬 선택됨")

                elif download_mode == "범위 선택":
                    range_col1, range_col2 = st.columns(2)
                    with range_col1:
                        start_scene = st.number_input(
                            "시작 씬",
                            min_value=1,
                            max_value=len(scenes),
                            value=1,
                            key="prompt_start_scene"
                        )
                    with range_col2:
                        end_scene = st.number_input(
                            "종료 씬",
                            min_value=1,
                            max_value=len(scenes),
                            value=min(50, len(scenes)),
                            key="prompt_end_scene"
                        )
                    selected_scenes = list(range(int(start_scene), int(end_scene) + 1))
                    st.caption(f"씬 {int(start_scene)} ~ {int(end_scene)} ({len(selected_scenes)}개) 선택됨")

                elif download_mode == "이미지 있는 씬만":
                    selected_scenes = sorted(list(scenes_with_images))
                    if selected_scenes:
                        st.caption(f"이미지가 있는 {len(selected_scenes)}개 씬 선택됨")
                    else:
                        st.warning("이미지가 생성된 씬이 없습니다.")

                elif download_mode == "개별 선택":
                    # 세션 스테이트 초기화
                    if 'selected_scenes_for_download' not in st.session_state:
                        st.session_state['selected_scenes_for_download'] = set()

                    # 빠른 선택 버튼
                    quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
                    with quick_col1:
                        if st.button("처음 50개", key="quick_first_50", use_container_width=True):
                            st.session_state['selected_scenes_for_download'] = set(range(1, min(51, len(scenes) + 1)))
                            st.rerun()
                    with quick_col2:
                        if st.button("이미지 있는 씬", key="quick_with_image", use_container_width=True):
                            st.session_state['selected_scenes_for_download'] = scenes_with_images.copy()
                            st.rerun()
                    with quick_col3:
                        if st.button("전체 선택", key="quick_all", use_container_width=True):
                            st.session_state['selected_scenes_for_download'] = set(range(1, len(scenes) + 1))
                            st.rerun()
                    with quick_col4:
                        if st.button("선택 해제", key="quick_clear", use_container_width=True):
                            st.session_state['selected_scenes_for_download'] = set()
                            st.rerun()

                    # 페이지네이션
                    scenes_per_page = 20
                    total_pages = (len(scenes) + scenes_per_page - 1) // scenes_per_page

                    page_col1, page_col2 = st.columns([3, 1])
                    with page_col1:
                        page = st.selectbox(
                            "페이지",
                            options=list(range(1, total_pages + 1)),
                            format_func=lambda x: f"페이지 {x} (씬 {(x-1)*scenes_per_page + 1}-{min(x*scenes_per_page, len(scenes))})",
                            key="prompt_page_select",
                            label_visibility="collapsed"
                        )
                    with page_col2:
                        st.caption(f"선택: {len(st.session_state['selected_scenes_for_download'])}개")

                    start_idx = (page - 1) * scenes_per_page
                    end_idx = min(start_idx + scenes_per_page, len(scenes))

                    # 씬 체크박스 (컴팩트 레이아웃)
                    for i in range(start_idx, end_idx):
                        scene = scenes[i]
                        scene_num = scene.get("scene_id") or (i + 1)
                        narration = scene.get("narration", scene.get("script_text", ""))[:35]
                        has_image = scene_num in scenes_with_images
                        image_indicator = "🖼️" if has_image else "⬜"

                        is_selected = scene_num in st.session_state['selected_scenes_for_download']

                        if st.checkbox(
                            f"씬 {scene_num}: {narration}... {image_indicator}",
                            value=is_selected,
                            key=f"scene_select_{scene_num}"
                        ):
                            st.session_state['selected_scenes_for_download'].add(scene_num)
                        else:
                            st.session_state['selected_scenes_for_download'].discard(scene_num)

                    selected_scenes = sorted(list(st.session_state['selected_scenes_for_download']))

                # ========== 옵션 ==========
                st.markdown("---")
                use_latest_metadata = st.checkbox(
                    "☑️ 최신 이미지 프롬프트 사용",
                    value=True,
                    help="체크 시: 실제 이미지 생성에 사용된 프롬프트 (메타데이터)\n체크 해제 시: 씬 분석 원본 프롬프트",
                    key="use_latest_metadata"
                )

                # ========== 프롬프트 수집 및 통계 ==========
                if selected_scenes:
                    prompts = collect_prompts_for_selected_scenes(
                        selected_scene_nums=selected_scenes,
                        scenes=scenes,
                        latest_images=latest_images,
                        use_latest_metadata=use_latest_metadata,
                        style_prefix=style_prefix,
                        style_suffix=style_suffix
                    )
                    stats = get_prompt_stats(prompts)

                    # 통계 표시
                    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
                    with stat_col1:
                        st.metric("선택된 씬", f"{stats['total']}개")
                    with stat_col2:
                        st.metric("원본 프롬프트", f"{stats['with_original']}개")
                    with stat_col3:
                        st.metric("한글 프롬프트", f"{stats['with_korean']}개")
                    with stat_col4:
                        st.metric("메타데이터 출처", f"{stats['from_metadata']}개")

                    # ========== 다운로드 버튼 (v1.1 - session_state 캐싱) ==========
                    st.markdown("---")

                    # ⭐ 캐시 키 생성 (선택 범위 + 옵션 기반)
                    download_cache_key = f"prompt_dl_{min(selected_scenes)}_{max(selected_scenes)}_{len(selected_scenes)}_{use_latest_metadata}"

                    # 캐시된 데이터 확인
                    cached_download = st.session_state.get('_prompt_download_cache', {})
                    cached_key = cached_download.get('cache_key')
                    options_changed = cached_key != download_cache_key

                    # 버튼 레이아웃
                    gen_col, info_col = st.columns([1, 2])

                    with gen_col:
                        # 생성 버튼
                        generate_clicked = st.button(
                            "📦 다운로드 파일 생성" if options_changed or not cached_download.get('excel') else "🔄 다시 생성",
                            key=f"gen_prompt_dl_{download_cache_key}",
                            use_container_width=True,
                            type="primary" if options_changed or not cached_download.get('excel') else "secondary"
                        )

                    with info_col:
                        if cached_download.get('excel') and not options_changed:
                            st.success(f"✅ 준비됨: 엑셀 {cached_download.get('excel_size', 0):,} bytes")
                        elif options_changed and cached_key:
                            st.warning("⚠️ 옵션 변경됨 - 다시 생성 필요")
                        else:
                            st.info("ℹ️ '다운로드 파일 생성' 버튼을 클릭하세요")

                    # 생성 버튼 클릭 시 데이터 생성
                    if generate_clicked:
                        with st.spinner("다운로드 파일 생성 중..."):
                            try:
                                excel_bytes = generate_prompts_excel(prompts, include_source=True)
                                korean_zip = generate_prompts_zip(prompts, "korean")
                                final_zip = generate_prompts_zip(prompts, "final")

                                # 디버깅: 데이터 크기 확인
                                print(f"[프롬프트 다운로드] 엑셀: {len(excel_bytes) if excel_bytes else 0} bytes, 한글ZIP: {len(korean_zip) if korean_zip else 0} bytes, 최종ZIP: {len(final_zip) if final_zip else 0} bytes", flush=True)

                                # 세션 스테이트에 캐싱
                                st.session_state['_prompt_download_cache'] = {
                                    'cache_key': download_cache_key,
                                    'excel': excel_bytes,
                                    'excel_size': len(excel_bytes) if excel_bytes else 0,
                                    'korean_zip': korean_zip,
                                    'korean_zip_size': len(korean_zip) if korean_zip else 0,
                                    'final_zip': final_zip,
                                    'final_zip_size': len(final_zip) if final_zip else 0,
                                    'stats': stats,
                                    'min_scene': min(selected_scenes),
                                    'max_scene': max(selected_scenes)
                                }
                                print(f"[프롬프트 다운로드] ✅ 캐싱 완료", flush=True)
                                st.rerun()  # 다운로드 버튼 활성화

                            except Exception as e:
                                st.error(f"다운로드 데이터 생성 실패: {e}")
                                print(f"[프롬프트 다운로드] ❌ 오류: {e}", flush=True)
                                st.session_state['_prompt_download_cache'] = {'cache_key': download_cache_key}

                    # 다운로드 버튼 (캐시된 데이터 사용)
                    btn_col1, btn_col2, btn_col3 = st.columns(3)

                    # 캐시된 데이터 가져오기
                    dl_cache = st.session_state.get('_prompt_download_cache', {})
                    if dl_cache.get('cache_key') == download_cache_key:
                        excel_bytes = dl_cache.get('excel')
                        korean_zip = dl_cache.get('korean_zip')
                        final_zip = dl_cache.get('final_zip')
                        cached_stats = dl_cache.get('stats', stats)
                        min_scene = dl_cache.get('min_scene', min(selected_scenes))
                        max_scene = dl_cache.get('max_scene', max(selected_scenes))
                    else:
                        excel_bytes = None
                        korean_zip = None
                        final_zip = None
                        cached_stats = stats
                        min_scene = min(selected_scenes)
                        max_scene = max(selected_scenes)

                    with btn_col1:
                        if excel_bytes and len(excel_bytes) > 100:
                            st.download_button(
                                label=f"📊 엑셀 ({cached_stats['total']}개)",
                                data=excel_bytes,
                                file_name=f"prompts_scene{min_scene}-{max_scene}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_excel_{download_cache_key}",
                                use_container_width=True
                            )
                        else:
                            st.button("📊 엑셀 (생성 필요)", disabled=True, use_container_width=True, key="dl_excel_disabled")

                    with btn_col2:
                        if cached_stats.get('with_korean', 0) > 0 and korean_zip and len(korean_zip) > 22:
                            st.download_button(
                                label=f"📁 한글 ZIP ({cached_stats['with_korean']}개)",
                                data=korean_zip,
                                file_name=f"korean_prompts_scene{min_scene}-{max_scene}.zip",
                                mime="application/zip",
                                key=f"dl_korean_{download_cache_key}",
                                use_container_width=True
                            )
                        else:
                            st.button("📁 한글 ZIP (생성 필요)", disabled=True, use_container_width=True, key="dl_korean_disabled")

                    with btn_col3:
                        if cached_stats.get('with_final', 0) > 0 and final_zip and len(final_zip) > 22:
                            st.download_button(
                                label=f"📁 최종 ZIP ({cached_stats['with_final']}개)",
                                data=final_zip,
                                file_name=f"final_prompts_scene{min_scene}-{max_scene}.zip",
                                mime="application/zip",
                                key=f"dl_final_{download_cache_key}",
                                use_container_width=True
                            )
                        else:
                            st.button("📁 최종 ZIP (생성 필요)", disabled=True, use_container_width=True, key="dl_final_disabled")

                else:
                    st.info("다운로드할 씬을 선택해주세요.")

            except ImportError as e:
                st.error(f"필요한 패키지가 설치되지 않았습니다: {e}")
            except Exception as e:
                st.error(f"다운로드 데이터 생성 오류: {e}")
                import traceback
                print(f"[다운로드] 오류 상세: {traceback.format_exc()}")

    # ============================================================
    # 🇰🇷 한글 텍스트 씬 선택 섹션 (v1.0)
    # ============================================================
    with st.expander("🇰🇷 한글 텍스트 씬 선택", expanded=False):
        st.caption("한글 텍스트가 포함된 이미지를 생성할 씬을 자동으로 선택합니다.")

        scenes = get_scenes()
        if not scenes:
            st.warning("씬 데이터가 없습니다.")
        elif not KOREAN_SCENE_SELECTOR_AVAILABLE:
            st.warning("한글 씬 선택 모듈을 불러올 수 없습니다.")
        else:
            total_scenes = len(scenes)

            # 선택 모드
            korean_mode = st.radio(
                "선택 방식",
                options=["랜덤 샘플링", "AI 추천"],
                horizontal=True,
                key="korean_select_mode",
                label_visibility="collapsed"
            )

            korean_selected_scenes = set()
            korean_recommendation_data = {}

            if korean_mode == "랜덤 샘플링":
                st.markdown("##### 🎲 랜덤 샘플링 설정")

                random_type = st.selectbox(
                    "샘플링 방식",
                    options=["비율 기반", "구간 텀", "혼합 모드"],
                    key="korean_random_type"
                )

                if random_type == "비율 기반":
                    ratio = st.slider(
                        "선택 비율 (%)",
                        min_value=5,
                        max_value=50,
                        value=10,
                        step=5,
                        key="korean_ratio_percent",
                        help="전체 씬 중 선택할 비율"
                    )
                    seed = st.number_input(
                        "랜덤 시드 (재현성 위해, 0=랜덤)",
                        min_value=0,
                        max_value=99999,
                        value=0,
                        key="korean_ratio_seed"
                    )
                    if st.button("🎲 비율 샘플링 실행", key="run_ratio_sample", use_container_width=True):
                        korean_selected_scenes = select_korean_scenes_by_ratio(
                            total_scenes=total_scenes,
                            ratio_percent=ratio,
                            seed=seed if seed > 0 else None
                        )
                        # v1.2: 새 상태 관리 시스템에 저장
                        set_auto_selected_scenes(korean_selected_scenes, 'random')
                        st.session_state['korean_selected_scenes'] = update_legacy_state()
                        st.success(f"✅ {len(korean_selected_scenes)}개 씬 선택됨 ({ratio}%)")

                elif random_type == "구간 텀":
                    interval = st.slider(
                        "선택 간격",
                        min_value=2,
                        max_value=20,
                        value=5,
                        step=1,
                        key="korean_interval",
                        help="N개 씬마다 1개 선택"
                    )
                    randomize = st.checkbox(
                        "구간 내 랜덤 위치",
                        value=False,
                        key="korean_interval_random",
                        help="체크 시 각 구간 내에서 랜덤 위치 선택"
                    )
                    if st.button("🎲 구간 샘플링 실행", key="run_interval_sample", use_container_width=True):
                        korean_selected_scenes = select_korean_scenes_by_interval(
                            total_scenes=total_scenes,
                            interval=interval,
                            randomize_offset=randomize
                        )
                        # v1.2: 새 상태 관리 시스템에 저장
                        set_auto_selected_scenes(korean_selected_scenes, 'random')
                        st.session_state['korean_selected_scenes'] = update_legacy_state()
                        st.success(f"✅ {len(korean_selected_scenes)}개 씬 선택됨 ({interval}씬당 1개)")

                elif random_type == "혼합 모드":
                    base_interval = st.slider(
                        "기본 간격",
                        min_value=3,
                        max_value=15,
                        value=5,
                        step=1,
                        key="korean_hybrid_interval"
                    )
                    variation = st.slider(
                        "변동 범위 (±)",
                        min_value=0,
                        max_value=3,
                        value=1,
                        step=1,
                        key="korean_hybrid_variation",
                        help="기본 위치에서 ±N 범위 내 랜덤 변동"
                    )
                    if st.button("🎲 혼합 샘플링 실행", key="run_hybrid_sample", use_container_width=True):
                        korean_selected_scenes = select_korean_scenes_hybrid(
                            total_scenes=total_scenes,
                            base_interval=base_interval,
                            variation=variation
                        )
                        # v1.2: 새 상태 관리 시스템에 저장
                        set_auto_selected_scenes(korean_selected_scenes, 'random')
                        st.session_state['korean_selected_scenes'] = update_legacy_state()
                        st.success(f"✅ {len(korean_selected_scenes)}개 씬 선택됨 (간격 {base_interval} ±{variation})")

            else:  # AI 추천
                st.markdown("##### 🤖 AI 추천 설정")

                ai_model = st.selectbox(
                    "AI 모델",
                    options=["gemini-2.0-flash-exp", "gemini-2.0-flash", "gemini-1.5-pro", "claude-3-5-sonnet-20241022"],
                    key="korean_ai_model",
                    help="추천에 사용할 AI 모델"
                )

                # ⭐ v1.1: 분석 기준 선택 추가
                st.markdown("###### 📊 분석 기준")

                # 한글프롬프트 있는 씬 개수 계산
                korean_prompt_count = _count_scenes_with_korean_prompt(scenes)

                analysis_basis = st.radio(
                    "프롬프트 기준",
                    options=["original", "korean"],
                    format_func=lambda x: {
                        "original": f"🌐 원본프롬프트 (영어) - 전체 {total_scenes}개 씬",
                        "korean": f"🇰🇷 한글프롬프트 - {korean_prompt_count}개 씬 (한글 있는 씬만)"
                    }[x],
                    key="korean_analysis_basis",
                    help="원본프롬프트: 모든 씬 대상 / 한글프롬프트: 한글 있는 씬만 대상",
                    horizontal=True
                )

                # 분석 기준별 안내 메시지
                if analysis_basis == "original":
                    st.info(f"💡 **원본프롬프트 기준**: 전체 {total_scenes}개 씬을 영어 프롬프트로 분석합니다.")
                    analysis_target_count = total_scenes
                else:
                    if korean_prompt_count == 0:
                        st.warning("⚠️ 한글프롬프트가 있는 씬이 없습니다. 원본프롬프트 기준을 선택하세요.")
                    else:
                        st.info(f"💡 **한글프롬프트 기준**: {korean_prompt_count}개 씬만 한글 프롬프트로 분석합니다.")
                    analysis_target_count = korean_prompt_count

                # ⭐ v1.6: 선택 모드 추가
                st.markdown("###### 🎯 선택 모드")

                selection_mode = st.radio(
                    "선택 모드",
                    options=["비율 제한", "전체 선택"],
                    index=0,
                    horizontal=True,
                    key="korean_selection_mode",
                    help="'비율 제한': 목표 비율만큼만 선택 / '전체 선택': 프롬프트 조건에 맞는 모든 씬 선택"
                )

                # 모드별 설명 및 슬라이더 조건부 표시
                if selection_mode == "비율 제한":
                    st.info("📊 **비율 제한 모드**: AI가 목표 비율에 맞춰 가장 적합한 씬들을 선택합니다.")

                    target_ratio = st.slider(
                        "목표 선택 비율 (%)",
                        min_value=5,
                        max_value=30,
                        value=10,
                        step=5,
                        key="korean_ai_ratio",
                        help="AI가 목표로 할 선택 비율"
                    )

                    # 예상 선택 개수 표시
                    expected_count = max(1, int(analysis_target_count * target_ratio / 100))
                    st.caption(f"📌 예상 선택: {expected_count}개 / {analysis_target_count}개")
                else:
                    # 전체 선택 모드
                    st.info("🎯 **전체 선택 모드**: AI가 프롬프트 조건에 해당하는 **모든 씬**을 선택합니다. 비율 제한 없음.")
                    target_ratio = None  # 비율 없음
                    expected_count = "?"  # 알 수 없음
                    st.caption(f"📌 선택 대상: {analysis_target_count}개 씬 (조건에 맞는 모든 씬 선택)")

                # ============================================================
                # ⭐ v1.5: AI 프롬프트 다중 관리 섹션
                # ============================================================
                with st.expander("🤖 AI 프롬프트 설정", expanded=False):
                    st.caption("AI 추천에 사용되는 프롬프트를 선택하고 관리할 수 있습니다.")

                    if PROMPT_MANAGER_AVAILABLE:
                        # 프롬프트 매니저 초기화
                        pm = get_prompt_manager()
                        all_prompts = pm.get_all_prompts()
                        selected_id = pm.get_selected_prompt_id()
                        prompt_list = pm.get_prompt_list()

                        # ─────────────────────────────────────────────────────────
                        # 섹션 1: 프롬프트 선택
                        # ─────────────────────────────────────────────────────────
                        st.markdown("##### 📚 저장된 프롬프트")

                        # 프롬프트 옵션 생성
                        prompt_options = [p["id"] for p in prompt_list]
                        prompt_display = {p["id"]: f"{'🔒 ' if p.get('is_builtin') else '✏️ '}{p['name']}" for p in prompt_list}

                        # 현재 선택 인덱스
                        current_idx = prompt_options.index(selected_id) if selected_id in prompt_options else 0

                        # 프롬프트 선택 라디오
                        new_selected = st.radio(
                            "프롬프트 선택",
                            options=prompt_options,
                            format_func=lambda x: prompt_display.get(x, x),
                            index=current_idx,
                            key="korean_prompt_selector",
                            label_visibility="collapsed"
                        )

                        # 선택 변경 시 저장
                        if new_selected != selected_id:
                            pm.select_prompt(new_selected)
                            st.success(f"✅ '{all_prompts[new_selected]['name']}' 프롬프트 선택됨")
                            st.rerun()

                        # 선택된 프롬프트 정보 표시
                        selected_prompt = pm.get_prompt(new_selected)
                        if selected_prompt:
                            st.caption(f"📌 {selected_prompt.get('description', '')}")

                        st.markdown("---")

                        # ─────────────────────────────────────────────────────────
                        # 섹션 2: 프롬프트 관리 버튼
                        # ─────────────────────────────────────────────────────────
                        btn_col1, btn_col2, btn_col3 = st.columns(3)

                        with btn_col1:
                            if st.button("➕ 새로 만들기", key="add_prompt_btn", use_container_width=True):
                                st.session_state["show_add_prompt_modal"] = True

                        with btn_col2:
                            if st.button("📋 복제하기", key="duplicate_prompt_btn", use_container_width=True):
                                new_id = pm.duplicate_prompt(new_selected)
                                if new_id:
                                    pm.select_prompt(new_id)
                                    st.success("✅ 프롬프트 복제됨")
                                    st.rerun()

                        with btn_col3:
                            can_delete = selected_prompt and not selected_prompt.get("is_builtin", False)
                            if st.button("🗑️ 삭제", key="delete_prompt_btn", use_container_width=True, disabled=not can_delete):
                                if pm.delete_prompt(new_selected):
                                    st.success("✅ 프롬프트 삭제됨")
                                    st.rerun()
                                else:
                                    st.error("내장 프롬프트는 삭제할 수 없습니다.")

                        # ─────────────────────────────────────────────────────────
                        # 모달: 새 프롬프트 추가
                        # ─────────────────────────────────────────────────────────
                        if st.session_state.get("show_add_prompt_modal"):
                            st.markdown("---")
                            st.markdown("##### ➕ 새 프롬프트 만들기")

                            new_name = st.text_input("프롬프트 이름", placeholder="예: 내 커스텀 프롬프트", key="new_prompt_name")
                            new_desc = st.text_input("설명", placeholder="예: 특정 용도에 맞는 프롬프트", key="new_prompt_desc")
                            new_content = st.text_area("프롬프트 내용", height=150, key="new_prompt_content",
                                                       placeholder="AI에게 전달할 프롬프트를 입력하세요...")

                            modal_col1, modal_col2 = st.columns(2)
                            with modal_col1:
                                if st.button("✅ 추가", type="primary", use_container_width=True, key="confirm_add_prompt"):
                                    if new_name and new_content:
                                        new_id = pm.add_prompt(new_name, new_desc, new_content)
                                        pm.select_prompt(new_id)
                                        st.session_state["show_add_prompt_modal"] = False
                                        st.success(f"✅ '{new_name}' 프롬프트 추가됨")
                                        st.rerun()
                                    else:
                                        st.error("이름과 내용을 입력해주세요.")
                            with modal_col2:
                                if st.button("❌ 취소", use_container_width=True, key="cancel_add_prompt"):
                                    st.session_state["show_add_prompt_modal"] = False
                                    st.rerun()

                        st.markdown("---")

                        # ─────────────────────────────────────────────────────────
                        # 섹션 3: 프롬프트 편집
                        # ─────────────────────────────────────────────────────────
                        st.markdown("##### 📝 프롬프트 내용")

                        if selected_prompt:
                            # 내장 프롬프트가 아니면 이름/설명 편집 가능
                            if not selected_prompt.get("is_builtin"):
                                edit_col1, edit_col2 = st.columns(2)
                                with edit_col1:
                                    edit_name = st.text_input("이름", value=selected_prompt.get("name", ""), key="edit_prompt_name")
                                with edit_col2:
                                    edit_desc = st.text_input("설명", value=selected_prompt.get("description", ""), key="edit_prompt_desc")
                            else:
                                edit_name = selected_prompt.get("name", "")
                                edit_desc = selected_prompt.get("description", "")
                                st.info(f"📌 **{edit_name}** (내장 프롬프트)")

                            # 프롬프트 내용 편집
                            edit_content = st.text_area(
                                "프롬프트 내용",
                                value=selected_prompt.get("content", ""),
                                height=300,
                                key="edit_prompt_content",
                                label_visibility="collapsed"
                            )

                            # 변경 감지
                            content_changed = edit_content != selected_prompt.get("content", "")
                            name_changed = (not selected_prompt.get("is_builtin") and
                                          (edit_name != selected_prompt.get("name", "") or
                                           edit_desc != selected_prompt.get("description", "")))

                            if content_changed or name_changed:
                                st.warning("⚠️ 변경사항이 있습니다.")

                            # 저장 버튼
                            save_col1, save_col2, save_col3 = st.columns(3)

                            with save_col1:
                                if st.button("💾 변경사항 저장", type="primary", use_container_width=True,
                                           disabled=not (content_changed or name_changed), key="save_prompt_changes"):
                                    if selected_prompt.get("is_builtin"):
                                        pm.update_prompt(new_selected, content=edit_content)
                                    else:
                                        pm.update_prompt(new_selected, name=edit_name, description=edit_desc, content=edit_content)
                                    st.success("✅ 저장됨")
                                    st.rerun()

                            with save_col2:
                                if selected_prompt.get("is_builtin"):
                                    if st.button("🔄 원본 복원", use_container_width=True, key="reset_builtin_prompt"):
                                        pm.reset_to_default(new_selected)
                                        st.success("✅ 원본으로 복원됨")
                                        st.rerun()

                            with save_col3:
                                if st.button("📋 복사", use_container_width=True, key="copy_prompt_content"):
                                    st.code(selected_prompt.get("content", ""), language=None)

                        # 미리보기
                        with st.expander("👁️ 실제 전달될 프롬프트 미리보기", expanded=False):
                            preview = pm.get_selected_prompt_content()[:500]
                            st.markdown("**시스템 프롬프트 (처음 500자):**")
                            st.code(preview + "...", language=None)

                            st.markdown("**+ 자동 추가되는 씬 정보:**")
                            # ⭐ v1.6: 선택 모드에 따른 미리보기
                            if selection_mode == "전체 선택":
                                st.code(f"""
## 입력 데이터
전체 씬 수: {analysis_target_count}개

## 선택 방식
⚠️ 비율 제한 없음: 기준에 해당하는 모든 씬을 선택

### 씬 목록
씬 1: [프롬프트 내용...]
씬 2: [프롬프트 내용...]
...
                                """, language=None)
                            else:
                                st.code(f"""
## 입력 데이터
전체 씬 수: {analysis_target_count}개
목표 선택 수: {expected_count}개 ({target_ratio}%)

### 씬 목록
씬 1: [프롬프트 내용...]
씬 2: [프롬프트 내용...]
...
                                """, language=None)
                    else:
                        st.warning("⚠️ 프롬프트 관리 기능을 사용할 수 없습니다.")

                # AI 추천 실행 버튼
                if st.button("🤖 AI 추천 실행", key="run_ai_recommend", use_container_width=True, disabled=(analysis_basis == "korean" and korean_prompt_count == 0)):
                    import asyncio

                    with st.spinner("AI가 씬을 분석 중..."):
                        try:
                            # ⭐ v1.6: 선택 모드 변환
                            backend_selection_mode = "select_all" if selection_mode == "전체 선택" else "ratio_limit"
                            effective_ratio = target_ratio if target_ratio is not None else 10.0  # 전체 선택 시 기본값 (실제 사용 안 함)

                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            result = loop.run_until_complete(
                                recommend_korean_scenes_with_ai(
                                    scenes=scenes,
                                    model_name=ai_model,
                                    target_ratio=effective_ratio,
                                    analysis_basis=analysis_basis,
                                    selection_mode=backend_selection_mode  # ⭐ v1.6
                                    # custom_prompt는 프롬프트 매니저에서 자동으로 가져옴
                                )
                            )
                            loop.close()

                            if result.get("error"):
                                st.error(f"AI 추천 오류: {result['error']}")
                            else:
                                korean_selected_scenes = extract_selected_scene_numbers(result)
                                # v1.2: 새 상태 관리 시스템에 저장
                                set_auto_selected_scenes(korean_selected_scenes, 'ai')
                                st.session_state['korean_selected_scenes'] = update_legacy_state()
                                st.session_state['korean_recommendation_data'] = result
                                prompt_name = result.get("prompt_name", "기본")

                                # ⭐ v1.6: 모드별 성공 메시지
                                if backend_selection_mode == "select_all":
                                    st.success(f"✅ 조건에 맞는 {len(korean_selected_scenes)}개 씬 모두 선택됨 (프롬프트: {prompt_name})")
                                else:
                                    st.success(f"✅ {len(korean_selected_scenes)}개 씬 AI 추천됨 (목표 {target_ratio}%, 프롬프트: {prompt_name})")

                                if result.get("selection_summary"):
                                    st.info(f"📝 {result['selection_summary']}")
                        except Exception as e:
                            st.error(f"AI 추천 실패: {e}")

            # v1.2: 세션에서 선택된 씬 복원 + 새 상태 관리 동기화
            init_korean_scene_state()
            sync_with_legacy_state()

            if 'korean_selected_scenes' in st.session_state:
                korean_selected_scenes = st.session_state['korean_selected_scenes']
            if 'korean_recommendation_data' in st.session_state:
                korean_recommendation_data = st.session_state['korean_recommendation_data']

            # v1.2: 새 상태 관리 시스템에서 전체 선택 (자동 + 수동) 가져오기
            all_selected_korean = get_all_selected_korean_scenes()
            korean_stats = get_korean_scene_stats()

            # 결과 표시 및 다운로드
            if all_selected_korean:
                st.markdown("---")
                st.markdown("##### 📊 선택 결과")

                # v1.2: 새로운 통계 표시 (자동 + 수동 구분)
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(
                        "선택된 씬",
                        f"{korean_stats['total_selected']}개",
                        help=f"자동: {korean_stats['auto_count']}개 + 수동: {korean_stats['manual_count']}개"
                    )
                with col2:
                    st.metric("전체 씬", f"{total_scenes}개")
                with col3:
                    ratio = (korean_stats['total_selected'] / total_scenes * 100) if total_scenes > 0 else 0
                    st.metric("선택 비율", f"{ratio:.1f}%")
                with col4:
                    # 자동/수동 구분 표시
                    st.markdown(f"""
                        <div style="font-size: 12px; color: #666; padding: 8px 0;">
                            🎲 자동: {korean_stats['auto_count']}개<br>
                            ✋ 수동: {korean_stats['manual_count']}개
                        </div>
                    """, unsafe_allow_html=True)

                # v1.2: 기존 stats 호환을 위한 보완
                stats = {
                    'selected_count': korean_stats['total_selected'],
                    'total_count': total_scenes,
                    'ratio_percent': ratio,
                    'scene_numbers': sorted(list(all_selected_korean))
                }
                # 기존 korean_selected_scenes를 all_selected_korean으로 업데이트
                korean_selected_scenes = all_selected_korean

                # v1.2: 선택된 씬 번호 미리보기 (자동/수동 구분)
                with st.expander("📋 선택된 씬 번호 보기"):
                    auto_scenes = get_auto_selected_scenes()
                    manual_scenes = get_manual_added_scenes()

                    if auto_scenes:
                        method_label = "AI 추천" if korean_stats['method'] == 'ai' else "랜덤 선택"
                        st.markdown(f"**🎲 {method_label}:** {sorted(auto_scenes)}")

                    if manual_scenes:
                        st.markdown(f"**✋ 수동 추가:** {sorted(manual_scenes)}")

                    st.markdown(f"**📌 전체 선택:** {stats['scene_numbers']}")

                # 다운로드 버튼
                st.markdown("---")
                st.markdown("##### 📥 엑셀 다운로드 (한글 추천 씬 음영 표시)")

                try:
                    # 프롬프트 데이터 수집
                    project_path = st.session_state.get("project_path", "")
                    backgrounds_folder = Path(project_path) / "images" / "backgrounds" if project_path else None

                    latest_images = {}
                    if backgrounds_folder and backgrounds_folder.exists():
                        latest_images = get_latest_image_per_scene(backgrounds_folder)

                    # 전체 씬 또는 선택된 씬만 포함
                    include_all_scenes = st.checkbox(
                        "전체 씬 포함 (선택 씬 음영 표시)",
                        value=True,
                        key="korean_include_all",
                        help="체크 시 전체 씬 포함, 해제 시 선택된 씬만 포함"
                    )

                    if include_all_scenes:
                        target_scenes = list(range(1, total_scenes + 1))
                    else:
                        target_scenes = sorted(list(korean_selected_scenes))

                    # 추천 정보 포함 여부
                    include_recommend_info = st.checkbox(
                        "AI 추천 정보 포함",
                        value=bool(korean_recommendation_data),
                        key="korean_include_recommend_info",
                        disabled=not korean_recommendation_data
                    )

                    # ⭐ v3.25.1: 엑셀 생성/다운로드 분리 - 다운로드 실패 버그 수정
                    # 원인: 다운로드 클릭 시 Streamlit rerun으로 엑셀이 재생성되어 해시 변경
                    # 해결: 명시적 "생성" 버튼 사용, 다운로드 시 재생성 방지

                    excel_cache_key = f"{len(target_scenes)}_{len(korean_selected_scenes)}_{include_recommend_info}"
                    cached_excel = st.session_state.get('_korean_excel_bytes')
                    cached_meta = st.session_state.get('_korean_excel_meta')
                    cached_key = st.session_state.get('_korean_excel_cache_key')

                    # 옵션 변경 감지 (캐시 무효화)
                    options_changed = cached_key != excel_cache_key

                    if options_changed and cached_excel:
                        st.info("ℹ️ 옵션이 변경되었습니다. '엑셀 생성' 버튼을 눌러 새로 생성하세요.")

                    # 엑셀 생성 버튼 (다운로드와 분리)
                    gen_col1, gen_col2 = st.columns([1, 1])

                    with gen_col1:
                        if st.button(
                            "📝 엑셀 생성" if not cached_excel or options_changed else "🔄 엑셀 재생성",
                            key="korean_excel_generate_btn",
                            type="secondary" if cached_excel and not options_changed else "primary",
                            use_container_width=True,
                            help="엑셀 파일을 생성합니다. 생성 후 다운로드 버튼이 활성화됩니다."
                        ):
                            # 프롬프트 수집
                            with st.spinner("엑셀 생성 중..."):
                                if korean_recommendation_data and include_recommend_info:
                                    prompts = collect_prompts_with_korean_recommendation(
                                        selected_scene_nums=target_scenes,
                                        scenes=scenes,
                                        latest_images=latest_images,
                                        korean_recommended=korean_recommendation_data,
                                        use_latest_metadata=True
                                    )
                                else:
                                    prompts = collect_prompts_for_selected_scenes(
                                        selected_scene_nums=target_scenes,
                                        scenes=scenes,
                                        latest_images=latest_images,
                                        use_latest_metadata=True
                                    )

                                # 프롬프트 데이터 검증
                                if not prompts:
                                    st.session_state['_korean_excel_bytes'] = None
                                    st.session_state['_korean_excel_cache_key'] = excel_cache_key
                                    st.session_state['_korean_excel_meta'] = None
                                    st.error("❌ 프롬프트 데이터가 없습니다. 이미지 생성을 먼저 진행해주세요.")
                                else:
                                    # 엑셀 생성 및 캐싱
                                    excel_bytes = generate_prompts_excel_with_highlight(
                                        prompts=prompts,
                                        korean_recommended_scenes=korean_selected_scenes,
                                        highlight_color="FFFF99",  # 연한 노란색
                                        include_recommendation_info=include_recommend_info
                                    )

                                    if excel_bytes and len(excel_bytes) > 0:
                                        st.session_state['_korean_excel_bytes'] = excel_bytes
                                        st.session_state['_korean_excel_cache_key'] = excel_cache_key
                                        st.session_state['_korean_excel_meta'] = {
                                            'prompts_count': len(prompts),
                                            'target_scenes': len(target_scenes),
                                            'selected_count': len(korean_selected_scenes)
                                        }
                                        print(f"[한글씬선택] 엑셀 생성 및 캐싱 완료: {len(excel_bytes)} bytes")
                                        st.success(f"✅ 엑셀 생성 완료! ({len(excel_bytes):,} bytes)")
                                        st.rerun()  # 다운로드 버튼 활성화를 위해 rerun
                                    else:
                                        st.session_state['_korean_excel_bytes'] = None
                                        st.session_state['_korean_excel_cache_key'] = excel_cache_key
                                        st.session_state['_korean_excel_meta'] = None
                                        st.error("❌ 엑셀 생성 실패 (빈 데이터)")

                    with gen_col2:
                        # 다운로드 버튼 - 캐시된 데이터만 사용 (재생성 없음!)
                        # v1.1: 동적 키 사용으로 rerun 시 temp file 무효화 방지
                        if cached_excel and cached_meta and not options_changed:
                            # 동적 키 생성 (캐시 키 기반)
                            dl_key = f"korean_excel_dl_{excel_cache_key}"
                            st.download_button(
                                label=f"📥 다운로드 ({cached_meta['selected_count']}개 음영)",
                                data=cached_excel,
                                file_name=f"korean_scenes_{cached_meta['selected_count']}selected.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=dl_key,
                                use_container_width=True,
                                type="primary"
                            )
                        else:
                            st.button(
                                "📥 다운로드 (생성 필요)",
                                disabled=True,
                                use_container_width=True,
                                key="korean_excel_download_disabled"
                            )

                    # 현재 상태 표시
                    if cached_excel and cached_meta and not options_changed:
                        st.success(f"✅ 엑셀 준비됨: {cached_meta['target_scenes']}개 씬, {cached_meta['selected_count']}개 음영 ({len(cached_excel):,} bytes)")

                        # 디버그 정보 (expander로 숨김)
                        with st.expander("🔍 디버그 정보", expanded=False):
                            st.caption(f"- 프롬프트 수: {cached_meta['prompts_count']}개")
                            st.caption(f"- 엑셀 크기: {len(cached_excel):,} bytes")
                            st.caption(f"- 대상 씬: {cached_meta['target_scenes']}개")
                            st.caption(f"- 음영 표시 씬: {sorted(korean_selected_scenes)[:10]}{'...' if len(korean_selected_scenes) > 10 else ''}")
                            st.caption(f"- 캐시 키: {cached_key}")
                    elif not cached_excel:
                        st.info("ℹ️ '엑셀 생성' 버튼을 눌러 다운로드 파일을 준비하세요.")

                except Exception as e:
                    st.error(f"엑셀 생성 오류: {e}")
                    import traceback
                    error_detail = traceback.format_exc()
                    print(f"[한글씬선택] 오류 상세: {error_detail}")
                    with st.expander("오류 상세", expanded=False):
                        st.code(error_detail)

                # ============================================================
                # 📋 스토리보드 연동 (v1.0)
                # ============================================================
                st.markdown("---")
                st.markdown("##### 📋 스토리보드 연동")

                storyboard_col1, storyboard_col2 = st.columns(2)

                with storyboard_col1:
                    if st.button(
                        "📋 스토리보드에 적용",
                        key="apply_korean_text_to_storyboard",
                        type="primary",
                        use_container_width=True,
                        help="스토리보드 페이지에서 한글 텍스트 씬 필터링 가능"
                    ):
                        # 세션에 저장 (스토리보드에서 사용)
                        st.session_state['korean_text_scenes_applied'] = True
                        st.session_state['korean_text_scene_ids'] = sorted(list(korean_selected_scenes))

                        # 적용 시간 기록 (datetime은 파일 상단에서 import됨)
                        st.session_state['korean_text_applied_at'] = datetime.now().isoformat()

                        st.success(f"✅ {len(korean_selected_scenes)}개 한글 텍스트 씬이 스토리보드에 적용되었습니다!")
                        st.info("💡 스토리보드 페이지에서 '🔤 한글 텍스트 씬 관리' 섹션을 확인하세요.")

                        print(f"[한글 텍스트 씬] 스토리보드 적용: {len(korean_selected_scenes)}개", flush=True)

                with storyboard_col2:
                    # 현재 적용 상태 표시
                    if st.session_state.get('korean_text_scenes_applied'):
                        applied_count = len(st.session_state.get('korean_text_scene_ids', []))
                        applied_at = st.session_state.get('korean_text_applied_at', '')
                        st.success(f"📋 적용됨 ({applied_count}개)")
                        if applied_at:
                            st.caption(f"적용 시간: {applied_at[:16].replace('T', ' ')}")
                    else:
                        st.caption("📋 미적용 상태")

                st.markdown("---")

                # 선택 초기화 버튼
                if st.button("🔄 선택 초기화", key="korean_reset", use_container_width=True):
                    if 'korean_selected_scenes' in st.session_state:
                        del st.session_state['korean_selected_scenes']
                    if 'korean_recommendation_data' in st.session_state:
                        del st.session_state['korean_recommendation_data']
                    st.rerun()

    # ============================================================
    # 📦 배치 이미지 업로드 섹션 (v1.0 - 씬별 일괄 대체)
    # ============================================================
    with st.expander("📦 배치 이미지 업로드 (씬별 일괄 대체)", expanded=False):
        st.info("""
        💡 **파일명 규칙**: 씬번호.확장자
        - 예시: `1.jpg`, `2.png`, `10.jpeg`, `100.jpg`
        - 지원 형식: JPG, JPEG, PNG, WEBP
        """)

        # 파일 업로더
        uploaded_files = st.file_uploader(
            "이미지 파일들을 선택하세요",
            type=['jpg', 'jpeg', 'png', 'webp'],
            accept_multiple_files=True,
            key="batch_image_upload"
        )

        if uploaded_files:
            try:
                from utils.batch_image_upload import (
                    analyze_batch_upload,
                    get_batch_upload_stats,
                    apply_batch_images,
                    get_existing_background_images
                )
                from utils.scene_image_manager import SceneImageManager

                scenes = get_scenes()
                total_scenes = len(scenes)

                if total_scenes == 0:
                    st.warning("씬 데이터가 없습니다. 먼저 씬 분석을 실행해주세요.")
                else:
                    # 기존 배경 이미지 정보 수집
                    existing_images = get_existing_background_images(scenes)

                    # 분석
                    results = analyze_batch_upload(uploaded_files, total_scenes, existing_images)
                    stats = get_batch_upload_stats(results)

                    # 통계 표시
                    st.markdown("---")
                    st.markdown("##### 📋 분석 결과")

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("전체 파일", stats["total"])
                    col2.metric("✅ 매칭 성공", stats["success"])
                    col3.metric("⚠️ 범위 초과", stats["out_of_range"])
                    col4.metric("❌ 인식 실패", stats["invalid_name"] + stats["invalid_format"])

                    # 상세 결과
                    if results:
                        st.markdown("##### 📊 상세 매칭 결과")

                        # 성공 항목
                        if stats["success_items"]:
                            with st.expander(f"✅ 매칭 성공 ({stats['success']}개)", expanded=True):
                                for item in stats["success_items"]:
                                    col1, col2, col3 = st.columns([2, 1, 2])
                                    with col1:
                                        st.text(f"📄 {item.filename}")
                                    with col2:
                                        st.text(f"→ 씬 {item.scene_number}")
                                    with col3:
                                        if item.current_image_path:
                                            st.caption("🔄 기존 이미지 대체")
                                        else:
                                            st.caption("➕ 새 이미지 추가")

                        # 실패 항목
                        if stats["failed_items"]:
                            with st.expander(f"❌ 실패/스킵 ({len(stats['failed_items'])}개)", expanded=False):
                                for item in stats["failed_items"]:
                                    status_icon = {"out_of_range": "⚠️", "duplicate": "🔁"}.get(item.status, "❌")
                                    st.text(f"{status_icon} {item.filename}: {item.message}")

                    # 옵션
                    st.markdown("---")
                    backup_enabled = st.checkbox(
                        "☑️ 기존 이미지 백업",
                        value=True,
                        help="대체되는 기존 이미지를 백업 폴더에 저장합니다",
                        key="batch_backup_option"
                    )

                    # 적용 버튼
                    if stats["success"] > 0:
                        if st.button(
                            f"🚀 {stats['success']}개 씬 이미지 일괄 대체하기",
                            type="primary",
                            key="apply_batch_upload"
                        ):
                            with st.spinner("이미지 적용 중..."):
                                # 배경 폴더 경로
                                bg_folder = project_path / "images" / "backgrounds"

                                # SceneImageManager 인스턴스
                                sim = SceneImageManager(str(project_path))

                                # 적용
                                apply_result = apply_batch_images(
                                    results=results,
                                    backgrounds_folder=bg_folder,
                                    backup=backup_enabled,
                                    scene_image_manager=sim
                                )

                            # 결과 표시
                            if apply_result["applied"] > 0:
                                st.success(f"✅ {apply_result['applied']}개 씬 이미지가 성공적으로 대체되었습니다!")

                                if apply_result["backed_up"] > 0:
                                    st.info(f"📁 {apply_result['backed_up']}개 기존 이미지가 백업되었습니다")

                                # 캐시 클리어
                                st.cache_data.clear()
                                st.toast("이미지 캐시가 새로고침되었습니다.")

                                time.sleep(1)
                                st.rerun()

                            if apply_result["failed"] > 0:
                                st.warning(f"⚠️ {apply_result['failed']}개 파일 적용 실패")
                    else:
                        st.warning("매칭된 파일이 없습니다. 파일명을 확인해주세요. (예: 1.jpg, 2.png)")

            except ImportError as e:
                st.error(f"배치 업로드 모듈 로드 실패: {e}")
            except Exception as e:
                st.error(f"배치 업로드 처리 오류: {e}")
                import traceback
                with st.expander("오류 상세"):
                    st.code(traceback.format_exc())
        else:
            st.caption("파일을 업로드하면 분석 결과가 표시됩니다.")

    if not images:
        st.info("생성된 이미지가 없습니다.")
        return

    st.markdown(f"**총 {len(images)}개 이미지**")

    # 옵션 체크박스 + 새로고침 버튼 (v2.2)
    opt_col1, opt_col2, opt_col3, opt_col4 = st.columns([1, 1, 1, 0.5])
    with opt_col1:
        multi_select = st.checkbox("다중 선택 모드", key="gallery_multi")
    with opt_col2:
        show_latest_only = st.checkbox("🕐 최신만 보기", key="gallery_show_latest", help="각 씬별 가장 최신 이미지만 표시")
    with opt_col3:
        st.caption(f"최신 이미지: {len(latest_images)}개")
    with opt_col4:
        # 🆕 v2.2: 새로고침 버튼
        if st.button("🔄", key="gallery_refresh", help="이미지 개수 새로고침"):
            clear_gallery_cache()
            st.rerun()

    # ============================================================
    # 🆕 최신만 다운로드 및 정리 섹션
    # ============================================================
    st.markdown("---")
    st.markdown("#### ⏰ 최신 이미지 다운로드")

    latest_dl_col1, latest_dl_col2, latest_dl_col3 = st.columns(3)

    # v1.1: ZIP 캐싱 (MediaFileHandler 에러 방지)
    latest_zip_key = f"gallery_latest_zip_{len(latest_images) if latest_images else 0}"
    all_zip_key = f"gallery_all_zip_{len(all_scanned) if all_scanned else 0}"

    with latest_dl_col1:
        # 최신만 다운로드
        if latest_images:
            # 캐시된 ZIP 사용 또는 생성 (v1.2: BytesIO → bytes 변환으로 다운로드 안정성 개선)
            if latest_zip_key not in st.session_state:
                zip_buffer = gallery_manager.create_zip_buffer(latest_images)
                st.session_state[latest_zip_key] = zip_buffer.getvalue()  # bytes로 변환
                st.session_state[f"{latest_zip_key}_name"] = gallery_manager.get_zip_filename("latest_images")

            st.download_button(
                label=f"⏰ 최신만 다운로드 ({len(latest_images)}개)",
                data=st.session_state[latest_zip_key],
                file_name=st.session_state.get(f"{latest_zip_key}_name", "latest_images.zip"),
                mime="application/zip",
                type="primary",
                key=f"dl_latest_{len(latest_images)}",
                use_container_width=True
            )
        else:
            st.button("⏰ 최신만 다운로드 (0개)", disabled=True, use_container_width=True, key="dl_latest_disabled")

    with latest_dl_col2:
        # 프로젝트 폴더에 최신만 저장
        if st.button("📁 최신만 폴더 저장", key="save_latest_to_folder", use_container_width=True):
            if latest_images:
                success, save_dir, saved_count = gallery_manager.save_latest_to_folder(latest_images)
                if success:
                    st.success(f"✅ {saved_count}개 저장: {save_dir}")
            else:
                st.warning("저장할 이미지가 없습니다.")

    with latest_dl_col3:
        # 전체 다운로드 (중복 포함)
        if all_scanned:
            # 캐시된 ZIP 사용 또는 생성 (v1.2: BytesIO → bytes 변환)
            if all_zip_key not in st.session_state:
                zip_buffer = gallery_manager.create_zip_with_timestamp(all_scanned)
                st.session_state[all_zip_key] = zip_buffer.getvalue()  # bytes로 변환
                st.session_state[f"{all_zip_key}_name"] = gallery_manager.get_zip_filename("all_images")

            st.download_button(
                label=f"📦 전체 다운로드 ({len(all_scanned)}개)",
                data=st.session_state[all_zip_key],
                file_name=st.session_state.get(f"{all_zip_key}_name", "all_images.zip"),
                mime="application/zip",
                key=f"dl_all_{len(all_scanned)}",
                use_container_width=True
            )

    # ============================================================
    # 🆕 이미지 정리 (중복 삭제)
    # ============================================================
    if analysis["duplicates_count"] > 0:
        st.markdown("---")
        with st.expander(f"🗑️ 이미지 정리 ({analysis['duplicates_count']}개 중복, {analysis['duplicates_size_mb']:.1f}MB 절약 가능)", expanded=False):
            # 중복 분석 상세
            st.markdown("##### 📊 씬별 중복 현황")

            for stat in analysis["scene_stats"][:15]:
                prog_col1, prog_col2, prog_col3 = st.columns([1, 2, 1])
                with prog_col1:
                    st.caption(f"씬 {stat['scene_id']}")
                with prog_col2:
                    st.progress(stat['keep'] / stat['total'])
                with prog_col3:
                    st.caption(f"{stat['total']}개 → {stat['keep']}개 (-{stat['delete']}개)")

            if len(analysis["scene_stats"]) > 15:
                st.caption(f"... 외 {len(analysis['scene_stats']) - 15}개 씬")

            st.markdown("---")

            # 정리 옵션
            cleanup_col1, cleanup_col2 = st.columns(2)

            with cleanup_col1:
                cleanup_action = st.radio(
                    "정리 방식",
                    options=["🗑️ 영구 삭제", "📁 아카이브로 이동"],
                    key="gallery_cleanup_action",
                    horizontal=True
                )

            with cleanup_col2:
                # 시뮬레이션
                if st.button("🔍 시뮬레이션", key="gallery_cleanup_simulate", use_container_width=True):
                    result = gallery_manager.delete_old_images(all_scanned, dry_run=True)
                    st.info(f"📋 {result['deleted_count']}개 파일 삭제 예정 ({result['deleted_size_mb']:.1f}MB)")

            # 확인 체크박스
            confirm_delete = st.checkbox("⚠️ 정말 실행하시겠습니까? (복구 불가)", key="gallery_cleanup_confirm")

            if "영구 삭제" in cleanup_action:
                if st.button(
                    f"🗑️ 최신 제외 모두 삭제 ({analysis['duplicates_count']}개)",
                    type="primary",
                    disabled=not confirm_delete,
                    use_container_width=True,
                    key="gallery_cleanup_delete"
                ):
                    with st.spinner("삭제 중..."):
                        result = gallery_manager.delete_old_images(all_scanned, dry_run=False)

                    if result["errors"]:
                        st.error(f"⚠️ {len(result['errors'])}개 파일 삭제 실패")
                    st.success(f"✅ {result['deleted_count']}개 파일 삭제 완료! ({result['deleted_size_mb']:.1f}MB 절약)")
                    clear_gallery_cache()  # ⭐ v2.2: 캐시 무효화
                    st.rerun()
            else:
                if st.button(
                    f"📁 아카이브로 이동 ({analysis['duplicates_count']}개)",
                    type="primary",
                    disabled=not confirm_delete,
                    use_container_width=True,
                    key="gallery_cleanup_archive"
                ):
                    with st.spinner("이동 중..."):
                        result = gallery_manager.move_old_to_archive(all_scanned)

                    if result["errors"]:
                        st.error(f"⚠️ {len(result['errors'])}개 파일 이동 실패")
                    st.success(f"✅ {result['moved_count']}개 파일 아카이브로 이동! ({result['moved_size_mb']:.1f}MB)")
                    st.caption(f"📁 아카이브: {result['archive_folder']}")
                    clear_gallery_cache()  # ⭐ v2.2: 캐시 무효화
                    st.rerun()

    st.markdown("---")

    # 최신만 보기 필터 적용
    if show_latest_only:
        # latest_images를 일반 images 형식으로 변환
        images = [{"path": img.path, "filename": img.filename, "scene_id": img.scene_id, "type": img.image_type, "created": img.created} for img in latest_images]
        st.info(f"🕐 각 씬별 최신 이미지만 표시 중 ({len(images)}개)")

    if multi_select:
        selected_images = st.session_state.get("selected_gallery_images", [])

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("전체 선택"):
                st.session_state["selected_gallery_images"] = [img["path"] for img in images]
                st.rerun()
        with col2:
            if st.button("전체 해제"):
                st.session_state["selected_gallery_images"] = []
                st.rerun()
        with col3:
            if st.button(f"🗑️ 선택 삭제 ({len(selected_images)}개)", disabled=len(selected_images) == 0):
                for path in selected_images:
                    delete_image(path)
                st.session_state["selected_gallery_images"] = []
                st.success(f"{len(selected_images)}개 이미지 삭제됨")
                clear_gallery_cache()  # ⭐ v2.2: 캐시 무효화
                st.rerun()

        # 📥 일괄 다운로드 섹션
        st.markdown("#### 📥 일괄 다운로드")
        dl_col1, dl_col2, dl_col3 = st.columns(3)

        with dl_col1:
            # 선택된 이미지 ZIP 다운로드 (v1.2: BytesIO → bytes 변환)
            if selected_images and len(selected_images) > 0:
                from utils.download_manager import create_images_zip
                zip_buffer, zip_filename = create_images_zip(selected_images)
                st.download_button(
                    label=f"📦 선택 다운로드 ({len(selected_images)}개)",
                    data=zip_buffer.getvalue(),  # bytes로 변환
                    file_name=zip_filename,
                    mime="application/zip",
                    key="download_selected_zip",
                    use_container_width=True
                )
            else:
                st.button("📦 선택 다운로드 (0개)", disabled=True, use_container_width=True)

        with dl_col2:
            # 전체 이미지 ZIP 다운로드 (v1.2: BytesIO → bytes 변환)
            all_image_paths = [img["path"] for img in images if os.path.exists(img["path"])]
            if all_image_paths:
                from utils.download_manager import create_images_zip
                zip_buffer_all, zip_filename_all = create_images_zip(all_image_paths, f"all_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
                st.download_button(
                    label=f"📦 전체 다운로드 ({len(all_image_paths)}개)",
                    data=zip_buffer_all.getvalue(),  # bytes로 변환
                    file_name=zip_filename_all,
                    mime="application/zip",
                    key="download_all_zip",
                    use_container_width=True
                )
            else:
                st.button("📦 전체 다운로드 (0개)", disabled=True, use_container_width=True)

        with dl_col3:
            # 프로젝트 폴더에 저장
            if st.button("📁 프로젝트 폴더 저장", key="save_to_folder", use_container_width=True):
                try:
                    from utils.download_manager import SceneDownloadManager
                    manager = SceneDownloadManager(video_path=str(project_path))
                    save_paths = selected_images if selected_images else all_image_paths
                    if save_paths:
                        save_images = manager.collect_images_from_paths(save_paths)
                        success, save_dir, saved_files = manager.save_to_project_folder(
                            images=save_images,
                            subfolder="downloaded_images"
                        )
                        if success and saved_files:
                            st.success(f"✅ {len(saved_files)}개 저장: {save_dir}")
                        else:
                            st.warning("저장할 이미지가 없습니다.")
                    else:
                        st.warning("저장할 이미지를 선택하세요.")
                except Exception as e:
                    st.error(f"저장 오류: {e}")

    # 📥 일괄 다운로드 (다중 선택 모드가 아닐 때)
    else:
        st.markdown("#### 📥 일괄 다운로드")
        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            all_image_paths = [img["path"] for img in images if os.path.exists(img["path"])]
            if all_image_paths:
                # v1.2: BytesIO → bytes 변환으로 다운로드 안정성 개선
                from utils.download_manager import create_images_zip
                zip_buffer_all, zip_filename_all = create_images_zip(all_image_paths, f"all_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
                st.download_button(
                    label=f"📦 전체 ZIP 다운로드 ({len(all_image_paths)}개)",
                    data=zip_buffer_all.getvalue(),  # bytes로 변환
                    file_name=zip_filename_all,
                    mime="application/zip",
                    key="download_all_zip_simple",
                    type="primary",
                    use_container_width=True
                )

        with dl_col2:
            if st.button("📁 프로젝트 폴더에 저장", key="save_to_folder_simple", use_container_width=True):
                try:
                    from utils.download_manager import SceneDownloadManager
                    all_image_paths = [img["path"] for img in images if os.path.exists(img["path"])]
                    manager = SceneDownloadManager(video_path=str(project_path))
                    if all_image_paths:
                        save_images = manager.collect_images_from_paths(all_image_paths)
                        success, save_dir, saved_files = manager.save_to_project_folder(
                            images=save_images,
                            subfolder="downloaded_images"
                        )
                        if success and saved_files:
                            st.success(f"✅ {len(saved_files)}개 저장: {save_dir}")
                        else:
                            st.warning("저장할 이미지가 없습니다.")
                except Exception as e:
                    st.error(f"저장 오류: {e}")

    st.markdown("---")

    # 🔄 프로세스 간 동기화 섹션
    from utils.sync_manager import ProcessType
    from utils.sync_ui import render_sync_buttons
    render_sync_buttons(ProcessType.IMAGE_GENERATION)

    st.markdown("---")

    # 세션 상태 초기화
    if "selected_gallery_images" not in st.session_state:
        st.session_state["selected_gallery_images"] = []

    # 선택된 이미지 수 표시 (다중 선택 모드일 때)
    if multi_select:
        selected_count = len(st.session_state.get("selected_gallery_images", []))
        if selected_count > 0:
            st.info(f"📌 **{selected_count}개** 이미지 선택됨")

    # v2.2: 페이지네이션 추가 (메모리 효율화)
    IMAGES_PER_PAGE = 20
    total_images = len(images)

    if total_images > IMAGES_PER_PAGE:
        # 페이지 상태 관리
        if "gallery_page" not in st.session_state:
            st.session_state["gallery_page"] = 1

        current_page = st.session_state["gallery_page"]

        # 페이지네이션 적용
        paginated_images, total_pages = get_paginated_images(images, current_page, IMAGES_PER_PAGE)

        # 페이지 네비게이션
        nav_col1, nav_col2, nav_col3, nav_col4, nav_col5 = st.columns([1, 1, 2, 1, 1])

        with nav_col1:
            if st.button("⏮️ 처음", disabled=current_page <= 1, key="gallery_first"):
                st.session_state["gallery_page"] = 1
                st.rerun()

        with nav_col2:
            if st.button("◀️ 이전", disabled=current_page <= 1, key="gallery_prev"):
                st.session_state["gallery_page"] = current_page - 1
                st.rerun()

        with nav_col3:
            st.markdown(f"<div style='text-align:center;padding-top:8px;'><b>페이지 {current_page} / {total_pages}</b> ({total_images}개 이미지)</div>", unsafe_allow_html=True)

        with nav_col4:
            if st.button("다음 ▶️", disabled=current_page >= total_pages, key="gallery_next"):
                st.session_state["gallery_page"] = current_page + 1
                st.rerun()

        with nav_col5:
            if st.button("마지막 ⏭️", disabled=current_page >= total_pages, key="gallery_last"):
                st.session_state["gallery_page"] = total_pages
                st.rerun()

        st.markdown("---")

        # 표시할 이미지 = 현재 페이지 이미지
        display_images = paginated_images
    else:
        # 이미지가 적으면 페이지네이션 없이 전체 표시
        display_images = images

    # 이미지 그리드
    cols = st.columns(4)

    for i, img in enumerate(display_images):
        with cols[i % 4]:
            # v2.2: 고유 키 생성 (이미지 파일명 기반, 페이지네이션 호환)
            img_key = img.get("filename", "").replace(".", "_").replace(" ", "_")[:50]

            # 다중 선택 모드: 체크박스 표시 (더 명확하게!)
            if multi_select:
                is_checked = img["path"] in st.session_state.get("selected_gallery_images", [])

                # 체크박스와 씬 번호를 한 행에 표시
                cb_col, info_col = st.columns([1, 2])
                with cb_col:
                    new_checked = st.checkbox(
                        "✓",
                        value=is_checked,
                        key=f"gallery_select_{img_key}",
                        help="이미지 선택"
                    )
                with info_col:
                    scene_id = img.get("scene_id", "?")
                    st.markdown(f"**씬 {scene_id}**" if is_checked else f"씬 {scene_id}")

                # 상태 업데이트
                if new_checked and img["path"] not in st.session_state["selected_gallery_images"]:
                    st.session_state["selected_gallery_images"].append(img["path"])
                elif not new_checked and img["path"] in st.session_state["selected_gallery_images"]:
                    st.session_state["selected_gallery_images"].remove(img["path"])

                is_selected = img["path"] in st.session_state.get("selected_gallery_images", [])
            else:
                is_selected = False

            # v1.2: 한글 씬 상태 확인
            scene_id_for_korean = img.get("scene_id")
            try:
                scene_id_int = int(scene_id_for_korean) if scene_id_for_korean else 0
            except (ValueError, TypeError):
                scene_id_int = 0

            is_korean_selected = is_korean_scene_selected(scene_id_int) if scene_id_int > 0 else False
            korean_source = get_selection_source(scene_id_int) if scene_id_int > 0 else None

            # 이미지 (선택 시 테두리 표시, 클릭 시 확대)
            if os.path.exists(img["path"]):
                # v1.2: 한글 씬 선택 시 초록색 테두리
                if is_korean_selected:
                    border_color = "#10B981"
                    bg_color = "rgba(16, 185, 129, 0.1)"
                elif is_selected:
                    border_color = "#667eea"
                    bg_color = "rgba(102,126,234,0.1)"
                else:
                    border_color = None
                    bg_color = None

                if border_color:
                    st.markdown(
                        f'<div style="border: 3px solid {border_color}; border-radius: 8px; padding: 2px; background: {bg_color};">',
                        unsafe_allow_html=True
                    )

                # v1.2: 한글 씬 배지 표시
                if is_korean_selected:
                    badge_color = "#10B981" if korean_source == 'auto' else "#3B82F6"
                    badge_text = "🎲" if korean_source == 'auto' else "✋"
                    st.markdown(f"""
                        <div style="
                            background: {badge_color};
                            color: white;
                            padding: 2px 8px;
                            border-radius: 4px;
                            font-size: 11px;
                            display: inline-block;
                            margin-bottom: 4px;
                        ">{badge_text} 한글</div>
                    """, unsafe_allow_html=True)

                render_lightbox_image(img["path"], key=f"gallery_{img_key}")

                if border_color:
                    st.markdown('</div>', unsafe_allow_html=True)

            # 정보 (다중 선택 모드가 아닐 때만 표시)
            if not multi_select:
                type_emoji = {"composited": "🎨", "background": "🏞️", "scene": "🎬"}.get(img.get("type"), "📷")
                st.caption(f"{type_emoji} 씬 {img.get('scene_id', '?')}")

            # 버튼들 (다중 선택 모드가 아닐 때만)
            if not multi_select:
                # v1.2: 5열로 변경 - 한글 씬 토글 버튼 추가
                btn_cols = st.columns(5)

                with btn_cols[0]:
                    # 스토리보드 적용
                    scene_id = img.get("scene_id")
                    if scene_id and str(scene_id).isdigit():
                        if st.button("📋", key=f"apply_gallery_{img_key}", help="스토리보드에 적용"):
                            save_to_storyboard(int(scene_id), img["path"])
                            st.success(f"씬 {scene_id}에 적용!")

                with btn_cols[1]:
                    # 🔍 프롬프트 보기 (v2.0)
                    if st.button("🔍", key=f"prompt_gallery_{img_key}", help="프롬프트 보기"):
                        st.session_state[f"show_prompt_{img_key}"] = not st.session_state.get(f"show_prompt_{img_key}", False)

                with btn_cols[2]:
                    # 다운로드
                    if os.path.exists(img["path"]):
                        with open(img["path"], "rb") as f:
                            st.download_button(
                                "💾",
                                data=f.read(),
                                file_name=img["filename"],
                                key=f"dl_gallery_{img_key}"
                            )

                with btn_cols[3]:
                    # 삭제
                    if st.button("🗑️", key=f"del_gallery_{img_key}"):
                        delete_image(img["path"])
                        clear_gallery_cache()  # ⭐ v2.2: 캐시 무효화
                        st.rerun()

                with btn_cols[4]:
                    # v1.2: 한글 씬 토글 버튼
                    if scene_id_int > 0:
                        if is_korean_selected:
                            # 선택됨 → 제거 버튼
                            if st.button("➖", key=f"korean_rm_{img_key}", help="한글 씬에서 제거"):
                                if remove_manual_scene(scene_id_int):
                                    update_legacy_state()
                                    st.toast(f"씬 {scene_id_int}이(가) 한글 씬에서 제거되었습니다.")
                                    st.rerun()
                        else:
                            # 미선택 → 추가 버튼
                            if st.button("➕", key=f"korean_add_{img_key}", help="한글 씬에 추가"):
                                if add_manual_scene(scene_id_int):
                                    update_legacy_state()
                                    st.toast(f"씬 {scene_id_int}이(가) 한글 씬에 추가되었습니다!")
                                    st.rerun()

                # 🔍 프롬프트 정보 표시 (v2.0)
                if st.session_state.get(f"show_prompt_{img_key}", False):
                    prompt_info = get_image_prompt_info(img["path"])
                    if prompt_info:
                        with st.container():
                            st.markdown("---")
                            prompts = prompt_info.get("prompts", {})
                            style = prompt_info.get("style", {})
                            gen = prompt_info.get("generation", {})

                            # 생성 정보 한 줄
                            api = gen.get('api_provider', 'N/A')
                            model = gen.get('model_name', gen.get('model', 'N/A'))
                            st.caption(f"🔧 {api} | {model}")

                            # 프롬프트 탭
                            prompt_tabs = st.tabs(["최종", "원본", "Negative"])

                            with prompt_tabs[0]:
                                final = prompts.get("final", "")
                                st.text_area(
                                    "최종 프롬프트",
                                    final if final else "(없음)",
                                    height=80,
                                    disabled=True,
                                    label_visibility="collapsed",
                                    key=f"prompt_final_{img_key}"
                                )
                                st.caption(f"📏 {len(final):,}자")

                            with prompt_tabs[1]:
                                original = prompts.get("original", "")
                                st.text_area(
                                    "원본 프롬프트",
                                    original if original else "(없음)",
                                    height=60,
                                    disabled=True,
                                    label_visibility="collapsed",
                                    key=f"prompt_orig_{img_key}"
                                )

                            with prompt_tabs[2]:
                                negative = prompts.get("negative", "")
                                neg_display = negative[:300] + "..." if len(negative) > 300 else negative
                                st.text_area(
                                    "네거티브",
                                    neg_display if neg_display else "(없음)",
                                    height=60,
                                    disabled=True,
                                    label_visibility="collapsed",
                                    key=f"prompt_neg_{img_key}"
                                )
                    else:
                        st.caption("📭 프롬프트 정보 없음 (메타데이터 미저장)")

            st.markdown("---")


# ===================================================================
# 탭 4: 설정
# ===================================================================

def render_settings_tab():
    """⚙️ 설정 탭"""
    st.markdown("## ⚙️ 이미지 생성 설정")

    # 페이지 ID (settings_manager용)
    PAGE_ID = "image_generation"

    # 스타일 설정
    st.markdown("### 🎨 기본 스타일")

    style_manager = get_style_manager(str(project_path))

    # StyleManager에서 배경 스타일 목록 로드
    from utils.style_manager import get_styles_by_segment
    bg_styles = get_styles_by_segment("background")
    style_ids = [s.id for s in bg_styles]
    style_names = {s.id: s.name_ko for s in bg_styles}

    col1, col2 = st.columns(2)

    with col1:
        default_style = st.selectbox(
            "기본 배경 스타일",
            options=style_ids,
            format_func=lambda x: style_names.get(x, x),
            key="default_image_style",
            help="스타일 관리 페이지에서 등록된 배경 스타일"
        )

        # 선택된 스타일 정보 표시
        selected = next((s for s in bg_styles if s.id == default_style), None)
        if selected:
            st.caption(f"💡 {selected.description or '설명 없음'}")

    with col2:
        default_resolution = persistent_selectbox(
            "기본 해상도",
            options=["1280x720", "1920x1080", "1024x576"],
            page=PAGE_ID,
            setting_key="resolution"
        )

    st.markdown("---")

    # API 설정
    st.markdown("### 🔑 API 설정")

    col1, col2 = st.columns(2)

    with col1:
        image_api = persistent_selectbox(
            "이미지 생성 API",
            options=[
                "Together.ai FLUX",
                "Google ImageFX",
                "OpenAI DALL-E",
                "Stability AI",
                "Gemini (Nano Banana)",      # v1.1: Gemini 추가
                "Gemini (Nano Banana Pro)"   # v1.1: Gemini Pro 추가
            ],
            page=PAGE_ID,
            setting_key="api",
            help="🆓 Google ImageFX: 무료 (쿠키 필요)\n💰 Together.ai FLUX: ~20원/장\n💰 OpenAI DALL-E: ~60원/장\n🍌 Gemini Nano Banana: ~15원/장 (레퍼런스 지원)"
        )

    with col2:
        if image_api == "Together.ai FLUX":
            model = persistent_selectbox(
                "모델",
                options=[
                    "black-forest-labs/FLUX.2-dev",
                    "black-forest-labs/FLUX.2-flex",
                    "black-forest-labs/FLUX.2-pro"
                ],
                page=PAGE_ID,
                setting_key="flux_model",
                format_func=lambda x: {
                    "black-forest-labs/FLUX.2-dev": "FLUX.2 Dev (권장, ~20원)",
                    "black-forest-labs/FLUX.2-flex": "FLUX.2 Flex (~40원)",
                    "black-forest-labs/FLUX.2-pro": "FLUX.2 Pro (고품질, ~40원)"
                }.get(x, x)
            )
        elif image_api == "Google ImageFX":
            model = persistent_selectbox(
                "모델",
                options=["IMAGEN_4", "IMAGEN_3_5", "IMAGEN_3_1", "IMAGEN_3"],
                page=PAGE_ID,
                setting_key="imagefx_model",
                format_func=lambda x: {
                    "IMAGEN_4": "Imagen 4 (최신, 무료)",
                    "IMAGEN_3_5": "Imagen 3.5 (무료)",
                    "IMAGEN_3_1": "Imagen 3.1 (무료)",
                    "IMAGEN_3": "Imagen 3.0 (무료)"
                }.get(x, x)
            )
        # v1.1: Gemini 모델 선택
        elif image_api == "Gemini (Nano Banana)":
            model = "gemini_nano_banana"
            st.info("🍌 Nano Banana (~15원/장, 레퍼런스 이미지 지원)")
        elif image_api == "Gemini (Nano Banana Pro)":
            model = "gemini_nano_banana_pro"
            st.info("🍌 Nano Banana Pro (~25원/장, 레퍼런스 이미지 지원)")

    # Google ImageFX 쿠키 설정 (ImageFX 선택 시)
    if image_api == "Google ImageFX":
        _render_imagefx_cookie_settings()

    # v1.1: Gemini API 키 확인
    if "Gemini" in image_api:
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if not gemini_key:
            st.warning("⚠️ GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 API 키를 추가하세요.")

    st.markdown("---")

    # 고급 설정
    st.markdown("### ⚙️ 고급 설정")

    col1, col2 = st.columns(2)

    with col1:
        persistent_checkbox(
            "캐릭터 배경 자동 제거 (rembg)",
            page=PAGE_ID,
            setting_key="rembg_enabled",
            default_value=True
        )
        persistent_checkbox(
            "생성 후 자동 스토리보드 저장",
            page=PAGE_ID,
            setting_key="auto_save_storyboard",
            default_value=False
        )

    with col2:
        persistent_checkbox(
            "생성 로그 저장",
            page=PAGE_ID,
            setting_key="save_generation_log",
            default_value=True
        )
        persistent_number_input(
            "API 호출 간격 (초)",
            page=PAGE_ID,
            setting_key="api_interval",
            min_value=0.5,
            max_value=10.0,
            default_value=1.0,
            step=0.5
        )

    st.markdown("---")

    # 유명인 자동 치환 설정 (ImageFX 전용)
    st.markdown("### 🛡️ 유명인 자동 치환 (ImageFX)")
    st.caption("ImageFX에서 유명인 필터(PROMINENT_PEOPLE_FILTER) 에러 발생 시 AI를 사용하여 자동으로 유명인 이름을 일반적인 설명으로 치환합니다.")

    col1, col2 = st.columns(2)

    with col1:
        enable_sanitizer = persistent_checkbox(
            "🔄 유명인 자동 치환 활성화",
            page=PAGE_ID,
            setting_key="celebrity_replacement",
            default_value=True,
            help="ImageFX에서 유명인 관련 에러 발생 시 AI가 자동으로 프롬프트를 수정하여 재시도합니다."
        )

    with col2:
        # 사용 가능한 AI 모델 목록
        available_models = get_available_sanitizer_models()
        if available_models:
            model_options = list(available_models.keys())
            model_labels = {k: f"{v.name} ({v.provider.value})" for k, v in available_models.items()}

            # 기본값 설정
            default_model = get_recommended_model()
            default_idx = model_options.index(default_model) if default_model in model_options else 0

            sanitizer_model = persistent_selectbox(
                "치환용 AI 모델",
                options=model_options,
                page=PAGE_ID,
                setting_key="celebrity_ai_model",
                default_index=default_idx,
                format_func=lambda x: model_labels.get(x, x),
                disabled=not enable_sanitizer,
                help="프롬프트에서 유명인 이름을 감지하고 치환하는 데 사용할 AI 모델"
            )
        else:
            st.warning("⚠️ 사용 가능한 AI 모델이 없습니다. API 키를 확인하세요.")
            sanitizer_model = None

    if enable_sanitizer and available_models and sanitizer_model:
        selected_model = available_models.get(sanitizer_model)
        if selected_model:
            st.info(f"💡 선택된 모델: **{selected_model.name}** - {selected_model.description}")

    st.markdown("---")

    # 캐시/저장소 관리
    st.markdown("### 🧹 저장소 관리")

    images = get_all_gallery_images()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("총 이미지", f"{len(images)}개")

    with col2:
        # 디스크 사용량
        total_size = sum(
            os.path.getsize(img["path"])
            for img in images
            if os.path.exists(img["path"])
        ) / (1024 * 1024)
        st.metric("디스크 사용량", f"{total_size:.1f} MB")

    with col3:
        if st.button("🗑️ 미사용 이미지 정리"):
            cleanup_unused_images()

    st.markdown("---")

    # v2.2: 메모리 관리 섹션
    st.markdown("### 🧠 메모리 관리")
    st.caption("세션에 저장된 이미지 데이터와 캐시를 정리합니다. 메모리 부족 오류가 발생하면 정리를 실행하세요.")

    # 현재 메모리 상태
    mem_stats = get_session_memory_stats()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("세션 키", f"{mem_stats['total_keys']}개")

    with col2:
        st.metric("이미지 데이터", f"{mem_stats['image_keys']}개")

    with col3:
        st.metric("추정 메모리", f"{mem_stats['estimated_size_mb']:.1f} MB")

    with col4:
        if st.button("🧹 메모리 정리", type="primary", key="memory_cleanup_btn"):
            with st.spinner("메모리 정리 중..."):
                cleaned = cleanup_session_images(force=True)
                gc_count = force_gc()
                st.success(f"✅ 정리 완료: 세션 데이터 {cleaned}개 삭제, GC {gc_count}개 수집")
                time.sleep(0.5)
                st.rerun()

    st.markdown("---")

    # 설정 관리 UI
    render_settings_management_ui(PAGE_ID, "이미지 생성")


# ===================================================================
# 헬퍼 함수 (이미지 생성/합성)
# ===================================================================

def generate_background_image(
    scene_id: int,
    prompt: str,
    style: str,
    width: int,
    height: int,
    api_provider: str = None,
    model: str = None,
    seed: int = None,
    seed_key_prefix: str = None  # v6.5: 시드 잠금 키 프리픽스 (자동 잠금용)
):
    """
    배경 이미지 생성 - StyleManager의 스타일 프롬프트 적용

    Args:
        scene_id: 씬 번호
        prompt: 이미지 프롬프트
        style: 스타일 ID 또는 이름
        width: 이미지 너비
        height: 이미지 높이
        api_provider: API 제공자 (None이면 설정에서 로드)
        model: 모델 ID (None이면 설정에서 로드)
        seed: 시드 값 (None이면 랜덤)
    """
    try:
        from utils.style_manager import get_style_by_id, get_styles_by_segment, build_prompt

        # ==============================
        # API 선택에 따른 클라이언트 초기화 (v2.0 - 설정 버그 수정)
        # ==============================
        # 파라미터가 없으면 설정에서 로드
        if api_provider is None or model is None:
            saved_api, saved_model = get_current_api_settings()
            api_provider = api_provider or saved_api
            model = model or saved_model

        selected_api = api_provider

        if selected_api == "Google ImageFX":
            # ImageFX 클라이언트 사용
            from utils.imagefx_client import ImageFXClient, AspectRatio
            from config.settings import load_imagefx_cookie

            # 쿠키 확인 (session_state > 파일 순서, 동적 로드)
            imagefx_cookie = st.session_state.get("imagefx_cookie", "") or load_imagefx_cookie()
            if not imagefx_cookie:
                st.error("❌ ImageFX 쿠키가 설정되지 않았습니다. API 관리 페이지에서 쿠키를 입력해주세요.")
                return None

            print(f"[배경 생성] ImageFX 쿠키 로드됨 (길이: {len(imagefx_cookie)})")

            client = ImageFXClient(cookie=imagefx_cookie)
            # v2.0: 모델은 파라미터에서 전달됨 (설정에서 이미 로드됨)
            api_name = "Google ImageFX"
            model_info = {"name": f"Imagen {model.replace('IMAGEN_', '').replace('_', '.')}", "price": 0.0}
            use_imagefx = True
            use_gemini = False  # v1.1: Gemini 플래그 초기화

            # 비율 계산
            if width > height:
                aspect_ratio = AspectRatio.LANDSCAPE
            elif height > width:
                aspect_ratio = AspectRatio.PORTRAIT
            else:
                aspect_ratio = AspectRatio.SQUARE

        # v1.1: Gemini 이미지 생성 지원
        elif "Gemini" in selected_api:
            from utils.image_api_manager import get_image_api_manager
            api_manager = get_image_api_manager()

            # Gemini API 키 확인
            if not api_manager.check_api_key(selected_api):
                st.error("❌ GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 API 키를 추가하세요.")
                return None

            # 모델 키 설정
            gemini_model = "gemini_nano_banana" if "Pro" not in selected_api else "gemini_nano_banana_pro"
            api_name = selected_api
            model_info = {"name": gemini_model.replace("_", " ").title(), "price": 0.015 if "Pro" not in selected_api else 0.025}
            use_imagefx = False
            use_gemini = True

            print(f"[배경 생성] Gemini 모델 사용: {gemini_model}")

        else:
            # Together.ai FLUX 클라이언트 사용 (기본값)
            from core.image.together_client import TogetherImageClient, get_model_price_info

            client = TogetherImageClient()
            # v2.0: 모델은 파라미터에서 전달됨 (설정에서 이미 로드됨)
            model_info = get_model_price_info(model)
            api_name = "Together.ai FLUX"
            use_imagefx = False
            use_gemini = False  # v1.1: Gemini 플래그 초기화

        # ==============================
        # 스타일 매니저에서 스타일 로드
        # ⭐ FIX: background 세그먼트에서 먼저 검색 (같은 ID가 여러 세그먼트에 있을 수 있음)
        # ==============================
        style_obj = None

        # 1차: background 세그먼트에서 검색 (ID, name_ko, name으로)
        bg_styles = get_styles_by_segment("background")
        for s in bg_styles:
            if s.id == style or s.name_ko == style or s.name == style:
                style_obj = s
                break

        # 2차: background에서 못 찾으면 전체에서 ID로 검색 (폴백)
        if not style_obj:
            style_obj = get_style_by_id(style)

        # 스타일 프롬프트 적용
        if style_obj:
            # StyleManager의 build_prompt 사용
            # 구조: [prompt_prefix] + [원본 프롬프트] + [prompt_suffix]
            style_prefix = style_obj.prompt_prefix.strip() if style_obj.prompt_prefix else ""
            style_suffix = style_obj.prompt_suffix.strip() if style_obj.prompt_suffix else ""
            negative_prompt = style_obj.negative_prompt.strip() if style_obj.negative_prompt else ""

            # 원본 프롬프트에 배경 공통 태그 추가
            scene_prompt = f"{prompt.strip()}, background scene, no characters, wide shot"

            # 최종 프롬프트 조합: prefix + scene + suffix
            parts = []
            if style_prefix:
                parts.append(style_prefix.rstrip(",").strip())
            parts.append(scene_prompt)
            if style_suffix:
                parts.append(style_suffix.lstrip(",").strip())

            full_prompt = ", ".join(filter(None, parts))

            print(f"[배경 생성] 스타일 '{style_obj.name_ko}' 로드됨 (세그먼트: {style_obj.segment})")
            print(f"[배경 생성] prefix: {style_prefix[:100]}..." if len(style_prefix) > 100 else f"[배경 생성] prefix: {style_prefix or '(없음)'}")
            print(f"[배경 생성] suffix: {style_suffix[:100]}..." if len(style_suffix) > 100 else f"[배경 생성] suffix: {style_suffix or '(없음)'}")
            # ⭐ 네거티브 프롬프트에 signature 키워드 있는지 확인용 로그
            has_signature = "signature" in negative_prompt.lower() if negative_prompt else False
            print(f"[배경 생성] negative_prompt 길이: {len(negative_prompt)}자, signature 키워드: {'✅ 있음' if has_signature else '❌ 없음'}")
        else:
            # 폴백: 스타일 못 찾으면 기본값 사용
            print(f"[배경 생성] ⚠️ 스타일 '{style}' 없음, 기본값 사용")
            full_prompt = f"{prompt}, background scene, no characters, wide shot, high quality, detailed"
            negative_prompt = ""
            style_prefix = ""
            style_suffix = ""

        # 디버그 로그 출력
        print("=" * 60)
        print(f"[배경 생성] 씬 {scene_id}")
        print(f"[배경 생성] 📌 API: {api_name}")
        print(f"[배경 생성] 📌 모델: {model}")
        print(f"[배경 생성] 📌 모델명: {model_info['name']}")
        if model_info['price'] > 0:
            print(f"[배경 생성] 📌 예상 비용: ${model_info['price']:.4f}/장 (~{int(model_info['price'] * 1400)}원)")
        else:
            print(f"[배경 생성] 📌 예상 비용: 무료")
        print(f"[배경 생성] 📌 크기: {width}x{height}")
        print(f"[배경 생성] 적용 스타일: {style}")
        print(f"[배경 생성] 원본 프롬프트: {prompt[:100]}..." if len(prompt) > 100 else f"[배경 생성] 원본 프롬프트: {prompt}")
        print(f"[배경 생성] 최종 프롬프트 길이: {len(full_prompt)}자")
        if negative_prompt:
            print(f"[배경 생성] 네거티브: {negative_prompt[:80]}..." if len(negative_prompt) > 80 else f"[배경 생성] 네거티브: {negative_prompt}")
        print("-" * 60)

        # UI에 프롬프트 표시
        with st.expander("🔍 생성에 사용된 프롬프트", expanded=True):
            # API/모델 정보 표시
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("API", api_name)
            with col2:
                st.metric("모델", model_info['name'])
            with col3:
                if model_info['price'] > 0:
                    st.metric("예상 비용", f"${model_info['price']:.4f} (~{int(model_info['price'] * 1400)}원)")
                else:
                    st.metric("예상 비용", "무료")

            st.markdown("---")
            st.markdown("**원본 (씬 분석):**")
            st.code(prompt, language=None)

            st.markdown(f"**스타일:** {style}")
            if style_obj:
                st.caption(f"스타일 ID: {style_obj.id}")

            if style_prefix:
                st.markdown("**스타일 Prefix:**")
                st.code(style_prefix, language=None)

            if style_suffix:
                st.markdown("**스타일 Suffix:**")
                st.code(style_suffix, language=None)

            st.markdown("**최종 프롬프트:**")
            st.code(full_prompt, language=None)

            if negative_prompt:
                st.markdown("**네거티브 프롬프트:**")
                st.code(negative_prompt, language=None)

        # API에 따른 이미지 생성
        used_seed = seed  # 실제 사용된 시드 추적
        if use_imagefx:
            # ImageFX 클라이언트 사용
            from utils.imagefx_client import ImagenModel, ImageFXError
            model_enum = ImagenModel[model] if model in ImagenModel.__members__ else ImagenModel.DEFAULT

            current_prompt = full_prompt
            max_sanitize_retries = 2
            sanitize_attempt = 0

            while True:
                try:
                    # ⭐ v6.2: 네거티브 프롬프트 전달
                    # ⭐ v6.3: 시드 파라미터 추가 (이미지 일관성 유지)
                    images = client.generate_image(
                        prompt=current_prompt,
                        model=model_enum,
                        aspect_ratio=aspect_ratio,
                        num_images=1,
                        negative_prompt=negative_prompt,  # ⭐ 네거티브 프롬프트 추가!
                        seed=seed  # ⭐ 시드 파라미터
                    )
                    if images and len(images) > 0:
                        img_data = images[0].get_bytes()
                        # 시드 정보 추출 (이미지 메타데이터에서)
                        if hasattr(images[0], 'seed') and images[0].seed:
                            used_seed = images[0].seed
                        break
                    else:
                        raise Exception("ImageFX 이미지 생성 실패: 결과 없음")

                except CookieExpiredError as e:
                    # 쿠키 만료 에러 - 재시도하지 않고 즉시 UI에 알림
                    show_cookie_expired_error_in_result(str(e))
                    st.stop()

                except (ImageFXError, Exception) as e:
                    error_msg = str(e)

                    # 유명인 필터 에러 확인 및 자동 치환
                    enable_sanitizer = st.session_state.get("enable_prominent_people_sanitizer", True)
                    if enable_sanitizer and sanitize_attempt < max_sanitize_retries:
                        if check_prominent_people_error(error_msg):
                            sanitize_attempt += 1
                            st.warning(f"유명인 필터 감지됨. AI로 프롬프트 치환 중... (시도 {sanitize_attempt}/{max_sanitize_retries})")

                            # AI 모델로 프롬프트 치환
                            ai_model = st.session_state.get("sanitizer_ai_model", get_recommended_model())
                            sanitized_prompt, result = sanitize_prompt_for_imagefx(current_prompt, ai_model)

                            if result.was_modified:
                                st.info(f"치환됨: {result.detected_names}")
                                with st.expander("치환 상세 정보"):
                                    st.write("**감지된 이름:**", result.detected_names)
                                    st.write("**치환 매핑:**", result.replacements)
                                    st.write("**원본:**", current_prompt[:200] + "..." if len(current_prompt) > 200 else current_prompt)
                                    st.write("**치환됨:**", sanitized_prompt[:200] + "..." if len(sanitized_prompt) > 200 else sanitized_prompt)

                                current_prompt = sanitized_prompt
                                continue  # 치환된 프롬프트로 재시도
                            else:
                                st.warning("AI가 유명인을 감지하지 못했습니다. 수동으로 프롬프트를 수정해주세요.")
                                raise e
                        else:
                            raise e
                    else:
                        raise e
        elif use_gemini:
            # v1.1: Gemini 이미지 생성 (Nano Banana / Pro)
            from utils.image_api_manager import get_image_api_manager
            api_manager = get_image_api_manager()

            result = api_manager.generate_image(
                prompt=full_prompt,
                api_provider=selected_api,
                model=gemini_model,
                width=width,
                height=height,
                negative_prompt=negative_prompt
            )

            if result.success:
                img_data = result.image_data
                # Gemini는 시드를 반환하지 않음
                used_seed = None
                print(f"[배경 생성] Gemini 이미지 생성 성공: {len(img_data):,} bytes")
            else:
                raise Exception(f"Gemini 이미지 생성 실패: {result.error}")
        else:
            # Together.ai FLUX 클라이언트 사용
            img_data = client.generate_image(
                prompt=full_prompt,
                model=model,
                width=width,
                height=height,
                negative_prompt=negative_prompt  # ⭐ Together.ai도 네거티브 지원
            )

        # 저장
        bg_dir = project_path / "images" / "backgrounds"
        bg_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time() * 1000)
        filename = f"bg_scene_{scene_id:03d}_{timestamp}.png"
        filepath = bg_dir / filename

        with open(filepath, "wb") as f:
            f.write(img_data)

        # 프롬프트 메타데이터 저장 (시드 정보 포함)
        save_image_with_prompt(
            image_path=str(filepath),
            original_prompt=prompt,
            final_prompt=full_prompt,
            negative_prompt=negative_prompt,
            style_id=style_obj.id if style_obj else "",
            style_name=style_obj.name_ko if style_obj else style,
            style_prefix=style_prefix,
            style_suffix=style_suffix,
            api_provider=api_name,
            model=model,
            model_name=model_info['name'],
            width=width,
            height=height,
            scene_id=scene_id,
            extra_info={"seed": used_seed} if used_seed else None
        )

        # 시드 정보 로깅
        if used_seed:
            print(f"[배경 생성] 시드 저장됨: {used_seed}", flush=True)

            # v6.5: 시드 잠금 자동 업데이트 (첫 이미지 시드 잠금용)
            if seed_key_prefix:
                from utils.imagefx_ui_components import update_locked_seed_from_result
                update_locked_seed_from_result(used_seed, key_prefix=seed_key_prefix)
                print(f"[배경 생성] 🔒 세션에 시드 잠금 업데이트: {used_seed} (key={seed_key_prefix})", flush=True)

        # 메타데이터 저장
        set_background_for_scene(scene_id, str(filepath))

        # SceneImageManager로 씬 데이터 업데이트
        update_scene_background(scene_id, str(filepath), str(project_path))

        st.success(f"배경 생성 완료: {filename}")

        # v1.1: 시드 정보 표시
        if used_seed:
            seed_col1, seed_col2 = st.columns([3, 1])
            with seed_col1:
                st.info(f"🔑 **시드:** `{used_seed:,}`")
            with seed_col2:
                # JavaScript 즉시 복사 버튼
                import streamlit.components.v1 as components
                seed_copy_html = f"""
                <button onclick="navigator.clipboard.writeText('{used_seed}').then(function(){{
                    this.innerHTML='✅ 복사됨!';
                    setTimeout(function(){{document.getElementById('seed_copy_btn').innerHTML='📋 시드 복사';}}, 1500);
                }}.bind(this))" id="seed_copy_btn" style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; border: none; border-radius: 6px;
                    padding: 8px 16px; cursor: pointer; font-size: 13px;
                ">📋 시드 복사</button>
                """
                components.html(seed_copy_html, height=45)
            st.caption("💡 동일한 시드를 사용하면 유사한 이미지를 재생성할 수 있습니다.")

        render_lightbox_image(str(filepath), key=f"bg_result_{scene_id}")

        return str(filepath)

    except Exception as e:
        st.error(f"배경 생성 실패: {e}")
        import traceback
        with st.expander("상세 오류"):
            st.code(traceback.format_exc())
        return None


def generate_background_image_with_prompt(
    scene_id: int,
    full_prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    api_provider: str = None,
    model: str = None,
    seed: int = None,
    seed_key_prefix: str = None  # v6.5: 시드 잠금 키 프리픽스 (자동 잠금용)
):
    """
    사용자가 직접 수정한 프롬프트로 배경 이미지 생성

    Args:
        scene_id: 씬 번호
        full_prompt: 최종 프롬프트 (prefix + scene + suffix 이미 조합됨)
        negative_prompt: 네거티브 프롬프트
        width: 이미지 너비
        height: 이미지 높이
        api_provider: API 제공자 (None이면 설정에서 로드)
        model: 모델 ID (None이면 설정에서 로드)
        seed: 시드 값 (None이면 랜덤)
        seed_key_prefix: 시드 잠금 키 프리픽스 (None이면 자동 잠금 안함)
    """
    try:
        # v2.0: 파라미터가 없으면 설정에서 로드
        if api_provider is None or model is None:
            saved_api, saved_model = get_current_api_settings()
            api_provider = api_provider or saved_api
            model = model or saved_model

        selected_api = api_provider

        if selected_api == "Google ImageFX":
            from utils.imagefx_client import ImageFXClient, AspectRatio, ImagenModel, ImageFXError
            from config.settings import load_imagefx_cookie, load_imagefx_auth_token

            auth_token = st.session_state.get("imagefx_auth_token", "") or load_imagefx_auth_token()
            imagefx_cookie = st.session_state.get("imagefx_cookie", "") or load_imagefx_cookie()

            if auth_token:
                client = ImageFXClient(authorization_token=auth_token)
            elif imagefx_cookie:
                client = ImageFXClient(cookie=imagefx_cookie)
            else:
                st.error("❌ ImageFX 인증이 설정되지 않았습니다.")
                return None

            # v2.0: 모델은 파라미터에서 전달됨 (설정에서 이미 로드됨)
            model_enum = ImagenModel[model] if model in ImagenModel.__members__ else ImagenModel.DEFAULT

            if width > height:
                aspect_ratio = AspectRatio.LANDSCAPE
            elif height > width:
                aspect_ratio = AspectRatio.PORTRAIT
            else:
                aspect_ratio = AspectRatio.SQUARE

            used_seed = seed  # 실제 사용된 시드 추적

            # ⭐ v6.2: 네거티브 프롬프트 전달
            # ⭐ v6.3: 시드 파라미터 추가
            images = client.generate_image(
                prompt=full_prompt,
                model=model_enum,
                aspect_ratio=aspect_ratio,
                num_images=1,
                negative_prompt=negative_prompt,  # ⭐ 네거티브 프롬프트 추가!
                seed=seed  # ⭐ 시드 파라미터
            )

            if images and len(images) > 0:
                img_data = images[0].get_bytes()
                # 시드 정보 추출
                if hasattr(images[0], 'seed') and images[0].seed:
                    used_seed = images[0].seed
            else:
                raise Exception("ImageFX 이미지 생성 실패")

        elif "Gemini" in selected_api:
            # v1.1: Gemini 이미지 생성 (Nano Banana / Pro)
            from utils.image_api_manager import get_image_api_manager
            api_manager = get_image_api_manager()

            gemini_model = "gemini_nano_banana" if "Pro" not in selected_api else "gemini_nano_banana_pro"

            result = api_manager.generate_image(
                prompt=full_prompt,
                api_provider=selected_api,
                model=gemini_model,
                width=width,
                height=height,
                negative_prompt=negative_prompt
            )

            if result.success:
                img_data = result.image_data
                used_seed = None  # Gemini는 시드 미지원
                print(f"[배경 생성(수정)] Gemini 이미지 생성 성공: {len(img_data):,} bytes")
            else:
                raise Exception(f"Gemini 이미지 생성 실패: {result.error}")

        else:
            from core.image.together_client import TogetherImageClient

            client = TogetherImageClient()
            # v2.0: 모델은 파라미터에서 전달됨 (설정에서 이미 로드됨)
            used_seed = None  # Together.ai는 시드 미지원

            img_data = client.generate_image(
                prompt=full_prompt,
                model=model,
                width=width,
                height=height,
                negative_prompt=negative_prompt  # ⭐ Together.ai도 네거티브 지원
            )

        # 저장
        bg_dir = project_path / "images" / "backgrounds"
        bg_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time() * 1000)
        filename = f"bg_scene_{scene_id:03d}_{timestamp}.png"
        filepath = bg_dir / filename

        with open(filepath, "wb") as f:
            f.write(img_data)

        # 프롬프트 메타데이터 저장 (시드 정보 포함)
        from core.image.together_client import get_model_price_info
        model_info = get_model_price_info(model) if selected_api != "Google ImageFX" else {"name": f"Imagen {model.replace('IMAGEN_', '').replace('_', '.')}"}
        extra = {"user_modified": True}
        if used_seed:
            extra["seed"] = used_seed
        save_image_with_prompt(
            image_path=str(filepath),
            original_prompt="[User Modified]",
            final_prompt=full_prompt,
            negative_prompt=negative_prompt,
            api_provider=selected_api,
            model=model,
            model_name=model_info.get('name', model),
            width=width,
            height=height,
            scene_id=scene_id,
            extra_info=extra
        )

        set_background_for_scene(scene_id, str(filepath))
        update_scene_background(scene_id, str(filepath), str(project_path))

        # v6.5: 시드 잠금 자동 업데이트
        if used_seed and seed_key_prefix:
            from utils.imagefx_ui_components import update_locked_seed_from_result
            update_locked_seed_from_result(used_seed, key_prefix=seed_key_prefix)
            print(f"[배경 생성(수정)] 🔒 세션에 시드 잠금 업데이트: {used_seed} (key={seed_key_prefix})", flush=True)

        print(f"[배경 생성(수정)] 씬 {scene_id} 완료: {filename}")
        return str(filepath)

    except Exception as e:
        st.error(f"배경 생성 실패: {e}")
        return None


def generate_scene_composite_image_with_prompt(
    scene_id: int,
    final_prompt: str,
    negative_prompt: str,
    width: int = 1280,
    height: int = 720,
    seed: int = None,
    seed_key_prefix: str = None  # v6.5: 시드 잠금 키 프리픽스 (자동 잠금용)
):
    """
    사용자가 직접 수정한 프롬프트로 씬 합성 이미지 생성

    Args:
        scene_id: 씬 번호
        final_prompt: 최종 프롬프트 (이미 조합됨)
        negative_prompt: 네거티브 프롬프트
        width: 이미지 너비
        height: 이미지 높이
        seed: 시드 값 (None이면 랜덤)
        seed_key_prefix: 시드 잠금 키 프리픽스 (None이면 자동 잠금 안함)
    """
    try:
        selected_api = st.session_state.get("image_api", "Together.ai FLUX")

        if selected_api == "Google ImageFX":
            from utils.imagefx_client import ImageFXClient, AspectRatio, ImagenModel
            from config.settings import load_imagefx_cookie, load_imagefx_auth_token

            auth_token = st.session_state.get("imagefx_auth_token", "") or load_imagefx_auth_token()
            imagefx_cookie = st.session_state.get("imagefx_cookie", "") or load_imagefx_cookie()

            if auth_token:
                client = ImageFXClient(authorization_token=auth_token)
            elif imagefx_cookie:
                client = ImageFXClient(cookie=imagefx_cookie)
            else:
                st.error("❌ ImageFX 인증이 설정되지 않았습니다.")
                return None

            model = st.session_state.get("imagefx_model", "IMAGEN_3_5")
            model_enum = ImagenModel[model] if model in ImagenModel.__members__ else ImagenModel.DEFAULT

            if width > height:
                aspect_ratio = AspectRatio.LANDSCAPE
            elif height > width:
                aspect_ratio = AspectRatio.PORTRAIT
            else:
                aspect_ratio = AspectRatio.SQUARE

            used_seed = seed  # 실제 사용된 시드 추적

            # ⭐ v6.2: 네거티브 프롬프트 전달
            # ⭐ v6.3: 시드 파라미터 추가
            images = client.generate_image(
                prompt=final_prompt,
                model=model_enum,
                aspect_ratio=aspect_ratio,
                num_images=1,
                negative_prompt=negative_prompt,  # ⭐ 네거티브 프롬프트 추가!
                seed=seed  # ⭐ 시드 파라미터
            )

            if images and len(images) > 0:
                img_data = images[0].get_bytes()
                # 시드 정보 추출
                if hasattr(images[0], 'seed') and images[0].seed:
                    used_seed = images[0].seed
            else:
                raise Exception("ImageFX 이미지 생성 실패")

        elif "Gemini" in selected_api:
            # v1.1: Gemini 이미지 생성 (Nano Banana / Pro)
            from utils.image_api_manager import get_image_api_manager
            api_manager = get_image_api_manager()

            gemini_model = "gemini_nano_banana" if "Pro" not in selected_api else "gemini_nano_banana_pro"
            model = gemini_model  # 저장용

            result = api_manager.generate_image(
                prompt=final_prompt,
                api_provider=selected_api,
                model=gemini_model,
                width=width,
                height=height,
                negative_prompt=negative_prompt
            )

            if result.success:
                img_data = result.image_data
                used_seed = None  # Gemini는 시드 미지원
                print(f"[씬합성(수정)] Gemini 이미지 생성 성공: {len(img_data):,} bytes")
            else:
                raise Exception(f"Gemini 이미지 생성 실패: {result.error}")

        else:
            from core.image.together_client import TogetherImageClient
            from config.settings import TOGETHER_DEFAULT_MODEL

            client = TogetherImageClient()
            model = st.session_state.get("flux_model") or TOGETHER_DEFAULT_MODEL or "black-forest-labs/FLUX.2-dev"
            used_seed = None  # Together.ai는 시드 미지원

            img_data = client.generate_image(
                prompt=final_prompt,
                model=model,
                width=width,
                height=height,
                negative_prompt=negative_prompt  # ⭐ Together.ai도 네거티브 지원
            )

        # 저장 (합성 이미지 폴더에)
        composite_dir = project_path / "images" / "composited"
        composite_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time() * 1000)
        filename = f"composite_scene_{scene_id:03d}_{timestamp}.png"
        filepath = composite_dir / filename

        with open(filepath, "wb") as f:
            f.write(img_data)

        # 프롬프트 메타데이터 저장 (시드 정보 포함)
        api_name = selected_api
        if selected_api == "Google ImageFX":
            model_name = f"Imagen {model.replace('IMAGEN_', '').replace('_', '.')}"
        else:
            from core.image.together_client import get_model_price_info
            model_info = get_model_price_info(model)
            model_name = model_info.get('name', model)

        extra = {"type": "composite", "user_modified": True}
        if used_seed:
            extra["seed"] = used_seed
        save_image_with_prompt(
            image_path=str(filepath),
            original_prompt="[User Modified Composite]",
            final_prompt=final_prompt,
            negative_prompt=negative_prompt,
            api_provider=api_name,
            model=model,
            model_name=model_name,
            width=width,
            height=height,
            scene_id=scene_id,
            extra_info=extra
        )

        # 메타데이터 업데이트
        set_composited_for_scene(scene_id, str(filepath))

        # v6.5: 시드 잠금 자동 업데이트
        if used_seed and seed_key_prefix:
            from utils.imagefx_ui_components import update_locked_seed_from_result
            update_locked_seed_from_result(used_seed, key_prefix=seed_key_prefix)
            print(f"[씬합성 생성(수정)] 🔒 세션에 시드 잠금 업데이트: {used_seed} (key={seed_key_prefix})", flush=True)

        print(f"[씬합성 생성(수정)] 씬 {scene_id} 완료: {filename}")
        return str(filepath)

    except Exception as e:
        st.error(f"씬 합성 이미지 생성 실패: {e}")
        return None


def generate_scene_composite_image(
    scene_id: int,
    scene_prompt: str,
    composite_style,
    apply_negative: bool = True,
    width: int = 1280,
    height: int = 720,
    seed: int = None,
    seed_key_prefix: str = None  # v6.5: 시드 잠금 키 프리픽스 (자동 잠금용)
):
    """
    씬 합성 이미지 생성 (배경 + 캐릭터 통합 스타일)

    Args:
        scene_id: 씬 번호
        scene_prompt: 씬 이미지 프롬프트
        composite_style: 씬 합성 스타일 Style 객체
        apply_negative: 네거티브 프롬프트 적용 여부
        width: 이미지 너비
        height: 이미지 높이
        seed: 시드 값 (None이면 랜덤)
        seed_key_prefix: 시드 잠금 키 프리픽스 (None이면 자동 잠금 안함)

    Returns:
        생성된 이미지 경로 또는 None
    """
    try:
        from utils.style_manager import build_scene_composite_prompt

        # ==============================
        # 프롬프트 조합
        # ==============================
        prompt_result = build_scene_composite_prompt(
            scene_prompt=scene_prompt,
            style=composite_style,
            include_negative=apply_negative
        )

        full_prompt = prompt_result["positive"]
        negative_prompt = prompt_result["negative"]

        # ==============================
        # API 선택에 따른 클라이언트 초기화
        # ==============================
        selected_api = st.session_state.get("image_api", "Together.ai FLUX")

        if selected_api == "Google ImageFX":
            from utils.imagefx_client import ImageFXClient, AspectRatio, ImagenModel, ImageFXError
            from config.settings import load_imagefx_cookie

            imagefx_cookie = st.session_state.get("imagefx_cookie", "") or load_imagefx_cookie()
            if not imagefx_cookie:
                st.error("❌ ImageFX 쿠키가 설정되지 않았습니다.")
                return None

            client = ImageFXClient(cookie=imagefx_cookie)
            model = st.session_state.get("imagefx_model", "IMAGEN_3_5")
            api_name = "Google ImageFX"
            model_info = {"name": f"Imagen {model.replace('IMAGEN_', '').replace('_', '.')}", "price": 0.0}
            use_imagefx = True
            use_gemini = False  # v1.1: Gemini 플래그 초기화

            if width > height:
                aspect_ratio = AspectRatio.LANDSCAPE
            elif height > width:
                aspect_ratio = AspectRatio.PORTRAIT
            else:
                aspect_ratio = AspectRatio.SQUARE

        elif "Gemini" in selected_api:
            # v1.1: Gemini 이미지 생성 (Nano Banana / Pro)
            from utils.image_api_manager import get_image_api_manager
            api_manager = get_image_api_manager()

            gemini_model = "gemini_nano_banana" if "Pro" not in selected_api else "gemini_nano_banana_pro"
            model = gemini_model
            api_name = selected_api
            model_info = {"name": gemini_model.replace("_", " ").title(), "price": 0.015 if "Pro" not in selected_api else 0.025}
            use_imagefx = False
            use_gemini = True

        else:
            from core.image.together_client import TogetherImageClient, get_model_price_info
            from config.settings import TOGETHER_DEFAULT_MODEL

            client = TogetherImageClient()
            model = st.session_state.get("flux_model") or TOGETHER_DEFAULT_MODEL or "black-forest-labs/FLUX.2-dev"
            model_info = get_model_price_info(model)
            api_name = "Together.ai FLUX"
            use_imagefx = False
            use_gemini = False  # v1.1: Gemini 플래그 초기화

        # ==============================
        # 디버그 로그 출력
        # ==============================
        print("=" * 60)
        print(f"[씬 합성 생성] 씬 {scene_id}")
        print(f"[씬 합성 생성] 📌 API: {api_name}")
        print(f"[씬 합성 생성] 📌 모델: {model}")
        print(f"[씬 합성 생성] 📌 스타일: {composite_style.name_ko}")
        print(f"[씬 합성 생성] 📌 크기: {width}x{height}")
        print(f"[씬 합성 생성] 원본 프롬프트: {scene_prompt[:100]}..." if len(scene_prompt) > 100 else f"[씬 합성 생성] 원본 프롬프트: {scene_prompt}")
        print(f"[씬 합성 생성] 최종 프롬프트 길이: {len(full_prompt)}자")
        if negative_prompt:
            print(f"[씬 합성 생성] 네거티브: {negative_prompt[:80]}..." if len(negative_prompt) > 80 else f"[씬 합성 생성] 네거티브: {negative_prompt}")
        print("-" * 60)

        # UI에 프롬프트 표시
        with st.expander(f"🔍 씬 {scene_id} - 생성에 사용된 프롬프트", expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("API", api_name)
            with col2:
                st.metric("모델", model_info['name'])
            with col3:
                st.metric("스타일", composite_style.name_ko)

            st.markdown("---")
            st.markdown("**원본 씬 프롬프트:**")
            st.code(scene_prompt, language=None)

            st.markdown("**최종 프롬프트:**")
            st.code(full_prompt[:500] + "..." if len(full_prompt) > 500 else full_prompt, language=None)

            if negative_prompt:
                st.markdown("**네거티브 프롬프트:**")
                st.code(negative_prompt, language=None)

        # ==============================
        # 이미지 생성
        # ==============================
        used_seed = seed  # 실제 사용된 시드 추적
        if use_imagefx:
            model_enum = ImagenModel[model] if model in ImagenModel.__members__ else ImagenModel.DEFAULT

            current_prompt = full_prompt
            max_sanitize_retries = 2
            sanitize_attempt = 0

            while True:
                try:
                    # ⭐ v6.2: 네거티브 프롬프트 전달
                    # ⭐ v6.3: 시드 파라미터 추가
                    images = client.generate_image(
                        prompt=current_prompt,
                        model=model_enum,
                        aspect_ratio=aspect_ratio,
                        num_images=1,
                        negative_prompt=negative_prompt,  # ⭐ 네거티브 프롬프트 추가!
                        seed=seed  # ⭐ 시드 파라미터
                    )
                    if images and len(images) > 0:
                        img_data = images[0].get_bytes()
                        # 시드 정보 추출
                        if hasattr(images[0], 'seed') and images[0].seed:
                            used_seed = images[0].seed
                        break
                    else:
                        raise Exception("ImageFX 이미지 생성 실패: 결과 없음")

                except CookieExpiredError as e:
                    show_cookie_expired_error_in_result(str(e))
                    st.stop()

                except (ImageFXError, Exception) as e:
                    error_msg = str(e)
                    enable_sanitizer = st.session_state.get("enable_prominent_people_sanitizer", True)

                    if enable_sanitizer and sanitize_attempt < max_sanitize_retries:
                        if check_prominent_people_error(error_msg):
                            sanitize_attempt += 1
                            st.warning(f"유명인 필터 감지됨. AI로 프롬프트 치환 중... (시도 {sanitize_attempt}/{max_sanitize_retries})")

                            ai_model = st.session_state.get("sanitizer_ai_model", get_recommended_model())
                            sanitized_prompt, result = sanitize_prompt_for_imagefx(current_prompt, ai_model)

                            if result.was_modified:
                                st.info(f"치환됨: {result.detected_names}")
                                current_prompt = sanitized_prompt
                                continue
                            else:
                                st.warning("AI가 유명인을 감지하지 못했습니다.")
                                raise e
                        else:
                            raise e
                    else:
                        raise e
        elif use_gemini:
            # v1.1: Gemini 이미지 생성 (Nano Banana / Pro)
            result = api_manager.generate_image(
                prompt=full_prompt,
                api_provider=selected_api,
                model=model,
                width=width,
                height=height,
                negative_prompt=negative_prompt
            )

            if result.success:
                img_data = result.image_data
                used_seed = None  # Gemini는 시드 미지원
                print(f"[씬 합성 생성] Gemini 이미지 생성 성공: {len(img_data):,} bytes")
            else:
                raise Exception(f"Gemini 이미지 생성 실패: {result.error}")
        else:
            used_seed = None  # Together.ai는 시드 미지원
            img_data = client.generate_image(
                prompt=full_prompt,
                model=model,
                width=width,
                height=height,
                negative_prompt=negative_prompt  # ⭐ Together.ai도 네거티브 지원
            )

        # ==============================
        # 저장 (composited 폴더에 저장)
        # ==============================
        comp_dir = project_path / "images" / "composited"
        comp_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time() * 1000)
        filename = f"composited_scene_{scene_id:03d}_{timestamp}.png"
        filepath = comp_dir / filename

        with open(filepath, "wb") as f:
            f.write(img_data)

        # 프롬프트 메타데이터 저장 (시드 정보 포함)
        extra = {"type": "composite"}
        if used_seed:
            extra["seed"] = used_seed
        save_image_with_prompt(
            image_path=str(filepath),
            original_prompt=scene_prompt,
            final_prompt=full_prompt,
            negative_prompt=negative_prompt,
            style_id=composite_style.id if composite_style else "",
            style_name=composite_style.name_ko if composite_style else "",
            style_prefix=composite_style.prompt_prefix if composite_style else "",
            style_suffix=composite_style.prompt_suffix if composite_style else "",
            api_provider=api_name,
            model=model,
            model_name=model_info['name'],
            width=width,
            height=height,
            scene_id=scene_id,
            extra_info=extra
        )

        # 시드 정보 로깅
        if used_seed:
            print(f"[씬 합성 생성] 시드 저장됨: {used_seed}", flush=True)

            # v6.5: 시드 잠금 자동 업데이트 (첫 이미지 시드 잠금용)
            if seed_key_prefix:
                from utils.imagefx_ui_components import update_locked_seed_from_result
                update_locked_seed_from_result(used_seed, key_prefix=seed_key_prefix)
                print(f"[씬 합성 생성] 🔒 세션에 시드 잠금 업데이트: {used_seed} (key={seed_key_prefix})", flush=True)

        # SceneImageManager로 씬 데이터 업데이트
        update_scene_composite(scene_id, str(filepath), str(project_path))

        st.success(f"씬 합성 이미지 생성 완료: {filename}")

        # v1.1: 시드 정보 표시
        if used_seed:
            seed_col1, seed_col2 = st.columns([3, 1])
            with seed_col1:
                st.info(f"🔑 **시드:** `{used_seed:,}`")
            with seed_col2:
                import streamlit.components.v1 as components
                seed_copy_html = f"""
                <button onclick="navigator.clipboard.writeText('{used_seed}').then(function(){{
                    this.innerHTML='✅ 복사됨!';
                    setTimeout(function(){{document.getElementById('comp_seed_copy_btn').innerHTML='📋 시드 복사';}}, 1500);
                }}.bind(this))" id="comp_seed_copy_btn" style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white; border: none; border-radius: 6px;
                    padding: 8px 16px; cursor: pointer; font-size: 13px;
                ">📋 시드 복사</button>
                """
                components.html(seed_copy_html, height=45)
            st.caption("💡 동일한 시드를 사용하면 유사한 이미지를 재생성할 수 있습니다.")

        render_lightbox_image(str(filepath), key=f"comp_result_{scene_id}")

        return str(filepath)

    except Exception as e:
        st.error(f"씬 합성 이미지 생성 실패: {e}")
        import traceback
        with st.expander("상세 오류"):
            st.code(traceback.format_exc())
        return None


def save_uploaded_background(scene_id: int, uploaded_file):
    """업로드된 배경 저장"""
    bg_dir = project_path / "images" / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time() * 1000)
    filename = f"bg_scene_{scene_id:03d}_uploaded_{timestamp}.png"
    filepath = bg_dir / filename

    with open(filepath, "wb") as f:
        f.write(uploaded_file.getbuffer())

    set_background_for_scene(scene_id, str(filepath))

    # ✅ SceneImageManager로 씬 데이터 업데이트
    update_scene_background(scene_id, str(filepath), str(project_path))

    st.success("배경이 저장되었습니다!")
    st.rerun()


def set_background_for_scene(scene_id: int, filepath: str):
    """씬의 배경 이미지 설정"""
    if "background_images" not in st.session_state:
        st.session_state["background_images"] = {}

    st.session_state["background_images"][str(scene_id)] = {
        "path": filepath,
        "url": filepath
    }

    # JSON 파일에도 저장
    bg_json = project_path / "images" / "backgrounds" / "backgrounds.json"
    bg_json.parent.mkdir(parents=True, exist_ok=True)

    bg_data = st.session_state["background_images"]
    with open(bg_json, "w", encoding="utf-8") as f:
        json.dump(bg_data, f, ensure_ascii=False, indent=2)


def execute_composite(scene_id: int, scene: Dict, remove_bg: bool, use_scene_pose: bool = False) -> Optional[str]:
    """
    합성 실행 - 드래그 편집기/슬라이더 형식 모두 지원

    좌표 형식:
    - 드래그 편집기: x, y (중심 비율 0~1), width, height (캔버스 대비 비율)
    - 슬라이더: x, y (중심 비율 0~1), scale (배율)

    Args:
        scene_id: 씬 ID
        scene: 씬 정보
        remove_bg: 캐릭터 배경 제거 여부
        use_scene_pose: 씬별 포즈 이미지 사용 여부 (캐릭터 관리에서 설정한 포즈)
    """
    try:
        from PIL import Image, ImageOps

        print(f"[Composite] 씬 {scene_id} 합성 시작")
        print(f"[Composite] 포즈 모드: {'씬별 다른 포즈' if use_scene_pose else '단일 포즈'}")

        # 배경 이미지 로드
        bg_data = get_background_for_scene(scene_id)
        if not bg_data:
            st.error("배경 이미지가 없습니다.")
            return None

        bg_path = bg_data.get("path") or bg_data.get("url")
        if not bg_path or not os.path.exists(bg_path):
            st.error("배경 이미지 파일을 찾을 수 없습니다.")
            return None

        background = Image.open(bg_path).convert("RGBA")
        bg_width, bg_height = background.size
        print(f"[Composite] 배경 크기: {bg_width}x{bg_height}")

        # 캐릭터 배치 정보
        char_positions = st.session_state.get(f"char_positions_{scene_id}", {})
        all_characters = st.session_state.get("characters", [])
        ext_characters = st.session_state.get("external_characters", [])
        all_chars_combined = all_characters + ext_characters

        # 커스텀 캐릭터 목록 사용 (씬별 추가/제거 반영)
        custom_chars_key = f"scene_chars_custom_{scene_id}"
        scene_characters = st.session_state.get(custom_chars_key, scene.get("characters", []))

        print(f"[Composite] 씬 캐릭터: {scene_characters}")
        print(f"[Composite] 저장된 위치: {list(char_positions.keys())}")

        # 캐릭터 레이어 준비 (z_index 순서로 정렬)
        char_layers = []
        for idx, char_name in enumerate(scene_characters):
            char_info = next((c for c in all_chars_combined if c.get("name") == char_name), None)

            if char_info:
                # 씬별 포즈 이미지 선택 (use_scene_pose가 True일 때)
                if use_scene_pose:
                    char_image_path = get_character_image_for_scene_from_session(
                        character_info=char_info,
                        scene_id=scene_id,
                        use_scene_pose=True
                    )
                else:
                    char_image_path = char_info.get("image_path") or char_info.get("image_url")

                if char_image_path and os.path.exists(char_image_path):
                    # 기본 위치 (캐릭터가 여러 개일 때 분산 배치)
                    default_x = 0.3 + (idx * 0.4 / max(1, len(scene_characters) - 1)) if len(scene_characters) > 1 else 0.5

                    pos = char_positions.get(char_name, {
                        "x": default_x,
                        "y": 0.7,
                        "scale": 1.0,
                        "flip_x": False,
                        "z_index": idx + 1
                    })

                    # 포즈 정보 로깅
                    if use_scene_pose:
                        scene_poses = char_info.get("scene_poses", {})
                        pose_info = scene_poses.get(str(scene_id), {})
                        pose_name = pose_info.get("pose", "default")
                        print(f"[Composite] ✅ '{char_name}': {pose_name} 포즈 적용")
                        print(f"[Composite]    이미지: {os.path.basename(char_image_path)}")

                    char_layers.append({
                        "name": char_name,
                        "image_path": char_image_path,
                        "pos": pos,
                        "z_index": pos.get("z_index", idx + 1)
                    })

        # z_index 순으로 정렬 (낮은 것부터 먼저 합성)
        char_layers.sort(key=lambda x: x["z_index"])

        # BackgroundRemover 초기화 (배경 제거 시)
        bg_remover = None
        if remove_bg:
            try:
                from utils.background_remover import get_background_remover
                bg_remover = get_background_remover()
            except ImportError as e:
                print(f"[Composite] BackgroundRemover 로드 실패: {e}")
                try:
                    import rembg
                except ImportError:
                    st.warning("⚠️ rembg 라이브러리가 설치되지 않아 배경 제거를 건너뜁니다.")
                    remove_bg = False

        # 캐릭터 레이어 합성
        for layer in char_layers:
            char_name = layer["name"]
            char_image_path = layer["image_path"]
            pos = layer["pos"]

            print(f"[Composite] 캐릭터 '{char_name}' 처리 중...")
            print(f"[Composite]   위치 데이터: {pos}")

            try:
                # 배경 제거 적용 (개선된 방식: 내부 구멍 보정 포함)
                if remove_bg and bg_remover:
                    # fix_holes=True로 캐릭터 내부 구멍 문제 해결
                    transparent_path = bg_remover.remove_background(
                        char_image_path,
                        fix_holes=True,
                        alpha_matting=True
                    )
                    if transparent_path:
                        char_img = Image.open(transparent_path).convert("RGBA")
                    else:
                        char_img = Image.open(char_image_path).convert("RGBA")
                elif remove_bg:
                    char_img = Image.open(char_image_path).convert("RGBA")
                    try:
                        from rembg import remove
                        char_img = remove(char_img)
                    except Exception as e:
                        st.warning(f"'{char_name}' 배경 제거 실패: {e}")
                else:
                    char_img = Image.open(char_image_path).convert("RGBA")

                # 좌우 반전 적용
                if pos.get("flip_x", False):
                    char_img = ImageOps.mirror(char_img)

                # 캐릭터 크기 계산 - 드래그 편집기 형식과 슬라이더 형식 모두 지원
                if "width" in pos and "height" in pos:
                    # 드래그 편집기 형식: width/height는 배경 이미지 대비 비율
                    # 캔버스와 배경 이미지의 비율은 동일하다고 가정 (16:9)
                    new_width = int(pos["width"] * bg_width)
                    new_height = int(pos["height"] * bg_height)
                    print(f"[Composite]   드래그 형식: width={pos['width']:.3f}, height={pos['height']:.3f}")
                else:
                    # 슬라이더 형식: scale은 기본 크기(배경 높이의 40%) 대비 배율
                    scale = pos.get("scale", 1.0)
                    new_height = int(bg_height * 0.4 * scale)
                    aspect = char_img.width / char_img.height if char_img.height > 0 else 1
                    new_width = int(new_height * aspect)
                    print(f"[Composite]   슬라이더 형식: scale={scale:.2f}")

                # 최소/최대 크기 제한
                new_width = max(50, min(new_width, bg_width))
                new_height = max(50, min(new_height, bg_height))

                char_img = char_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                print(f"[Composite]   최종 크기: {new_width}x{new_height}")

                # 위치 계산 (x, y는 캐릭터 중심의 비율 좌표)
                center_x = pos.get("x", 0.5) * bg_width
                center_y = pos.get("y", 0.7) * bg_height

                # 좌상단 좌표 계산 (paste는 좌상단 기준)
                paste_x = int(center_x - new_width / 2)
                paste_y = int(center_y - new_height / 2)

                print(f"[Composite]   중심: ({center_x:.0f}, {center_y:.0f})")
                print(f"[Composite]   좌상단: ({paste_x}, {paste_y})")

                # 경계 체크 (일부가 화면 밖으로 나가도 허용)
                paste_x = max(-new_width + 10, min(paste_x, bg_width - 10))
                paste_y = max(-new_height + 10, min(paste_y, bg_height - 10))

                # 합성
                background.paste(char_img, (paste_x, paste_y), char_img)
                print(f"[Composite]   ✅ 합성 완료")

            except Exception as e:
                st.warning(f"'{char_name}' 합성 실패: {e}")
                continue

        # 저장
        comp_dir = project_path / "images" / "composited"
        comp_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time())
        filename = f"scene_{scene_id:03d}_composited_{timestamp}.png"
        filepath = comp_dir / filename

        background.save(filepath, "PNG")

        # ✅ SceneImageManager로 씬 데이터 업데이트
        update_scene_composite(scene_id, str(filepath), str(project_path))

        print(f"[Composite] ✅ 씬 {scene_id} 합성 저장: {filename}")

        return str(filepath)

    except Exception as e:
        st.error(f"합성 실패: {e}")
        import traceback
        with st.expander("상세 오류"):
            st.code(traceback.format_exc())
        return None


def execute_representative_character_composite(
    scene_id: int,
    scene: Dict,
    remove_bg: bool = True
) -> Optional[str]:
    """
    대표 캐릭터 합성 실행

    대표 캐릭터 관리에서 생성한 씬별 액션 이미지를 배경에 합성합니다.

    Args:
        scene_id: 씬 ID
        scene: 씬 정보
        remove_bg: 캐릭터 배경 제거 여부
    """
    try:
        from PIL import Image, ImageOps

        print(f"[RepCharComposite] 씬 {scene_id} 대표 캐릭터 합성 시작")

        # 배경 이미지 로드
        bg_data = get_background_for_scene(scene_id)
        if not bg_data:
            st.error("배경 이미지가 없습니다.")
            return None

        bg_path = bg_data.get("path") or bg_data.get("url")
        if not bg_path or not os.path.exists(bg_path):
            st.error("배경 이미지 파일을 찾을 수 없습니다.")
            return None

        background = Image.open(bg_path).convert("RGBA")
        bg_width, bg_height = background.size
        print(f"[RepCharComposite] 배경 크기: {bg_width}x{bg_height}")

        # 대표 캐릭터 액션 이미지 가져오기
        char_image_path = get_representative_character_image_for_scene(scene_id)

        if not char_image_path:
            st.warning(f"씬 {scene_id}의 대표 캐릭터 액션 이미지가 없습니다. 캐릭터 관리에서 생성하세요.")
            return None

        if not os.path.exists(char_image_path):
            st.warning(f"대표 캐릭터 이미지 파일을 찾을 수 없습니다: {char_image_path}")
            return None

        print(f"[RepCharComposite] 캐릭터 이미지: {os.path.basename(char_image_path)}")

        # 캐릭터 이미지 로드 및 배경 제거
        char_img = Image.open(char_image_path).convert("RGBA")

        if remove_bg:
            try:
                from utils.background_remover import get_background_remover
                bg_remover = get_background_remover()
                transparent_path = bg_remover.remove_background(
                    char_image_path,
                    fix_holes=True,
                    alpha_matting=True
                )
                if transparent_path:
                    char_img = Image.open(transparent_path).convert("RGBA")
            except Exception as e:
                print(f"[RepCharComposite] 배경 제거 실패, rembg 시도: {e}")
                try:
                    from rembg import remove
                    char_img = remove(char_img)
                except Exception as e2:
                    st.warning(f"배경 제거 실패: {e2}")

        # 캐릭터 크기 조정 (배경의 50% 높이로)
        char_width, char_height = char_img.size
        target_height = int(bg_height * 0.5)
        scale_ratio = target_height / char_height
        new_width = int(char_width * scale_ratio)
        new_height = target_height

        char_img = char_img.resize((new_width, new_height), Image.LANCZOS)

        # 중앙 하단에 배치 (기본 위치)
        x = (bg_width - new_width) // 2
        y = bg_height - new_height - int(bg_height * 0.05)  # 하단에서 5% 여백

        # 합성
        background.paste(char_img, (x, y), char_img)
        print(f"[RepCharComposite] 합성 위치: ({x}, {y}), 크기: {new_width}x{new_height}")

        # 저장
        comp_dir = project_path / "images" / "composited"
        comp_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time())
        filename = f"scene_{scene_id:03d}_rep_char_{timestamp}.png"
        filepath = comp_dir / filename

        background.save(filepath, "PNG")

        # SceneImageManager로 씬 데이터 업데이트
        update_scene_composite(scene_id, str(filepath), str(project_path))

        print(f"[RepCharComposite] ✅ 씬 {scene_id} 대표 캐릭터 합성 저장: {filename}")
        st.success(f"✅ 씬 {scene_id} 대표 캐릭터 합성 완료")

        return str(filepath)

    except Exception as e:
        st.error(f"대표 캐릭터 합성 실패: {e}")
        import traceback
        with st.expander("상세 오류"):
            st.code(traceback.format_exc())
        return None


def cleanup_unused_images():
    """미사용 이미지 정리"""
    storyboard = st.session_state.get("storyboard_images", {})
    used_paths = set(storyboard.values())

    images = get_all_gallery_images()
    deleted_count = 0

    # 합성 이미지만 정리 (배경은 유지)
    for img in images:
        if img.get("type") == "composited" and img["path"] not in used_paths:
            # 씬당 최신 1개는 유지
            scene_id = img.get("scene_id")
            scene_images = [i for i in images if i.get("scene_id") == scene_id and i.get("type") == "composited"]

            if len(scene_images) > 1:
                # 가장 최신이 아니면 삭제
                scene_images.sort(key=lambda x: x["created"], reverse=True)
                if img["path"] != scene_images[0]["path"]:
                    delete_image(img["path"])
                    deleted_count += 1

    if deleted_count > 0:
        clear_gallery_cache()  # ⭐ v2.2: 캐시 무효화
    st.success(f"✅ {deleted_count}개 미사용 이미지 삭제됨")


# ===================================================================
# 인포그래픽 탭 렌더링
# ===================================================================

def render_infographic_tab():
    """인포그래픽용 이미지 생성 탭"""

    st.markdown("### 📊 인포그래픽용 이미지 생성")
    st.caption("가운데를 비워두고 모서리/가장자리에 요소를 배치한 이미지를 생성합니다.")

    # ✅ v2.0: API/모델 선택 UI (탭 상단에 배치)
    infographic_api, infographic_model = render_api_selector(
        key_prefix="infographic",
        show_in_expander=True,
        expander_default_open=False,
        show_save_button=True
    )

    # 설명
    with st.expander("💡 인포그래픽용 이미지란?", expanded=False):
        st.markdown("""
        **인포그래픽용 이미지**는 텍스트나 그래프와 합성할 때 사용합니다.

        - 가운데가 비어 있어 텍스트/정보를 배치하기 좋습니다
        - 모서리/가장자리에 장식 요소가 있어 시각적으로 풍부합니다
        - 프레젠테이션, 유튜브 썸네일, 인포그래픽 등에 활용

        ```
        일반 이미지:           인포그래픽용:
        ┌─────────────┐       ┌─────────────┐
        │  [메인 요소] │       │[A]       [B]│
        │   중앙 배치  │       │             │
        │             │       │   (비움)    │
        └─────────────┘       │[C]       [D]│
                              └─────────────┘
        ```
        """)

    # 씬 데이터 확인
    scenes = st.session_state.get("scenes", [])
    if not scenes:
        st.warning("씬이 없습니다. 먼저 씬 분석을 실행하세요.")
        return

    # 서브탭
    sub_tabs = st.tabs(["🎨 개별 생성", "🚀 일괄 생성", "🖼️ 갤러리"])

    with sub_tabs[0]:
        _render_infographic_single_generation(scenes)

    with sub_tabs[1]:
        _render_infographic_batch_generation(scenes)

    with sub_tabs[2]:
        _render_infographic_gallery()


def _render_infographic_single_generation(scenes: List[Dict]):
    """인포그래픽 개별 생성"""

    from utils.infographic_image_generator import (
        InfographicImageGenerator,
        get_available_layouts,
        get_layout_by_id,
        get_layout_preview_html
    )

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("#### 씬 선택")

        # 씬 선택
        scene_options = {
            f"씬 {s.get('scene_id', i+1)}: {s.get('title', '')[:30]}": s.get('scene_id', i+1)
            for i, s in enumerate(scenes)
        }
        selected_scene_name = st.selectbox(
            "씬",
            list(scene_options.keys()),
            key="infographic_scene_select"
        )
        selected_scene_id = scene_options[selected_scene_name]
        selected_scene = next((s for s in scenes if s.get('scene_id') == selected_scene_id), scenes[0])

        # 프롬프트
        base_prompt = (
            selected_scene.get("image_prompt_en", "") or
            selected_scene.get("image_prompt", "") or
            selected_scene.get("prompts", {}).get("image_prompt_en", "") or
            selected_scene.get("description", "")
        )

        st.markdown("#### 기본 프롬프트")
        edit_prompt = st.text_area(
            "프롬프트 (편집 가능)",
            value=base_prompt,
            height=100,
            key="infographic_prompt"
        )

    with col_right:
        st.markdown("#### 레이아웃 선택")

        # 레이아웃 선택
        layouts = get_available_layouts()
        layout_options = {f"{l['icon']} {l['name']}": l['id'] for l in layouts}

        selected_layout_name = st.selectbox(
            "레이아웃",
            list(layout_options.keys()),
            key="infographic_layout_select"
        )
        selected_layout_id = layout_options[selected_layout_name]
        selected_layout = get_layout_by_id(selected_layout_id)

        # 레이아웃 미리보기
        st.markdown("**미리보기:**")
        preview_html = get_layout_preview_html(selected_layout_id)
        st.markdown(preview_html, unsafe_allow_html=True)

        # 레이아웃 설명
        layout_info = next((l for l in layouts if l['id'] == selected_layout_id), None)
        if layout_info:
            st.caption(layout_info['description'])

    st.markdown("---")

    # 스타일 선택
    st.markdown("#### 스타일")
    style_manager = get_style_manager(str(project_path))
    infographic_styles = style_manager.get_styles_by_segment("infographic")

    if infographic_styles:
        style_options = {f"{s.name_ko} ({s.name})": s for s in infographic_styles}
        selected_style_name = st.selectbox(
            "인포그래픽 스타일",
            list(style_options.keys()),
            key="infographic_style_select"
        )
        selected_style = style_options[selected_style_name]
        style_dict = {
            "prompt_prefix": selected_style.prompt_prefix,
            "prompt_suffix": selected_style.prompt_suffix,
            "negative_prompt": selected_style.negative_prompt
        }

        with st.expander("스타일 상세"):
            st.markdown(f"**Prefix:** {selected_style.prompt_prefix}")
            st.markdown(f"**Suffix:** {selected_style.prompt_suffix}")
            if selected_style.negative_prompt:
                st.markdown(f"**Negative:** {selected_style.negative_prompt}")
    else:
        st.info("인포그래픽 스타일이 없습니다. '스타일 관리' 페이지에서 추가하세요.")
        style_dict = None

    # 생성 옵션
    col_a, col_b = st.columns(2)
    with col_a:
        width = st.selectbox("너비", [1024, 1280, 1536, 1920], index=1, key="infographic_width")
    with col_b:
        height = st.selectbox("높이", [576, 720, 864, 1080], index=1, key="infographic_height")

    # v2.0: 세션에서 선택된 API 가져와서 infographic API 형식으로 변환
    selected_api = st.session_state.get("_infographic_api", "Together.ai FLUX")
    if selected_api == "Google ImageFX":
        api_type = "imagefx"
    else:
        api_type = "together"

    st.markdown("---")

    # 생성 버튼
    if st.button("🎨 인포그래픽 이미지 생성", type="primary", key="generate_infographic"):
        with st.spinner("인포그래픽용 이미지 생성 중..."):
            try:
                generator = InfographicImageGenerator(str(project_path))

                result_path = generator.generate_image(
                    scene_id=selected_scene_id,
                    prompt=edit_prompt,
                    layout=selected_layout,
                    style=style_dict,
                    api_type=api_type,
                    width=width,
                    height=height
                )

                if result_path and os.path.exists(result_path):
                    st.success(f"✅ 생성 완료!")

                    # 이미지 표시
                    clickable_image(result_path, caption=f"씬 {selected_scene_id} - {selected_layout_name}")

                    # 세션에 저장
                    if "infographic_images" not in st.session_state:
                        st.session_state["infographic_images"] = {}
                    st.session_state["infographic_images"][str(selected_scene_id)] = result_path

                else:
                    st.error("이미지 생성에 실패했습니다.")

            except Exception as e:
                st.error(f"오류: {e}")
                import traceback
                with st.expander("상세 오류"):
                    st.code(traceback.format_exc())


def _render_infographic_batch_generation(scenes: List[Dict]):
    """인포그래픽 일괄 생성"""

    from utils.infographic_image_generator import (
        InfographicImageGenerator,
        get_available_layouts,
        get_layout_by_id,
        get_layout_preview_html
    )

    st.markdown("#### 일괄 생성 설정")

    col1, col2 = st.columns(2)

    with col1:
        # 레이아웃 선택
        layouts = get_available_layouts()
        layout_options = {f"{l['icon']} {l['name']}": l['id'] for l in layouts}

        selected_layout_name = st.selectbox(
            "레이아웃 (전체 씬에 적용)",
            list(layout_options.keys()),
            key="batch_infographic_layout"
        )
        selected_layout_id = layout_options[selected_layout_name]
        selected_layout = get_layout_by_id(selected_layout_id)

        # 미리보기
        preview_html = get_layout_preview_html(selected_layout_id)
        st.markdown(preview_html, unsafe_allow_html=True)

    with col2:
        # 스타일 선택
        style_manager = get_style_manager(str(project_path))
        infographic_styles = style_manager.get_styles_by_segment("infographic")

        if infographic_styles:
            style_options = {f"{s.name_ko}": s for s in infographic_styles}
            selected_style_name = st.selectbox(
                "스타일",
                list(style_options.keys()),
                key="batch_infographic_style"
            )
            selected_style = style_options[selected_style_name]
            style_dict = {
                "prompt_prefix": selected_style.prompt_prefix,
                "prompt_suffix": selected_style.prompt_suffix,
                "negative_prompt": selected_style.negative_prompt
            }
        else:
            style_dict = None
            st.info("스타일 없음")

        # v2.0: 세션에서 선택된 API 가져와서 infographic API 형식으로 변환
        selected_api = st.session_state.get("_infographic_api", "Together.ai FLUX")
        if selected_api == "Google ImageFX":
            api_type = "imagefx"
        else:
            api_type = "together"

        st.caption(f"💡 API: {selected_api} → {api_type}")

    # 씬 목록
    st.markdown("---")
    st.markdown(f"#### 대상 씬 ({len(scenes)}개)")

    for scene in scenes[:5]:  # 미리보기는 5개만
        scene_id = scene.get("scene_id", 0)
        title = scene.get("title", "")[:40]
        st.caption(f"• 씬 {scene_id}: {title}")

    if len(scenes) > 5:
        st.caption(f"... 외 {len(scenes) - 5}개")

    st.markdown("---")

    # 일괄 생성 버튼
    if st.button("🚀 전체 씬 인포그래픽 생성", type="primary", key="batch_generate_infographic"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        def on_progress(current, total, message):
            progress_bar.progress(current / total)
            status_text.text(message)

        with st.spinner("일괄 생성 중..."):
            try:
                generator = InfographicImageGenerator(str(project_path))

                results = generator.batch_generate(
                    scenes=scenes,
                    layout=selected_layout,
                    style=style_dict,
                    api_type=api_type,
                    on_progress=on_progress
                )

                progress_bar.progress(1.0)
                status_text.empty()

                if results:
                    st.success(f"✅ {len(results)}/{len(scenes)}개 씬 생성 완료!")

                    # 세션에 저장
                    if "infographic_images" not in st.session_state:
                        st.session_state["infographic_images"] = {}

                    for scene_id, image_path in results.items():
                        st.session_state["infographic_images"][str(scene_id)] = image_path

                    # 결과 미리보기
                    st.markdown("#### 생성 결과")
                    cols = st.columns(3)
                    for idx, (scene_id, image_path) in enumerate(list(results.items())[:6]):
                        with cols[idx % 3]:
                            if os.path.exists(image_path):
                                clickable_image(image_path, caption=f"씬 {scene_id}")

                else:
                    st.warning("생성된 이미지가 없습니다.")

            except Exception as e:
                st.error(f"일괄 생성 오류: {e}")
                import traceback
                with st.expander("상세 오류"):
                    st.code(traceback.format_exc())


def _render_infographic_gallery():
    """인포그래픽 이미지 갤러리"""

    st.markdown("#### 생성된 인포그래픽 이미지")

    # 저장된 이미지 조회
    infographic_dir = project_path / "images" / "infographic"

    if not infographic_dir.exists():
        st.info("아직 생성된 인포그래픽 이미지가 없습니다.")
        return

    image_files = list(infographic_dir.glob("*.png"))

    if not image_files:
        st.info("아직 생성된 인포그래픽 이미지가 없습니다.")
        return

    # 최신순 정렬
    image_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    st.caption(f"총 {len(image_files)}개 이미지")

    # 그리드 표시
    cols = st.columns(3)

    for idx, img_path in enumerate(image_files):
        with cols[idx % 3]:
            with st.container(border=True):
                clickable_image(str(img_path), caption="")

                # 파일 정보
                filename = img_path.name
                st.caption(filename[:30] + "..." if len(filename) > 30 else filename)

                # 삭제 버튼
                if st.button("🗑️", key=f"del_infographic_{idx}", help="삭제"):
                    try:
                        os.remove(img_path)
                        clear_gallery_cache()  # ⭐ v2.2: 캐시 무효화
                        st.rerun()
                    except Exception as e:
                        st.error(f"삭제 실패: {e}")


# ===================================================================
# 메인
# ===================================================================

# 데이터 동기화
sync_all_data()

# 헤더
st.title("🎨 6단계: 이미지 생성")
st.caption(f"프로젝트: {project_path.name}")

# ImageFX 쿠키 갱신 모달 (활성화된 경우 표시)
show_cookie_renewal_modal()

# ImageFX 쿠키 상태 배너 (만료/미설정 시 표시)
show_cookie_status_banner()

# API 키 확인
if not require_api_key("TOGETHER_API_KEY", "Together.ai API"):
    st.stop()

st.divider()

# 탭 구성
tabs = st.tabs([
    "🎬 씬별 생성",
    "🚀 일괄 생성",
    "📊 인포그래픽",
    "🖼️ 갤러리",
    "⚙️ 설정"
])

with tabs[0]:
    render_scene_editor_tab()

with tabs[1]:
    render_batch_generation_tab()

with tabs[2]:
    render_infographic_tab()

with tabs[3]:
    render_gallery_tab()

with tabs[4]:
    render_settings_tab()

# 푸터
st.divider()
col1, col2 = st.columns(2)
with col1:
    st.page_link("pages/7_📦_Vrew_Export.py", label="📦 7단계: Vrew Export", icon="➡️")
with col2:
    st.page_link("pages/8_📋_스토리보드.py", label="📋 8단계: 스토리보드", icon="➡️")
