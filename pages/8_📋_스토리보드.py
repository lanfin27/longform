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
import io

# Windows cp949 인코딩 에러 방지: stdout/stderr를 UTF-8 + errors='replace'로 래핑
if sys.stdout and hasattr(sys.stdout, 'buffer') and getattr(sys.stdout, 'encoding', 'utf-8') != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer') and getattr(sys.stderr, 'encoding', 'utf-8') != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    get_current_project_config,
    render_project_sidebar
)
from utils.api_helper import show_api_status_sidebar

# ⭐ 안전한 import (KeyError 방지)
try:
    from utils.image_scene_matcher import ImageSceneMatcher, auto_sync_images_to_storyboard
    IMAGE_SCENE_MATCHER_AVAILABLE = True
except (ImportError, KeyError) as e:
    print(f"[스토리보드] ⚠️ image_scene_matcher import 실패: {e}")
    IMAGE_SCENE_MATCHER_AVAILABLE = False

    # Fallback 구현
    class ImageSceneMatcher:
        def __init__(self, project_path):
            self.project_path = project_path

        def get_scene_images(self, scene_id):
            return {"background": None, "character": None, "korean_text": None, "composite": None}

        def match_images_to_scenes(self, scenes, **kwargs):
            return {}

        def get_matching_summary(self, scenes, **kwargs):
            return {"total_scenes": 0, "matched_exact": 0, "matched_sequential": 0, "unmatched": 0, "total_images": 0, "match_rate": 0}

        def find_all_images(self, **kwargs):
            return []

        def invalidate_cache(self):
            pass

    def auto_sync_images_to_storyboard(project_path, scenes, copy_to_scenes=True):
        return {"match_results": {}, "copy_results": None, "summary": {}}

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
    from utils.models.infographic import InfographicData, SceneVisualSelection
    from utils.infographic_parser import InfographicParser, parse_infographic_html, get_parsing_info
    from utils.visual_selection_manager import VisualSelectionManager
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
        try:
            print(f"[PROFILER] [{elapsed:.3f}s] {message}", flush=True)
        except UnicodeEncodeError:
            import re
            safe_msg = re.sub(r'[^\x00-\x7F가-힣\s\[\]\(\)\{\}\.,:;!?\-_=+/*@#$%&]+', '', message)
            print(f"[PROFILER] [{elapsed:.3f}s] {safe_msg}", flush=True)


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
            try:
                print(f"[TIMER] {self.name}: {elapsed:.3f}s", flush=True)
            except UnicodeEncodeError:
                import re
                safe_name = re.sub(r'[^\x00-\x7F가-힣\s\[\]\(\)\{\}\.,:;!?\-_=+/*@#$%&]+', '', self.name)
                print(f"[TIMER] {safe_name}: {elapsed:.3f}s", flush=True)


# ============================================================
# 성능 최적화: 캐싱된 싱글톤 객체들 (v3.17)
# ============================================================

@st.cache_resource
def get_cached_image_scene_matcher(project_path_str: str):
    """
    ImageSceneMatcher 캐싱 (프로젝트당 1회만 생성)
    - Streamlit rerun마다 새로 생성하지 않음
    - 프로젝트 변경 시에만 새로 생성
    """
    from pathlib import Path
    return ImageSceneMatcher(Path(project_path_str))


@st.cache_data(ttl=300, show_spinner=False)
def get_scenes_data_cached(scenes_path_str: str, file_mtime: float) -> list:
    """
    scenes.json 데이터 캐싱 (5분)
    - file_mtime을 키로 사용하여 파일 변경 시 자동 갱신
    - 318개 씬 로드 최적화
    """
    from pathlib import Path
    import json

    scenes_path = Path(scenes_path_str)
    if not scenes_path.exists():
        return []

    with open(scenes_path, 'r', encoding='utf-8') as f:
        scenes = json.load(f)

    # 로그는 캐시 미스 시에만 출력
    print(f"[Storyboard] scenes.json 로드: {len(scenes)}개 씬 (캐시 갱신)")
    return scenes


@st.cache_data(ttl=120, show_spinner=False)
def get_metadata_index(project_path_str: str, cache_key: str = "") -> dict:
    """
    메타데이터 인덱스 사전 구축 (역방향 검색 최적화)
    - 모든 JSON 파일을 한 번 스캔하여 scene_id → metadata 매핑 생성
    - 이후 O(1) 검색 가능
    """
    from pathlib import Path
    import json

    project_path = Path(project_path_str)
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


def _update_scene_image_in_json(project_path, scene_id: int, new_image_path: str):
    """타임라인 뷰 드래그앤드롭 후 scenes.json 업데이트 (직접 대체)"""
    import time as _time
    scenes_path = Path(project_path) / "analysis" / "scenes.json"
    if not scenes_path.exists():
        return
    try:
        with open(scenes_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if content.startswith('\ufeff'):
            content = content[1:]
        scenes = json.loads(content)

        for scene in scenes:
            sid = scene.get('scene_id', scene.get('id', 0))
            if sid == scene_id:
                # 대체 이미지 경로 (최우선)
                scene['replaced_image_path'] = new_image_path
                scene['composited_image_path'] = new_image_path
                scene['real_image_path'] = new_image_path
                scene['image_replaced'] = True
                scene['replaced_at'] = int(_time.time() * 1000)
                scene['replacement_type'] = 'timeline_replace'
                # 이미지로 대체 시 비디오 모드 해제
                if not new_image_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
                    scene['media_type'] = 'image'
                    scene.pop('background_video', None)
                print(f"[Timeline] 씬 {scene_id} 이미지 대체: {os.path.basename(new_image_path)}")
                break

        with open(scenes_path, 'w', encoding='utf-8') as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Timeline] scenes.json 업데이트 실패: {e}")


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
# 인포그래픽 생성 후 scenes.json 즉시 반영
# ============================================================

def _sync_infographic_to_scenes_json(
    project_path,
    results: dict,
    media_type: str,
    infographic_data=None
):
    """
    인포그래픽 이미지/동영상 생성 후 scenes.json에 즉시 반영

    Args:
        project_path: 프로젝트 경로 (Path)
        results: {scene_id: output_path} 딕셔너리 (실제 씬 번호 키)
        media_type: "image" 또는 "video"
        infographic_data: InfographicData (현재 미사용, 호환성 유지)
    """
    import time
    scenes_path = project_path / "analysis" / "scenes.json"
    if not scenes_path.exists():
        print(f"[인포그래픽 Sync] scenes.json 없음: {scenes_path}")
        return 0

    try:
        with open(scenes_path, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
    except Exception as e:
        print(f"[인포그래픽 Sync] scenes.json 로드 실패: {e}")
        return 0

    # results 키가 이미 실제 scene_id (scene_id_map 적용 후)
    infographic_map = {}
    for scene_id, output_path in results.items():
        infographic_map[scene_id] = output_path

    # scenes.json 업데이트
    updated_count = 0
    timestamp = int(time.time() * 1000)

    for scene in scenes:
        sid = scene.get('scene_id', scene.get('id', 0))
        if sid in infographic_map:
            output_path = infographic_map[sid]

            if media_type == "image":
                scene['infographic_image_path'] = output_path
                scene['infographic_type'] = 'image'
            elif media_type == "video":
                scene['infographic_video_path'] = output_path
                scene['infographic_type'] = 'video'
                scene['media_type'] = 'video'
                scene['background_video'] = output_path

            scene['visual_type'] = 'infographic'
            scene['infographic_updated_at'] = timestamp
            updated_count += 1

    if updated_count > 0:
        try:
            with open(scenes_path, 'w', encoding='utf-8') as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            print(f"[인포그래픽 Sync] scenes.json 업데이트 완료: {updated_count}개 씬 ({media_type})")
        except Exception as e:
            print(f"[인포그래픽 Sync] scenes.json 저장 실패: {e}")
            return 0

        # session_state 캐시 무효화
        st.session_state['_scene_files_dirty'] = True
        st.session_state['force_reload_scenes'] = True
        st.session_state['storyboard_needs_refresh'] = True

        # ⭐ v2.5: 미디어 내보내기 캐시 무효화 (image_cache_version 증가)
        invalidate_image_list_cache_light()

        # 씬별 시각 자료 선택 초기화 플래그 제거 (재동기화 유도)
        for key in list(st.session_state.keys()):
            if key.startswith("scene_sel_initialized_"):
                del st.session_state[key]

        # scene_infographic_map 업데이트 (sync_manager 호환)
        existing_map = st.session_state.get('scene_infographic_map', {})
        for sid, path in infographic_map.items():
            existing_map[sid] = path
        st.session_state['scene_infographic_map'] = existing_map

        # scenes 세션 캐시도 업데이트
        if 'scenes' in st.session_state:
            st.session_state['scenes'] = scenes

    else:
        print(f"[인포그래픽 Sync] 매칭된 씬 없음 (infographic IDs: {list(infographic_map.keys())})")

    return updated_count


def _apply_infographic_files_to_storyboard(
    project_path,
    media_dir: str,
    media_files: list,
    media_type: str
):
    """
    기존 생성된 인포그래픽 파일들을 스토리보드(scenes.json)에 반영 (수동 버튼용)

    Args:
        project_path: 프로젝트 경로 (Path)
        media_dir: 이미지/동영상 디렉토리 경로
        media_files: 파일명 리스트
        media_type: "image" 또는 "video"
    """
    import time
    import re as _re

    scenes_path = project_path / "analysis" / "scenes.json"
    if not scenes_path.exists():
        print(f"[인포그래픽 반영] scenes.json 없음: {scenes_path}")
        return 0

    try:
        with open(scenes_path, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
    except Exception as e:
        print(f"[인포그래픽 반영] scenes.json 로드 실패: {e}")
        return 0

    # 파일명에서 씬 번호 추출 → {scene_id: file_path}
    scene_file_map = {}
    for filename in media_files:
        # infographic_scene_001.png → 1, infographic_scene_011.mp4 → 11
        match = _re.search(r'scene_(\d+)', filename)
        if match:
            scene_id = int(match.group(1))
            file_path = os.path.join(media_dir, filename)
            # 같은 씬에 여러 파일이 있으면 최신 파일 사용
            if scene_id not in scene_file_map or os.path.getmtime(file_path) > os.path.getmtime(scene_file_map[scene_id]):
                scene_file_map[scene_id] = file_path

    if not scene_file_map:
        print(f"[인포그래픽 반영] 파일명에서 씬 번호를 추출할 수 없음")
        return 0

    # scenes.json 업데이트
    updated_count = 0
    timestamp = int(time.time() * 1000)

    for scene in scenes:
        sid = scene.get('scene_id', scene.get('id', 0))
        if sid in scene_file_map:
            file_path = scene_file_map[sid]

            if media_type == "image":
                scene['infographic_image_path'] = file_path
                scene['infographic_type'] = 'image'
            elif media_type == "video":
                scene['infographic_video_path'] = file_path
                scene['infographic_type'] = 'video'
                scene['media_type'] = 'video'
                scene['background_video'] = file_path

            scene['visual_type'] = 'infographic'
            scene['infographic_updated_at'] = timestamp
            updated_count += 1

    if updated_count > 0:
        try:
            with open(scenes_path, 'w', encoding='utf-8') as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            print(f"[인포그래픽 반영] scenes.json 업데이트: {updated_count}개 씬 ({media_type})")
        except Exception as e:
            print(f"[인포그래픽 반영] scenes.json 저장 실패: {e}")
            return 0

        # session_state 캐시 무효화
        st.session_state['_scene_files_dirty'] = True
        st.session_state['force_reload_scenes'] = True
        st.session_state['storyboard_needs_refresh'] = True

        # ⭐ v2.5: 미디어 내보내기 캐시 무효화 (image_cache_version 증가)
        invalidate_image_list_cache_light()

        for key in list(st.session_state.keys()):
            if key.startswith("scene_sel_initialized_"):
                del st.session_state[key]

        # scene_infographic_map 업데이트 (sync_manager 호환)
        existing_map = st.session_state.get('scene_infographic_map', {})
        existing_map.update(scene_file_map)
        st.session_state['scene_infographic_map'] = existing_map

        if 'scenes' in st.session_state:
            st.session_state['scenes'] = scenes

    else:
        print(f"[인포그래픽 반영] 매칭된 씬 없음 (file IDs: {list(scene_file_map.keys())})")

    return updated_count


def _find_scene_background(scenes_data: list, scene_id: int, project_path) -> str:
    """scenes.json에서 해당 scene_id의 기존 이미지 경로를 찾는다"""
    for scene in scenes_data:
        sid = scene.get('scene_id', scene.get('id', 0))
        if sid == scene_id:
            for key in ['composited_image_path', 'real_image_path', 'composite_image_path',
                         'image_path', 'background_image']:
                path = scene.get(key)
                if path and os.path.exists(path):
                    return path
            break
    # 파일시스템 폴백: scenes/scene_XXX.png
    from pathlib import Path
    p = Path(project_path) if isinstance(project_path, str) else project_path
    scene_num_str = f"{scene_id:03d}"
    for pattern in [f"images/scenes/scene_{scene_num_str}.png",
                    f"images/scenes/scene_{scene_num_str}.*",
                    f"images/backgrounds/bg_scene_{scene_num_str}_*.png"]:
        import glob as _glob
        matches = _glob.glob(str(p / pattern))
        if matches:
            return max(matches, key=os.path.getmtime)
    return None


INFOGRAPHIC_POSITION_MAP = {
    "중앙": "center",
    "상단 중앙": "top",
    "하단 중앙": "bottom",
    "좌측": "left",
    "우측": "right",
    "좌측 상단": "top-left",
    "우측 상단": "top-right",
    "좌측 하단": "bottom-left",
    "우측 하단": "bottom-right",
}


def _calculate_infographic_position(canvas_w, canvas_h, obj_w, obj_h, position="center", margin=20):
    """캔버스 내 인포그래픽 배치 위치 계산"""
    if position == "center":
        return ((canvas_w - obj_w) // 2, (canvas_h - obj_h) // 2)
    elif position == "top":
        return ((canvas_w - obj_w) // 2, margin)
    elif position == "bottom":
        return ((canvas_w - obj_w) // 2, canvas_h - obj_h - margin)
    elif position == "left":
        return (margin, (canvas_h - obj_h) // 2)
    elif position == "right":
        return (canvas_w - obj_w - margin, (canvas_h - obj_h) // 2)
    elif position == "top-left":
        return (margin, margin)
    elif position == "top-right":
        return (canvas_w - obj_w - margin, margin)
    elif position == "bottom-left":
        return (margin, canvas_h - obj_h - margin)
    elif position == "bottom-right":
        return (canvas_w - obj_w - margin, canvas_h - obj_h - margin)
    return ((canvas_w - obj_w) // 2, (canvas_h - obj_h) // 2)


def _composite_with_scene_background(
    infographic_path: str,
    background_path,
    bg_opacity_pct: int,
    width_pct: int = 100,
    height_pct: int = 100,
    position: str = "center"
):
    """인포그래픽 이미지에 배경 + 크기/위치 합성 (in-place)

    Args:
        infographic_path: 인포그래픽 이미지 경로
        background_path: 배경 이미지 경로 (None이면 배경 없이 크기/위치만 적용)
        bg_opacity_pct: 배경 투명도 (0-100)
        width_pct: 인포그래픽 너비 비율 (10-100)
        height_pct: 인포그래픽 높이 비율 (10-100)
        position: 위치 (center, top, bottom, left, right, top-left, ...)
    """
    from PIL import Image

    infographic = Image.open(infographic_path).convert("RGBA")
    canvas_size = infographic.size  # 원본 캔버스 크기 유지
    canvas_w, canvas_h = canvas_size

    # 흰색 캔버스
    canvas = Image.new("RGBA", canvas_size, (255, 255, 255, 255))

    # 배경 합성 (있는 경우)
    if background_path and os.path.exists(str(background_path)) and bg_opacity_pct > 0:
        background = Image.open(str(background_path)).convert("RGBA")
        if background.size != canvas_size:
            background = background.resize(canvas_size, Image.LANCZOS)

        alpha_factor = bg_opacity_pct / 100.0
        r, g, b, a = background.split()
        a = a.point(lambda p: int(p * alpha_factor))
        background = Image.merge("RGBA", (r, g, b, a))
        canvas = Image.alpha_composite(canvas, background)

    # 인포그래픽 리사이즈 (크기 비율 적용)
    new_w = int(canvas_w * width_pct / 100)
    new_h = int(canvas_h * height_pct / 100)

    if width_pct < 100 or height_pct < 100:
        infographic = infographic.resize((new_w, new_h), Image.LANCZOS)

    # 위치 계산
    x, y = _calculate_infographic_position(canvas_w, canvas_h, new_w, new_h, position)

    # 인포그래픽 배치
    canvas.paste(infographic, (x, y), infographic)

    canvas.save(infographic_path, "PNG")
    log_parts = [f"크기 {width_pct}%x{height_pct}%", f"위치 {position}"]
    if background_path:
        log_parts.append(f"배경 {bg_opacity_pct}%")
    print(f"[합성] {os.path.basename(infographic_path)}: {', '.join(log_parts)}")


def _extract_video_first_frame_to_file(video_file, output_path: str):
    """업로드된 비디오에서 첫 프레임을 추출하여 이미지로 저장"""
    import tempfile
    try:
        import cv2
    except ImportError:
        print("[오류] cv2(OpenCV) 미설치 - 비디오 프레임 추출 불가")
        return None

    try:
        video_file.seek(0)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_file.read())
            tmp_path = tmp.name
        video_file.seek(0)

        cap = cv2.VideoCapture(tmp_path)
        ret, frame = cap.read()
        cap.release()

        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            from PIL import Image as _PILImg
            img = _PILImg.fromarray(frame_rgb).convert("RGBA")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img.save(output_path, "PNG")
            print(f"[배경] 비디오 첫 프레임 추출: {os.path.basename(output_path)}")
            return output_path
        return None
    except Exception as e:
        print(f"[오류] 비디오 프레임 추출 실패: {e}")
        return None


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

    # v2.5: 씬 번호(ID) 기준 min/max 계산 (개수가 아닌 실제 씬 번호 사용)
    scene_ids = [s['scene_id'] for s in scene_list]
    min_scene_id = min(scene_ids) if scene_ids else 1
    max_scene_id = max(scene_ids) if scene_ids else 1

    col_select, col_direct = st.columns([3, 1])

    with col_select:
        selected_label = st.selectbox(
            "씬 선택",
            options=list(scene_options.keys()),
            key="scene_editor_select",
            label_visibility="collapsed"
        )
        selected_scene_id = scene_options.get(selected_label, min_scene_id)

    with col_direct:
        # v2.5: max_value를 씬 개수가 아닌 실제 최대 씬 번호로 설정
        # 방어적 처리: value가 범위를 벗어나면 클램핑
        clamped_value = max(min_scene_id, min(selected_scene_id, max_scene_id))
        direct_id = st.number_input(
            "직접 입력",
            min_value=min_scene_id,
            max_value=max_scene_id,
            value=clamped_value,
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
# 인포그래픽 합성 설정 섹션
# ============================================================

def render_background_replacement_section(infographic_data, project_path, visual_manager):
    """인포그래픽 합성 설정 렌더링 (크기/위치/배경 소스)"""

    st.markdown("### 🖼️ 2.5 인포그래픽 합성 설정")
    st.caption("이미지/비디오 생성 시 인포그래픽 크기, 위치, 배경을 설정합니다.")

    with st.expander("📊 합성 설정", expanded=True):
        _ic_col1, _ic_col2 = st.columns(2)
        with _ic_col1:
            st.slider(
                "인포그래픽 너비 (%)",
                min_value=30, max_value=100, value=60,
                key="infographic_comp_width_pct"
            )
        with _ic_col2:
            st.slider(
                "인포그래픽 높이 (%)",
                min_value=30, max_value=100, value=60,
                key="infographic_comp_height_pct"
            )

        st.selectbox(
            "위치",
            options=["중앙", "상단 중앙", "하단 중앙"],
            key="infographic_comp_position"
        )

        st.slider(
            "배경 투명도 (%)",
            min_value=0, max_value=100, value=30,
            key="infographic_comp_bg_opacity"
        )

        # 배경 설정 (Step 3과 동일)
        st.markdown("---")
        st.markdown("##### 배경 설정")

        st.radio(
            "배경 소스 선택",
            options=["기존 이미지", "업로드 이미지", "업로드 비디오"],
            horizontal=True,
            key="infographic_comp_bg_source",
            help="인포그래픽 뒤에 표시될 배경을 선택합니다"
        )

        _bg_source = st.session_state.get("infographic_comp_bg_source", "기존 이미지")

        if _bg_source == "기존 이미지":
            st.info("📷 각 씬의 기존 이미지(합성/생성/원본)를 배경으로 사용합니다.")

        elif _bg_source == "업로드 이미지":
            _bg_img = st.file_uploader(
                "배경 이미지 업로드",
                type=["png", "jpg", "jpeg", "webp"],
                key="infographic_comp_bg_upload_image",
                help="모든 선택된 씬에 동일한 배경 이미지가 적용됩니다"
            )
            if _bg_img:
                st.success(f"배경 이미지: {_bg_img.name}")
                st.image(_bg_img, caption="배경 이미지 미리보기", use_container_width=True)

        elif _bg_source == "업로드 비디오":
            _bg_vid = st.file_uploader(
                "배경 비디오 업로드",
                type=["mp4", "mov", "avi", "mkv", "webm"],
                key="infographic_comp_bg_upload_video",
                help="인포그래픽을 비디오 위에 오버레이하여 MP4를 생성합니다"
            )
            if _bg_vid:
                try:
                    from utils.timeline_composite import get_video_info_from_file, extract_video_thumbnail
                    _bg_vid.seek(0)
                    _bg_video_info = get_video_info_from_file(_bg_vid)
                    if _bg_video_info:
                        st.success(f"배경 비디오: {_bg_vid.name}")
                        _vi_c1, _vi_c2, _vi_c3 = st.columns(3)
                        with _vi_c1:
                            st.metric("길이", f"{_bg_video_info.get('duration', 0):.1f}초")
                        with _vi_c2:
                            st.metric("해상도", f"{_bg_video_info.get('width', 0)}x{_bg_video_info.get('height', 0)}")
                        with _vi_c3:
                            st.metric("FPS", f"{_bg_video_info.get('fps', 0):.0f}")

                        _bg_vid.seek(0)
                        _thumb = extract_video_thumbnail(_bg_vid, 0, str(project_path))
                        _bg_vid.seek(0)
                        if _thumb and os.path.exists(_thumb):
                            st.image(_thumb, caption="🎬 배경 비디오 미리보기 (첫 프레임)", width=400)

                        _tmp = _bg_video_info.get('temp_path')
                        if _tmp and os.path.exists(_tmp):
                            try:
                                os.unlink(_tmp)
                            except OSError:
                                pass
                except ImportError:
                    st.warning("비디오 미리보기에 필요한 모듈이 없습니다.")



# 페이지 설정
st.set_page_config(
    page_title="스토리보드",
    page_icon="📋",
    layout="wide"
)

# ============================================================
# v3.97: 위젯 session_state 초기화 (위젯 생성 전!)
# Streamlit 규칙: 위젯 key와 연결된 session_state는 위젯 생성 전에만 수정 가능
# ============================================================
def _init_workflow_session_state():
    """워크플로우 위젯 session_state 초기화 (위젯 생성 전에 실행!)"""
    # Step 1: 한글 텍스트
    if "step1_processing_mode" not in st.session_state:
        st.session_state["step1_processing_mode"] = "batch"
    if "step1_selection_mode" not in st.session_state:
        st.session_state["step1_selection_mode"] = "AI 분석 씬만"
    if "step1_reference" not in st.session_state:
        st.session_state["step1_reference"] = "기존 이미지 사용"
    if "step1_char_ref" not in st.session_state:
        st.session_state["step1_char_ref"] = True
    if "step1_model_select" not in st.session_state:
        st.session_state["step1_model_select"] = "gemini_nano_banana"
    if "step1_max_concurrent" not in st.session_state:
        st.session_state["step1_max_concurrent"] = 4

    # Step 2: 캐릭터 합성
    if "step2_processing_mode" not in st.session_state:
        st.session_state["step2_processing_mode"] = "순차 처리"
    if "step2_method" not in st.session_state:
        st.session_state["step2_method"] = "Nano Banana 합성"
    if "step2_max_workers" not in st.session_state:
        st.session_state["step2_max_workers"] = 4

    # Step 3: 실사 이미지
    if "step3_prompt_selector" not in st.session_state:
        st.session_state["step3_prompt_selector"] = None

# 위젯 session_state 초기화 호출 (최우선!)
_init_workflow_session_state()

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


def get_page_scene_id_ranges(scenes: list, per_page: int = 10) -> list:
    """
    각 페이지의 실제 씬 ID 범위를 계산

    Args:
        scenes: 씬 목록 (scene_id 필드 포함)
        per_page: 페이지당 씬 수

    Returns:
        페이지별 (start_scene_id, end_scene_id) 튜플 리스트
    """
    if not scenes:
        return []

    total_pages = (len(scenes) + per_page - 1) // per_page
    page_ranges = []

    for page in range(total_pages):
        start_idx = page * per_page
        end_idx = min(start_idx + per_page - 1, len(scenes) - 1)

        # 실제 씬 ID 가져오기
        start_scene_id = scenes[start_idx].get('scene_id', start_idx + 1)
        end_scene_id = scenes[end_idx].get('scene_id', end_idx + 1)

        page_ranges.append((start_scene_id, end_scene_id))

    return page_ranges

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
# v3.20: 5단계 워크플로우 탭 추가
if INFOGRAPHIC_AVAILABLE:
    tab_auto, tab_workflow, tab_infographic, tab_manual = st.tabs([
        "🔄 자동 조합",
        "🔢 5단계 워크플로우",
        "📊 인포그래픽",
        "✏️ 수동 구성"
    ])
else:
    tab_auto, tab_workflow, tab_manual = st.tabs([
        "🔄 자동 조합",
        "🔢 5단계 워크플로우",
        "✏️ 수동 구성"
    ])
    tab_infographic = None

# === 5단계 워크플로우 탭 (v3.20) ===
with tab_workflow:
    st.subheader("🔢 5단계 이미지 대체 워크플로우")

    # 프로젝트/영상 선택 확인
    if not project_path:
        st.warning("⚠️ 프로젝트를 먼저 선택하세요.")
    else:
        # scenes.json 로드 (v3.21: 캐싱 적용으로 성능 최적화)
        scenes_path = project_path / "analysis" / "scenes.json"

        if not scenes_path.exists():
            st.warning("⚠️ scenes.json 파일이 없습니다. 먼저 씬 분석을 수행하세요.")
        else:
            try:
                # v3.21: 캐싱 함수 사용 (파일 mtime 기반 자동 갱신)
                file_mtime = scenes_path.stat().st_mtime
                workflow_scenes = get_scenes_data_cached(str(scenes_path), file_mtime)

                if workflow_scenes:
                    # 5단계 워크플로우 렌더링
                    try:
                        from components.storyboard_workflow import render_5step_workflow
                        render_5step_workflow(workflow_scenes, project_path)
                    except ImportError as e:
                        st.error(f"워크플로우 모듈 로드 실패: {e}")
                        st.info("components/storyboard_workflow/ 디렉토리를 확인하세요.")
                else:
                    st.info("씬 데이터가 없습니다.")

            except Exception as e:
                st.error(f"scenes.json 로드 오류: {e}")

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

                # === 2.5. 인포그래픽 합성 설정 ===
                render_background_replacement_section(infographic_data, project_path, visual_manager)

                st.divider()

                # === 3. 인포그래픽 생성 ===
                st.markdown("### 🎬 3. 인포그래픽 생성 (내보내기용)")

                # 씬 수 + scene_id 맵 구축
                scene_count = len(infographic_data.scenes)
                scene_id_map = {i: scene.scene_id for i, scene in enumerate(infographic_data.scenes)}

                # ⚙️ 생성 설정
                with st.expander("⚙️ 생성 설정", expanded=False):
                    _size_col1, _size_col2 = st.columns(2)
                    with _size_col1:
                        output_width = st.number_input(
                            "출력 너비 (px)", value=1920, min_value=640, max_value=3840,
                            step=10, key="infographic_output_width"
                        )
                    with _size_col2:
                        output_height = st.number_input(
                            "출력 높이 (px)", value=1080, min_value=360, max_value=2160,
                            step=10, key="infographic_output_height"
                        )
                    st.caption("💡 인포그래픽 크기/위치/배경 설정은 위 '2.5 배경 이미지 대체' 섹션의 합성 설정에서 조절하세요.")

                # 2.5 합성 설정 읽기
                comp_width_pct = st.session_state.get("infographic_comp_width_pct", 60)
                comp_height_pct = st.session_state.get("infographic_comp_height_pct", 60)
                comp_position = st.session_state.get("infographic_comp_position", "중앙")
                comp_bg_opacity = st.session_state.get("infographic_comp_bg_opacity", 30)
                comp_bg_source = st.session_state.get("infographic_comp_bg_source", "기존 이미지")

                # ⭐ v2.5: 배경이 비디오면 자동으로 비디오(MP4) 출력
                _force_video_output = (comp_bg_source == "업로드 비디오")

                if _force_video_output:
                    st.info("🎬 배경이 비디오이므로 최종 출력은 자동으로 동영상(MP4)으로 생성됩니다.")
                    # 비활성 라디오 표시 (동영상 선택 고정)
                    st.radio(
                        "📷 출력 형식",
                        options=["📸 이미지 (PNG)", "🎬 동영상 (MP4)"],
                        index=1,
                        horizontal=True,
                        disabled=True,
                        key="infographic_output_format_video_forced",
                        help="배경이 비디오이므로 동영상 출력 고정"
                    )
                    is_image_mode = True  # 이미지 캡처 파이프라인 사용 (HTML → PNG → 비디오 합성)
                else:
                    output_format = st.radio(
                        "📷 출력 형식",
                        options=["📸 이미지 (PNG)", "🎬 동영상 (MP4)"],
                        index=0,
                        horizontal=True,
                        key="infographic_output_format",
                        help="이미지: 즉시 캐쳐 (빠름)\n동영상: CSS 애니메이션 녹화 (느림)"
                    )
                    is_image_mode = "이미지" in output_format

                if is_image_mode:
                    if _force_video_output:
                        st.caption("HTML 캡처 → 배경 비디오 합성 → MP4 출력 (FFmpeg 필요)")
                    else:
                        st.caption("Selenium 기반 PNG 이미지 캐쳐 (FFmpeg 불필요)")

                    img_gen_mode = st.radio(
                        "생성 범위", ["전체", "범위", "개별"],
                        key="img_gen_mode", horizontal=True
                    )

                    if img_gen_mode == "범위":
                        img_range = st.slider(
                            "씬 범위 (순서)", min_value=1, max_value=scene_count,
                            value=(1, min(5, scene_count)), key="img_range_slider"
                        )
                        selected_img_indices = list(range(img_range[0] - 1, img_range[1]))
                    elif img_gen_mode == "개별":
                        img_options = [f"씬 {scene.scene_id}" for scene in infographic_data.scenes]
                        selected_img_labels = st.multiselect(
                            "캐쳐할 씬 선택", options=img_options,
                            default=[img_options[0]] if img_options else [],
                            key="img_scene_multiselect"
                        )
                        # 실제 scene_id → 0-based index 변환
                        _scene_id_to_idx = {scene.scene_id: i for i, scene in enumerate(infographic_data.scenes)}
                        selected_img_indices = [
                            _scene_id_to_idx[int(s.replace("씬 ", ""))]
                            for s in selected_img_labels
                            if int(s.replace("씬 ", "")) in _scene_id_to_idx
                        ]
                    else:
                        selected_img_indices = list(range(scene_count))

                    _selected_scene_ids = [scene_id_map.get(idx, idx + 1) for idx in selected_img_indices]
                    if _force_video_output:
                        st.info(f"📊 선택: {len(selected_img_indices)}개 씬 (씬 {', '.join(str(s) for s in _selected_scene_ids[:8])}{'...' if len(_selected_scene_ids) > 8 else ''}) | 🎬 비디오 모드 (배경 비디오 → MP4)")
                    else:
                        st.info(f"📊 선택: {len(selected_img_indices)}개 씬 (씬 {', '.join(str(s) for s in _selected_scene_ids[:8])}{'...' if len(_selected_scene_ids) > 8 else ''}) | ⚡ 이미지 모드")

                    # ⭐ v2.5: 비디오 배경인데 파일 미업로드 시 경고
                    _has_video_file = bool(st.session_state.get("infographic_comp_bg_upload_video"))
                    if _force_video_output and not _has_video_file:
                        st.warning("⚠️ 배경 비디오 파일을 먼저 업로드하세요 (위 '배경 설정' 섹션).")

                    _gen_btn_label = "🎬 인포그래픽 비디오 생성" if _force_video_output else "📸 인포그래픽 이미지 생성"
                    if st.button(_gen_btn_label, type="primary", use_container_width=True, key="capture_images"):
                        if not selected_img_indices:
                            st.error("캐쳐할 씬을 선택하세요.")
                        elif _force_video_output and not _has_video_file:
                            st.error("배경 비디오 파일이 업로드되지 않았습니다.")
                        else:
                            try:
                                output_dir = str(project_path / "infographics" / "images")
                                os.makedirs(output_dir, exist_ok=True)

                                progress_bar = st.progress(0)
                                status_text = st.empty()

                                def img_progress(current, total, message):
                                    progress_bar.progress(current / total)
                                    status_text.text(message)

                                from utils.infographic_video_recorder import get_video_recorder

                                with get_video_recorder(
                                    output_dir=output_dir,
                                    output_width=output_width,
                                    output_height=output_height
                                ) as recorder:
                                    recording_html = (st.session_state.get("modified_infographic_html")
                                                      or st.session_state.get("infographic_html_content")
                                                      or infographic_data.html_code)

                                    results = recorder.capture_selected_scenes_as_images(
                                        html_content=recording_html,
                                        scene_indices=selected_img_indices,
                                        output_dir=output_dir,
                                        scene_id_map=scene_id_map,
                                        output_size=(output_width, output_height),
                                        progress_callback=img_progress
                                    )

                                # 비디오 배경 여부 체크
                                # ⭐ v2.5: _force_video_output로 보강 (opacity 0이어도 비디오 배경이면 비디오 출력)
                                _is_video_bg = (comp_bg_source == "업로드 비디오")
                                _up_vid_for_composite = st.session_state.get("infographic_comp_bg_upload_video") if _is_video_bg else None
                                _is_video_bg = _is_video_bg and _up_vid_for_composite is not None
                                if _is_video_bg and comp_bg_opacity == 0:
                                    comp_bg_opacity = 30  # 비디오 배경 선택 시 투명도 기본값 적용

                                # 합성 처리 (2.5 설정 적용: 크기, 위치, 배경)
                                # ⭐ v2.5: 비디오 배경일 때 이미지 합성 건너뛰기 (이중 합성 방지)
                                # composite_infographic_on_video()가 크기/위치/배경을 일괄 처리하므로
                                # 이미지 단계에서 합성하면 배경+크기+위치가 이중 적용됨
                                need_composite = (
                                    comp_bg_opacity > 0
                                    or comp_width_pct < 100
                                    or comp_height_pct < 100
                                )
                                if need_composite and results and not _is_video_bg:
                                    status_text.text("이미지 합성 처리 중...")
                                    from PIL import Image as _PILImage

                                    # 배경 데이터 로드 (기존 이미지용)
                                    scenes_data_bg = []
                                    if comp_bg_source == "기존 이미지" and comp_bg_opacity > 0:
                                        scenes_path_bg = project_path / "analysis" / "scenes.json"
                                        if scenes_path_bg.exists():
                                            with open(scenes_path_bg, 'r', encoding='utf-8') as f:
                                                scenes_data_bg = json.load(f)

                                    # 업로드 배경 처리 (이미지 합성용)
                                    uploaded_bg_path = None
                                    _bg_dir = str(project_path / "infographics")
                                    os.makedirs(_bg_dir, exist_ok=True)

                                    if comp_bg_source == "업로드 이미지" and comp_bg_opacity > 0:
                                        _up_img = st.session_state.get("infographic_comp_bg_upload_image")
                                        if _up_img:
                                            uploaded_bg_path = os.path.join(_bg_dir, "temp_bg.png")
                                            _PILImage.open(_up_img).save(uploaded_bg_path)

                                    elif _is_video_bg:
                                        # 비디오 배경: 첫 프레임을 이미지 합성용으로 추출 (미리보기 PNG)
                                        uploaded_bg_path = _extract_video_first_frame_to_file(
                                            _up_vid_for_composite, os.path.join(_bg_dir, "temp_bg_video.png")
                                        )

                                    pos_key = INFOGRAPHIC_POSITION_MAP.get(comp_position, "center")
                                    composited = 0
                                    for scene_id, img_path in results.items():
                                        bg_path = None
                                        if comp_bg_opacity > 0:
                                            if comp_bg_source == "기존 이미지":
                                                bg_path = _find_scene_background(
                                                    scenes_data_bg, scene_id, project_path
                                                )
                                            else:
                                                bg_path = uploaded_bg_path
                                        _composite_with_scene_background(
                                            img_path, bg_path, comp_bg_opacity,
                                            width_pct=comp_width_pct,
                                            height_pct=comp_height_pct,
                                            position=pos_key
                                        )
                                        composited += 1
                                    if composited > 0:
                                        print(f"[합성] {composited}개 씬 이미지 합성 완료")

                                # 비디오 배경 합성 (배경이 비디오인 경우 MP4 생성)
                                _video_results = {}
                                if _is_video_bg and results:
                                    status_text.text("비디오 배경 합성 중...")
                                    from utils.timeline_composite import composite_infographic_on_video

                                    # 씬별 duration 로드
                                    _scene_durations = {}
                                    _scenes_path_dur = project_path / "analysis" / "scenes.json"
                                    if _scenes_path_dur.exists():
                                        try:
                                            with open(_scenes_path_dur, 'r', encoding='utf-8') as f:
                                                _scenes_dur = json.load(f)
                                            for s in _scenes_dur:
                                                _sid = s.get('scene_id', s.get('id', 0))
                                                _scene_durations[_sid] = s.get('duration_estimate', s.get('duration', 10))
                                        except Exception:
                                            pass

                                    pos_key = INFOGRAPHIC_POSITION_MAP.get(comp_position, "center")
                                    _total = len(results)
                                    for _vidx, (scene_id, img_path) in enumerate(results.items()):
                                        status_text.text(f"비디오 합성 중... ({_vidx+1}/{_total}) 씬 {scene_id}")
                                        progress_bar.progress((_vidx + 1) / _total * 0.5 + 0.5)

                                        _vid_settings = {
                                            'output_width': output_width,
                                            'output_height': output_height,
                                            'width_pct': comp_width_pct,
                                            'height_pct': comp_height_pct,
                                            'position': pos_key,
                                            'bg_opacity_pct': comp_bg_opacity,
                                            'target_duration': _scene_durations.get(scene_id, 10),
                                            'loop_video': True,
                                        }

                                        _vid_path = composite_infographic_on_video(
                                            infographic_png_path=img_path,
                                            bg_video_source=_up_vid_for_composite,
                                            scene_num=scene_id,
                                            project_path=str(project_path),
                                            settings=_vid_settings
                                        )

                                        if _vid_path:
                                            _video_results[scene_id] = _vid_path
                                        else:
                                            print(f"[합성] 씬 {scene_id} 비디오 합성 실패")

                                    if _video_results:
                                        print(f"[합성] {len(_video_results)}개 씬 비디오 합성 완료")

                                progress_bar.progress(1.0)

                                # 스토리보드 자동 반영
                                if _video_results:
                                    _sync_infographic_to_scenes_json(
                                        project_path, _video_results, "video"
                                    )
                                    status_text.text(f"완료! {len(results)}개 이미지 + {len(_video_results)}개 비디오 생성")
                                    st.success(f"✅ {len(results)}개 이미지 + {len(_video_results)}개 비디오 생성 완료!")
                                else:
                                    status_text.text(f"완료! {len(results)}개 이미지 생성")
                                    st.success(f"✅ {len(results)}개 인포그래픽 이미지 생성 완료! 미리보기를 확인하세요.")

                                st.rerun()

                            except RuntimeError as e:
                                st.error(f"이미지 캐쳐 초기화 실패: {str(e)}")
                                st.info("필수 요소: `pip install selenium webdriver-manager pillow`")
                            except Exception as e:
                                st.error(f"캐쳐 오류: {str(e)}")

                    # 이미지 미리보기 (선택/삭제 기능 포함)
                    images_dir = str(project_path / "infographics" / "images")
                    if os.path.exists(images_dir):
                        image_files = sorted([f for f in os.listdir(images_dir) if f.endswith('.png')])
                        if image_files:
                            with st.expander(f"📸 생성된 이미지 ({len(image_files)}개)", expanded=False):
                                # ── 선택/삭제 컨트롤 ──
                                _img_sel_key = "infographic_img_selected"
                                if _img_sel_key not in st.session_state:
                                    st.session_state[_img_sel_key] = set()

                                _sel_count = len(st.session_state[_img_sel_key])
                                _ctrl_c1, _ctrl_c2, _ctrl_c3, _ctrl_c4 = st.columns([1, 1, 2, 1])
                                with _ctrl_c1:
                                    if st.button("☑️ 전체 선택", key="img_sel_all", use_container_width=True):
                                        st.session_state[_img_sel_key] = set(image_files)
                                        st.rerun()
                                with _ctrl_c2:
                                    if st.button("⬜ 전체 해제", key="img_desel_all", use_container_width=True):
                                        st.session_state[_img_sel_key] = set()
                                        st.rerun()
                                with _ctrl_c3:
                                    if _sel_count > 0:
                                        if st.button(f"🗑️ 선택 삭제 ({_sel_count}개)", key="img_del_selected", type="primary", use_container_width=True):
                                            _del_ok = 0
                                            for _df in list(st.session_state[_img_sel_key]):
                                                _dp = os.path.join(images_dir, _df)
                                                if os.path.exists(_dp):
                                                    try:
                                                        os.remove(_dp)
                                                        _del_ok += 1
                                                    except OSError:
                                                        pass
                                            st.session_state[_img_sel_key] = set()
                                            st.success(f"✅ {_del_ok}개 이미지 삭제 완료")
                                            st.rerun()
                                    else:
                                        st.caption(f"선택: 0 / {len(image_files)}")
                                with _ctrl_c4:
                                    if st.button("🗑️ 전체 삭제", key="img_del_all", use_container_width=True):
                                        st.session_state["_confirm_del_all_img"] = True

                                # 전체 삭제 확인
                                if st.session_state.get("_confirm_del_all_img"):
                                    st.warning(f"⚠️ 모든 인포그래픽 이미지 {len(image_files)}개를 삭제하시겠습니까?")
                                    _dc1, _dc2, _dc3 = st.columns([1, 1, 3])
                                    with _dc1:
                                        if st.button("✅ 삭제 확인", key="img_del_all_confirm", type="primary", use_container_width=True):
                                            _del_ok = 0
                                            for _df in image_files:
                                                _dp = os.path.join(images_dir, _df)
                                                if os.path.exists(_dp):
                                                    try:
                                                        os.remove(_dp)
                                                        _del_ok += 1
                                                    except OSError:
                                                        pass
                                            st.session_state[_img_sel_key] = set()
                                            st.session_state["_confirm_del_all_img"] = False
                                            st.success(f"✅ {_del_ok}개 이미지 삭제 완료")
                                            st.rerun()
                                    with _dc2:
                                        if st.button("❌ 취소", key="img_del_all_cancel", use_container_width=True):
                                            st.session_state["_confirm_del_all_img"] = False
                                            st.rerun()

                                # ── 이미지 갤러리 그리드 (체크박스 포함) ──
                                img_cols_count = min(4, len(image_files))
                                for row_start in range(0, len(image_files), img_cols_count):
                                    img_cols = st.columns(img_cols_count)
                                    for col_idx in range(img_cols_count):
                                        img_idx = row_start + col_idx
                                        if img_idx < len(image_files):
                                            _fname = image_files[img_idx]
                                            with img_cols[col_idx]:
                                                _is_sel = _fname in st.session_state[_img_sel_key]
                                                _cb = st.checkbox(
                                                    _fname,
                                                    value=_is_sel,
                                                    key=f"img_cb_{img_idx}"
                                                )
                                                if _cb and _fname not in st.session_state[_img_sel_key]:
                                                    st.session_state[_img_sel_key].add(_fname)
                                                elif not _cb and _fname in st.session_state[_img_sel_key]:
                                                    st.session_state[_img_sel_key].discard(_fname)
                                                img_path = os.path.join(images_dir, _fname)
                                                st.image(img_path, use_container_width=True)

                                # 스토리보드 반영 버튼
                                st.divider()
                                apply_col1, apply_col2 = st.columns([2, 3])
                                with apply_col1:
                                    if st.button("📋 스토리보드에 반영", type="primary", key="apply_infographic_images", use_container_width=True):
                                        synced = _apply_infographic_files_to_storyboard(
                                            project_path, images_dir, image_files, "image"
                                        )
                                        if synced > 0:
                                            st.success(f"✅ {synced}개 씬 스토리보드에 반영 완료!")
                                            st.rerun()
                                        else:
                                            st.warning("매칭된 씬이 없습니다. 파일명에 씬 번호가 포함되어야 합니다.")
                                with apply_col2:
                                    st.caption(f"📸 {len(image_files)}개 이미지 → scenes.json 반영")

                    # 비디오 미리보기 (배경 비디오 합성으로 생성된 MP4) - 선택/삭제 포함
                    _vid_preview_dir = str(project_path / "infographics" / "videos")
                    if os.path.exists(_vid_preview_dir):
                        _vid_preview_files = sorted([
                            f for f in os.listdir(_vid_preview_dir)
                            if f.endswith('.mp4') and 'infographic_scene' in f
                        ])
                        if _vid_preview_files:
                            with st.expander(f"🎬 생성된 비디오 - 배경 합성 ({len(_vid_preview_files)}개)", expanded=False):

                                # ── 비디오 선택/삭제 컨트롤 ──
                                _vid_sel_key = "infographic_vid_selected"
                                if _vid_sel_key not in st.session_state:
                                    st.session_state[_vid_sel_key] = set()

                                _vsel_count = len(st.session_state[_vid_sel_key])
                                _vc1, _vc2, _vc3, _vc4 = st.columns([1, 1, 2, 1])
                                with _vc1:
                                    if st.button("☑️ 전체 선택", key="vid_bg_sel_all", use_container_width=True):
                                        st.session_state[_vid_sel_key] = set(_vid_preview_files)
                                        st.rerun()
                                with _vc2:
                                    if st.button("⬜ 전체 해제", key="vid_bg_desel_all", use_container_width=True):
                                        st.session_state[_vid_sel_key] = set()
                                        st.rerun()
                                with _vc3:
                                    if _vsel_count > 0:
                                        if st.button(f"🗑️ 선택 삭제 ({_vsel_count}개)", key="vid_bg_del_selected", type="primary", use_container_width=True):
                                            _vdel_ok = 0
                                            for _vdf in list(st.session_state[_vid_sel_key]):
                                                _vdp = os.path.join(_vid_preview_dir, _vdf)
                                                if os.path.exists(_vdp):
                                                    try:
                                                        os.remove(_vdp)
                                                        _vdel_ok += 1
                                                    except OSError:
                                                        pass
                                            st.session_state[_vid_sel_key] = set()
                                            st.success(f"✅ {_vdel_ok}개 비디오 삭제 완료")
                                            st.rerun()
                                    else:
                                        st.caption(f"선택: 0 / {len(_vid_preview_files)}")
                                with _vc4:
                                    if st.button("🗑️ 전체 삭제", key="vid_bg_del_all", use_container_width=True):
                                        st.session_state["_confirm_del_all_vid_bg"] = True

                                if st.session_state.get("_confirm_del_all_vid_bg"):
                                    st.warning(f"⚠️ 모든 비디오 {len(_vid_preview_files)}개를 삭제하시겠습니까?")
                                    _vdc1, _vdc2, _vdc3 = st.columns([1, 1, 3])
                                    with _vdc1:
                                        if st.button("✅ 삭제 확인", key="vid_bg_del_all_confirm", type="primary", use_container_width=True):
                                            _vdel_ok = 0
                                            for _vdf in _vid_preview_files:
                                                _vdp = os.path.join(_vid_preview_dir, _vdf)
                                                if os.path.exists(_vdp):
                                                    try:
                                                        os.remove(_vdp)
                                                        _vdel_ok += 1
                                                    except OSError:
                                                        pass
                                            st.session_state[_vid_sel_key] = set()
                                            st.session_state["_confirm_del_all_vid_bg"] = False
                                            st.success(f"✅ {_vdel_ok}개 비디오 삭제 완료")
                                            st.rerun()
                                    with _vdc2:
                                        if st.button("❌ 취소", key="vid_bg_del_all_cancel", use_container_width=True):
                                            st.session_state["_confirm_del_all_vid_bg"] = False
                                            st.rerun()

                                # 비디오 갤러리
                                _vid_cols_count = min(4, len(_vid_preview_files))
                                for _vrow_start in range(0, len(_vid_preview_files), _vid_cols_count):
                                    _vid_cols = st.columns(_vid_cols_count)
                                    for _vcol_idx in range(_vid_cols_count):
                                        _vid_idx = _vrow_start + _vcol_idx
                                        if _vid_idx < len(_vid_preview_files):
                                            _vfname = _vid_preview_files[_vid_idx]
                                            with _vid_cols[_vcol_idx]:
                                                _vis_sel = _vfname in st.session_state[_vid_sel_key]
                                                _vcb = st.checkbox(
                                                    _vfname,
                                                    value=_vis_sel,
                                                    key=f"vid_bg_cb_{_vid_idx}"
                                                )
                                                if _vcb and _vfname not in st.session_state[_vid_sel_key]:
                                                    st.session_state[_vid_sel_key].add(_vfname)
                                                elif not _vcb and _vfname in st.session_state[_vid_sel_key]:
                                                    st.session_state[_vid_sel_key].discard(_vfname)
                                                _vp = os.path.join(_vid_preview_dir, _vfname)
                                                st.video(_vp)
                                                _vsize = os.path.getsize(_vp) / (1024 * 1024)
                                                st.caption(f"{_vfname} ({_vsize:.1f}MB)")

                                st.divider()
                                _va_col1, _va_col2 = st.columns([2, 3])
                                with _va_col1:
                                    if st.button("📋 비디오 스토리보드에 반영", type="primary", key="apply_infographic_bg_videos", use_container_width=True):
                                        _vsynced = _apply_infographic_files_to_storyboard(
                                            project_path, _vid_preview_dir, _vid_preview_files, "video"
                                        )
                                        if _vsynced > 0:
                                            st.success(f"✅ {_vsynced}개 씬 비디오 스토리보드에 반영 완료!")
                                            st.rerun()
                                        else:
                                            st.warning("매칭된 씬이 없습니다.")
                                with _va_col2:
                                    st.caption(f"🎬 {len(_vid_preview_files)}개 비디오 → scenes.json 반영")

                else:
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
                            "씬 범위 (순서)",
                            min_value=1,
                            max_value=scene_count,
                            value=(1, min(5, scene_count)),
                            key="video_range_slider"
                        )
                        selected_video_indices = list(range(video_range[0] - 1, video_range[1]))
                    elif video_gen_mode == "개별":
                        video_scene_options = [f"씬 {scene.scene_id}" for scene in infographic_data.scenes]
                        selected_video_labels = st.multiselect(
                            "녹화할 씬 선택",
                            options=video_scene_options,
                            default=[video_scene_options[0]] if video_scene_options else [],
                            key="video_scene_multiselect"
                        )
                        _vid_scene_id_to_idx = {scene.scene_id: i for i, scene in enumerate(infographic_data.scenes)}
                        selected_video_indices = [
                            _vid_scene_id_to_idx[int(s.replace("씬 ", ""))]
                            for s in selected_video_labels
                            if int(s.replace("씬 ", "")) in _vid_scene_id_to_idx
                        ]
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
                    _selected_vid_scene_ids = [scene_id_map.get(idx, idx + 1) for idx in selected_video_indices]
                    st.info(f"📊 선택: {len(selected_video_indices)}개 씬 (씬 {', '.join(str(s) for s in _selected_vid_scene_ids[:8])}{'...' if len(_selected_vid_scene_ids) > 8 else ''}) | {mode_emoji} {video_quality_label.split()[0]} | 📁 ~{est_size:.1f}MB")

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

                                with get_video_recorder(
                                    output_dir=output_dir,
                                    quality=video_quality,
                                    output_width=output_width,
                                    output_height=output_height
                                ) as recorder:
                                    # 전체/선택 모두 동일한 메서드 사용
                                    scene_list = selected_video_indices if video_gen_mode != "전체" else list(range(scene_count))

                                    # ============================================================
                                    # ✅ 핵심: 수정된 HTML 우선 사용 (배경 합성 포함)
                                    # ============================================================
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
                                        fade_effect=not is_animation_mode,
                                        scene_id_map=scene_id_map,
                                        progress_callback=video_progress
                                    )

                                progress_bar.progress(1.0)
                                status_text.text(f"완료! {len(results)}개 동영상 생성")

                                visual_manager.set_infographic_data(infographic_data)

                                st.success(f"✅ {len(results)}개 동영상 녹화 완료! 미리보기를 확인하세요.")

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
                            # ── 동영상 선택/삭제 컨트롤 ──
                            _mvid_sel_key = "infographic_main_vid_selected"
                            if _mvid_sel_key not in st.session_state:
                                st.session_state[_mvid_sel_key] = set()

                            _mvsel = len(st.session_state[_mvid_sel_key])
                            _mv_c1, _mv_c2, _mv_c3, _mv_c4 = st.columns([1, 1, 2, 1])
                            with _mv_c1:
                                if st.button("☑️ 전체 선택", key="mvid_sel_all", use_container_width=True):
                                    st.session_state[_mvid_sel_key] = set(video_files)
                                    st.rerun()
                            with _mv_c2:
                                if st.button("⬜ 전체 해제", key="mvid_desel_all", use_container_width=True):
                                    st.session_state[_mvid_sel_key] = set()
                                    st.rerun()
                            with _mv_c3:
                                if _mvsel > 0:
                                    if st.button(f"🗑️ 선택 삭제 ({_mvsel}개)", key="mvid_del_selected", type="primary", use_container_width=True):
                                        _mdel = 0
                                        for _mdf in list(st.session_state[_mvid_sel_key]):
                                            _mdp = os.path.join(videos_dir, _mdf)
                                            if os.path.exists(_mdp):
                                                try:
                                                    os.remove(_mdp)
                                                    _mdel += 1
                                                except OSError:
                                                    pass
                                        st.session_state[_mvid_sel_key] = set()
                                        st.success(f"✅ {_mdel}개 동영상 삭제 완료")
                                        st.rerun()
                                else:
                                    st.caption(f"선택: 0 / {len(video_files)}")
                            with _mv_c4:
                                if st.button("🗑️ 전체 삭제", key="mvid_del_all", use_container_width=True):
                                    st.session_state["_confirm_del_all_mvid"] = True

                            if st.session_state.get("_confirm_del_all_mvid"):
                                st.warning(f"⚠️ 모든 동영상 {len(video_files)}개를 삭제하시겠습니까?")
                                _mdc1, _mdc2, _mdc3 = st.columns([1, 1, 3])
                                with _mdc1:
                                    if st.button("✅ 삭제 확인", key="mvid_del_all_confirm", type="primary", use_container_width=True):
                                        _mdel = 0
                                        for _mdf in video_files:
                                            try:
                                                os.remove(os.path.join(videos_dir, _mdf))
                                                _mdel += 1
                                            except OSError:
                                                pass
                                        st.session_state[_mvid_sel_key] = set()
                                        st.session_state["_confirm_del_all_mvid"] = False
                                        st.success(f"✅ {_mdel}개 동영상 삭제 완료")
                                        st.rerun()
                                with _mdc2:
                                    if st.button("❌ 취소", key="mvid_del_all_cancel", use_container_width=True):
                                        st.session_state["_confirm_del_all_mvid"] = False
                                        st.rerun()

                            # 그리드 레이아웃 (5열, 체크박스 포함)
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
                                        # 체크박스
                                        _mv_is_sel = video_file in st.session_state[_mvid_sel_key]
                                        _mv_cb = st.checkbox(
                                            video_file,
                                            value=_mv_is_sel,
                                            key=f"mvid_cb_{video_idx}",
                                            label_visibility="collapsed"
                                        )
                                        if _mv_cb and video_file not in st.session_state[_mvid_sel_key]:
                                            st.session_state[_mvid_sel_key].add(video_file)
                                        elif not _mv_cb and video_file in st.session_state[_mvid_sel_key]:
                                            st.session_state[_mvid_sel_key].discard(video_file)

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
                                            st.markdown(
                                                '<div style="background:#f0f0f0;border-radius:8px;padding:15px;text-align:center;height:60px;display:flex;align-items:center;justify-content:center;"><span style="font-size:20px;">🎬</span></div>',
                                                unsafe_allow_html=True
                                            )

                                        # 씬 번호 및 파일 정보
                                        file_size = os.path.getsize(video_path) / (1024 * 1024)
                                        st.caption(f"씬 {scene_num} ({file_size:.1f}MB)")

                                        # 버튼 행
                                        btn_col1, btn_col2 = st.columns(2)

                                        with btn_col1:
                                            if st.button("▶️", key=f"play_video_{video_idx}", help="미리보기"):
                                                st.session_state[f'show_video_{video_idx}'] = True

                                        with btn_col2:
                                            if st.button("📂", key=f"open_folder_{video_idx}", help="폴더 열기"):
                                                open_file_location(video_path)

                                        # 비디오 플레이어 (토글)
                                        if st.session_state.get(f'show_video_{video_idx}', False):
                                            st.video(video_path)
                                            if st.button("닫기", key=f"close_video_{video_idx}"):
                                                st.session_state[f'show_video_{video_idx}'] = False
                                                st.rerun()

                            # 폴더/병합 버튼
                            st.divider()
                            folder_col1, folder_col2 = st.columns([1, 1])

                            with folder_col1:
                                if st.button("📂 동영상 폴더 열기", use_container_width=True, key="open_videos_folder"):
                                    open_folder(videos_dir)

                            with folder_col2:
                                merged_path = os.path.join(videos_dir, "merged_all.mp4")
                                if os.path.exists(merged_path):
                                    merged_size = os.path.getsize(merged_path) / (1024 * 1024)
                                    st.success(f"✅ 병합 ({merged_size:.1f}MB)")
                                    if st.button("▶️ 병합 영상", key="play_merged"):
                                        st.video(merged_path)
                                else:
                                    st.caption("병합 파일 없음")

                    # 동영상 스토리보드 반영 버튼
                    if video_files:
                        st.divider()
                        vid_apply_col1, vid_apply_col2 = st.columns([2, 3])
                        with vid_apply_col1:
                            if st.button("📋 스토리보드에 반영", type="primary", key="apply_infographic_videos", use_container_width=True):
                                synced = _apply_infographic_files_to_storyboard(
                                    project_path, videos_dir, video_files, "video"
                                )
                                if synced > 0:
                                    st.success(f"✅ {synced}개 씬 스토리보드에 반영 완료!")
                                    st.rerun()
                                else:
                                    st.warning("매칭된 씬이 없습니다. 파일명에 씬 번호가 포함되어야 합니다.")
                        with vid_apply_col2:
                            st.caption(f"🎬 {len(video_files)}개 동영상 → scenes.json 반영")

            # (섹션 4 "씬별 시각 자료 선택", 섹션 5 "내보내기 요약" 제거됨)
            # 인포그래픽 반영은 위의 "스토리보드에 반영" 버튼으로 처리

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
        # v3.35: 캐릭터 자동 연동 (페이지 로드 시 한 번 실행, 에러 핸들링 강화)
        # ═══════════════════════════════════════════════════════════════
        if NANO_COMPOSITE_AVAILABLE and auto_link_characters_to_scenes:
            # 세션 캐시 키 (프로젝트 + 캐시 버전별)
            auto_link_cache_key = f"_char_auto_linked_{str(project_path)}_{st.session_state.get('image_cache_version', 0)}"

            if auto_link_cache_key not in st.session_state:
                # 자동 연동 실행 (v3.35: 에러 핸들링 추가)
                try:
                    link_result = auto_link_characters_to_scenes(scenes, str(project_path))

                    # 에러 발생 시 경고 표시
                    if link_result.get("errors", 0) > 0:
                        print(f"[스토리보드] ⚠️ 캐릭터 연동 중 {link_result['errors']}개 씬에서 오류 발생")

                except Exception as e:
                    print(f"[스토리보드] ❌ 캐릭터 자동 연동 오류: {e}")
                    import traceback
                    traceback.print_exc()
                    link_result = {"linked_count": 0, "errors": 1}

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

                # ⭐ v2.0: 최종 대체 미디어 기준 내보내기 (워크플로우 결과 반영)
                # 캐싱: 매 렌더링 시 전체 씬 스캔 방지
                export_cache_key = f"export_media_list_{str(project_path)}_{st.session_state.get('image_cache_version', 0)}"
                if export_cache_key not in st.session_state:
                    export_media_list = []
                    for s in scenes:
                        scene_id = s.get("scene_id") or s.get("scene_num")
                        if not scene_id:
                            continue

                        _found = False

                        # ⭐ v2.0: 비디오 우선순위 체크 (여러 비디오 필드 확인)
                        _video_fields = [
                            "infographic_video_path",   # 인포그래픽 비디오
                            "final_video_path",         # 최종 비디오
                            "background_video",         # 실사 배경 비디오
                        ]
                        for _vf in _video_fields:
                            _vp = s.get(_vf, "")
                            if _vp and Path(_vp).exists():
                                export_media_list.append({
                                    "scene_id": scene_id,
                                    "media_type": "video",
                                    "path": _vp,
                                    "ext": Path(_vp).suffix.lower()
                                })
                                _found = True
                                break

                        if not _found:
                            # ⭐ v2.0: 이미지 - get_latest_scene_image()로 최종 대체 이미지 검색
                            # 우선순위: replaced > infographic > real > composited > nano_composite > korean_text > scenes > backgrounds
                            img_path = None
                            if TIMELINE_COMPOSITE_AVAILABLE:
                                img_path = get_latest_scene_image(s, str(project_path))

                            # 폴백: image_map 패턴 매칭 (기존 방식)
                            if not img_path:
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
                    # 실제 씬 ID 범위 계산 (인덱스가 아닌 실제 scene_id)
                    if paginated_scenes:
                        first_scene_id = paginated_scenes[0].get('scene_id', start_idx + 1)
                        last_scene_id = paginated_scenes[-1].get('scene_id', end_idx)
                    else:
                        first_scene_id = start_idx + 1
                        last_scene_id = end_idx

                    st.markdown(
                        f"<div style='text-align:center; padding:8px;'>"
                        f"<b>페이지 {current_page + 1} / {total_pages}</b><br>"
                        f"<small>씬 {first_scene_id} ~ {last_scene_id} (총 {len(filtered_scenes)}개)</small>"
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
                    # 실제 씬 ID 범위를 사용하여 페이지 옵션 생성 (인덱스 기반이 아닌 실제 scene_id)
                    page_id_ranges = get_page_scene_id_ranges(filtered_scenes, SCENES_PER_PAGE)
                    page_options = [
                        f"페이지 {p+1} (씬 {page_id_ranges[p][0]}~{page_id_ranges[p][1]})"
                        if p < len(page_id_ranges) else f"페이지 {p+1}"
                        for p in range(total_pages)
                    ]

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
                                    # 비디오 썸네일을 이미지와 동일한 크기(300px)로 표시
                                    video_thumb_shown = False

                                    # 썸네일 소스 1: composited_image_path (Step3 썸네일)
                                    thumb_candidate = scene.get('composited_image_path', '')
                                    if (thumb_candidate
                                            and not thumb_candidate.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))
                                            and Path(thumb_candidate).exists()):
                                        render_lightbox_image(str(thumb_candidate), width=300, key=f"storyboard_vid_thumb_{i}_{scene_id}")
                                        video_thumb_shown = True

                                    # 썸네일 소스 2: video_thumbnails 폴더
                                    if not video_thumb_shown:
                                        vid_thumb_path = project_path / "images" / "video_thumbnails" / f"scene_{scene_id:03d}_video_thumb.png"
                                        if vid_thumb_path.exists():
                                            render_lightbox_image(str(vid_thumb_path), width=300, key=f"storyboard_vid_thumb_{i}_{scene_id}")
                                            video_thumb_shown = True

                                    # 썸네일 소스 3: extract_video_thumbnail 동적 생성
                                    if not video_thumb_shown and TIMELINE_COMPOSITE_AVAILABLE:
                                        try:
                                            extracted = extract_video_thumbnail(str(video_path), scene_id, str(project_path))
                                            if extracted and Path(extracted).exists():
                                                render_lightbox_image(extracted, width=300, key=f"storyboard_vid_thumb_{i}_{scene_id}")
                                                video_thumb_shown = True
                                        except Exception:
                                            pass

                                    # 폴백: 비디오 아이콘 플레이스홀더
                                    if not video_thumb_shown:
                                        st.markdown(
                                            '<div style="width:300px;height:169px;background:#1a1a2e;'
                                            'display:flex;align-items:center;justify-content:center;'
                                            'border-radius:8px;"><span style="font-size:48px;">🎬</span></div>',
                                            unsafe_allow_html=True
                                        )

                                    st.caption(f"🎬 비디오: {video_path.name}")

                                    # 비디오 재생 (접이식)
                                    with st.expander("▶️ 비디오 재생"):
                                        st.video(str(video_path))

                                    # 비디오 관리 버튼
                                    vid_btn_cols = st.columns(4)
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
                                        try:
                                            vid_size = video_path.stat().st_size
                                            if vid_size > 50 * 1024 * 1024:
                                                st.caption(f"📥 {vid_size // (1024*1024)}MB")
                                            else:
                                                import base64 as _b64
                                                with open(video_path, "rb") as vf:
                                                    _vb64 = _b64.b64encode(vf.read()).decode()
                                                _vfn = f"scene_{str(scene_id).zfill(3)}_video{video_path.suffix}"
                                                st.markdown(
                                                    f'<a href="data:video/mp4;base64,{_vb64}" download="{_vfn}" '
                                                    f'style="text-decoration:none;font-size:18px;" title="비디오 다운로드">📥</a>',
                                                    unsafe_allow_html=True
                                                )
                                        except Exception:
                                            st.caption("📥")
                                    with vid_btn_cols[3]:
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
                                is_composite_image = False

                                # ⭐ v3.36: get_latest_scene_image()로 통합 (타임라인 뷰와 동일한 우선순위)
                                # 우선순위: real_image_path → composited_image_path → composite_image_path
                                #          → nano_composite → composited 폴더 → composite_realshot 폴더
                                #          → realshot 폴더 → video_thumbnails → scenes → backgrounds
                                if TIMELINE_COMPOSITE_AVAILABLE:
                                    latest_path = get_latest_scene_image(scene, str(project_path))
                                    if latest_path:
                                        scene_image = Path(latest_path)
                                        # 합성/실사 대체 이미지 여부 판단
                                        path_lower = str(latest_path).lower()
                                        is_composite_image = any(kw in path_lower for kw in ['compos', 'realshot', 'real_image'])

                                # 폴백 1: 파일명으로 매칭
                                if not scene_image and filename and filename.replace(".png", "") in image_map:
                                    scene_image = image_map[filename.replace(".png", "")]

                                # 폴백 2: 씬 번호 패턴 매칭 (image_map 기반)
                                if not scene_image:
                                    scene_num_str = f"{scene_id:03d}"
                                    real_scene_key = f"real_scene_{scene_num_str}"
                                    if real_scene_key in image_map:
                                        scene_image = image_map[real_scene_key]
                                    else:
                                        for img_name, img_path in image_map.items():
                                            if (img_name.startswith(f"real_scene_{scene_num_str}") or
                                                f"_{scene_num_str}" in img_name or
                                                f"_seg_{scene_num_str}" in img_name or
                                                img_name.startswith(f"{scene_num_str}_") or
                                                img_name.startswith(f"{scene_num_str}.")):
                                                scene_image = img_path
                                                break

                                # 폴백 3: get_scene_image_path() (씬 ID 기반 정확 매칭)
                                if not scene_image:
                                    scene_image_path = get_scene_image_path(scene, str(project_path))
                                    if scene_image_path and Path(scene_image_path).exists():
                                        scene_image = Path(scene_image_path)

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

                                    # 6. 🆕 v1.2: 이미지 다운로드 링크 (rerun 방지)
                                    with img_btn_cols[5]:
                                        try:
                                            import base64 as _b64
                                            with open(scene_image, "rb") as img_file:
                                                _ib64 = _b64.b64encode(img_file.read()).decode()
                                            dl_filename = f"scene_{str(scene_id).zfill(3)}{scene_image.suffix}"
                                            mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
                                            dl_mime = mime_map.get(scene_image.suffix.lower(), "image/png")
                                            st.markdown(
                                                f'<a href="data:{dl_mime};base64,{_ib64}" download="{dl_filename}" '
                                                f'style="text-decoration:none;font-size:18px;" title="이미지 다운로드">📥</a>',
                                                unsafe_allow_html=True
                                            )
                                        except Exception:
                                            st.caption("📥")

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
                    # v3.35: 씬 ID 기반 이미지 확인 (인덱스 기반 매칭 제거)
                    scene_has_image = get_scene_image_path(scene, str(project_path)) is not None
                    row = {
                        "씬": scene.get("scene_id", i + 1),
                        "시간(초)": scene.get("duration_estimate", 10),
                        "스크립트": scene.get("script_text", "")[:100] + "...",
                        "캐릭터": safe_join_characters(scene.get("characters", [])),
                        "분위기": scene.get("mood", ""),
                        "이미지": "O" if scene_has_image else "X"
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

                    # 타임라인 드래그앤드롭: 이미지 직접 대체 (합성 없음)
                    if TIMELINE_COMPOSITE_AVAILABLE:
                        st.caption("💡 이미지를 드래그&드롭하면 즉시 대체됩니다.")

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

                            # ⭐ 드래그 앤 드롭 이미지 대체 (v2.0 - 무한 루프 수정)
                            if TIMELINE_COMPOSITE_AVAILABLE:
                                # 동적 키: 처리 후 카운터 증가 → file_uploader 초기화
                                _drop_count = st.session_state.get(f"tl_drop_count_{scene_id}", 0)
                                uploaded_file = st.file_uploader(
                                    "이미지/비디오",
                                    type=['png', 'jpg', 'jpeg', 'webp', 'mp4', 'mov'],
                                    key=f"tl_drop_{idx}_{scene_id}_{_drop_count}",
                                    label_visibility="collapsed"
                                )

                                if uploaded_file:
                                    with st.spinner(f"씬 {scene_id} 이미지 대체 중..."):
                                        file_ext = uploaded_file.name.split('.')[-1].lower()
                                        is_video = file_ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']

                                        # 저장 디렉토리
                                        replaced_dir = project_path / 'images' / 'replaced'
                                        os.makedirs(str(replaced_dir), exist_ok=True)

                                        if is_video:
                                            # 비디오: 파일 저장 + 썸네일을 대체 이미지로 사용
                                            save_realshot_file(uploaded_file, scene_id, str(project_path))
                                            thumb_path = extract_video_thumbnail(uploaded_file, scene_id, str(project_path))
                                            if thumb_path and os.path.exists(thumb_path):
                                                import shutil
                                                save_path = str(replaced_dir / f"scene_{scene_id:03d}_replaced.png")
                                                shutil.copy2(thumb_path, save_path)
                                            else:
                                                st.error("비디오 썸네일 추출 실패")
                                                save_path = None
                                        else:
                                            # 이미지: 직접 저장 (합성 없음!)
                                            ext = f".{file_ext}" if file_ext in ['png', 'jpg', 'jpeg', 'webp'] else ".png"
                                            save_path = str(replaced_dir / f"scene_{scene_id:03d}_replaced{ext}")
                                            with open(save_path, "wb") as _f:
                                                _f.write(uploaded_file.getbuffer())

                                        if save_path and os.path.exists(save_path):
                                            if bundle_replace_mode and bundle_id:
                                                # 묶음: 동일 이미지를 모든 묶음 씬에 복사
                                                import shutil
                                                replaced_count = 0
                                                for bs in filtered_scenes:
                                                    if bs.get('bundle_id') == bundle_id:
                                                        bs_id = bs.get('scene_id') or bs.get('scene_number') or bs.get('id', 0)
                                                        bs_path = str(replaced_dir / f"scene_{bs_id:03d}_replaced{ext if not is_video else '.png'}")
                                                        if bs_id != scene_id:
                                                            shutil.copy2(save_path, bs_path)
                                                        _update_scene_image_in_json(project_path, bs_id, bs_path)
                                                        replaced_count += 1
                                                invalidate_all_image_caches()
                                                st.success(f"✅ 묶음 {bundle_id} 이미지 대체 완료! ({replaced_count}개 씬)")
                                            else:
                                                # 단일 씬 대체
                                                _update_scene_image_in_json(project_path, scene_id, save_path)
                                                invalidate_all_image_caches()
                                                st.success(f"✅ 씬 {scene_id} 이미지 대체 완료!")
                                        else:
                                            st.error("이미지 저장 실패")

                                    # 키 변경 → rerun 후 file_uploader가 새 키로 초기화됨 (무한 루프 방지)
                                    st.session_state[f"tl_drop_count_{scene_id}"] = _drop_count + 1
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
