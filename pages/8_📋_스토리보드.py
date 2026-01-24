"""
8단계: 스토리보드

씬별로 이미지 + 스크립트 + TTS를 한눈에 보고 편집
+ 인포그래픽 통합 지원
"""
import streamlit as st
import json
import re
from pathlib import Path
from datetime import datetime
import sys
import os

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    get_current_project_config,
    render_project_sidebar
)
from utils.api_helper import show_api_status_sidebar
from utils.image_scene_matcher import ImageSceneMatcher, auto_sync_images_to_storyboard
from components.image_viewer import render_lightbox_container, render_lightbox_image
# 확대 + 프롬프트 뷰어 (st.dialog 기반)
from utils.image_viewer import (
    render_clickable_image,
    render_image_card_with_zoom,
    ImagePromptManager
)
from utils.scene_selector import SceneSelector
from utils.storyboard_downloader import StoryboardDownloader

# ⭐ v3.18: 스토리보드 필터 유틸리티 (복합 필터, 프리셋 지원)
try:
    from utils.storyboard_filter import (
        get_bundle_map,
        get_bundle_representative_ids,
        has_korean_text,
        get_korean_text_scene_ids,
        get_no_image_scene_ids,
        get_no_video_scene_ids,
        get_not_generated_scene_ids,
        apply_filters,
        apply_complex_filters,
        get_filter_summary,
        get_extended_filter_summary,
        get_scene_tags_only,
        apply_preset_filter,
        get_filter_presets,
        get_filter_info,
        get_active_filter_labels,
        FILTER_PRESETS,
        FILTER_INFO
    )
    STORYBOARD_FILTER_AVAILABLE = True
except ImportError:
    STORYBOARD_FILTER_AVAILABLE = False

# ⭐ v3.25: 씬 타입 필터 UI (Flow 1/2/3)
# ⭐ v3.26: 파이프라인 워크플로우 통합
try:
    from utils.scene_type_ui import (
        is_scene_type_available,
        init_scene_type_for_project,
        render_scene_type_expander,
        render_combined_workflow_expander,
        render_scene_card_type_badge,
        execute_character_composite,
        sync_scene_types_from_data,
        is_pipeline_available,
        get_pipeline_summary,
        SCENE_TYPE_UI_AVAILABLE,
        PIPELINE_UI_AVAILABLE
    )
except ImportError:
    SCENE_TYPE_UI_AVAILABLE = False
    PIPELINE_UI_AVAILABLE = False

# 이미지 캐시 관리 (MediaFileStorageError 방지)
try:
    from utils.image_cache import ImageCache, display_image_safe, refresh_session_images
    IMAGE_CACHE_AVAILABLE = True
except ImportError:
    IMAGE_CACHE_AVAILABLE = False

# 이미지 프롬프트 메타데이터
try:
    from utils.image_prompt_metadata import (
        get_image_prompt_info,
        render_prompt_info_expander,
        has_prompt_metadata
    )
    PROMPT_METADATA_AVAILABLE = True
except ImportError:
    PROMPT_METADATA_AVAILABLE = False

# 배치 비디오 업로드 (v1.1)
try:
    from utils.batch_video_upload import (
        analyze_batch_video_upload,
        quick_analyze_batch_video_upload,
        get_batch_video_stats,
        apply_batch_videos,
        apply_batch_videos_direct,
        get_existing_videos,
        get_scene_media_info
    )
    BATCH_VIDEO_AVAILABLE = True
except ImportError:
    BATCH_VIDEO_AVAILABLE = False

# 실사 이미지 관리 (v1.0)
try:
    from utils.real_image_manager import (
        quick_analyze_real_images,
        get_real_image_stats,
        apply_real_images,
        save_single_real_image,
        restore_ai_image,
        get_scene_image_status,
        get_existing_ai_images
    )
    REAL_IMAGE_MANAGER_AVAILABLE = True
except ImportError:
    REAL_IMAGE_MANAGER_AVAILABLE = False

# AI 씬-이미지 매핑 파서 (v1.0)
try:
    from utils.image_mapping_parser import (
        ImageMappingParser,
        parse_ai_mapping,
        generate_mapping_template,
        get_image_folder_listing
    )
    AI_MAPPING_PARSER_AVAILABLE = True
except ImportError:
    AI_MAPPING_PARSER_AVAILABLE = False

# 실사 이미지 합성 모듈 (v1.1)
try:
    from utils.image_composer import (
        ImageComposer,
        IMAGE_SIZE_PRESETS,
        batch_compose_real_images,
        compose_real_image_scene,
        hex_to_rgb
    )
    IMAGE_COMPOSER_AVAILABLE = True
except ImportError:
    IMAGE_COMPOSER_AVAILABLE = False

# 나노바나나 이미지 대체 (v1.0)
try:
    from components.nano_banana_replacer import render_nano_banana_replacer
    from utils.gemini_image_generator import check_gemini_api_key
    NANO_BANANA_AVAILABLE = True
except ImportError:
    NANO_BANANA_AVAILABLE = False

# 나노바나나 배경+캐릭터 합성 (v1.0)
# v3.34: 캐릭터 자동 연동 함수 추가
try:
    from components.nano_banana_composite import (
        render_nano_banana_composite,
        auto_link_characters_to_scenes,
        get_auto_linked_character_count
    )
    NANO_COMPOSITE_AVAILABLE = True
except ImportError:
    NANO_COMPOSITE_AVAILABLE = False
    auto_link_characters_to_scenes = None
    get_auto_linked_character_count = None

# 타임라인 뷰 합성 유틸리티 (v1.0)
try:
    from utils.timeline_composite import (
        get_latest_scene_image,
        get_existing_scene_background,
        create_composite_realshot,
        replace_bundle_scenes,
        extract_video_thumbnail,
        save_realshot_file,
        DEFAULT_COMPOSITE_SETTINGS,
        POSITION_OPTIONS,
        BG_SOURCE_OPTIONS
    )
    TIMELINE_COMPOSITE_AVAILABLE = True
except ImportError as e:
    TIMELINE_COMPOSITE_AVAILABLE = False
    print(f"[스토리보드] 타임라인 합성 모듈 로드 실패: {e}", flush=True)

# 인포그래픽 관련 import
try:
    from utils.models.infographic import VisualType, MediaType, InfographicData, SceneVisualSelection
    from utils.infographic_parser import InfographicParser, parse_infographic_html, get_parsing_info
    from utils.visual_selection_manager import VisualSelectionManager, get_session_manager
    # 팩토리 패턴: 자동 폴백 (Playwright → Selenium → html2image)
    from utils.infographic_renderer_factory import (
        generate_thumbnails as factory_generate_thumbnails,
        record_videos as factory_record_videos,
        check_environment
    )
    from utils.infographic_video_recorder import check_ffmpeg_available
    from utils.infographic_compositor import (
        batch_composite_sync,
        get_compositor,
        is_bg_removal_available,
        is_mapper_available,
        get_bg_removal_diagnostic,
        test_bg_removal
    )
    from utils.scene_character_mapper import (
        get_scene_character_matcher,
        get_mapping_summary
    )
    from utils.background_remover import install_rembg_ui
    from utils.character_editor import render_character_editor, render_character_preview_only
    from utils.html_scene_editor import HTMLSceneEditor, get_scene_editor, clear_scene_editor
    INFOGRAPHIC_AVAILABLE = True
except ImportError as e:
    INFOGRAPHIC_AVAILABLE = False
    print(f"[스토리보드] 인포그래픽 모듈 로드 실패: {e}", flush=True)

# AI Video API imports
try:
    from utils.scene_video_generator import (
        get_available_video_platforms,
        get_i2v_models_for_platform,
        estimate_video_cost,
        generate_scene_video,
        get_video_prompt_for_scene,
        get_scene_image_path,
        batch_generate_scene_videos,
        VIDEO_API_AVAILABLE,
        # ⭐ v3.22: SRT 기반 비디오 길이 자동 추천
        get_scene_srt_duration,
        get_recommended_video_duration,
        get_batch_duration_info,
    )
    from utils.video_api import ALL_MODELS, PLATFORM_CONFIGS
except ImportError as e:
    VIDEO_API_AVAILABLE = False
    print(f"[스토리보드] Video API 모듈 로드 실패: {e}", flush=True)

# Settings Manager (영구 저장)
from utils.settings_manager import (
    get_setting,
    set_setting,
    persistent_selectbox,
    persistent_radio,
    persistent_checkbox,
    render_settings_management_ui
)

import subprocess


# ============================================================
# 성능 프로파일링 도구 (v3.18)
# ============================================================

class Profiler:
    """간단한 전역 프로파일러"""
    _start_time = None

    @classmethod
    def start(cls):
        import time
        cls._start_time = time.time()

    @classmethod
    def log(cls, message: str):
        import time
        if cls._start_time is None:
            cls._start_time = time.time()
        elapsed = time.time() - cls._start_time
        print(f"[PROFILER] [{elapsed:.3f}s] {message}", flush=True)


class Timer:
    """컨텍스트 매니저 타이머"""
    def __init__(self, name: str):
        self.name = name
        self.start = None

    def __enter__(self):
        import time
        self.start = time.time()
        return self

    def __exit__(self, *args):
        import time
        elapsed = time.time() - self.start
        if elapsed > 0.05:  # 0.05초 이상만 출력
            print(f"[TIMER] {self.name}: {elapsed:.3f}s", flush=True)


# ============================================================
# 성능 최적화: 캐싱된 싱글톤 객체들 (v3.17)
# ============================================================

@st.cache_resource
def get_cached_image_scene_matcher(_project_path_str: str):
    """
    ImageSceneMatcher 캐싱 (프로젝트당 1회만 생성)
    - Streamlit rerun마다 새로 생성하지 않음
    - 프로젝트 변경 시에만 새로 생성
    """
    from pathlib import Path
    return ImageSceneMatcher(Path(_project_path_str))


@st.cache_data(ttl=120, show_spinner=False)
def get_metadata_index(_project_path_str: str, _cache_key: str = "") -> dict:
    """
    메타데이터 인덱스 사전 구축 (역방향 검색 최적화)
    - 모든 JSON 파일을 한 번 스캔하여 scene_id → metadata 매핑 생성
    - 이후 O(1) 검색 가능
    """
    from pathlib import Path
    import json

    project_path = Path(_project_path_str)
    index = {}

    metadata_dirs = [
        project_path / "images" / "backgrounds",
        project_path / "images" / "composited",
        project_path / "images" / "scenes",
    ]

    for meta_dir in metadata_dirs:
        if not meta_dir.exists():
            continue

        for json_file in meta_dir.glob("*.json"):
            if json_file.name.startswith("metadata_"):
                continue

            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)

                if isinstance(metadata, list):
                    metadata = metadata[0] if metadata else {}

                if not isinstance(metadata, dict):
                    continue

                scene_id = metadata.get("scene_id")
                if scene_id is not None:
                    scene_id = int(scene_id)
                    mtime = json_file.stat().st_mtime

                    # 같은 scene_id가 있으면 최신 것 유지
                    if scene_id not in index or mtime > index[scene_id]["mtime"]:
                        index[scene_id] = {
                            "metadata": metadata,
                            "mtime": mtime,
                            "json_path": str(json_file)
                        }

            except Exception:
                continue

    return index


def get_metadata_by_scene_id(project_path: str, scene_id: int, cache_key: str = "") -> dict:
    """scene_id로 메타데이터 즉시 조회 (O(1))"""
    index = get_metadata_index(project_path, cache_key)
    entry = index.get(scene_id)
    return entry["metadata"] if entry else None


# ============================================================
# 유틸리티 함수: 파일/폴더 열기 (Windows)
# ============================================================

def open_file_location(file_path: str):
    """파일 위치를 탐색기에서 열기 (Windows)"""
    try:
        subprocess.Popen(f'explorer /select,"{file_path}"')
    except Exception as e:
        st.error(f"폴더 열기 실패: {e}")


def open_folder(folder_path: str):
    """폴더 열기 (Windows)"""
    try:
        os.makedirs(folder_path, exist_ok=True)
        subprocess.Popen(f'explorer "{folder_path}"')
    except Exception as e:
        st.error(f"폴더 열기 실패: {e}")


# ============================================================
# 유틸리티: 캐릭터 목록 안전하게 문자열 변환
# ============================================================

def safe_join_characters(characters: list) -> str:
    """
    캐릭터 목록을 안전하게 문자열로 변환

    characters가 str 리스트이든 dict 리스트이든 처리
    """
    if not characters:
        return ""

    names = []
    for char in characters:
        if isinstance(char, str):
            names.append(char)
        elif isinstance(char, dict):
            # name, character_name, id 순으로 시도
            name = char.get('name') or char.get('character_name') or char.get('id', '')
            if name:
                names.append(str(name))
        elif char is not None:
            names.append(str(char))

    return ', '.join(names)


# ============================================================
# 실사 이미지 대체 기능 (v1.0)
# ============================================================

import shutil
import streamlit.components.v1 as components_js

def copy_path_to_clipboard(path: str, key: str):
    """이미지 경로를 클립보드에 복사 (JavaScript 사용)"""
    # 윈도우 경로는 역슬래시를 이스케이프 처리
    escaped_path = path.replace("\\", "\\\\")

    # JavaScript로 클립보드 복사
    js_code = f"""
    <script>
    (function() {{
        const path = "{escaped_path}";
        navigator.clipboard.writeText(path).then(function() {{
            // 복사 성공 시 알림 (옵션)
        }}).catch(function(err) {{
            console.error('클립보드 복사 실패:', err);
        }});
    }})();
    </script>
    <div style="display:none;">copied</div>
    """
    components_js.html(js_code, height=0)
    return True


def render_instant_copy_button(text: str, key: str, label: str = "Copy", help_text: str = "클립보드에 복사"):
    """
    즉시 클립보드 복사 버튼 렌더링 (v1.3)

    JavaScript로 즉시 복사하고 '✅ 복사됨!' 피드백 표시
    v1.3: json.dumps()로 안전한 이스케이프 (전체 텍스트 복사 보장)

    Args:
        text: 복사할 텍스트
        key: 고유 키
        label: 버튼 라벨
        help_text: 툴팁 텍스트
    """
    import json

    if not text:
        st.button(label, disabled=True, key=f"{key}_disabled", help="복사할 내용이 없습니다")
        return

    # v1.3: json.dumps()로 모든 특수문자 안전하게 이스케이프
    # 이 방법은 따옴표, 줄바꿈, 유니코드 등 모든 문자를 올바르게 처리
    safe_text_json = json.dumps(text, ensure_ascii=False)  # "텍스트" 형태 (따옴표 포함)

    btn_id = f"copy_btn_{key}"
    func_name = key.replace('-', '_').replace('.', '_')

    # HTML + JavaScript 인라인 버튼
    html_code = f"""
    <style>
        #{btn_id} {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 6px;
            padding: 6px 14px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            min-width: 60px;
        }}
        #{btn_id}:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }}
        #{btn_id}.copied {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }}
    </style>
    <button id="{btn_id}" title="{help_text}" onclick="copyPrompt_{func_name}()">
        {label}
    </button>
    <script>
        function copyPrompt_{func_name}() {{
            // v1.3: JSON.parse로 안전하게 텍스트 복원 (전체 텍스트 보장)
            const text = {safe_text_json};
            const btn = document.getElementById("{btn_id}");

            navigator.clipboard.writeText(text).then(function() {{
                // 복사 성공
                btn.innerHTML = "✅ 복사됨!";
                btn.classList.add("copied");
                setTimeout(function() {{
                    btn.innerHTML = "{label}";
                    btn.classList.remove("copied");
                }}, 1500);
            }}).catch(function(err) {{
                console.error("복사 실패:", err);
                // 폴백: execCommand 사용
                try {{
                    const textarea = document.createElement("textarea");
                    textarea.value = text;
                    textarea.style.position = "fixed";
                    textarea.style.opacity = "0";
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand("copy");
                    document.body.removeChild(textarea);

                    btn.innerHTML = "✅ 복사됨!";
                    btn.classList.add("copied");
                    setTimeout(function() {{
                        btn.innerHTML = "{label}";
                        btn.classList.remove("copied");
                    }}, 1500);
                }} catch(e) {{
                    btn.innerHTML = "❌ 실패";
                    setTimeout(function() {{
                        btn.innerHTML = "{label}";
                    }}, 1500);
                }}
            }});
        }}
    </script>
    """

    components_js.html(html_code, height=38)


def get_backup_path(image_path: Path) -> Path:
    """AI 이미지 백업 경로 반환"""
    backup_dir = image_path.parent / "_ai_backup"
    backup_dir.mkdir(exist_ok=True)
    return backup_dir / image_path.name


def backup_ai_image(image_path: Path) -> bool:
    """AI 이미지를 백업 폴더에 복사"""
    try:
        backup_path = get_backup_path(image_path)
        if image_path.exists() and not backup_path.exists():
            shutil.copy2(image_path, backup_path)
            return True
        return False
    except Exception as e:
        st.error(f"백업 실패: {e}")
        return False


def restore_ai_image(image_path: Path) -> bool:
    """백업에서 AI 이미지 복원"""
    try:
        backup_path = get_backup_path(image_path)
        if backup_path.exists():
            shutil.copy2(backup_path, image_path)
            return True
        return False
    except Exception as e:
        st.error(f"복원 실패: {e}")
        return False


def has_backup(image_path: Path) -> bool:
    """백업 파일 존재 여부 확인"""
    return get_backup_path(image_path).exists()


def batch_backup_images(image_paths: list) -> int:
    """여러 이미지 일괄 백업"""
    backed_up = 0
    for img_path in image_paths:
        if isinstance(img_path, str):
            img_path = Path(img_path)
        if backup_ai_image(img_path):
            backed_up += 1
    return backed_up


def batch_restore_images(image_paths: list) -> int:
    """여러 이미지 일괄 복원"""
    restored = 0
    for img_path in image_paths:
        if isinstance(img_path, str):
            img_path = Path(img_path)
        if restore_ai_image(img_path):
            restored += 1
    return restored


def invalidate_image_cache(image_path: str):
    """이미지 캐시 무효화 (새로고침용)"""
    # Streamlit은 파일 경로 기반으로 캐시하므로,
    # 새로고침 시 timestamp 파라미터를 변경하면 됨
    # 여기서는 session_state를 사용하여 refresh 플래그 설정
    if "image_refresh_timestamps" not in st.session_state:
        st.session_state["image_refresh_timestamps"] = {}
    st.session_state["image_refresh_timestamps"][image_path] = datetime.now().timestamp()


def get_image_cache_buster(image_path: str) -> str:
    """이미지 캐시 버스터 문자열 반환"""
    if "image_refresh_timestamps" not in st.session_state:
        return ""
    ts = st.session_state["image_refresh_timestamps"].get(image_path, "")
    return f"?t={ts}" if ts else ""


def invalidate_image_list_cache_light():
    """
    가벼운 이미지 캐시 무효화 (파일 목록만)

    새 이미지 추가/삭제 후 파일 목록만 갱신할 때 사용
    ImageSceneMatcher나 세션 상태는 유지하여 성능 보장
    """
    # 세션 기반 캐시 버전만 증가 (파일 목록 갱신)
    current_version = st.session_state.get("image_cache_version", 0)
    st.session_state["image_cache_version"] = current_version + 1
    print(f"[스토리보드] 이미지 목록 캐시 갱신 (버전: {current_version + 1})", flush=True)
    return 1


def invalidate_all_image_caches(full_reset: bool = False):
    """
    이미지 관련 캐시 무효화

    Args:
        full_reset: True면 모든 캐시 완전 초기화 (새로고침 버튼용)
                   False면 가벼운 갱신만 (파일 변경 후)
    """
    cleared_count = 0

    # 세션 기반 캐시 버전 증가 (항상 실행)
    current_version = st.session_state.get("image_cache_version", 0)
    st.session_state["image_cache_version"] = current_version + 1
    cleared_count += 1

    # ⭐ v2.3: 이미지 파일 변경 시 항상 캐시 클리어 필요 (실사 이미지 반영 버그 수정)
    # load_image_files_cached 캐시 항상 클리어
    try:
        load_image_files_cached.clear()
        cleared_count += 1
        print(f"[스토리보드] 이미지 파일 캐시 클리어됨", flush=True)
    except Exception:
        pass

    # full_reset이 아니면 여기서 종료 (가벼운 갱신)
    if not full_reset:
        print(f"[스토리보드] 이미지 캐시 갱신 (버전: {current_version + 1})", flush=True)
        return cleared_count

    # === 아래는 full_reset=True 일 때만 실행 ===
    print(f"[스토리보드] 전체 캐시 초기화 시작...", flush=True)

    # 1-2. 메타데이터 인덱스 캐시 클리어 (v3.17)
    try:
        get_metadata_index.clear()
        cleared_count += 1
    except Exception:
        pass

    # 1-3. ImageSceneMatcher 캐시 클리어 (v3.17)
    try:
        get_cached_image_scene_matcher.clear()
        cleared_count += 1
    except Exception:
        pass

    # 2. 세션 상태에서 이미지 관련 키 삭제 (full_reset만)
    keys_to_delete = []
    for key in list(st.session_state.keys()):
        # 중요 설정은 유지
        if key.startswith('compose_') or key == 'image_cache_version':
            continue
        if any(keyword in key.lower() for keyword in [
            'scene_img', 'matched', '_storyboard_images_dir_logged',
            'matching_summary_', 'ai_folder_files_',  # ⭐ 매칭 요약 + AI 폴더 캐시
            'backup_count_', 'export_media_list_'  # ⭐ 백업 카운트 + 내보내기 목록 캐시
        ]):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        try:
            del st.session_state[key]
            cleared_count += 1
        except KeyError:
            pass

    # ⭐ 성능 최적화: ImageSceneMatcher 플래그 리셋 제거 (불필요한 재초기화 방지)
    # _init_logged는 더 이상 사용하지 않음

    print(f"[스토리보드] 전체 캐시 초기화 완료 ({cleared_count}개 항목)", flush=True)
    return cleared_count


# ============================================================
# 개별 씬 HTML 편집 섹션
# ============================================================

def render_scene_editor_section(infographic_data, project_path, visual_manager):
    """개별 씬 HTML 편집 섹션 렌더링"""

    import streamlit.components.v1 as components

    st.markdown("### ✏️ 2.3 개별 씬 HTML 편집")
    st.caption("특정 씬의 HTML 코드를 직접 수정하고 미리보기합니다.")

    # HTML 내용 확인
    html_content = infographic_data.html_code if hasattr(infographic_data, 'html_code') else None

    if not html_content:
        source_path = infographic_data.source_path if hasattr(infographic_data, 'source_path') else None
        if source_path and os.path.exists(source_path):
            try:
                with open(source_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            except Exception as e:
                st.warning(f"HTML 파일 로드 실패: {e}")
                return
        else:
            st.warning("인포그래픽 HTML 콘텐츠를 찾을 수 없습니다.")
            return

    # 편집기 인스턴스 생성/가져오기
    source_path_str = infographic_data.source_path if hasattr(infographic_data, 'source_path') else ""

    # ✅ HTML 콘텐츠 해시로 변경 감지 (버그 수정: 경로만 비교하면 내용 변경 감지 못함)
    import hashlib
    html_content_hash = hashlib.md5(html_content.encode('utf-8')).hexdigest()[:16]

    # 세션에서 편집기 가져오기
    editor_key = "scene_html_editor"
    cached_hash = st.session_state.get("scene_editor_html_hash", "")

    # ✅ 경로 OR HTML 내용이 변경되었으면 에디터 재생성
    needs_refresh = (
        editor_key not in st.session_state or
        st.session_state.get("scene_editor_source") != source_path_str or
        cached_hash != html_content_hash
    )

    if needs_refresh:
        editor = HTMLSceneEditor(html_content, source_path_str)
        st.session_state[editor_key] = editor
        st.session_state["scene_editor_source"] = source_path_str
        st.session_state["scene_editor_html_hash"] = html_content_hash
    else:
        editor = st.session_state[editor_key]

    if not editor.scenes:
        st.warning("씬을 파싱할 수 없습니다. HTML 형식을 확인하세요.")
        return

    # 설명 Expander
    with st.expander("💡 사용 방법", expanded=False):
        st.markdown("""
        **개별 씬 HTML 편집 기능**

        1. **씬 선택**: 드롭다운에서 수정할 씬을 선택합니다
        2. **현재 HTML 확인**: 선택한 씬의 현재 HTML 코드를 확인합니다
        3. **HTML 수정**: 텍스트 영역에서 HTML을 직접 수정합니다
        4. **미리보기**: 수정 내용을 미리보기로 확인합니다
        5. **적용**: 수정 사항을 적용합니다
        6. **복원**: 원래 HTML로 되돌립니다

        **형식 안내:**
        - `sceneData` 형식: `{ id: 1, text: "...", sub: "..." }` 형태의 JavaScript 객체
        - `HTML` 형식: `<div class="scene">...</div>` 형태의 HTML 요소
        """)

    # 수정 상태 표시
    diff_summary = editor.get_diff_summary()
    if diff_summary["has_changes"]:
        modified_list = editor.get_modified_scenes()
        st.info(f"📝 수정된 씬: {', '.join(str(s) for s in modified_list)} ({len(modified_list)}개)")

    # ============================================================
    # 씬 선택 UI
    # ============================================================
    st.markdown("#### 📍 수정할 씬 선택")

    scene_list = editor.get_scene_list()
    scene_options = {f"씬 {s['scene_id']}: {s['text'][:30]}": s['scene_id'] for s in scene_list}

    col_select, col_direct = st.columns([3, 1])

    with col_select:
        selected_label = st.selectbox(
            "씬 선택",
            options=list(scene_options.keys()),
            key="scene_editor_select",
            label_visibility="collapsed"
        )
        selected_scene_id = scene_options.get(selected_label, 1)

    with col_direct:
        direct_id = st.number_input(
            "직접 입력",
            min_value=1,
            max_value=len(scene_list),
            value=selected_scene_id,
            key="scene_editor_direct_input",
            label_visibility="collapsed"
        )
        if direct_id != selected_scene_id:
            selected_scene_id = direct_id

    # 현재 선택된 씬 정보
    current_scene = editor.get_scene(selected_scene_id)
    if not current_scene:
        st.error(f"씬 {selected_scene_id}을(를) 찾을 수 없습니다.")
        return

    is_modified = editor.is_scene_modified(selected_scene_id)

    # 씬 정보 표시
    info_col1, info_col2, info_col3 = st.columns(3)
    with info_col1:
        st.caption(f"📄 형식: {current_scene.format_type}")
    with info_col2:
        st.caption(f"📏 크기: {len(current_scene.html_content):,} 문자")
    with info_col3:
        if is_modified:
            st.caption("✏️ **수정됨**")
        else:
            st.caption("✅ 원본")

    # ============================================================
    # 현재 HTML 코드 보기
    # ============================================================
    st.markdown("#### 📋 현재 씬 HTML 코드")

    with st.expander("현재 HTML 보기", expanded=True):
        st.code(current_scene.html_content, language="javascript" if current_scene.format_type == "scenedata" else "html")

    # ============================================================
    # HTML 수정 입력
    # ============================================================
    st.markdown("#### ✏️ 수정된 HTML 코드 입력")

    # 수정 입력 영역
    modified_html_input = st.text_area(
        "HTML 코드 수정",
        value=current_scene.html_content,
        height=200,
        key=f"scene_edit_input_{selected_scene_id}",
        label_visibility="collapsed"
    )

    # 변경 여부 확인
    has_local_changes = modified_html_input.strip() != current_scene.html_content.strip()

    if has_local_changes:
        st.info("📝 변경 사항이 있습니다. 미리보기 후 적용하세요.")

    # ============================================================
    # 미리보기 (sceneData 형식인 경우)
    # ============================================================
    if has_local_changes and current_scene.format_type == "scenedata":
        st.markdown("#### 👁️ 수정 미리보기")

        try:
            # 수정된 객체 파싱 시도
            test_obj = modified_html_input.strip()

            # 간단한 미리보기
            text_match = re.search(r'text\s*:\s*["\']([^"\']*)["\']', test_obj)
            sub_match = re.search(r'sub\s*:\s*["\']([^"\']*)["\']', test_obj)

            preview_text = text_match.group(1) if text_match else "(텍스트 없음)"
            preview_sub = sub_match.group(1) if sub_match else "(서브텍스트 없음)"

            col_before, col_after = st.columns(2)

            with col_before:
                st.markdown("**현재:**")
                st.markdown(f"- 텍스트: {current_scene.text}")
                st.markdown(f"- 서브: {current_scene.sub[:50] if current_scene.sub else '없음'}")

            with col_after:
                st.markdown("**수정 후:**")
                st.markdown(f"- 텍스트: {preview_text}")
                st.markdown(f"- 서브: {preview_sub[:50] if preview_sub else '없음'}")

        except Exception as e:
            st.warning(f"미리보기 파싱 오류: {e}")

    # ============================================================
    # 버튼 영역
    # ============================================================
    st.markdown("---")

    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

    with btn_col1:
        apply_disabled = not has_local_changes
        if st.button(
            "✅ 씬 HTML 교체 적용",
            type="primary",
            disabled=apply_disabled,
            use_container_width=True,
            key="apply_scene_edit"
        ):
            success, msg = editor.replace_scene(
                selected_scene_id,
                modified_html_input,
                description=f"씬 {selected_scene_id} 수동 수정"
            )
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with btn_col2:
        restore_disabled = not is_modified
        if st.button(
            "🔄 원래대로 되돌리기",
            disabled=restore_disabled,
            use_container_width=True,
            key="restore_scene"
        ):
            success, msg = editor.restore_scene(selected_scene_id)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with btn_col3:
        if st.button(
            "🔙 전체 복원",
            disabled=not diff_summary["has_changes"],
            use_container_width=True,
            key="restore_all_scenes"
        ):
            success, msg = editor.restore_all()
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with btn_col4:
        if st.button(
            "💾 HTML 저장",
            disabled=not diff_summary["has_changes"],
            use_container_width=True,
            key="save_edited_html"
        ):
            # 수정된 HTML 저장
            output_path = project_path / "infographics" / "infographic_edited.html"
            success, msg = editor.save_to_file(str(output_path))
            if success:
                st.success(msg)

                # 인포그래픽 데이터 업데이트
                infographic_data.html_code = editor.get_current_html()
                visual_manager.set_infographic_data(infographic_data)

                st.info("💡 수정된 HTML이 저장되었습니다. 썸네일/동영상을 다시 생성해야 변경 사항이 반영됩니다.")
            else:
                st.error(msg)

    # ============================================================
    # 수정 이력
    # ============================================================
    edit_history = editor.get_edit_history()
    if edit_history:
        with st.expander(f"📜 수정 이력 ({len(edit_history)}개)", expanded=False):
            for i, record in enumerate(reversed(edit_history[-10:])):  # 최근 10개
                st.markdown(f"**{i+1}.** 씬 {record['scene_id']} - {record['timestamp'][:19]}")
                if record['description']:
                    st.caption(f"   {record['description']}")

    # 다운로드 버튼
    if diff_summary["has_changes"]:
        st.download_button(
            "💾 수정된 HTML 다운로드",
            data=editor.get_current_html(),
            file_name="infographic_edited.html",
            mime="text/html",
            use_container_width=True,
            key="download_edited_html"
        )


# ============================================================
# 스토리보드 비디오 변환 모달 (카드 뷰에서 호출)
# ============================================================

def _render_video_conversion_modal(project_path):
    """
    스토리보드 카드 뷰에서 이미지 클릭 시 비디오 변환 모달
    session_state에서 필요한 정보를 가져옴
    """
    scene_id = st.session_state.get("video_convert_scene_id")
    image_path = st.session_state.get("video_convert_image_path")
    scene = st.session_state.get("video_convert_scene", {})

    if not scene_id or not image_path:
        return

    # 비디오 프롬프트 가져오기
    video_prompt_char = get_video_prompt_for_scene(scene, "character")
    video_prompt_full = get_video_prompt_for_scene(scene, "full")

    st.markdown("---")
    with st.container(border=True):
        st.markdown(f"### 🎬 씬 {scene_id} 이미지 → 비디오 변환")

        col_img, col_settings = st.columns([1, 2])

        with col_img:
            if os.path.exists(image_path):
                render_lightbox_image(image_path, caption="현재 이미지", key=f"video_modal_{scene_id}")
            else:
                st.warning("이미지 파일을 찾을 수 없습니다")

        with col_settings:
            st.markdown("**📋 비디오 프롬프트**")

            # 프롬프트 유형 선택
            prompt_type = st.radio(
                "프롬프트 유형",
                options=["character", "full"],
                format_func=lambda x: "👤 비디오(캐릭터)" if x == "character" else "🌍 비디오(전체)",
                horizontal=True,
                key="video_modal_prompt_type"
            )

            # 선택된 프롬프트
            if prompt_type == "character":
                selected_prompt = video_prompt_char
            else:
                selected_prompt = video_prompt_full

            # 프롬프트 수정 가능
            edited_prompt = st.text_area(
                "프롬프트 (수정 가능)",
                value=selected_prompt if selected_prompt else "",
                height=100,
                key="video_modal_prompt_edit"
            )

        st.markdown("---")

        # ⭐ v3.22: SRT 기반 비디오 길이 추천
        recommended_duration, actual_srt_duration, duration_reason = get_recommended_video_duration(scene)

        if actual_srt_duration is not None:
            # 실제 SRT/TTS 데이터가 있는 경우
            st.info(f"📊 **SRT 기반 추천**: 이 씬은 **{actual_srt_duration:.1f}초** → 비디오 **{recommended_duration}초** 추천")
        else:
            # TTS 데이터 없음
            estimated_dur = scene.get("duration_estimate", 5)
            st.caption(f"💡 TTS 데이터 없음. 추정치 {estimated_dur:.1f}초 기반 → {recommended_duration}초 추천")

        st.markdown("**⚙️ 비디오 생성 설정**")

        # 페이지 ID (settings_manager용)
        VIDEO_PAGE_ID = "video_generation"

        col_api, col_model, col_dur = st.columns(3)

        with col_api:
            # 플랫폼 선택
            available_platforms = get_available_video_platforms()

            if not available_platforms:
                st.warning("사용 가능한 Video API가 없습니다")
                selected_platform = None
            else:
                platform_names = {
                    "fal_ai": "fal.ai (Kling, Wan 등)",
                    "replicate": "Replicate",
                    "pixverse": "PixVerse"
                }
                selected_platform = persistent_selectbox(
                    "🤖 플랫폼",
                    options=available_platforms,
                    page=VIDEO_PAGE_ID,
                    setting_key="platform",
                    format_func=lambda x: platform_names.get(x, x)
                )

        with col_model:
            # 모델 선택
            if selected_platform:
                models = get_i2v_models_for_platform(selected_platform)
                model_options = list(models.keys())

                if model_options:
                    selected_model = persistent_selectbox(
                        "🎨 모델",
                        options=model_options,
                        page=VIDEO_PAGE_ID,
                        setting_key="model",
                        format_func=lambda x: models[x].display_name if x in models else x
                    )
                else:
                    selected_model = None
                    st.warning("사용 가능한 모델 없음")
            else:
                selected_model = None

        with col_dur:
            # 길이 선택 - 모델별 지원 duration 기반 동적 생성
            if selected_platform and selected_model and models:
                model_config = models.get(selected_model)
                if model_config and model_config.durations:
                    duration_options = sorted(model_config.durations)
                    # ⭐ v3.22: SRT 추천값이 모델 옵션에 있으면 그것을 기본값으로
                    if recommended_duration in duration_options:
                        default_idx = duration_options.index(recommended_duration)
                    elif model_config.default_duration in duration_options:
                        default_idx = duration_options.index(model_config.default_duration)
                    else:
                        default_idx = 0
                else:
                    duration_options = [5]
                    default_idx = 0
            else:
                duration_options = [5]
                default_idx = 0

            # ⭐ v3.22: 추천 표시 추가
            selected_duration = st.selectbox(
                "⏱️ 비디오 길이",
                options=duration_options,
                index=default_idx,
                format_func=lambda x: f"{x}초 {'✨추천' if x == recommended_duration else ''}",
                key=f"video_modal_duration_{scene_id}"
            )

        # 비용 예측 및 플랫폼 정보
        if selected_platform and selected_model:
            estimate = estimate_video_cost(
                platform=selected_platform,
                model_key=selected_model,
                duration=selected_duration
            )

            if estimate and not estimate.get("error"):
                # 기본 비용 정보
                col_cost1, col_cost2, col_cost3, col_cost4 = st.columns(4)
                with col_cost1:
                    cost_usd = estimate.get('cost_usd', 0)
                    credits = estimate.get('credits', 0)
                    if credits > 0:
                        st.metric("💰 예상 비용", f"{credits} 크레딧")
                    else:
                        st.metric("💰 예상 비용", f"${cost_usd:.3f}")
                with col_cost2:
                    st.metric("⏱️ 예상 시간", f"{estimate.get('time_seconds', 0)}초")
                with col_cost3:
                    speed_tier = estimate.get('speed_tier', 'medium')
                    speed_emoji = {"fast": "⚡", "medium": "🔄", "slow": "🐢"}.get(speed_tier, "🔄")
                    st.metric("속도", f"{speed_emoji} {speed_tier.upper()}")
                with col_cost4:
                    st.metric("⭐ 품질", "⭐" * estimate.get("quality_tier", 3))

                # 모델 정보 및 경고
                model_name = estimate.get('model_name', selected_model)
                st.caption(f"📌 모델: **{model_name}**")

                # 법적 경고 (MiniMax 등)
                legal_warning = estimate.get('legal_warning')
                if legal_warning:
                    st.warning(f"⚠️ {legal_warning}")

                # 플랫폼별 추가 정보
                if selected_platform == "pixverse":
                    st.info("ℹ️ PixVerse: 무료 90 크레딧 (가입) + 60 크레딧/일. 워터마크 포함.")
                elif selected_platform == "fal_ai":
                    st.info("ℹ️ fal.ai: 신규 $10 무료 크레딧. 고품질 모델 다수.")
                elif selected_platform == "replicate":
                    st.info("ℹ️ Replicate: 사용량 기반 과금. 다양한 오픈소스 모델.")

        st.markdown("---")

        # 버튼
        col_btn1, col_btn2 = st.columns(2)

        with col_btn1:
            generate_disabled = not (edited_prompt and selected_platform and selected_model)

            if st.button(
                "🎬 비디오 생성 시작",
                type="primary",
                use_container_width=True,
                disabled=generate_disabled,
                key="video_modal_generate"
            ):
                # 비디오 생성 실행
                print(f"[VideoModal] 비디오 생성 시작 - 씬 {scene_id}")
                print(f"[VideoModal] 플랫폼: {selected_platform}, 모델: {selected_model}, 길이: {selected_duration}초")

                with st.spinner(f"씬 {scene_id} 비디오 생성 중... ({selected_duration}초)"):
                    result = generate_scene_video(
                        image_path=image_path,
                        prompt=edited_prompt,
                        platform=selected_platform,
                        model_key=selected_model,
                        duration=selected_duration,
                        output_dir=str(project_path / "videos" / "storyboard"),
                        scene_id=scene_id
                    )
                    print(f"[VideoModal] 생성 결과: {result}")

                if result.get("success"):
                    video_path = result.get("video_path")
                    print(f"[VideoModal] ✅ 생성 성공! 경로: {video_path}")

                    # v3.23: 세션 상태에 결과 저장 (rerun 후에도 유지)
                    st.session_state[f"video_modal_result_{scene_id}"] = result

                    st.success(f"✅ 비디오 생성 완료!")
                else:
                    error_msg = result.get('error', 'Unknown error')
                    print(f"[VideoModal] ❌ 생성 실패: {error_msg}")
                    st.error(f"❌ 비디오 생성 실패: {error_msg}")

        # v3.23: 세션 상태에서 최근 생성 결과 표시 (버튼 블록 외부)
        recent_result = st.session_state.get(f"video_modal_result_{scene_id}")
        if recent_result and recent_result.get("success"):
            video_path = recent_result.get("video_path")

            st.markdown("---")
            st.markdown("**🎥 최근 생성된 비디오**")

            if video_path and os.path.exists(video_path):
                try:
                    st.video(video_path)
                    print(f"[VideoModal] st.video() 호출 성공: {video_path}")

                    # 다운로드 버튼 (파일 데이터를 미리 읽어서 제공)
                    with open(video_path, "rb") as f:
                        video_data = f.read()

                    st.download_button(
                        "📥 비디오 다운로드",
                        data=video_data,
                        file_name=os.path.basename(video_path),
                        mime="video/mp4",
                        key=f"download_recent_{scene_id}"
                    )
                except Exception as e:
                    print(f"[VideoModal] 비디오 표시 오류: {e}")
                    st.error(f"비디오 표시 오류: {e}")
                    # 폴백: 링크로 제공
                    st.markdown(f"📁 비디오 경로: `{video_path}`")
            else:
                st.warning(f"비디오 파일을 찾을 수 없습니다: {video_path}")

            # 프롬프트 뷰어 (최종 프롬프트 확인)
            original_prompt = recent_result.get("original_prompt", edited_prompt)
            final_prompt = recent_result.get("final_prompt", edited_prompt)
            prompt_expanded = recent_result.get("prompt_expanded", False)

            with st.expander("📝 사용된 프롬프트 보기", expanded=False):
                col_info1, col_info2 = st.columns([1, 2])

                with col_info1:
                    st.markdown(f"**플랫폼:** {recent_result.get('platform', 'N/A')}")
                    st.markdown(f"**모델:** {recent_result.get('model', 'N/A')}")
                    st.markdown(f"**비용:** ${recent_result.get('cost_usd', 0):.3f}")
                    st.markdown(f"**생성 시간:** {recent_result.get('generation_time', 0):.1f}초")

                with col_info2:
                    if prompt_expanded:
                        st.info("🔄 프롬프트가 AI에 의해 자동 확장되었습니다")

                    st.markdown("**원본 프롬프트:**")
                    st.code(original_prompt[:200] + "..." if len(original_prompt) > 200 else original_prompt, language=None)

                    if final_prompt and final_prompt != original_prompt:
                        st.markdown("**최종 프롬프트 (AI 확장):**")
                        st.code(final_prompt[:300] + "..." if len(final_prompt) > 300 else final_prompt, language=None)

        with col_btn2:
            if st.button("닫기", use_container_width=True, key="video_modal_close"):
                # 모달 닫기
                del st.session_state["video_convert_scene_id"]
                if "video_convert_image_path" in st.session_state:
                    del st.session_state["video_convert_image_path"]
                if "video_convert_scene" in st.session_state:
                    del st.session_state["video_convert_scene"]
                st.rerun()

        # 이전 생성 결과 표시
        st.markdown("---")
        st.markdown("**📊 이전 생성 결과**")

        videos_dir = project_path / "videos" / "storyboard"
        if videos_dir.exists():
            pattern = f"scene_{scene_id:03d}_*.mp4"
            existing_videos = list(videos_dir.glob(pattern))

            if existing_videos:
                for video_path in existing_videos[:3]:
                    with st.expander(f"▶️ {video_path.name}"):
                        st.video(str(video_path))
                        col_dl, col_del = st.columns(2)
                        with col_dl:
                            with open(video_path, "rb") as f:
                                st.download_button(
                                    "📥 다운로드",
                                    data=f.read(),
                                    file_name=video_path.name,
                                    mime="video/mp4",
                                    key=f"dl_{video_path.name}"
                                )
                        with col_del:
                            if st.button("🗑️ 삭제", key=f"del_{video_path.name}"):
                                os.remove(video_path)
                                st.rerun()
            else:
                st.caption("생성된 비디오가 없습니다.")
        else:
            st.caption("비디오 폴더가 없습니다.")

    st.markdown("---")


# ============================================================
# AI 비디오 생성 섹션 (Video API)
# ============================================================

def render_ai_video_generation_section(scenes: list, project_path, visual_manager=None):
    """
    AI Video API를 사용한 씬 이미지 → 비디오 변환 섹션

    Args:
        scenes: 씬 데이터 리스트
        project_path: 프로젝트 경로
        visual_manager: 비주얼 매니저 (선택)
    """
    st.markdown("### 🎬 AI 비디오 생성")
    st.caption("씬 이미지를 AI Video API로 변환하여 동영상을 생성합니다.")

    if not VIDEO_API_AVAILABLE:
        st.warning("Video API 모듈이 설치되지 않았습니다.")
        st.code("pip install httpx pydantic", language="bash")
        return

    # 사용 가능한 플랫폼 확인
    available_platforms = get_available_video_platforms()

    if not available_platforms:
        st.error("사용 가능한 Video API가 없습니다. API 키를 설정하세요.")
        with st.expander("🔑 API 키 설정 방법"):
            st.markdown("""
            `.env` 파일에 다음 API 키 중 하나 이상을 추가하세요:

            ```
            FAL_KEY=xxx              # fal.ai (권장)
            REPLICATE_API_TOKEN=xxx  # Replicate
            PIXVERSE_API_KEY=xxx     # PixVerse
            ```
            """)
        return

    if not scenes:
        st.warning("씬 데이터가 없습니다. 씬 분석을 먼저 진행하세요.")
        return

    # ============================================================
    # 설정 섹션
    # ============================================================
    # 페이지 ID (settings_manager용)
    VIDEO_PAGE_ID = "video_generation"

    with st.container(border=True):
        st.markdown("#### ⚙️ 비디오 생성 설정")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            # 플랫폼 선택
            platform_options = {
                p: PLATFORM_CONFIGS[p].get("display_name", p)
                for p in available_platforms
            }
            selected_platform = persistent_selectbox(
                "플랫폼",
                options=list(platform_options.keys()),
                page=VIDEO_PAGE_ID,
                setting_key="platform",
                format_func=lambda x: platform_options[x]
            )

        with col2:
            # 모델 선택
            i2v_models = get_i2v_models_for_platform(selected_platform)

            if i2v_models:
                model_options = {k: v.display_name for k, v in i2v_models.items()}
                selected_model = persistent_selectbox(
                    "모델",
                    options=list(model_options.keys()),
                    page=VIDEO_PAGE_ID,
                    setting_key="model",
                    format_func=lambda x: model_options[x]
                )
            else:
                st.warning("I2V 모델 없음")
                selected_model = None

        with col3:
            # 비디오 길이
            if selected_model and selected_platform:
                model_config = ALL_MODELS[selected_platform][selected_model]
                available_durations = model_config.durations
            else:
                available_durations = [5]

            duration = persistent_selectbox(
                "영상 길이",
                options=available_durations,
                page=VIDEO_PAGE_ID,
                setting_key="duration",
                format_func=lambda x: f"{x}초"
            )

        with col4:
            # 프롬프트 타입
            prompt_type = st.radio(
                "프롬프트 타입",
                options=["full", "character"],
                format_func=lambda x: "🌆 전체 장면" if x == "full" else "🎭 캐릭터 중심",
                horizontal=True,
                key="ai_video_prompt_type"
            )

        # 비용 예측 표시
        if selected_platform and selected_model:
            estimate = estimate_video_cost(
                platform=selected_platform,
                model_key=selected_model,
                duration=duration,
                resolution="720p"
            )

            if estimate and "error" not in estimate:
                est_col1, est_col2, est_col3 = st.columns(3)

                with est_col1:
                    if estimate["cost_usd"] > 0:
                        st.metric("예상 비용", f"${estimate['cost_usd']:.2f}")
                    else:
                        st.metric("예상 비용", f"{estimate['credits']} 크레딧")

                with est_col2:
                    time_min = estimate.get("time_seconds", 180) // 60
                    st.metric("예상 시간", f"~{time_min}분")

                with est_col3:
                    st.metric("품질", "⭐" * estimate.get("quality_tier", 4))

                if estimate.get("legal_warning"):
                    st.warning(f"⚠️ {estimate['legal_warning']}")

    # ============================================================
    # 씬 선택 섹션
    # ============================================================
    st.markdown("#### 🎬 씬 선택")

    # 이미지가 있는 씬만 필터링
    scenes_with_images = []
    for idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id") or scene.get("scene_num") or (idx + 1)
        image_path = get_scene_image_path(scene, str(project_path))

        if image_path:
            scenes_with_images.append({
                "scene_id": scene_id,
                "scene": scene,
                "image_path": image_path
            })

    if not scenes_with_images:
        st.warning("이미지가 있는 씬이 없습니다. 먼저 이미지를 생성하세요.")
        return

    st.info(f"📊 이미지가 있는 씬: {len(scenes_with_images)}개 / 전체 {len(scenes)}개")

    # 빠른 선택 버튼
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if st.button("✅ 전체 선택", key="ai_video_select_all", use_container_width=True):
            for s in scenes_with_images:
                st.session_state[f"ai_video_select_{s['scene_id']}"] = True
            st.rerun()

    with btn_col2:
        if st.button("❌ 전체 해제", key="ai_video_deselect_all", use_container_width=True):
            for s in scenes_with_images:
                st.session_state[f"ai_video_select_{s['scene_id']}"] = False
            st.rerun()

    with btn_col3:
        # 범위 선택
        range_col1, range_col2, range_col3 = st.columns([2, 1, 2])

        with range_col1:
            range_start = st.number_input(
                "시작",
                min_value=1,
                max_value=len(scenes_with_images),
                value=1,
                key="ai_video_range_start",
                label_visibility="collapsed"
            )

        with range_col2:
            st.markdown("<div style='text-align:center;padding-top:8px;'>~</div>", unsafe_allow_html=True)

        with range_col3:
            range_end = st.number_input(
                "끝",
                min_value=1,
                max_value=len(scenes_with_images),
                value=min(5, len(scenes_with_images)),
                key="ai_video_range_end",
                label_visibility="collapsed"
            )

        if st.button("범위 선택", key="ai_video_apply_range", use_container_width=True):
            for s in scenes_with_images:
                in_range = range_start <= s["scene_id"] <= range_end
                st.session_state[f"ai_video_select_{s['scene_id']}"] = in_range
            st.rerun()

    # 씬 체크박스 그리드
    selected_scenes = []
    cols_count = 6

    with st.expander("📋 씬 선택 (클릭하여 선택)", expanded=True):
        for row_start in range(0, len(scenes_with_images), cols_count):
            row_scenes = scenes_with_images[row_start:row_start + cols_count]
            cols = st.columns(cols_count)

            for col_idx, scene_info in enumerate(row_scenes):
                scene_id = scene_info["scene_id"]
                unique_idx = row_start + col_idx  # 고유 인덱스

                with cols[col_idx]:
                    is_selected = st.checkbox(
                        f"씬 {scene_id}",
                        value=st.session_state.get(f"ai_video_select_{scene_id}", False),
                        key=f"ai_video_cb_{scene_id}_{unique_idx}"
                    )

                    if is_selected:
                        selected_scenes.append(scene_info)
                        st.session_state[f"ai_video_select_{scene_id}"] = True
                    else:
                        st.session_state[f"ai_video_select_{scene_id}"] = False

    # 선택된 씬 수 표시
    if selected_scenes:
        total_cost = len(selected_scenes) * (estimate.get("cost_usd", 0) if estimate else 0)
        st.success(f"✅ {len(selected_scenes)}개 씬 선택됨 | 예상 총 비용: ${total_cost:.2f}")
    else:
        st.warning("⚠️ 선택된 씬이 없습니다.")

    # ============================================================
    # 프롬프트 미리보기
    # ============================================================
    if selected_scenes:
        with st.expander("📝 선택된 씬 프롬프트 미리보기", expanded=False):
            for scene_info in selected_scenes[:5]:  # 처음 5개만
                scene = scene_info["scene"]
                scene_id = scene_info["scene_id"]
                prompt = get_video_prompt_for_scene(scene, prompt_type)

                st.markdown(f"**씬 {scene_id}:**")
                st.code(prompt[:300] + "..." if len(prompt) > 300 else prompt)

            if len(selected_scenes) > 5:
                st.caption(f"... 외 {len(selected_scenes) - 5}개 씬")

    # ============================================================
    # 생성 버튼
    # ============================================================
    st.markdown("---")

    if st.button(
        f"🚀 {len(selected_scenes)}개 씬 AI 비디오 생성",
        type="primary",
        use_container_width=True,
        disabled=len(selected_scenes) == 0 or not selected_model,
        key="ai_video_generate"
    ):
        # ⭐ v2.4: 향상된 프로그레스 표시
        progress_container = st.container()
        with progress_container:
            progress_bar = st.progress(0)
            col_status, col_count = st.columns([3, 1])
            status_text = col_status.empty()
            count_text = col_count.empty()

        # 예상 비용 (단가)
        unit_cost = estimate.get("cost_usd", 0) if estimate else 0

        def progress_callback(current, total, message):
            progress_pct = (current + 1) / total if total > 0 else 0
            progress_bar.progress(progress_pct)
            status_text.text(message)
            count_text.markdown(f"**{current + 1}/{total}** ({int(progress_pct * 100)}%)")

        # 선택된 씬의 scene 데이터 리스트 추출
        scenes_to_process = [s["scene"] for s in selected_scenes]

        with st.spinner("AI 비디오 생성 중..."):
            results = batch_generate_scene_videos(
                scenes=scenes_to_process,
                project_path=str(project_path),
                platform=selected_platform,
                model_key=selected_model,
                prompt_type=prompt_type,
                duration=duration,
                resolution="720p",
                progress_callback=progress_callback
            )

        progress_bar.progress(1.0)
        status_text.text("✅ 완료!")
        count_text.markdown(f"**{len(selected_scenes)}/{len(selected_scenes)}** (100%)")

        # 결과 표시
        success_count = sum(1 for r in results if r.get("success"))
        fail_count = len(results) - success_count
        total_cost = sum(r.get("cost_usd", 0) for r in results if r.get("success"))
        total_time = sum(r.get("generation_time", 0) for r in results if r.get("success"))

        if success_count > 0:
            st.success(f"✅ {success_count}개 비디오 생성 성공! (총 비용: ${total_cost:.2f}, 총 시간: {total_time:.1f}초)")

        if fail_count > 0:
            st.error(f"❌ {fail_count}개 비디오 생성 실패")

            with st.expander("실패 상세"):
                for r in results:
                    if not r.get("success"):
                        st.markdown(f"- 씬 {r.get('scene_id')}: {r.get('error')}")

        # ⭐ v2.4: 성공 결과 상세 정보 (프롬프트 뷰어 포함)
        success_results = [r for r in results if r.get("success")]
        if success_results:
            with st.expander("📝 생성 상세 정보 및 사용된 프롬프트", expanded=False):
                for r in success_results:
                    scene_id = r.get("scene_id", "?")
                    st.markdown(f"### 씬 {scene_id}")

                    col1, col2 = st.columns([1, 2])

                    with col1:
                        st.markdown(f"**모델:** {r.get('model', 'N/A')}")
                        st.markdown(f"**비용:** ${r.get('cost_usd', 0):.3f}")
                        st.markdown(f"**생성 시간:** {r.get('generation_time', 0):.1f}초")

                    with col2:
                        # 프롬프트 정보
                        original_prompt = r.get("original_prompt", "")
                        final_prompt = r.get("final_prompt", "")
                        prompt_expanded = r.get("prompt_expanded", False)

                        if prompt_expanded:
                            st.info("🔄 프롬프트가 AI에 의해 확장되었습니다")

                        st.markdown("**원본 프롬프트:**")
                        st.code(original_prompt[:200] + "..." if len(original_prompt) > 200 else original_prompt, language=None)

                        if final_prompt and final_prompt != original_prompt:
                            st.markdown("**최종 프롬프트 (AI 확장):**")
                            st.code(final_prompt[:300] + "..." if len(final_prompt) > 300 else final_prompt, language=None)

                    st.divider()

        # 세션에 결과 저장 (나중에 확인용)
        if "video_generation_history" not in st.session_state:
            st.session_state.video_generation_history = []
        st.session_state.video_generation_history.extend(results)

        st.rerun()

    # ============================================================
    # 생성된 AI 비디오 미리보기
    # ============================================================
    ai_videos_dir = Path(project_path) / "videos" / "ai_generated"

    if ai_videos_dir.exists():
        video_files = sorted([f for f in ai_videos_dir.glob("*.mp4")])

        if video_files:
            with st.expander(f"🎬 생성된 AI 비디오 ({len(video_files)}개)", expanded=True):
                cols_per_row = 3

                for row_start in range(0, len(video_files), cols_per_row):
                    row_files = video_files[row_start:row_start + cols_per_row]
                    cols = st.columns(cols_per_row)

                    for col_idx, video_file in enumerate(row_files):
                        with cols[col_idx]:
                            st.video(str(video_file))
                            st.caption(video_file.name)

                            # 삭제 버튼
                            if st.button("🗑️", key=f"delete_ai_video_{video_file.name}"):
                                video_file.unlink()
                                st.rerun()


# ============================================================
# 배경 이미지 대체 섹션
# ============================================================

def render_background_replacement_section(infographic_data, project_path, visual_manager):
    """배경 이미지 대체 섹션 렌더링"""

    try:
        from utils.html_background_replacer import (
            HTMLBackgroundReplacer,
            get_project_images,
            get_infographic_images
        )
    except ImportError:
        st.warning("배경 대체 모듈을 로드할 수 없습니다.")
        return

    st.markdown("### 🖼️ 2.5 배경 이미지 대체")
    st.caption("인포그래픽 HTML에 배경 이미지를 추가합니다.")

    # HTML 내용 확인
    html_content = infographic_data.html_code if hasattr(infographic_data, 'html_code') else None

    if not html_content:
        # 소스 파일에서 로드 시도
        source_path = infographic_data.source_path if hasattr(infographic_data, 'source_path') else None
        if source_path and os.path.exists(source_path):
            try:
                with open(source_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            except Exception as e:
                st.warning(f"HTML 파일 로드 실패: {e}")
                return
        else:
            st.warning("인포그래픽 HTML 콘텐츠를 찾을 수 없습니다.")
            return

    # 설명
    with st.expander("💡 배경 이미지 대체란?", expanded=False):
        st.markdown("""
        **인포그래픽 배경 이미지 대체** 기능은:

        - 인포그래픽 HTML의 흰색 배경을 이미지로 대체합니다
        - 이미지는 반투명하게 적용되어 텍스트가 잘 보입니다
        - 프로젝트에서 생성한 인포그래픽용 이미지를 사용할 수 있습니다

        ```
        적용 전:                     적용 후:
        ┌─────────────────┐         ┌─────────────────┐
        │    흰색 배경     │         │ ░░░░░░░░░░░░░░░│
        │  [인포그래픽]   │    →    │ ░ [인포그래픽] ░│
        │    콘텐츠       │         │ ░   콘텐츠     ░│
        └─────────────────┘         └─────────────────┘
        ```
        """)

    # 배경 대체 모드 선택
    replace_mode = st.radio(
        "배경 대체 방식",
        options=[
            "🌐 전체 동일 배경",
            "🎭 씬별 개별 배경"
        ],
        key="bg_replace_mode",
        horizontal=True
    )

    if "전체 동일" in replace_mode:
        _render_global_background_options(html_content, project_path, infographic_data, visual_manager)
    else:
        _render_scene_background_options(html_content, project_path, infographic_data, visual_manager)


def _render_global_background_options(html_content, project_path, infographic_data, visual_manager):
    """전체 동일 배경 옵션"""

    from utils.html_background_replacer import HTMLBackgroundReplacer, get_project_images, get_infographic_images

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("#### 📁 배경 이미지 선택")

        # 이미지 소스 선택
        image_source = st.radio(
            "이미지 소스",
            options=[
                "📊 인포그래픽용 이미지",
                "📂 프로젝트 전체 이미지",
                "📤 파일 업로드"
            ],
            key="bg_image_source",
            horizontal=True
        )

        selected_image = None

        if "인포그래픽용" in image_source:
            # 인포그래픽용 이미지 목록
            infographic_images = get_infographic_images(str(project_path))

            if infographic_images:
                st.markdown("**사용 가능한 인포그래픽 이미지:**")

                # 이미지 그리드 (확대 기능 포함)
                cols = st.columns(4)
                for idx, img_path in enumerate(infographic_images[:12]):
                    with cols[idx % 4]:
                        if os.path.exists(img_path):
                            st.image(img_path, width=120)
                            btn_c1, btn_c2 = st.columns(2)
                            with btn_c1:
                                if st.button("선택", key=f"select_infographic_bg_{idx}", use_container_width=True):
                                    st.session_state["selected_bg_image"] = img_path
                                    st.rerun()
                            with btn_c2:
                                if st.button("🔍", key=f"zoom_infographic_bg_{idx}", help="확대"):
                                    st.session_state[f"zoom_infographic_{idx}"] = True
                            # 확대 모달
                            if st.session_state.get(f"zoom_infographic_{idx}", False):
                                from utils.image_viewer import show_image_modal
                                show_image_modal(img_path, idx + 1, None, f"인포그래픽 {idx + 1}")
                                st.session_state[f"zoom_infographic_{idx}"] = False

                selected_image = st.session_state.get("selected_bg_image")

                if selected_image:
                    st.success(f"선택됨: {os.path.basename(selected_image)}")
            else:
                st.info("인포그래픽용 이미지가 없습니다. '이미지 생성' 페이지의 인포그래픽 탭에서 생성하세요.")

        elif "프로젝트 전체" in image_source:
            # 프로젝트 내 모든 이미지
            project_images = get_project_images(str(project_path))

            if project_images:
                # 드롭다운으로 선택
                img_options = ["(선택하세요)"] + [os.path.basename(p) for p in project_images]
                selected_name = st.selectbox(
                    "이미지 선택",
                    options=img_options,
                    key="project_bg_select"
                )

                if selected_name and selected_name != "(선택하세요)":
                    for p in project_images:
                        if os.path.basename(p) == selected_name:
                            selected_image = p
                            break

                    if selected_image and os.path.exists(selected_image):
                        st.image(selected_image, width=200)
                        if st.button("🔍 확대", key="zoom_project_img"):
                            from utils.image_viewer import show_image_modal
                            show_image_modal(selected_image, 0, None, "선택된 이미지")
            else:
                st.warning("프로젝트에 이미지가 없습니다.")

        else:
            # 파일 업로드
            uploaded = st.file_uploader(
                "배경 이미지 업로드",
                type=["png", "jpg", "jpeg", "webp"],
                key="bg_upload"
            )

            if uploaded:
                # 임시 저장
                import tempfile
                temp_dir = Path(tempfile.gettempdir()) / "longform_temp"
                temp_dir.mkdir(exist_ok=True)
                temp_path = temp_dir / uploaded.name

                with open(temp_path, "wb") as f:
                    f.write(uploaded.getbuffer())

                selected_image = str(temp_path)
                st.image(selected_image, width=200)
                if st.button("🔍 확대", key="zoom_uploaded_img"):
                    from utils.image_viewer import show_image_modal
                    show_image_modal(selected_image, 0, None, "업로드된 이미지")

    with col2:
        st.markdown("#### ⚙️ 옵션")

        opacity = st.slider(
            "🔅 배경 투명도",
            min_value=0.0,
            max_value=1.0,
            value=0.3,
            step=0.05,
            key="bg_opacity",
            help="0 = 투명, 1 = 불투명"
        )

        st.caption(f"현재: {int(opacity * 100)}%")

        blend_mode = st.selectbox(
            "🎨 블렌드 모드",
            options=["normal", "multiply", "screen", "overlay", "soft-light"],
            key="bg_blend_mode"
        )

        position = st.selectbox(
            "📍 배경 위치",
            options=["center", "top", "bottom", "left", "right",
                     "top left", "top right", "bottom left", "bottom right"],
            key="bg_position"
        )

        # 배경 크기 옵션 (개선됨)
        from utils.html_background_replacer import get_background_size_options
        size_options = get_background_size_options()

        size = st.selectbox(
            "📐 배경 크기",
            options=[opt["id"] for opt in size_options],
            format_func=lambda x: next(
                (opt["name"] for opt in size_options if opt["id"] == x), x
            ),
            index=0,  # 기본값: cover (전체 채움)
            key="bg_size"
        )

        # 선택된 옵션 설명 표시
        selected_size_opt = next(
            (opt for opt in size_options if opt["id"] == size), None
        )
        if selected_size_opt:
            st.caption(f"ℹ️ {selected_size_opt['description']}")

    # 적용 버튼
    st.markdown("---")

    col_apply, col_download = st.columns(2)

    with col_apply:
        if st.button(
            "🎨 배경 이미지 적용",
            type="primary",
            disabled=not selected_image,
            use_container_width=True,
            key="apply_bg_btn"
        ):
            if selected_image and os.path.exists(selected_image):
                with st.spinner("배경 이미지 적용 중..."):
                    replacer = HTMLBackgroundReplacer(html_content)
                    modified_html = replacer.replace_global_background(
                        image_path=selected_image,
                        opacity=opacity,
                        blend_mode=blend_mode,
                        position=position,
                        size=size
                    )

                    # 세션에 저장
                    st.session_state["modified_infographic_html"] = modified_html

                    # 파일로도 저장
                    output_path = project_path / "infographics" / "infographic_with_background.html"
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(modified_html)

                    st.success(f"배경 이미지가 적용되었습니다!")
                    st.caption(f"저장 위치: {output_path}")

                    # 결과 미리보기
                    _render_modified_html_preview(modified_html, output_path)

    with col_download:
        modified_html = st.session_state.get("modified_infographic_html")
        if modified_html:
            st.download_button(
                label="💾 수정된 HTML 다운로드",
                data=modified_html,
                file_name="infographic_with_background.html",
                mime="text/html",
                use_container_width=True
            )


def _render_scene_background_options(html_content, project_path, infographic_data, visual_manager):
    """씬별 개별 배경 옵션 (체크박스 + 벌크 선택 지원)"""

    from utils.html_background_replacer import (
        HTMLBackgroundReplacer, get_project_images, get_infographic_images,
        get_background_size_options
    )

    st.markdown("#### 📋 씬별 배경 이미지 설정")

    # 프로젝트 이미지 로드
    infographic_images = get_infographic_images(str(project_path))
    project_images = get_project_images(str(project_path))
    all_images = infographic_images + [p for p in project_images if p not in infographic_images]

    if not all_images:
        st.warning("프로젝트 내 이미지가 없습니다. 먼저 이미지를 생성해주세요.")
        return

    # 씬 정보
    scene_count = infographic_data.total_scenes if hasattr(infographic_data, 'total_scenes') else len(infographic_data.scenes)

    # ============================================================
    # 벌크 선택 버튼
    # ============================================================
    st.markdown("**🎯 씬 선택 관리:**")

    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

    with btn_col1:
        if st.button("✅ 전체 선택", key="select_all_scenes_btn", use_container_width=True):
            for i in range(1, scene_count + 1):
                st.session_state[f"scene_bg_enabled_{i}"] = True
            st.rerun()

    with btn_col2:
        if st.button("❌ 전체 해제", key="deselect_all_scenes_btn", use_container_width=True):
            for i in range(1, scene_count + 1):
                st.session_state[f"scene_bg_enabled_{i}"] = False
            st.rerun()

    with btn_col3:
        if st.button("🔄 자동 매칭", key="auto_match_scenes_btn", use_container_width=True):
            # 씬 번호 기반 자동 매칭
            matched_count = 0
            for i in range(1, scene_count + 1):
                matched_img = None
                for img_path in all_images:
                    img_name = os.path.basename(img_path).lower()
                    patterns = [f"scene_{i:03d}", f"scene_{i:02d}", f"scene_{i}", f"scene{i:03d}", f"scene{i}"]
                    if any(pattern in img_name for pattern in patterns):
                        matched_img = os.path.basename(img_path)
                        break

                if matched_img:
                    st.session_state[f"scene_bg_enabled_{i}"] = True
                    st.session_state[f"scene_bg_image_{i}"] = matched_img
                    matched_count += 1
                else:
                    st.session_state[f"scene_bg_enabled_{i}"] = False
                    st.session_state[f"scene_bg_image_{i}"] = "(선택 안함)"

            st.toast(f"🔄 {matched_count}개 씬 자동 매칭 완료!")
            st.rerun()

    with btn_col4:
        if st.button("🖼️ 매칭된 씬만", key="select_matched_only_btn", use_container_width=True):
            # 이미지가 선택된 씬만 활성화
            img_options_set = set(os.path.basename(p) for p in all_images)
            for i in range(1, scene_count + 1):
                selected_img = st.session_state.get(f"scene_bg_image_{i}", "(선택 안함)")
                if selected_img and selected_img != "(선택 안함)" and selected_img in img_options_set:
                    st.session_state[f"scene_bg_enabled_{i}"] = True
                else:
                    st.session_state[f"scene_bg_enabled_{i}"] = False
            st.rerun()

    # ============================================================
    # 선택 현황 표시
    # ============================================================
    selected_count = sum(
        1 for i in range(1, scene_count + 1)
        if st.session_state.get(f"scene_bg_enabled_{i}", False)
        and st.session_state.get(f"scene_bg_image_{i}", "(선택 안함)") != "(선택 안함)"
    )

    st.info(f"📊 **적용 대상: {selected_count}개** / {scene_count}개 씬 선택됨")

    st.markdown("---")

    # ============================================================
    # 공통 설정
    # ============================================================
    col1, col2, col3 = st.columns(3)

    with col1:
        opacity = st.slider(
            "🔅 공통 투명도",
            min_value=0.0,
            max_value=1.0,
            value=0.3,
            step=0.05,
            key="scene_bg_opacity"
        )

    with col2:
        blend_mode = st.selectbox(
            "🎨 공통 블렌드 모드",
            options=["normal", "multiply", "screen", "overlay", "soft-light"],
            key="scene_bg_blend"
        )

    with col3:
        # 배경 크기 옵션
        size_options = get_background_size_options()
        scene_bg_size = st.selectbox(
            "📐 공통 배경 크기",
            options=[opt["id"] for opt in size_options],
            format_func=lambda x: next(
                (opt["name"] for opt in size_options if opt["id"] == x), x
            ),
            index=0,  # 기본값: cover
            key="scene_bg_size"
        )

    st.markdown("---")

    # ============================================================
    # 씬별 선택 UI (체크박스 + 드롭다운)
    # ============================================================
    st.markdown("**씬별 이미지 선택:**")

    img_options = ["(선택 안함)"] + [os.path.basename(p) for p in all_images]
    img_path_map = {os.path.basename(p): p for p in all_images}

    # 씬 목록을 스크롤 가능한 컨테이너로 표시
    scene_container = st.container()

    with scene_container:
        for i in range(1, scene_count + 1):
            scene_data = infographic_data.scenes[i - 1] if i <= len(infographic_data.scenes) else None
            scene_title = scene_data.text[:25] if scene_data and hasattr(scene_data, 'text') else f"씬 {i}"

            col_check, col_info, col_select, col_preview = st.columns([0.5, 1.5, 3, 0.8])

            with col_check:
                # 체크박스: 이 씬에 배경 적용 여부
                is_enabled = st.checkbox(
                    "",
                    value=st.session_state.get(f"scene_bg_enabled_{i}", False),
                    key=f"scene_bg_enabled_{i}",
                    label_visibility="collapsed"
                )

            with col_info:
                st.markdown(f"**📍 씬 {i}**")
                st.caption(scene_title[:20] + "..." if len(scene_title) > 20 else scene_title)

            with col_select:
                # 현재 선택값
                current_img = st.session_state.get(f"scene_bg_image_{i}", "(선택 안함)")
                if current_img not in img_options:
                    current_img = "(선택 안함)"

                selected = st.selectbox(
                    f"씬 {i} 배경",
                    options=img_options,
                    index=img_options.index(current_img) if current_img in img_options else 0,
                    key=f"scene_bg_image_{i}",
                    label_visibility="collapsed",
                    disabled=not is_enabled
                )

            with col_preview:
                # 선택된 이미지 미리보기
                if is_enabled and selected and selected != "(선택 안함)":
                    img_path = img_path_map.get(selected)
                    if img_path and os.path.exists(img_path):
                        st.image(img_path, width=60)
                else:
                    st.caption("-")

    # 적용 버튼
    st.markdown("---")

    # ✅ 체크박스가 활성화되고 이미지가 선택된 씬만 추출
    scene_images = {}
    for i in range(1, scene_count + 1):
        if not st.session_state.get(f"scene_bg_enabled_{i}", False):
            continue
        selected_img_name = st.session_state.get(f"scene_bg_image_{i}", "(선택 안함)")
        if selected_img_name and selected_img_name != "(선택 안함)":
            img_path = img_path_map.get(selected_img_name)
            if img_path and os.path.exists(img_path):
                scene_images[i] = img_path

    apply_count = len(scene_images)

    col_apply, col_download = st.columns(2)

    with col_apply:
        if st.button(
            f"🎨 {apply_count}개 씬 배경 적용",
            type="primary",
            disabled=apply_count == 0,
            use_container_width=True,
            key="apply_scene_bg_btn"
        ):
            with st.spinner("씬별 배경 이미지 적용 중..."):
                replacer = HTMLBackgroundReplacer(html_content)
                modified_html = replacer.replace_scene_backgrounds(
                    scene_images=scene_images,
                    opacity=opacity,
                    blend_mode=blend_mode,
                    size=scene_bg_size
                )

                # 세션에 저장
                st.session_state["modified_infographic_html"] = modified_html

                # 파일로도 저장
                output_path = project_path / "infographics" / "infographic_with_scene_backgrounds.html"
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(modified_html)

                st.success(f"{apply_count}개 씬 배경이 적용되었습니다!")
                st.caption(f"저장 위치: {output_path}")

                # 결과 미리보기
                _render_modified_html_preview(modified_html, output_path)

    with col_download:
        modified_html = st.session_state.get("modified_infographic_html")
        if modified_html:
            st.download_button(
                label="💾 수정된 HTML 다운로드",
                data=modified_html,
                file_name="infographic_with_scene_backgrounds.html",
                mime="text/html",
                use_container_width=True
            )


def _render_modified_html_preview(modified_html: str, output_path):
    """수정된 HTML 미리보기 - 씬별 프리뷰 지원"""

    import streamlit.components.v1 as components
    from utils.html_background_replacer import HTMLBackgroundReplacer

    st.markdown("### 👁️ 결과 미리보기")

    # 씬 정보 파싱
    try:
        replacer = HTMLBackgroundReplacer(modified_html)
        scenes_info = replacer.get_scenes_info()
    except Exception:
        scenes_info = []

    # 탭 구성
    preview_tabs = st.tabs(["📋 씬별 미리보기", "🖥️ 전체 미리보기", "📄 HTML 코드"])

    # ============================================================
    # 탭 1: 씬별 미리보기
    # ============================================================
    with preview_tabs[0]:
        if not scenes_info:
            st.info("씬 정보를 파싱할 수 없습니다. 전체 미리보기를 확인하세요.")
        else:
            st.markdown(f"**총 {len(scenes_info)}개 씬 - 클릭하여 개별 미리보기:**")

            for scene in scenes_info:
                scene_idx = scene.get("index", 0)
                scene_id = scene.get("id", f"scene{scene_idx}")
                scene_title = scene.get("title", f"씬 {scene_idx}")[:40]

                # 기본 닫힘 상태의 expander
                with st.expander(
                    f"📍 씬 {scene_idx}: {scene_title}",
                    expanded=False
                ):
                    _render_single_scene_preview(
                        modified_html=modified_html,
                        scene_id=scene_id,
                        scene_idx=scene_idx
                    )

    # ============================================================
    # 탭 2: 전체 미리보기
    # ============================================================
    with preview_tabs[1]:
        st.markdown("**전체 인포그래픽 미리보기:**")

        # 높이 조절 옵션
        preview_height = st.slider(
            "미리보기 높이",
            min_value=300,
            max_value=800,
            value=500,
            step=50,
            key="full_preview_height"
        )

        try:
            components.html(
                modified_html,
                height=preview_height,
                scrolling=True
            )
        except Exception as e:
            st.warning(f"미리보기 렌더링 실패: {e}")
            st.info(f"저장된 파일을 브라우저에서 열어 확인하세요: {output_path}")

    # ============================================================
    # 탭 3: HTML 코드
    # ============================================================
    with preview_tabs[2]:
        st.markdown("**수정된 HTML 코드:**")
        st.caption(f"총 {len(modified_html):,} 문자")

        with st.expander("HTML 코드 보기", expanded=False):
            code_preview = modified_html[:5000] + ("..." if len(modified_html) > 5000 else "")
            st.code(code_preview, language="html")

        st.download_button(
            "💾 HTML 파일 다운로드",
            data=modified_html,
            file_name="infographic_with_background.html",
            mime="text/html",
            use_container_width=True
        )


def _render_single_scene_preview(modified_html: str, scene_id: str, scene_idx: int):
    """단일 씬 미리보기 렌더링 (잘림 문제 해결 - 스케일 조절)"""

    import streamlit.components.v1 as components
    import json

    # ✅ 스케일 조절을 통한 전체 보기 (1280x720 → 축소)
    # 표시 너비 700px 기준, 스케일 = 700/1280 ≈ 0.547
    scale_factor = 0.55
    display_width = int(1280 * scale_factor)  # 704px
    display_height = int(720 * scale_factor)  # 396px

    # 래퍼 HTML: 원본 HTML을 iframe srcdoc으로 로드하고 스케일 조절
    wrapper_html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}

            body {{
                background: #e5e7eb;
                display: flex;
                justify-content: center;
                align-items: flex-start;
                padding: 8px;
                min-height: 100%;
                overflow: hidden;
            }}

            .preview-container {{
                width: {display_width}px;
                height: {display_height}px;
                overflow: hidden;
                background: white;
                border-radius: 8px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.15);
                position: relative;
            }}

            .preview-scaler {{
                width: 1280px;
                height: 720px;
                transform: scale({scale_factor});
                transform-origin: top left;
                position: absolute;
                top: 0;
                left: 0;
            }}

            .preview-scaler iframe {{
                width: 1280px;
                height: 720px;
                border: none;
            }}
        </style>
    </head>
    <body>
        <div class="preview-container">
            <div class="preview-scaler">
                <iframe id="scene-frame" srcdoc=""></iframe>
            </div>
        </div>

        <script>
            // 원본 HTML 콘텐츠
            const originalHtml = {json.dumps(modified_html)};

            // 해당 씬만 표시하는 스크립트
            const sceneOnlyScript = `
                <script>
                    (function() {{
                        // 모든 씬 숨기기
                        document.querySelectorAll('.scene').forEach(function(s) {{
                            s.classList.remove('active');
                            s.style.display = 'none';
                        }});

                        // 대상 씬만 표시
                        var target = document.getElementById('{scene_id}');
                        if (target) {{
                            target.classList.add('active');
                            target.style.display = 'flex';
                        }}

                        // 네비게이션 숨기기
                        document.querySelectorAll('.nav-btn, .progress-outer, .scene-counter').forEach(function(el) {{
                            if (el) el.style.display = 'none';
                        }});
                    }})();

                    document.addEventListener('DOMContentLoaded', function() {{
                        document.querySelectorAll('.scene').forEach(function(s) {{
                            s.classList.remove('active');
                            s.style.display = 'none';
                        }});

                        var target = document.getElementById('{scene_id}');
                        if (target) {{
                            target.classList.add('active');
                            target.style.display = 'flex';
                        }}

                        document.querySelectorAll('.nav-btn, .progress-outer, .scene-counter').forEach(function(el) {{
                            if (el) el.style.display = 'none';
                        }});
                    }});
                <\\/script>
            `;

            // HTML에 스크립트 삽입
            let modifiedContent = originalHtml;
            if (modifiedContent.includes('</body>')) {{
                modifiedContent = modifiedContent.replace('</body>', sceneOnlyScript + '</body>');
            }} else {{
                modifiedContent += sceneOnlyScript;
            }}

            // iframe에 로드
            document.getElementById('scene-frame').srcdoc = modifiedContent;
        </script>
    </body>
    </html>
    '''

    col1, col2 = st.columns([3, 1])

    with col1:
        # ✅ 스케일 조절된 씬 미리보기 (16:9 비율 유지, 잘림 없음)
        # 컨테이너 높이 = display_height + 패딩
        container_height = display_height + 20

        components.html(
            wrapper_html,
            height=container_height,
            scrolling=False
        )

    with col2:
        st.markdown(f"**씬 {scene_idx}**")
        st.markdown(f"ID: `{scene_id}`")
        st.caption("💡 썸네일 생성 섹션에서\n이 씬을 캡처할 수 있습니다.")


# 페이지 설정
st.set_page_config(
    page_title="스토리보드",
    page_icon="📋",
    layout="wide"
)

# ============================================================
# 미디어 캐시 초기화 (MediaFileStorageError 방지)
# ============================================================
def init_media_cache():
    """미디어 캐시 초기화 및 정리"""
    if "media_cache_initialized" not in st.session_state:
        st.session_state["media_cache_initialized"] = True
        st.session_state["loaded_images"] = {}  # 이미지 캐시
        st.session_state["image_load_times"] = {}  # 로드 시간 추적

        # 기존 미디어 캐시 정리 (Streamlit 내부 캐시)
        try:
            # MediaFileStorageError 방지를 위한 세션 정리
            keys_to_remove = []
            for key in st.session_state.keys():
                # 업로드된 파일 참조 제거 (만료된 참조 방지)
                if '_uploader' in key.lower() or 'uploaded_file' in key.lower():
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                try:
                    del st.session_state[key]
                except Exception:
                    pass
        except Exception:
            pass

        # ⭐ 성능 최적화: 초기화 로그 제거 (불필요한 콘솔 출력 방지)
        # print("[DEBUG] 미디어 캐시 초기화 완료", flush=True)

# 캐시 초기화 호출
init_media_cache()

# ============================================================
# 이미지 로딩 캐시 (중복 로드 방지)
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)  # ⭐ TTL 5분으로 증가
def load_image_files_cached(backgrounds_dir: str, scenes_dir: str, content_dir: str, cache_key: str = "") -> tuple:
    """
    이미지 파일 목록 캐싱 (중복 로드 방지)

    Args:
        backgrounds_dir: 배경 이미지 폴더
        scenes_dir: 씬 이미지 폴더
        content_dir: 콘텐츠 이미지 폴더
        cache_key: 캐시 무효화용 키 (폴더 mtime 등) - v2.3: _cache_key → cache_key (해시 포함)
    """
    import re

    image_files = []

    # ⭐ v2.3: 실사 이미지 폴더 추가 (우선순위 최상위)
    # 우선순위: real > backgrounds > scenes > content
    real_dir = Path(backgrounds_dir).parent / "real"  # images/real
    dirs_to_search = [
        (real_dir, "real"),  # ⭐ 실사 이미지 최우선
        (Path(backgrounds_dir), "backgrounds"),
        (Path(scenes_dir), "scenes"),
        (Path(content_dir), "content"),
    ]

    for dir_path, source in dirs_to_search:
        if dir_path.exists():
            for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                for img in dir_path.glob(ext):
                    try:
                        mtime = img.stat().st_mtime
                        image_files.append((img, mtime))
                    except (OSError, IOError):
                        continue

    # ⭐ 핵심 수정: 수정 시간 기준 내림차순 정렬 (최신 이미지 먼저!)
    image_files.sort(key=lambda x: x[1], reverse=True)

    # 중복 제거 (같은 씬 번호 파일이 있으면 최신 이미지 사용)
    # ⭐ 씬 번호 기반 중복 제거 (bg_scene_001, scene_001 → 001로 통합)
    seen_scene_ids = set()
    unique_images = []

    # ⭐ v2.3: 실사 이미지 패턴 추가 (real_scene_002.jpg 등)
    # 씬 번호 추출 패턴 (AI 매핑 파일명 "001_scene.jpg" 포함)
    patterns = [r'real[_-]?scene[_-]?(\d+)', r'bg[_-]?scene[_-]?(\d+)', r'scene[_-]?(\d+)', r'^(\d+)[_-]', r'^(\d+)$', r'[_-](\d+)$']

    for img, mtime in image_files:
        # 씬 번호 추출
        scene_num = None
        name = img.stem.lower()

        for p in patterns:
            m = re.search(p, name)
            if m:
                scene_num = int(m.group(1))
                break

        # 씬 번호가 없거나 처음 보는 씬 번호면 추가
        # (이미 mtime 정렬되어 있으므로 처음 만나는 것이 최신)
        if scene_num is None or scene_num not in seen_scene_ids:
            unique_images.append(str(img))
            if scene_num is not None:
                seen_scene_ids.add(scene_num)

    image_map = {Path(img).stem: img for img in unique_images}

    # ⭐ 성능 최적화: 캐시 내 로그 완전 제거 (Streamlit rerun마다 출력 방지)
    # 디버깅 필요 시에만 활성화:
    # print(f"[DEBUG] 이미지 캐시 로드: {len(unique_images)}개", flush=True)

    return tuple(unique_images), image_map


def get_image_dirs_mtime(project_path: Path) -> str:
    """
    이미지 캐시 키 반환 (세션 기반)

    성능 개선: 매 렌더링마다 파일 mtime 읽지 않고,
    invalidate_all_image_caches() 호출 시에만 캐시 무효화
    """
    # 세션 기반 캐시 버전 (invalidate 시 증가)
    cache_version = st.session_state.get("image_cache_version", 0)

    # 프로젝트 경로도 포함 (프로젝트 전환 시 캐시 갱신)
    project_key = str(project_path).replace("\\", "/")

    return f"{project_key}_{cache_version}"


def get_paginated_scenes(scenes: list, page: int, per_page: int = 10) -> tuple:
    """씬 목록 페이지네이션"""
    total_pages = (len(scenes) + per_page - 1) // per_page
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, len(scenes))
    return scenes[start_idx:end_idx], start_idx, end_idx, total_pages

render_project_sidebar()
show_api_status_sidebar()

if not ensure_project_selected():
    st.stop()

project_path = get_current_project()
project_config = get_current_project_config()
Profiler.log("🗂️ 프로젝트 로드 완료")

st.title("📋 8단계: 스토리보드")
st.caption("씬별 이미지, 스크립트, TTS를 한눈에 확인하고 편집")

# 라이트박스 컨테이너 (이미지 클릭 확대용)
render_lightbox_container()

st.divider()

# === 탭 구성 ===
if INFOGRAPHIC_AVAILABLE:
    tab_auto, tab_infographic, tab_manual = st.tabs(["🔄 자동 조합", "📊 인포그래픽", "✏️ 수동 구성"])
else:
    tab_auto, tab_manual = st.tabs(["🔄 자동 조합", "✏️ 수동 구성"])
    tab_infographic = None

# === 수동 구성 탭 ===
with tab_manual:
    st.subheader("✏️ 수동 스토리보드 구성")

    st.info("""
    💡 **수동 구성 모드**
    - 외부에서 준비한 컴포넌트를 업로드하여 스토리보드 구성
    - 씬 데이터, 이미지, 스크립트를 직접 업로드 가능
    """)

    # 구성 방식 선택
    manual_compose_method = st.radio(
        "구성 방식",
        ["📁 씬 JSON 업로드", "✏️ 스크립트로 씬 생성", "🖼️ 이미지와 텍스트 매핑"],
        horizontal=True,
        key="manual_compose_method"
    )

    manual_scenes = []

    if manual_compose_method == "📁 씬 JSON 업로드":
        st.markdown("#### 씬 JSON 파일 업로드")
        uploaded_scenes = st.file_uploader(
            "scenes.json 파일",
            type=["json"],
            help="씬 분석 결과 JSON 파일 (scene_id, script_text, duration_estimate 등)",
            key="manual_scenes_upload"
        )

        if uploaded_scenes:
            try:
                content = uploaded_scenes.read().decode("utf-8")
                manual_scenes = json.loads(content)

                if manual_scenes:
                    st.success(f"✅ {len(manual_scenes)}개 씬 로드됨")
                    with st.expander("씬 미리보기"):
                        for i, s in enumerate(manual_scenes[:5]):
                            st.text(f"씬 {s.get('scene_id', i+1)}: {s.get('script_text', '')[:50]}...")
                        if len(manual_scenes) > 5:
                            st.caption(f"... 외 {len(manual_scenes) - 5}개")

            except Exception as e:
                st.error(f"JSON 파싱 오류: {str(e)}")

    elif manual_compose_method == "✏️ 스크립트로 씬 생성":
        st.markdown("#### 스크립트 입력")
        st.caption("줄바꿈으로 씬 구분, 또는 '---' 구분자 사용")

        manual_script_text = st.text_area(
            "스크립트",
            height=200,
            placeholder="첫 번째 씬 대사입니다.\n---\n두 번째 씬 대사입니다.\n---\n세 번째 씬 대사입니다.",
            key="manual_storyboard_script"
        )

        # 기본 씬 설정
        col1, col2 = st.columns(2)
        with col1:
            default_duration = st.number_input("기본 씬 길이 (초)", min_value=5, max_value=60, value=10, key="manual_default_duration")
        with col2:
            scene_separator = st.selectbox("씬 구분자", ["---", "빈 줄 (2줄 이상)", "한 줄 = 한 씬"], key="scene_separator")

        if manual_script_text.strip():
            # 씬 분리
            if scene_separator == "---":
                script_parts = [p.strip() for p in manual_script_text.split("---") if p.strip()]
            elif scene_separator == "빈 줄 (2줄 이상)":
                import re
                script_parts = [p.strip() for p in re.split(r'\n\s*\n', manual_script_text) if p.strip()]
            else:  # 한 줄 = 한 씬
                script_parts = [p.strip() for p in manual_script_text.strip().split("\n") if p.strip()]

            manual_scenes = []
            for i, script in enumerate(script_parts):
                manual_scenes.append({
                    "scene_id": i + 1,
                    "script_text": script,
                    "duration_estimate": default_duration,
                    "direction_guide": "",
                    "characters": [],
                    "mood": ""
                })

            st.info(f"📝 {len(manual_scenes)}개 씬 감지됨")

    elif manual_compose_method == "🖼️ 이미지와 텍스트 매핑":
        st.markdown("#### 이미지 업로드")
        uploaded_images = st.file_uploader(
            "이미지 파일들",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="manual_storyboard_images"
        )

        if uploaded_images:
            st.success(f"✅ {len(uploaded_images)}개 이미지 업로드됨")

            st.markdown("#### 각 이미지에 대한 스크립트")
            manual_scripts = st.text_area(
                "스크립트 (줄바꿈으로 구분, 이미지 순서대로)",
                height=150,
                placeholder="첫 번째 이미지 대사\n두 번째 이미지 대사\n...",
                key="manual_image_scripts"
            )

            script_lines = [s.strip() for s in manual_scripts.split("\n") if s.strip()] if manual_scripts else []

            # 씬 생성
            manual_scenes = []
            for i, img in enumerate(uploaded_images):
                script = script_lines[i] if i < len(script_lines) else ""
                manual_scenes.append({
                    "scene_id": i + 1,
                    "script_text": script,
                    "duration_estimate": 10,
                    "direction_guide": "",
                    "characters": [],
                    "mood": "",
                    "manual_image": img  # 업로드된 이미지 참조
                })

            st.info(f"📊 {len(manual_scenes)}개 씬 생성됨 (이미지 {len(uploaded_images)}개, 스크립트 {len(script_lines)}줄)")

    st.divider()

    # 저장 버튼
    if manual_scenes:
        st.markdown("### 💾 저장 및 적용")

        if st.button("📥 스토리보드에 적용", type="primary", use_container_width=True, key="apply_manual_storyboard"):
            try:
                # 씬 데이터 저장
                scenes_path = project_path / "analysis" / "scenes.json"
                scenes_path.parent.mkdir(parents=True, exist_ok=True)

                # manual_image 필드 제거 (저장용)
                scenes_to_save = []
                for s in manual_scenes:
                    scene_copy = {k: v for k, v in s.items() if k != "manual_image"}
                    scenes_to_save.append(scene_copy)

                with open(scenes_path, "w", encoding="utf-8") as f:
                    json.dump(scenes_to_save, f, ensure_ascii=False, indent=2)

                # 이미지 저장 (이미지 매핑 방식인 경우)
                if manual_compose_method == "🖼️ 이미지와 텍스트 매핑" and uploaded_images:
                    images_dir = project_path / "images" / "content"
                    images_dir.mkdir(parents=True, exist_ok=True)

                    for i, img in enumerate(uploaded_images):
                        img_path = images_dir / f"manual_{i+1:03d}.png"
                        with open(img_path, "wb") as f:
                            f.write(img.read())

                st.success(f"✅ {len(manual_scenes)}개 씬이 저장되었습니다!")
                st.info("'자동 조합' 탭에서 스토리보드를 확인하세요.")
                st.rerun()

            except Exception as e:
                st.error(f"저장 오류: {str(e)}")
    else:
        st.warning("⚠️ 씬 데이터를 입력하거나 업로드하세요.")

# === 인포그래픽 탭 ===
if INFOGRAPHIC_AVAILABLE and tab_infographic is not None:
    with tab_infographic:
        Profiler.log("📊 인포그래픽 탭 시작")

        # ⭐ 성능 최적화: Lazy Loading (항상 비활성으로 시작)
        _infographic_active_key = f"infographic_active_{project_path}"

        # 활성화 여부 체크 - 항상 비활성으로 시작하여 5초+ 지연 방지
        if _infographic_active_key not in st.session_state:
            st.session_state[_infographic_active_key] = False  # ⭐ 항상 비활성 시작

        # Lazy Loading UI (비활성 상태)
        if not st.session_state.get(_infographic_active_key, False):
            st.subheader("📊 인포그래픽 동영상 통합")
            st.info("⚡ **성능 최적화**: 이 탭은 무거운 기능을 포함하고 있어 필요할 때만 로드합니다.")
            st.markdown("**포함된 기능:** HTML 업로드, 썸네일/동영상 생성, 캐릭터 합성, 씬별 시각자료 선택")

            if st.button("🚀 인포그래픽 탭 활성화", type="primary", use_container_width=True):
                st.session_state[_infographic_active_key] = True
                st.rerun()

            Profiler.log("📊 인포그래픽 탭 종료 (비활성 - 빠름)")

        # === 활성화된 인포그래픽 탭 콘텐츠 ===
        if st.session_state.get(_infographic_active_key, False):
            # 헤더 + 비활성화 버튼
            _header_col, _deactivate_col = st.columns([5, 1])
            with _header_col:
                st.subheader("📊 인포그래픽 동영상 통합")
            with _deactivate_col:
                if st.button("⏸️ 비활성화", key="btn_deactivate_infographic", help="인포그래픽 기능을 비활성화하여 페이지 로딩 속도를 높입니다"):
                    st.session_state[_infographic_active_key] = False
                    st.rerun()

            st.info("""
            💡 **인포그래픽 동영상 통합 모드 v2**
            - **UI 표시**: 인포그래픽 첫 프레임 이미지 (썸네일)
            - **내보내기**: CSS 애니메이션을 녹화한 MP4 동영상
            - **캐릭터 합성**: 동영상 전체에 캐릭터 PNG 오버레이
            """)

            # 선택 매니저 초기화
            with Timer("VisualSelectionManager 초기화"):
                if "visual_manager" not in st.session_state:
                    st.session_state.visual_manager = VisualSelectionManager(str(project_path))
                visual_manager = st.session_state.visual_manager

            # 인포그래픽 데이터 상태
            infographic_data = visual_manager.get_infographic_data()

            # 렌더링 환경 상태 확인 (Selenium 기반)
            with Timer("check_environment"):
                env_status = check_environment()
            ffmpeg_ok = env_status.get("ffmpeg", False)
            selenium_ok = env_status.get("selenium", False)

            # 환경 상태 표시 (접을 수 있는 형태)
            with st.expander("🔧 렌더링 환경 상태 (Selenium 기반)", expanded=False):
                env_col1, env_col2, env_col3 = st.columns(3)
                with env_col1:
                    sel_icon = "✅" if selenium_ok else "❌"
                    st.metric("Selenium", sel_icon)
                with env_col2:
                    pil_icon = "✅" if env_status.get("pillow") else "❌"
                    st.metric("Pillow", pil_icon)
                with env_col3:
                    ff_icon = "✅" if ffmpeg_ok else "❌"
                    st.metric("FFmpeg", ff_icon)

                if selenium_ok:
                    st.success("✅ Selenium WebDriver 사용 가능")
                else:
                    st.error("❌ Selenium이 설치되지 않았습니다.")
                    st.code("pip install selenium webdriver-manager pillow", language="bash")

            if not ffmpeg_ok:
                st.warning("⚠️ FFmpeg이 설치되지 않았습니다. 동영상 녹화 및 합성을 위해 FFmpeg을 설치하세요.")

            # === 1. 인포그래픽 HTML 업로드 섹션 ===
            st.markdown("### 📁 1. 인포그래픽 HTML 업로드")

            upload_method = st.radio(
                "업로드 방식",
                ["파일 업로드", "HTML 코드 붙여넣기"],
                horizontal=True,
                key="html_upload_method"
            )

            html_content = None
            html_filename = "infographic.html"

            if upload_method == "파일 업로드":
                uploaded_html = st.file_uploader(
                    "인포그래픽 HTML 파일",
                    type=["html", "htm"],
                    help="sceneData 배열이 포함된 HTML 파일을 업로드하세요",
                    key="infographic_html_upload"
                )
                if uploaded_html:
                    html_content = uploaded_html.read().decode("utf-8")
                    html_filename = uploaded_html.name
            else:
                html_text = st.text_area(
                    "HTML 코드",
                    height=200,
                    placeholder="<!DOCTYPE html>...",
                    key="infographic_html_paste"
                )
                if html_text.strip():
                    html_content = html_text

            if html_content:
                try:
                    # 상세 파싱 정보 가져오기
                    parse_info = get_parsing_info(html_content)

                    if parse_info["success"]:
                        parsed_data = parse_info["data"]

                        st.success(f"✅ {parse_info['scene_count']}개 씬 파싱 완료!")

                        # 파싱 형식 표시
                        format_col1, format_col2 = st.columns(2)
                        with format_col1:
                            st.caption(f"📄 감지된 형식: **{parse_info['format_name']}**")
                        with format_col2:
                            if parse_info["animated_count"] > 0:
                                st.caption(f"🎬 애니메이션 포함: {parse_info['animated_count']}개 씬")

                        # 미리보기
                        with st.expander("📋 파싱된 씬 미리보기", expanded=True):
                            for scene in parsed_data.scenes[:5]:
                                col1, col2 = st.columns([1, 3])
                                with col1:
                                    st.markdown(f"**씬 {scene.scene_id}**")
                                    if scene.chart_type:
                                        st.caption(f"📊 {scene.chart_type}")
                                    if scene.comment:
                                        st.caption(f"📝 {scene.comment}")
                                with col2:
                                    st.markdown(f"**{scene.text[:50]}...**" if len(scene.text) > 50 else f"**{scene.text}**")
                                    if scene.sub:
                                        st.caption(scene.sub[:100] + "..." if len(scene.sub) > 100 else scene.sub)
                                    if scene.icons:
                                        st.caption(f"🎨 아이콘: {', '.join(scene.icons[:3])}")

                            if len(parsed_data.scenes) > 5:
                                st.caption(f"... 외 {len(parsed_data.scenes) - 5}개 씬")

                        # 저장 버튼
                        if st.button("💾 인포그래픽 저장", type="primary", key="save_infographic"):
                            # 인포그래픽 디렉토리 생성
                            infographic_dir = project_path / "infographics"
                            infographic_dir.mkdir(parents=True, exist_ok=True)

                            # HTML 파일 저장
                            html_path = infographic_dir / html_filename
                            with open(html_path, "w", encoding="utf-8") as f:
                                f.write(html_content)

                            # 데이터 저장
                            parsed_data.source_path = str(html_path)
                            visual_manager.set_infographic_data(parsed_data)

                            # ✅ 개별 씬 편집기 캐시 초기화 (새 HTML로 동기화 보장)
                            if "scene_html_editor" in st.session_state:
                                del st.session_state["scene_html_editor"]
                            if "scene_editor_source" in st.session_state:
                                del st.session_state["scene_editor_source"]
                            if "scene_editor_html_hash" in st.session_state:
                                del st.session_state["scene_editor_html_hash"]

                            st.success("인포그래픽 데이터가 저장되었습니다!")
                            st.rerun()
                    else:
                        st.error(f"❌ 파싱 실패: {parse_info['message']}")

                        # 디버깅 힌트 표시
                        with st.expander("🔧 문제 해결 힌트"):
                            st.markdown("""
                            **지원되는 HTML 형식:**

                            **1. JavaScript sceneData 배열**
                            ```javascript
                            const sceneData = [
                                { id: 1, text: "메인 텍스트", sub: "서브 텍스트" },
                                { id: 2, text: "두 번째 씬", sub: "설명" },
                                ...
                            ];
                            ```

                            **2. HTML scene 요소**
                            ```html
                            <!-- 씬 1: 설명 -->
                            <div class="scene" id="scene1">
                                <h1>메인 텍스트</h1>
                                <p>서브 텍스트</p>
                            </div>
                            ```

                            **확인 사항:**
                            - HTML 코드가 완전히 복사되었는지 확인
                            - `<div class="scene" id="sceneN">` 형식의 요소가 있는지 확인
                            - 또는 `sceneData = [...]` JavaScript 배열이 있는지 확인
                            - BeautifulSoup이 설치되어 있는지 확인: `pip install beautifulsoup4`
                            """)

                except Exception as e:
                    st.error(f"파일 처리 오류: {str(e)}")

            st.divider()

            # === 2. 저장된 인포그래픽 관리 ===
            if infographic_data:
                st.markdown("### 📊 2. 저장된 인포그래픽")

                # 상태 메트릭
                thumbnail_ready = len([s for s in infographic_data.scenes if s.is_thumbnail_ready])
                video_ready = len([s for s in infographic_data.scenes if s.is_video_ready])
                composite_ready = len([s for s in infographic_data.scenes if s.is_composite_ready])

                info_col1, info_col2, info_col3, info_col4 = st.columns(4)
                with info_col1:
                    st.metric("총 씬 수", infographic_data.total_scenes)
                with info_col2:
                    st.metric("썸네일", f"{thumbnail_ready}/{infographic_data.total_scenes}")
                with info_col3:
                    st.metric("동영상", f"{video_ready}/{infographic_data.total_scenes}")
                with info_col4:
                    st.metric("합성", f"{composite_ready}/{infographic_data.total_scenes}")

                st.caption(f"📁 소스: {Path(infographic_data.source_path).name if infographic_data.source_path else '없음'}")

                st.divider()

                # === 2.3. 개별 씬 HTML 편집 ===
                with st.expander("✏️ 개별 씬 HTML 편집", expanded=False):
                    render_scene_editor_section(infographic_data, project_path, visual_manager)

                st.divider()

                # === 2.5. 배경 이미지 대체 === (⭐ 성능 최적화: 버튼 클릭 시에만 로드)
                _bg_section_key = f"show_bg_replacement_{project_path}"
                st.markdown("### 🖼️ 2.5 배경 이미지 대체")
                if not st.session_state.get(_bg_section_key, False):
                    st.caption("인포그래픽 HTML의 배경 이미지를 대체합니다.")
                    if st.button("🖼️ 배경 대체 기능 열기", key="btn_open_bg_replace"):
                        st.session_state[_bg_section_key] = True
                        st.rerun()
                else:
                    if st.button("🔼 접기", key="btn_close_bg_replace"):
                        st.session_state[_bg_section_key] = False
                        st.rerun()
                    render_background_replacement_section(infographic_data, project_path, visual_manager)

                st.divider()

                # === 2.6. AI 비디오 생성 === (⭐ 성능 최적화: 버튼 클릭 시에만 로드)
                _ai_video_section_key = f"show_ai_video_{project_path}"
                st.markdown("### 🎬 2.6 AI 비디오 생성")
                if not st.session_state.get(_ai_video_section_key, False):
                    st.caption("씬 이미지를 AI Video API로 변환하여 동영상을 생성합니다.")
                    if st.button("🎬 AI 비디오 기능 열기", key="btn_open_ai_video"):
                        st.session_state[_ai_video_section_key] = True
                        st.rerun()
                else:
                    if st.button("🔼 접기", key="btn_close_ai_video"):
                        st.session_state[_ai_video_section_key] = False
                        st.rerun()
                    # InfographicScene 객체를 딕셔너리로 변환하여 전달
                    scenes_for_video = [
                        s.to_dict() if hasattr(s, 'to_dict') else s
                        for s in infographic_data.scenes
                    ]
                    render_ai_video_generation_section(scenes_for_video, project_path, visual_manager)

                st.divider()

                # === 3. 썸네일 생성 ===
                st.markdown("### 🖼️ 3. 썸네일 생성 (UI 표시용)")
                st.caption("각 씬의 첫 프레임을 캡처하여 썸네일 이미지 생성")
                scene_count = infographic_data.total_scenes

                # 씬 선택 옵션
                thumb_mode_col, thumb_select_col = st.columns([1, 2])

                with thumb_mode_col:
                    thumb_gen_mode = st.radio(
                        "생성 범위",
                        ["전체 씬", "범위 선택", "개별 선택"],
                        key="thumb_gen_mode",
                        horizontal=False
                    )

                with thumb_select_col:
                    if thumb_gen_mode == "범위 선택":
                        thumb_range = st.slider(
                            "씬 범위",
                            min_value=1,
                            max_value=scene_count,
                            value=(1, min(10, scene_count)),
                            key="thumb_range_slider"
                        )
                        selected_thumb_indices = list(range(thumb_range[0] - 1, thumb_range[1]))
                        st.info(f"씬 {thumb_range[0]} ~ {thumb_range[1]} 선택됨 ({len(selected_thumb_indices)}개)")

                    elif thumb_gen_mode == "개별 선택":
                        # 멀티셀렉트
                        scene_options = [f"씬 {i+1}" for i in range(scene_count)]
                        default_selected = scene_options[:min(5, scene_count)]
                        selected_labels = st.multiselect(
                            "생성할 씬 선택",
                            options=scene_options,
                            default=default_selected,
                            key="thumb_scene_multiselect"
                        )
                        selected_thumb_indices = [int(s.replace("씬 ", "")) - 1 for s in selected_labels]
                        st.info(f"{len(selected_thumb_indices)}개 씬 선택됨")
                    else:
                        selected_thumb_indices = list(range(scene_count))
                        st.info(f"전체 {scene_count}개 씬 선택됨")

                thumb_col1, thumb_col2 = st.columns(2)
                with thumb_col1:
                    if st.button("🖼️ 썸네일 생성", type="primary", use_container_width=True, key="generate_thumbnails"):
                        if not selected_thumb_indices:
                            st.error("생성할 씬을 선택하세요.")
                        else:
                            try:
                                output_dir = str(project_path / "infographics" / "thumbnails")
                                os.makedirs(output_dir, exist_ok=True)

                                progress_bar = st.progress(0)
                                status_text = st.empty()

                                if thumb_gen_mode == "전체 씬":
                                    # 기존 전체 생성 로직
                                    def thumb_progress(current, total, message):
                                        progress_bar.progress(current / total)
                                        status_text.text(message)

                                    results = factory_generate_thumbnails(
                                        infographic_data,
                                        output_dir=output_dir,
                                        progress_callback=thumb_progress
                                    )

                                    success = sum(1 for v in results.values() if v)
                                    fail = len(results) - success
                                else:
                                    # 선택적 생성 로직
                                    from utils.infographic_thumbnail import generate_selected_thumbnails_sync

                                    def thumb_progress(current, total):
                                        progress_bar.progress(current / total)
                                        status_text.text(f"씬 {selected_thumb_indices[current-1]+1} 완료 ({current}/{total})")

                                    results = generate_selected_thumbnails_sync(
                                        html_content=infographic_data.html_code,
                                        scene_indices=selected_thumb_indices,
                                        output_dir=output_dir,
                                        progress_callback=thumb_progress
                                    )

                                    success = len(results)
                                    fail = len(selected_thumb_indices) - success

                                progress_bar.progress(1.0)
                                status_text.text(f"완료! 성공: {success}, 실패: {fail}")

                                visual_manager.set_infographic_data(infographic_data)
                                st.success(f"✅ {success}개 썸네일 생성 완료!")

                                if fail > 0:
                                    st.warning(f"⚠️ {fail}개 씬 실패")

                                st.rerun()

                            except RuntimeError as e:
                                st.error(f"렌더러 오류: {str(e)}")
                                with st.expander("🔧 설치 방법"):
                                    st.markdown("""
                                    **Selenium WebDriver 설치:**

                                    ```bash
                                    pip install selenium webdriver-manager pillow
                                    ```

                                    Chrome 브라우저가 설치되어 있어야 합니다.
                                    ChromeDriver는 자동으로 다운로드됩니다.
                                    """)
                            except Exception as e:
                                st.error(f"썸네일 생성 오류: {str(e)}")

                with thumb_col2:
                    if st.button("🗑️ 인포그래픽 삭제", use_container_width=True, key="clear_infographic"):
                        visual_manager.state.infographic_data = None
                        visual_manager.save_state()
                        st.success("인포그래픽 데이터가 삭제되었습니다.")
                        st.rerun()

                # 썸네일 미리보기
                thumbnail_scenes = [s for s in infographic_data.scenes if s.is_thumbnail_ready]
                if thumbnail_scenes:
                    with st.expander(f"🖼️ 썸네일 미리보기 ({len(thumbnail_scenes)}개)", expanded=False):
                        cols_per_row = 4
                        for row_start in range(0, len(thumbnail_scenes), cols_per_row):
                            cols = st.columns(cols_per_row)
                            for j, col in enumerate(cols):
                                idx = row_start + j
                                if idx >= len(thumbnail_scenes):
                                    break
                                scene = thumbnail_scenes[idx]
                                with col:
                                    thumb = scene.thumbnail_path or scene.first_frame_path
                                    if thumb and os.path.exists(thumb):
                                        st.image(thumb, caption=f"씬 {scene.scene_id}")
                                    else:
                                        st.info(f"씬 {scene.scene_id}")

                st.divider()

                # === 4. 동영상 녹화 ===
                st.markdown("### 🎬 4. 동영상 녹화 (내보내기용)")
                st.caption("Selenium + FFmpeg 기반 MP4 동영상 녹화 (중앙정렬 + 고화질)")

                # 화질 프리셋 정보
                QUALITY_OPTIONS = {
                    "⚡ 미리보기 (480p)": {"key": "preview", "time_factor": 0.5, "size_mb": 0.5},
                    "📺 표준 (720p)": {"key": "standard", "time_factor": 1.0, "size_mb": 1.0},
                    "🎬 고화질 (1080p)": {"key": "high", "time_factor": 1.5, "size_mb": 2.0},
                    "🌟 초고화질 (1080p+)": {"key": "ultra", "time_factor": 3.0, "size_mb": 4.0},
                }

                # 설정 행 1: 화질 + 시간
                video_set_row1_col1, video_set_row1_col2 = st.columns([2, 1])

                with video_set_row1_col1:
                    video_quality_label = st.selectbox(
                        "🎥 화질 선택",
                        options=list(QUALITY_OPTIONS.keys()),
                        index=2,  # 기본: 고화질
                        key="video_quality_select",
                        help="미리보기: 빠른 테스트용\n표준: 일반적인 용도\n고화질: 유튜브 권장\n초고화질: 최상의 품질 (느림)"
                    )
                    video_quality = QUALITY_OPTIONS[video_quality_label]["key"]

                with video_set_row1_col2:
                    video_duration = st.slider(
                        "🕐 씬당 재생 시간 (초)",
                        min_value=1,
                        max_value=15,
                        value=5,
                        step=1,
                        key="video_duration"
                    )

                # 설정 행 2: 생성 범위 + 방식
                video_set_row2_col1, video_set_row2_col2 = st.columns(2)

                with video_set_row2_col1:
                    video_gen_mode = st.radio(
                        "생성 범위",
                        ["전체", "범위", "개별"],
                        key="video_gen_mode",
                        horizontal=True
                    )

                with video_set_row2_col2:
                    video_speed_mode = st.radio(
                        "생성 방식",
                        ["⚡ 빠른 생성", "🎭 애니메이션"],
                        key="video_speed_mode",
                        horizontal=True,
                        help="빠른 생성: 정적 이미지 기반 (권장, 10배 빠름)\n애니메이션: CSS 애니메이션 실시간 프레임 캡처 (느림)"
                    )

                is_fast_mode = "빠른" in video_speed_mode
                is_animation_mode = "애니메이션" in video_speed_mode

                # 애니메이션 모드 추가 설정
                animation_fps = 15  # 기본값
                if is_animation_mode:
                    st.info("🎭 **애니메이션 모드**: CSS 애니메이션이 실시간으로 캡처됩니다. 처리 시간이 5~10배 증가합니다.")
                    anim_col1, anim_col2 = st.columns([1, 2])
                    with anim_col1:
                        animation_fps = st.slider(
                            "캡처 FPS",
                            min_value=10,
                            max_value=25,
                            value=15,
                            key="animation_fps_slider",
                            help="높을수록 부드럽지만 캡처 시간 증가"
                        )
                    with anim_col2:
                        total_frames = video_duration * animation_fps
                        st.caption(f"📊 씬당 {video_duration}초 × {animation_fps}fps = **{total_frames}프레임** 캡처")

                # 씬 선택 UI
                if video_gen_mode == "범위":
                    video_range = st.slider(
                        "씬 범위",
                        min_value=1,
                        max_value=scene_count,
                        value=(1, min(5, scene_count)),
                        key="video_range_slider"
                    )
                    selected_video_indices = list(range(video_range[0] - 1, video_range[1]))
                elif video_gen_mode == "개별":
                    video_scene_options = [f"씬 {i+1}" for i in range(scene_count)]
                    selected_video_labels = st.multiselect(
                        "녹화할 씬 선택",
                        options=video_scene_options,
                        default=[video_scene_options[0]] if video_scene_options else [],
                        key="video_scene_multiselect"
                    )
                    selected_video_indices = [int(s.replace("씬 ", "")) - 1 for s in selected_video_labels]
                else:
                    selected_video_indices = list(range(scene_count))

                # 예상 시간/용량 계산
                quality_info = QUALITY_OPTIONS[video_quality_label]
                time_factor = quality_info["time_factor"]
                size_per_scene = quality_info["size_mb"] * video_duration

                if is_animation_mode:
                    # 애니메이션 모드: 씬당 (duration + 인코딩 시간)
                    base_time = len(selected_video_indices) * (video_duration + 3)  # 캡처 + 인코딩
                elif is_fast_mode:
                    base_time = len(selected_video_indices) * 2  # 씬당 약 2초
                else:
                    base_time = len(selected_video_indices) * video_duration * 5  # 씬당 약 5초/1초영상

                est_seconds = int(base_time * time_factor)
                est_minutes = est_seconds // 60
                est_sec_remain = est_seconds % 60
                est_size = len(selected_video_indices) * size_per_scene

                mode_emoji = "🎭" if is_animation_mode else "⚡"
                st.info(f"📊 선택: {len(selected_video_indices)}개 씬 | {mode_emoji} {video_quality_label.split()[0]} | ⏱️ 예상: ~{est_minutes}분 {est_sec_remain}초 | 📁 ~{est_size:.1f}MB")

                if st.button("🎬 동영상 녹화 시작", type="primary", use_container_width=True, key="record_videos", disabled=not ffmpeg_ok):
                    if not selected_video_indices:
                        st.error("녹화할 씬을 선택하세요.")
                    else:
                        try:
                            output_dir = str(project_path / "infographics" / "videos")
                            os.makedirs(output_dir, exist_ok=True)

                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            def video_progress(current, total, message):
                                progress_bar.progress(current / total)
                                status_text.text(message)

                            # 레코더로 녹화
                            from utils.infographic_video_recorder import get_video_recorder

                            with get_video_recorder(output_dir=output_dir, quality=video_quality) as recorder:
                                # 전체/선택 모두 동일한 메서드 사용
                                scene_list = selected_video_indices if video_gen_mode != "전체" else list(range(scene_count))

                                # ============================================================
                                # ✅ 핵심: 수정된 HTML 우선 사용 (배경 합성 포함)
                                # ============================================================
                                # 우선순위:
                                # 1. modified_infographic_html (배경 합성됨)
                                # 2. infographic_html_content (현재 작업 중인 HTML)
                                # 3. infographic_data.html_code (파일에서 로드한 원본)
                                recording_html = st.session_state.get("modified_infographic_html")
                                if not recording_html:
                                    recording_html = st.session_state.get("infographic_html_content")
                                if not recording_html:
                                    recording_html = infographic_data.html_code

                                results = recorder.record_selected_scenes(
                                    html_content=recording_html,
                                    scene_indices=scene_list,
                                    duration=video_duration,
                                    output_dir=output_dir,
                                    fast_mode=is_fast_mode,
                                    animation_mode=is_animation_mode,
                                    animation_fps=animation_fps,
                                    preserve_layout=True,
                                    fade_effect=not is_animation_mode,  # 애니메이션 모드에서는 페이드 off
                                    progress_callback=video_progress
                                )

                            progress_bar.progress(1.0)
                            status_text.text(f"완료! {len(results)}개 동영상 생성")

                            visual_manager.set_infographic_data(infographic_data)
                            st.success(f"✅ {len(results)}개 동영상 녹화 완료!")

                            # 병합 옵션 표시
                            if len(results) > 1:
                                st.info("💡 여러 씬을 하나의 영상으로 병합하려면 아래 '영상 병합' 기능을 사용하세요.")

                            st.rerun()

                        except RuntimeError as e:
                            st.error(f"동영상 녹화기 초기화 실패: {str(e)}")
                            st.info("동영상 녹화 필수 요소: `pip install selenium webdriver-manager pillow` + FFmpeg 설치")
                        except Exception as e:
                            st.error(f"녹화 오류: {str(e)}")
                            import traceback
                            with st.expander("오류 상세"):
                                st.code(traceback.format_exc())

                # ============================================================
                # 동영상 미리보기 섹션
                # ============================================================
                videos_dir = str(project_path / "infographics" / "videos")
                thumbnails_dir = str(project_path / "infographics" / "thumbnails")

                # 동영상 파일 목록 가져오기
                video_files = []
                if os.path.exists(videos_dir):
                    video_files = sorted([
                        f for f in os.listdir(videos_dir)
                        if f.endswith('.mp4') and 'scene' in f.lower()
                    ])

                with st.expander(f"🎬 생성된 동영상 미리보기 ({len(video_files)}/{scene_count}개)", expanded=len(video_files) > 0):

                    if not video_files:
                        st.info("아직 생성된 동영상이 없습니다. 위에서 동영상 녹화를 시작하세요.")
                    else:
                        # 그리드 레이아웃 (5열)
                        cols_per_row = 5

                        for row_start in range(0, len(video_files), cols_per_row):
                            cols = st.columns(cols_per_row)

                            for col_idx, col in enumerate(cols):
                                video_idx = row_start + col_idx

                                if video_idx >= len(video_files):
                                    break

                                video_file = video_files[video_idx]
                                video_path = os.path.join(videos_dir, video_file)

                                with col:
                                    # 씬 번호 추출 (예: infographic_scene_001.mp4 → 1)
                                    try:
                                        scene_num = int(video_file.split('_')[-1].replace('.mp4', ''))
                                    except:
                                        scene_num = video_idx + 1

                                    # 썸네일 이미지 (있으면 사용)
                                    thumb_path = os.path.join(thumbnails_dir, f"scene_{scene_num:03d}.png")
                                    alt_thumb_path = os.path.join(thumbnails_dir, f"scene_{scene_num:03d}_thumb.png")

                                    if os.path.exists(thumb_path):
                                        render_lightbox_image(thumb_path, key=f"vid_thumb_{scene_num}")
                                    elif os.path.exists(alt_thumb_path):
                                        render_lightbox_image(alt_thumb_path, key=f"vid_thumb_alt_{scene_num}")
                                    else:
                                        # 비디오 아이콘 placeholder
                                        st.markdown(
                                            f"""
                                            <div style="
                                                background: #f0f0f0;
                                                border-radius: 8px;
                                                padding: 15px;
                                                text-align: center;
                                                height: 60px;
                                                display: flex;
                                                align-items: center;
                                                justify-content: center;
                                            ">
                                                <span style="font-size: 20px;">🎬</span>
                                            </div>
                                            """,
                                            unsafe_allow_html=True
                                        )

                                    # 씬 번호 및 파일 정보
                                    file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
                                    st.caption(f"씬 {scene_num} ({file_size:.1f}MB)")

                                    # 버튼 행
                                    btn_col1, btn_col2 = st.columns(2)

                                    with btn_col1:
                                        # 재생 버튼
                                        if st.button("▶️", key=f"play_video_{video_idx}", help="미리보기"):
                                            st.session_state[f'show_video_{video_idx}'] = True

                                    with btn_col2:
                                        # 폴더 열기 버튼
                                        if st.button("📂", key=f"open_folder_{video_idx}", help="폴더 열기"):
                                            open_file_location(video_path)

                                    # 비디오 플레이어 (토글)
                                    if st.session_state.get(f'show_video_{video_idx}', False):
                                        st.video(video_path)
                                        if st.button("닫기", key=f"close_video_{video_idx}"):
                                            st.session_state[f'show_video_{video_idx}'] = False
                                            st.rerun()

                        # 전체 폴더 열기 버튼
                        st.divider()
                        folder_col1, folder_col2, folder_col3 = st.columns([1, 1, 1])

                        with folder_col1:
                            if st.button("📂 동영상 폴더 열기", use_container_width=True, key="open_videos_folder"):
                                open_folder(videos_dir)

                        with folder_col2:
                            if st.button("🗑️ 전체 동영상 삭제", use_container_width=True, type="secondary", key="delete_all_videos"):
                                if st.session_state.get('confirm_delete_videos', False):
                                    # 삭제 실행
                                    for vf in video_files:
                                        try:
                                            os.remove(os.path.join(videos_dir, vf))
                                        except:
                                            pass
                                    st.session_state['confirm_delete_videos'] = False
                                    st.success("삭제 완료!")
                                    st.rerun()
                                else:
                                    st.session_state['confirm_delete_videos'] = True
                                    st.warning("정말 삭제하시겠습니까? 다시 클릭하면 삭제됩니다.")

                        with folder_col3:
                            # 병합된 파일 확인
                            merged_path = os.path.join(videos_dir, "merged_all.mp4")
                            if os.path.exists(merged_path):
                                merged_size = os.path.getsize(merged_path) / (1024 * 1024)
                                st.success(f"✅ 병합 ({merged_size:.1f}MB)")
                                if st.button("▶️ 병합 영상", key="play_merged"):
                                    st.video(merged_path)
                            else:
                                st.caption("병합 파일 없음")

                st.divider()

                # === 5. 캐릭터 합성 ===
                st.markdown("### 👤 5. 캐릭터 동영상 합성")
                st.caption("인포그래픽 동영상 위에 캐릭터 PNG 오버레이 (FFmpeg)")

                # ========================================
                # 캐릭터 로드 (CharacterManager + 직접 PNG 스캔)
                # ========================================
                try:
                    from core.character.character_manager import CharacterManager
                    char_manager = CharacterManager(str(project_path))
                    registered_characters = char_manager.get_all_characters()
                except Exception as e:
                    registered_characters = []
                    st.warning(f"캐릭터 매니저 로드 실패: {e}")

                # 캐릭터 이미지 목록 구성 (등록된 캐릭터 + 폴더 스캔)
                character_dir = project_path / "characters"
                character_images_dir = project_path / "images" / "characters"
                character_options = []

                # 1. 등록된 캐릭터 (generated_images 포함)
                for char in registered_characters:
                    # 생성된 이미지 사용
                    if char.generated_images:
                        for img_path in char.generated_images:
                            full_path = Path(img_path) if os.path.isabs(img_path) else project_path / img_path
                            if full_path.exists():
                                character_options.append({
                                    'name': f"👤 {char.name}",
                                    'path': full_path,
                                    'type': 'registered',
                                    'char_id': char.id
                                })
                                break  # 첫 번째 이미지만 사용

                # 2. characters 폴더 직접 스캔 (등록 안 된 PNG)
                registered_paths = {opt['path'] for opt in character_options}
                for scan_dir in [character_dir, character_images_dir]:
                    if scan_dir.exists():
                        for img_file in scan_dir.glob("*.png"):
                            if img_file not in registered_paths:
                                character_options.append({
                                    'name': f"📁 {img_file.stem}",
                                    'path': img_file,
                                    'type': 'folder',
                                    'char_id': None
                                })
                                registered_paths.add(img_file)

                # 동영상이 있는 씬 확인 (파일 시스템 기반)
                video_dir = project_path / "infographics" / "videos"
                video_files = list(video_dir.glob("infographic_scene_*.mp4")) if video_dir.exists() else []

                # InfographicData와 동기화
                video_ready_scenes = []
                for scene in infographic_data.scenes:
                    video_path = video_dir / f"infographic_scene_{scene.scene_id:03d}.mp4"
                    if video_path.exists():
                        scene.is_video_ready = True
                        scene.video_path = str(video_path)
                        video_ready_scenes.append(scene)

                if not character_options:
                    st.info("캐릭터 이미지가 없습니다.")

                    # 탭: 캐릭터 관리로 이동 / 직접 업로드
                    char_tab1, char_tab2 = st.tabs(["📦 캐릭터 관리 페이지", "📤 직접 업로드"])

                    with char_tab1:
                        st.write("**캐릭터 관리** 페이지에서 캐릭터를 생성하면 여기에 표시됩니다.")
                        if registered_characters:
                            st.write(f"등록된 캐릭터: {len(registered_characters)}명 (이미지 없음)")
                            for char in registered_characters[:5]:
                                st.caption(f"- {char.name}: 이미지 생성 필요")
                        else:
                            st.caption("등록된 캐릭터가 없습니다.")

                    with char_tab2:
                        uploaded_char = st.file_uploader(
                            "캐릭터 PNG 업로드",
                            type=["png"],
                            key="upload_character"
                        )
                        if uploaded_char:
                            character_dir.mkdir(parents=True, exist_ok=True)
                            char_path = character_dir / uploaded_char.name
                            with open(char_path, "wb") as f:
                                f.write(uploaded_char.read())
                            st.success(f"캐릭터 저장: {char_path.name}")
                            st.rerun()
                else:
                    # 합성 상태 메트릭
                    composites_dir = project_path / "infographics" / "composites"
                    composite_files = list(composites_dir.glob("composite_scene_*.mp4")) if composites_dir.exists() else []

                    # 씬-캐릭터 매처 초기화
                    try:
                        matcher = get_scene_character_matcher(str(project_path))
                        mapping_summary = matcher.get_mapping_summary()
                        scene_analysis = matcher.load_scene_analysis()
                    except Exception as e:
                        matcher = None
                        mapping_summary = {'total': 0, 'matched': 0, 'default': 0, 'by_character': {}}
                        scene_analysis = []

                    comp_metric_col1, comp_metric_col2, comp_metric_col3, comp_metric_col4, comp_metric_col5 = st.columns(5)
                    with comp_metric_col1:
                        st.metric("캐릭터 이미지", len(character_options))
                    with comp_metric_col2:
                        st.metric("씬 분석", len(scene_analysis))
                    with comp_metric_col3:
                        st.metric("자동 매칭", mapping_summary['matched'])
                    with comp_metric_col4:
                        st.metric("동영상", len(video_files))
                    with comp_metric_col5:
                        st.metric("합성 완료", len(composite_files))

                    # 탭: 씬분석 자동 매칭 / 수동 선택 / 설정
                    comp_tab_auto, comp_tab_manual, comp_tab_settings = st.tabs([
                        "🤖 씬분석 자동 매칭",
                        "✋ 수동 선택",
                        "⚙️ 설정"
                    ])

                    # 기본값: 자동 배경 제거 활성화
                    auto_remove_bg = True

                    # ========================================
                    # 탭 1: 씬분석 자동 매칭
                    # ========================================
                    with comp_tab_auto:
                        st.markdown("#### 🤖 씬분석 → 캐릭터 자동 매칭")
                        st.caption("씬 분석 페이지의 '등장 캐릭터' 정보를 캐릭터 관리의 캐릭터와 자동 매칭합니다.")

                        if not scene_analysis:
                            st.warning("씬 분석 데이터가 없습니다.")
                            st.info("👉 **씬 분석** 페이지에서 먼저 씬을 분석하세요.")
                        elif not matcher or not matcher.get_available_characters():
                            st.warning("등록된 캐릭터가 없습니다.")
                            st.info("👉 **캐릭터 관리** 페이지에서 캐릭터를 먼저 추가하세요.")
                        else:
                            # 🔴 v3.12: 로드된 캐릭터 디버그 정보 표시
                            available_chars = matcher.get_available_characters()
                            with st.expander(f"👤 매칭 가능 캐릭터 ({len(available_chars)}명)", expanded=False):
                                if available_chars:
                                    for c in available_chars:
                                        has_image = "✅" if c.get('image_path') else "❌"
                                        st.caption(f"- {c['name']} ({c['id']}) {has_image}")
                                else:
                                    st.warning("캐릭터가 로드되지 않았습니다.")
                                    st.info("캐릭터 관리 페이지에서 캐릭터 이미지를 생성하세요.")

                            # 현재 매핑 미리보기
                            existing_mappings = matcher.load_mappings()

                            with st.expander("📋 현재 씬-캐릭터 매핑", expanded=len(existing_mappings) > 0):
                                if existing_mappings:
                                    import pandas as pd
                                    mapping_data = []
                                    for m in existing_mappings[:15]:
                                        mapping_data.append({
                                            "씬": m.get('scene_num', '-'),
                                            "분석된 캐릭터": m.get('original_name', '-'),
                                            "매칭된 캐릭터": m.get('character_name', '-'),
                                            "신뢰도": f"{m.get('confidence', 0):.0%}",
                                            "소스": "✅ 자동" if m.get('match_type') != 'default' else "⚪ 기본"
                                        })

                                    df = pd.DataFrame(mapping_data)
                                    st.dataframe(df, use_container_width=True, hide_index=True)

                                    if len(existing_mappings) > 15:
                                        st.caption(f"... 외 {len(existing_mappings) - 15}개")

                                    # 캐릭터별 등장 횟수
                                    if mapping_summary['by_character']:
                                        st.markdown("**캐릭터별 등장 횟수:**")
                                        for char_name, count in mapping_summary['by_character'].items():
                                            st.write(f"- {char_name}: **{count}회**")
                                else:
                                    st.info("아직 생성된 매핑이 없습니다. 아래에서 자동 매핑을 생성하세요.")

                            st.divider()

                            # 자동 매핑 생성
                            st.markdown("##### 🔄 자동 매핑 생성")

                            auto_col1, auto_col2 = st.columns(2)

                            with auto_col1:
                                # 기본 캐릭터 선택 (available_chars는 위에서 이미 로드됨)
                                default_options = ["없음 (매칭된 것만)"] + [c['name'] for c in available_chars]
                                default_select = st.selectbox(
                                    "기본 캐릭터 (매칭 실패 시)",
                                    options=default_options,
                                    key="default_char_matcher"
                                )

                                default_char_id = None
                                if default_select != "없음 (매칭된 것만)":
                                    default_char = next((c for c in available_chars if c['name'] == default_select), None)
                                    if default_char:
                                        default_char_id = default_char['id']

                            with auto_col2:
                                # 미리 계산
                                preview_mappings = matcher.generate_mappings(scene_analysis, default_char_id)
                                auto_count = sum(1 for m in preview_mappings if m.get('match_type') != 'default')
                                default_count = len(preview_mappings) - auto_count

                                st.write("📊 **예상 결과:**")
                                st.write(f"- 자동 매칭: **{auto_count}개** 씬")
                                st.write(f"- 기본값 사용: **{default_count}개** 씬")

                            # 매핑 생성 버튼
                            if st.button("🔍 씬분석에서 캐릭터 자동 매칭", key="generate_auto_mapping", type="primary"):
                                with st.spinner("씬 분석 데이터에서 캐릭터 매칭 중..."):
                                    new_mappings = matcher.generate_mappings(scene_analysis, default_char_id)

                                    if new_mappings:
                                        matcher.save_mappings(new_mappings)
                                        st.success(f"✅ {len(new_mappings)}개 씬에 캐릭터 매핑 완료!")
                                        st.rerun()
                                    else:
                                        st.warning("매핑할 수 있는 씬이 없습니다.")

                            st.divider()

                            # 일괄 합성 실행
                            st.markdown("##### 🎬 자동 매핑 기반 일괄 합성")

                            existing_mappings = matcher.load_mappings()

                            # 합성 가능한 씬 필터링 (동영상이 있는 씬)
                            video_scene_nums = set()
                            for vf in video_files:
                                try:
                                    scene_num = int(vf.stem.split('_')[-1])
                                    video_scene_nums.add(scene_num)
                                except ValueError:
                                    pass

                            mappings_with_video = [
                                m for m in existing_mappings
                                if m.get('scene_num') in video_scene_nums and m.get('image_path')
                            ]

                            if not mappings_with_video:
                                st.warning("합성 가능한 씬이 없습니다.")
                                if not existing_mappings:
                                    st.info("먼저 위에서 자동 매핑을 생성하세요.")
                                elif not video_files:
                                    st.info("먼저 동영상을 생성하세요.")
                            else:
                                # 합성 옵션
                                auto_c1, auto_c2, auto_c3 = st.columns(3)

                                with auto_c1:
                                    # v2.0: 9개 위치 프리셋 (3x3 그리드)
                                    position_options_auto = {
                                        "↘️ 우하단 (기본)": "bottom_right",
                                        "↙️ 좌하단": "bottom_left",
                                        "⬇️ 하단 중앙": "bottom_center",
                                        "➡️ 우측 중앙": "middle_right",
                                        "⬅️ 좌측 중앙": "middle_left",
                                        "⏺️ 정중앙": "middle_center",
                                        "↗️ 우상단": "top_right",
                                        "↖️ 좌상단": "top_left",
                                        "⬆️ 상단 중앙": "top_center",
                                    }
                                    auto_pos_label = st.selectbox(
                                        "📍 위치 (3x3 그리드)",
                                        list(position_options_auto.keys()),
                                        key="auto_compose_pos"
                                    )
                                    auto_position = position_options_auto[auto_pos_label]

                                with auto_c2:
                                    # v2.0: 10-60% 크기 범위
                                    auto_scale = st.slider(
                                        "📏 크기 (%)",
                                        min_value=10,
                                        max_value=60,
                                        value=35,
                                        step=5,
                                        key="auto_compose_scale",
                                        help="배경 높이 대비 캐릭터 높이 비율 (10-60%)"
                                    ) / 100  # 백분율을 비율로 변환

                                with auto_c3:
                                    bg_available, bg_msg = is_bg_removal_available()
                                    # v3.14: 배경 제거 기본값 True, 체크박스 항상 활성화
                                    auto_remove_bg_opt = st.checkbox(
                                        "🎭 배경 제거",
                                        value=True,  # 항상 기본값 True
                                        key="auto_remove_bg_opt",
                                        help="캐릭터 배경을 자동으로 제거합니다"
                                    )
                                    if not bg_available:
                                        st.caption("⚠️ rembg 미설치 (합성 시 자동 설치 시도)")
                                        with st.expander("🔧 수동 설치하기"):
                                            install_rembg_ui(key_suffix="auto_match")

                                st.info(f"📊 합성 대상: **{len(mappings_with_video)}개** 씬")

                                if st.button(
                                    "🎬 자동 매핑 기반 일괄 합성",
                                    key="start_auto_compose",
                                    use_container_width=True,
                                    type="primary"
                                ):
                                    try:
                                        output_dir = str(project_path / "infographics" / "composites")
                                        os.makedirs(output_dir, exist_ok=True)

                                        progress_bar = st.progress(0)
                                        status_text = st.empty()

                                        results = []
                                        total = len(mappings_with_video)

                                        for i, mapping in enumerate(mappings_with_video):
                                            scene_num = mapping['scene_num']
                                            char_name = mapping.get('character_name', 'Unknown')
                                            image_path = mapping.get('image_path')

                                            progress_bar.progress((i + 1) / total)
                                            status_text.text(f"[{i+1}/{total}] 씬 {scene_num}: {char_name}")

                                            # 동영상 경로
                                            video_path = video_dir / f"infographic_scene_{scene_num:03d}.mp4"
                                            if not video_path.exists() or not image_path:
                                                continue

                                            # 합성 실행
                                            from utils.infographic_compositor import composite_character_sync
                                            output = composite_character_sync(
                                                video_path=str(video_path),
                                                character_image_path=image_path,
                                                scene_id=scene_num,
                                                position=auto_position,
                                                scale=auto_scale,
                                                output_dir=output_dir,
                                                auto_remove_bg=auto_remove_bg_opt
                                            )

                                            if output:
                                                results.append(output)

                                        progress_bar.empty()
                                        status_text.empty()

                                        if results:
                                            st.success(f"✅ {len(results)}개 씬 일괄 합성 완료!")
                                            st.balloons()
                                            st.rerun()
                                        else:
                                            st.error("합성 실패")

                                    except Exception as e:
                                        st.error(f"오류: {e}")
                                        import traceback
                                        st.code(traceback.format_exc())

                            st.divider()

                            # ========================================
                            # 합성 결과 미리보기 (자동 매핑)
                            # ========================================
                            st.markdown("##### 👁️ 합성 결과 미리보기")

                            # 합성된 파일 확인
                            composites_dir = project_path / "infographics" / "composites"
                            composite_thumbs = list(composites_dir.glob("composite_scene_*_thumb.png")) if composites_dir.exists() else []

                            if composite_thumbs:
                                st.success(f"✅ {len(composite_thumbs)}개 합성 완료된 씬")

                                # 그리드로 미리보기
                                preview_cols_per_row = 4
                                composite_thumbs_sorted = sorted(composite_thumbs, key=lambda x: x.stem)

                                for i in range(0, len(composite_thumbs_sorted), preview_cols_per_row):
                                    cols = st.columns(preview_cols_per_row)
                                    for j, col in enumerate(cols):
                                        idx = i + j
                                        if idx < len(composite_thumbs_sorted):
                                            thumb_path = composite_thumbs_sorted[idx]
                                            # 씬 번호 추출
                                            try:
                                                scene_num = int(thumb_path.stem.split('_')[2])
                                            except:
                                                scene_num = idx + 1

                                            with col:
                                                st.image(str(thumb_path), caption=f"씬 {scene_num}", use_container_width=True)

                                # 개별 씬 편집 버튼
                                with st.expander("✏️ 개별 씬 위치/크기 조정"):
                                    st.caption("특정 씬의 캐릭터 위치나 크기를 수정하려면 '수동 선택' 탭에서 개별 편집을 사용하세요.")
                                    st.info("👉 '수동 선택' 탭 → 씬 선택 → 캐릭터 에디터에서 위치/크기 조정")
                            else:
                                st.info("합성된 결과가 없습니다. 위에서 '일괄 합성'을 실행하세요.")

                    # ========================================
                    # 탭 2: 수동 선택 (기존 코드)
                    # ========================================
                    with comp_tab_manual:
                        st.markdown("#### ✋ 수동 캐릭터 선택")
                        st.caption("개별 씬에 특정 캐릭터를 직접 지정합니다.")

                        char_col1, char_col2 = st.columns([3, 2])

                        with char_col1:
                            # 캐릭터 선택 (이름과 유형 표시)
                            selected_char_idx = st.selectbox(
                                "캐릭터 선택",
                                range(len(character_options)),
                                format_func=lambda i: character_options[i]['name'],
                                key="select_character_idx"
                            )
                            selected_char_info = character_options[selected_char_idx]
                            selected_char = selected_char_info['path']

                            # v2.0: 위치 설정 (9개 프리셋)
                            position_options = {
                                "↘️ 우하단 (기본)": "bottom_right",
                                "↙️ 좌하단": "bottom_left",
                                "⬇️ 하단 중앙": "bottom_center",
                                "➡️ 우측 중앙": "middle_right",
                                "⬅️ 좌측 중앙": "middle_left",
                                "⏺️ 정중앙": "middle_center",
                                "↗️ 우상단": "top_right",
                                "↖️ 좌상단": "top_left",
                                "⬆️ 상단 중앙": "top_center",
                            }
                            char_position_label = st.selectbox(
                                "📍 위치 (3x3 그리드)",
                                list(position_options.keys()),
                                key="char_position_select"
                            )
                            char_position = position_options[char_position_label]

                            # v2.0: 크기 설정 (10-60%)
                            scale_options = {
                                "아주 작게 (10%)": 0.10,
                                "작게 (20%)": 0.20,
                                "보통 (30%)": 0.30,
                                "크게 (40%)": 0.40,
                                "아주 크게 (50%)": 0.50,
                                "최대 (60%)": 0.60
                            }
                            scale_label = st.selectbox(
                                "📏 크기",
                                list(scale_options.keys()),
                                index=2,  # 기본: 보통 (30%)
                                key="char_scale_select"
                            )
                            char_scale = scale_options[scale_label]

                            # 고급 설정
                            with st.expander("⚙️ 고급 설정"):
                                char_scale_custom = st.slider(
                                    "세부 크기 조정 (%)",
                                    min_value=10,
                                    max_value=60,
                                    value=int(char_scale * 100),
                                    step=5,
                                    key="char_scale_custom",
                                    help="배경 높이 대비 캐릭터 높이 비율 (10-60%)"
                                ) / 100  # 백분율을 비율로 변환
                                if char_scale_custom != char_scale:
                                    char_scale = char_scale_custom

                                st.divider()

                                # 배경 제거 옵션
                                st.markdown("##### 🎭 배경 제거")
                                rembg_available, rembg_msg = is_bg_removal_available()

                                # v3.14: 배경 제거 항상 활성화, 기본값 True
                                auto_remove_bg = st.checkbox(
                                    "🎭 자동 배경 제거",
                                    value=True,  # 항상 기본값 True
                                    help="캐릭터 이미지에 배경이 있으면 자동으로 제거합니다",
                                    key="auto_remove_bg_checkbox"
                                )

                                if rembg_available:
                                    st.success(rembg_msg)
                                else:
                                    st.warning(f"{rembg_msg} (합성 시 자동 설치 시도)")
                                    with st.expander("🔧 수동 설치하기"):
                                        install_rembg_ui(key_suffix="manual_select")

                        with char_col2:
                            if selected_char and selected_char.exists():
                                st.image(str(selected_char), caption=selected_char_info['name'], width=180)
                                if selected_char_info['type'] == 'registered':
                                    st.caption(f"✅ 캐릭터 관리에서 등록됨")
                                else:
                                    st.caption(f"📁 폴더에서 직접 로드")

                        # 합성 대상 선택
                        st.markdown("#### 합성 대상 선택")
                        comp_target_mode = st.radio(
                            "합성 범위",
                            ["미합성 씬만", "전체 재합성", "개별 선택"],
                            horizontal=True,
                            key="comp_target_mode"
                        )

                        if comp_target_mode == "미합성 씬만":
                            compositable_scenes = [s for s in infographic_data.scenes if s.is_video_ready and not s.is_composite_ready]
                        elif comp_target_mode == "전체 재합성":
                            compositable_scenes = video_ready_scenes
                        else:  # 개별 선택
                            scene_options = [f"씬 {s.scene_id}" for s in video_ready_scenes]
                            selected_comp_labels = st.multiselect(
                                "합성할 씬 선택",
                                options=scene_options,
                                default=[],
                                key="comp_scene_multiselect"
                            )
                            selected_comp_ids = [int(s.replace("씬 ", "")) for s in selected_comp_labels]
                            compositable_scenes = [s for s in video_ready_scenes if s.scene_id in selected_comp_ids]

                        st.info(f"📊 합성 대상: {len(compositable_scenes)}개 씬")

                        st.divider()

                        # ========================================
                        # 🔴 v3.12: 시각적 캐릭터 에디터 (위치/크기 조정)
                        # ========================================
                        st.markdown("#### 🎨 시각적 위치/크기 조정 (미리보기)")

                        # 개별 씬 선택해서 시각적 편집
                        if video_ready_scenes and selected_char and selected_char.exists():
                            edit_scene_options = [f"씬 {s.scene_id}" for s in video_ready_scenes]

                            use_visual_editor = st.checkbox(
                                "🖼️ 시각적 에디터 사용 (개별 씬)",
                                value=False,
                                key="use_visual_editor",
                                help="선택한 씬의 인포그래픽에 캐릭터를 미리 배치하고 위치/크기를 조정합니다."
                            )

                            if use_visual_editor:
                                selected_edit_scene = st.selectbox(
                                    "편집할 씬 선택",
                                    edit_scene_options,
                                    key="visual_edit_scene_select"
                                )
                                edit_scene_id = int(selected_edit_scene.replace("씬 ", ""))

                                # 해당 씬의 인포그래픽 찾기
                                infographic_thumb_path = project_path / "infographics" / "thumbnails" / f"infographic_{edit_scene_id:03d}.png"
                                video_frame_path = project_path / "infographics" / "composites" / f"composite_scene_{edit_scene_id:03d}_thumb.png"

                                # 썸네일 없으면 동영상 첫 프레임 추출 시도
                                if not infographic_thumb_path.exists():
                                    # 동영상에서 첫 프레임 추출
                                    video_path = project_path / "infographics" / "videos" / f"infographic_scene_{edit_scene_id:03d}.mp4"
                                    if video_path.exists():
                                        temp_frame = project_path / "infographics" / "thumbnails" / f"temp_frame_{edit_scene_id:03d}.png"
                                        temp_frame.parent.mkdir(parents=True, exist_ok=True)
                                        try:
                                            subprocess.run([
                                                "ffmpeg", "-y", "-i", str(video_path),
                                                "-vframes", "1", str(temp_frame)
                                            ], capture_output=True)
                                            if temp_frame.exists():
                                                infographic_thumb_path = temp_frame
                                        except:
                                            pass

                                if infographic_thumb_path.exists():
                                    st.caption(f"씬 {edit_scene_id}에 캐릭터 배치 미리보기")

                                    # 캐릭터 에디터 호출
                                    editor_result = render_character_editor(
                                        background_path=str(infographic_thumb_path),
                                        character_path=str(selected_char),
                                        initial_size=int(char_scale * 100),
                                        remove_background=auto_remove_bg if 'auto_remove_bg' in dir() else True,
                                        key=f"char_editor_scene_{edit_scene_id}"
                                    )

                                    if editor_result:
                                        st.success(f"✅ 캐릭터 위치: ({editor_result['position_x']}, {editor_result['position_y']}), 크기: {editor_result['size_percent']}%")

                                        # 이 설정으로 합성 버튼
                                        if st.button(
                                            f"📸 씬 {edit_scene_id}에 이 설정으로 합성",
                                            key=f"apply_editor_scene_{edit_scene_id}",
                                            type="secondary"
                                        ):
                                            # 결과 이미지 저장
                                            output_path = project_path / "infographics" / "composites" / f"composite_scene_{edit_scene_id:03d}_preview.png"
                                            output_path.parent.mkdir(parents=True, exist_ok=True)
                                            editor_result['composite_image'].save(str(output_path), 'PNG')
                                            st.success(f"미리보기 저장: {output_path.name}")

                                            # 동영상 합성은 별도로 실행해야 함
                                            st.info("💡 동영상 합성은 아래 '캐릭터 합성 시작' 버튼을 사용하세요.")
                                else:
                                    st.warning(f"씬 {edit_scene_id}의 인포그래픽 이미지를 찾을 수 없습니다.")
                                    st.caption("동영상을 먼저 생성하거나, 인포그래픽 썸네일이 필요합니다.")
                        else:
                            st.caption("캐릭터를 선택하고 동영상이 있는 씬이 있어야 시각적 에디터를 사용할 수 있습니다.")

                        st.divider()

                        # 합성 실행 버튼
                        can_composite = ffmpeg_ok and len(compositable_scenes) > 0 and selected_char
                        if st.button(
                            "👤 캐릭터 합성 시작",
                            type="primary",
                            use_container_width=True,
                            key="composite_videos",
                            disabled=not can_composite
                        ):
                            try:
                                output_dir = str(project_path / "infographics" / "composites")
                                os.makedirs(output_dir, exist_ok=True)

                                progress_bar = st.progress(0)
                                status_text = st.empty()

                                def comp_progress(current, total, message):
                                    progress_bar.progress(current / total)
                                    status_text.text(message)

                                # 합성 대상 씬 ID 목록
                                target_scene_ids = [s.scene_id for s in compositable_scenes]

                                results = batch_composite_sync(
                                    infographic_data,
                                    character_image_path=str(selected_char),
                                    position=char_position,
                                    scale=char_scale,
                                    scene_ids=target_scene_ids,
                                    output_dir=output_dir,
                                    auto_remove_bg=auto_remove_bg,
                                    progress_callback=comp_progress
                                )

                                progress_bar.progress(1.0)
                                status_text.text(f"완료! {len(results)}개 합성")

                                visual_manager.set_infographic_data(infographic_data)
                                st.success(f"✅ {len(results)}개 동영상 합성 완료!")
                                st.rerun()

                            except Exception as e:
                                st.error(f"합성 오류: {str(e)}")
                                import traceback
                                with st.expander("오류 상세"):
                                    st.code(traceback.format_exc())

                        if not can_composite:
                            if not ffmpeg_ok:
                                st.warning("⚠️ FFmpeg이 필요합니다.")
                            elif len(compositable_scenes) == 0:
                                st.warning("⚠️ 합성할 동영상이 없습니다. 먼저 동영상을 녹화하세요.")
                            elif not selected_char:
                                st.warning("⚠️ 캐릭터를 선택하세요.")

                    # ========================================
                    # 탭 3: 설정
                    # ========================================
                    with comp_tab_settings:
                        st.markdown("#### ⚙️ 캐릭터 합성 설정")

                        # 🔴 v3.12: 배경 제거 상세 진단
                        st.markdown("##### 🎭 배경 제거 상태")

                        try:
                            diag = get_bg_removal_diagnostic()

                            diag_col1, diag_col2 = st.columns([2, 1])

                            with diag_col1:
                                if diag['available']:
                                    st.success(diag['message'])
                                    st.info("✅ 캐릭터 이미지에 배경이 있으면 합성 시 자동으로 제거됩니다.")
                                else:
                                    st.error(diag['message'])
                                    st.warning("⚠️ 배경 제거 없이 합성되면 캐릭터 배경이 보일 수 있습니다!")

                                    # 상세 상태
                                    with st.expander("🔍 상세 진단"):
                                        st.write(f"- 모듈 로드: {'✅' if diag['module_loaded'] else '❌'}")
                                        st.write(f"- rembg 설치: {'✅' if diag['rembg_installed'] else '❌'}")
                                        st.code(diag['install_cmd'], language="bash")

                                    install_rembg_ui(key_suffix="settings")

                            with diag_col2:
                                if diag['available']:
                                    if st.button("🧪 테스트", key="test_bg_removal"):
                                        success, msg = test_bg_removal()
                                        if success:
                                            st.success(msg)
                                        else:
                                            st.error(msg)
                        except Exception as e:
                            bg_available, bg_msg = is_bg_removal_available()
                            if bg_available:
                                st.success(bg_msg)
                            else:
                                st.error(bg_msg)
                                install_rembg_ui(key_suffix="settings")

                        st.divider()

                        # 씬-캐릭터 매핑 정보
                        st.markdown("##### 📊 씬-캐릭터 매핑 현황")
                        if matcher:
                            ms = matcher.get_mapping_summary()
                            settings_col1, settings_col2, settings_col3 = st.columns(3)
                            with settings_col1:
                                st.metric("총 매핑", ms['total'])
                            with settings_col2:
                                st.metric("자동 매칭", ms['matched'])
                            with settings_col3:
                                st.metric("기본값", ms['default'])

                            if ms['by_character']:
                                st.write("**캐릭터별 등장:**")
                                for name, count in ms['by_character'].items():
                                    st.write(f"- {name}: {count}회")
                        else:
                            st.info("씬-캐릭터 매핑 정보가 없습니다.")

                        st.divider()

                        # 캐시 관리
                        st.markdown("##### 🗑️ 캐시 관리")
                        cache_dir = project_path / "infographics" / "composites" / ".bg_removed_cache"
                        cache_count = len(list(cache_dir.glob("*_nobg.png"))) if cache_dir.exists() else 0

                        st.write(f"배경 제거 캐시: **{cache_count}**개 파일")

                        if st.button("🗑️ 배경 제거 캐시 삭제", key="clear_bg_cache"):
                            if cache_dir.exists():
                                import shutil
                                shutil.rmtree(cache_dir)
                                st.success("캐시가 삭제되었습니다.")
                                st.rerun()

                    # 합성 결과 미리보기
                    composite_scenes = [s for s in infographic_data.scenes if s.is_composite_ready]
                    if composite_scenes:
                        composites_dir = str(project_path / "infographics" / "composites")

                        with st.expander(f"👤 합성 결과 미리보기 ({len(composite_scenes)}개)", expanded=True):
                            cols_per_row = 5
                            for row_start in range(0, len(composite_scenes), cols_per_row):
                                cols = st.columns(cols_per_row)
                                for j, col in enumerate(cols):
                                    idx = row_start + j
                                    if idx >= len(composite_scenes):
                                        break
                                    scene = composite_scenes[idx]
                                    with col:
                                        # 썸네일 이미지 (클릭 시 확대)
                                        if scene.composite_thumbnail_path and os.path.exists(scene.composite_thumbnail_path):
                                            render_lightbox_image(scene.composite_thumbnail_path, key=f"comp_scene_{idx}")
                                        else:
                                            st.markdown(
                                                f"""
                                                <div style="
                                                    background: #e8f5e9;
                                                    border-radius: 8px;
                                                    padding: 15px;
                                                    text-align: center;
                                                    height: 60px;
                                                    display: flex;
                                                    align-items: center;
                                                    justify-content: center;
                                                ">
                                                    <span style="font-size: 20px;">👤</span>
                                                </div>
                                                """,
                                                unsafe_allow_html=True
                                            )

                                        st.caption(f"씬 {scene.scene_id}")

                                        # 재생 버튼
                                        btn_col1, btn_col2 = st.columns(2)
                                        with btn_col1:
                                            if st.button("▶️", key=f"play_comp_{scene.scene_id}", help="미리보기"):
                                                st.session_state[f'show_comp_video_{scene.scene_id}'] = True
                                        with btn_col2:
                                            if scene.composite_video_path and os.path.exists(scene.composite_video_path):
                                                if st.button("📂", key=f"open_comp_{scene.scene_id}", help="폴더"):
                                                    open_file_location(scene.composite_video_path)

                                        # 비디오 플레이어
                                        if st.session_state.get(f'show_comp_video_{scene.scene_id}', False):
                                            if scene.composite_video_path and os.path.exists(scene.composite_video_path):
                                                st.video(scene.composite_video_path)
                                            if st.button("닫기", key=f"close_comp_{scene.scene_id}"):
                                                st.session_state[f'show_comp_video_{scene.scene_id}'] = False
                                                st.rerun()

                            # 폴더 열기 버튼
                            st.divider()
                            comp_folder_col1, comp_folder_col2 = st.columns(2)
                            with comp_folder_col1:
                                if st.button("📂 합성 폴더 열기", use_container_width=True, key="open_composites_folder"):
                                    open_folder(composites_dir)
                            with comp_folder_col2:
                                if st.button("🗑️ 합성 결과 초기화", use_container_width=True, key="clear_composites"):
                                    for scene in composite_scenes:
                                        scene.is_composite_ready = False
                                        scene.composite_video_path = None
                                        scene.composite_thumbnail_path = None
                                    visual_manager.set_infographic_data(infographic_data)
                                    st.success("합성 상태가 초기화되었습니다.")
                                    st.rerun()

            st.divider()

            # === 6. 씬별 시각 자료 선택 ===
            st.markdown("### 🎯 6. 씬별 시각 자료 선택")

            # 씬 데이터 로드
            scenes_path = project_path / "analysis" / "scenes.json"
            if scenes_path.exists():
                with open(scenes_path, "r", encoding="utf-8") as f:
                    scenes_for_selection = json.load(f)

                if scenes_for_selection:
                    # ⭐ 성능 최적화: 파일 시스템 스캔 캐싱
                    _cache_key = f"scene_selection_files_{project_path}"
                    if _cache_key not in st.session_state or st.session_state.get("_scene_files_dirty", False):
                        ai_images_dir = project_path / "images" / "scenes"
                        ai_images = list(ai_images_dir.glob("*.png")) if ai_images_dir.exists() else []

                        infographic_thumbs_dir = project_path / "infographics" / "thumbnails"
                        infographic_thumbs = list(infographic_thumbs_dir.glob("*.png")) if infographic_thumbs_dir.exists() else []

                        infographic_videos_dir = project_path / "infographics" / "videos"
                        infographic_videos = list(infographic_videos_dir.glob("infographic_scene_*.mp4")) if infographic_videos_dir.exists() else []

                        composites_dir = project_path / "infographics" / "composites"
                        composite_videos = list(composites_dir.glob("composite_scene_*.mp4")) if composites_dir.exists() else []

                        st.session_state[_cache_key] = {
                            "ai_images": ai_images,
                            "infographic_thumbs": infographic_thumbs,
                            "infographic_videos": infographic_videos,
                            "composite_videos": composite_videos,
                            "ai_images_dir": ai_images_dir,
                            "infographic_thumbs_dir": infographic_thumbs_dir,
                            "infographic_videos_dir": infographic_videos_dir,
                            "composites_dir": composites_dir,
                        }
                        st.session_state["_scene_files_dirty"] = False
                    else:
                        _cached = st.session_state[_cache_key]
                        ai_images = _cached["ai_images"]
                        infographic_thumbs = _cached["infographic_thumbs"]
                        infographic_videos = _cached["infographic_videos"]
                        composite_videos = _cached["composite_videos"]
                        ai_images_dir = _cached["ai_images_dir"]
                        infographic_thumbs_dir = _cached["infographic_thumbs_dir"]
                        infographic_videos_dir = _cached["infographic_videos_dir"]
                        composites_dir = _cached["composites_dir"]

                    # 선택 초기화 (최초 1회만)
                    _init_key = f"scene_sel_initialized_{project_path}"
                    if _init_key not in st.session_state:
                        visual_manager.initialize_selections_from_scenes(
                            [s.get("scene_id", i+1) for i, s in enumerate(scenes_for_selection)]
                        )
                        # 파일 시스템 기반 동영상 경로 동기화
                        for i, scene in enumerate(scenes_for_selection):
                            scene_id = scene.get("scene_id", i + 1)
                            selection = visual_manager.state.selections.get(scene_id)
                            if selection:
                                video_path = infographic_videos_dir / f"infographic_scene_{scene_id:03d}.mp4"
                                if video_path.exists():
                                    selection.infographic_video = str(video_path)
                                composite_path = composites_dir / f"composite_scene_{scene_id:03d}.mp4"
                                if composite_path.exists():
                                    selection.composite_video = str(composite_path)
                        st.session_state[_init_key] = True

                    # 통계 표시 + 새로고침 버튼
                    stats = visual_manager.get_statistics()
                    stat_col1, stat_col2, stat_col3, stat_col4, stat_col5, stat_col6, stat_col_refresh = st.columns([1, 1, 1, 1, 1, 1, 0.5])
                    with stat_col1:
                        st.metric("AI 이미지", stats["type_counts"].get("ai_image", 0))
                    with stat_col2:
                        st.metric("인포그래픽", stats["type_counts"].get("infographic", 0))
                    with stat_col3:
                        st.metric("캐릭터 합성", stats["type_counts"].get("composite", 0))
                    with stat_col4:
                        st.metric("🎬 동영상", f"{len(infographic_videos)}/{len(composite_videos)}", help="인포그래픽/합성")
                    with stat_col5:
                        st.metric("⏳ 생성필요", stats.get("videos_needed", 0))
                    with stat_col6:
                        st.metric("확정률", f"{stats['completion_rate']:.0f}%")
                    with stat_col_refresh:
                        if st.button("🔄", key="refresh_scene_files", help="파일 목록 새로고침"):
                            st.session_state["_scene_files_dirty"] = True
                            st.session_state.pop(f"scene_sel_initialized_{project_path}", None)
                            st.rerun()

                    # 일괄 적용 버튼
                    bulk_col1, bulk_col2, bulk_col3, bulk_col4 = st.columns(4)
                    with bulk_col1:
                        if st.button("🎨 전체 AI 이미지로", key="bulk_ai", use_container_width=True):
                            scene_nums = [s.get("scene_id", i+1) for i, s in enumerate(scenes_for_selection)]
                            visual_manager.apply_bulk_type(scene_nums, VisualType.AI_IMAGE)
                            st.rerun()
                    with bulk_col2:
                        if st.button("📊 전체 인포그래픽으로", key="bulk_infographic", use_container_width=True):
                            scene_nums = [s.get("scene_id", i+1) for i, s in enumerate(scenes_for_selection)]
                            visual_manager.apply_bulk_type(scene_nums, VisualType.INFOGRAPHIC)
                            st.rerun()
                    with bulk_col3:
                        if st.button("🤖 AI 추천 적용", key="apply_ai_recommendation", use_container_width=True):
                            try:
                                from utils.ai_visual_recommender import AIVisualRecommender
                                recommender = AIVisualRecommender()

                                has_infographic = infographic_data is not None
                                for i, scene in enumerate(scenes_for_selection):
                                    scene_id = scene.get("scene_id", i + 1)
                                    script_text = scene.get("script_text", "")
                                    scene_title = scene.get("title", "")

                                    result = recommender.recommend(
                                        script_text=script_text,
                                        scene_title=scene_title,
                                        has_infographic=has_infographic
                                    )

                                    visual_manager.set_ai_recommendation(
                                        scene_id,
                                        result.visual_type,
                                        result.reason,
                                        result.score
                                    )
                                    visual_manager.set_visual_type(scene_id, result.visual_type, auto_save=False)

                                visual_manager.save_state()
                                st.success("AI 추천이 적용되었습니다!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"AI 추천 오류: {str(e)}")
                    with bulk_col4:
                        if st.button("💾 선택 저장", type="primary", key="save_selections", use_container_width=True):
                            visual_manager.save_state()
                            st.success("선택이 저장되었습니다!")

                    # 📥 일괄 다운로드 섹션
                    st.markdown("#### 📥 자료 일괄 다운로드")
                    dl_col1, dl_col2, dl_col3, dl_col4 = st.columns(4)

                    # 이미지 경로 수집
                    scene_images = []
                    scene_videos = []
                    for i, scene in enumerate(scenes_for_selection):
                        scene_id = scene.get("scene_id", i + 1)
                        selection = visual_manager.get_selection(scene_id)

                        # AI 이미지
                        for img in ai_images:
                            if f"_{scene_id:03d}" in img.stem or f"scene_{scene_id}" in img.stem:
                                scene_images.append({"scene_num": scene_id, "image_path": str(img), "type": "ai"})
                                break
                            elif i < len(ai_images) and img == ai_images[i]:
                                scene_images.append({"scene_num": scene_id, "image_path": str(ai_images[i]), "type": "ai"})
                                break

                        # 인포그래픽 동영상
                        if selection and selection.selected_type == VisualType.INFOGRAPHIC:
                            for vid in infographic_videos:
                                if f"_{scene_id:03d}" in vid.stem or f"scene{scene_id}" in vid.stem.lower():
                                    scene_videos.append({"scene_num": scene_id, "video_path": str(vid), "type": "video"})
                                    break

                    # v1.1: ZIP 데이터 캐싱 (MediaFileHandler 에러 방지)
                    # 기존: 매 렌더링마다 ZIP 생성 → rerun 시 파일 ID 변경 → 다운로드 실패
                    # 수정: session_state에 캐싱 + 동적 키 사용

                    # 캐시 키 생성 (내용 기반)
                    img_cache_key = f"sb_zip_img_{len(scene_images)}_{hash(str([i.get('scene_num') for i in scene_images])) if scene_images else 0}"
                    vid_cache_key = f"sb_zip_vid_{len(scene_videos)}_{hash(str([v.get('scene_num') for v in scene_videos])) if scene_videos else 0}"
                    all_cache_key = f"sb_zip_all_{len(scene_images)}_{len(scene_videos)}"

                    with dl_col1:
                        if scene_images:
                            # 캐시된 데이터 확인 또는 생성
                            if img_cache_key not in st.session_state:
                                from utils.download_manager import SceneDownloadManager
                                manager = SceneDownloadManager(video_path=str(project_path))
                                st.session_state[img_cache_key] = manager.create_zip_buffer(images=scene_images)
                                st.session_state[f"{img_cache_key}_name"] = manager.get_zip_filename("scene_images")

                            st.download_button(
                                label=f"🖼️ 이미지 다운로드 ({len(scene_images)}개)",
                                data=st.session_state[img_cache_key],
                                file_name=st.session_state.get(f"{img_cache_key}_name", "scene_images.zip"),
                                mime="application/zip",
                                key=f"sb_dl_images_{len(scene_images)}",
                                use_container_width=True
                            )
                        else:
                            st.button("🖼️ 이미지 없음", disabled=True, use_container_width=True, key="sb_img_disabled")

                    with dl_col2:
                        if scene_videos:
                            # 캐시된 데이터 확인 또는 생성
                            if vid_cache_key not in st.session_state:
                                from utils.download_manager import SceneDownloadManager
                                manager = SceneDownloadManager(video_path=str(project_path))
                                st.session_state[vid_cache_key] = manager.create_zip_buffer(videos=scene_videos)
                                st.session_state[f"{vid_cache_key}_name"] = manager.get_zip_filename("scene_videos")

                            st.download_button(
                                label=f"🎬 동영상 다운로드 ({len(scene_videos)}개)",
                                data=st.session_state[vid_cache_key],
                                file_name=st.session_state.get(f"{vid_cache_key}_name", "scene_videos.zip"),
                                mime="application/zip",
                                key=f"sb_dl_videos_{len(scene_videos)}",
                                use_container_width=True
                            )
                        else:
                            st.button("🎬 동영상 없음", disabled=True, use_container_width=True, key="sb_vid_disabled")

                    with dl_col3:
                        if scene_images or scene_videos:
                            # 캐시된 데이터 확인 또는 생성
                            if all_cache_key not in st.session_state:
                                from utils.download_manager import SceneDownloadManager
                                manager = SceneDownloadManager(video_path=str(project_path))
                                st.session_state[all_cache_key] = manager.create_zip_buffer(
                                    images=scene_images if scene_images else None,
                                    videos=scene_videos if scene_videos else None
                                )
                                st.session_state[f"{all_cache_key}_name"] = manager.get_zip_filename("storyboard_assets")

                            total_items = len(scene_images) + len(scene_videos)
                            st.download_button(
                                label=f"📦 전체 다운로드 ({total_items}개)",
                                data=st.session_state[all_cache_key],
                                file_name=st.session_state.get(f"{all_cache_key}_name", "storyboard_assets.zip"),
                                mime="application/zip",
                                key=f"sb_dl_all_{total_items}",
                                type="primary",
                                use_container_width=True
                            )
                        else:
                            st.button("📦 자료 없음", disabled=True, use_container_width=True, key="sb_all_disabled")

                    with dl_col4:
                        if st.button("📁 프로젝트 폴더 저장", key="storyboard_save_to_folder", use_container_width=True):
                            try:
                                from utils.download_manager import SceneDownloadManager
                                manager = SceneDownloadManager(video_path=str(project_path))
                                saved_count = 0

                                if scene_images:
                                    success, save_dir, saved_files = manager.save_to_project_folder(
                                        images=scene_images,
                                        subfolder="storyboard_images"
                                    )
                                    if success:
                                        saved_count += len(saved_files)

                                if scene_videos:
                                    success, save_dir, saved_files = manager.save_videos_to_project_folder(
                                        videos=scene_videos,
                                        subfolder="storyboard_videos"
                                    )
                                    if success:
                                        saved_count += len(saved_files)

                                if saved_count > 0:
                                    st.success(f"✅ {saved_count}개 파일 저장 완료!")
                                else:
                                    st.warning("저장할 파일이 없습니다.")
                            except Exception as e:
                                st.error(f"저장 오류: {e}")

                    # 🔄 프로세스 간 동기화 섹션
                    from utils.sync_manager import ProcessType
                    from utils.sync_ui import render_sync_buttons
                    render_sync_buttons(ProcessType.STORYBOARD)

                    st.divider()

                    # 씬별 선택 UI - ⭐ 페이지네이션 적용 (성능 최적화)
                    _SCENES_PER_PAGE = 10
                    _total_scenes = len(scenes_for_selection)
                    _total_pages = (_total_scenes + _SCENES_PER_PAGE - 1) // _SCENES_PER_PAGE

                    # 페이지 선택 UI
                    _page_col1, _page_col2, _page_col3 = st.columns([1, 2, 1])
                    with _page_col1:
                        if st.button("◀ 이전", key="scene_sel_prev", disabled=st.session_state.get("scene_sel_page", 0) <= 0):
                            st.session_state["scene_sel_page"] = max(0, st.session_state.get("scene_sel_page", 0) - 1)
                            st.rerun()
                    with _page_col2:
                        _current_page = st.session_state.get("scene_sel_page", 0)
                        st.markdown(f"**페이지 {_current_page + 1} / {_total_pages}** ({_total_scenes}개 씬)")
                    with _page_col3:
                        if st.button("다음 ▶", key="scene_sel_next", disabled=st.session_state.get("scene_sel_page", 0) >= _total_pages - 1):
                            st.session_state["scene_sel_page"] = min(_total_pages - 1, st.session_state.get("scene_sel_page", 0) + 1)
                            st.rerun()

                    # 현재 페이지의 씬만 표시
                    _start_idx = st.session_state.get("scene_sel_page", 0) * _SCENES_PER_PAGE
                    _end_idx = min(_start_idx + _SCENES_PER_PAGE, _total_scenes)
                    _paginated_scenes = scenes_for_selection[_start_idx:_end_idx]

                    for i, scene in enumerate(_paginated_scenes):
                        _actual_idx = _start_idx + i  # 실제 인덱스
                        scene_id = scene.get("scene_id", _actual_idx + 1)
                        script_text = scene.get("script_text", "")

                        selection = visual_manager.get_selection(scene_id)
                        current_type = selection.selected_type if selection else VisualType.AI_IMAGE

                        with st.container():
                            main_col1, main_col2 = st.columns([2, 3])

                            with main_col1:
                                # 씬 번호 + AI 추천 표시
                                header_cols = st.columns([3, 2])
                                with header_cols[0]:
                                    st.markdown(f"#### 씬 {scene_id}")
                                with header_cols[1]:
                                    if selection and selection.ai_recommendation:
                                        rec_icon = {"ai_image": "🎨", "infographic": "📊", "composite": "👤"}.get(
                                            selection.ai_recommendation.value, "❓"
                                        )
                                        st.caption(f"🤖 추천: {rec_icon} ({selection.recommendation_score:.0%})")

                                st.caption(script_text[:80] + "..." if len(script_text) > 80 else script_text)

                                # AI 추천 이유 표시
                                if selection and selection.recommendation_reason:
                                    st.caption(f"💡 {selection.recommendation_reason}")

                                # 시각 자료 타입 선택
                                type_options = ["🎨 AI 이미지", "📊 인포그래픽", "👤 캐릭터 합성"]
                                type_values = [VisualType.AI_IMAGE, VisualType.INFOGRAPHIC, VisualType.COMPOSITE]

                                current_idx = type_values.index(current_type) if current_type in type_values else 0

                                selected_type_name = st.radio(
                                    f"시각 자료 타입 (씬 {scene_id})",
                                    type_options,
                                    index=current_idx,
                                    key=f"visual_type_{scene_id}_{i}",
                                    horizontal=True,
                                    label_visibility="collapsed"
                                )

                                new_type = type_values[type_options.index(selected_type_name)]
                                if new_type != current_type:
                                    visual_manager.set_visual_type(scene_id, new_type, auto_save=False)

                                # 내보내기 미디어 타입 표시
                                if selection:
                                    _, media_type = selection.get_export_media()
                                    media_icon = "🖼️" if media_type == MediaType.IMAGE else "🎬"
                                    st.caption(f"내보내기: {media_icon} {media_type.value}")

                            with main_col2:
                                img_cols = st.columns(3)

                                # AI 이미지 미리보기
                                with img_cols[0]:
                                    st.caption("🎨 AI 이미지")
                                    ai_img = None
                                    for img in ai_images:
                                        if f"_{scene_id:03d}" in img.stem or f"scene_{scene_id}" in img.stem:
                                            ai_img = img
                                            break
                                    if not ai_img and _actual_idx < len(ai_images):
                                        ai_img = ai_images[_actual_idx]

                                    if ai_img and ai_img.exists():
                                        st.image(str(ai_img), width=120)
                                        if st.button("🔍", key=f"zoom_ai_{scene_id}_{i}", help="확대"):
                                            st.session_state[f"zoom_ai_{scene_id}_{i}"] = True
                                        if st.session_state.get(f"zoom_ai_{scene_id}_{i}", False):
                                            from utils.image_viewer import show_image_modal
                                            show_image_modal(str(ai_img), scene_id, None, f"씬 {scene_id} AI 이미지")
                                            st.session_state[f"zoom_ai_{scene_id}_{i}"] = False
                                        if selection:
                                            visual_manager.state.selections[scene_id].ai_image_path = str(ai_img)
                                    else:
                                        st.info("없음")

                                # 인포그래픽 썸네일 미리보기
                                with img_cols[1]:
                                    # 동영상 상태 확인
                                    info_video_path = infographic_videos_dir / f"infographic_scene_{scene_id:03d}.mp4"
                                    info_video_exists = info_video_path.exists()
                                    video_icon = "🎬" if info_video_exists else "⏳"
                                    st.caption(f"📊 인포그래픽 {video_icon}")

                                    info_thumb = None

                                    # infographic_data에서 찾기
                                    if infographic_data:
                                        for info_scene in infographic_data.scenes:
                                            if info_scene.scene_id == scene_id:
                                                info_thumb = info_scene.thumbnail_path or info_scene.first_frame_path
                                                break

                                    # 디렉토리에서 찾기
                                    if not info_thumb:
                                        for img in infographic_thumbs:
                                            if f"_{scene_id:03d}" in img.stem or f"scene_{scene_id}" in img.stem:
                                                info_thumb = str(img)
                                                break

                                    if info_thumb and os.path.exists(info_thumb):
                                        st.image(info_thumb, width=120)
                                        if st.button("🔍", key=f"zoom_info_{scene_id}_{i}", help="확대"):
                                            st.session_state[f"zoom_info_{scene_id}_{i}"] = True
                                        if st.session_state.get(f"zoom_info_{scene_id}_{i}", False):
                                            from utils.image_viewer import show_image_modal
                                            show_image_modal(info_thumb, scene_id, None, f"씬 {scene_id} 인포그래픽")
                                            st.session_state[f"zoom_info_{scene_id}_{i}"] = False
                                        if selection:
                                            visual_manager.state.selections[scene_id].infographic_thumbnail = info_thumb
                                            if info_video_exists:
                                                visual_manager.state.selections[scene_id].infographic_video = str(info_video_path)
                                    else:
                                        st.info("없음")

                                # 캐릭터 합성 미리보기
                                with img_cols[2]:
                                    # 합성 동영상 상태 확인
                                    comp_video_path = composites_dir / f"composite_scene_{scene_id:03d}.mp4"
                                    comp_video_exists = comp_video_path.exists()
                                    comp_icon = "🎬" if comp_video_exists else "⏳"
                                    st.caption(f"👤 합성 {comp_icon}")

                                    comp_thumb = None

                                    if infographic_data:
                                        for info_scene in infographic_data.scenes:
                                            if info_scene.scene_id == scene_id and info_scene.is_composite_ready:
                                                comp_thumb = info_scene.composite_thumbnail_path
                                                break

                                    # 합성 썸네일 직접 확인
                                    if not comp_thumb:
                                        comp_thumb_path = composites_dir / f"composite_scene_{scene_id:03d}_thumb.png"
                                        if comp_thumb_path.exists():
                                            comp_thumb = str(comp_thumb_path)

                                    if comp_thumb and os.path.exists(comp_thumb):
                                        st.image(comp_thumb, width=120)
                                        if st.button("🔍", key=f"zoom_comp_{scene_id}_{i}", help="확대"):
                                            st.session_state[f"zoom_comp_{scene_id}_{i}"] = True
                                        if st.session_state.get(f"zoom_comp_{scene_id}_{i}", False):
                                            from utils.image_viewer import show_image_modal
                                            show_image_modal(comp_thumb, scene_id, None, f"씬 {scene_id} 합성")
                                            st.session_state[f"zoom_comp_{scene_id}_{i}"] = False
                                        if selection:
                                            visual_manager.state.selections[scene_id].composite_thumbnail = comp_thumb
                                            if comp_video_exists:
                                                visual_manager.state.selections[scene_id].composite_video = str(comp_video_path)
                                    elif comp_video_exists:
                                        # 동영상은 있지만 썸네일이 없을 때
                                        st.success("🎬 준비됨")
                                        if selection:
                                            visual_manager.state.selections[scene_id].composite_video = str(comp_video_path)
                                    else:
                                        st.info("없음")

                            st.divider()

                    # === 7. 내보내기 요약 ===
                    st.markdown("### 📤 7. 내보내기 요약")

                    export_data = visual_manager.export_for_video_pipeline()

                    if export_data:
                        # 미디어 타입별 카운트
                        image_count = sum(1 for e in export_data if e["media_type"] == "image")
                        video_count = sum(1 for e in export_data if e["media_type"] == "video")

                        exp_col1, exp_col2, exp_col3 = st.columns(3)
                        with exp_col1:
                            st.metric("총 씬", len(export_data))
                        with exp_col2:
                            st.metric("🖼️ 이미지", image_count)
                        with exp_col3:
                            st.metric("🎬 동영상", video_count)

                        with st.expander("📋 내보내기 상세", expanded=False):
                            for item in export_data:
                                media_icon = "🖼️" if item["media_type"] == "image" else "🎬"
                                visual_icon = {"ai_image": "🎨", "infographic": "📊", "composite": "👤"}.get(item["visual_type"], "❓")
                                finalized = "✅" if item["is_finalized"] else "⏳"
                                st.text(f"{finalized} 씬 {item['scene_number']}: {visual_icon} {item['visual_type']} → {media_icon} {item['media_type']}")

                        # 내보내기 JSON 다운로드
                        st.download_button(
                            "📥 내보내기 JSON 다운로드",
                            data=json.dumps(export_data, ensure_ascii=False, indent=2),
                            file_name="visual_export.json",
                            mime="application/json",
                            use_container_width=True
                        )
                    else:
                        st.info("내보내기할 씬이 없습니다. 씬별 시각 자료를 선택하세요.")

            else:
                st.warning("씬 분석 결과가 없습니다. '자동 조합' 또는 '수동 구성' 탭에서 씬을 먼저 생성하세요.")

            Profiler.log("📊 인포그래픽 탭 종료 (활성)")

# === 자동 조합 탭 ===
with tab_auto:
    # 사이드바 옵션 (탭 외부에서 설정하지만, 자동 조합 탭에서 사용)
    with st.sidebar:
        st.subheader("📐 표시 옵션")
        language = st.selectbox(
            "언어",
            ["ko", "ja"],
            format_func=lambda x: "한국어" if x == "ko" else "일본어",
            index=0 if project_config.get("language") == "ko" else 1
        )
        # ⭐ v3.27: 표시 옵션 영구 저장 (persistent_checkbox)
        show_images = persistent_checkbox("이미지 표시", page="storyboard", setting_key="show_images", default_value=True)
        show_script = persistent_checkbox("스크립트 표시", page="storyboard", setting_key="show_script", default_value=True)
        show_direction = persistent_checkbox("연출가이드 표시", page="storyboard", setting_key="show_direction", default_value=True)
        show_characters = persistent_checkbox("캐릭터 표시", page="storyboard", setting_key="show_characters", default_value=True)
        show_prompt = persistent_checkbox("프롬프트 표시", page="storyboard", setting_key="show_prompt", default_value=False)
        show_video_prompt = persistent_checkbox("🎬 비디오 프롬프트 표시", page="storyboard", setting_key="show_video_prompt", default_value=True)

    # 씬 데이터 로드
    scenes_path = project_path / "analysis" / "scenes.json"
    # 이미지 디렉토리 (backgrounds > scenes > content 순 우선)
    backgrounds_images_dir = project_path / "images" / "backgrounds"
    scenes_images_dir = project_path / "images" / "scenes"
    content_images_dir = project_path / "images" / "content"
    audio_dir = project_path / "audio"

    # ⭐ 이미지 디렉토리 선택 (세션 캐싱으로 반복 로그 방지)
    def get_images_dir_cached():
        """이미지 디렉토리 결정 (세션당 한 번만 로그)"""
        cache_key = f"_storyboard_images_dir_{project_path}"
        log_key = f"_storyboard_images_dir_logged_{project_path}"

        # 캐시에 있으면 바로 반환 (로그 없음)
        if cache_key in st.session_state:
            return st.session_state[cache_key]

        def has_images(d):
            return d.exists() and (any(d.glob("*.png")) or any(d.glob("*.jpg")) or any(d.glob("*.webp")))

        if has_images(backgrounds_images_dir):
            selected_dir = backgrounds_images_dir
            source = "backgrounds"
        elif has_images(scenes_images_dir):
            selected_dir = scenes_images_dir
            source = "scenes"
        else:
            selected_dir = content_images_dir
            source = "content"

        # 세션에 저장
        st.session_state[cache_key] = selected_dir

        # ⭐ 성능 최적화: 로그 제거 (불필요한 콘솔 출력 방지)
        # 디버깅 필요 시에만 활성화:
        # if log_key not in st.session_state:
        #     st.session_state[log_key] = True
        #     print(f"[DEBUG] {source} 폴더: {selected_dir}", flush=True)

        return selected_dir

    images_dir = get_images_dir_cached()

    # 씬 분석 결과 확인
    if not scenes_path.exists():
        st.warning("씬 분석 결과가 없습니다.")
        st.info("방법 1: 3.5단계에서 씬 분석을 실행하세요.")
        st.page_link("pages/3.5_🎬_씬_분석.py", label="🎬 씬 분석으로 이동", icon="➡️")

        st.divider()
        st.info("방법 2: '수동 구성' 탭에서 직접 스토리보드를 만들 수 있습니다.")
        st.info("방법 3: 기존 이미지 프롬프트로 스토리보드를 생성할 수 있습니다.")

        # 기존 프롬프트 파일로 대체
        prompts_path = project_path / "prompts" / "image_prompts.json"
        if prompts_path.exists():
            with open(prompts_path, "r", encoding="utf-8") as f:
                prompts = json.load(f)

            if prompts:
                st.success(f"이미지 프롬프트 {len(prompts)}개 발견!")

                if st.button("프롬프트 기반 스토리보드 생성", key="create_from_prompts"):
                    # 프롬프트 기반 스토리보드
                    scenes = []
                    for i, p in enumerate(prompts):
                        scenes.append({
                            "scene_id": i + 1,
                            "script_text": p.get("text_content", ""),
                            "duration_estimate": p.get("duration_sec", 10),
                            "image_prompt_en": p.get("prompt", ""),
                            "filename": p.get("filename", f"{i+1:03d}.png")
                        })

                    # 임시 저장
                    scenes_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(scenes_path, "w", encoding="utf-8") as f:
                        json.dump(scenes, f, ensure_ascii=False, indent=2)

                    st.success("프롬프트 기반 스토리보드 생성 완료!")
                    st.rerun()
    else:
        # 씬 데이터 로드
        with open(scenes_path, "r", encoding="utf-8") as f:
            scenes = json.load(f)

        # ═══════════════════════════════════════════════════════════════
        # v3.34: 캐릭터 자동 연동 (페이지 로드 시 한 번 실행)
        # ═══════════════════════════════════════════════════════════════
        if NANO_COMPOSITE_AVAILABLE and auto_link_characters_to_scenes:
            # 세션 캐시 키 (프로젝트 + 캐시 버전별)
            auto_link_cache_key = f"_char_auto_linked_{str(project_path)}_{st.session_state.get('image_cache_version', 0)}"

            if auto_link_cache_key not in st.session_state:
                # 자동 연동 실행
                link_result = auto_link_characters_to_scenes(scenes, str(project_path))

                if link_result.get("linked_count", 0) > 0:
                    # 씬 데이터 저장 (연동 정보 포함)
                    try:
                        with open(scenes_path, "w", encoding="utf-8") as f:
                            json.dump(scenes, f, ensure_ascii=False, indent=2)
                        print(f"[스토리보드] ✅ 캐릭터 자동 연동 완료: {link_result['linked_count']}개 씬")
                    except Exception as e:
                        print(f"[스토리보드] ⚠️ 씬 데이터 저장 실패: {e}")

                # 캐시에 결과 저장 (중복 실행 방지)
                st.session_state[auto_link_cache_key] = link_result

        if not scenes:
            st.warning("씬 데이터가 비어있습니다.")
        else:
            # === 이미지 자동 동기화 섹션 ===
            sync_header_col1, sync_header_col2 = st.columns([4, 1])
            with sync_header_col1:
                st.subheader("🔄 이미지 자동 동기화")
            with sync_header_col2:
                if st.button("🔄 새로고침", key="refresh_image_cache_sync", help="이미지 캐시 새로고침 (새 이미지 반영, 캐릭터 재연동 포함)"):
                    # ⭐ 전체 캐시 초기화 (명시적 새로고침)
                    cleared = invalidate_all_image_caches(full_reset=True)

                    # ⭐ v3.34: 캐릭터 자동 연동 캐시 초기화 (재연동 실행)
                    auto_link_keys = [k for k in st.session_state.keys() if k.startswith("_char_auto_linked_")]
                    for key in auto_link_keys:
                        del st.session_state[key]

                    st.toast(f"✅ 이미지 캐시 새로고침 완료! ({cleared}개 항목, 캐릭터 재연동 예정)")
                    st.rerun()

            # ⭐ 캐싱된 ImageSceneMatcher 사용 (v3.17 성능 최적화)
            matcher = get_cached_image_scene_matcher(str(project_path))

            # ⭐ 매칭 요약 캐싱 (성능 개선 v3.18)
            # get_matching_summary()는 파일 시스템을 스캔하므로 매 렌더링마다 호출하지 않음
            summary_cache_key = f"matching_summary_{str(project_path)}_{st.session_state.get('image_cache_version', 0)}"
            if summary_cache_key not in st.session_state:
                summary = matcher.get_matching_summary(scenes)
                st.session_state[summary_cache_key] = summary
            else:
                summary = st.session_state[summary_cache_key]

            # 매칭 상태 표시
            sync_col1, sync_col2, sync_col3, sync_col4 = st.columns(4)
            with sync_col1:
                st.metric("씬 번호 매칭", f"{summary['matched_exact']}개",
                         help="파일명에서 씬 번호를 추출하여 매칭")
            with sync_col2:
                st.metric("순차 매칭", f"{summary['matched_sequential']}개",
                         help="씬 번호 없는 이미지를 순서대로 매칭")
            with sync_col3:
                st.metric("미매칭", f"{summary['unmatched']}개",
                         delta=f"-{summary['unmatched']}" if summary['unmatched'] > 0 else None,
                         delta_color="inverse")
            with sync_col4:
                st.metric("매칭률", f"{summary['match_rate']:.1f}%")

            # 동기화 버튼
            sync_btn_col1, sync_btn_col2, sync_btn_col3 = st.columns([1, 1, 2])

            with sync_btn_col1:
                if st.button("🔄 이미지 자동 매칭", type="primary", use_container_width=True,
                            help="생성된 이미지를 씬에 자동으로 매칭합니다 (최신 이미지 우선)"):
                    with st.spinner("이미지 매칭 중..."):
                        # ⭐ 먼저 캐시 무효화 (최신 이미지 반영)
                        invalidate_all_image_caches()

                        # 최신 이미지 우선 매칭
                        sync_result = auto_sync_images_to_storyboard(
                            project_path, scenes, copy_to_scenes=True
                        )

                        # 결과 표시
                        copy_info = sync_result.get("copy_results", {})
                        summary = sync_result.get("summary", {})

                        if copy_info:
                            st.success(f"✅ 동기화 완료! 복사: {copy_info.get('copied', 0)}개, 스킵: {copy_info.get('skipped', 0)}개")
                            st.info(f"📊 검색된 이미지: {summary.get('total_images', 0)}개, 매칭률: {summary.get('match_rate', 0):.1f}%")
                            if copy_info.get("errors"):
                                with st.expander("⚠️ 오류 목록"):
                                    for err in copy_info["errors"]:
                                        st.warning(err)
                        st.rerun()

            with sync_btn_col2:
                if st.button("📊 매칭 상세 보기", use_container_width=True):
                    match_results = matcher.match_images_to_scenes(scenes)

                    with st.expander("🔍 씬별 매칭 결과", expanded=True):
                        for scene_id, info in sorted(match_results.items()):
                            match_type = info.get("match_type", "none")
                            if match_type == "exact":
                                icon = "✅"
                                status = "정확 매칭"
                            elif match_type == "sequential":
                                icon = "🔢"
                                status = "순차 매칭"
                            else:
                                icon = "❌"
                                status = "미매칭"

                            img_name = info["matched_image"].name if info["matched_image"] else "없음"
                            st.text(f"{icon} 씬 {scene_id}: {status} - {img_name}")

            with sync_btn_col3:
                st.caption("💡 이미지 파일명에 씬 번호가 포함되어 있으면 자동으로 매칭됩니다.\n예: scene_001.png, seg_001.png, 001.png")

            st.divider()

            # 이미지 파일 목록 (캐싱된 함수 사용 - 중복 로드 방지)
            # ⭐ v2.3: cache_key 사용 (해시에 포함되어 캐시 무효화 정상 동작)
            cache_key = get_image_dirs_mtime(project_path)
            image_files_tuple, image_map = load_image_files_cached(
                str(backgrounds_images_dir),
                str(scenes_images_dir),
                str(content_images_dir),
                cache_key=cache_key
            )
            image_files = [Path(p) for p in image_files_tuple]  # Path 객체로 변환

            # 통계 표시
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("총 씬 수", len(scenes))
            with col2:
                st.metric("생성된 이미지", len(image_files))
            with col3:
                total_duration = sum(s.get("duration_estimate", 10) for s in scenes)
                st.metric("예상 길이", f"{total_duration // 60}분 {total_duration % 60}초")
            with col4:
                # TTS 파일 확인
                tts_file = audio_dir / f"voice_{language}.mp3"
                tts_status = "완료" if tts_file.exists() else "없음"
                st.metric("TTS", tts_status)

            st.divider()

            # ============================================================
            # 실사 이미지 관리 섹션 (v1.0)
            # ============================================================
            with st.expander("🖼️ 실사 이미지 관리", expanded=False):
                st.caption("AI 생성 이미지를 실사 이미지로 대체하고 관리할 수 있습니다.")

                # 기존 버튼들
                batch_col1, batch_col2, batch_col3, batch_col4 = st.columns(4)

                # 전체 백업
                with batch_col1:
                    if st.button("💾 전체 백업", use_container_width=True, help="모든 AI 이미지를 백업합니다"):
                        backed_up = batch_backup_images(image_files)
                        st.toast(f"{backed_up}개 이미지 백업 완료")
                        st.rerun()

                # 전체 복원
                with batch_col2:
                    if st.button("↩️ 전체 복원", use_container_width=True, help="모든 AI 이미지를 복원합니다"):
                        restored = batch_restore_images(image_files)
                        if restored > 0:
                            # 캐시 무효화
                            for img in image_files:
                                invalidate_image_cache(str(img))
                            st.toast(f"{restored}개 이미지 복원 완료")
                            st.rerun()
                        else:
                            st.warning("복원할 백업이 없습니다.")

                # 전체 새로고침
                with batch_col3:
                    if st.button("🔄 전체 새로고침", use_container_width=True, help="모든 이미지 캐시를 새로고침합니다"):
                        # ⭐ 전체 캐시 무효화 (명시적 새로고침)
                        cleared = invalidate_all_image_caches(full_reset=True)
                        st.toast(f"이미지 캐시 새로고침됨 ({cleared}개 항목)")
                        st.rerun()

                # 이미지 폴더 열기
                with batch_col4:
                    if st.button("📂 이미지 폴더", use_container_width=True, help="이미지 폴더를 탐색기에서 엽니다"):
                        open_folder(str(scenes_images_dir))

                # 백업 상태 표시 (캐시된 결과 사용)
                # ⭐ 성능 최적화: 백업 카운트 캐싱 (매 렌더링 시 300+개 파일 확인 방지)
                backup_cache_key = f"backup_count_{str(project_path)}_{st.session_state.get('image_cache_version', 0)}"
                if backup_cache_key not in st.session_state:
                    backup_count = sum(1 for img in image_files if has_backup(img))
                    st.session_state[backup_cache_key] = backup_count
                else:
                    backup_count = st.session_state[backup_cache_key]
                if backup_count > 0:
                    st.info(f"💾 백업된 이미지: {backup_count}개 / {len(image_files)}개")

                st.divider()

                # 실사 이미지 업로드 기능 (REAL_IMAGE_MANAGER_AVAILABLE 확인)
                if REAL_IMAGE_MANAGER_AVAILABLE:
                    # 탭으로 구분 (AI 매핑 탭 추가)
                    if AI_MAPPING_PARSER_AVAILABLE:
                        real_tab1, real_tab2, real_tab3 = st.tabs(["📤 배치 업로드", "🎯 개별 씬 업로드", "🤖 AI 매핑 적용"])
                    else:
                        real_tab1, real_tab2 = st.tabs(["📤 배치 업로드", "🎯 개별 씬 업로드"])
                        real_tab3 = None

                    with real_tab1:
                        st.markdown("**파일명에서 씬 번호를 자동 인식합니다.**")
                        st.caption("예: `1.png`, `scene_05.jpg`, `씬10.webp`")

                        # 파일 업로더
                        uploaded_real_images = st.file_uploader(
                            "실사 이미지 업로드",
                            type=["png", "jpg", "jpeg", "webp"],
                            accept_multiple_files=True,
                            key="batch_real_image_upload",
                            help="씬 번호가 포함된 이미지 파일들을 업로드하세요"
                        )

                        if uploaded_real_images:
                            # 빠른 분석
                            existing_ai = get_existing_ai_images(scenes_images_dir, scenes)
                            real_results = quick_analyze_real_images(uploaded_real_images, len(scenes), existing_ai)
                            real_stats = get_real_image_stats(real_results)

                            # 업로드 완료 메시지
                            st.success(f"📁 {len(uploaded_real_images)}개 이미지 파일 업로드 완료")

                            # 통계 표시
                            stat_cols = st.columns(4)
                            with stat_cols[0]:
                                st.metric("전체", real_stats["total"])
                            with stat_cols[1]:
                                st.metric("매칭 성공", real_stats["success"])
                            with stat_cols[2]:
                                failed_count = real_stats["out_of_range"] + real_stats["invalid_name"] + real_stats["invalid_format"] + real_stats["duplicate"]
                                st.metric("실패", failed_count)
                            with stat_cols[3]:
                                replace_count = sum(1 for r in real_results if r.status == "success" and r.current_ai_image)
                                st.metric("AI 대체", replace_count)

                            # 미리보기
                            if real_stats["success"] > 0:
                                st.markdown("##### ✅ 매칭된 이미지")
                                for item in real_stats["success_items"]:
                                    icon = "🔄" if item.current_ai_image else "➕"
                                    st.text(f"{icon} 씬 {item.scene_number}: {item.filename} ({item.message})")

                            if real_stats["failed_items"]:
                                st.markdown("##### ❌ 실패 항목")
                                for item in real_stats["failed_items"]:
                                    st.text(f"⚠️ {item.filename}: {item.message}")

                            # 적용 버튼
                            if real_stats["success"] > 0:
                                st.divider()
                                apply_cols = st.columns([2, 1])
                                with apply_cols[0]:
                                    backup_ai_images = st.checkbox("AI 이미지 백업", value=True, key="batch_real_backup_ai")
                                with apply_cols[1]:
                                    apply_real_btn = st.button("🖼️ 실사 이미지 적용", type="primary", use_container_width=True, key="apply_batch_real_images")

                                if apply_real_btn:
                                    # 진행률 표시
                                    progress_bar = st.progress(0, text="이미지 저장 준비 중...")
                                    status_text = st.empty()

                                    # 진행률 콜백
                                    def real_progress_callback(current: int, total: int, filename: str):
                                        progress = current / total
                                        progress_bar.progress(progress, text=f"저장 중... ({current}/{total})")
                                        status_text.text(f"🖼️ {filename}")

                                    # 실사 이미지 적용
                                    apply_real_result = apply_real_images(
                                        uploaded_files=uploaded_real_images,
                                        results=real_results,
                                        images_folder=scenes_images_dir,
                                        backup_ai=backup_ai_images,
                                        progress_callback=real_progress_callback
                                    )

                                    # 완료 표시
                                    progress_bar.progress(1.0, text="완료!")
                                    status_text.empty()

                                    # 캐시 무효화
                                    invalidate_all_image_caches()

                                    st.success(f"✅ {apply_real_result['applied']}개 실사 이미지 적용 완료!")
                                    if apply_real_result["backed_up"] > 0:
                                        st.info(f"💾 {apply_real_result['backed_up']}개 AI 이미지 백업됨")
                                    if apply_real_result["failed"] > 0:
                                        st.warning(f"⚠️ {apply_real_result['failed']}개 저장 실패")
                                    st.rerun()

                    with real_tab2:
                        st.markdown("**특정 씬의 이미지를 직접 대체합니다.**")

                        # 씬 선택
                        scene_options = [(i+1, f"씬 {i+1}") for i in range(len(scenes))]
                        if scene_options:
                            selected_scene_idx = st.selectbox(
                                "대체할 씬 선택",
                                options=range(len(scene_options)),
                                format_func=lambda x: scene_options[x][1],
                                key="single_real_scene_select"
                            )
                            target_scene_num = scene_options[selected_scene_idx][0]

                            # 현재 이미지 미리보기
                            existing_ai = get_existing_ai_images(scenes_images_dir, scenes)
                            current_ai_path = existing_ai.get(target_scene_num)

                            if current_ai_path and Path(current_ai_path).exists():
                                st.image(current_ai_path, caption=f"현재 씬 {target_scene_num} AI 이미지", width=200)
                            else:
                                st.info(f"씬 {target_scene_num}의 이미지가 없습니다.")

                            # 파일 업로더
                            single_real_image = st.file_uploader(
                                "실사 이미지 선택",
                                type=["png", "jpg", "jpeg", "webp"],
                                key=f"single_real_upload_{target_scene_num}"
                            )

                            if single_real_image:
                                # 미리보기
                                st.image(single_real_image, caption="업로드할 실사 이미지", width=200)

                                single_backup_ai = st.checkbox("AI 이미지 백업", value=True, key=f"single_backup_ai_{target_scene_num}")

                                if st.button(f"🔄 씬 {target_scene_num} 이미지 대체", type="primary", key=f"apply_single_real_{target_scene_num}"):
                                    single_result = save_single_real_image(
                                        uploaded_file=single_real_image,
                                        images_folder=scenes_images_dir,
                                        scene_num=target_scene_num,
                                        current_ai_image=current_ai_path,
                                        backup_ai=single_backup_ai
                                    )

                                    if single_result['success']:
                                        invalidate_all_image_caches()
                                        st.success(f"✅ 씬 {target_scene_num} 이미지가 실사로 대체되었습니다!")
                                        if single_result['ai_backup_path']:
                                            st.info(f"AI 이미지 백업: {Path(single_result['ai_backup_path']).name}")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ 대체 실패: {single_result['error']}")

                    # ============================================================
                    # 🤖 AI 매핑 적용 탭 (v1.0)
                    # ============================================================
                    if real_tab3 is not None:
                        with real_tab3:
                            st.markdown("### 🤖 AI 매핑 결과 일괄 적용")
                            st.info("""
                            AI(Gemini, GPT 등)가 생성한 씬-이미지 매핑 결과를 붙여넣으면 자동으로 파싱하여 일괄 적용합니다.

                            **지원 형식**: JSON, CSV, 텍스트 (자동 감지)
                            """)

                            # 이미지 폴더 설정
                            col_folder1, col_folder2 = st.columns([3, 1])
                            with col_folder1:
                                ai_image_folder = st.text_input(
                                    "📁 이미지 폴더 경로",
                                    value=st.session_state.get('ai_mapping_image_folder', ''),
                                    placeholder="C:/Users/이름/images/프로젝트명",
                                    help="AI가 매핑한 이미지 파일들이 저장된 폴더 경로",
                                    key="ai_mapping_folder_input"
                                )
                            with col_folder2:
                                st.markdown("<br>", unsafe_allow_html=True)
                                if st.button("📂 폴더 선택", key="select_ai_folder_btn"):
                                    # ⭐ 성능 최적화: tkinter 모듈 사전 캐싱 + 즉시 정리
                                    try:
                                        import tkinter as tk
                                        from tkinter import filedialog
                                        root = tk.Tk()
                                        root.withdraw()
                                        root.wm_attributes('-topmost', 1)
                                        root.focus_force()  # 포커스 강제 설정
                                        folder_selected = filedialog.askdirectory(parent=root)
                                        root.destroy()  # ⭐ 즉시 정리 (메모리 누수 방지)
                                        if folder_selected:
                                            st.session_state['ai_mapping_image_folder'] = folder_selected
                                            st.rerun()
                                    except Exception:
                                        st.warning("폴더 선택 다이얼로그를 열 수 없습니다. 경로를 직접 입력하세요.")

                            # 폴더 상태 표시
                            if ai_image_folder:
                                st.session_state['ai_mapping_image_folder'] = ai_image_folder
                                folder_path = Path(ai_image_folder)
                                if folder_path.exists():
                                    # ⭐ 성능 최적화: 폴더 파일 목록 캐싱
                                    ai_folder_cache_key = f"ai_folder_files_{ai_image_folder}_{st.session_state.get('image_cache_version', 0)}"
                                    if ai_folder_cache_key not in st.session_state:
                                        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
                                        ai_image_files = [f for f in folder_path.iterdir()
                                                         if f.is_file() and f.suffix.lower() in image_exts]
                                        st.session_state[ai_folder_cache_key] = ai_image_files
                                    else:
                                        ai_image_files = st.session_state[ai_folder_cache_key]
                                    st.success(f"✅ 폴더 확인됨: **{len(ai_image_files)}개** 이미지 파일")

                                    with st.expander(f"📋 이미지 파일 목록 ({len(ai_image_files)}개)", expanded=False):
                                        for f in sorted(ai_image_files)[:30]:
                                            st.caption(f"• {f.name}")
                                        if len(ai_image_files) > 30:
                                            st.caption(f"... 외 {len(ai_image_files) - 30}개")

                                        # AI 프롬프트용 목록 복사 버튼
                                        if st.button("📋 AI 프롬프트용 목록 복사", key="copy_file_list"):
                                            file_list = get_image_folder_listing(ai_image_folder)
                                            st.code(file_list, language=None)
                                            st.info("위 텍스트를 복사하여 AI에게 전달하세요.")
                                else:
                                    st.error("❌ 폴더가 존재하지 않습니다.")

                            st.divider()

                            # ============================================================
                            # 🖼️ 실사 이미지 레이아웃 설정 (v1.1)
                            # ============================================================
                            if IMAGE_COMPOSER_AVAILABLE:
                                st.markdown("#### 🖼️ 실사 이미지 레이아웃 설정")
                                st.caption("실사 이미지가 정중앙에 배치되며, 배경 이미지와 합성됩니다.")

                                # 크기 설정
                                col_size1, col_size2 = st.columns([1, 1])

                                with col_size1:
                                    size_preset = st.selectbox(
                                        "📐 실사 이미지 크기",
                                        options=list(IMAGE_SIZE_PRESETS.keys()),
                                        format_func=lambda x: IMAGE_SIZE_PRESETS[x]['name'],
                                        index=1,  # 기본값: medium
                                        help="실사 이미지가 배치될 크기를 선택합니다.",
                                        key="compose_size_preset"
                                    )

                                    # 사용자 지정 크기
                                    if size_preset == 'custom':
                                        col_w, col_h = st.columns(2)
                                        with col_w:
                                            custom_width = st.number_input(
                                                "너비 (px)",
                                                min_value=100,
                                                max_value=1280,
                                                value=640,
                                                step=10,
                                                key="compose_custom_width"
                                            )
                                        with col_h:
                                            custom_height = st.number_input(
                                                "높이 (px)",
                                                min_value=100,
                                                max_value=720,
                                                value=360,
                                                step=10,
                                                key="compose_custom_height"
                                            )
                                    else:
                                        custom_width = None
                                        custom_height = None

                                with col_size2:
                                    preset_data = IMAGE_SIZE_PRESETS[size_preset]
                                    if size_preset != 'custom':
                                        st.info(f"""
                                        **선택된 크기**
                                        - 최대 너비: {preset_data['max_width']}px
                                        - 최대 높이: {preset_data['max_height']}px
                                        - 비율: {int(preset_data['scale'] * 100)}%
                                        """)
                                    else:
                                        st.info(f"""
                                        **사용자 지정 크기**
                                        - 너비: {custom_width}px
                                        - 높이: {custom_height}px
                                        """)

                                # 배경 설정
                                st.markdown("##### 🎨 배경 설정")
                                col_bg1, col_bg2 = st.columns([2, 1])

                                with col_bg1:
                                    use_background = st.checkbox(
                                        "배경 이미지 사용",
                                        value=False,
                                        help="실사 이미지 뒤에 배경 이미지를 배치합니다.",
                                        key="compose_use_background"
                                    )

                                    if use_background:
                                        background_source = st.radio(
                                            "배경 소스",
                                            options=["파일 업로드", "단색 배경"],
                                            horizontal=True,
                                            key="compose_bg_source"
                                        )

                                        if background_source == "파일 업로드":
                                            bg_uploaded = st.file_uploader(
                                                "배경 이미지 업로드",
                                                type=['jpg', 'jpeg', 'png', 'webp'],
                                                help="모든 실사 이미지 씬에 일괄 적용됩니다.",
                                                key="compose_bg_uploader"
                                            )

                                            if bg_uploaded:
                                                # 임시 저장
                                                bg_temp_dir = Path("data/temp")
                                                bg_temp_dir.mkdir(parents=True, exist_ok=True)
                                                bg_temp_path = bg_temp_dir / "background_temp.jpg"
                                                with open(bg_temp_path, 'wb') as f:
                                                    f.write(bg_uploaded.read())
                                                st.session_state['compose_bg_image_path'] = str(bg_temp_path)
                                                st.image(bg_uploaded, caption="선택된 배경 이미지", width=200)

                                            background_image_path = st.session_state.get('compose_bg_image_path')
                                        else:
                                            background_image_path = None
                                    else:
                                        background_source = "단색 배경"
                                        background_image_path = None

                                    # 배경 색상 (단색 배경 또는 배경 이미지 없을 때)
                                    if not use_background or background_source == "단색 배경":
                                        bg_color_hex = st.color_picker(
                                            "배경 색상",
                                            value="#1e1e1e",
                                            help="실사 이미지 뒤에 표시될 배경 색상",
                                            key="compose_bg_color"
                                        )
                                        bg_color_rgb = hex_to_rgb(bg_color_hex)
                                    else:
                                        bg_color_rgb = (30, 30, 30)

                                with col_bg2:
                                    if use_background and background_source == "파일 업로드":
                                        bg_opacity = st.slider(
                                            "배경 투명도",
                                            min_value=0.0,
                                            max_value=1.0,
                                            value=0.3,
                                            step=0.05,
                                            help="0.0 = 완전 투명, 1.0 = 불투명",
                                            key="compose_bg_opacity"
                                        )
                                        opacity_percent = int(bg_opacity * 100)
                                        opacity_label = '매우 투명' if bg_opacity < 0.3 else '반투명' if bg_opacity < 0.7 else '불투명'
                                        st.caption(f"투명도: {opacity_percent}% ({opacity_label})")
                                    else:
                                        bg_opacity = 1.0

                                # 효과 설정
                                st.markdown("##### ✨ 효과 설정")
                                col_fx1, col_fx2, col_fx3 = st.columns(3)

                                with col_fx1:
                                    add_shadow = st.checkbox(
                                        "그림자 효과",
                                        value=True,
                                        help="실사 이미지에 그림자를 추가합니다.",
                                        key="compose_add_shadow"
                                    )

                                with col_fx2:
                                    add_border = st.checkbox(
                                        "테두리 추가",
                                        value=True,
                                        help="실사 이미지에 테두리를 추가합니다.",
                                        key="compose_add_border"
                                    )

                                with col_fx3:
                                    if add_border:
                                        border_width = st.number_input(
                                            "테두리 두께",
                                            min_value=1,
                                            max_value=10,
                                            value=3,
                                            key="compose_border_width"
                                        )
                                    else:
                                        border_width = 0

                                # 미리보기 버튼
                                if st.button("👁️ 미리보기 생성", key="compose_preview_btn"):
                                    mapping = st.session_state.get('ai_mapping_result', {})

                                    if mapping and ai_image_folder:
                                        first_scene = sorted(mapping.keys())[0]
                                        first_data = mapping[first_scene]
                                        first_image = first_data.get('image')

                                        if first_image:
                                            real_image_path = Path(ai_image_folder) / first_image

                                            if real_image_path.exists():
                                                try:
                                                    composer = ImageComposer()

                                                    preview = composer.compose_scene_image(
                                                        real_image_path=str(real_image_path),
                                                        background_image_path=background_image_path if use_background else None,
                                                        size_preset=size_preset,
                                                        custom_width=custom_width,
                                                        custom_height=custom_height,
                                                        bg_opacity=bg_opacity if use_background else 1.0,
                                                        bg_color=bg_color_rgb,
                                                        add_shadow=add_shadow,
                                                        add_border=add_border,
                                                        border_width=border_width if add_border else 0
                                                    )

                                                    st.image(preview, caption=f"미리보기 (씬 {first_scene}: {first_image})", use_container_width=True)
                                                    st.success("✅ 미리보기 생성 완료! 위 설정이 모든 실사 이미지 씬에 적용됩니다.")

                                                except Exception as e:
                                                    st.error(f"미리보기 생성 실패: {e}")
                                            else:
                                                st.warning(f"이미지 파일을 찾을 수 없습니다: {first_image}")
                                    else:
                                        st.warning("먼저 AI 매핑 결과를 분석하고 이미지 폴더를 지정하세요.")

                                st.divider()

                            # AI 매핑 결과 입력
                            st.markdown("#### 📝 AI 매핑 결과 붙여넣기")

                            with st.expander("📖 입력 형식 안내", expanded=False):
                                st.markdown("""
**형식 1: JSON (권장)**
```json
{
  "mapping": [
    {"scene": 1, "image": "imgi_101_images.jpg", "reason": "선택 이유"},
    {"scene": 2, "image": "imgi_167_hq720.jpg", "reason": "선택 이유"},
    {"scene": 4, "image": null}
  ]
}
```

**형식 2: CSV**
```
scene,image,reason
1,imgi_101_images.jpg,선택 이유
2,imgi_167_hq720.jpg,선택 이유
4,,
```

**형식 3: 텍스트 (AI 원본 출력)**
```
Scene 1 (00:00:00 --> 00:00:05)
• 이미지: imgi_101_images.jpg
• 이유: 선택 이유

Scene 2 (00:00:06 --> 00:00:12)
• 이미지: imgi_167_hq720.jpg

Scene 4: (비워둠)
```
                                """)

                            mapping_input = st.text_area(
                                "AI 매핑 결과",
                                height=250,
                                placeholder='''여기에 AI 매핑 결과를 붙여넣으세요...

예시:
Scene 1: imgi_101_images.jpg
Scene 2: imgi_167_hq720.jpg
Scene 3: imgi_192_image.jpg
Scene 4: (비워둠)
...''',
                                key="ai_mapping_input"
                            )

                            # 분석 및 적용 버튼
                            col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])

                            with col_btn1:
                                analyze_btn = st.button("🔍 분석", type="secondary", use_container_width=True, key="analyze_ai_mapping")
                            with col_btn2:
                                apply_mapping_btn = st.button("✅ 일괄 적용", type="primary", use_container_width=True, key="apply_ai_mapping")

                            # 분석 결과 저장
                            if 'ai_mapping_result' not in st.session_state:
                                st.session_state['ai_mapping_result'] = None
                                st.session_state['ai_mapping_warnings'] = []

                            # 분석 실행
                            if analyze_btn and mapping_input and ai_image_folder:
                                with st.spinner("매핑 결과 분석 중..."):
                                    try:
                                        parser = ImageMappingParser()

                                        # 형식 감지
                                        detected_format = parser.detect_format(mapping_input)
                                        st.info(f"📊 감지된 형식: **{detected_format.upper()}**")

                                        # 파싱 및 검증
                                        total_scenes_count = len(scenes)
                                        mapping_result, warnings = parse_ai_mapping(mapping_input, ai_image_folder, total_scenes_count)

                                        st.session_state['ai_mapping_result'] = mapping_result
                                        st.session_state['ai_mapping_warnings'] = warnings

                                        # 결과 표시
                                        st.success(f"✅ **{len(mapping_result)}개 씬**에 이미지 매핑됨")

                                        # 경고 표시
                                        if warnings:
                                            with st.expander(f"⚠️ 경고 ({len(warnings)}개)", expanded=True):
                                                for w in warnings:
                                                    st.warning(w)

                                        # 매핑 미리보기
                                        if mapping_result:
                                            with st.expander(f"📋 매핑 결과 미리보기 ({len(mapping_result)}개)", expanded=True):
                                                preview_data = []
                                                for scene_num in sorted(mapping_result.keys()):
                                                    data = mapping_result[scene_num]
                                                    reason_preview = data.get('reason', '')[:50]
                                                    if len(data.get('reason', '')) > 50:
                                                        reason_preview += '...'
                                                    preview_data.append({
                                                        '씬': scene_num,
                                                        '이미지': data['image'],
                                                        '이유': reason_preview
                                                    })

                                                st.dataframe(preview_data, use_container_width=True)

                                    except Exception as e:
                                        st.error(f"❌ 파싱 오류: {str(e)}")
                                        import traceback
                                        with st.expander("오류 상세"):
                                            st.code(traceback.format_exc())

                            elif analyze_btn:
                                if not mapping_input:
                                    st.warning("AI 매핑 결과를 입력하세요.")
                                if not ai_image_folder:
                                    st.warning("이미지 폴더 경로를 입력하세요.")

                            # 일괄 적용 실행
                            if apply_mapping_btn:
                                mapping_result = st.session_state.get('ai_mapping_result')

                                if not mapping_result:
                                    st.error("❌ 먼저 '분석' 버튼을 눌러 매핑 결과를 확인하세요.")
                                elif not ai_image_folder:
                                    st.error("❌ 이미지 폴더 경로를 입력하세요.")
                                else:
                                    with st.spinner("🖼️ 실사 이미지 합성 및 적용 중..."):
                                        try:
                                            success_count = 0
                                            fail_count = 0
                                            error_messages = []

                                            progress_bar = st.progress(0)
                                            status_text = st.empty()

                                            total = len(mapping_result)
                                            existing_ai = get_existing_ai_images(scenes_images_dir, scenes)

                                            # ImageComposer 사용 여부 결정
                                            use_composer = IMAGE_COMPOSER_AVAILABLE and st.session_state.get('compose_size_preset', 'medium') != 'full'

                                            # 합성 설정 가져오기
                                            if use_composer:
                                                compose_size_preset = st.session_state.get('compose_size_preset', 'medium')
                                                compose_custom_width = st.session_state.get('compose_custom_width')
                                                compose_custom_height = st.session_state.get('compose_custom_height')
                                                compose_use_background = st.session_state.get('compose_use_background', False)
                                                compose_bg_source = st.session_state.get('compose_bg_source', '단색 배경')
                                                compose_bg_opacity = st.session_state.get('compose_bg_opacity', 0.3)
                                                compose_add_shadow = st.session_state.get('compose_add_shadow', True)
                                                compose_add_border = st.session_state.get('compose_add_border', True)
                                                compose_border_width = st.session_state.get('compose_border_width', 3)
                                                compose_bg_color_hex = st.session_state.get('compose_bg_color', '#1e1e1e')
                                                compose_bg_color_rgb = hex_to_rgb(compose_bg_color_hex)
                                                compose_bg_image_path = st.session_state.get('compose_bg_image_path') if compose_use_background and compose_bg_source == '파일 업로드' else None

                                                composer = ImageComposer()

                                            for idx, (scene_num, data) in enumerate(sorted(mapping_result.items()), 1):
                                                status_text.text(f"씬 {scene_num} 처리 중... ({idx}/{total})")

                                                image_path = data.get('path') or str(Path(ai_image_folder) / data['image'])

                                                if Path(image_path).exists():
                                                    # 기존 AI 이미지 경로 가져오기
                                                    current_ai_path = existing_ai.get(scene_num)

                                                    # 기존 이미지 백업
                                                    if current_ai_path and Path(current_ai_path).exists():
                                                        backup_path = Path(current_ai_path).with_suffix(f".ai_backup{Path(current_ai_path).suffix}")
                                                        if not backup_path.exists():
                                                            import shutil
                                                            shutil.copy2(current_ai_path, backup_path)

                                                    # 파일명 생성 (씬 번호 기반)
                                                    target_filename = f"{scene_num:03d}_scene_composed.jpg"
                                                    target_path = scenes_images_dir / target_filename

                                                    if use_composer:
                                                        # ImageComposer로 합성
                                                        try:
                                                            composed_image = composer.compose_scene_image(
                                                                real_image_path=image_path,
                                                                background_image_path=compose_bg_image_path,
                                                                size_preset=compose_size_preset,
                                                                custom_width=compose_custom_width,
                                                                custom_height=compose_custom_height,
                                                                bg_opacity=compose_bg_opacity if compose_use_background and compose_bg_source != '단색 배경' else 1.0,
                                                                bg_color=compose_bg_color_rgb,
                                                                add_shadow=compose_add_shadow,
                                                                add_border=compose_add_border,
                                                                border_width=compose_border_width if compose_add_border else 0
                                                            )
                                                            composed_image.save(target_path, quality=95)
                                                            success_count += 1
                                                        except Exception as compose_err:
                                                            error_messages.append(f"씬 {scene_num}: 합성 실패 - {str(compose_err)}")
                                                            fail_count += 1
                                                    else:
                                                        # 단순 복사 (full 크기 또는 ImageComposer 없음)
                                                        ext = Path(image_path).suffix.lower()
                                                        target_filename = f"{scene_num:03d}_scene{ext}"
                                                        target_path = scenes_images_dir / target_filename

                                                        with open(image_path, 'rb') as f:
                                                            file_content = f.read()
                                                        with open(target_path, 'wb') as f:
                                                            f.write(file_content)
                                                        success_count += 1
                                                else:
                                                    error_messages.append(f"씬 {scene_num}: 파일 없음 - {data['image']}")
                                                    fail_count += 1

                                                progress_bar.progress(idx / total)

                                            status_text.empty()

                                            # 캐시 무효화
                                            invalidate_all_image_caches()

                                            # 결과 표시
                                            col_result1, col_result2 = st.columns(2)
                                            with col_result1:
                                                st.metric("✅ 합성 성공", f"{success_count}개")
                                            with col_result2:
                                                if fail_count > 0:
                                                    st.metric("❌ 합성 실패", f"{fail_count}개", delta_color="inverse")
                                                else:
                                                    st.metric("❌ 합성 실패", "0개")

                                            # 오류 상세 표시
                                            if error_messages:
                                                with st.expander(f"⚠️ 오류 상세 ({len(error_messages)}개)"):
                                                    for err in error_messages:
                                                        st.warning(err)

                                            if success_count > 0:
                                                st.success(f"✅ {success_count}개 씬에 실사 이미지가 합성/적용되었습니다!")
                                                st.info("💡 위의 스토리보드에서 결과를 확인하세요.")

                                                # 분석 결과 초기화
                                                st.session_state['ai_mapping_result'] = None
                                                st.session_state['ai_mapping_warnings'] = []

                                                st.rerun()

                                        except Exception as e:
                                            st.error(f"❌ 적용 중 오류 발생: {str(e)}")
                                            import traceback
                                            with st.expander("오류 상세"):
                                                st.code(traceback.format_exc())

                            # 이전 분석 결과 표시 (있는 경우)
                            if st.session_state.get('ai_mapping_result') and not analyze_btn:
                                mapping_result = st.session_state['ai_mapping_result']
                                warnings = st.session_state.get('ai_mapping_warnings', [])

                                st.divider()
                                st.markdown("#### 📊 이전 분석 결과")
                                st.info(f"**{len(mapping_result)}개 씬**에 이미지 매핑됨")

                                if warnings:
                                    st.warning(f"⚠️ {len(warnings)}개 경고")

                else:
                    st.warning("⚠️ 실사 이미지 관리 모듈을 불러올 수 없습니다.")

            # ============================================================
            # 🍌 나노바나나 이미지 대체 섹션 (v1.2 - 필터 동기화 수정)
            # ============================================================
            if NANO_BANANA_AVAILABLE:
                with st.expander("🍌 나노바나나로 이미지 대체 (Gemini)", expanded=False):
                    st.caption("필터로 선택된 씬들의 이미지를 Gemini Nano Banana 모델로 재생성합니다.")

                    # ═══════════════════════════════════════════════════════════════
                    # v1.2: 필터 상태 명확히 읽기 (체크박스 직접 상태 + 세션 상태)
                    # ═══════════════════════════════════════════════════════════════

                    # 선택된 씬 ID 가져오기
                    storyboard_selected = st.session_state.get("storyboard_selected_scene_ids", set())
                    if not isinstance(storyboard_selected, set):
                        storyboard_selected = set(storyboard_selected) if storyboard_selected else set()

                    # 선택된 씬만 표시 체크박스 상태 (두 가지 키 모두 확인)
                    show_selected_only = (
                        st.session_state.get('show_selected_scenes_only_cb', False) or  # 체크박스 직접 상태
                        st.session_state.get('show_selected_scenes_only', False)  # 수동 동기화된 상태
                    )

                    # 디버그 로그
                    print(f"[나노바나나] 선택된 씬 ID: {storyboard_selected}")
                    print(f"[나노바나나] 선택된 씬만 표시 체크: {show_selected_only}")

                    # 현재 필터링된 씬 가져오기
                    nano_filtered_scenes = []

                    # 복합 필터 모드 확인
                    if st.session_state.get('use_complex_filter', False):
                        complex_filters = st.session_state.get('complex_filters', {})
                        combine_mode = st.session_state.get('filter_combine_mode', 'union')
                        if complex_filters and any(complex_filters.get(f, False) for f in complex_filters):
                            display_ids, _ = apply_complex_filters(scenes, complex_filters, combine_mode, "first")
                            nano_filtered_scenes = [s for s in scenes if s.get('scene_id', 0) in display_ids]

                    # 레거시 필터 모드
                    if not nano_filtered_scenes:
                        filter_mode = st.session_state.get('storyboard_scene_filter', 'all')
                        if filter_mode == 'korean_only' and korean_text_ids:
                            nano_filtered_scenes = [s for s in scenes if s.get('scene_id', 0) in korean_text_ids]
                        elif filter_mode == 'bundle_rep' and bundle_rep_ids:
                            nano_filtered_scenes = [s for s in scenes if s.get('scene_id', 0) in bundle_rep_ids]
                        elif filter_mode != 'all':
                            # 기타 필터 적용된 경우
                            nano_filtered_scenes = filtered_scenes if 'filtered_scenes' in dir() else scenes
                        else:
                            nano_filtered_scenes = scenes

                    # ═══════════════════════════════════════════════════════════════
                    # v1.2: 선택된 씬만 표시 필터 적용 (핵심 수정!)
                    # ═══════════════════════════════════════════════════════════════
                    if show_selected_only and storyboard_selected:
                        # scene_id 또는 scene_num으로 매칭
                        nano_filtered_scenes = [
                            s for s in nano_filtered_scenes
                            if s.get('scene_id', s.get('scene_num', 0)) in storyboard_selected
                        ]
                        print(f"[나노바나나] ✅ 선택 필터 적용됨: {len(nano_filtered_scenes)}개 씬")
                    else:
                        print(f"[나노바나나] 선택 필터 미적용 (show_selected={show_selected_only}, selected_count={len(storyboard_selected)})")

                    # 나노바나나 대체 UI 렌더링
                    render_nano_banana_replacer(
                        filtered_scenes=nano_filtered_scenes,
                        project_path=str(project_path),
                        all_scenes=scenes,
                        on_complete=lambda results: st.session_state.update({'storyboard_refresh': True})
                    )

            # ============================================================
            # 🎨 나노바나나 배경+캐릭터 합성 섹션 (v1.0)
            # ============================================================
            if NANO_COMPOSITE_AVAILABLE:
                with st.expander("🎨 나노바나나 배경+캐릭터 합성 (Gemini)", expanded=False):
                    st.caption("캐릭터가 있는 씬의 배경과 캐릭터를 분리 생성 후 합성합니다.")

                    # 합성 UI 렌더링
                    render_nano_banana_composite(
                        scenes=scenes,
                        project_path=str(project_path),
                        on_complete=lambda results: st.session_state.update({'storyboard_refresh': True})
                    )

            # ============================================================
            # 배치 비디오 업로드 섹션
            # ============================================================
            if BATCH_VIDEO_AVAILABLE:
                with st.expander("🎬 배치 비디오 업로드", expanded=False):
                    st.caption("비디오 파일을 일괄 업로드하여 씬의 배경을 비디오로 대체합니다.")
                    st.markdown("""
                    **지원 파일명 형식:**
                    - `1.mp4`, `2.webm`, `100.mov` (순수 숫자)
                    - `001.mp4`, `005.webm` (앞에 0 패딩)
                    - `scene_1.mp4`, `scene_10.webm` (scene_ 접두사)
                    - `씬1.mp4`, `씬_5.webm` (한글 접두사)
                    """)

                    # 비디오 파일 업로드
                    uploaded_videos = st.file_uploader(
                        "비디오 파일 업로드",
                        type=["mp4", "webm", "mov", "avi", "mkv"],
                        accept_multiple_files=True,
                        key="batch_video_upload",
                        help="씬 번호가 포함된 비디오 파일들을 업로드하세요"
                    )

                    if uploaded_videos:
                        # 빠른 분석 실행 (v1.1 - 파일 데이터 읽지 않음)
                        existing_videos = get_existing_videos(scenes)
                        results = quick_analyze_batch_video_upload(uploaded_videos, len(scenes), existing_videos)
                        stats = get_batch_video_stats(results)

                        # 업로드 완료 메시지
                        st.success(f"📁 {len(uploaded_videos)}개 비디오 파일 업로드 완료")

                        # 통계 표시
                        stat_cols = st.columns(4)
                        with stat_cols[0]:
                            st.metric("전체", stats["total"])
                        with stat_cols[1]:
                            st.metric("매칭 성공", stats["success"], delta_color="normal")
                        with stat_cols[2]:
                            failed_count = stats["out_of_range"] + stats["invalid_name"] + stats["invalid_format"] + stats["duplicate"]
                            st.metric("실패", failed_count, delta_color="inverse" if failed_count > 0 else "off")
                        with stat_cols[3]:
                            replace_count = sum(1 for r in results if r.status == "success" and r.current_video_path)
                            st.metric("기존 대체", replace_count)

                        # 미리보기 테이블
                        if stats["success"] > 0:
                            st.markdown("##### ✅ 매칭된 비디오")
                            for item in stats["success_items"]:
                                icon = "🔄" if item.current_video_path else "➕"
                                st.text(f"{icon} 씬 {item.scene_number}: {item.filename} ({item.message})")

                        if stats["failed_items"]:
                            st.markdown("##### ❌ 실패 항목")
                            for item in stats["failed_items"]:
                                st.text(f"⚠️ {item.filename}: {item.message}")

                        # 적용 버튼
                        if stats["success"] > 0:
                            st.divider()
                            apply_cols = st.columns([2, 1])
                            with apply_cols[0]:
                                backup_existing = st.checkbox("기존 비디오 백업", value=True, key="batch_video_backup")
                            with apply_cols[1]:
                                apply_btn = st.button("🎬 비디오 적용", type="primary", use_container_width=True, key="apply_batch_videos")

                            if apply_btn:
                                # 비디오 저장 폴더
                                videos_folder = project_path / "videos" / "backgrounds"

                                # 진행률 표시
                                progress_bar = st.progress(0, text="비디오 저장 준비 중...")
                                status_text = st.empty()

                                # 씬 데이터 업데이트 콜백
                                def update_scene_video(scene_num: int, video_path: str):
                                    for s in scenes:
                                        if s.get("scene_id") == scene_num or s.get("scene_num") == scene_num:
                                            s["media_type"] = "video"
                                            s["background_video"] = video_path
                                            break

                                # 진행률 콜백
                                def progress_callback(current: int, total: int, filename: str):
                                    progress = current / total
                                    progress_bar.progress(progress, text=f"저장 중... ({current}/{total})")
                                    status_text.text(f"📼 {filename}")

                                # 비디오 적용 (v1.1 - 직접 저장)
                                apply_result = apply_batch_videos_direct(
                                    uploaded_files=uploaded_videos,
                                    results=results,
                                    videos_folder=videos_folder,
                                    backup=backup_existing,
                                    update_scene_callback=update_scene_video,
                                    progress_callback=progress_callback
                                )

                                # 씬 데이터 저장
                                scenes_path = project_path / "analysis" / "scenes.json"
                                with open(scenes_path, 'w', encoding='utf-8') as f:
                                    json.dump(scenes, f, ensure_ascii=False, indent=2)

                                # 완료 표시
                                progress_bar.progress(1.0, text="완료!")
                                status_text.empty()

                                st.success(f"✅ {apply_result['applied']}개 비디오 적용 완료!")
                                if apply_result["backed_up"] > 0:
                                    st.info(f"💾 {apply_result['backed_up']}개 기존 비디오 백업됨")
                                if apply_result["failed"] > 0:
                                    st.warning(f"⚠️ {apply_result['failed']}개 저장 실패")
                                st.rerun()

            # ============================================================
            # 미디어 일괄 내보내기 섹션
            # ============================================================
            with st.expander("📤 미디어 일괄 내보내기", expanded=False):
                st.caption("씬별 이미지/비디오를 씬 번호 기반 파일명으로 일괄 내보냅니다.")

                # ⭐ 성능 최적화: 내보내기 목록 캐싱 (매 렌더링 시 전체 씬 스캔 방지)
                export_cache_key = f"export_media_list_{str(project_path)}_{st.session_state.get('image_cache_version', 0)}"
                if export_cache_key not in st.session_state:
                    export_media_list = []
                    for s in scenes:
                        scene_id = s.get("scene_id") or s.get("scene_num")
                        media_type = s.get("media_type", "image")

                        if media_type == "video":
                            video_path = s.get("background_video", "")
                            if video_path and Path(video_path).exists():
                                export_media_list.append({
                                    "scene_id": scene_id,
                                    "media_type": "video",
                                    "path": video_path,
                                    "ext": Path(video_path).suffix.lower()
                                })
                        else:
                            # 이미지 매칭 로직 (간소화)
                            img_path = None
                            for img_name, path in image_map.items():
                                if f"_{scene_id:03d}" in img_name or f"_seg_{scene_id:03d}" in img_name:
                                    img_path = str(path)
                                    break
                            if img_path and Path(img_path).exists():
                                export_media_list.append({
                                    "scene_id": scene_id,
                                    "media_type": "image",
                                    "path": img_path,
                                    "ext": Path(img_path).suffix.lower()
                                })
                    st.session_state[export_cache_key] = export_media_list
                else:
                    export_media_list = st.session_state[export_cache_key]

                # 통계 표시
                image_count = sum(1 for m in export_media_list if m["media_type"] == "image")
                video_count = sum(1 for m in export_media_list if m["media_type"] == "video")

                exp_stat_cols = st.columns(3)
                with exp_stat_cols[0]:
                    st.metric("전체 씬", len(scenes))
                with exp_stat_cols[1]:
                    st.metric("이미지", image_count)
                with exp_stat_cols[2]:
                    st.metric("비디오", video_count)

                if export_media_list:
                    st.divider()

                    # 파일명 형식 선택
                    filename_format = st.selectbox(
                        "파일명 형식",
                        ["scene_{num:03d}", "{num}", "{num:03d}"],
                        format_func=lambda x: f"{x.format(num=1)} (예: {x.format(num=1)}.mp4)",
                        key="media_export_filename_format"
                    )

                    # ZIP 생성 및 다운로드
                    if st.button("📦 ZIP 다운로드 준비", key="prepare_media_zip", use_container_width=True):
                        import zipfile
                        from io import BytesIO

                        zip_buffer = BytesIO()
                        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                            for item in export_media_list:
                                src_path = Path(item["path"])
                                new_name = f"{filename_format.format(num=item['scene_id'])}{item['ext']}"
                                zf.write(src_path, new_name)

                        zip_buffer.seek(0)
                        st.session_state["media_export_zip"] = zip_buffer.getvalue()
                        st.session_state["media_export_count"] = len(export_media_list)
                        st.rerun()

                    # 다운로드 버튼 표시 (v1.1: 동적 키 사용)
                    if "media_export_zip" in st.session_state:
                        export_count = st.session_state.get('media_export_count', 0)
                        st.download_button(
                            label=f"⬇️ 다운로드 ({export_count}개 파일)",
                            data=st.session_state["media_export_zip"],
                            file_name=f"scene_media_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                            mime="application/zip",
                            key=f"download_media_zip_{export_count}"
                        )
                else:
                    st.info("내보낼 미디어가 없습니다. 먼저 이미지/비디오를 생성하세요.")

            # ============================================================
            # 🎯 통합 씬 선택 및 다운로드 섹션 (v2.0 - 필터 통합)
            # ============================================================
            korean_text_applied = st.session_state.get('korean_text_scenes_applied', False)

            # ⭐ v3.25: AI 추천 적용 시 session_state 우선 사용 (동기화 문제 해결)
            # 기존 v3.24: 항상 씬 데이터에서 계산 → AI 추천 6개가 무시되고 22개로 표시
            # 수정: AI 추천 적용 시 session_state 사용, 미적용 시 씬 데이터에서 계산
            if korean_text_applied:
                # AI 추천이 적용된 경우: session_state에서 로드 (우선순위 높음)
                applied_ids = st.session_state.get('korean_text_scene_ids', [])
                korean_text_ids = set(applied_ids) if applied_ids else set()
                print(f"[스토리보드] AI 추천 적용됨 - session_state에서 로드: {len(korean_text_ids)}개")
            elif STORYBOARD_FILTER_AVAILABLE:
                # AI 추천 미적용: 씬 데이터에서 계산
                korean_text_ids = get_korean_text_scene_ids(scenes)
                print(f"[스토리보드] AI 추천 미적용 - 씬 데이터에서 계산: {len(korean_text_ids)}개")
            else:
                # 폴백: 세션 스테이트 사용
                korean_text_ids = set(st.session_state.get('korean_text_scene_ids', []))

            # ⭐ v3.19: 진단 로그 추가
            if korean_text_ids:
                print(f"[스토리보드] 한글 텍스트 씬: {len(korean_text_ids)}개 - {sorted(korean_text_ids)[:10]}{'...' if len(korean_text_ids) > 10 else ''}")

            # ⭐ v3.17: 묶음 대표 씬 ID 계산 (expander 밖에서 계산해야 씬 카드에서도 사용 가능)
            bundle_rep_ids = set()
            has_bundles = False
            if STORYBOARD_FILTER_AVAILABLE:
                bundle_size = scenes[0].get("bundle_size", 1) if scenes else 1
                has_bundles = bundle_size > 1
                if has_bundles:
                    bundle_rep_ids = get_bundle_representative_ids(scenes, mode="first")

            # ⭐ v2.2: 합성 완료 씬 ID 계산 (씬 카드에서 🎨 배지 표시용)
            composite_scene_ids = set()
            for s in scenes:
                if s.get("composite_image_path") or s.get("nano_composite_image") or s.get("composite_path"):
                    sid = s.get('scene_id', 0)
                    if sid:
                        composite_scene_ids.add(sid)

            # ⭐ v3.20: expander 상태 유지 (체크박스 클릭 시 닫히지 않도록)
            if "scene_selector_expander_open" not in st.session_state:
                st.session_state.scene_selector_expander_open = False

            with st.expander("🎯 씬 선택 및 다운로드", expanded=st.session_state.scene_selector_expander_open):
                # ⭐ v3.19: 씬 태그 상태 요약 표시 (expander 내부로 이동)
                tag_status_parts = []
                if bundle_rep_ids:
                    tag_status_parts.append(f"📦 묶음대표: {len(bundle_rep_ids)}개")
                if korean_text_ids:
                    tag_status_parts.append(f"🔤 한글텍스트: {len(korean_text_ids)}개")
                if composite_scene_ids:
                    tag_status_parts.append(f"🎨 합성완료: {len(composite_scene_ids)}개")
                if tag_status_parts:
                    st.info(" | ".join(tag_status_parts))

                # ─────────────────────────────────────────────────────────
                # 📌 씬 필터 섹션 (v3.18 - 복합 필터 지원)
                # ─────────────────────────────────────────────────────────
                st.markdown("#### 🎯 씬 필터 (복합 선택 가능)")

                # 필터 상태 초기화
                if "complex_filters" not in st.session_state:
                    st.session_state.complex_filters = {
                        "bundle_representative": False,
                        "korean_text": False,
                        "no_image": False,
                        "no_video": False,
                        "not_generated": False,
                        "has_characters": False,  # v2.1: 캐릭터 필터 추가
                        "has_composite": False,  # v2.2: 합성 완료 필터
                        "no_composite": False  # v2.2: 합성 미완료 필터
                    }
                if "filter_combine_mode" not in st.session_state:
                    st.session_state.filter_combine_mode = "union"

                # 필터 요약 정보 계산
                if STORYBOARD_FILTER_AVAILABLE:
                    filter_summary = get_extended_filter_summary(scenes, bundle_mode="first")
                else:
                    # 폴백: 기본 계산
                    all_scene_ids_list = [s.get('scene_id', i + 1) for i, s in enumerate(scenes)]
                    no_image_ids_list = [s.get('scene_id', i + 1) for i, s in enumerate(scenes)
                                   if not s.get("image_path") and not s.get("composite_path")]
                    no_video_ids_list = [s.get('scene_id', i + 1) for i, s in enumerate(scenes)
                                   if not s.get("video_path")]
                    not_generated_ids_list = [s.get('scene_id', i + 1) for i, s in enumerate(scenes)
                                        if not s.get("image_path") and not s.get("composite_path") and not s.get("video_path")]
                    # v2.1: 캐릭터 있는 씬 계산
                    has_characters_ids_list = [s.get('scene_id', i + 1) for i, s in enumerate(scenes)
                                               if s.get("characters") and len(s.get("characters", [])) > 0]
                    # v2.2: 합성 이미지 씬 계산
                    has_composite_ids_list = [s.get('scene_id', i + 1) for i, s in enumerate(scenes)
                                              if s.get("composite_image_path") or s.get("nano_composite_image") or s.get("composite_path")]
                    no_composite_ids_list = [s.get('scene_id', i + 1) for i, s in enumerate(scenes)
                                             if not (s.get("composite_image_path") or s.get("nano_composite_image") or s.get("composite_path"))]
                    filter_summary = {
                        "total": len(scenes),
                        "bundle_representative": len(bundle_rep_ids) if has_bundles else 0,
                        "korean_text": len(korean_text_ids),
                        "no_image": len(no_image_ids_list),
                        "no_video": len(no_video_ids_list),
                        "not_generated": len(not_generated_ids_list),
                        "has_characters": len(has_characters_ids_list),  # v2.1: 캐릭터 필터
                        "has_composite": len(has_composite_ids_list),  # v2.2: 합성 완료 필터
                        "no_composite": len(no_composite_ids_list),  # v2.2: 합성 미완료 필터
                        "bundle_korean_overlap": 0,
                        "has_bundles": has_bundles
                    }

                # ═══════════════════════════════════════════════════════
                # ⚡ 빠른 프리셋 버튼 (v3.19: 자동 선택 기능 추가)
                # ═══════════════════════════════════════════════════════
                st.markdown("**⚡ 빠른 필터 프리셋**")

                # 🆕 자동 선택 헬퍼 함수
                def auto_select_filtered_scenes(scene_ids: set):
                    """필터된 씬을 SceneSelector에 자동 선택으로 설정"""
                    selector_key_prefix = "storyboard_download"
                    uuid_key = f"_selector_uuid_{selector_key_prefix}"

                    # UUID가 없으면 생성
                    if uuid_key not in st.session_state:
                        import uuid
                        st.session_state[uuid_key] = str(uuid.uuid4())[:8]

                    unique_id = st.session_state[uuid_key]
                    selected_key = f"{selector_key_prefix}_{unique_id}_selected"

                    # 선택된 씬 저장
                    st.session_state[selected_key] = scene_ids
                    st.session_state['auto_selected_by_filter'] = True
                    st.session_state['auto_selected_count'] = len(scene_ids)

                    # ⭐ v3.20: expander 상태 유지 (Problem 2 해결)
                    st.session_state.scene_selector_expander_open = True

                    print(f"[빠른필터] 자동 선택: {len(scene_ids)}개 씬")

                preset_cols = st.columns(6)

                with preset_cols[0]:
                    if st.button("📋 전체", key="preset_all", use_container_width=True, help="모든 필터 해제, 전체 선택"):
                        st.session_state.complex_filters = {k: False for k in st.session_state.complex_filters}
                        # v2.2: 새 필터 추가시 명시적 초기화
                        st.session_state.complex_filters["has_composite"] = False
                        st.session_state.complex_filters["no_composite"] = False
                        # 🆕 전체 씬 자동 선택
                        all_ids = set(s.get('scene_id', i + 1) for i, s in enumerate(scenes))
                        auto_select_filtered_scenes(all_ids)
                        st.rerun()

                with preset_cols[1]:
                    if st.button("📦+🔤 OR", key="preset_bundle_korean_or", use_container_width=True,
                                help="묶음대표 또는 한글텍스트 (합집합) - 자동 선택"):
                        st.session_state.complex_filters = {
                            "bundle_representative": True,
                            "korean_text": True,
                            "no_image": False,
                            "no_video": False,
                            "not_generated": False,
                            "has_characters": False,
                            "has_composite": False,
                            "no_composite": False
                        }
                        st.session_state.filter_combine_mode = "union"
                        # 🆕 합집합 자동 선택
                        or_ids = bundle_rep_ids.union(korean_text_ids)
                        auto_select_filtered_scenes(or_ids)
                        st.rerun()

                with preset_cols[2]:
                    if st.button("📦∩🔤 AND", key="preset_bundle_korean_and", use_container_width=True,
                                help="묶음대표이면서 한글텍스트 (교집합) - 자동 선택"):
                        st.session_state.complex_filters = {
                            "bundle_representative": True,
                            "korean_text": True,
                            "no_image": False,
                            "no_video": False,
                            "not_generated": False,
                            "has_characters": False,
                            "has_composite": False,
                            "no_composite": False
                        }
                        st.session_state.filter_combine_mode = "intersection"
                        # 🆕 교집합 자동 선택
                        and_ids = bundle_rep_ids.intersection(korean_text_ids)
                        auto_select_filtered_scenes(and_ids)
                        st.rerun()

                with preset_cols[3]:
                    if st.button("🔤 한글만", key="preset_korean", use_container_width=True,
                                help="한글 텍스트 씬만 - 자동 선택"):
                        st.session_state.complex_filters = {
                            "bundle_representative": False,
                            "korean_text": True,
                            "no_image": False,
                            "no_video": False,
                            "not_generated": False,
                            "has_characters": False,
                            "has_composite": False,
                            "no_composite": False
                        }
                        st.session_state.filter_combine_mode = "union"
                        # 🆕 한글 텍스트 씬 자동 선택
                        auto_select_filtered_scenes(korean_text_ids.copy())
                        st.rerun()

                with preset_cols[4]:
                    if st.button("📦 묶음만", key="preset_bundle", use_container_width=True,
                                help="묶음 대표 씬만 - 자동 선택"):
                        st.session_state.complex_filters = {
                            "bundle_representative": True,
                            "korean_text": False,
                            "no_image": False,
                            "no_video": False,
                            "not_generated": False,
                            "has_characters": False,
                            "has_composite": False,
                            "no_composite": False
                        }
                        st.session_state.filter_combine_mode = "union"
                        # 🆕 묶음 대표 씬 자동 선택
                        auto_select_filtered_scenes(bundle_rep_ids.copy())
                        st.rerun()

                with preset_cols[5]:
                    if st.button("⬜ 미생성", key="preset_not_gen", use_container_width=True,
                                help="이미지/비디오 미생성 씬 - 자동 선택"):
                        st.session_state.complex_filters = {
                            "bundle_representative": False,
                            "korean_text": False,
                            "no_image": False,
                            "no_video": False,
                            "not_generated": True,
                            "has_characters": False,
                            "has_composite": False,
                            "no_composite": False
                        }
                        st.session_state.filter_combine_mode = "union"
                        # 🆕 미생성 씬 자동 선택
                        if STORYBOARD_FILTER_AVAILABLE:
                            not_gen_ids = get_not_generated_scene_ids(scenes)
                        else:
                            # 폴백: 직접 계산
                            not_gen_ids = set(
                                s.get('scene_id', i + 1) for i, s in enumerate(scenes)
                                if not s.get("image_path") and not s.get("composite_path") and not s.get("video_path")
                            )
                        auto_select_filtered_scenes(not_gen_ids)
                        st.rerun()

                # 🆕 자동 선택 상태 표시
                if st.session_state.get('auto_selected_by_filter'):
                    auto_count = st.session_state.get('auto_selected_count', 0)
                    st.success(f"⚡ 필터 적용 완료: {auto_count}개 씬 자동 선택됨")
                    # 한 번 표시 후 초기화 (다음 렌더링에서 안 보이게)
                    st.session_state['auto_selected_by_filter'] = False

                st.markdown("---")

                # ═══════════════════════════════════════════════════════
                # 📌 필터 체크박스 (복수 선택)
                # ═══════════════════════════════════════════════════════
                st.markdown("**📌 필터 선택** (복수 선택 가능)")

                filter_cols = st.columns(8)  # v2.2: 8열로 확장 (합성 필터 추가)
                filters = st.session_state.complex_filters

                with filter_cols[0]:
                    bundle_disabled = not (has_bundles and bundle_rep_ids)
                    filters["bundle_representative"] = st.checkbox(
                        f"📦 묶음 대표 ({filter_summary['bundle_representative']}개)",
                        value=filters.get("bundle_representative", False),
                        key="filter_cb_bundle",
                        disabled=bundle_disabled,
                        help="묶음 없음" if bundle_disabled else "각 묶음의 대표 씬"
                    )

                with filter_cols[1]:
                    korean_disabled = not korean_text_ids
                    filters["korean_text"] = st.checkbox(
                        f"🔤 한글 텍스트 ({filter_summary['korean_text']}개)",
                        value=filters.get("korean_text", False),
                        key="filter_cb_korean",
                        disabled=korean_disabled,
                        help="한글 텍스트 씬 없음" if korean_disabled else "한글 텍스트가 필요한 씬"
                    )

                with filter_cols[2]:
                    filters["no_image"] = st.checkbox(
                        f"🖼️ 이미지 없음 ({filter_summary['no_image']}개)",
                        value=filters.get("no_image", False),
                        key="filter_cb_no_image",
                        help="이미지가 생성되지 않은 씬"
                    )

                with filter_cols[3]:
                    filters["no_video"] = st.checkbox(
                        f"🎬 비디오 없음 ({filter_summary['no_video']}개)",
                        value=filters.get("no_video", False),
                        key="filter_cb_no_video",
                        help="비디오가 생성되지 않은 씬"
                    )

                with filter_cols[4]:
                    filters["not_generated"] = st.checkbox(
                        f"⬜ 미생성 ({filter_summary['not_generated']}개)",
                        value=filters.get("not_generated", False),
                        key="filter_cb_not_gen",
                        help="이미지, 비디오 모두 없는 씬"
                    )

                # v2.1: 등장 캐릭터 필터 추가
                with filter_cols[5]:
                    has_characters_count = filter_summary.get('has_characters', 0)
                    char_disabled = has_characters_count == 0
                    filters["has_characters"] = st.checkbox(
                        f"👤 캐릭터 있음 ({has_characters_count}개)",
                        value=filters.get("has_characters", False),
                        key="filter_cb_has_char",
                        disabled=char_disabled,
                        help="캐릭터 있는 씬 없음" if char_disabled else "등장 캐릭터가 있는 씬"
                    )

                # v2.2: 합성 이미지 필터 추가
                with filter_cols[6]:
                    has_composite_count = filter_summary.get('has_composite', 0)
                    composite_disabled = has_composite_count == 0
                    filters["has_composite"] = st.checkbox(
                        f"🎨 합성 완료 ({has_composite_count}개)",
                        value=filters.get("has_composite", False),
                        key="filter_cb_has_composite",
                        disabled=composite_disabled,
                        help="합성 완료된 씬 없음" if composite_disabled else "합성 이미지가 있는 씬"
                    )

                with filter_cols[7]:
                    no_composite_count = filter_summary.get('no_composite', 0)
                    no_composite_disabled = no_composite_count == 0
                    filters["no_composite"] = st.checkbox(
                        f"🖌️ 합성 미완료 ({no_composite_count}개)",
                        value=filters.get("no_composite", False),
                        key="filter_cb_no_composite",
                        disabled=no_composite_disabled,
                        help="합성 미완료된 씬 없음" if no_composite_disabled else "합성이 필요한 씬"
                    )

                st.session_state.complex_filters = filters

                # ═══════════════════════════════════════════════════════
                # 🔀 필터 조합 방식
                # ═══════════════════════════════════════════════════════
                active_count = sum(1 for v in filters.values() if v)

                if active_count >= 2:
                    st.markdown("**🔀 필터 조합 방식**")
                    combine_mode = st.radio(
                        "조합 방식",
                        options=["union", "intersection"],
                        format_func=lambda x: (
                            "합집합 (OR) - 선택한 필터 중 하나라도 해당되면 표시" if x == "union"
                            else "교집합 (AND) - 선택한 필터 모두 해당되어야 표시"
                        ),
                        horizontal=True,
                        key="filter_combine_radio",
                        index=0 if st.session_state.filter_combine_mode == "union" else 1,
                        label_visibility="collapsed"
                    )
                    st.session_state.filter_combine_mode = combine_mode
                else:
                    combine_mode = st.session_state.filter_combine_mode

                # ═══════════════════════════════════════════════════════
                # 📊 필터 결과 미리보기
                # ═══════════════════════════════════════════════════════
                if active_count > 0:
                    st.markdown("---")
                    st.markdown("**📊 필터 결과**")

                    # 복합 필터 적용
                    if STORYBOARD_FILTER_AVAILABLE:
                        final_ids, filter_results = apply_complex_filters(
                            scenes, filters, combine_mode, "first"
                        )
                    else:
                        # 폴백: 단순 필터링
                        all_scene_ids_set = set(s.get('scene_id', i + 1) for i, s in enumerate(scenes))
                        filter_results = {}
                        if filters.get("bundle_representative") and bundle_rep_ids:
                            filter_results["bundle_representative"] = bundle_rep_ids
                        if filters.get("korean_text") and korean_text_ids:
                            filter_results["korean_text"] = korean_text_ids

                        if not filter_results:
                            final_ids = all_scene_ids_set
                        elif combine_mode == "union":
                            final_ids = set()
                            for ids in filter_results.values():
                                final_ids = final_ids.union(ids)
                        else:
                            final_ids = all_scene_ids_set.copy()
                            for ids in filter_results.values():
                                final_ids = final_ids.intersection(ids)

                    # 결과 메트릭 표시
                    result_cols = st.columns(min(len(filter_results) + 1, 6))
                    col_idx = 0

                    filter_icons = {
                        "bundle_representative": "📦",
                        "korean_text": "🔤",
                        "no_image": "🖼️",
                        "no_video": "🎬",
                        "not_generated": "⬜",
                        "has_characters": "👤"  # v2.1: 캐릭터 필터
                    }
                    filter_names = {
                        "bundle_representative": "묶음대표",
                        "korean_text": "한글텍스트",
                        "no_image": "이미지없음",
                        "no_video": "비디오없음",
                        "not_generated": "미생성",
                        "has_characters": "캐릭터있음"  # v2.1: 캐릭터 필터
                    }

                    for filter_key, ids in filter_results.items():
                        if col_idx < len(result_cols) - 1:
                            with result_cols[col_idx]:
                                icon = filter_icons.get(filter_key, "")
                                name = filter_names.get(filter_key, filter_key)
                                st.metric(f"{icon} {name}", f"{len(ids)}개")
                            col_idx += 1

                    # 최종 결과
                    with result_cols[-1]:
                        mode_label = "합집합" if combine_mode == "union" else "교집합"
                        st.metric(f"🎯 최종 ({mode_label})", f"{len(final_ids)}개")

                    # 중복 정보 (묶음대표 + 한글텍스트)
                    if filters.get("bundle_representative") and filters.get("korean_text"):
                        overlap_count = filter_summary.get("bundle_korean_overlap", 0)
                        if overlap_count > 0:
                            st.caption(f"ℹ️ 묶음 대표 ∩ 한글 텍스트 중복: {overlap_count}개")

                    valid_scene_ids = sorted(list(final_ids))
                    filter_label = get_active_filter_labels(filters, combine_mode) if STORYBOARD_FILTER_AVAILABLE else "복합 필터"
                else:
                    # 필터 미선택: 전체 표시
                    all_scene_ids = [s.get('scene_id', i + 1) for i, s in enumerate(scenes)]
                    valid_scene_ids = all_scene_ids
                    filter_label = None
                    final_ids = set(all_scene_ids)

                # ─────────────────────────────────────────────────────────
                # ⭐ v3.25: 씬 타입 필터 (Flow 1/2/3)
                # ⭐ v3.26: 파이프라인 워크플로우 통합 (순차 소거)
                # ─────────────────────────────────────────────────────────
                if SCENE_TYPE_UI_AVAILABLE:
                    # 프로젝트 씬 타입 초기화
                    init_scene_type_for_project(project_path)

                    # 통합 워크플로우 Expander (파이프라인 + 씬 타입 필터)
                    if PIPELINE_UI_AVAILABLE:
                        st_filtered_ids, st_filter_label = render_combined_workflow_expander(scenes, project_path)

                        # 파이프라인 요약 정보 (사이드바 또는 메트릭으로 표시 가능)
                        pipeline_info = get_pipeline_summary(scenes, project_path)
                        if pipeline_info.get("available") and pipeline_info.get("ai_savings_percent", 0) > 0:
                            st.caption(f"💰 AI 비용 절감 예상: **{pipeline_info['ai_savings_percent']:.1f}%**")
                    else:
                        # 파이프라인 미사용 시 기존 씬 타입 필터만
                        st_filtered_ids, st_filter_label = render_scene_type_expander(scenes, project_path)

                    # 씬 타입/파이프라인 필터가 활성화되면 기존 필터와 교집합
                    if st_filter_label != "전체" and st_filtered_ids:
                        if valid_scene_ids:
                            new_ids = set(valid_scene_ids).intersection(st_filtered_ids)
                            if new_ids:
                                valid_scene_ids = sorted(list(new_ids))
                                if filter_label:
                                    filter_label = f"{filter_label} + {st_filter_label}"
                                else:
                                    filter_label = st_filter_label

                st.divider()

                # ─────────────────────────────────────────────────────────
                # 🎬 씬 선택 (필터 적용)
                # ─────────────────────────────────────────────────────────
                if valid_scene_ids:
                    # 필터된 씬 데이터
                    filtered_scene_data = [s for s in scenes if s.get('scene_id', 0) in valid_scene_ids or
                                          scenes.index(s) + 1 in valid_scene_ids]

                    # SceneSelector에 유효한 씬 ID 전달
                    selector = SceneSelector(
                        len(scenes),
                        key_prefix="storyboard_download",
                        valid_scene_ids=valid_scene_ids
                    )
                    selected_ids = selector.render(filtered_scene_data, filter_label=filter_label)

                    # ⭐ v3.20: 선택된 씬 ID를 session_state에 저장 (카드뷰 필터용)
                    st.session_state["storyboard_selected_scene_ids"] = selected_ids

                    # 선택된 ID 중 현재 필터에 해당하는 것만
                    selected_in_filter = selected_ids.intersection(set(valid_scene_ids))

                    if selected_in_filter:
                        st.divider()
                        downloader = StoryboardDownloader(str(project_path), key_prefix="sb_main_dl")
                        downloader.render_download_ui(scenes, selected_in_filter)
                    else:
                        st.info("📥 다운로드할 씬을 선택하세요.")
                else:
                    st.warning("⚠️ 현재 필터 조건에 맞는 씬이 없습니다.")

                # ─────────────────────────────────────────────────────────
                # 🔤 한글 텍스트 씬 정보 (접힌 상태)
                # ─────────────────────────────────────────────────────────
                if korean_text_applied and korean_text_ids:
                    with st.expander("📋 한글 텍스트 씬 상세 정보", expanded=False):
                        kt_col1, kt_col2, kt_col3 = st.columns(3)
                        with kt_col1:
                            st.metric("한글 텍스트 씬", f"{len(korean_text_ids)}개")
                        with kt_col2:
                            ratio = (len(korean_text_ids) / len(scenes) * 100) if scenes else 0
                            st.metric("비율", f"{ratio:.1f}%")
                        with kt_col3:
                            applied_at = st.session_state.get('korean_text_applied_at', '')[:16].replace('T', ' ')
                            st.metric("적용 시간", applied_at if applied_at else "-")

                        # 씬 번호 목록
                        sorted_ids = sorted(korean_text_ids)
                        st.caption("씬 번호: " + ", ".join(map(str, sorted_ids[:20])) + ("..." if len(sorted_ids) > 20 else ""))

                        # 적용 해제 버튼
                        if st.button("🗑️ 한글 텍스트 씬 적용 해제", key="clear_korean_text"):
                            st.session_state['korean_text_scenes_applied'] = False
                            st.session_state['korean_text_scene_ids'] = []
                            st.session_state['storyboard_scene_filter'] = 'all'
                            st.session_state['korean_text_filter_mode'] = 'all'
                            st.success("✅ 해제됨")
                            st.rerun()

            # ⭐ v3.18: 복합 필터 적용 (스토리보드 표시용)
            complex_filters = st.session_state.get('complex_filters', {})
            combine_mode = st.session_state.get('filter_combine_mode', 'union')
            active_filter_count = sum(1 for v in complex_filters.values() if v)

            if active_filter_count > 0 and STORYBOARD_FILTER_AVAILABLE:
                # 복합 필터 적용
                display_ids, filter_results = apply_complex_filters(
                    scenes, complex_filters, combine_mode, "first"
                )
                filtered_scenes = [s for s in scenes if s.get('scene_id', 0) in display_ids]

                # 필터 라벨 생성
                filter_label = get_active_filter_labels(complex_filters, combine_mode)
                mode_text = "합집합" if combine_mode == "union" else "교집합"

                # 활성화된 필터 아이콘 수집
                filter_icons = []
                if complex_filters.get("bundle_representative"):
                    filter_icons.append("📦")
                if complex_filters.get("korean_text"):
                    filter_icons.append("🔤")
                if complex_filters.get("no_image"):
                    filter_icons.append("🖼️")
                if complex_filters.get("no_video"):
                    filter_icons.append("🎬")
                if complex_filters.get("not_generated"):
                    filter_icons.append("⬜")
                if complex_filters.get("has_composite"):
                    filter_icons.append("🎨")
                if complex_filters.get("no_composite"):
                    filter_icons.append("🖌️")

                separator = " + " if combine_mode == "union" else " ∩ "
                icon_str = separator.join(filter_icons)

                st.info(f"🎯 **필터 적용 중**: {icon_str} ({mode_text}) → {len(filtered_scenes)}개 씬")
            else:
                # 레거시 호환: 기존 단일 필터 모드
                filter_mode = st.session_state.get('storyboard_scene_filter', st.session_state.get('korean_text_filter_mode', 'all'))
                if filter_mode == 'korean_only' and korean_text_ids:
                    filtered_scenes = [s for s in scenes if s.get('scene_id', 0) in korean_text_ids]
                    st.info(f"🔤 한글 텍스트 씬만 표시 중 ({len(filtered_scenes)}개)")
                elif filter_mode == 'exclude_korean' and korean_text_ids:
                    filtered_scenes = [s for s in scenes if s.get('scene_id', 0) not in korean_text_ids]
                    st.info(f"🖼️ 한글 텍스트 씬 제외 표시 중 ({len(filtered_scenes)}개)")
                elif filter_mode == 'no_image':
                    filtered_scenes = [s for s in scenes if not s.get("image_path") and not s.get("composite_path")]
                    st.info(f"⬜ 이미지 없는 씬만 표시 중 ({len(filtered_scenes)}개)")
                elif filter_mode == 'no_video':
                    filtered_scenes = [s for s in scenes if not s.get("video_path")]
                    st.info(f"🎬 비디오 없는 씬만 표시 중 ({len(filtered_scenes)}개)")
                elif filter_mode == 'not_generated':
                    filtered_scenes = [s for s in scenes if not s.get("image_path") and not s.get("composite_path") and not s.get("video_path")]
                    st.info(f"⚪ 미생성 씬만 표시 중 ({len(filtered_scenes)}개)")
                elif filter_mode == 'bundle_rep' and bundle_rep_ids:
                    filtered_scenes = [s for s in scenes if s.get('scene_id', 0) in bundle_rep_ids]
                    st.info(f"📦 묶음 대표 씬만 표시 중 ({len(filtered_scenes)}개)")
                else:
                    filtered_scenes = scenes

            # ============================================================
            # ⭐ v3.20: 선택된 씬만 표시 옵션 (Problem 1 해결)
            # ============================================================
            storyboard_selected_ids = st.session_state.get("storyboard_selected_scene_ids", set())

            filter_col1, filter_col2, filter_col3 = st.columns([2, 1, 2])

            with filter_col1:
                show_selected_only = st.checkbox(
                    f"✅ 선택된 씬만 표시 ({len(storyboard_selected_ids)}개)",
                    value=st.session_state.get("show_selected_scenes_only", False),
                    key="show_selected_scenes_only_cb",
                    disabled=len(storyboard_selected_ids) == 0
                )
                st.session_state["show_selected_scenes_only"] = show_selected_only

            with filter_col2:
                if storyboard_selected_ids:
                    st.caption(f"선택: {', '.join(map(str, sorted(storyboard_selected_ids)[:10]))}{'...' if len(storyboard_selected_ids) > 10 else ''}")

            # 선택된 씬 필터 적용
            if show_selected_only and storyboard_selected_ids:
                filtered_scenes = [s for s in filtered_scenes if s.get('scene_id', 0) in storyboard_selected_ids]
                st.success(f"✅ **선택된 {len(filtered_scenes)}개 씬만 표시 중**")

            # ============================================================
            # ⭐ v3.20: 일괄 비디오 변환 섹션 (Problem 3 해결)
            # ============================================================
            if storyboard_selected_ids and len(storyboard_selected_ids) > 0:
                with st.expander(f"🎬 선택된 {len(storyboard_selected_ids)}개 씬 일괄 비디오 변환", expanded=False):
                    st.markdown("#### 🚀 배치 비디오 변환")

                    # ⭐ v3.23: 선택된 씬 중 이미지가 있는 씬 확인 (get_scene_image_path 사용)
                    # 기존: s.get("image_path") 직접 확인 → 씬 데이터에 경로가 없으면 누락
                    # 수정: get_scene_image_path()로 파일시스템 스캔 (카드뷰와 동일)
                    scenes_with_image = []
                    for s in scenes:
                        sid = s.get('scene_id', 0)
                        if sid in storyboard_selected_ids:
                            # ⭐ get_scene_image_path: 실사이미지, 합성이미지, 패턴매칭 모두 확인
                            img_path = get_scene_image_path(s, str(project_path))
                            if img_path:
                                # 이미지 경로를 씬 데이터에 임시 저장 (비디오 생성용)
                                s["_batch_image_path"] = img_path
                                scenes_with_image.append(s)

                    batch_col1, batch_col2, batch_col3 = st.columns(3)

                    with batch_col1:
                        st.metric("선택된 씬", f"{len(storyboard_selected_ids)}개")

                    with batch_col2:
                        st.metric("이미지 있는 씬", f"{len(scenes_with_image)}개")

                    with batch_col3:
                        # 비용 예측
                        estimated_cost = len(scenes_with_image) * 0.10  # Wan I2V 기준
                        st.metric("예상 비용 (Wan)", f"${estimated_cost:.2f}")

                    if scenes_with_image:
                        # 플랫폼/모델/길이 선택
                        batch_settings_col1, batch_settings_col2, batch_settings_col3 = st.columns(3)

                        with batch_settings_col1:
                            batch_platform = st.selectbox(
                                "플랫폼",
                                options=get_available_video_platforms() if VIDEO_API_AVAILABLE else [],
                                key="batch_storyboard_platform"
                            )

                        with batch_settings_col2:
                            if batch_platform and VIDEO_API_AVAILABLE:
                                i2v_models = get_i2v_models_for_platform(batch_platform)
                                model_options = list(i2v_models.keys())
                                batch_model = st.selectbox(
                                    "모델",
                                    options=model_options,
                                    format_func=lambda x: i2v_models[x].display_name if x in i2v_models else x,
                                    key="batch_storyboard_model"
                                )
                            else:
                                batch_model = None

                        with batch_settings_col3:
                            # ⭐ v3.22: 비디오 길이 선택 (자동 모드 추가)
                            if batch_platform and batch_model and VIDEO_API_AVAILABLE:
                                try:
                                    model_config = ALL_MODELS[batch_platform][batch_model]
                                    available_durations = model_config.durations if model_config.durations else [5]
                                except:
                                    available_durations = [5]
                            else:
                                available_durations = [5]

                            # ⭐ v3.22: 자동/수동 모드 선택
                            duration_mode = st.radio(
                                "📐 영상 길이 모드",
                                options=["auto", "manual"],
                                format_func=lambda x: "🤖 SRT 기반 자동" if x == "auto" else "📏 수동 선택",
                                horizontal=True,
                                key="batch_duration_mode",
                                help="자동: SRT 길이에 따라 5초/10초 자동 결정 | 수동: 모든 씬에 동일한 길이 적용"
                            )

                            if duration_mode == "manual":
                                batch_duration = st.selectbox(
                                    "영상 길이",
                                    options=available_durations,
                                    format_func=lambda x: f"{x}초",
                                    key="batch_storyboard_duration",
                                    help="5초: 빠른 생성 | 10초: 더 자연스러운 움직임"
                                )
                            else:
                                batch_duration = None  # 자동 모드에서는 사용하지 않음

                        # ⭐ v3.22: 자동 모드일 때 씬별 duration 정보 표시
                        if duration_mode == "auto" and scenes_with_image:
                            duration_info = get_batch_duration_info(scenes_with_image)
                            info_col1, info_col2, info_col3 = st.columns(3)
                            with info_col1:
                                st.metric("5초 추천", f"{duration_info['short_count']}개", help="SRT 6초 이하")
                            with info_col2:
                                st.metric("10초 추천", f"{duration_info['long_count']}개", help="SRT 7초 이상")
                            with info_col3:
                                if duration_info['no_data_count'] > 0:
                                    st.metric("TTS 없음", f"{duration_info['no_data_count']}개", help="추정치 기반")
                                else:
                                    st.metric("TTS 데이터", "✅ 완전", help="모든 씬에 TTS 데이터 있음")

                        # 길이에 따른 비용 재계산 표시
                        if batch_platform and batch_model:
                            try:
                                if duration_mode == "auto":
                                    # ⭐ v3.22: 자동 모드 비용 계산 (씬별 다른 duration)
                                    duration_info = get_batch_duration_info(scenes_with_image)
                                    cost_5s = estimate_video_cost(batch_platform, batch_model, 5, "720p")
                                    cost_10s = estimate_video_cost(batch_platform, batch_model, 10, "720p") if 10 in available_durations else cost_5s

                                    cost_5s_unit = cost_5s.get("cost_usd", 0.10) if cost_5s else 0.10
                                    cost_10s_unit = cost_10s.get("cost_usd", 0.15) if cost_10s else 0.15

                                    total_5s_cost = duration_info['short_count'] * cost_5s_unit
                                    total_10s_cost = duration_info['long_count'] * cost_10s_unit
                                    total_no_data_cost = duration_info['no_data_count'] * cost_5s_unit  # 기본 5초

                                    total_estimated_cost = total_5s_cost + total_10s_cost + total_no_data_cost
                                    st.info(f"💰 예상 총 비용 (자동): **${total_estimated_cost:.2f}** (5초 {duration_info['short_count']}개 + 10초 {duration_info['long_count']}개)")
                                else:
                                    updated_estimate = estimate_video_cost(
                                        platform=batch_platform,
                                        model_key=batch_model,
                                        duration=batch_duration,
                                        resolution="720p"
                                    )
                                    unit_cost = updated_estimate.get("cost_usd", 0.10) if updated_estimate else 0.10
                                    total_estimated_cost = len(scenes_with_image) * unit_cost
                                    st.info(f"💰 예상 총 비용: **${total_estimated_cost:.2f}** (씬당 ${unit_cost:.2f} × {len(scenes_with_image)}개, {batch_duration}초)")
                            except:
                                pass

                        # 배치 변환 버튼
                        btn_label = f"🚀 {len(scenes_with_image)}개 씬 일괄 비디오 생성"
                        if duration_mode == "auto":
                            btn_label += " (🤖 자동)"

                        if st.button(
                            btn_label,
                            type="primary",
                            use_container_width=True,
                            key="batch_storyboard_video_btn",
                            disabled=not batch_platform or not batch_model or len(scenes_with_image) == 0
                        ):
                            # 배치 처리 실행
                            st.markdown("---")
                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            def batch_progress_callback(current, total, message):
                                progress_bar.progress((current + 1) / total if total > 0 else 0)
                                status_text.text(f"{message} ({current + 1}/{total})")

                            # ⭐ v3.22: 자동 모드 처리
                            is_auto_mode = (duration_mode == "auto")
                            actual_duration = 5 if is_auto_mode else batch_duration
                            spinner_msg = "배치 비디오 생성 중... (🤖 SRT 기반 자동)" if is_auto_mode else f"배치 비디오 생성 중... ({batch_duration}초)"

                            with st.spinner(spinner_msg):
                                batch_results = batch_generate_scene_videos(
                                    scenes=scenes_with_image,
                                    project_path=str(project_path),
                                    platform=batch_platform,
                                    model_key=batch_model,
                                    prompt_type="full",
                                    duration=actual_duration,
                                    resolution="720p",
                                    progress_callback=batch_progress_callback,
                                    auto_duration=is_auto_mode,  # ⭐ v3.22: 자동 모드 전달
                                )

                            progress_bar.progress(1.0)
                            status_text.text("✅ 완료!")

                            # 결과 표시
                            success_count = sum(1 for r in batch_results if r.get("success"))
                            fail_count = len(batch_results) - success_count
                            total_cost = sum(r.get("cost_usd", 0) for r in batch_results if r.get("success"))

                            if success_count > 0:
                                st.success(f"🎉 **{success_count}개 비디오 생성 완료!** | 실패: {fail_count}개 | 총 비용: ${total_cost:.2f}")

                                # ⭐ v3.22: 자동 모드일 때 씬별 duration 결과 표시
                                if is_auto_mode:
                                    successful_results = [r for r in batch_results if r.get("success")]
                                    dur_5s = sum(1 for r in successful_results if r.get("video_duration") == 5)
                                    dur_10s = sum(1 for r in successful_results if r.get("video_duration") == 10)
                                    st.caption(f"📊 생성된 비디오: 5초 {dur_5s}개, 10초 {dur_10s}개")
                            else:
                                st.error(f"❌ 모든 비디오 생성 실패 ({fail_count}개)")

                            # 실패 상세
                            failed_results = [r for r in batch_results if not r.get("success")]
                            if failed_results:
                                with st.expander("❌ 실패 상세"):
                                    for r in failed_results:
                                        st.markdown(f"- 씬 {r.get('scene_id')}: {r.get('error')}")

                            # ⭐ v3.22: 자동 모드 상세 (어떤 duration이 사용되었는지)
                            if is_auto_mode and success_count > 0:
                                with st.expander("📋 씬별 비디오 길이 상세"):
                                    for r in batch_results:
                                        if r.get("success"):
                                            dur = r.get("video_duration", "?")
                                            reason = r.get("auto_duration_reason", "")
                                            st.markdown(f"- 씬 {r.get('scene_id')}: **{dur}초** - {reason}")

                            st.rerun()
                    else:
                        st.warning("⚠️ 선택된 씬 중 이미지가 있는 씬이 없습니다. 먼저 이미지를 생성하세요.")

            st.divider()

            # 뷰 모드 선택
            view_mode = st.radio(
                "뷰 모드",
                ["카드 뷰", "테이블 뷰", "타임라인 뷰"],
                horizontal=True
            )

            # === 카드 뷰 ===
            if view_mode == "카드 뷰":
                st.subheader("🎬 스토리보드 (카드 뷰)")

                # 🎬 비디오 변환 모달 (NEW!)
                if "video_convert_scene_id" in st.session_state:
                    _render_video_conversion_modal(project_path)

                # ============================================================
                # 페이지네이션 (10개씩 표시 - 로딩 시간 80% 감소)
                # ============================================================
                SCENES_PER_PAGE = 10

                # 현재 페이지 상태 관리
                if "storyboard_page" not in st.session_state:
                    st.session_state["storyboard_page"] = 0

                current_page = st.session_state["storyboard_page"]

                # v3.30: 먼저 total_pages 계산하여 current_page 범위 검증
                total_pages = max(1, (len(filtered_scenes) + SCENES_PER_PAGE - 1) // SCENES_PER_PAGE)

                # ✅ 필터 변경으로 페이지 수가 줄어든 경우 current_page 조정
                if current_page >= total_pages:
                    current_page = max(0, total_pages - 1)
                    st.session_state["storyboard_page"] = current_page
                    print(f"[스토리보드] 페이지 조정됨: → {current_page + 1}/{total_pages} (필터로 씬 수 감소)")

                if current_page < 0:
                    current_page = 0
                    st.session_state["storyboard_page"] = current_page

                paginated_scenes, start_idx, end_idx, total_pages = get_paginated_scenes(
                    filtered_scenes, current_page, SCENES_PER_PAGE
                )

                # 페이지 네비게이션 UI
                page_nav_cols = st.columns([1, 1, 2, 1, 1])

                with page_nav_cols[0]:
                    if st.button("⏮️ 처음", key="page_first", disabled=(current_page == 0)):
                        st.session_state["storyboard_page"] = 0
                        st.rerun()

                with page_nav_cols[1]:
                    if st.button("◀️ 이전", key="page_prev", disabled=(current_page == 0)):
                        st.session_state["storyboard_page"] = max(0, current_page - 1)
                        st.rerun()

                with page_nav_cols[2]:
                    st.markdown(
                        f"<div style='text-align:center; padding:8px;'>"
                        f"<b>페이지 {current_page + 1} / {total_pages}</b><br>"
                        f"<small>씬 {start_idx + 1} ~ {end_idx} (총 {len(filtered_scenes)}개)</small>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

                with page_nav_cols[3]:
                    if st.button("▶️ 다음", key="page_next", disabled=(current_page >= total_pages - 1)):
                        st.session_state["storyboard_page"] = min(total_pages - 1, current_page + 1)
                        st.rerun()

                with page_nav_cols[4]:
                    if st.button("⏭️ 끝", key="page_last", disabled=(current_page >= total_pages - 1)):
                        st.session_state["storyboard_page"] = total_pages - 1
                        st.rerun()

                # 빠른 페이지 이동 & 캐시 관리
                quick_nav_cols = st.columns([2, 1, 1])
                with quick_nav_cols[0]:
                    page_options = [f"페이지 {p+1} (씬 {p*SCENES_PER_PAGE+1}~{min((p+1)*SCENES_PER_PAGE, len(filtered_scenes))})" for p in range(total_pages)]

                    # v3.30: selectbox 인덱스 안전 검증 (이중 보호)
                    safe_page_index = max(0, min(current_page, total_pages - 1)) if total_pages > 0 else 0

                    selected_page = st.selectbox(
                        "빠른 이동",
                        options=range(total_pages) if total_pages > 0 else [0],
                        format_func=lambda x: page_options[x] if x < len(page_options) else f"페이지 {x+1}",
                        index=safe_page_index,
                        key="quick_page_select",
                        label_visibility="collapsed"
                    )
                    if selected_page != current_page:
                        st.session_state["storyboard_page"] = selected_page
                        st.rerun()

                with quick_nav_cols[1]:
                    if st.button("🔄 이미지 캐시 새로고침", key="refresh_image_cache_quicknav", help="모든 이미지 캐시 삭제 (최신 이미지 반영)"):
                        cleared = invalidate_all_image_caches(full_reset=True)
                        st.toast(f"이미지 캐시 새로고침됨 ({cleared}개 항목)")
                        st.rerun()

                with quick_nav_cols[2]:
                    st.caption(f"📊 {len(image_files)}개 이미지")

                st.divider()

                # 페이지네이션된 씬 표시
                for page_idx, scene in enumerate(paginated_scenes):
                    i = start_idx + page_idx  # 전체 인덱스
                    scene_id = scene.get("scene_id", i + 1)
                    script_text = scene.get("script_text", "")
                    direction = scene.get("direction_guide", "")
                    characters = scene.get("characters", [])
                    # v3.19: 세분화된 프롬프트 지원 (필드명 직접 매핑)
                    # 배경 프롬프트: background_prompt_en 필드 (없으면 빈 문자열, 폴백 없음)
                    background_prompt_en = scene.get("background_prompt_en", "")
                    background_prompt_ko = scene.get("background_prompt_ko", "")
                    # 캐릭터 프롬프트: character_prompt_en 필드
                    character_prompt_en = scene.get("character_prompt_en", "")
                    character_prompt_ko = scene.get("character_prompt_ko", "")
                    # 전체 프롬프트: image_prompt_en 필드 (기존 통합 프롬프트)
                    # 없으면 배경+캐릭터 조합으로 생성
                    full_prompt_en = scene.get("image_prompt_en", "")
                    if not full_prompt_en and (background_prompt_en or character_prompt_en):
                        full_prompt_en = ", ".join(filter(None, [background_prompt_en, character_prompt_en]))
                    full_prompt_ko = scene.get("image_prompt_ko", "")
                    if not full_prompt_ko and (background_prompt_ko or character_prompt_ko):
                        full_prompt_ko = ", ".join(filter(None, [background_prompt_ko, character_prompt_ko]))
                    # 하위 호환성: 기존 변수명 유지
                    image_prompt = full_prompt_en
                    image_prompt_korean = full_prompt_ko or scene.get("image_prompt_korean_text", "")
                    duration = scene.get("duration_estimate", 10)
                    filename = scene.get("filename", "")

                    # 씬 컨테이너
                    with st.container():
                        cols = st.columns([1, 3, 2])

                        with cols[0]:
                            # ⭐ v3.17: 씬 태그 표시 (묶음 대표 + 한글 텍스트 + 합성 완료)
                            tags = []
                            if scene_id in bundle_rep_ids:
                                tags.append("📦")
                            if scene_id in korean_text_ids:
                                tags.append("🔤")
                            if scene_id in composite_scene_ids:
                                tags.append("🎨")
                            tag_str = " ".join(tags)
                            if tag_str:
                                st.markdown(f"### 씬 {scene_id} {tag_str}")
                            else:
                                st.markdown(f"### 씬 {scene_id}")
                            st.caption(f"~{duration}초")

                        with cols[1]:
                            # 스크립트
                            if show_script and script_text:
                                st.markdown("**📝 스크립트**")
                                st.write(script_text)

                            # 연출가이드
                            if show_direction and direction:
                                st.markdown("**🎬 연출가이드**")
                                st.info(direction)

                            # 캐릭터
                            if show_characters and characters:
                                char_names = safe_join_characters(characters)
                                if char_names:
                                    st.markdown(f"**👤 등장 캐릭터:** {char_names}")

                            # 📝 프롬프트 섹션 (v3.16 개선 - 이미지/한글/비디오 탭)
                            if show_prompt or show_video_prompt:
                                # 비디오 프롬프트 가져오기
                                video_prompt_char = get_video_prompt_for_scene(scene, "character") if show_video_prompt else ""
                                video_prompt_full = get_video_prompt_for_scene(scene, "full") if show_video_prompt else ""

                                # v3.18: 세분화된 프롬프트 표시 여부 확인
                                has_full_en = full_prompt_en and full_prompt_en.upper() != "N/A"
                                has_full_ko = full_prompt_ko and full_prompt_ko.upper() != "N/A"
                                has_bg_en = background_prompt_en and background_prompt_en.upper() != "N/A"
                                has_char_en = character_prompt_en and character_prompt_en.upper() != "N/A"
                                has_video = (video_prompt_char and video_prompt_char.upper() != "N/A") or \
                                           (video_prompt_full and video_prompt_full.upper() != "N/A")
                                # 하위 호환성
                                has_image = has_full_en
                                has_korean = has_full_ko or (image_prompt_korean and image_prompt_korean.upper() != "N/A")

                                if has_image or has_korean or has_bg_en or has_char_en or has_video:
                                    st.markdown("**📝 프롬프트**")
                                    with st.container(border=True):
                                        # v3.18: 5개 탭 (이미지전체, 한글전체, 배경, 캐릭터, 비디오)
                                        prompt_tabs = st.tabs(["🖼️ 이미지(전체)", "🇰🇷 한글(전체)", "🏞️ 배경", "👤 캐릭터", "🎬 비디오"])

                                        # 🖼️ 이미지(전체) 프롬프트 탭 - 배경 + 캐릭터 조합
                                        with prompt_tabs[0]:
                                            if has_full_en:
                                                st.code(full_prompt_en[:300] + "..." if len(full_prompt_en) > 300 else full_prompt_en, language=None)
                                                render_instant_copy_button(
                                                    text=full_prompt_en,
                                                    key=f"copy_full_en_{i}_{scene_id}",
                                                    label="📋 복사",
                                                    help_text="전체 영문 프롬프트 복사 (배경+캐릭터)"
                                                )
                                            else:
                                                st.caption("이미지 프롬프트 없음")

                                        # 🇰🇷 한글(전체) 이미지 프롬프트 탭
                                        with prompt_tabs[1]:
                                            display_korean = full_prompt_ko or image_prompt_korean
                                            if display_korean and display_korean.upper() != "N/A":
                                                st.code(display_korean[:300] + "..." if len(display_korean) > 300 else display_korean, language=None)
                                                render_instant_copy_button(
                                                    text=display_korean,
                                                    key=f"copy_full_ko_{i}_{scene_id}",
                                                    label="📋 복사",
                                                    help_text="전체 한글 프롬프트 복사"
                                                )
                                            else:
                                                st.caption("한글 프롬프트 없음 (씬 재분석 필요)")

                                        # 🏞️ 배경 프롬프트 탭
                                        with prompt_tabs[2]:
                                            if has_bg_en:
                                                st.code(background_prompt_en[:300] + "..." if len(background_prompt_en) > 300 else background_prompt_en, language=None)
                                                render_instant_copy_button(
                                                    text=background_prompt_en,
                                                    key=f"copy_bg_en_{i}_{scene_id}",
                                                    label="📋 복사",
                                                    help_text="배경 프롬프트 복사"
                                                )
                                            else:
                                                st.caption("배경 프롬프트 없음")

                                        # 👤 캐릭터 프롬프트 탭
                                        with prompt_tabs[3]:
                                            if has_char_en:
                                                st.code(character_prompt_en[:300] + "..." if len(character_prompt_en) > 300 else character_prompt_en, language=None)
                                                render_instant_copy_button(
                                                    text=character_prompt_en,
                                                    key=f"copy_char_en_{i}_{scene_id}",
                                                    label="📋 복사",
                                                    help_text="캐릭터 프롬프트 복사"
                                                )
                                            else:
                                                st.caption("캐릭터 프롬프트 없음")

                                        # 🎬 비디오 프롬프트 탭
                                        with prompt_tabs[4]:
                                            if has_video:
                                                vp_tab1, vp_tab2 = st.tabs(["👤 캐릭터", "🌍 전체"])

                                                with vp_tab1:
                                                    if video_prompt_char and video_prompt_char.upper() != "N/A":
                                                        st.code(video_prompt_char[:200] + "..." if len(video_prompt_char) > 200 else video_prompt_char, language=None)
                                                    else:
                                                        st.caption("캐릭터 비디오 프롬프트 없음")

                                                with vp_tab2:
                                                    if video_prompt_full and video_prompt_full.upper() != "N/A":
                                                        st.code(video_prompt_full[:200] + "..." if len(video_prompt_full) > 200 else video_prompt_full, language=None)
                                                    else:
                                                        st.caption("전체 비디오 프롬프트 없음")
                                            else:
                                                st.caption("비디오 프롬프트 없음")

                        with cols[2]:
                            # 미디어 타입 확인 (video 또는 image)
                            scene_media_type = scene.get("media_type", "image")
                            background_video = scene.get("background_video", "")

                            # 🎬 비디오 표시 (media_type이 video인 경우)
                            if scene_media_type == "video" and background_video:
                                video_path = Path(background_video)
                                if video_path.exists():
                                    st.video(str(video_path))
                                    st.caption(f"🎬 비디오: {video_path.name}")

                                    # 비디오 관리 버튼
                                    vid_btn_cols = st.columns(3)
                                    with vid_btn_cols[0]:
                                        if st.button("Copy", key=f"copy_video_{i}_{scene_id}", help="비디오 경로 복사"):
                                            abs_path = str(video_path.resolve())
                                            copy_path_to_clipboard(abs_path, f"copy_vid_{i}_{scene_id}")
                                            st.toast("경로 복사됨!")
                                            st.code(abs_path, language=None)
                                    with vid_btn_cols[1]:
                                        if st.button("Open", key=f"open_video_{i}_{scene_id}", help="비디오 폴더 열기"):
                                            open_file_location(str(video_path))
                                    with vid_btn_cols[2]:
                                        if st.button("이미지로 전환", key=f"switch_to_img_{i}_{scene_id}", help="이미지 모드로 전환"):
                                            scene["media_type"] = "image"
                                            scenes_path = project_path / "analysis" / "scenes.json"
                                            with open(scenes_path, 'w', encoding='utf-8') as f:
                                                json.dump(scenes, f, ensure_ascii=False, indent=2)
                                            st.toast(f"씬 {scene_id} 이미지 모드로 전환됨")
                                            st.rerun()
                                else:
                                    st.warning(f"비디오 파일 없음: {background_video}")

                            # 🖼️ 이미지 표시
                            elif show_images:
                                scene_image = None
                                is_composite_image = False  # v2.2: 합성 이미지 여부 플래그

                                # ⭐ v2.2: 합성 이미지 우선 매칭 (최고 우선순위)
                                composite_path = scene.get("composite_image_path") or scene.get("nano_composite_image") or scene.get("composite_path")
                                if composite_path:
                                    composite_path_obj = Path(composite_path)
                                    if composite_path_obj.exists():
                                        scene_image = composite_path_obj
                                        is_composite_image = True

                                # 파일명으로 매칭
                                if not scene_image and filename and filename.replace(".png", "") in image_map:
                                    scene_image = image_map[filename.replace(".png", "")]

                                # ⭐ v2.3: 실사 이미지 우선 매칭
                                # 씬 번호로 매칭 (다양한 파일명 패턴 지원)
                                if not scene_image:
                                    scene_num_str = f"{scene_id:03d}"
                                    # 실사 이미지 우선 검색
                                    real_scene_key = f"real_scene_{scene_num_str}"
                                    if real_scene_key in image_map:
                                        scene_image = image_map[real_scene_key]
                                    else:
                                        for img_name, img_path in image_map.items():
                                            # 패턴: real_scene_001, _001, _seg_001, 001_, 001_scene 등
                                            if (img_name.startswith(f"real_scene_{scene_num_str}") or
                                                f"_{scene_num_str}" in img_name or
                                                f"_seg_{scene_num_str}" in img_name or
                                                img_name.startswith(f"{scene_num_str}_") or
                                                img_name.startswith(f"{scene_num_str}.")):
                                                scene_image = img_path
                                                break

                                # 순서대로 매칭
                                if not scene_image and i < len(image_files):
                                    scene_image = image_files[i]

                                # Path 객체로 통일 (str/Path 모두 처리)
                                if scene_image:
                                    scene_image = Path(scene_image) if isinstance(scene_image, str) else scene_image

                                if scene_image and scene_image.exists():
                                    render_lightbox_image(str(scene_image), width=300, key=f"storyboard_img_{i}_{scene_id}")

                                    # v2.2: 합성 이미지인 경우 배지 표시
                                    if is_composite_image:
                                        st.caption("🎨 합성 이미지")

                                    # === 실사 이미지 대체 기능 ===
                                    img_btn_cols = st.columns(6)  # v1.1: 6열로 변경 (다운로드 버튼 추가)

                                    # 1. 🆕 v1.2: 한글 프롬프트 즉시 복사 버튼 (원클릭 복사)
                                    with img_btn_cols[0]:
                                        render_instant_copy_button(
                                            text=image_prompt_korean,
                                            key=f"copy_kr_{i}_{scene_id}",
                                            label="Copy",
                                            help_text="한글 이미지 프롬프트 복사"
                                        )

                                    # 2. 폴더 열기 버튼
                                    with img_btn_cols[1]:
                                        if st.button("Open", key=f"open_folder_{i}_{scene_id}", help="이미지 폴더 열기"):
                                            open_file_location(str(scene_image))

                                    # 3. 이미지 새로고침 버튼
                                    with img_btn_cols[2]:
                                        if st.button("Sync", key=f"refresh_img_{i}_{scene_id}", help="이미지 새로고침"):
                                            invalidate_image_cache(str(scene_image))
                                            st.toast(f"씬 {scene_id} 이미지 새로고침됨")
                                            st.rerun()

                                    # 4. 백업/복원 버튼
                                    with img_btn_cols[3]:
                                        scene_img_path = Path(scene_image) if isinstance(scene_image, str) else scene_image
                                        if has_backup(scene_img_path):
                                            if st.button("Undo", key=f"restore_img_{i}_{scene_id}", help="AI 이미지 복원"):
                                                if restore_ai_image(scene_img_path):
                                                    invalidate_image_cache(str(scene_image))
                                                    st.toast(f"씬 {scene_id} AI 이미지 복원됨")
                                                    st.rerun()
                                        else:
                                            if st.button("Save", key=f"backup_img_{i}_{scene_id}", help="AI 이미지 백업"):
                                                if backup_ai_image(scene_img_path):
                                                    st.toast(f"씬 {scene_id} AI 이미지 백업됨")
                                                    # 백업은 rerun 불필요 (UI 변경 없음)

                                    # 5. 프롬프트 정보 버튼
                                    with img_btn_cols[4]:
                                        if PROMPT_METADATA_AVAILABLE and has_prompt_metadata(str(scene_image)):
                                            if st.button("Prompt", key=f"prompt_info_{i}_{scene_id}", help="프롬프트 정보 보기"):
                                                st.session_state[f"show_prompt_{i}_{scene_id}"] = True

                                    # 6. 🆕 v1.1: 이미지 다운로드 버튼
                                    with img_btn_cols[5]:
                                        try:
                                            with open(scene_image, "rb") as img_file:
                                                img_bytes = img_file.read()
                                            # 파일명 생성: scene_001.png 형식
                                            dl_filename = f"scene_{str(scene_id).zfill(3)}{scene_image.suffix}"
                                            # MIME 타입 결정
                                            mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
                                            dl_mime = mime_map.get(scene_image.suffix.lower(), "image/png")
                                            st.download_button(
                                                "📥",
                                                data=img_bytes,
                                                file_name=dl_filename,
                                                mime=dl_mime,
                                                key=f"dl_img_{i}_{scene_id}",
                                                help="이미지 다운로드"
                                            )
                                        except Exception as e:
                                            st.button("📥", disabled=True, key=f"dl_img_{i}_{scene_id}", help=f"다운로드 실패: {e}")

                                    # 프롬프트 정보 표시 (expander)
                                    if PROMPT_METADATA_AVAILABLE and st.session_state.get(f"show_prompt_{i}_{scene_id}", False):
                                        render_prompt_info_expander(str(scene_image), key_prefix=f"prompt_{i}_{scene_id}")
                                        if st.button("Close", key=f"close_prompt_{i}_{scene_id}"):
                                            st.session_state[f"show_prompt_{i}_{scene_id}"] = False
                                            st.rerun()

                                    # 🎬 비디오 변환 버튼 (NEW!)
                                    if st.button(
                                        "🎬 비디오로 변환",
                                        key=f"storyboard_video_btn_{i}_{scene_id}",
                                        use_container_width=True
                                    ):
                                        st.session_state["video_convert_scene_id"] = scene_id
                                        st.session_state["video_convert_image_path"] = str(scene_image)
                                        st.session_state["video_convert_scene"] = scene
                                        st.rerun()
                                else:
                                    st.info("이미지 없음")

                        st.divider()

            # === 테이블 뷰 ===
            elif view_mode == "테이블 뷰":
                st.subheader("🎬 스토리보드 (테이블 뷰)")

                import pandas as pd

                table_data = []
                for i, scene in enumerate(filtered_scenes):
                    row = {
                        "씬": scene.get("scene_id", i + 1),
                        "시간(초)": scene.get("duration_estimate", 10),
                        "스크립트": scene.get("script_text", "")[:100] + "...",
                        "캐릭터": safe_join_characters(scene.get("characters", [])),
                        "분위기": scene.get("mood", ""),
                        "이미지": "O" if i < len(image_files) else "X"
                    }
                    table_data.append(row)

                df = pd.DataFrame(table_data)
                st.dataframe(df, use_container_width=True)

            # === 타임라인 뷰 (v2.0: 개선된 버전) ===
            elif view_mode == "타임라인 뷰":
                st.subheader("🎬 스토리보드 (타임라인 뷰)")

                # ─────────────────────────────────────────────────────────
                # 타임라인 설정 패널
                # ─────────────────────────────────────────────────────────
                with st.expander("⚙️ 타임라인 설정 & 이미지 대체", expanded=False):

                    # 한 행 당 씬 수 설정
                    tl_col1, tl_col2, tl_col3 = st.columns([1, 1, 1])

                    with tl_col1:
                        cols_per_row = st.slider(
                            "한 행 당 씬 수",
                            min_value=2, max_value=6, value=4,
                            key="timeline_cols_per_row"
                        )

                    with tl_col2:
                        # 새로고침 버튼
                        if st.button("🔄 이미지 새로고침", key="tl_refresh_btn", use_container_width=True):
                            st.cache_data.clear()
                            st.rerun()

                    with tl_col3:
                        # 묶음 대체 모드
                        bundle_replace_mode = st.toggle(
                            "📦 묶음 대체 모드",
                            value=st.session_state.get('tl_bundle_replace_mode', False),
                            key="tl_bundle_toggle",
                            help="활성화하면 같은 묶음의 모든 씬이 함께 대체됩니다"
                        )
                        st.session_state['tl_bundle_replace_mode'] = bundle_replace_mode

                    # 합성 설정 (타임라인 합성 모듈 사용 가능할 때만)
                    if TIMELINE_COMPOSITE_AVAILABLE:
                        st.markdown("---")
                        st.markdown("#### 🎨 이미지 합성 설정")

                        comp_col1, comp_col2, comp_col3 = st.columns(3)

                        with comp_col1:
                            realshot_width_pct = st.slider(
                                "실사 가로 비율 (%)",
                                min_value=20, max_value=100, value=60, step=5,
                                key="tl_realshot_width"
                            )

                        with comp_col2:
                            realshot_height_pct = st.slider(
                                "실사 세로 비율 (%)",
                                min_value=20, max_value=100, value=60, step=5,
                                key="tl_realshot_height"
                            )

                        with comp_col3:
                            position_options = [opt[1] for opt in POSITION_OPTIONS]
                            position_values = [opt[0] for opt in POSITION_OPTIONS]
                            position_idx = st.selectbox(
                                "위치",
                                options=range(len(position_options)),
                                format_func=lambda i: position_options[i],
                                index=0,
                                key="tl_position"
                            )
                            position = position_values[position_idx]

                        # 배경 설정
                        bg_col1, bg_col2 = st.columns(2)

                        with bg_col1:
                            bg_source_options = [opt[1] for opt in BG_SOURCE_OPTIONS]
                            bg_source_values = [opt[0] for opt in BG_SOURCE_OPTIONS]
                            bg_source_idx = st.selectbox(
                                "배경 소스",
                                options=range(len(bg_source_options)),
                                format_func=lambda i: bg_source_options[i],
                                index=0,
                                key="tl_bg_source"
                            )
                            bg_source = bg_source_values[bg_source_idx]

                        with bg_col2:
                            if bg_source == 'existing':
                                bg_opacity = st.slider(
                                    "배경 투명도",
                                    min_value=0.0, max_value=1.0, value=0.3, step=0.05,
                                    key="tl_bg_opacity",
                                    help="0 = 검정, 1 = 완전히 보임"
                                )
                                bg_darken = st.slider(
                                    "배경 어둡게",
                                    min_value=0.0, max_value=1.0, value=0.2, step=0.05,
                                    key="tl_bg_darken"
                                )
                            elif bg_source == 'color':
                                bg_color = st.color_picker(
                                    "배경 색상",
                                    value="#1a1a2e",
                                    key="tl_bg_color"
                                )
                            elif bg_source == 'blur':
                                blur_radius = st.slider(
                                    "블러 강도",
                                    min_value=5, max_value=50, value=20, step=5,
                                    key="tl_blur_radius"
                                )

                        # 합성 설정 저장
                        composite_settings = {
                            'realshot_width_pct': realshot_width_pct,
                            'realshot_height_pct': realshot_height_pct,
                            'position': position,
                            'bg_source': bg_source,
                            'bg_settings': {}
                        }

                        if bg_source == 'existing':
                            composite_settings['bg_settings']['opacity'] = bg_opacity
                            composite_settings['bg_settings']['darken'] = bg_darken
                        elif bg_source == 'color':
                            composite_settings['bg_settings']['color'] = bg_color
                        elif bg_source == 'blur':
                            composite_settings['bg_settings']['blur_radius'] = blur_radius

                        st.session_state['tl_composite_settings'] = composite_settings
                    else:
                        cols_per_row = 4
                        composite_settings = None

                st.markdown("---")

                # ─────────────────────────────────────────────────────────
                # 타임라인 그리드
                # ─────────────────────────────────────────────────────────
                current_time = 0

                for row_start in range(0, len(filtered_scenes), cols_per_row):
                    cols = st.columns(cols_per_row)

                    for j, col in enumerate(cols):
                        idx = row_start + j
                        if idx >= len(filtered_scenes):
                            break

                        scene = filtered_scenes[idx]
                        scene_id = scene.get("scene_id", idx + 1)
                        bundle_id = scene.get("bundle_id")
                        duration = scene.get("duration_estimate", 10)

                        with col:
                            # ⭐ 씬 번호 헤더 (v2.0)
                            header_col1, header_col2 = st.columns([2, 1])
                            with header_col1:
                                if bundle_id:
                                    st.markdown(f"**씬 {scene_id}** <span style='color:#888;font-size:11px;'>묶음{bundle_id}</span>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"**씬 {scene_id}**")
                            with header_col2:
                                minutes = current_time // 60
                                seconds = current_time % 60
                                st.caption(f"⏱️{minutes:02d}:{seconds:02d}")

                            # ⭐ 이미지 실시간 동기화 (v2.0)
                            img_path = None
                            if TIMELINE_COMPOSITE_AVAILABLE:
                                img_path = get_latest_scene_image(scene, str(project_path))

                            # 폴백: 기존 방식
                            if not img_path and idx < len(image_files):
                                img_path = str(image_files[idx])

                            if img_path and os.path.exists(img_path):
                                st.image(img_path, use_container_width=True)

                                # 확대/프롬프트 버튼
                                btn_c1, btn_c2 = st.columns(2)
                                with btn_c1:
                                    if st.button("🔍", key=f"tl_zoom_{idx}_{scene_id}", help="확대"):
                                        st.session_state[f'tl_zoom_{idx}_{scene_id}'] = True
                                with btn_c2:
                                    if st.button("📝", key=f"tl_prompt_{idx}_{scene_id}", help="프롬프트"):
                                        st.session_state[f'tl_prompt_{idx}_{scene_id}'] = not st.session_state.get(f'tl_prompt_{idx}_{scene_id}', False)

                                # 확대 모달
                                if st.session_state.get(f'tl_zoom_{idx}_{scene_id}', False):
                                    from utils.image_viewer import show_image_modal
                                    show_image_modal(img_path, scene_id, scene, f"씬 {scene_id}")
                                    st.session_state[f'tl_zoom_{idx}_{scene_id}'] = False

                                # 프롬프트 expander
                                if st.session_state.get(f'tl_prompt_{idx}_{scene_id}', False):
                                    prompt_info = ImagePromptManager.get_prompt_from_scene(scene)
                                    prompt_text = prompt_info.get('image_prompt', '')
                                    if prompt_text:
                                        st.caption(prompt_text[:80] + "..." if len(prompt_text) > 80 else prompt_text)
                                    else:
                                        st.caption("프롬프트 없음")
                            else:
                                st.info(f"씬 {scene_id} - 이미지 없음")

                            # ⭐ 드래그 앤 드롭 이미지 대체 (v2.0)
                            if TIMELINE_COMPOSITE_AVAILABLE:
                                uploaded_file = st.file_uploader(
                                    "이미지/비디오",
                                    type=['png', 'jpg', 'jpeg', 'webp', 'mp4', 'mov'],
                                    key=f"tl_drop_{idx}_{scene_id}",
                                    label_visibility="collapsed"
                                )

                                if uploaded_file:
                                    # 합성 설정 가져오기
                                    settings = st.session_state.get('tl_composite_settings', DEFAULT_COMPOSITE_SETTINGS)

                                    with st.spinner(f"씬 {scene_id} 처리 중..."):
                                        # 파일 타입 확인
                                        file_ext = uploaded_file.name.split('.')[-1].lower()
                                        is_video = file_ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']

                                        if is_video:
                                            # 비디오: 썸네일 추출 후 합성
                                            thumb_path = extract_video_thumbnail(uploaded_file, scene_id, str(project_path))
                                            if thumb_path:
                                                realshot_source = thumb_path
                                            else:
                                                st.error("비디오 썸네일 추출 실패")
                                                realshot_source = None

                                            # 비디오 파일도 저장
                                            save_realshot_file(uploaded_file, scene_id, str(project_path))
                                        else:
                                            realshot_source = uploaded_file

                                        if realshot_source:
                                            if bundle_replace_mode and bundle_id:
                                                # 묶음 대체
                                                count = replace_bundle_scenes(
                                                    realshot_source=realshot_source,
                                                    scene=scene,
                                                    all_scenes=filtered_scenes,
                                                    project_path=str(project_path),
                                                    settings=settings
                                                )
                                                st.success(f"✅ 묶음 {bundle_id} 대체 완료! ({count}개 씬)")
                                            else:
                                                # 단일 씬 대체
                                                result = create_composite_realshot(
                                                    realshot_source=realshot_source,
                                                    scene_num=scene_id,
                                                    project_path=str(project_path),
                                                    settings=settings
                                                )
                                                if result:
                                                    st.success(f"✅ 씬 {scene_id} 합성 완료!")
                                                else:
                                                    st.error("합성 실패")

                                    st.rerun()

                            # 스크립트 미리보기
                            script_preview = scene.get("script_text", "")[:30]
                            st.caption(script_preview + "..." if script_preview else "")

                            current_time += duration

            # 내보내기 옵션
            st.divider()
            st.subheader("📤 내보내기")

            col1, col2, col3 = st.columns(3)

            with col1:
                storyboard_data = {
                    "project": project_path.name,
                    "created_at": datetime.now().isoformat(),
                    "scenes": scenes,
                    "total_duration": sum(s.get("duration_estimate", 10) for s in scenes),
                    "image_count": len(image_files)
                }
                st.download_button(
                    "📥 스토리보드 JSON",
                    data=json.dumps(storyboard_data, ensure_ascii=False, indent=2),
                    file_name="storyboard.json",
                    mime="application/json",
                    use_container_width=True
                )

            with col2:
                st.page_link(
                    "pages/7_📦_Vrew_Export.py",
                    label="📦 Vrew Export",
                    icon="➡️",
                    use_container_width=True
                )

            with col3:
                st.button("📊 프리미어 XML 생성", use_container_width=True, disabled=True)
                st.caption("준비 중")

            # 다음 단계 안내
            st.divider()
            st.info("스토리보드 확인 후 Vrew Export로 최종 영상 제작을 진행하세요.")
