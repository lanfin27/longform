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
from utils.style_manager import get_style_manager
from components.style_selector import style_radio_selector, get_selected_style
from utils.pose_manager import PoseManager, get_pose_manager

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

st.title("👤 3.6단계: 캐릭터 관리")
st.caption("캐릭터 생성, 편집, 배치 이미지 생성")

st.divider()

# 캐릭터 매니저 초기화
manager = CharacterManager(str(project_path))

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

auto_sync_characters()

# === 씬 분석 데이터 로드 함수 (Problem 56) ===
def load_scene_analysis_data():
    """
    씬 분석 결과에서 씬별 분위기(mood) 정보 로드

    Returns:
        List[Dict]: [{'scene_number': 1, 'title': '...', 'mood': '정보 전달'}, ...]
    """
    scenes = []

    # 1. 세션에서 먼저 확인
    if "scene_analysis" in st.session_state and st.session_state.scene_analysis:
        raw_scenes = st.session_state.scene_analysis
        print(f"[씬 로드] 세션에서 {len(raw_scenes)}개 씬 발견")
    else:
        # 2. 파일에서 로드
        analysis_path = project_path / "analysis" / "scenes.json"
        if analysis_path.exists():
            try:
                with open(analysis_path, "r", encoding="utf-8") as f:
                    raw_scenes = json.load(f)
                print(f"[씬 로드] 파일에서 {len(raw_scenes)}개 씬 발견")
            except Exception as e:
                print(f"[씬 로드] 파일 로드 실패: {e}")
                raw_scenes = []
        else:
            raw_scenes = []

    # 3. 씬 데이터 정규화
    for i, scene in enumerate(raw_scenes):
        scene_data = {
            "scene_number": scene.get("scene_number", scene.get("id", i + 1)),
            "title": scene.get("title", scene.get("name", f"씬 {i+1}")),
            "mood": scene.get("mood", scene.get("분위기", "default")),
            "description": scene.get("description", scene.get("내용", ""))
        }
        scenes.append(scene_data)

    return scenes

# PoseManager 초기화
pose_manager = get_pose_manager()

# 탭 구성
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 캐릭터 목록", "➕ 캐릭터 추가", "🎨 배치 생성", "🧍 포즈 설정", "📥 가져오기"])

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
                for i in range(len(characters)):
                    st.session_state[f"del_char_{i}"] = True
                st.rerun()

        with col_sel2:
            if st.button("❎ 전체 해제", key="deselect_all_del"):
                for i in range(len(characters)):
                    st.session_state[f"del_char_{i}"] = False
                st.rerun()

        with col_sel3:
            # 선택된 캐릭터 수 계산
            selected_del_count = sum(
                1 for i in range(len(characters))
                if st.session_state.get(f"del_char_{i}", False)
            )

            if st.button(f"🗑️ 선택 삭제 ({selected_del_count}명)", key="delete_selected",
                        disabled=selected_del_count == 0, type="secondary"):
                st.session_state.show_bulk_delete_confirm = True

        # 삭제 확인 다이얼로그
        if st.session_state.get("show_bulk_delete_confirm", False):
            selected_indices = [
                i for i in range(len(characters))
                if st.session_state.get(f"del_char_{i}", False)
            ]
            selected_names = [characters[i].name for i in selected_indices]

            st.warning(f"⚠️ 다음 {len(selected_names)}명의 캐릭터를 삭제하시겠습니까?")
            st.write(", ".join(selected_names))

            col_confirm, col_cancel = st.columns(2)

            with col_confirm:
                if st.button("🗑️ 삭제 확인", type="primary", key="confirm_bulk_delete"):
                    # 역순으로 삭제
                    for idx in sorted(selected_indices, reverse=True):
                        manager.delete_character(characters[idx].id)

                    # 상태 초기화
                    st.session_state.show_bulk_delete_confirm = False
                    for i in range(len(characters)):
                        if f"del_char_{i}" in st.session_state:
                            del st.session_state[f"del_char_{i}"]

                    st.success(f"✅ {len(selected_names)}명의 캐릭터가 삭제되었습니다.")
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
                st.checkbox(
                    "",
                    key=f"del_char_{idx}",
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
                        # 생성된 이미지 표시
                        st.markdown("**생성된 이미지:**")
                        if char.generated_images:
                            for img_path in char.generated_images[-3:]:  # 최근 3개만
                                if Path(img_path).exists():
                                    st.image(img_path, use_container_width=True)
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

    with col1:
        st.markdown("#### 🧍 포즈")
        char_pose = st.selectbox(
            "기본 포즈",
            ["standing", "standing_left", "standing_right", "portrait"],
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
            ["solid_gray", "solid_white", "solid_blue"],
            format_func=lambda x: {
                "solid_gray": "단색 회색 (합성 추천)",
                "solid_white": "단색 흰색",
                "solid_blue": "단색 파랑"
            }.get(x, x),
            key="char_bg_select"
        )

    # 이미지 크기
    col_size1, col_size2 = st.columns(2)
    with col_size1:
        char_width = st.selectbox("너비", [1024, 768, 512], index=0, key="char_width")
    with col_size2:
        char_height = st.selectbox("높이", [1024, 768, 512], index=0, key="char_height")

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # ⭐ 새로 추가: API 선택 및 병렬 처리 설정
    # ═══════════════════════════════════════════════════════════════
    st.markdown("### 🔧 API 및 성능 설정")

    col_api1, col_api2 = st.columns(2)

    with col_api1:
        # API 제공자 선택
        api_options = ["Together.ai FLUX", "OpenAI DALL-E", "Stability AI", "Replicate SDXL"]
        char_api_provider = st.selectbox(
            "🔧 이미지 생성 API",
            options=api_options,
            index=0,
            key="char_api_provider",
            help="⚡ 빠른 생성: Together.ai FLUX\n🎨 고품질: OpenAI DALL-E\n🚀 초고속: Replicate Lightning"
        )

    with col_api2:
        # API별 모델 옵션
        model_options_map = {
            "Together.ai FLUX": [
                ("black-forest-labs/FLUX.1-schnell-Free", "FLUX Schnell (무료, 빠름)"),
                ("black-forest-labs/FLUX.1-schnell", "FLUX Schnell (유료)"),
                ("black-forest-labs/FLUX.1.1-pro", "FLUX Pro (고품질)"),
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
        char_model = st.selectbox(
            "🤖 모델",
            options=[o[0] for o in options],
            format_func=lambda x: next((o[1] for o in options if o[0] == x), x),
            key="char_model"
        )

    col_perf1, col_perf2 = st.columns(2)

    with col_perf1:
        # 병렬 처리 옵션
        char_parallel = st.slider(
            "⚡ 동시 생성 수",
            min_value=1,
            max_value=5,
            value=2,
            key="char_parallel",
            help="높을수록 빠르지만 API Rate Limit에 주의하세요.\n무료 API는 1~2 추천"
        )

    with col_perf2:
        # API 키 상태 확인
        api_key_status = "❓"
        if char_api_provider == "Together.ai FLUX":
            from config.settings import TOGETHER_API_KEY
            api_key_status = "✅ 설정됨" if TOGETHER_API_KEY else "❌ 미설정"
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

    # 프롬프트 없는 캐릭터 경고
    chars_without_prompt = [c for c in selected_chars if not c.character_prompt]
    if chars_without_prompt:
        st.warning(f"⚠️ {len(chars_without_prompt)}명의 캐릭터에 프롬프트가 없습니다: {', '.join([c.name for c in chars_without_prompt])}")

    # ═══════════════════════════════════════════════════════════════
    # ⭐ 포즈별 씬 선택 UI
    # ═══════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("### 🧍 포즈별 씬 설정")

    # 포즈 모드 선택
    pose_mode = st.radio(
        "포즈 설정 방식",
        ["단일 포즈 (모든 씬에 동일)", "포즈별 씬 선택 (씬마다 다른 포즈)"],
        horizontal=True,
        key="pose_mode"
    )

    from utils.character_scene_linker import POSE_OPTIONS, CharacterSceneLinker

    # 선택된 캐릭터의 등장 씬 수집
    all_appearance_scenes = set()
    char_scenes_map = {}

    for char in selected_chars:
        scenes = []
        if hasattr(char, 'appearance_scenes') and char.appearance_scenes:
            scenes = char.appearance_scenes
        elif hasattr(char, 'scenes') and char.scenes:
            scenes = char.scenes

        # 문자열/정수 변환
        scenes = [int(s) if isinstance(s, str) and s.isdigit() else s for s in scenes if s]
        scenes = [s for s in scenes if isinstance(s, int)]

        char_scenes_map[char.name] = scenes
        all_appearance_scenes.update(scenes)

    all_scenes = sorted(all_appearance_scenes)

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

    else:
        # 포즈별 씬 선택 UI
        if not all_scenes:
            st.warning("선택된 캐릭터에 등장 씬 정보가 없습니다. 씬 분석을 먼저 실행해주세요.")
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

    # API별 예상 시간
    time_per_char_map = {
        "Together.ai FLUX": 15 if "Free" in char_model else 8,
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

            # 설정 생성 (⭐ API 선택 + 병렬 처리 적용)
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
                parallel_count=char_parallel
            )

            generator = CharacterImageGenerator(str(project_path))

            generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 총 {total_chars}명 이미지 생성 시작")
            generation_logs.append(f"[{time.strftime('%H:%M:%S')}] API: {char_api_provider}, 병렬: {char_parallel}")
            generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 🔴 포즈: {char_pose}, 배경: {char_background}")

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

            # ⭐ 배치 생성 (콜백 포함)
            def on_batch_progress(current, total, result):
                update_progress_ui()

                # 이미지 미리보기
                if result.get("success") and result.get("image_path"):
                    image_preview.image(result["image_path"], caption=result.get("character_name", ""), width=300)

            results = generator.generate_batch(
                characters=char_dicts,
                config=config,
                output_dir=output_dir,
                on_progress=on_batch_progress,
                on_start=on_char_start,
                on_complete=on_char_complete
            )

            # 결과 처리
            scene_linker = CharacterSceneLinker(project_path)
            linked_count = 0

            for i, result in enumerate(results):
                char = selected_chars[i]
                elapsed = result.get("generation_time", 0)

                if result.get("success"):
                    success_count += 1

                    # 캐릭터에 이미지 경로 저장
                    manager.add_generated_image(char.id, result.get("image_path", ""))

                    # 이미지 스토리지에도 저장
                    save_character_image(char.name, result, project_path)

                    # 캐릭터 합성용 폴더에도 복사 (스토리보드 연동)
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
                    pose_mapping = st.session_state.get("pose_scene_mapping", {})
                    target_scenes = []

                    # 포즈별 씬 매핑에서 해당 캐릭터의 씬 찾기
                    for pose_key, pose_data in pose_mapping.items():
                        if char_pose == pose_key or pose_data.get("name") == char_pose:
                            target_scenes = pose_data.get("scenes", [])
                            break

                    # 씬 연결 시도
                    if target_scenes or char_scenes_map.get(char.name):
                        link_result = scene_linker.link_character_image_to_scenes(
                            character_name=char.name,
                            image_path=result.get("image_path", ""),
                            pose=char_pose,
                            specific_scenes=target_scenes if target_scenes else None
                        )
                        if link_result.get("success"):
                            linked_count += len(link_result.get("linked_scenes", []))
                            generation_logs.append(
                                f"[{time.strftime('%H:%M:%S')}] {char.name} → 씬 {link_result.get('linked_scenes', [])}에 연결됨"
                            )

                    # 사용량 기록
                    provider_name = "together" if char_api_provider == "Together.ai FLUX" else char_api_provider.lower().replace(" ", "_")
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
                    provider_name = "together" if char_api_provider == "Together.ai FLUX" else char_api_provider.lower().replace(" ", "_")
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
                st.balloons()
                update_project_step(3)
                time.sleep(1)
                st.rerun()

        except Exception as e:
            overall_status.error(f"❌ 오류 발생: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

    # 생성된 이미지 갤러리
    st.markdown("### 🖼️ 생성된 캐릭터 이미지")

    image_dir = project_path / "images" / "characters"
    if image_dir.exists():
        images = list(image_dir.glob("*.png"))

        if images:
            cols = st.columns(4)
            for i, img_path in enumerate(images):
                with cols[i % 4]:
                    st.image(str(img_path), caption=img_path.stem, use_container_width=True)

            st.info("💡 이제 '이미지 생성' 페이지에서 배경을 생성한 후 합성할 수 있습니다.")
        else:
            st.info("아직 생성된 캐릭터 이미지가 없습니다.")
    else:
        st.info("캐릭터 이미지 폴더가 없습니다.")

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

        analysis_chars = None
        data_source = None

        # 🔴 v3.11: 파일 우선 로드 (세션 상태보다 파일이 더 신뢰성 높음)
        # 1. 먼저 파일에서 로드 시도
        analysis_path = project_path / "analysis" / "characters.json"
        if analysis_path.exists():
            try:
                with open(analysis_path, "r", encoding="utf-8") as f:
                    file_chars = json.load(f)
                if file_chars and isinstance(file_chars, list) and len(file_chars) > 0:
                    analysis_chars = file_chars
                    data_source = f"📁 파일: {analysis_path.name}"
                    print(f"[캐릭터 관리] ✅ 파일에서 {len(analysis_chars)}개 캐릭터 로드: {analysis_path}")
            except Exception as e:
                print(f"[캐릭터 관리] ❌ 파일 로드 실패: {e}")

        # 2. 파일에서 못 찾으면 세션에서 로드 시도 (fallback)
        if not analysis_chars:
            session_keys = ["characters", "scene_characters", "extracted_characters"]
            for key in session_keys:
                if key in st.session_state and st.session_state[key]:
                    session_data = st.session_state[key]
                    if isinstance(session_data, list) and len(session_data) > 0:
                        analysis_chars = session_data
                        data_source = f"💾 세션: {key}"
                        print(f"[캐릭터 관리] ✅ 세션 '{key}'에서 {len(analysis_chars)}개 캐릭터 로드")
                        break

        # 3. 결과 표시
        if analysis_chars and len(analysis_chars) > 0:
            # visual_prompt 통계 계산
            chars_with_prompt = sum(1 for c in analysis_chars if c.get("visual_prompt") or c.get("character_prompt"))
            chars_without_prompt = len(analysis_chars) - chars_with_prompt

            st.success(f"📊 씬 분석에서 **{len(analysis_chars)}명**의 캐릭터가 발견되었습니다.")
            st.caption(f"📂 데이터 소스: {data_source}")

            if chars_without_prompt > 0:
                st.warning(f"⚠️ {chars_without_prompt}명의 캐릭터에 visual_prompt가 없습니다.")
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
            st.warning("⚠️ 씬 분석 결과가 없습니다. 3.5단계에서 먼저 씬 분석을 실행하세요.")
            st.page_link("pages/3.5_🎬_씬_분석.py", label="🎬 3.5단계: 씬 분석으로 이동", icon="➡️")

            # 🔴 v3.11: 향상된 디버그 정보
            with st.expander("🔍 디버그 정보"):
                st.write("**📁 파일 상태:**")
                if analysis_path.exists():
                    try:
                        with open(analysis_path, "r", encoding="utf-8") as f:
                            raw = json.load(f)
                        st.write(f"- {analysis_path.name}: 존재함 ({len(raw) if isinstance(raw, list) else 'dict'})")
                        if raw:
                            st.json(raw[:2] if isinstance(raw, list) else raw)
                    except Exception as e:
                        st.write(f"- {analysis_path.name}: 읽기 오류 - {e}")
                else:
                    st.write(f"- {analysis_path.name}: ❌ 파일 없음")

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

# 다음 단계 안내
st.divider()
st.info("👉 캐릭터 설정이 완료되면 4단계 TTS 생성으로 이동하세요.")
st.page_link("pages/4_🎤_TTS_생성.py", label="🎤 4단계: TTS 생성", icon="➡️")
