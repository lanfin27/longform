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


def get_composited_for_scene(scene_id: int) -> Optional[str]:
    """씬의 합성 이미지 가져오기"""
    comp_dir = project_path / "images" / "composited"
    if comp_dir.exists():
        # 최신 합성 이미지 찾기
        pattern = f"scene_{scene_id:03d}_*"
        files = sorted(comp_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)
        if files:
            return str(files[0])
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
        st.markdown(f"**설명:** {scene.get('description', '')}")
        st.markdown(f"**캐릭터:** {', '.join(scene.get('characters', []))}")
        narration = scene.get('narration', '')
        if narration:
            st.markdown(f"**나레이션:** {narration[:300]}...")

    # 편집 단계 탭
    step_tabs = st.tabs([
        "🏞️ 배경",
        "🎭 캐릭터 배치",
        "🔄 합성",
        "✏️ 편집",
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

    # --- 단계 5: 저장 ---
    with step_tabs[4]:
        render_save_step(scene_id, scene)


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
            default_prompt = scene.get("background_prompt", scene.get("description", ""))
            prompt = st.text_area(
                "배경 프롬프트",
                value=default_prompt,
                height=100,
                key=f"bg_prompt_{scene_id}"
            )

        with col2:
            style = st.selectbox(
                "스타일",
                options=["semoji", "animation", "realistic", "illustration"],
                format_func=lambda x: {
                    "semoji": "세모지",
                    "animation": "애니메이션",
                    "realistic": "실사",
                    "illustration": "일러스트"
                }.get(x, x),
                key=f"bg_style_{scene_id}"
            )

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
    """캐릭터 배치 단계"""
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
                            "X 위치",
                            0.0, 1.0, pos.get("x", 0.5), 0.05,
                            key=f"pos_x_{scene_id}_{char_name}"
                        )

                    with col_y:
                        pos["y"] = st.slider(
                            "Y 위치",
                            0.0, 1.0, pos.get("y", 0.7), 0.05,
                            key=f"pos_y_{scene_id}_{char_name}"
                        )

                    with col_s:
                        pos["scale"] = st.slider(
                            "크기",
                            0.3, 2.0, pos.get("scale", 1.0), 0.1,
                            key=f"scale_{scene_id}_{char_name}"
                        )

                    char_positions[char_name] = pos
            else:
                st.warning(f"'{char_name}' 캐릭터 정보를 찾을 수 없습니다.")
                st.info("캐릭터 관리에서 먼저 캐릭터를 등록하세요.")

    # 위치 저장
    st.session_state[f"char_positions_{scene_id}"] = char_positions

    if st.button("👁️ 배치 미리보기", key=f"preview_placement_{scene_id}"):
        st.info("미리보기 기능 - 합성 단계에서 확인 가능합니다.")


def render_composite_step(scene_id: int, scene: Dict):
    """합성 단계"""
    st.markdown("#### 🔄 이미지 합성")

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

    # 합성 옵션
    col1, col2 = st.columns(2)

    with col1:
        remove_bg = st.checkbox(
            "캐릭터 배경 제거 (rembg)",
            value=True,
            key=f"remove_bg_{scene_id}"
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

    st.info("💡 이 단계에서는 합성된 이미지의 캐릭터 위치/크기를 미세 조정할 수 있습니다.")

    # 현재 합성 결과 표시
    st.image(result, use_container_width=True)

    # 드래그 편집기 시도
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
                char_layers.append({
                    "name": char_name,
                    "image_url": char_info.get("image_url") or char_info.get("image_path"),
                    "x": pos.get("x", 0.5),
                    "y": pos.get("y", 0.7),
                    "width": 0.25 * pos.get("scale", 1.0),
                    "height": 0.4 * pos.get("scale", 1.0),
                    "z_index": 1
                })

        if char_layers:
            with st.expander("🎮 드래그 편집기", expanded=False):
                post_composite_editor(
                    background_url=bg_url,
                    character_layers=char_layers,
                    canvas_width=800,
                    canvas_height=450,
                    editor_id=f"editor_scene_{scene_id}"
                )

                if st.button("🔄 재합성", type="primary", key=f"recomposite_{scene_id}"):
                    with st.spinner("재합성 중..."):
                        result = execute_composite(scene_id, scene, remove_bg=True)
                        if result:
                            st.session_state[f"composite_result_{scene_id}"] = result
                            st.success("재합성 완료!")
                            st.rerun()

    except ImportError:
        st.caption("드래그 편집기 컴포넌트를 사용할 수 없습니다.")


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

    st.info("💡 여러 씬의 배경과 합성 이미지를 한 번에 생성합니다.")

    # 씬 선택
    st.markdown("### 생성할 씬 선택")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✅ 전체 선택"):
            for scene in scenes:
                st.session_state[f"batch_select_{scene.get('scene_id')}"] = True
            st.rerun()
    with col2:
        if st.button("❌ 전체 해제"):
            for scene in scenes:
                st.session_state[f"batch_select_{scene.get('scene_id')}"] = False
            st.rerun()
    with col3:
        if st.button("🔄 미완료만 선택"):
            for scene in scenes:
                scene_id = scene.get("scene_id")
                has_image = get_composited_for_scene(scene_id) is not None
                st.session_state[f"batch_select_{scene_id}"] = not has_image
            st.rerun()

    # 씬 체크박스
    selected_scenes = []
    cols = st.columns(min(6, len(scenes)))

    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id")
        with cols[i % 6]:
            is_selected = st.checkbox(
                f"씬 {scene_id}",
                value=st.session_state.get(f"batch_select_{scene_id}", False),
                key=f"batch_cb_{scene_id}"
            )
            if is_selected:
                selected_scenes.append(scene_id)

    st.markdown(f"**선택된 씬:** {len(selected_scenes)}개")

    st.markdown("---")

    # 생성 옵션
    st.markdown("### 생성 옵션")

    col1, col2, col3 = st.columns(3)

    with col1:
        style = st.selectbox(
            "스타일",
            options=["semoji", "animation", "realistic"],
            format_func=lambda x: {"semoji": "세모지", "animation": "애니메이션", "realistic": "실사"}.get(x, x),
            key="batch_style"
        )

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
                    prompt = scene.get("background_prompt", scene.get("description", ""))
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

    # 이미지 그리드
    cols = st.columns(4)

    for i, img in enumerate(images):
        with cols[i % 4]:
            # 이미지
            if os.path.exists(img["path"]):
                st.image(img["path"], use_container_width=True)

            # 정보
            type_emoji = {"composited": "🎨", "background": "🏞️", "scene": "🎬"}.get(img.get("type"), "📷")
            st.caption(f"{type_emoji} 씬 {img.get('scene_id', '?')}")

            # 버튼들
            btn_cols = st.columns(3)

            with btn_cols[0]:
                # 스토리보드 적용
                scene_id = img.get("scene_id")
                if scene_id and scene_id.isdigit():
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

    col1, col2 = st.columns(2)

    with col1:
        default_style = st.selectbox(
            "기본 이미지 스타일",
            options=["semoji", "animation", "realistic", "illustration", "watercolor"],
            format_func=lambda x: {
                "semoji": "세모지 스타일",
                "animation": "애니메이션",
                "realistic": "실사",
                "illustration": "일러스트",
                "watercolor": "수채화"
            }.get(x, x),
            key="default_image_style"
        )

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
            options=["Together.ai FLUX", "OpenAI DALL-E", "Stability AI"],
            key="image_api"
        )

    with col2:
        if image_api == "Together.ai FLUX":
            model = st.selectbox(
                "모델",
                options=[
                    "black-forest-labs/FLUX.1-schnell-Free",
                    "black-forest-labs/FLUX.1-schnell",
                    "black-forest-labs/FLUX.1-dev"
                ],
                key="flux_model"
            )

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
    """배경 이미지 생성"""
    try:
        from core.image.together_client import TogetherImageClient

        client = TogetherImageClient()

        # 스타일 프롬프트 적용
        style_prefixes = {
            "semoji": "semoji style, cute illustration, ",
            "animation": "anime style, vibrant colors, ",
            "realistic": "photorealistic, high detail, ",
            "illustration": "digital illustration, "
        }

        full_prompt = style_prefixes.get(style, "") + prompt + ", background scene, no characters, wide shot"

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
    """합성 실행"""
    try:
        from PIL import Image

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

        # 캐릭터 배치
        char_positions = st.session_state.get(f"char_positions_{scene_id}", {})
        all_characters = st.session_state.get("characters", [])

        for char_name in scene.get("characters", []):
            char_info = next((c for c in all_characters if c.get("name") == char_name), None)

            if char_info:
                char_image_path = char_info.get("image_path") or char_info.get("image_url")

                if char_image_path and os.path.exists(char_image_path):
                    char_img = Image.open(char_image_path).convert("RGBA")

                    # 배경 제거
                    if remove_bg:
                        try:
                            from rembg import remove
                            char_img = remove(char_img)
                        except ImportError:
                            st.warning("rembg 라이브러리가 없어 배경 제거를 건너뜁니다.")

                    # 위치 및 크기 계산
                    pos = char_positions.get(char_name, {"x": 0.5, "y": 0.7, "scale": 1.0})

                    # 캐릭터 크기 조정
                    scale = pos.get("scale", 1.0)
                    new_height = int(background.height * 0.4 * scale)
                    aspect = char_img.width / char_img.height
                    new_width = int(new_height * aspect)

                    char_img = char_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                    # 위치 계산
                    x = int(pos.get("x", 0.5) * background.width - new_width / 2)
                    y = int(pos.get("y", 0.7) * background.height - new_height / 2)

                    # 합성
                    background.paste(char_img, (x, y), char_img)

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
