# -*- coding: utf-8 -*-
"""
6단계: 이미지 생성 (리팩토링)

탭 구조:
- 🎬 씬별 생성: 개별 씬 선택 → 배경 → 캐릭터 배치 → 합성 → 편집 → 저장
- 🚀 일괄 생성: 전체 씬 자동 생성
- 🖼️ 갤러리: 생성된 이미지 관리
- ⚙️ 설정: 스타일 및 API 설정
"""
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
from utils.style_manager import get_style_manager
from components.style_selector import style_radio_selector, get_selected_style

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

project_path = get_current_project()

# ===================================================================
# 유틸리티 함수
# ===================================================================

def sync_all_data():
    """페이지 로드 시 모든 데이터 동기화"""
    # 씬 데이터 로드
    scenes = load_scenes(project_path)
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

    # 배경 이미지 로드
    bg_json = project_path / "images" / "backgrounds" / "backgrounds.json"
    if bg_json.exists():
        try:
            with open(bg_json, "r", encoding="utf-8") as f:
                bg_data = json.load(f)
                st.session_state["background_images"] = {str(k): v for k, v in bg_data.items()}
        except:
            pass

    # 합성 이미지 로드
    comp_json = project_path / "images" / "composited" / "composited.json"
    if comp_json.exists():
        try:
            with open(comp_json, "r", encoding="utf-8") as f:
                comp_data = json.load(f)
                st.session_state["composited_images"] = comp_data
        except:
            pass


def get_scenes() -> List[Dict]:
    """씬 목록 가져오기"""
    return st.session_state.get("scenes", [])


def get_scene_by_id(scene_id: int) -> Optional[Dict]:
    """씬 ID로 씬 정보 가져오기"""
    scenes = get_scenes()
    for scene in scenes:
        if scene.get("scene_id") == scene_id:
            return scene
    return None


def get_all_gallery_images() -> List[Dict]:
    """모든 생성된 이미지 목록"""
    images = []

    # 합성 이미지
    comp_dir = project_path / "images" / "composited"
    if comp_dir.exists():
        for f in comp_dir.glob("*.png"):
            images.append({
                "path": str(f),
                "filename": f.name,
                "type": "composited",
                "scene_id": extract_scene_id(f.name),
                "created": f.stat().st_mtime
            })

    # 씬 이미지
    scene_dir = project_path / "images" / "scenes"
    if scene_dir.exists():
        for f in scene_dir.glob("*.png"):
            images.append({
                "path": str(f),
                "filename": f.name,
                "type": "scene",
                "scene_id": extract_scene_id(f.name),
                "created": f.stat().st_mtime
            })

    # 배경 이미지
    bg_dir = project_path / "images" / "backgrounds"
    if bg_dir.exists():
        for f in bg_dir.glob("*.png"):
            images.append({
                "path": str(f),
                "filename": f.name,
                "type": "background",
                "scene_id": extract_scene_id(f.name),
                "created": f.stat().st_mtime
            })

    # 최신순 정렬
    images.sort(key=lambda x: x["created"], reverse=True)
    return images


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
                st.image(comp_img, use_container_width=True)
                st.caption("✅ 합성완료")
            elif bg_data:
                bg_path = bg_data.get("path") or bg_data.get("url")
                if bg_path and os.path.exists(bg_path):
                    st.image(bg_path, use_container_width=True)
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
                st.caption(f"👤 {', '.join(chars[:3])}{'...' if len(chars) > 3 else ''}")

            # 선택 버튼
            is_selected = scene_id == selected_scene_id
            btn_type = "primary" if is_selected else "secondary"
            if st.button(
                "✏️ 편집 중" if is_selected else "선택",
                key=f"select_scene_{scene_id}",
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

        st.markdown(f"**캐릭터:** {', '.join(scene.get('characters', []))}")

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
    prompt_tabs = st.tabs(["🖼️ 이미지", "🎬 비디오", "🎭 캐릭터"])

    # --- 이미지 프롬프트 ---
    with prompt_tabs[0]:
        st.markdown("##### 배경 이미지 프롬프트")
        st.caption("씬 배경 생성용 (캐릭터 제외)")

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

    # --- 비디오 프롬프트 ---
    with prompt_tabs[1]:
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
    with prompt_tabs[2]:
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

                        # 캐릭터 이미지 미리보기
                        char_img = char_info.get("image_path") or char_info.get("image_url")
                        if char_img and os.path.exists(char_img):
                            st.image(char_img, width=150)
                else:
                    st.info(f"'{char_name}' 캐릭터 정보를 찾을 수 없습니다.")
        else:
            st.info("이 씬에 등장하는 캐릭터가 없습니다.")


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
            generate_background_image(scene_id, prompt, style, width, height)

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

    st.markdown(f"**등장 캐릭터:** {', '.join(scene_characters)}")

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
                        # 캐릭터 이미지
                        char_image = char_info.get("image_url") or char_info.get("image_path")
                        if char_image and os.path.exists(char_image):
                            st.image(char_image, width=120)
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

    st.markdown("**배경 이미지:**")
    st.image(bg_path, use_container_width=True)

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

    # 합성 실행
    if st.button("🎨 합성 실행", type="primary", use_container_width=True, key=f"composite_{scene_id}"):
        with st.spinner("합성 중..."):
            result = execute_composite(scene_id, scene, remove_bg)

            if result:
                st.session_state[f"composite_result_{scene_id}"] = result
                st.success("✅ 합성 완료!")
                st.rerun()

    # 합성 결과 표시
    result = st.session_state.get(f"composite_result_{scene_id}")
    if result and os.path.exists(result):
        st.markdown("---")
        st.markdown("**합성 결과:**")
        st.image(result, use_container_width=True)


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
        st.image(result, use_container_width=True)

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
                            new_result = execute_composite(scene_id, scene, remove_bg=True)
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
            st.image(result, use_container_width=True)


def render_save_step(scene_id: int, scene: Dict):
    """저장 단계"""
    st.markdown("#### 💾 저장 및 적용")

    result = st.session_state.get(f"composite_result_{scene_id}")

    if not result or not os.path.exists(result):
        st.info("먼저 이미지를 합성하세요.")
        return

    st.image(result, use_container_width=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        with open(result, "rb") as f:
            st.download_button(
                "💾 다운로드",
                data=f.read(),
                file_name=f"scene_{scene_id:03d}.png",
                mime="image/png",
                use_container_width=True
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

    # 서브탭 구성
    batch_tabs = st.tabs(["🎨 배경+합성 일괄 생성", "🔄 합성만 일괄 실행"])

    with batch_tabs[0]:
        _render_batch_background_and_composite(scenes)

    with batch_tabs[1]:
        _render_batch_composite_only(scenes)


def _render_imagefx_cookie_settings():
    """Google ImageFX 인증 설정 UI (Authorization 토큰 권장)"""
    from config.settings import IMAGEFX_COOKIE, SECRETS_DIR, save_imagefx_auth_token, load_imagefx_auth_token

    # 현재 인증 상태 확인
    current_token = st.session_state.get("imagefx_auth_token", "") or load_imagefx_auth_token()
    current_cookie = st.session_state.get("imagefx_cookie") or IMAGEFX_COOKIE
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

    # 씬 선택
    st.markdown("### 생성할 씬 선택")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✅ 전체 선택", key="batch_select_all"):
            for scene in scenes:
                st.session_state[f"batch_select_{scene.get('scene_id')}"] = True
            st.rerun()
    with col2:
        if st.button("❌ 전체 해제", key="batch_deselect_all"):
            for scene in scenes:
                st.session_state[f"batch_select_{scene.get('scene_id')}"] = False
            st.rerun()
    with col3:
        if st.button("🔄 미완료만 선택", key="batch_select_incomplete"):
            for scene in scenes:
                scene_id = scene.get("scene_id")
                has_image = get_composited_for_scene(scene_id) is not None
                st.session_state[f"batch_select_{scene_id}"] = not has_image
            st.rerun()

    # 씬 체크박스 (텍스트 미리보기 포함)
    selected_scenes = []

    # 선택 UI 모드
    view_mode = st.radio(
        "표시 모드",
        options=["컴팩트", "텍스트 포함"],
        horizontal=True,
        key="batch_view_mode"
    )

    if view_mode == "컴팩트":
        # 기존 컴팩트 모드
        cols = st.columns(min(6, len(scenes)))
        for i, scene in enumerate(scenes):
            scene_id = scene.get("scene_id")
            with cols[i % 6]:
                # 완료 상태 표시
                has_image = get_composited_for_scene(scene_id) is not None
                status_icon = "✅" if has_image else "⬜"

                is_selected = st.checkbox(
                    f"{status_icon} 씬 {scene_id}",
                    value=st.session_state.get(f"batch_select_{scene_id}", False),
                    key=f"batch_cb_{scene_id}",
                    help=_get_scene_preview_text(scene)
                )
                if is_selected:
                    selected_scenes.append(scene_id)
    else:
        # 텍스트 포함 모드
        for i, scene in enumerate(scenes):
            scene_id = scene.get("scene_id")
            has_image = get_composited_for_scene(scene_id) is not None
            status_icon = "✅" if has_image else "⬜"

            # 씬 텍스트 가져오기 (script_text 우선)
            scene_text = (
                scene.get("script_text", "") or
                scene.get("narration", "") or
                scene.get("description", "") or
                scene.get("text", "")
            )
            preview_text = scene_text[:80] + "..." if len(scene_text) > 80 else scene_text

            col1, col2 = st.columns([1, 10])

            with col1:
                is_selected = st.checkbox(
                    f"선택",
                    value=st.session_state.get(f"batch_select_{scene_id}", False),
                    key=f"batch_cb_{scene_id}",
                    label_visibility="collapsed"
                )
                if is_selected:
                    selected_scenes.append(scene_id)

            with col2:
                # 씬 정보 카드
                chars = scene.get("characters", [])
                char_str = f" 👤 {', '.join(chars[:2])}{'...' if len(chars) > 2 else ''}" if chars else ""

                with st.expander(f"{status_icon} **씬 {scene_id}**{char_str}", expanded=False):
                    st.markdown(f"**내용:**")
                    st.text(scene_text if scene_text else "(텍스트 없음)")

                    if scene.get("background_prompt"):
                        st.markdown(f"**배경 프롬프트:** {scene.get('background_prompt')[:100]}...")

    st.markdown(f"**선택된 씬:** {len(selected_scenes)}개")

    st.markdown("---")

    # 생성 옵션
    st.markdown("### 생성 옵션")

    col1, col2, col3 = st.columns(3)

    with col1:
        # StyleManager에서 배경 스타일 목록 로드
        from utils.style_manager import get_styles_by_segment
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

        # 선택된 스타일 프롬프트 미리보기
        selected_style = next((s for s in bg_styles if s.id == style), None)
        if selected_style and (selected_style.prompt_prefix or selected_style.prompt_suffix):
            with st.expander("📝 스타일 프롬프트 미리보기", expanded=False):
                if selected_style.prompt_prefix:
                    st.caption("**Prefix:**")
                    st.code(selected_style.prompt_prefix[:200] + "..." if len(selected_style.prompt_prefix) > 200 else selected_style.prompt_prefix, language=None)
                if selected_style.prompt_suffix:
                    st.caption("**Suffix:**")
                    st.code(selected_style.prompt_suffix[:200] + "..." if len(selected_style.prompt_suffix) > 200 else selected_style.prompt_suffix, language=None)

    with col2:
        generate_background = st.checkbox("배경 생성", value=True, key="batch_gen_bg")
        generate_composite = st.checkbox("합성 실행", value=True, key="batch_gen_comp")

    with col3:
        remove_bg = st.checkbox("캐릭터 배경 제거", value=True, key="batch_remove_bg")

    st.markdown("---")

    # 생성 버튼
    if st.button(
        f"🚀 {len(selected_scenes)}개 씬 일괄 생성",
        type="primary",
        use_container_width=True,
        disabled=len(selected_scenes) == 0
    ):
        progress = st.progress(0)
        status = st.empty()

        success_count = 0
        error_count = 0

        for i, scene_id in enumerate(selected_scenes):
            status.text(f"씬 {scene_id} 처리 중... ({i+1}/{len(selected_scenes)})")
            progress.progress((i + 1) / len(selected_scenes))

            scene = get_scene_by_id(scene_id)
            if not scene:
                error_count += 1
                continue

            try:
                # 배경 생성
                if generate_background:
                    # 프롬프트 우선순위: image_prompt_en > prompts.image_prompt_en > background_prompt > description
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

                    print(f"[일괄생성] 씬 {scene_id} 프롬프트: {prompt[:100]}...")
                    generate_background_image(scene_id, prompt, style, 1280, 720)
                    time.sleep(1)  # API 속도 제한

                # 합성
                if generate_composite:
                    execute_composite(scene_id, scene, remove_bg)

                success_count += 1

            except Exception as e:
                st.error(f"씬 {scene_id} 처리 실패: {e}")
                error_count += 1

        progress.progress(1.0)
        status.empty()

        if success_count > 0:
            st.success(f"✅ {success_count}개 씬 처리 완료!")
        if error_count > 0:
            st.warning(f"⚠️ {error_count}개 씬 처리 실패")


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
                    st.image(char["image_path"], width=80)
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
                            key=f"preview_cb_{scene_id}",
                            label_visibility="collapsed"
                        )
                        if is_selected:
                            selected_scene_ids.append(scene_id)

                    with header_col2:
                        status_icon = "✅" if has_composite else "⬜"
                        st.markdown(f"**{status_icon} 씬 {scene_id}**")

                    # 배경 프리뷰
                    bg_data = get_background_for_scene(scene_id)
                    if bg_data:
                        bg_path = bg_data.get("path") or bg_data.get("url")
                        if bg_path and os.path.exists(bg_path):
                            st.image(bg_path, use_container_width=True)
                        else:
                            st.info("🖼️ 배경 파일 없음")
                    else:
                        st.info("🖼️ 배경 없음")

                    # 캐릭터 썸네일
                    st.markdown("**캐릭터:**")

                    # 씬에 할당된 캐릭터 (커스텀 가능)
                    custom_chars_key = f"scene_chars_custom_{scene_id}"
                    if custom_chars_key not in st.session_state:
                        st.session_state[custom_chars_key] = list(scene_chars)

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
                                        st.image(char_img, width=60)
                                    else:
                                        st.markdown("👤")
                                    st.caption(char_name[:8])

                                    # 제거 버튼
                                    if st.button("❌", key=f"rm_char_{scene_id}_{char_name}"):
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
                                key=f"add_char_select_{scene_id}"
                            )
                            if add_char != "선택..." and st.button("추가", key=f"add_char_btn_{scene_id}"):
                                st.session_state[custom_chars_key].append(add_char)
                                st.rerun()

                    st.markdown("---")

    return selected_scene_ids


def _render_scene_list_view(scenes: List[Dict], all_characters: List[Dict]) -> List[int]:
    """기존 리스트 뷰 렌더링 (리팩토링)"""
    selected_scene_ids = []
    ext_chars = st.session_state.get("external_characters", [])
    all_chars_combined = all_characters + ext_chars

    for scene in scenes:
        scene_id = scene.get("scene_id")
        scene_chars = scene.get("characters", [])
        has_composite = get_composited_for_scene(scene_id) is not None

        col1, col2, col3 = st.columns([1, 4, 3])

        with col1:
            is_selected = st.checkbox(
                "선택",
                value=st.session_state.get(f"comp_select_{scene_id}", False),
                key=f"list_cb_{scene_id}",
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
                st.session_state[custom_chars_key] = list(scene_chars)

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

    st.markdown("---")

    # 일괄 합성 실행
    if st.button(
        f"🔄 {len(selected_scene_ids)}개 씬 일괄 합성",
        type="primary",
        use_container_width=True,
        disabled=len(selected_scene_ids) == 0
    ):
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
                result = execute_composite(scene_id, scene, remove_bg)

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

        progress.progress(1.0)
        status.empty()

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
            st.rerun()

    # 이미지 목록 가져오기
    images = get_all_gallery_images()

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

    if not images:
        st.info("생성된 이미지가 없습니다.")
        return

    st.markdown(f"**총 {len(images)}개 이미지**")

    # 다중 선택 모드
    multi_select = st.checkbox("다중 선택 모드", key="gallery_multi")

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
                st.rerun()

    st.markdown("---")

    # 세션 상태 초기화
    if "selected_gallery_images" not in st.session_state:
        st.session_state["selected_gallery_images"] = []

    # 선택된 이미지 수 표시 (다중 선택 모드일 때)
    if multi_select:
        selected_count = len(st.session_state.get("selected_gallery_images", []))
        if selected_count > 0:
            st.info(f"📌 **{selected_count}개** 이미지 선택됨")

    # 이미지 그리드
    cols = st.columns(4)

    for i, img in enumerate(images):
        with cols[i % 4]:
            # 다중 선택 모드: 체크박스 표시 (더 명확하게!)
            if multi_select:
                is_checked = img["path"] in st.session_state.get("selected_gallery_images", [])

                # 체크박스와 씬 번호를 한 행에 표시
                cb_col, info_col = st.columns([1, 2])
                with cb_col:
                    new_checked = st.checkbox(
                        "✓",
                        value=is_checked,
                        key=f"gallery_select_{i}",
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

            # 이미지 (선택 시 테두리 표시)
            if os.path.exists(img["path"]):
                if is_selected:
                    st.markdown(
                        '<div style="border: 3px solid #667eea; border-radius: 8px; padding: 2px; background: rgba(102,126,234,0.1);">',
                        unsafe_allow_html=True
                    )
                st.image(img["path"], use_container_width=True)
                if is_selected:
                    st.markdown('</div>', unsafe_allow_html=True)

            # 정보 (다중 선택 모드가 아닐 때만 표시)
            if not multi_select:
                type_emoji = {"composited": "🎨", "background": "🏞️", "scene": "🎬"}.get(img.get("type"), "📷")
                st.caption(f"{type_emoji} 씬 {img.get('scene_id', '?')}")

            # 버튼들 (다중 선택 모드가 아닐 때만)
            if not multi_select:
                btn_cols = st.columns(3)

                with btn_cols[0]:
                    # 스토리보드 적용
                    scene_id = img.get("scene_id")
                    if scene_id and str(scene_id).isdigit():
                        if st.button("📋", key=f"apply_gallery_{i}", help="스토리보드에 적용"):
                            save_to_storyboard(int(scene_id), img["path"])
                            st.success(f"씬 {scene_id}에 적용!")

                with btn_cols[1]:
                    # 다운로드
                    if os.path.exists(img["path"]):
                        with open(img["path"], "rb") as f:
                            st.download_button(
                                "💾",
                                data=f.read(),
                                file_name=img["filename"],
                                key=f"dl_gallery_{i}"
                            )

                with btn_cols[2]:
                    # 삭제
                    if st.button("🗑️", key=f"del_gallery_{i}"):
                        delete_image(img["path"])
                        st.rerun()

            st.markdown("---")


# ===================================================================
# 탭 4: 설정
# ===================================================================

def render_settings_tab():
    """⚙️ 설정 탭"""
    st.markdown("## ⚙️ 이미지 생성 설정")

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
        default_resolution = st.selectbox(
            "기본 해상도",
            options=["1280x720", "1920x1080", "1024x576"],
            key="default_resolution"
        )

    st.markdown("---")

    # API 설정
    st.markdown("### 🔑 API 설정")

    col1, col2 = st.columns(2)

    with col1:
        image_api = st.selectbox(
            "이미지 생성 API",
            options=["Together.ai FLUX", "Google ImageFX", "OpenAI DALL-E", "Stability AI"],
            key="image_api",
            help="🆓 Google ImageFX: 무료 (쿠키 필요)\n💰 Together.ai FLUX: ~20원/장\n💰 OpenAI DALL-E: ~60원/장"
        )

    with col2:
        if image_api == "Together.ai FLUX":
            model = st.selectbox(
                "모델",
                options=[
                    "black-forest-labs/FLUX.2-dev",
                    "black-forest-labs/FLUX.2-flex",
                    "black-forest-labs/FLUX.2-pro"
                ],
                format_func=lambda x: {
                    "black-forest-labs/FLUX.2-dev": "FLUX.2 Dev (권장, ~20원)",
                    "black-forest-labs/FLUX.2-flex": "FLUX.2 Flex (~40원)",
                    "black-forest-labs/FLUX.2-pro": "FLUX.2 Pro (고품질, ~40원)"
                }.get(x, x),
                key="flux_model"
            )
        elif image_api == "Google ImageFX":
            model = st.selectbox(
                "모델",
                options=["IMAGEN_4", "IMAGEN_3_5", "IMAGEN_3_1", "IMAGEN_3"],
                format_func=lambda x: {
                    "IMAGEN_4": "Imagen 4 (최신, 무료)",
                    "IMAGEN_3_5": "Imagen 3.5 (무료)",
                    "IMAGEN_3_1": "Imagen 3.1 (무료)",
                    "IMAGEN_3": "Imagen 3.0 (무료)"
                }.get(x, x),
                key="imagefx_model"
            )

    # Google ImageFX 쿠키 설정 (ImageFX 선택 시)
    if image_api == "Google ImageFX":
        _render_imagefx_cookie_settings()

    st.markdown("---")

    # 고급 설정
    st.markdown("### ⚙️ 고급 설정")

    col1, col2 = st.columns(2)

    with col1:
        st.checkbox(
            "캐릭터 배경 자동 제거 (rembg)",
            value=True,
            key="auto_remove_bg"
        )
        st.checkbox(
            "생성 후 자동 스토리보드 저장",
            value=False,
            key="auto_save_storyboard"
        )

    with col2:
        st.checkbox(
            "생성 로그 저장",
            value=True,
            key="save_generation_log"
        )
        st.number_input(
            "API 호출 간격 (초)",
            min_value=0.5,
            max_value=10.0,
            value=1.0,
            step=0.5,
            key="api_delay"
        )

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


# ===================================================================
# 헬퍼 함수 (이미지 생성/합성)
# ===================================================================

def generate_background_image(scene_id: int, prompt: str, style: str, width: int, height: int):
    """배경 이미지 생성 - StyleManager의 스타일 프롬프트 적용"""
    try:
        from core.image.together_client import TogetherImageClient, get_model_price_info
        from utils.style_manager import get_style_by_id, get_styles_by_segment, build_prompt
        from config.settings import TOGETHER_DEFAULT_MODEL

        # 사용할 모델 (설정에서 가져옴)
        model = TOGETHER_DEFAULT_MODEL or "black-forest-labs/FLUX.2-dev"
        model_info = get_model_price_info(model)

        client = TogetherImageClient()

        # ==============================
        # 스타일 매니저에서 스타일 로드
        # ==============================
        style_obj = get_style_by_id(style)

        # ID로 못 찾으면 이름으로 검색
        if not style_obj:
            bg_styles = get_styles_by_segment("background")
            for s in bg_styles:
                if s.name_ko == style or s.name == style or s.id == style:
                    style_obj = s
                    break

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

            print(f"[배경 생성] 스타일 '{style_obj.name_ko}' 로드됨")
            print(f"[배경 생성] prefix: {style_prefix[:100]}..." if len(style_prefix) > 100 else f"[배경 생성] prefix: {style_prefix or '(없음)'}")
            print(f"[배경 생성] suffix: {style_suffix[:100]}..." if len(style_suffix) > 100 else f"[배경 생성] suffix: {style_suffix or '(없음)'}")
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
        print(f"[배경 생성] 📌 API: Together.ai FLUX")
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
                st.metric("API", "Together.ai FLUX")
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

        img_data = client.generate_image(
            prompt=full_prompt,
            width=width,
            height=height
        )

        # 저장
        bg_dir = project_path / "images" / "backgrounds"
        bg_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time() * 1000)
        filename = f"bg_scene_{scene_id:03d}_{timestamp}.png"
        filepath = bg_dir / filename

        with open(filepath, "wb") as f:
            f.write(img_data)

        # 메타데이터 저장
        set_background_for_scene(scene_id, str(filepath))

        st.success(f"✅ 배경 생성 완료: {filename}")
        st.image(str(filepath), use_container_width=True)

        return str(filepath)

    except Exception as e:
        st.error(f"배경 생성 실패: {e}")
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


def execute_composite(scene_id: int, scene: Dict, remove_bg: bool) -> Optional[str]:
    """
    합성 실행 - 드래그 편집기/슬라이더 형식 모두 지원

    좌표 형식:
    - 드래그 편집기: x, y (중심 비율 0~1), width, height (캔버스 대비 비율)
    - 슬라이더: x, y (중심 비율 0~1), scale (배율)
    """
    try:
        from PIL import Image, ImageOps

        print(f"[Composite] 씬 {scene_id} 합성 시작")

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

        return str(filepath)

    except Exception as e:
        st.error(f"합성 실패: {e}")
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

    st.success(f"✅ {deleted_count}개 미사용 이미지 삭제됨")


# ===================================================================
# 메인
# ===================================================================

# 데이터 동기화
sync_all_data()

# 헤더
st.title("🎨 6단계: 이미지 생성")
st.caption(f"프로젝트: {project_path.name}")

# API 키 확인
if not require_api_key("TOGETHER_API_KEY", "Together.ai API"):
    st.stop()

st.divider()

# 탭 구성
tabs = st.tabs([
    "🎬 씬별 생성",
    "🚀 일괄 생성",
    "🖼️ 갤러리",
    "⚙️ 설정"
])

with tabs[0]:
    render_scene_editor_tab()

with tabs[1]:
    render_batch_generation_tab()

with tabs[2]:
    render_gallery_tab()

with tabs[3]:
    render_settings_tab()

# 푸터
st.divider()
col1, col2 = st.columns(2)
with col1:
    st.page_link("pages/7_📦_Vrew_Export.py", label="📦 7단계: Vrew Export", icon="➡️")
with col2:
    st.page_link("pages/8_📋_스토리보드.py", label="📋 8단계: 스토리보드", icon="➡️")
