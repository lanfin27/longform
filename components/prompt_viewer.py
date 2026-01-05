# -*- coding: utf-8 -*-
"""
프롬프트 뷰어 컴포넌트

씬별 프롬프트를 표시하고 복사/다운로드 기능 제공
+ 유형별/범위별 다운로드 기능
"""
import streamlit as st
import json
import zipfile
from datetime import datetime
from typing import Dict, List, Optional
import io
import csv


# ============================================================
# 프롬프트 유형 정의
# ============================================================

PROMPT_TYPES = {
    "image_prompt_en": {
        "label": "🖼️ 이미지",
        "alt_keys": ["image_prompt", "img_prompt", "background_prompt", "이미지_프롬프트"],
        "description": "AI 이미지 생성용 (Midjourney, DALL-E)"
    },
    "character_prompt_en": {
        "label": "👤 캐릭터",
        "alt_keys": ["character_prompt", "char_prompt", "캐릭터_프롬프트", "person_prompt"],
        "description": "캐릭터 이미지 생성용"
    },
    "video_prompt_character": {
        "label": "🎬 비디오(캐릭터)",
        "alt_keys": ["video_prompt", "motion_prompt", "비디오_프롬프트"],
        "description": "립싱크/표정 연기용 (D-ID, HeyGen)"
    },
    "video_prompt_full": {
        "label": "🎬 비디오(전체)",
        "alt_keys": ["video_prompt_cinematic", "cinematic_prompt", "full_video_prompt"],
        "description": "시네마틱 연출용 (Runway, Pika)"
    },
    "audio_prompt": {
        "label": "🎵 배경음",
        "alt_keys": ["bgm_prompt", "music_prompt", "sound_prompt", "배경음_프롬프트"],
        "description": "배경음악/효과음 생성용"
    }
}


def get_prompt(scene: dict, prompt_type: str) -> str:
    """씬에서 프롬프트 추출 (다양한 구조 지원)"""
    # 1. prompts 객체 안에 있는 경우
    prompts = scene.get("prompts", {})
    if prompts.get(prompt_type):
        return prompts[prompt_type]

    # 2. 최상위에 있는 경우
    if scene.get(prompt_type):
        return scene[prompt_type]

    # 3. ai_prompts 딕셔너리 확인
    ai_prompts = scene.get("ai_prompts", {})
    if isinstance(ai_prompts, dict) and ai_prompts.get(prompt_type):
        return ai_prompts[prompt_type]

    # 4. 대체 키들로 시도
    config = PROMPT_TYPES.get(prompt_type, {})
    for alt_key in config.get("alt_keys", []):
        # prompts 객체 내
        if prompts.get(alt_key):
            return prompts[alt_key]
        # 최상위
        if scene.get(alt_key):
            return scene[alt_key]
        # ai_prompts 내
        if isinstance(ai_prompts, dict) and ai_prompts.get(alt_key):
            return ai_prompts[alt_key]

    # 5. 없으면 빈 문자열
    return ""


def get_all_prompts_from_scene(scene: dict) -> Dict[str, str]:
    """씬에서 모든 프롬프트 추출"""
    result = {}
    for prompt_type in PROMPT_TYPES.keys():
        result[prompt_type] = get_prompt(scene, prompt_type)
    return result


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
        lines.append("Audio Prompt:")
        lines.append(get_prompt(scene, "audio_prompt") or "N/A")
        lines.append("")
        lines.append("=" * 60)
        lines.append("")

    return "\n".join(lines)


# ============================================================
# ✅ 유형별 빠른 다운로드
# ============================================================

def render_quick_prompt_downloads(scenes: list):
    """유형별 빠른 다운로드 버튼들"""

    st.markdown("#### 🤖 AI 프롬프트 유형별 다운로드")

    # 각 유형별 프롬프트 개수 계산
    type_counts = {}
    for prompt_type in PROMPT_TYPES.keys():
        count = sum(1 for s in scenes if get_prompt(s, prompt_type))
        type_counts[prompt_type] = count

    # 버튼 배치 (5개 유형)
    cols = st.columns(5)

    for idx, (prompt_type, config) in enumerate(PROMPT_TYPES.items()):
        with cols[idx % 5]:
            count = type_counts[prompt_type]
            label = config["label"]

            if count > 0:
                # 해당 유형 프롬프트 생성
                txt_data = generate_prompts_by_type(scenes, prompt_type)

                st.download_button(
                    label=f"{label} ({count})",
                    data=txt_data,
                    file_name=f"{prompt_type}.txt",
                    mime="text/plain",
                    key=f"quick_dl_{prompt_type}",
                    use_container_width=True
                )
            else:
                st.button(
                    f"{label} (0)",
                    disabled=True,
                    key=f"quick_dl_{prompt_type}_disabled",
                    use_container_width=True
                )


def generate_prompts_by_type(scenes: list, prompt_type: str) -> str:
    """특정 유형의 프롬프트만 추출하여 TXT 생성"""

    config = PROMPT_TYPES.get(prompt_type, {})
    label = config.get("label", prompt_type)

    lines = []
    lines.append("=" * 60)
    lines.append(f"{label} 프롬프트")
    lines.append(f"총 {len(scenes)}개 씬")
    lines.append("=" * 60)
    lines.append("")

    for scene in scenes:
        scene_id = scene.get("scene_id", "?")
        prompt_text = get_prompt(scene, prompt_type)

        if prompt_text:
            lines.append(f"--- 씬 {scene_id} ---")
            lines.append(prompt_text)
            lines.append("")

    return "\n".join(lines)


# ============================================================
# ✅ 상세 다운로드 섹션 (범위 + 유형 선택)
# ============================================================

def render_advanced_download_section(scenes: list):
    """상세 다운로드 옵션 (범위/유형 선택)"""

    with st.expander("⚙️ 상세 다운로드 옵션", expanded=False):

        if not scenes:
            st.warning("씬 데이터가 없습니다.")
            return

        total_scenes = len(scenes)

        st.markdown("### ⚙️ 다운로드 설정")

        col1, col2 = st.columns(2)

        # === 프롬프트 유형 선택 ===
        with col1:
            st.markdown("**프롬프트 유형 선택**")

            selected_types = {}
            for prompt_type, config in PROMPT_TYPES.items():
                selected_types[prompt_type] = st.checkbox(
                    config["label"],
                    value=True,
                    key=f"adv_select_{prompt_type}"
                )

            col_sel1, col_sel2 = st.columns(2)
            with col_sel1:
                if st.button("✅ 전체 선택", key="adv_select_all"):
                    for prompt_type in PROMPT_TYPES.keys():
                        st.session_state[f"adv_select_{prompt_type}"] = True
                    st.rerun()
            with col_sel2:
                if st.button("⬜ 전체 해제", key="adv_deselect_all"):
                    for prompt_type in PROMPT_TYPES.keys():
                        st.session_state[f"adv_select_{prompt_type}"] = False
                    st.rerun()

        # === 씬 범위 선택 ===
        with col2:
            st.markdown("**씬 범위 선택**")

            range_option = st.radio(
                "범위",
                options=["전체", "범위 지정", "개별 선택"],
                horizontal=True,
                key="adv_range_option"
            )

            if range_option == "전체":
                selected_scene_ids = [s.get("scene_id", i+1) for i, s in enumerate(scenes)]
                st.caption(f"✅ 전체 {total_scenes}개 씬")

            elif range_option == "범위 지정":
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    start_scene = st.number_input(
                        "시작 씬",
                        min_value=1,
                        max_value=total_scenes,
                        value=1,
                        key="adv_range_start"
                    )
                with col_r2:
                    end_scene = st.number_input(
                        "끝 씬",
                        min_value=1,
                        max_value=total_scenes,
                        value=min(10, total_scenes),
                        key="adv_range_end"
                    )
                selected_scene_ids = list(range(start_scene, end_scene + 1))
                st.caption(f"✅ 씬 {start_scene} ~ {end_scene} ({len(selected_scene_ids)}개)")

            else:  # 개별 선택
                all_scene_ids = [s.get("scene_id", i+1) for i, s in enumerate(scenes)]
                selected_scene_ids = st.multiselect(
                    "씬 선택",
                    options=all_scene_ids,
                    default=all_scene_ids[:3] if len(all_scene_ids) >= 3 else all_scene_ids,
                    key="adv_individual_scenes"
                )
                st.caption(f"✅ {len(selected_scene_ids)}개 씬 선택됨")

        # === 미리보기 ===
        st.markdown("---")
        st.markdown("### 👁️ 다운로드 미리보기")

        active_types = [t for t, selected in selected_types.items() if selected]

        if not active_types:
            st.warning("프롬프트 유형을 선택하세요.")
            return

        if not selected_scene_ids:
            st.warning("씬을 선택하세요.")
            return

        # 선택된 씬 필터링
        filtered_scenes = [s for s in scenes if s.get("scene_id", 0) in selected_scene_ids]

        # 통계 계산
        total_prompts = 0
        type_stats = {}
        for prompt_type in active_types:
            count = sum(1 for s in filtered_scenes if get_prompt(s, prompt_type))
            type_stats[prompt_type] = count
            total_prompts += count

        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            st.metric("선택된 씬", f"{len(filtered_scenes)}개")
        with col_p2:
            st.metric("프롬프트 유형", f"{len(active_types)}개")
        with col_p3:
            st.metric("총 프롬프트", f"{total_prompts}개")

        # 유형별 상세 통계
        with st.expander("📊 유형별 상세", expanded=False):
            for prompt_type in active_types:
                label = PROMPT_TYPES[prompt_type]["label"]
                count = type_stats[prompt_type]
                st.caption(f"{label}: {count}개")

        # === 다운로드 버튼들 ===
        st.markdown("---")
        st.markdown("### 📥 다운로드")

        col_d1, col_d2, col_d3 = st.columns(3)

        with col_d1:
            # 개별 파일 ZIP
            zip_data = create_prompts_zip_individual(filtered_scenes, active_types)
            st.download_button(
                label="📦 개별 파일 ZIP",
                data=zip_data,
                file_name=f"prompts_individual_{len(filtered_scenes)}scenes.zip",
                mime="application/zip",
                key="adv_dl_zip_individual",
                use_container_width=True
            )

        with col_d2:
            # 유형별 통합 ZIP
            zip_data = create_prompts_zip_merged(filtered_scenes, active_types)
            st.download_button(
                label="📄 유형별 통합 ZIP",
                data=zip_data,
                file_name=f"prompts_merged_{len(filtered_scenes)}scenes.zip",
                mime="application/zip",
                key="adv_dl_zip_merged",
                use_container_width=True
            )

        with col_d3:
            # 전체 통합 TXT
            txt_data = create_prompts_single_file(filtered_scenes, active_types)
            st.download_button(
                label="📄 전체 통합 TXT",
                data=txt_data,
                file_name=f"all_prompts_{len(filtered_scenes)}scenes.txt",
                mime="text/plain",
                key="adv_dl_single_txt",
                use_container_width=True
            )


def create_prompts_zip_individual(scenes: list, prompt_types: list) -> bytes:
    """개별 파일 ZIP 생성 (prompt_type/scene_001.txt 구조)"""

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for scene in scenes:
            scene_id = scene.get("scene_id", "?")

            for prompt_type in prompt_types:
                prompt_text = get_prompt(scene, prompt_type)

                if not prompt_text:
                    continue

                # 폴더/파일명 생성
                filename = f"{prompt_type}/scene_{scene_id:03d}.txt" if isinstance(scene_id, int) else f"{prompt_type}/scene_{scene_id}.txt"
                zf.writestr(filename, prompt_text)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def create_prompts_zip_merged(scenes: list, prompt_types: list) -> bytes:
    """유형별 통합 파일 ZIP 생성"""

    zip_buffer = io.BytesIO()

    # 유형별 텍스트 수집
    type_texts = {t: [] for t in prompt_types}

    for scene in scenes:
        scene_id = scene.get("scene_id", "?")

        for prompt_type in prompt_types:
            prompt_text = get_prompt(scene, prompt_type)

            if prompt_text:
                type_texts[prompt_type].append(
                    f"=== 씬 {scene_id} ===\n{prompt_text}\n"
                )

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for prompt_type, texts in type_texts.items():
            if not texts:
                continue

            content = "\n".join(texts)
            label = PROMPT_TYPES.get(prompt_type, {}).get("label", prompt_type)
            filename = f"{prompt_type}_all.txt"

            # 헤더 추가
            header = f"# {label} 프롬프트 ({len(texts)}개 씬)\n{'='*60}\n\n"
            zf.writestr(filename, header + content)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def create_prompts_single_file(scenes: list, prompt_types: list) -> str:
    """전체 통합 단일 파일 생성"""

    scene_ids = [s.get("scene_id", 0) for s in scenes]
    min_id = min(scene_ids) if scene_ids else 0
    max_id = max(scene_ids) if scene_ids else 0

    lines = []
    lines.append("=" * 60)
    lines.append("AI 프롬프트 모음")
    lines.append(f"씬: {min_id} ~ {max_id} ({len(scenes)}개)")
    lines.append(f"유형: {', '.join([PROMPT_TYPES[t]['label'] for t in prompt_types])}")
    lines.append(f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    lines.append("")

    for scene in scenes:
        scene_id = scene.get("scene_id", "?")
        script = scene.get("script_text") or scene.get("narration", "") or scene.get("text", "")

        lines.append(f"\n{'='*40}")
        lines.append(f"씬 {scene_id}")
        if script:
            lines.append(f"스크립트: {script[:50]}...")
        lines.append(f"{'='*40}")

        for prompt_type in prompt_types:
            prompt_text = get_prompt(scene, prompt_type)
            label = PROMPT_TYPES[prompt_type]["label"]

            lines.append(f"\n[{label}]")
            if prompt_text:
                lines.append(prompt_text)
            else:
                lines.append("(없음)")

    return "\n".join(lines)


# ============================================================
# ✅ 통합 다운로드 섹션 (기존 + 확장)
# ============================================================

def render_enhanced_bulk_download_section(scenes: list, characters: list = None):
    """향상된 전체 다운로드 섹션"""

    st.markdown("### 📥 다운로드")

    if not scenes:
        st.warning("씬 데이터가 없습니다.")
        return

    # 기본 다운로드 버튼들
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
            file_name="analysis_result.json",
            mime="application/json",
            key="enh_dl_json"
        )

    with col2:
        # 프롬프트 CSV
        csv_content = generate_prompts_csv(scenes)
        st.download_button(
            label="📥 프롬프트 CSV",
            data=csv_content,
            file_name="prompts.csv",
            mime="text/csv",
            key="enh_dl_csv"
        )

    with col3:
        # 전체 프롬프트 TXT
        txt_content = generate_prompts_txt(scenes)
        st.download_button(
            label="📥 전체 프롬프트 TXT",
            data=txt_content,
            file_name="all_prompts.txt",
            mime="text/plain",
            key="enh_dl_txt"
        )

    st.markdown("---")

    # 유형별 빠른 다운로드
    render_quick_prompt_downloads(scenes)

    st.markdown("---")

    # 상세 다운로드 옵션
    render_advanced_download_section(scenes)
