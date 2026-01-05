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
    print(f"[스토리보드] 인포그래픽 모듈 로드 실패: {e}")

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
        VIDEO_API_AVAILABLE
    )
    from utils.video_api import ALL_MODELS, PLATFORM_CONFIGS
except ImportError as e:
    VIDEO_API_AVAILABLE = False
    print(f"[스토리보드] Video API 모듈 로드 실패: {e}")

# Settings Manager (영구 저장)
from utils.settings_manager import (
    get_setting,
    set_setting,
    persistent_selectbox,
    render_settings_management_ui
)

import subprocess


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
                    default_idx = (
                        duration_options.index(model_config.default_duration)
                        if model_config.default_duration in duration_options else 0
                    )
                else:
                    duration_options = [5]
                    default_idx = 0
            else:
                duration_options = [5]
                default_idx = 0

            selected_duration = persistent_selectbox(
                "⏱️ 비디오 길이",
                options=duration_options,
                page=VIDEO_PAGE_ID,
                setting_key="duration",
                default_index=default_idx,
                format_func=lambda x: f"{x}초"
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

                if result.get("success"):
                    st.success(f"✅ 비디오 생성 완료!")
                    st.video(result.get("video_path"))

                    # 다운로드 버튼
                    video_path = result.get("video_path")
                    if video_path and os.path.exists(video_path):
                        with open(video_path, "rb") as f:
                            st.download_button(
                                "📥 비디오 다운로드",
                                data=f.read(),
                                file_name=os.path.basename(video_path),
                                mime="video/mp4"
                            )
                else:
                    st.error(f"❌ 비디오 생성 실패: {result.get('error', 'Unknown error')}")

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

                with cols[col_idx]:
                    is_selected = st.checkbox(
                        f"씬 {scene_id}",
                        value=st.session_state.get(f"ai_video_select_{scene_id}", False),
                        key=f"ai_video_cb_{scene_id}"
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
        progress_bar = st.progress(0)
        status_text = st.empty()

        def progress_callback(current, total, message):
            progress_bar.progress((current + 1) / total)
            status_text.text(message)

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
        status_text.text("완료!")

        # 결과 표시
        success_count = sum(1 for r in results if r.get("success"))
        fail_count = len(results) - success_count
        total_cost = sum(r.get("cost_usd", 0) for r in results if r.get("success"))

        if success_count > 0:
            st.success(f"✅ {success_count}개 비디오 생성 성공! (총 비용: ${total_cost:.2f})")

        if fail_count > 0:
            st.error(f"❌ {fail_count}개 비디오 생성 실패")

            with st.expander("실패 상세"):
                for r in results:
                    if not r.get("success"):
                        st.markdown(f"- 씬 {r.get('scene_id')}: {r.get('error')}")

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
            if hasattr(st, 'cache_data'):
                # 필요시 캐시 클리어 (옵션)
                pass
        except Exception:
            pass

# 캐시 초기화 호출
init_media_cache()

# ============================================================
# 이미지 로딩 캐시 (중복 로드 방지)
# ============================================================
@st.cache_data(ttl=60, show_spinner=False)
def load_image_files_cached(scenes_dir: str, content_dir: str) -> tuple:
    """이미지 파일 목록 캐싱 (중복 로드 방지)"""
    image_files = []

    scenes_path = Path(scenes_dir)
    content_path = Path(content_dir)

    if scenes_path.exists():
        image_files.extend(sorted(scenes_path.glob("*.png")))
    if content_path.exists():
        image_files.extend(sorted(content_path.glob("*.png")))

    # 중복 제거 (같은 이름 파일이 있을 경우 scenes 우선)
    seen_names = set()
    unique_images = []
    for img in image_files:
        if img.stem not in seen_names:
            unique_images.append(str(img))  # 문자열로 변환 (캐싱 안정성)
            seen_names.add(img.stem)

    image_map = {Path(img).stem: img for img in unique_images}

    return tuple(unique_images), image_map


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
        st.subheader("📊 인포그래픽 동영상 통합")

        st.info("""
        💡 **인포그래픽 동영상 통합 모드 v2**
        - **UI 표시**: 인포그래픽 첫 프레임 이미지 (썸네일)
        - **내보내기**: CSS 애니메이션을 녹화한 MP4 동영상
        - **캐릭터 합성**: 동영상 전체에 캐릭터 PNG 오버레이
        """)

        # 선택 매니저 초기화
        if "visual_manager" not in st.session_state:
            st.session_state.visual_manager = VisualSelectionManager(str(project_path))
        visual_manager = st.session_state.visual_manager

        # 인포그래픽 데이터 상태
        infographic_data = visual_manager.get_infographic_data()

        # 렌더링 환경 상태 확인 (Selenium 기반)
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

            # === 2.5. 배경 이미지 대체 ===
            render_background_replacement_section(infographic_data, project_path, visual_manager)

            st.divider()

            # === 2.6. AI 비디오 생성 ===
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
                # AI 이미지 디렉토리
                ai_images_dir = project_path / "images" / "scenes"
                ai_images = list(ai_images_dir.glob("*.png")) if ai_images_dir.exists() else []

                # 인포그래픽 썸네일 디렉토리
                infographic_thumbs_dir = project_path / "infographics" / "thumbnails"
                infographic_thumbs = list(infographic_thumbs_dir.glob("*.png")) if infographic_thumbs_dir.exists() else []

                # 인포그래픽 동영상 디렉토리
                infographic_videos_dir = project_path / "infographics" / "videos"
                infographic_videos = list(infographic_videos_dir.glob("infographic_scene_*.mp4")) if infographic_videos_dir.exists() else []

                # 합성 동영상 디렉토리
                composites_dir = project_path / "infographics" / "composites"
                composite_videos = list(composites_dir.glob("composite_scene_*.mp4")) if composites_dir.exists() else []

                # 선택 초기화
                visual_manager.initialize_selections_from_scenes(
                    [s.get("scene_id", i+1) for i, s in enumerate(scenes_for_selection)]
                )

                # 파일 시스템 기반 동영상 경로 동기화
                for i, scene in enumerate(scenes_for_selection):
                    scene_id = scene.get("scene_id", i + 1)
                    selection = visual_manager.state.selections.get(scene_id)

                    if selection:
                        # 인포그래픽 동영상 경로 동기화
                        video_path = infographic_videos_dir / f"infographic_scene_{scene_id:03d}.mp4"
                        if video_path.exists():
                            selection.infographic_video = str(video_path)

                        # 합성 동영상 경로 동기화
                        composite_path = composites_dir / f"composite_scene_{scene_id:03d}.mp4"
                        if composite_path.exists():
                            selection.composite_video = str(composite_path)

                # 통계 표시
                stats = visual_manager.get_statistics()
                stat_col1, stat_col2, stat_col3, stat_col4, stat_col5, stat_col6 = st.columns(6)
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

                with dl_col1:
                    if scene_images:
                        from utils.download_manager import SceneDownloadManager
                        manager = SceneDownloadManager(video_path=str(project_path))
                        zip_buffer = manager.create_zip_buffer(images=scene_images)
                        st.download_button(
                            label=f"🖼️ 이미지 다운로드 ({len(scene_images)}개)",
                            data=zip_buffer,
                            file_name=manager.get_zip_filename("scene_images"),
                            mime="application/zip",
                            key="sb_dl_images",
                            use_container_width=True
                        )
                    else:
                        st.button("🖼️ 이미지 없음", disabled=True, use_container_width=True)

                with dl_col2:
                    if scene_videos:
                        from utils.download_manager import SceneDownloadManager
                        manager = SceneDownloadManager(video_path=str(project_path))
                        zip_buffer = manager.create_zip_buffer(videos=scene_videos)
                        st.download_button(
                            label=f"🎬 동영상 다운로드 ({len(scene_videos)}개)",
                            data=zip_buffer,
                            file_name=manager.get_zip_filename("scene_videos"),
                            mime="application/zip",
                            key="sb_dl_videos",
                            use_container_width=True
                        )
                    else:
                        st.button("🎬 동영상 없음", disabled=True, use_container_width=True)

                with dl_col3:
                    if scene_images or scene_videos:
                        from utils.download_manager import SceneDownloadManager
                        manager = SceneDownloadManager(video_path=str(project_path))
                        zip_buffer = manager.create_zip_buffer(
                            images=scene_images if scene_images else None,
                            videos=scene_videos if scene_videos else None
                        )
                        total_items = len(scene_images) + len(scene_videos)
                        st.download_button(
                            label=f"📦 전체 다운로드 ({total_items}개)",
                            data=zip_buffer,
                            file_name=manager.get_zip_filename("storyboard_assets"),
                            mime="application/zip",
                            key="sb_dl_all_zip",
                            type="primary",
                            use_container_width=True
                        )
                    else:
                        st.button("📦 자료 없음", disabled=True, use_container_width=True)

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

                # 씬별 선택 UI
                for i, scene in enumerate(scenes_for_selection):
                    scene_id = scene.get("scene_id", i + 1)
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
                                key=f"visual_type_{scene_id}",
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
                                if not ai_img and i < len(ai_images):
                                    ai_img = ai_images[i]

                                if ai_img and ai_img.exists():
                                    st.image(str(ai_img), width=120)
                                    if st.button("🔍", key=f"zoom_ai_{scene_id}", help="확대"):
                                        st.session_state[f"zoom_ai_{scene_id}"] = True
                                    if st.session_state.get(f"zoom_ai_{scene_id}", False):
                                        from utils.image_viewer import show_image_modal
                                        show_image_modal(str(ai_img), scene_id, None, f"씬 {scene_id} AI 이미지")
                                        st.session_state[f"zoom_ai_{scene_id}"] = False
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
                                    if st.button("🔍", key=f"zoom_info_{scene_id}", help="확대"):
                                        st.session_state[f"zoom_info_{scene_id}"] = True
                                    if st.session_state.get(f"zoom_info_{scene_id}", False):
                                        from utils.image_viewer import show_image_modal
                                        show_image_modal(info_thumb, scene_id, None, f"씬 {scene_id} 인포그래픽")
                                        st.session_state[f"zoom_info_{scene_id}"] = False
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
                                    if st.button("🔍", key=f"zoom_comp_{scene_id}", help="확대"):
                                        st.session_state[f"zoom_comp_{scene_id}"] = True
                                    if st.session_state.get(f"zoom_comp_{scene_id}", False):
                                        from utils.image_viewer import show_image_modal
                                        show_image_modal(comp_thumb, scene_id, None, f"씬 {scene_id} 합성")
                                        st.session_state[f"zoom_comp_{scene_id}"] = False
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
        show_images = st.checkbox("이미지 표시", value=True)
        show_script = st.checkbox("스크립트 표시", value=True)
        show_direction = st.checkbox("연출가이드 표시", value=True)
        show_characters = st.checkbox("캐릭터 표시", value=True)
        show_prompt = st.checkbox("프롬프트 표시", value=False)
        show_video_prompt = st.checkbox("🎬 비디오 프롬프트 표시", value=True)

    # 씬 데이터 로드
    scenes_path = project_path / "analysis" / "scenes.json"
    # 이미지 디렉토리 (scenes 우선, content 폴백)
    scenes_images_dir = project_path / "images" / "scenes"
    content_images_dir = project_path / "images" / "content"
    audio_dir = project_path / "audio"

    # 이미지 디렉토리 선택 (scenes에 이미지가 있으면 우선, 없으면 content)
    if scenes_images_dir.exists() and any(scenes_images_dir.glob("*.png")):
        images_dir = scenes_images_dir
        print(f"[스토리보드] scenes 폴더 사용: {scenes_images_dir}")
    else:
        images_dir = content_images_dir
        print(f"[스토리보드] content 폴더 사용: {content_images_dir}")

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

        if not scenes:
            st.warning("씬 데이터가 비어있습니다.")
        else:
            # === 이미지 자동 동기화 섹션 ===
            st.subheader("🔄 이미지 자동 동기화")

            matcher = ImageSceneMatcher(project_path)
            summary = matcher.get_matching_summary(scenes)

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
                            help="생성된 이미지를 씬에 자동으로 매칭합니다"):
                    with st.spinner("이미지 매칭 중..."):
                        sync_result = auto_sync_images_to_storyboard(
                            project_path, scenes, copy_to_scenes=True
                        )

                        copy_info = sync_result.get("copy_results", {})
                        if copy_info:
                            st.success(f"✅ 동기화 완료! 복사: {copy_info.get('copied', 0)}개, 스킵: {copy_info.get('skipped', 0)}개")
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
            image_files_tuple, image_map = load_image_files_cached(
                str(scenes_images_dir), str(content_images_dir)
            )
            image_files = [Path(p) for p in image_files_tuple]  # Path 객체로 변환
            print(f"[스토리보드] 총 {len(image_files)}개 이미지 로드됨 (캐싱)")

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
            # 실사 이미지 관리 섹션
            # ============================================================
            with st.expander("🖼️ 실사 이미지 관리", expanded=False):
                st.caption("AI 생성 이미지를 실사 이미지로 대체하고 관리할 수 있습니다.")

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
                        for img in image_files:
                            invalidate_image_cache(str(img))
                        st.toast(f"{len(image_files)}개 이미지 새로고침됨")
                        st.rerun()

                # 이미지 폴더 열기
                with batch_col4:
                    if st.button("📂 이미지 폴더", use_container_width=True, help="이미지 폴더를 탐색기에서 엽니다"):
                        open_folder(str(scenes_images_dir))

                # 백업 상태 표시
                backup_count = sum(1 for img in image_files if has_backup(img))
                if backup_count > 0:
                    st.info(f"💾 백업된 이미지: {backup_count}개 / {len(image_files)}개")

            # ============================================================
            # 씬 선택 및 다운로드 섹션
            # ============================================================
            with st.expander("🎯 씬 선택 및 다운로드", expanded=False):
                selector = SceneSelector(len(scenes), key_prefix="storyboard_download")
                selected_ids = selector.render(scenes)

                if selected_ids:
                    st.divider()
                    downloader = StoryboardDownloader(str(project_path), key_prefix="sb_main_dl")
                    downloader.render_download_ui(scenes, selected_ids)
                else:
                    st.info("다운로드할 씬을 선택하세요.")

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
                paginated_scenes, start_idx, end_idx, total_pages = get_paginated_scenes(
                    scenes, current_page, SCENES_PER_PAGE
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
                        f"<small>씬 {start_idx + 1} ~ {end_idx} (총 {len(scenes)}개)</small>"
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
                    page_options = [f"페이지 {p+1} (씬 {p*SCENES_PER_PAGE+1}~{min((p+1)*SCENES_PER_PAGE, len(scenes))})" for p in range(total_pages)]
                    selected_page = st.selectbox(
                        "빠른 이동",
                        options=range(total_pages),
                        format_func=lambda x: page_options[x],
                        index=current_page,
                        key="quick_page_select",
                        label_visibility="collapsed"
                    )
                    if selected_page != current_page:
                        st.session_state["storyboard_page"] = selected_page
                        st.rerun()

                with quick_nav_cols[1]:
                    if st.button("🔄 이미지 캐시 새로고침", key="refresh_image_cache", help="이미지 목록 캐시 삭제"):
                        load_image_files_cached.clear()
                        st.toast("이미지 캐시 새로고침됨")
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
                    image_prompt = scene.get("image_prompt_en", "")
                    duration = scene.get("duration_estimate", 10)
                    filename = scene.get("filename", "")

                    # 씬 컨테이너
                    with st.container():
                        cols = st.columns([1, 3, 2])

                        with cols[0]:
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
                                st.markdown(f"**👤 등장 캐릭터:** {', '.join(characters)}")

                            # 프롬프트
                            if show_prompt and image_prompt:
                                st.markdown("**🎨 프롬프트**")
                                st.code(image_prompt[:200] + "..." if len(image_prompt) > 200 else image_prompt)

                            # 🎬 비디오 프롬프트 (NEW!)
                            if show_video_prompt:
                                video_prompt_char = get_video_prompt_for_scene(scene, "character")
                                video_prompt_full = get_video_prompt_for_scene(scene, "full")

                                if video_prompt_char or video_prompt_full:
                                    st.markdown("**🎬 비디오 프롬프트**")
                                    with st.container(border=True):
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

                        with cols[2]:
                            # 이미지 표시
                            if show_images:
                                scene_image = None

                                # 파일명으로 매칭
                                if filename and filename.replace(".png", "") in image_map:
                                    scene_image = image_map[filename.replace(".png", "")]

                                # 씬 번호로 매칭
                                if not scene_image:
                                    for img_name, img_path in image_map.items():
                                        if f"_{scene_id:03d}" in img_name or f"_seg_{scene_id:03d}" in img_name:
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

                                    # === 실사 이미지 대체 기능 ===
                                    img_btn_cols = st.columns(5)

                                    # 1. 경로 복사 버튼
                                    with img_btn_cols[0]:
                                        if st.button("Copy", key=f"copy_path_{i}_{scene_id}", help="이미지 경로 복사"):
                                            # 절대 경로로 변환
                                            abs_path = str(scene_image.resolve())
                                            copy_path_to_clipboard(abs_path, f"copy_{i}_{scene_id}")
                                            st.toast(f"경로 복사됨!")
                                            # 전체 경로 표시 (사용자가 직접 복사 가능)
                                            st.code(abs_path, language=None)

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
                for i, scene in enumerate(scenes):
                    row = {
                        "씬": scene.get("scene_id", i + 1),
                        "시간(초)": scene.get("duration_estimate", 10),
                        "스크립트": scene.get("script_text", "")[:100] + "...",
                        "캐릭터": ", ".join(scene.get("characters", [])),
                        "분위기": scene.get("mood", ""),
                        "이미지": "O" if i < len(image_files) else "X"
                    }
                    table_data.append(row)

                df = pd.DataFrame(table_data)
                st.dataframe(df, use_container_width=True)

            # === 타임라인 뷰 ===
            elif view_mode == "타임라인 뷰":
                st.subheader("🎬 스토리보드 (타임라인 뷰)")

                # 이미지 그리드로 표시
                cols_per_row = 4
                current_time = 0

                for row_start in range(0, len(scenes), cols_per_row):
                    cols = st.columns(cols_per_row)

                    for j, col in enumerate(cols):
                        idx = row_start + j
                        if idx >= len(scenes):
                            break

                        scene = scenes[idx]
                        scene_id = scene.get("scene_id", idx + 1)
                        duration = scene.get("duration_estimate", 10)

                        with col:
                            # 타임코드
                            minutes = current_time // 60
                            seconds = current_time % 60
                            st.caption(f"{minutes:02d}:{seconds:02d}")

                            # 이미지 (확대 + 프롬프트 기능 포함)
                            if idx < len(image_files):
                                img_path = str(image_files[idx])
                                st.image(img_path, use_container_width=True)
                                # 확대/프롬프트 버튼
                                btn_c1, btn_c2 = st.columns(2)
                                with btn_c1:
                                    if st.button("🔍", key=f"tl_zoom_{idx}", help="확대"):
                                        st.session_state[f'tl_zoom_{idx}'] = True
                                with btn_c2:
                                    if st.button("📝", key=f"tl_prompt_{idx}", help="프롬프트"):
                                        st.session_state[f'tl_prompt_{idx}'] = not st.session_state.get(f'tl_prompt_{idx}', False)
                                # 확대 모달
                                if st.session_state.get(f'tl_zoom_{idx}', False):
                                    from utils.image_viewer import show_image_modal
                                    show_image_modal(img_path, scene_id, scene, f"씬 {scene_id}")
                                    st.session_state[f'tl_zoom_{idx}'] = False
                                # 프롬프트 expander
                                if st.session_state.get(f'tl_prompt_{idx}', False):
                                    prompt_info = ImagePromptManager.get_prompt_from_scene(scene)
                                    prompt_text = prompt_info.get('image_prompt', '')
                                    if prompt_text:
                                        st.caption(prompt_text[:80] + "..." if len(prompt_text) > 80 else prompt_text)
                                    else:
                                        st.caption("프롬프트 없음")
                            else:
                                st.info(f"씬 {scene_id}")

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
