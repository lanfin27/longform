# -*- coding: utf-8 -*-
"""
프롬프트 뷰어 컴포넌트

씬별 프롬프트를 표시하고 복사/다운로드 기능 제공
"""
import streamlit as st
import json
from datetime import datetime
from typing import Dict, List, Optional
import io
import csv


def get_prompt(scene: dict, prompt_type: str) -> str:
    """씬에서 프롬프트 추출 (다양한 구조 지원)"""
    # 1. prompts 객체 안에 있는 경우
    prompts = scene.get("prompts", {})
    if prompts.get(prompt_type):
        return prompts[prompt_type]

    # 2. 최상위에 있는 경우
    if scene.get(prompt_type):
        return scene[prompt_type]

    # 3. 없으면 빈 문자열
    return ""


def render_scene_prompts(scene: dict, show_download: bool = True, key_suffix: str = ""):
    """씬의 프롬프트를 탭으로 표시하는 컴포넌트"""

    scene_id = scene.get("scene_id", "?")
    unique_key = f"{scene_id}_{key_suffix}" if key_suffix else str(scene_id)

    # 프롬프트 추출
    prompts = {
        "image_prompt_ko": get_prompt(scene, "image_prompt_ko"),
        "image_prompt_en": get_prompt(scene, "image_prompt_en"),
        "character_prompt_ko": get_prompt(scene, "character_prompt_ko"),
        "character_prompt_en": get_prompt(scene, "character_prompt_en"),
        "video_prompt_character": get_prompt(scene, "video_prompt_character"),
        "video_prompt_full": get_prompt(scene, "video_prompt_full"),
    }

    # 탭 생성
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏞️ 배경 이미지",
        "🎭 캐릭터",
        "🎬 비디오 (캐릭터)",
        "🎬 비디오 (전체)"
    ])

    with tab1:
        render_prompt_card(
            title="배경 이미지 프롬프트",
            prompt_ko=prompts.get("image_prompt_ko", ""),
            prompt_en=prompts.get("image_prompt_en", ""),
            key_prefix=f"img_{unique_key}",
            description="AI 이미지 생성 서비스(Midjourney, DALL-E, Stable Diffusion)에 사용"
        )

    with tab2:
        render_prompt_card(
            title="캐릭터 프롬프트",
            prompt_ko=prompts.get("character_prompt_ko", ""),
            prompt_en=prompts.get("character_prompt_en", ""),
            key_prefix=f"char_{unique_key}",
            description="캐릭터 이미지 생성용 (배경 없이 캐릭터만)"
        )

    with tab3:
        render_prompt_card(
            title="비디오 프롬프트 (캐릭터만 움직임)",
            prompt_ko="",
            prompt_en=prompts.get("video_prompt_character", ""),
            key_prefix=f"vchar_{unique_key}",
            description="립싱크, 표정 연기용 (Runway, D-ID, HeyGen)"
        )

    with tab4:
        render_prompt_card(
            title="비디오 프롬프트 (전체 움직임)",
            prompt_ko="",
            prompt_en=prompts.get("video_prompt_full", ""),
            key_prefix=f"vfull_{unique_key}",
            description="시네마틱 연출용 (Runway, Pika, Kling)"
        )

    # 다운로드 버튼
    if show_download:
        render_scene_download_buttons(scene_id, prompts, unique_key)


def render_prompt_card(
    title: str,
    prompt_ko: str,
    prompt_en: str,
    key_prefix: str,
    description: str = ""
):
    """개별 프롬프트 카드 렌더링"""

    st.markdown(f"**{title}**")
    if description:
        st.caption(description)

    # 영어 프롬프트 (메인)
    if prompt_en and prompt_en != "N/A":
        st.markdown("**English (AI 생성용):**")

        col1, col2 = st.columns([6, 1])
        with col1:
            st.text_area(
                "prompt_en",
                value=prompt_en,
                height=100,
                key=f"{key_prefix}_en",
                label_visibility="collapsed"
            )
        with col2:
            if st.button("📋", key=f"copy_{key_prefix}_en", help="클립보드에 복사"):
                st.code(prompt_en, language=None)
                st.success("위 텍스트를 복사하세요")
    else:
        st.info("프롬프트가 생성되지 않았습니다. 씬 분석을 다시 실행하세요.")

    # 한국어 프롬프트 (참고용)
    if prompt_ko:
        with st.expander("🇰🇷 한국어 (참고용)"):
            st.write(prompt_ko)


def render_scene_download_buttons(scene_id, prompts: dict, unique_key: str):
    """씬별 다운로드 버튼"""

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        # JSON 다운로드
        json_data = json.dumps({
            "scene_id": scene_id,
            "prompts": prompts
        }, ensure_ascii=False, indent=2)

        st.download_button(
            label="📥 JSON",
            data=json_data,
            file_name=f"scene_{scene_id}_prompts.json",
            mime="application/json",
            key=f"dl_json_{unique_key}"
        )

    with col2:
        # TXT 다운로드 (영어 프롬프트만)
        txt_content = f"""Scene {scene_id} Prompts
{'='*50}

[Image Prompt]
{prompts.get('image_prompt_en', 'N/A')}

[Character Prompt]
{prompts.get('character_prompt_en', 'N/A')}

[Video Prompt - Character Only]
{prompts.get('video_prompt_character', 'N/A')}

[Video Prompt - Full Animation]
{prompts.get('video_prompt_full', 'N/A')}
"""
        st.download_button(
            label="📥 TXT",
            data=txt_content,
            file_name=f"scene_{scene_id}_prompts.txt",
            mime="text/plain",
            key=f"dl_txt_{unique_key}"
        )

    with col3:
        # 전체 복사용 코드 표시
        if st.button("📋 전체 복사", key=f"copy_all_{unique_key}"):
            all_prompts = f"""Image: {prompts.get('image_prompt_en', '')}

Video (Character): {prompts.get('video_prompt_character', '')}

Video (Full): {prompts.get('video_prompt_full', '')}"""
            st.code(all_prompts, language=None)


def render_prompts_viewer(scenes: list):
    """프롬프트 뷰어 - 모든 씬의 프롬프트 표시"""

    st.markdown("### ✨ 프롬프트 뷰어")
    st.info("각 씬의 AI 생성용 프롬프트를 확인하고 복사/다운로드할 수 있습니다.")

    if not scenes:
        st.warning("씬 데이터가 없습니다.")
        return

    # 씬 선택 옵션 생성
    scene_options = []
    for s in scenes:
        script_preview = s.get('script_text', '')[:30]
        scene_options.append(f"씬 {s['scene_id']}: {script_preview}...")

    # 전체 보기 / 개별 보기 선택
    view_mode = st.radio(
        "보기 모드",
        options=["개별 씬 선택", "모든 씬 보기"],
        horizontal=True,
        key="prompt_view_mode"
    )

    if view_mode == "개별 씬 선택":
        selected_idx = st.selectbox(
            "씬 선택",
            options=range(len(scenes)),
            format_func=lambda i: scene_options[i],
            key="prompt_scene_select"
        )

        if selected_idx is not None:
            scene = scenes[selected_idx]

            # 씬 정보 표시
            st.markdown(f"#### 씬 {scene['scene_id']}")

            script_text = get_prompt(scene, "script_text") or scene.get("narration", "") or scene.get("text", "")
            if script_text:
                st.write(script_text)

            st.divider()

            # 프롬프트 표시
            render_scene_prompts(scene, show_download=True, key_suffix="single")

    else:  # 모든 씬 보기
        for idx, scene in enumerate(scenes):
            script_preview = get_prompt(scene, "script_text") or scene.get("narration", "")
            with st.expander(f"씬 {scene['scene_id']}: {script_preview[:50]}...", expanded=False):
                render_scene_prompts(scene, show_download=True, key_suffix=f"all_{idx}")


def render_bulk_download_section(scenes: list, characters: list = None):
    """전체 다운로드 섹션"""

    st.markdown("### 📥 전체 다운로드")

    col1, col2, col3 = st.columns(3)

    with col1:
        # 전체 JSON
        full_data = {
            "scenes": scenes,
            "characters": characters or [],
            "exported_at": datetime.now().isoformat()
        }
        st.download_button(
            label="📥 전체 JSON",
            data=json.dumps(full_data, ensure_ascii=False, indent=2),
            file_name="all_prompts.json",
            mime="application/json",
            key="dl_all_json"
        )

    with col2:
        # 프롬프트만 CSV
        csv_content = generate_prompts_csv(scenes)
        st.download_button(
            label="📥 프롬프트 CSV",
            data=csv_content,
            file_name="prompts.csv",
            mime="text/csv",
            key="dl_all_csv"
        )

    with col3:
        # 프롬프트 TXT (한 파일에 모두)
        txt_content = generate_prompts_txt(scenes)
        st.download_button(
            label="📥 프롬프트 TXT",
            data=txt_content,
            file_name="all_prompts.txt",
            mime="text/plain",
            key="dl_all_txt"
        )


def generate_prompts_csv(scenes: list) -> str:
    """프롬프트 CSV 생성"""
    output = io.StringIO()
    writer = csv.writer(output)

    # 헤더
    writer.writerow([
        "scene_id",
        "script_text",
        "image_prompt_en",
        "character_prompt_en",
        "video_prompt_character",
        "video_prompt_full"
    ])

    # 데이터
    for scene in scenes:
        script_text = get_prompt(scene, "script_text") or scene.get("narration", "")
        writer.writerow([
            scene.get("scene_id", ""),
            script_text[:100] if script_text else "",  # 100자 제한
            get_prompt(scene, "image_prompt_en"),
            get_prompt(scene, "character_prompt_en"),
            get_prompt(scene, "video_prompt_character"),
            get_prompt(scene, "video_prompt_full")
        ])

    return output.getvalue()


def generate_prompts_txt(scenes: list) -> str:
    """프롬프트 TXT 생성"""

    lines = []
    lines.append("=" * 60)
    lines.append("AI PROMPTS - All Scenes")
    lines.append("=" * 60)
    lines.append("")

    for scene in scenes:
        scene_id = scene.get("scene_id", "?")
        script_text = get_prompt(scene, "script_text") or scene.get("narration", "")

        lines.append(f"[Scene {scene_id}]")
        lines.append("-" * 40)
        lines.append(f"Script: {script_text[:100]}..." if script_text else "Script: N/A")
        lines.append("")
        lines.append("Image Prompt (EN):")
        lines.append(get_prompt(scene, "image_prompt_en") or "N/A")
        lines.append("")
        lines.append("Character Prompt (EN):")
        lines.append(get_prompt(scene, "character_prompt_en") or "N/A")
        lines.append("")
        lines.append("Video Prompt (Character):")
        lines.append(get_prompt(scene, "video_prompt_character") or "N/A")
        lines.append("")
        lines.append("Video Prompt (Full):")
        lines.append(get_prompt(scene, "video_prompt_full") or "N/A")
        lines.append("")
        lines.append("=" * 60)
        lines.append("")

    return "\n".join(lines)
