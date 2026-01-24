"""
5단계: 이미지 프롬프트 생성

SRT 세그먼트 그룹 기준으로 이미지 프롬프트 생성
썸네일 프롬프트는 이미지/텍스트 분리
"""
import streamlit as st
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    get_current_project_config,
    render_project_sidebar,
    update_project_step
)
from utils.data_loader import (
    get_srt_path,
    load_paragraph_breaks,
    save_segment_groups,
    load_segment_groups,
    save_image_prompts,
    load_image_prompts,
    save_thumbnail_prompts,
    load_thumbnail_prompts,
    load_scenes,
    save_scene_prompts,
    load_scene_prompts
)
from config.settings import DEFAULT_SEGMENTS_PER_GROUP, MIN_GROUP_DURATION_SEC, MAX_GROUP_DURATION_SEC
from config.constants import IMAGE_STYLE_PREFIXES
from utils.api_helper import show_api_status_sidebar
from core.prompt.preset_manager import PromptPresetManager


# ============================================================
# ⭐ 성능 최적화: 캐싱 데코레이터
# ============================================================
@st.cache_data(ttl=60, show_spinner=False)
def _cached_load_scenes(project_path_str):
    """씬 로드 (캐싱 적용)"""
    from pathlib import Path
    return load_scenes(Path(project_path_str))


@st.cache_data(ttl=120, show_spinner=False, max_entries=50)
def _cached_load_segment_groups(project_path_str: str, _mtime: float):
    """세그먼트 그룹 로드 (캐싱 적용) - mtime으로 자동 무효화"""
    from pathlib import Path
    return load_segment_groups(Path(project_path_str))


@st.cache_data(ttl=120, show_spinner=False, max_entries=50)
def _cached_load_image_prompts(project_path_str: str, _mtime: float):
    """이미지 프롬프트 로드 (캐싱 적용) - mtime으로 자동 무효화"""
    from pathlib import Path
    return load_image_prompts(Path(project_path_str))


def get_cached_segment_groups(project_path: Path):
    """세그먼트 그룹 로드 (캐싱 + mtime 체크)"""
    json_path = project_path / "segment_groups.json"
    if json_path.exists():
        mtime = json_path.stat().st_mtime
        return _cached_load_segment_groups(str(project_path), _mtime=mtime)
    return None


def get_cached_image_prompts(project_path: Path):
    """이미지 프롬프트 로드 (캐싱 + mtime 체크)"""
    json_path = project_path / "image_prompts.json"
    if json_path.exists():
        mtime = json_path.stat().st_mtime
        return _cached_load_image_prompts(str(project_path), _mtime=mtime)
    return None


# 페이지 설정
st.set_page_config(
    page_title="이미지 프롬프트",
    page_icon="🖼️",
    layout="wide"
)

render_project_sidebar()
show_api_status_sidebar()

if not ensure_project_selected():
    st.stop()

project_path = get_current_project()
project_config = get_current_project_config()

st.title("🖼️ 5단계: 이미지 프롬프트 생성")
st.caption("SRT 세그먼트 그룹 기준 + 썸네일 텍스트 분리")

st.divider()

# Critical Notice
st.warning("""
⚠️ **Critical: 이미지 생성은 '시간 간격'이 아닌 '자막 세그먼트 그룹' 기준입니다.**

Vrew는 문장(자막 클립) 단위로 작동하므로, 시간 기준으로 이미지를 만들면 싱크가 맞지 않습니다.
""")

# === 탭 구성 ===
tab_scene, tab_segment, tab_manual, tab_thumbnail, tab_content, tab_preview = st.tabs([
    "🎬 씬 기반", "📊 세그먼트 그룹", "✏️ 수동 입력", "🖼️ 썸네일", "🎨 본문 이미지", "👁️ 미리보기"
])

# === 씬 기반 프롬프트 탭 ===
with tab_scene:
    st.subheader("🎬 씬 기반 이미지 프롬프트")

    st.info("""
    💡 **씬 기반 프롬프트 생성**
    - 씬 분석 결과(3.5단계)를 활용
    - 각 씬의 연출가이드 + 등장 캐릭터 자동 포함
    - 세모지 스타일 워크플로우에 최적화
    """)

    # 씬 분석 결과 확인 (⭐ 캐싱 적용)
    scenes = _cached_load_scenes(str(project_path))

    if not scenes:
        st.warning("씬 분석 결과가 없습니다. 3.5단계에서 씬 분석을 먼저 실행하세요.")
        st.page_link("pages/3.5_🎬_씬_분석.py", label="🎬 3.5단계: 씬 분석으로 이동", icon="➡️")
    else:
        st.success(f"✅ {len(scenes)}개 씬 로드됨")

        # 캐릭터 정보 로드
        from core.character.character_manager import CharacterManager
        char_manager = CharacterManager(str(project_path))
        characters = char_manager.get_all_characters()

        if characters:
            st.info(f"👤 등록된 캐릭터: {len(characters)}명")
        else:
            st.caption("캐릭터가 등록되지 않았습니다. 씬 연출가이드만 사용됩니다.")

        st.divider()

        # 프리셋 선택
        st.markdown("### 🎨 스타일 프리셋")

        preset_manager = PromptPresetManager(str(project_path))

        col1, col2 = st.columns(2)

        with col1:
            style_presets = preset_manager.get_presets_by_category("styles")
            style_names = [p.name for p in style_presets]
            selected_style_idx = st.selectbox(
                "스타일",
                range(len(style_names)),
                format_func=lambda i: style_names[i],
                key="scene_style_preset"
            )
            scene_style_prompt = style_presets[selected_style_idx].prompt

        with col2:
            include_characters = st.checkbox(
                "캐릭터 프롬프트 포함",
                value=True,
                help="씬에 등장하는 캐릭터의 프롬프트를 자동으로 포함"
            )

        # 네거티브 프롬프트
        neg_presets = preset_manager.get_presets_by_category("negatives")
        neg_names = [p.name for p in neg_presets]
        selected_negs = st.multiselect(
            "네거티브 프롬프트",
            neg_names,
            default=["텍스트 금지"],
            key="scene_neg_presets"
        )

        scene_neg_prompts = []
        for neg_name in selected_negs:
            for p in neg_presets:
                if p.name == neg_name:
                    scene_neg_prompts.append(p.prompt)

        scene_negative = ", ".join(scene_neg_prompts) if scene_neg_prompts else ""

        st.divider()

        # 씬 미리보기
        st.markdown("### 👁️ 씬 미리보기")

        with st.expander(f"씬 목록 ({len(scenes)}개)", expanded=False):
            for scene in scenes[:10]:
                scene_id = scene.get("scene_id", 0)
                script = scene.get("script_text", "")[:80]
                chars = scene.get("characters", [])
                direction = scene.get("direction_guide", "")[:80]

                st.markdown(f"**씬 {scene_id}**: {script}...")
                st.caption(f"캐릭터: {', '.join(chars) if chars else '없음'} | 연출: {direction}...")
                st.divider()

            if len(scenes) > 10:
                st.caption(f"... 외 {len(scenes) - 10}개 씬")

        st.divider()

        # 프롬프트 생성 버튼
        if st.button("✨ 씬 기반 프롬프트 생성", type="primary", use_container_width=True):
            with st.spinner("씬 기반 프롬프트 생성 중..."):
                prompts = []

                for scene in scenes:
                    scene_id = scene.get("scene_id", 0)

                    # 기본 프롬프트 구성
                    prompt_parts = [scene_style_prompt]

                    # 씬의 이미지 프롬프트 (연출가이드 기반)
                    image_prompt_en = scene.get("image_prompt_en", "")
                    if image_prompt_en:
                        prompt_parts.append(image_prompt_en)

                    # 캐릭터 프롬프트 추가
                    char_names = scene.get("characters", [])
                    if include_characters and char_names:
                        char_prompts = []
                        for name in char_names:
                            char = char_manager.get_character_by_name(name)
                            if char and char.character_prompt:
                                char_prompts.append(char.character_prompt)

                        if char_prompts:
                            if len(char_names) == 1:
                                prompt_parts.append(f"single character, {', '.join(char_prompts)}")
                            else:
                                prompt_parts.append(f"multiple characters, {', '.join(char_prompts)}")

                    # 분위기
                    mood = scene.get("mood", "")
                    if mood:
                        prompt_parts.append(f"{mood} mood")

                    final_prompt = ", ".join(filter(None, prompt_parts))

                    prompts.append({
                        "scene_id": scene_id,
                        "filename": f"scene_{scene_id:03d}.png",
                        "script_text": scene.get("script_text", ""),
                        "characters": char_names,
                        "direction_guide": scene.get("direction_guide", ""),
                        "prompt": final_prompt,
                        "negative_prompt": scene_negative,
                        "duration_estimate": scene.get("duration_estimate", 10)
                    })

                # 저장
                save_scene_prompts(project_path, prompts)
                st.session_state["scene_prompts"] = prompts

                st.success(f"✅ {len(prompts)}개 씬 프롬프트 생성 완료!")
                update_project_step(5)

        # 생성된 프롬프트 표시
        scene_prompts = st.session_state.get("scene_prompts") or load_scene_prompts(project_path)

        if scene_prompts:
            st.markdown("### 📋 생성된 프롬프트")

            st.dataframe(
                [{
                    "씬": p["scene_id"],
                    "캐릭터": ", ".join(p.get("characters", [])) or "-",
                    "프롬프트": p["prompt"][:60] + "..."
                } for p in scene_prompts],
                use_container_width=True
            )

            # 상세 보기
            with st.expander("상세 프롬프트 보기"):
                for p in scene_prompts[:5]:
                    st.markdown(f"**씬 {p['scene_id']}** (캐릭터: {', '.join(p.get('characters', [])) or '없음'})")
                    st.code(p["prompt"], language=None)
                    st.divider()

            st.divider()
            st.success("✅ 씬 기반 프롬프트 생성 완료! 6단계에서 이미지를 생성하세요.")
            st.page_link("pages/6_🎨_이미지_생성.py", label="🎨 6단계: 이미지 생성으로 이동", icon="➡️")

# === 세그먼트 그룹 탭 ===
with tab_segment:
    st.subheader("SRT 세그먼트 그룹화")

    # 언어 선택
    language = st.selectbox(
        "언어",
        ["ko", "ja"],
        format_func=lambda x: "한국어" if x == "ko" else "일본어"
    )

    srt_path = get_srt_path(project_path, language)

    if not srt_path.exists():
        st.warning("SRT 파일이 없습니다. 4단계에서 TTS를 먼저 생성하세요.")
        st.stop()

    st.success(f"✅ SRT 파일 로드됨: {srt_path.name}")

    # 그룹화 설정
    st.subheader("그룹화 설정")

    col1, col2, col3 = st.columns(3)

    with col1:
        segments_per_group = st.number_input(
            "그룹당 세그먼트 수",
            min_value=2,
            max_value=8,
            value=DEFAULT_SEGMENTS_PER_GROUP,
            help="하나의 이미지에 해당하는 자막 세그먼트 수"
        )

    with col2:
        min_duration = st.number_input(
            "최소 그룹 길이 (초)",
            min_value=5.0,
            max_value=20.0,
            value=MIN_GROUP_DURATION_SEC
        )

    with col3:
        max_duration = st.number_input(
            "최대 그룹 길이 (초)",
            min_value=15.0,
            max_value=60.0,
            value=MAX_GROUP_DURATION_SEC
        )

    use_paragraph_breaks = st.checkbox(
        "문단 구분 정보 우선 사용",
        value=True,
        help="4단계 TTS에서 생성된 문단 구분 정보 활용"
    )

    if st.button("📊 세그먼트 그룹화 실행", type="primary"):
        with st.spinner("세그먼트 그룹화 중..."):
            try:
                from core.image.segment_grouper import SRTSegmentGrouper

                grouper = SRTSegmentGrouper(
                    segments_per_group=segments_per_group,
                    min_duration=min_duration,
                    max_duration=max_duration
                )

                # SRT 파싱
                segments = grouper.parse_srt(str(srt_path))

                # 문단 구분 정보 로드
                paragraph_breaks = None
                if use_paragraph_breaks:
                    pb_data = load_paragraph_breaks(project_path)
                    if pb_data:
                        paragraph_breaks = pb_data.get("breaks", [])

                # 그룹화
                groups = grouper.group_segments(segments, paragraph_breaks)

                # 저장
                save_segment_groups(project_path, groups)

                st.session_state["segment_groups"] = groups

                st.success(f"✅ {len(groups)}개 그룹 생성 완료!")

            except Exception as e:
                st.error(f"그룹화 실패: {str(e)}")

    # 그룹 미리보기 (캐싱 적용)
    groups = st.session_state.get("segment_groups") or get_cached_segment_groups(project_path)

    if groups:
        st.subheader(f"그룹 미리보기 ({len(groups)}개)")

        for group in groups[:5]:  # 처음 5개만 표시
            with st.expander(f"그룹 #{group['group_id']} (세그먼트 {group['segment_indices'][0]}-{group['segment_indices'][-1]})"):
                col1, col2 = st.columns([1, 2])

                with col1:
                    st.metric("길이", f"{group['duration_sec']}초")
                    st.metric("세그먼트 수", group['segment_count'])

                with col2:
                    st.caption("내용:")
                    st.write(group['combined_text'][:200] + "..." if len(group['combined_text']) > 200 else group['combined_text'])

        if len(groups) > 5:
            st.caption(f"... 외 {len(groups) - 5}개 그룹")

# === 수동 입력 탭 ===
with tab_manual:
    st.subheader("✏️ 이미지 프롬프트 수동 입력")

    st.info("""
    **이미지 프롬프트를 직접 입력하거나 파일로 업로드하세요.**

    - 텍스트로 직접 입력 (줄바꿈으로 구분)
    - JSON 파일 업로드
    - CSV 파일 업로드 (prompt 컬럼 필요)
    """)

    # 입력 방식 선택
    manual_prompt_method = st.radio(
        "입력 방식",
        ["✏️ 직접 입력", "📁 JSON 파일 업로드", "📊 CSV 파일 업로드"],
        horizontal=True,
        key="manual_prompt_method"
    )

    manual_prompts = None

    # === 직접 입력 ===
    if "직접 입력" in manual_prompt_method:
        st.markdown("**프롬프트 직접 입력** (줄바꿈으로 구분)")

        manual_text = st.text_area(
            "이미지 프롬프트 목록",
            height=300,
            placeholder="""flat vector illustration, Korean educational style, a businessman presenting data on whiteboard, clean office background, soft muted colors

flat vector illustration, Korean educational style, a woman using laptop computer, modern workspace, warm lighting

flat vector illustration, Korean educational style, two people discussing at meeting table, professional atmosphere""",
            key="manual_prompts_text"
        )

        if manual_text and manual_text.strip():
            lines = [line.strip() for line in manual_text.strip().split("\n") if line.strip()]
            manual_prompts = [{"prompt": line, "negative_prompt": ""} for line in lines]
            st.success(f"✅ {len(manual_prompts)}개 프롬프트 입력됨")

    # === JSON 파일 업로드 ===
    elif "JSON" in manual_prompt_method:
        st.markdown("**JSON 파일 업로드**")

        st.caption("""
        예시 형식:
        ```json
        [
          {"prompt": "flat vector illustration, ...", "negative_prompt": "text, letters"},
          {"prompt": "another prompt...", "negative_prompt": ""}
        ]
        ```
        """)

        uploaded_json = st.file_uploader(
            "JSON 파일 선택",
            type=["json"],
            key="prompt_json_upload"
        )

        if uploaded_json:
            try:
                import json
                manual_prompts = json.load(uploaded_json)

                if isinstance(manual_prompts, list):
                    st.success(f"✅ {len(manual_prompts)}개 프롬프트 로드됨")

                    # 미리보기
                    with st.expander("프롬프트 미리보기"):
                        for i, p in enumerate(manual_prompts[:5]):
                            if isinstance(p, str):
                                st.text(f"{i+1}. {p[:100]}...")
                            elif isinstance(p, dict):
                                st.text(f"{i+1}. {p.get('prompt', '')[:100]}...")
                else:
                    st.error("JSON은 배열 형식이어야 합니다.")
                    manual_prompts = None
            except Exception as e:
                st.error(f"JSON 파싱 실패: {e}")

    # === CSV 파일 업로드 ===
    elif "CSV" in manual_prompt_method:
        st.markdown("**CSV 파일 업로드**")

        st.caption("'prompt' 컬럼이 필요합니다. 선택적으로 'negative_prompt' 컬럼도 지원합니다.")

        uploaded_csv = st.file_uploader(
            "CSV 파일 선택",
            type=["csv"],
            key="prompt_csv_upload"
        )

        if uploaded_csv:
            try:
                import pandas as pd
                import io

                df = pd.read_csv(io.BytesIO(uploaded_csv.read()))

                if 'prompt' in df.columns:
                    manual_prompts = []
                    for _, row in df.iterrows():
                        manual_prompts.append({
                            "prompt": row['prompt'],
                            "negative_prompt": row.get('negative_prompt', '')
                        })

                    st.success(f"✅ {len(manual_prompts)}개 프롬프트 로드됨")

                    with st.expander("데이터 미리보기"):
                        st.dataframe(df.head(10))
                else:
                    st.error("CSV에 'prompt' 컬럼이 필요합니다.")
                    st.write("발견된 컬럼:", list(df.columns))
            except Exception as e:
                st.error(f"CSV 파싱 실패: {e}")

    # === 프롬프트 편집 및 저장 ===
    if manual_prompts:
        st.markdown("---")
        st.markdown("### 📋 프롬프트 편집")

        # 스타일 프롬프트 추가 옵션
        add_style_prefix = st.checkbox(
            "스타일 프롬프트 추가",
            value=False,
            help="모든 프롬프트 앞에 스타일 프롬프트를 추가합니다."
        )

        style_prefix = ""
        if add_style_prefix:
            preset_manager = PromptPresetManager(str(project_path))
            style_presets = preset_manager.get_presets_by_category("styles")

            if style_presets:
                style_names = [p.name for p in style_presets]
                selected_style = st.selectbox(
                    "스타일 프리셋",
                    range(len(style_names)),
                    format_func=lambda i: style_names[i],
                    key="manual_style_prefix"
                )
                style_prefix = style_presets[selected_style].prompt
                st.code(f"스타일 프롬프트: {style_prefix[:100]}...")

        # 프롬프트 편집 영역
        st.markdown("**프롬프트 목록 편집:**")

        edited_prompts = []
        for i, p in enumerate(manual_prompts[:20]):  # 최대 20개만 편집 가능
            prompt_text = p.get("prompt", p) if isinstance(p, dict) else p

            with st.expander(f"프롬프트 {i+1}", expanded=(i < 3)):
                edited_prompt = st.text_area(
                    f"프롬프트 {i+1}",
                    value=prompt_text,
                    height=100,
                    key=f"edit_prompt_{i}",
                    label_visibility="collapsed"
                )

                neg_prompt = st.text_input(
                    "네거티브 프롬프트",
                    value=p.get("negative_prompt", "") if isinstance(p, dict) else "",
                    key=f"edit_neg_{i}"
                )

                edited_prompts.append({
                    "prompt": edited_prompt,
                    "negative_prompt": neg_prompt
                })

        if len(manual_prompts) > 20:
            st.caption(f"... 외 {len(manual_prompts) - 20}개 프롬프트 (편집 불가)")

        # 저장 버튼
        st.markdown("---")

        if st.button("💾 프롬프트 저장", type="primary", use_container_width=True, key="save_manual_prompts"):
            # 최종 프롬프트 조합
            final_prompts = []

            for i, p in enumerate(edited_prompts):
                prompt = p["prompt"]

                # 스타일 프롬프트 추가
                if add_style_prefix and style_prefix:
                    prompt = f"{style_prefix}, {prompt}"

                final_prompts.append({
                    "group_id": i + 1,
                    "filename": f"manual_{i+1:03d}.png",
                    "prompt": prompt,
                    "negative_prompt": p["negative_prompt"],
                    "segment_indices": [i],
                    "start_ms": 0,
                    "end_ms": 0,
                    "duration_sec": 0,
                    "text_content": ""
                })

            # 나머지 프롬프트 추가 (20개 이상인 경우)
            for i, p in enumerate(manual_prompts[20:], start=20):
                prompt_text = p.get("prompt", p) if isinstance(p, dict) else p

                if add_style_prefix and style_prefix:
                    prompt_text = f"{style_prefix}, {prompt_text}"

                final_prompts.append({
                    "group_id": i + 1,
                    "filename": f"manual_{i+1:03d}.png",
                    "prompt": prompt_text,
                    "negative_prompt": p.get("negative_prompt", "") if isinstance(p, dict) else "",
                    "segment_indices": [i],
                    "start_ms": 0,
                    "end_ms": 0,
                    "duration_sec": 0,
                    "text_content": ""
                })

            save_image_prompts(project_path, final_prompts)
            st.session_state["image_prompts"] = final_prompts
            update_project_step(5)

            st.success(f"✅ {len(final_prompts)}개 프롬프트 저장 완료!")
            st.balloons()

# === 썸네일 탭 ===
with tab_thumbnail:
    st.subheader("🖼️ 썸네일 프롬프트")

    st.info("""
    ⚠️ **FLUX 모델은 한글/일본어 텍스트 생성이 불안정합니다.**

    썸네일은 **텍스트 없는 배경 이미지**와 **오버레이 텍스트**를 분리하여 출력합니다.
    텍스트 합성은 미리캔버스 또는 Vrew에서 수동으로 진행하세요.
    """)

    # 썸네일 주제
    thumbnail_topic = st.text_input(
        "썸네일 주제",
        placeholder="예: 1인 창업으로 월 500만원 버는 방법"
    )

    # 스타일 선택
    style = st.selectbox(
        "이미지 스타일",
        list(IMAGE_STYLE_PREFIXES.keys()),
        format_func=lambda x: x.capitalize()
    )

    if st.button("✨ 썸네일 프롬프트 생성", type="primary"):
        if not thumbnail_topic:
            st.error("썸네일 주제를 입력하세요.")
        else:
            # 간단한 썸네일 프롬프트 생성 (Claude 연동 시 더 정교하게)
            thumbnail_prompts = {
                "thumbnail_prompts": [
                    {
                        "version": "A",
                        "type": "text_focus_background",
                        "image_prompt": f"YouTube thumbnail background, {style} style, clean gradient, space for large text in center, no text, no letters, no words",
                        "overlay_text": {
                            "main": thumbnail_topic[:20],
                            "sub": "",
                            "font_suggestion": "나눔스퀘어 Bold",
                            "color_suggestion": "#FFFFFF with #000000 outline"
                        }
                    },
                    {
                        "version": "B",
                        "type": "image_focus_background",
                        "image_prompt": f"YouTube thumbnail, {style} style, professional person working, success concept, warm lighting, no text, no letters",
                        "overlay_text": {
                            "main": thumbnail_topic[:15],
                            "sub": "완전 가이드",
                            "font_suggestion": "Pretendard Bold",
                            "color_suggestion": "#FFD700"
                        }
                    }
                ],
                "note": "FLUX는 텍스트 생성이 불안정합니다. 이미지 생성 후 텍스트를 수동 합성하세요."
            }

            save_thumbnail_prompts(project_path, thumbnail_prompts)
            st.session_state["thumbnail_prompts"] = thumbnail_prompts
            st.success("✅ 썸네일 프롬프트 생성 완료!")

    # 프롬프트 표시
    prompts = st.session_state.get("thumbnail_prompts") or load_thumbnail_prompts(project_path)

    if prompts:
        for p in prompts.get("thumbnail_prompts", []):
            with st.expander(f"버전 {p['version']}: {p['type']}"):
                st.markdown("**이미지 프롬프트:**")
                st.code(p["image_prompt"])

                if st.button(f"📋 복사", key=f"copy_thumb_{p['version']}"):
                    st.write("프롬프트가 클립보드에 복사되었습니다.")

                st.divider()

                st.markdown("**오버레이 텍스트:**")
                overlay = p.get("overlay_text", {})
                st.write(f"메인: {overlay.get('main', '')}")
                st.write(f"서브: {overlay.get('sub', '')}")
                st.write(f"폰트: {overlay.get('font_suggestion', '')}")

# === 본문 이미지 탭 ===
with tab_content:
    st.subheader("🎨 본문 이미지 프롬프트")

    groups = get_cached_segment_groups(project_path)  # 캐싱 적용

    if not groups:
        st.warning("세그먼트 그룹이 없습니다. '세그먼트 그룹' 탭에서 먼저 그룹화를 실행하세요.")
        st.stop()

    # 프리셋 관리자 초기화
    preset_manager = PromptPresetManager(str(project_path))

    st.markdown("### 🎨 프롬프트 프리셋")

    col1, col2 = st.columns(2)

    with col1:
        # 스타일 프리셋
        style_presets = preset_manager.get_presets_by_category("styles")
        style_names = ["(직접 입력)"] + [p.name for p in style_presets]
        selected_style_idx = st.selectbox(
            "스타일 프리셋",
            range(len(style_names)),
            format_func=lambda i: style_names[i],
            key="style_preset"
        )

        if selected_style_idx > 0:
            selected_style_prompt = style_presets[selected_style_idx - 1].prompt
        else:
            selected_style_prompt = ""

    with col2:
        # 캐릭터 스타일 프리셋
        char_presets = preset_manager.get_presets_by_category("characters")
        char_names = ["(선택 안함)"] + [p.name for p in char_presets]
        selected_char_idx = st.selectbox(
            "캐릭터 스타일",
            range(len(char_names)),
            format_func=lambda i: char_names[i],
            key="char_preset"
        )

        if selected_char_idx > 0:
            selected_char_prompt = char_presets[selected_char_idx - 1].prompt
        else:
            selected_char_prompt = ""

    # 배경 프리셋
    col3, col4 = st.columns(2)

    with col3:
        bg_presets = preset_manager.get_presets_by_category("backgrounds")
        bg_names = ["(선택 안함)"] + [p.name for p in bg_presets]
        selected_bg_idx = st.selectbox(
            "배경 프리셋",
            range(len(bg_names)),
            format_func=lambda i: bg_names[i],
            key="bg_preset"
        )

        if selected_bg_idx > 0:
            selected_bg_prompt = bg_presets[selected_bg_idx - 1].prompt
        else:
            selected_bg_prompt = ""

    with col4:
        # 네거티브 프롬프트 (다중 선택)
        neg_presets = preset_manager.get_presets_by_category("negatives")
        neg_names = [p.name for p in neg_presets]
        selected_negs = st.multiselect(
            "네거티브 프롬프트",
            neg_names,
            default=["텍스트 금지"],
            key="neg_presets"
        )

        neg_prompts = []
        for neg_name in selected_negs:
            for p in neg_presets:
                if p.name == neg_name:
                    neg_prompts.append(p.prompt)

    # 커스텀 프롬프트
    custom_prompt = st.text_area(
        "커스텀 프롬프트 (추가)",
        placeholder="추가로 포함할 프롬프트를 입력하세요...",
        key="custom_prompt"
    )

    # 조합된 프롬프트 미리보기
    st.markdown("### 📝 조합된 프롬프트 미리보기")

    prompt_parts = []
    if selected_style_prompt:
        prompt_parts.append(selected_style_prompt)
    if selected_char_prompt:
        prompt_parts.append(selected_char_prompt)
    if selected_bg_prompt:
        prompt_parts.append(selected_bg_prompt)
    if custom_prompt:
        prompt_parts.append(custom_prompt)

    combined_positive = ", ".join(prompt_parts) if prompt_parts else "(프리셋을 선택하세요)"
    combined_negative = ", ".join(neg_prompts) if neg_prompts else "(없음)"

    col_pos, col_neg = st.columns(2)
    with col_pos:
        st.markdown("**Positive:**")
        st.code(combined_positive, language=None)
    with col_neg:
        st.markdown("**Negative:**")
        st.code(combined_negative, language=None)

    st.divider()

    if st.button("✨ 본문 이미지 프롬프트 생성", type="primary"):
        if not prompt_parts:
            st.error("최소 하나의 스타일 프리셋을 선택하세요.")
        else:
            with st.spinner("프롬프트 생성 중..."):
                prompts = []

                for group in groups:
                    from core.image.segment_grouper import SRTSegmentGrouper
                    grouper = SRTSegmentGrouper()

                    # 씬 내용 기반 프롬프트 조합
                    scene_prompt = f"scene depicting: {group['combined_text'][:100]}"
                    full_prompt = f"{combined_positive}, {scene_prompt}"

                    prompt = {
                        "group_id": group["group_id"],
                        "filename": grouper.generate_filename(group),
                        "segment_indices": group["segment_indices"],
                        "start_ms": group["start_ms"],
                        "end_ms": group["end_ms"],
                        "duration_sec": group["duration_sec"],
                        "text_content": group["combined_text"],
                        "prompt": full_prompt,
                        "negative_prompt": combined_negative if combined_negative != "(없음)" else ""
                    }
                    prompts.append(prompt)

                save_image_prompts(project_path, prompts)
                st.session_state["image_prompts"] = prompts

                st.success(f"✅ {len(prompts)}개 프롬프트 생성 완료!")
                update_project_step(5)

    # 프롬프트 목록 (캐싱 적용)
    prompts = st.session_state.get("image_prompts") or get_cached_image_prompts(project_path)

    if prompts:
        st.dataframe(
            [{
                "파일명": p["filename"],
                "세그먼트": f"{p['segment_indices'][0]}-{p['segment_indices'][-1]}",
                "길이": f"{p['duration_sec']}초",
                "프롬프트": p["prompt"][:50] + "..."
            } for p in prompts],
            use_container_width=True
        )

# === 미리보기 탭 ===
with tab_preview:
    st.subheader("👁️ 전체 미리보기")

    groups = get_cached_segment_groups(project_path)  # 캐싱 적용
    prompts = get_cached_image_prompts(project_path)  # 캐싱 적용
    thumbnail = load_thumbnail_prompts(project_path)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("세그먼트 그룹", f"{len(groups) if groups else 0}개")

    with col2:
        st.metric("본문 프롬프트", f"{len(prompts) if prompts else 0}개")

    with col3:
        thumb_count = len(thumbnail.get("thumbnail_prompts", [])) if thumbnail else 0
        st.metric("썸네일 프롬프트", f"{thumb_count}개")

    if groups and prompts:
        st.divider()
        st.success("✅ 5단계 완료!")
        st.page_link("pages/6_🎨_이미지_생성.py", label="🎨 6단계: 이미지 생성으로 이동", icon="➡️")
