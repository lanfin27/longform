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
from utils.style_manager import get_style_manager, get_styles_by_segment, get_default_style
from components.style_selector import style_radio_selector, get_selected_style
from utils.pose_manager import PoseManager, get_pose_manager
from utils.scene_character_loader import (
    load_scenes_data,
    get_character_appearances,
    get_all_characters_from_scenes,
    build_character_scene_map,
    sync_character_appearance_scenes
)
from components.image_viewer import (
    render_lightbox_container,
    render_lightbox_image,
    clickable_image
)

# 대표 캐릭터 시스템
from utils.representative_character import (
    RepresentativeCharacter,
    RepresentativeCharacterManager,
    SceneCharacterAction,
    STYLE_PRESETS,
    BASE_IMAGE_TYPES,
    get_rep_char_manager
)

# 대표 캐릭터 라이브러리 (다중 캐릭터 관리)
from utils.rep_char_library import (
    get_rep_char_library,
    get_selected_rep_char,
    get_selected_rep_char_id
)
from utils.character_action_generator import (
    CharacterActionGenerator,
    get_available_models as get_action_ai_models
)

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

# Lightbox 컨테이너 초기화 (페이지당 한 번)
render_lightbox_container()

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

# === 씬-캐릭터 등장 정보 자동 동기화 (Problem 56 수정) ===
# 씬 데이터에서 캐릭터 등장 정보를 추출하여 appearance_scenes 업데이트
try:
    synced_count = sync_character_appearance_scenes(str(project_path))
    if synced_count > 0:
        print(f"[캐릭터 관리] ✅ {synced_count}명 캐릭터 appearance_scenes 동기화 완료")
        # CharacterManager도 다시 로드하여 반영
        manager = CharacterManager(str(project_path))
except Exception as e:
    print(f"[캐릭터 관리] ⚠️ 씬-캐릭터 동기화 오류: {e}")

# === 씬 분석 데이터 로드 함수 (v2.0 - 최신 파일 자동 감지) ===
from datetime import datetime


def load_scene_analysis_data(force_refresh: bool = False) -> tuple:
    """
    최신 씬 분석 결과 로드 (v2.0)

    ⭐ 개선사항:
    1. 여러 분석 파일 중 최신(수정 시간 기준) 파일 선택
    2. 파일 수정 시간 반환
    3. 캐시 무시 옵션

    Returns:
        Tuple[List[Dict], str]: (씬 데이터 리스트, 파일 수정 시간 문자열)
    """
    # 가능한 분석 파일 경로들
    analysis_paths = [
        # 1순위: analysis 폴더 (현재 구조)
        project_path / "analysis" / "scenes.json",
        project_path / "analysis" / "scene_analysis.json",
        project_path / "analysis" / "hybrid_v5_scenes.json",

        # 2순위: 프로젝트 루트
        project_path / "scenes.json",
        project_path / "data" / "scenes.json",
    ]

    # 새 구조 (videos 하위)인 경우
    video_name = st.session_state.get("current_video")
    if video_name:
        analysis_paths.insert(0, project_path / "videos" / video_name / "analysis" / "scenes.json")
        analysis_paths.insert(1, project_path / "videos" / video_name / "analysis" / "scene_analysis.json")

    # ⭐ 존재하는 파일 중 가장 최근 수정된 파일 찾기
    latest_file = None
    latest_mtime = 0

    for path in analysis_paths:
        if path.exists():
            mtime = path.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = path

    if not latest_file:
        print(f"[씬 로드] ⚠️ 씬 분석 파일을 찾을 수 없습니다.")
        return [], None

    # 파일 로드
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 데이터 형식에 따라 처리
        if isinstance(data, list):
            raw_scenes = data
        elif isinstance(data, dict):
            raw_scenes = data.get('scenes', data.get('data', []))
        else:
            raw_scenes = []

        # 수정 시간 문자열
        mtime_str = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[씬 로드] ✅ 파일: {latest_file.name}")
        print(f"[씬 로드]    씬 개수: {len(raw_scenes)}개")
        print(f"[씬 로드]    수정 시간: {mtime_str}")

    except Exception as e:
        print(f"[씬 로드] ❌ 씬 분석 로드 실패: {e}")
        return [], None

    # 씬 데이터 정규화
    scenes = []
    for i, scene in enumerate(raw_scenes):
        scene_id = scene.get("scene_id", scene.get("scene_number", scene.get("id", i + 1)))
        if isinstance(scene_id, str) and scene_id.isdigit():
            scene_id = int(scene_id)

        scene_data = {
            "scene_number": scene_id,
            "scene_id": scene_id,
            "title": scene.get("title", scene.get("name", f"씬 {scene_id}")),
            "mood": scene.get("mood", scene.get("분위기", "default")),
            "description": scene.get("description", scene.get("내용", "")),
            "script_text": scene.get("script_text", scene.get("narration", "")),
            "characters": scene.get("characters", [])
        }
        scenes.append(scene_data)

    # 세션에 파일 정보 저장 (UI 표시용)
    st.session_state['scene_file_mtime'] = mtime_str
    st.session_state['scene_file_name'] = latest_file.name

    return scenes, mtime_str

# PoseManager 초기화
pose_manager = get_pose_manager()

# 탭 구성
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 캐릭터 목록",
    "➕ 캐릭터 추가",
    "🎨 배치 생성",
    "🧍 포즈 설정",
    "📥 가져오기",
    "⭐ 대표 캐릭터"
])

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
                for char in characters:
                    st.session_state[f"del_char_{char.id}"] = True
                st.rerun()

        with col_sel2:
            if st.button("❎ 전체 해제", key="deselect_all_del"):
                for char in characters:
                    st.session_state[f"del_char_{char.id}"] = False
                st.rerun()

        with col_sel3:
            # 선택된 캐릭터 수 계산 (ID 기반)
            selected_del_count = sum(
                1 for char in characters
                if st.session_state.get(f"del_char_{char.id}", False)
            )

            # 디버그 로그
            selected_debug = [char.name for char in characters if st.session_state.get(f"del_char_{char.id}", False)]
            print(f"[캐릭터 삭제] 선택된 캐릭터: {selected_debug} (총 {selected_del_count}명)")

            if st.button(f"🗑️ 선택 삭제 ({selected_del_count}명)", key="delete_selected",
                        disabled=selected_del_count == 0, type="secondary"):
                st.session_state.show_bulk_delete_confirm = True
                print(f"[캐릭터 삭제] 삭제 확인 다이얼로그 표시")

        # 삭제 확인 다이얼로그
        if st.session_state.get("show_bulk_delete_confirm", False):
            # ID 기반으로 선택된 캐릭터 찾기
            selected_chars = [
                char for char in characters
                if st.session_state.get(f"del_char_{char.id}", False)
            ]
            selected_names = [char.name for char in selected_chars]
            selected_ids = [char.id for char in selected_chars]

            print(f"[캐릭터 삭제] 확인 다이얼로그 - 선택된 ID: {selected_ids}")
            print(f"[캐릭터 삭제] 확인 다이얼로그 - 선택된 이름: {selected_names}")

            st.warning(f"⚠️ 다음 {len(selected_names)}명의 캐릭터를 삭제하시겠습니까?")
            st.write(", ".join(selected_names))

            col_confirm, col_cancel = st.columns(2)

            with col_confirm:
                if st.button("🗑️ 삭제 확인", type="primary", key="confirm_bulk_delete"):
                    print(f"[캐릭터 삭제] ⚡ 삭제 실행 시작")

                    # ID 기반으로 삭제 (순서 무관)
                    deleted_count = 0
                    for char in selected_chars:
                        print(f"[캐릭터 삭제] 삭제 중: {char.name} (id={char.id})")

                        success = manager.delete_character(char.id)
                        if success:
                            deleted_count += 1
                            print(f"[캐릭터 삭제] ✅ '{char.name}' 삭제 성공")
                        else:
                            print(f"[캐릭터 삭제] ❌ '{char.name}' 삭제 실패")

                    # 상태 초기화 (ID 기반)
                    st.session_state.show_bulk_delete_confirm = False
                    for char in characters:
                        key = f"del_char_{char.id}"
                        if key in st.session_state:
                            del st.session_state[key]

                    print(f"[캐릭터 삭제] ✅ 총 {deleted_count}명 삭제 완료")
                    st.success(f"✅ {deleted_count}명의 캐릭터가 삭제되었습니다.")
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
                # ⭐ ID 기반 키 사용으로 인덱스 변경 시에도 안정적
                st.checkbox(
                    "선택",
                    key=f"del_char_{char.id}",
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
                        # 생성된 이미지 표시 (작은 썸네일 - 클릭 시 확대)
                        st.markdown("**생성된 이미지:**")
                        if char.generated_images:
                            for img_idx, img_path in enumerate(char.generated_images[-3:]):  # 최근 3개만
                                if Path(img_path).exists():
                                    clickable_image(img_path, width=120, key=f"char_img_{char.id}_{img_idx}")
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
        api_options = ["Together.ai FLUX", "Google ImageFX", "OpenAI DALL-E", "Stability AI", "Replicate SDXL"]
        char_api_provider = st.selectbox(
            "🔧 이미지 생성 API",
            options=api_options,
            index=0,
            key="char_api_provider",
            help="⚡ 빠른 생성: Together.ai FLUX\n🆓 무료: Google ImageFX\n🎨 고품질: OpenAI DALL-E\n🚀 초고속: Replicate Lightning"
        )

    with col_api2:
        # API별 모델 옵션
        model_options_map = {
            "Together.ai FLUX": [
                ("black-forest-labs/FLUX.2-dev", "FLUX.2 Dev (권장, ~20원)"),
                ("black-forest-labs/FLUX.2-flex", "FLUX.2 Flex (~40원)"),
                ("black-forest-labs/FLUX.2-pro", "FLUX.2 Pro (고품질, ~40원)"),
            ],
            "Google ImageFX": [
                ("IMAGEN_4", "Imagen 4 (최신, 무료)"),
                ("IMAGEN_3_5", "Imagen 3.5 (무료)"),
                ("IMAGEN_3_1", "Imagen 3.1 (무료)"),
                ("IMAGEN_3", "Imagen 3.0 (무료)"),
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
        elif char_api_provider == "Google ImageFX":
            from config.settings import load_imagefx_cookie
            imagefx_cookie = st.session_state.get("imagefx_cookie") or load_imagefx_cookie()
            api_key_status = "✅ 쿠키 설정됨" if imagefx_cookie else "❌ 쿠키 미설정"
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

    # 포즈 모드 선택 (AI 자동 분석 옵션 추가)
    pose_mode = st.radio(
        "포즈 설정 방식",
        [
            "단일 포즈 (모든 씬에 동일)",
            "포즈별 씬 선택 (씬마다 다른 포즈)",
            "🤖 AI 자동 분석 (씬 내용 기반 추천)"
        ],
        horizontal=True,
        key="pose_mode"
    )

    from utils.character_scene_linker import POSE_OPTIONS, CharacterSceneLinker

    # === 선택된 캐릭터의 등장 씬 수집 (Problem 56 수정: 다중 소스 탐색) ===
    all_appearance_scenes = set()
    char_scenes_map = {}

    # 씬 데이터에서 캐릭터별 등장 정보 미리 빌드 (폴백용)
    scene_based_char_map = build_character_scene_map()

    for char in selected_chars:
        scenes = []

        # 1. CharacterManager에서 appearance_scenes 확인
        if hasattr(char, 'appearance_scenes') and char.appearance_scenes:
            scenes = char.appearance_scenes
        elif hasattr(char, 'scenes') and char.scenes:
            scenes = char.scenes

        # 2. 씬 데이터에서 폴백 조회 (appearance_scenes가 없는 경우)
        if not scenes:
            # 유연한 이름 매칭
            char_name_normalized = char.name.strip().lower().replace(" ", "")
            for scene_char_name, scene_ids in scene_based_char_map.items():
                scene_char_normalized = scene_char_name.strip().lower().replace(" ", "")
                if (char_name_normalized == scene_char_normalized or
                    char_name_normalized in scene_char_normalized or
                    scene_char_normalized in char_name_normalized):
                    scenes = scene_ids
                    print(f"[포즈 설정] '{char.name}' → 씬 데이터에서 {scenes} 발견")
                    break

        # 문자열/정수 변환
        scenes = [int(s) if isinstance(s, str) and s.isdigit() else s for s in scenes if s]
        scenes = [s for s in scenes if isinstance(s, int)]

        char_scenes_map[char.name] = scenes
        all_appearance_scenes.update(scenes)

    all_scenes = sorted(all_appearance_scenes)

    # 디버그 로그
    print(f"[포즈 설정] 선택된 캐릭터: {len(selected_chars)}명")
    print(f"[포즈 설정] 수집된 등장 씬: {all_scenes}")

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

    elif "AI 자동 분석" in pose_mode:
        # ═══════════════════════════════════════════════════════════════
        # AI 자동 포즈 분석 (Problem 56: 새 기능)
        # ═══════════════════════════════════════════════════════════════
        from utils.pose_analyzer import (
            analyze_character_poses,
            AVAILABLE_POSES,
            get_pose_info
        )

        st.markdown("#### 🤖 AI 자동 포즈 분석")

        if not all_scenes:
            st.warning("⚠️ 씬 데이터가 없습니다. 씬 분석을 먼저 실행해주세요.")
        else:
            # AI 모델 선택
            col1, col2 = st.columns([3, 1])

            with col1:
                model_options = {
                    "Gemini 2.0 Flash Exp (무료, 추천)": "gemini-2.0-flash-exp",
                    "Gemini 2.0 Flash (무료)": "gemini-2.0-flash",
                    "Claude Sonnet 4 ($0.003/1K)": "claude-sonnet-4-20250514",
                    "Claude Haiku 3.5 ($0.001/1K)": "claude-3-5-haiku-latest",
                    "GPT-4o Mini ($0.00015/1K)": "gpt-4o-mini",
                }

                selected_model_label = st.selectbox(
                    "분석 AI 모델",
                    options=list(model_options.keys()),
                    index=0,
                    key="pose_analysis_model"
                )

                selected_model = model_options[selected_model_label]

            with col2:
                st.markdown("")
                st.markdown("")
                analyze_btn = st.button(
                    "🔍 AI 포즈 분석",
                    type="primary",
                    key="run_pose_analysis"
                )

            # 분석 실행
            if analyze_btn:
                # 씬 데이터 로드
                scenes_data = load_scenes_data(str(project_path))
                character_names = [char.name for char in selected_chars]

                progress = st.progress(0)
                status = st.empty()

                def update_progress(p):
                    progress.progress(p)

                def update_status(s):
                    status.text(s)

                with st.spinner("🤖 AI가 씬별 포즈를 분석하고 있습니다..."):
                    result = analyze_character_poses(
                        scenes=scenes_data,
                        characters=character_names,
                        model_id=selected_model,
                        progress_callback=update_progress,
                        status_callback=update_status
                    )

                progress.empty()
                status.empty()

                if result["success"]:
                    st.session_state.pose_analysis_result = result["pose_assignments"]
                    st.success(f"✅ 분석 완료! {len(result['pose_assignments'])}개 포즈 추천")
                else:
                    st.error(f"❌ 분석 실패: {result.get('error', '알 수 없는 오류')}")

            # 분석 결과 표시
            if "pose_analysis_result" in st.session_state and st.session_state.pose_analysis_result:
                st.markdown("---")
                st.markdown("#### 📊 AI 분석 결과")

                assignments = st.session_state.pose_analysis_result

                # 결과 테이블
                for i, assignment in enumerate(assignments):
                    scene_id = assignment.get("scene_id", 0)
                    char_name = assignment.get("character", "")
                    pose_id = assignment.get("pose", "standing")
                    reason = assignment.get("reason", "")

                    pose_info = AVAILABLE_POSES.get(pose_id, {"emoji": "🧍", "name": pose_id})
                    pose_emoji = pose_info.get("emoji", "🧍")
                    pose_name = pose_info.get("name", pose_id)

                    col1, col2, col3, col4 = st.columns([1, 2, 2, 3])

                    with col1:
                        st.write(f"**씬 {scene_id}**")

                    with col2:
                        st.write(f"👤 {char_name}")

                    with col3:
                        # 포즈 수정 가능
                        pose_options = list(AVAILABLE_POSES.keys())
                        current_idx = pose_options.index(pose_id) if pose_id in pose_options else 0

                        new_pose = st.selectbox(
                            "포즈",
                            options=pose_options,
                            index=current_idx,
                            format_func=lambda x: f"{AVAILABLE_POSES[x]['emoji']} {AVAILABLE_POSES[x]['name']}",
                            key=f"ai_pose_{scene_id}_{char_name}_{i}",
                            label_visibility="collapsed"
                        )

                        # 수정된 포즈 반영
                        assignment["pose"] = new_pose

                    with col4:
                        st.caption(reason if reason else "-")

                # 적용 버튼
                st.markdown("---")

                col1, col2 = st.columns(2)

                with col1:
                    if st.button("✅ 분석 결과 적용", type="primary", key="apply_ai_poses"):
                        # pose_scene_mapping 형식으로 변환
                        pose_scene_mapping = {}

                        for assignment in assignments:
                            pose_id = assignment.get("pose", "standing")
                            scene_id = assignment.get("scene_id", 0)

                            if pose_id not in pose_scene_mapping:
                                pose_info = AVAILABLE_POSES.get(pose_id, {})
                                pose_scene_mapping[pose_id] = {
                                    "name": pose_info.get("name", pose_id),
                                    "scenes": []
                                }

                            if scene_id not in pose_scene_mapping[pose_id]["scenes"]:
                                pose_scene_mapping[pose_id]["scenes"].append(scene_id)

                        st.session_state.pose_scene_mapping = pose_scene_mapping
                        st.success("✅ 포즈 설정이 적용되었습니다!")
                        st.rerun()

                with col2:
                    if st.button("🔄 다시 분석", key="reanalyze_poses"):
                        del st.session_state.pose_analysis_result
                        st.rerun()

    elif "포즈별 씬 선택" in pose_mode:
        # 포즈별 씬 선택 UI
        if not all_scenes:
            st.warning("""
            ⚠️ **선택된 캐릭터에 등장 씬 정보가 없습니다.**

            **해결 방법:**
            1. '씬 분석' 페이지에서 분석을 실행해주세요.
            2. 분석 완료 후 이 페이지를 새로고침하세요.
            """)

            # 디버깅 정보 표시
            with st.expander("🔧 디버깅 정보"):
                st.write("**선택된 캐릭터:**")
                for char in selected_chars:
                    app_scenes = getattr(char, 'appearance_scenes', [])
                    st.caption(f"  - {char.name}: appearance_scenes = {app_scenes}")

                st.write("**씬 데이터 상태:**")
                scenes_from_file = load_scenes_data(str(project_path))
                st.caption(f"  - 로드된 씬: {len(scenes_from_file)}개")

                if scenes_from_file:
                    all_chars_in_scenes = get_all_characters_from_scenes(scenes_from_file)
                    st.caption(f"  - 씬에 등장하는 캐릭터: {', '.join(all_chars_in_scenes[:5])}")
                else:
                    st.caption("  - ⚠️ 씬 분석 결과 없음")

                st.write("**프로젝트 경로:**")
                st.caption(f"  - {project_path}")
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

    # API별 예상 시간 (FLUX.2 모델 기준)
    time_per_char_map = {
        "Together.ai FLUX": 8,  # FLUX.2 유료 모델 기준
        "Google ImageFX": 10,  # Imagen 모델 (무료)
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

            # ═══════════════════════════════════════════════════════════════
            # ⭐ 포즈 모드에 따른 분기 처리
            # ═══════════════════════════════════════════════════════════════
            pose_mode = st.session_state.get("pose_mode", "")
            pose_analysis = st.session_state.get("pose_analysis_result", [])

            # ✅ 핵심 수정: AI 자동 분석 모드일 때만 ScenePoseGenerator 사용
            # "단일 포즈" 모드에서는 pose_analysis가 있어도 사용하지 않음!
            if pose_analysis and "AI 자동 분석" in pose_mode:
                # 씬별 포즈 이미지 생성 모드 (AI 분석 결과 사용)
                from utils.scene_pose_image_generator import ScenePoseImageGenerator

                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 🎭 AI 포즈 분석 결과 사용 - 씬별 이미지 생성")

                scene_pose_gen = ScenePoseImageGenerator(str(project_path))
                results = []

                for char_idx, char in enumerate(selected_chars):
                    char_name = char.name
                    visual_prompt = char.character_prompt

                    # 해당 캐릭터의 포즈 할당 필터
                    char_pose_assignments = [
                        p for p in pose_analysis
                        if p.get("character", "").strip().lower().replace(" ", "") in char_name.strip().lower().replace(" ", "")
                        or char_name.strip().lower().replace(" ", "") in p.get("character", "").strip().lower().replace(" ", "")
                    ]

                    if not char_pose_assignments:
                        generation_logs.append(f"[{time.strftime('%H:%M:%S')}] ⚠️ {char_name}: 포즈 분석 결과 없음")
                        results.append({
                            "success": False,
                            "character_name": char_name,
                            "error": "포즈 분석 결과 없음"
                        })
                        on_char_complete(char_name, 0, False, "포즈 분석 결과 없음")
                        continue

                    unique_poses = list(set(p.get("pose", "standing") for p in char_pose_assignments))
                    generation_logs.append(f"[{time.strftime('%H:%M:%S')}] {char_name}: {len(unique_poses)}개 포즈 발견 ({', '.join(unique_poses)})")

                    on_char_start(char_name)
                    char_start_time = time.time()

                    # 진행률 콜백
                    def pose_progress(current, total, msg):
                        progress_pct = (char_idx / total_chars) + (current / total) / total_chars
                        overall_progress_bar.progress(min(progress_pct, 1.0))
                        overall_status.text(f"[{char_idx + 1}/{total_chars}] {msg}")
                        generation_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
                        log_area.code("\n".join(generation_logs[-15:]))

                    # 씬별 포즈 이미지 생성
                    pose_result = scene_pose_gen.generate_scene_pose_images(
                        character_name=char_name,
                        visual_prompt=visual_prompt,
                        pose_assignments=char_pose_assignments,
                        image_generator=generator,
                        config=config,
                        on_progress=pose_progress
                    )

                    char_elapsed = time.time() - char_start_time
                    images_generated = pose_result.get("images_generated", 0)

                    if images_generated > 0:
                        # 생성된 모든 이미지를 결과에 추가
                        for pose_id, img_path in pose_result.get("pose_images", {}).items():
                            if img_path:
                                results.append({
                                    "success": True,
                                    "character_name": char_name,
                                    "image_path": img_path,
                                    "pose": pose_id,
                                    "generation_time": char_elapsed / max(images_generated, 1)
                                })

                                # 이미지 미리보기
                                if Path(img_path).exists():
                                    image_preview.image(img_path, caption=f"{char_name} ({pose_id})", width=300)

                        generation_logs.append(f"[{time.strftime('%H:%M:%S')}] ✅ {char_name}: {images_generated}개 이미지 생성 완료 ({char_elapsed:.1f}초)")
                        on_char_complete(char_name, char_elapsed, True)
                    else:
                        results.append({
                            "success": False,
                            "character_name": char_name,
                            "error": "이미지 생성 실패"
                        })
                        generation_logs.append(f"[{time.strftime('%H:%M:%S')}] ❌ {char_name}: 이미지 생성 실패")
                        on_char_complete(char_name, char_elapsed, False, "이미지 생성 실패")

                    update_progress_ui()

            else:
                # ═══════════════════════════════════════════════════════════════
                # 기존 단일 포즈 배치 생성
                # ═══════════════════════════════════════════════════════════════
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 📷 단일 포즈 모드 - 모든 캐릭터에 '{char_pose}' 적용")

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

            # 캐릭터 이름 → ID 맵핑 생성
            char_name_to_id = {char.name: char.id for char in selected_chars}
            char_name_to_obj = {char.name: char for char in selected_chars}
            processed_chars = set()  # 이미 처리된 캐릭터 (성공)

            for result in results:
                char_name = result.get("character_name", "")
                elapsed = result.get("generation_time", 0)

                # 캐릭터 객체 찾기
                char = char_name_to_obj.get(char_name)
                if not char:
                    # 부분 매칭 시도
                    for c in selected_chars:
                        if char_name.strip().lower() in c.name.strip().lower() or c.name.strip().lower() in char_name.strip().lower():
                            char = c
                            break

                if result.get("success"):
                    success_count += 1
                    if char:
                        processed_chars.add(char.name)

                        # 캐릭터에 이미지 경로 저장
                        manager.add_generated_image(char.id, result.get("image_path", ""))

                        # 이미지 스토리지에도 저장
                        save_character_image(char_name, result, project_path)

                        # 캐릭터 합성용 폴더에도 복사 (스토리보드 연동) - 첫 번째 이미지만
                        if char.name not in [c.name for c in selected_chars if char_name_to_id.get(c.name) and (project_path / "characters" / f"{char_name_to_id.get(c.name)}.png").exists()]:
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
                    result_pose = result.get("pose", char_pose)

                    # AI 분석 결과에서 이 포즈에 해당하는 씬 찾기
                    target_scenes = []
                    if pose_analysis:
                        for assignment in pose_analysis:
                            if (assignment.get("pose") == result_pose and
                                (assignment.get("character", "").strip().lower() in char_name.strip().lower() or
                                 char_name.strip().lower() in assignment.get("character", "").strip().lower())):
                                scene_id = assignment.get("scene_id")
                                if scene_id and scene_id not in target_scenes:
                                    target_scenes.append(scene_id)
                    else:
                        # 기존 pose_mapping 사용
                        pose_mapping = st.session_state.get("pose_scene_mapping", {})
                        for pose_key, pose_data in pose_mapping.items():
                            if result_pose == pose_key or pose_data.get("name") == result_pose:
                                target_scenes = pose_data.get("scenes", [])
                                break

                    # 씬 연결 시도
                    if target_scenes or (char and char_scenes_map.get(char.name)):
                        link_result = scene_linker.link_character_image_to_scenes(
                            character_name=char_name,
                            image_path=result.get("image_path", ""),
                            pose=result_pose,
                            specific_scenes=target_scenes if target_scenes else None
                        )
                        if link_result.get("success"):
                            linked_count += len(link_result.get("linked_scenes", []))
                            generation_logs.append(
                                f"[{time.strftime('%H:%M:%S')}] {char_name} ({result_pose}) → 씬 {link_result.get('linked_scenes', [])}에 연결됨"
                            )

                    # 사용량 기록
                    provider_name_map = {"Together.ai FLUX": "together", "Google ImageFX": "imagefx"}
                    provider_name = provider_name_map.get(char_api_provider, char_api_provider.lower().replace(" ", "_"))
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
                    provider_name_map = {"Together.ai FLUX": "together", "Google ImageFX": "imagefx"}
                    provider_name = provider_name_map.get(char_api_provider, char_api_provider.lower().replace(" ", "_"))
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
                # 대표 이미지 자동 업데이트
                from utils.character_image_manager import CharacterImageManager
                img_mgr = CharacterImageManager(str(project_path))
                img_mgr.update_character_data_with_latest_images()
                generation_logs.append(f"[{time.strftime('%H:%M:%S')}] 대표 이미지 자동 업데이트 완료")

                st.balloons()
                update_project_step(3)
                time.sleep(1)
                st.rerun()

        except Exception as e:
            overall_status.error(f"❌ 오류 발생: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

    # ================================================================
    # 생성된 이미지 갤러리 (개선: 전체 선택, 일괄 삭제, 대표 이미지)
    # ================================================================
    st.markdown("### 🖼️ 생성된 캐릭터 이미지 관리")

    from utils.character_image_manager import CharacterImageManager

    img_manager = CharacterImageManager(str(project_path))

    # 통계 표시
    stats = img_manager.get_statistics()

    stat_cols = st.columns(4)
    with stat_cols[0]:
        st.metric("총 이미지", f"{stats['total_images']}개")
    with stat_cols[1]:
        st.metric("캐릭터 수", f"{stats['total_characters']}명")
    with stat_cols[2]:
        st.metric("중복 캐릭터", f"{stats['duplicates']}개")
    with stat_cols[3]:
        st.metric("용량", f"{stats['total_size_mb']} MB")

    # 이미지 목록 가져오기
    all_char_images = img_manager.get_all_character_images()

    if not all_char_images:
        st.info("아직 생성된 캐릭터 이미지가 없습니다.")
    else:
        st.divider()

        # ============================================================
        # 전체 선택 및 일괄 작업 버튼
        # ============================================================
        action_cols = st.columns([2, 2, 2, 2])

        with action_cols[0]:
            select_all = st.checkbox(
                f"☑️ 전체 선택 ({len(all_char_images)}개)",
                key="char_img_select_all"
            )

        with action_cols[1]:
            delete_selected_btn = st.button(
                "🗑️ 선택 삭제",
                type="secondary",
                key="char_img_delete_selected"
            )

        with action_cols[2]:
            cleanup_btn = st.button(
                "🧹 중복 정리",
                help="각 캐릭터별 최신 1개만 유지",
                key="char_img_cleanup"
            )

        with action_cols[3]:
            refresh_btn = st.button(
                "🔄 새로고침",
                key="char_img_refresh"
            )

        # 선택 상태 초기화
        if "char_selected_images" not in st.session_state:
            st.session_state.char_selected_images = set()

        # 전체 선택 처리
        if select_all:
            st.session_state.char_selected_images = {img["filename"] for img in all_char_images}
        elif not select_all and "char_img_select_all" in st.session_state:
            # 체크 해제 시 선택 초기화
            if len(st.session_state.char_selected_images) == len(all_char_images):
                st.session_state.char_selected_images = set()

        # 삭제 확인 및 처리
        if delete_selected_btn:
            selected_files = list(st.session_state.char_selected_images)
            if selected_files:
                with st.spinner(f"{len(selected_files)}개 이미지 삭제 중..."):
                    result = img_manager.delete_images(selected_files)
                    if result["deleted"]:
                        st.success(f"✅ {len(result['deleted'])}개 이미지 삭제됨")
                        st.session_state.char_selected_images.clear()
                        img_manager.update_character_data_with_latest_images()
                        st.rerun()
                    if result["failed"]:
                        st.error(f"❌ {len(result['failed'])}개 삭제 실패")
            else:
                st.warning("삭제할 이미지를 선택해주세요.")

        # 중복 정리 처리
        if cleanup_btn:
            with st.spinner("중복 이미지 정리 중..."):
                result = img_manager.cleanup_duplicate_images(keep_count=1)
                if result["deleted"]:
                    st.success(f"✅ {len(result['deleted'])}개 중복 이미지 삭제됨")
                    st.rerun()
                else:
                    st.info("정리할 중복 이미지가 없습니다.")

        # 새로고침 처리
        if refresh_btn:
            st.rerun()

        # 선택된 이미지 수 표시
        selected_count = len(st.session_state.char_selected_images)
        if selected_count > 0:
            st.info(f"📌 {selected_count}개 이미지 선택됨")

        st.divider()

        # ============================================================
        # 캐릭터별 이미지 그리드
        # ============================================================
        char_groups = {}
        for img in all_char_images:
            char_name = img["character_name"]
            if char_name not in char_groups:
                char_groups[char_name] = []
            char_groups[char_name].append(img)

        for char_name, char_images in char_groups.items():
            with st.expander(f"👤 {char_name} ({len(char_images)}개 이미지)", expanded=False):
                # 이미지 그리드 (최대 6열, 작은 썸네일)
                num_cols = min(len(char_images), 6)
                img_cols = st.columns(num_cols)

                for i, img in enumerate(char_images):
                    with img_cols[i % num_cols]:
                        # 체크박스
                        is_selected = img["filename"] in st.session_state.char_selected_images
                        if st.checkbox(
                            "선택",
                            value=is_selected,
                            key=f"char_chk_{img['filename']}",
                            label_visibility="collapsed"
                        ):
                            st.session_state.char_selected_images.add(img["filename"])
                        else:
                            st.session_state.char_selected_images.discard(img["filename"])

                        # 이미지 표시 (작은 썸네일 - 클릭 시 확대)
                        try:
                            clickable_image(img["path"], width=100, key=f"gallery_img_{img['filename']}")
                        except:
                            st.error("❌")

                        # 대표 이미지 배지
                        if img["is_representative"]:
                            st.markdown("⭐ **대표 이미지**")

                        # 메타 정보
                        st.caption(f"📅 {img['created_at']}")
                        st.caption(f"📦 {img['size_bytes'] // 1024} KB")

                        # 개별 작업 버튼
                        btn_cols = st.columns(2)
                        with btn_cols[0]:
                            if not img["is_representative"]:
                                if st.button("⭐", key=f"char_rep_{img['filename']}", help="대표 이미지로 설정"):
                                    img_manager.set_representative_image(char_name, img["filename"])
                                    st.rerun()
                        with btn_cols[1]:
                            if st.button("🗑️", key=f"char_del_{img['filename']}", help="삭제"):
                                img_manager.delete_images([img["filename"]])
                                img_manager.update_character_data_with_latest_images()
                                st.rerun()

        st.info("💡 이제 '이미지 생성' 페이지에서 배경을 생성한 후 합성할 수 있습니다.")

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

                # Visual Prompt 일괄 생성 버튼
                st.markdown("---")
                st.markdown("##### 🎨 Visual Prompt 자동 생성")

                col_model, col_btn = st.columns([2, 1])

                with col_model:
                    from utils.ai_model_config import AVAILABLE_MODELS
                    model_options = {
                        "⚡ 빠름 (Haiku)": "claude-3-5-haiku-20241022",
                        "⚖️ 균형 (Sonnet)": "claude-sonnet-4-20250514"
                    }
                    selected_label = st.selectbox(
                        "AI 모델 선택",
                        options=list(model_options.keys()),
                        index=0,
                        key="visual_prompt_model",
                        help="Haiku가 빠르고 저렴합니다"
                    )
                    selected_model = model_options[selected_label]

                with col_btn:
                    st.write("")  # 정렬용 빈 공간
                    if st.button("🎨 Visual Prompt 생성", type="primary", key="gen_visual_prompts"):
                        from utils.character_visual_prompt import generate_character_visual_prompts

                        # 스크립트 컨텍스트 수집
                        context = ""
                        script_path = project_path / "scripts" / "full_script.txt"
                        if script_path.exists():
                            try:
                                context = script_path.read_text(encoding="utf-8")[:2000]
                            except:
                                pass

                        # visual_prompt가 없는 캐릭터만 추출
                        chars_to_process = [
                            c for c in analysis_chars
                            if not c.get('visual_prompt') and not c.get('character_prompt')
                        ]

                        with st.spinner(f"Visual Prompt 생성 중... ({len(chars_to_process)}명)"):
                            updated_chars = generate_character_visual_prompts(
                                chars_to_process,
                                context=context,
                                model=selected_model
                            )

                            # 원본 리스트에 결과 반영
                            result_map = {c['name']: c.get('visual_prompt', '') for c in updated_chars}
                            for char in analysis_chars:
                                name = char.get('name', '')
                                if name in result_map and result_map[name]:
                                    char['visual_prompt'] = result_map[name]

                            # 파일에 저장
                            try:
                                with open(analysis_path, "w", encoding="utf-8") as f:
                                    json.dump(analysis_chars, f, ensure_ascii=False, indent=2)
                                st.success(f"✅ {len(chars_to_process)}명의 visual_prompt 생성 완료!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"저장 실패: {e}")
                st.markdown("---")
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

# === 탭 6: 대표 캐릭터 ===
with tab6:
    st.subheader("⭐ 대표 캐릭터")

    st.info("""
    **대표 캐릭터란?**

    채널이나 영상의 시그니처 캐릭터입니다.
    등장인물이 없는 설명형 콘텐츠(경제, 브랜드 소개 등)에서도
    일관된 캐릭터를 사용할 수 있습니다.
    """)

    # 라이브러리 -> 프로젝트 동기화 함수
    def sync_library_to_project(lib_char_id: str, rep_manager_instance=None):
        """라이브러리 캐릭터를 현재 프로젝트로 동기화"""
        lib_char_data = rep_library.get_character(lib_char_id)
        if not lib_char_data:
            return False

        try:
            from utils.representative_character import RepresentativeCharacter
            import uuid

            # RepresentativeCharacter 객체 생성
            synced_char = RepresentativeCharacter(
                id=lib_char_data.get("id", str(uuid.uuid4())),
                name=lib_char_data.get("name", "캐릭터"),
                description=lib_char_data.get("description", ""),
                base_prompt=lib_char_data.get("prompt", ""),
                negative_prompt=lib_char_data.get("negative_prompt", ""),
                style_preset=lib_char_data.get("style_preset", ""),
                style_suffix=lib_char_data.get("style_suffix", "")
            )

            # 기본 이미지 복사
            lib_base_images = lib_char_data.get("base_images", [])
            for img_info in lib_base_images:
                if isinstance(img_info, dict):
                    img_path = img_info.get("path", "")
                    img_type = img_info.get("type", "front")
                else:
                    img_path = str(img_info)
                    img_type = "front"

                if img_path and os.path.exists(img_path):
                    synced_char.base_images[img_type] = img_path

            # 프로젝트 매니저에 설정 (매니저 인스턴스가 있으면 사용, 없으면 새로 생성)
            if rep_manager_instance:
                rep_manager_instance.set_character(synced_char)
            else:
                _rep_manager = get_rep_char_manager(str(project_path))
                _rep_manager.set_character(synced_char)

            print(f"[RepChar] 라이브러리 캐릭터 '{lib_char_data.get('name')}' -> 프로젝트 동기화 완료")
            return True
        except Exception as e:
            print(f"[RepChar] 동기화 실패: {e}")
            return False

    # ============================================================
    # 📁 캐릭터 라이브러리 선택
    # ============================================================
    st.markdown("### 📁 캐릭터 라이브러리")

    rep_library = get_rep_char_library()
    all_characters = rep_library.get_all_characters()
    selected_lib_id = rep_library.get_selected_character_id()

    with st.container(border=True):
        if all_characters:
            # 캐릭터 선택 UI
            col_sel1, col_sel2, col_sel3 = st.columns([3, 1, 1])

            with col_sel1:
                # 드롭다운으로 선택
                char_options = {c["name"]: c["id"] for c in all_characters}
                char_names = ["➕ 새 캐릭터 정의..."] + list(char_options.keys())

                # 현재 선택된 캐릭터의 인덱스
                current_index = 0
                if selected_lib_id:
                    for i, c in enumerate(all_characters):
                        if c["id"] == selected_lib_id:
                            current_index = i + 1  # "새 캐릭터 정의" 옵션 때문에 +1
                            break

                selected_name = st.selectbox(
                    "저장된 대표 캐릭터 선택",
                    char_names,
                    index=current_index,
                    key="rep_char_library_select"
                )

                if selected_name == "➕ 새 캐릭터 정의...":
                    st.session_state["rep_char_mode"] = "create"
                    new_selected_id = None
                else:
                    new_selected_id = char_options.get(selected_name)
                    if new_selected_id and new_selected_id != selected_lib_id:
                        rep_library.select_character(new_selected_id)
                        # 프로젝트에 동기화
                        sync_library_to_project(new_selected_id)
                        st.rerun()

            with col_sel2:
                if selected_lib_id and st.button("📋 복제", use_container_width=True, key="rep_char_duplicate"):
                    new_id = rep_library.duplicate_character(selected_lib_id)
                    if new_id:
                        rep_library.select_character(new_id)
                        st.success("캐릭터가 복제되었습니다!")
                        time.sleep(0.5)
                        st.rerun()

            with col_sel3:
                if selected_lib_id:
                    if st.button("🗑️ 삭제", use_container_width=True, key="rep_char_lib_delete"):
                        if st.session_state.get("confirm_lib_delete") == selected_lib_id:
                            rep_library.delete_character(selected_lib_id)
                            st.warning("삭제되었습니다.")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.session_state["confirm_lib_delete"] = selected_lib_id
                            st.warning("다시 클릭하면 삭제됩니다.")

            # 캐릭터 카드 그리드 (썸네일 표시)
            if len(all_characters) > 1:
                st.markdown("---")
                st.caption("📌 저장된 캐릭터 목록 (클릭하여 선택)")

                cols = st.columns(min(len(all_characters), 6))

                for i, char in enumerate(all_characters):
                    with cols[i % 6]:
                        # 썸네일 (클릭 시 확대)
                        thumb_path = rep_library.get_thumbnail_path(char["id"])
                        if thumb_path and os.path.exists(thumb_path):
                            render_lightbox_image(thumb_path, width=80, key=f"lib_thumb_{char['id']}")
                        else:
                            st.markdown("🎭", help="썸네일 없음")

                        # 이름 (선택된 캐릭터 강조)
                        if char["id"] == selected_lib_id:
                            st.markdown(f"**⭐ {char['name'][:10]}**")
                        else:
                            if st.button(char["name"][:10], key=f"select_lib_{char['id']}", use_container_width=True):
                                rep_library.select_character(char["id"])
                                # 프로젝트에 동기화
                                sync_library_to_project(char["id"])
                                st.rerun()

                        # 사용 횟수
                        st.caption(f"사용: {char.get('usage_count', 0)}회")

        else:
            st.info("저장된 대표 캐릭터가 없습니다. 아래에서 새 캐릭터를 정의해주세요.")
            st.session_state["rep_char_mode"] = "create"

            # 기존 프로젝트 캐릭터 마이그레이션 제안
            temp_manager = get_rep_char_manager(str(project_path))
            existing_project_char = temp_manager.get_character()
            if existing_project_char and existing_project_char.base_prompt:
                with st.container(border=True):
                    st.warning(f"💡 프로젝트에 기존 대표 캐릭터 '{existing_project_char.name}'이(가) 있습니다.")
                    if st.button("📥 라이브러리로 마이그레이션", key="migrate_char_btn"):
                        # 기존 캐릭터를 라이브러리로 마이그레이션
                        new_id = rep_library.migrate_from_old_format(
                            old_data={
                                "name": existing_project_char.name,
                                "description": existing_project_char.description,
                                "base_prompt": existing_project_char.base_prompt,
                                "negative_prompt": existing_project_char.negative_prompt,
                                "style_preset": existing_project_char.style_preset,
                                "base_images": existing_project_char.base_images
                            },
                            project_path=str(project_path)
                        )
                        if new_id:
                            rep_library.select_character(new_id)
                            st.success(f"✅ '{existing_project_char.name}'이(가) 라이브러리에 저장되었습니다!")
                            time.sleep(0.5)
                            st.rerun()

    st.markdown("---")

    # 매니저 초기화 (프로젝트별 씬 액션 관리용)
    rep_manager = get_rep_char_manager(str(project_path))

    # 라이브러리에서 선택된 캐릭터가 있으면 매니저에 동기화 (페이지 로드시 한번)
    if selected_lib_id:
        current_char = rep_manager.get_character()
        if not current_char or current_char.id != selected_lib_id:
            sync_library_to_project(selected_lib_id, rep_manager)

    # ============================================================
    # 1️⃣ 대표 캐릭터 정의
    # ============================================================
    st.markdown("### 1️⃣ 대표 캐릭터 정의")

    with st.container(border=True):
        existing_char = rep_manager.get_character()

        col_def1, col_def2 = st.columns([1, 1])

        with col_def1:
            rep_char_name = st.text_input(
                "캐릭터 이름",
                value=existing_char.name if existing_char else "",
                placeholder="예: 채널 MC 마루",
                key="rep_char_name"
            )

            rep_char_description = st.text_area(
                "캐릭터 설명 (간단히)",
                value=existing_char.description if existing_char else "",
                placeholder="예: 30대 남성, 경제 전문가, 안경 착용",
                height=80,
                key="rep_char_description"
            )

        with col_def2:
            # ✅ 수정: 스타일 관리에서 캐릭터 스타일 동적 로드
            character_styles = get_styles_by_segment("character")

            if not character_styles:
                st.warning("캐릭터 스타일이 없습니다. 스타일 관리에서 추가해주세요.")
                # 폴백: STYLE_PRESETS 사용
                style_options = {k: v["name"] for k, v in STYLE_PRESETS.items()}
                style_data_map = {k: v for k, v in STYLE_PRESETS.items()}
            else:
                # 스타일 관리에서 가져온 스타일 사용
                style_options = {
                    style.id: f"{style.name_ko} ({style.name})"
                    for style in character_styles
                }
                style_data_map = {
                    style.id: {
                        "name": f"{style.name_ko} ({style.name})",
                        "suffix": style.prompt_suffix,
                        "prefix": style.prompt_prefix,
                        "negative": style.negative_prompt
                    }
                    for style in character_styles
                }

            # 현재 선택된 스타일 인덱스 찾기
            current_style_idx = 0
            if existing_char and existing_char.style_preset in style_options:
                current_style_idx = list(style_options.keys()).index(existing_char.style_preset)
            else:
                # 기본 스타일 찾기
                for idx, style in enumerate(character_styles if character_styles else []):
                    if style.is_default:
                        current_style_idx = idx
                        break

            selected_style = st.selectbox(
                "🎨 스타일 프리셋 (스타일 관리에서 로드)",
                options=list(style_options.keys()),
                format_func=lambda x: style_options.get(x, x),
                index=current_style_idx,
                key="rep_char_style"
            )

            # 선택된 스타일 정보 표시
            selected_style_data = style_data_map.get(selected_style, {})
            suffix_preview = selected_style_data.get('suffix', '')[:50]
            st.caption(f"스타일 suffix: {suffix_preview}...")

            # 스타일 관리 페이지 링크
            if character_styles:
                st.caption("💡 스타일 추가/수정: [스타일 관리] 페이지")

        st.markdown("**📝 캐릭터 생성 프롬프트 (상세)**")

        with st.expander("💡 프롬프트 작성 가이드", expanded=False):
            st.markdown("""
            **좋은 캐릭터 프롬프트 예시:**

            ```
            A professional Korean male character in his 30s,
            wearing round black-framed glasses and a navy blue suit with white shirt,
            clean-cut short black hair neatly styled,
            friendly and trustworthy expression,
            upper body portrait, white background
            ```

            **포함하면 좋은 요소:**
            - 성별, 나이대
            - 의상 (색상, 스타일)
            - 헤어스타일
            - 특징적인 액세서리 (안경, 모자 등)
            - 기본 표정
            - 배경
            """)

        rep_char_prompt = st.text_area(
            "캐릭터 프롬프트",
            value=existing_char.base_prompt if existing_char else "",
            height=150,
            placeholder="A professional Korean male character in his 30s...",
            key="rep_char_prompt",
            label_visibility="collapsed"
        )

        rep_negative_prompt = st.text_input(
            "네거티브 프롬프트 (선택)",
            value=existing_char.negative_prompt if existing_char else "text, watermark, low quality, blurry, deformed",
            key="rep_char_negative"
        )

        col_save1, col_save2 = st.columns(2)

        with col_save1:
            # 새 캐릭터인지 기존 캐릭터 수정인지 판단
            is_new_char = st.session_state.get("rep_char_mode") == "create" or not selected_lib_id
            save_label = "💾 새 캐릭터 저장" if is_new_char else "💾 프롬프트 저장"

            if st.button(save_label, type="primary", use_container_width=True, key="save_rep_char"):
                if not rep_char_name or not rep_char_prompt:
                    st.error("캐릭터 이름과 프롬프트를 입력해주세요.")
                else:
                    import uuid

                    # 라이브러리에 저장/업데이트
                    if is_new_char:
                        # 새 캐릭터 생성
                        new_lib_id = rep_library.create_character(
                            name=rep_char_name,
                            description=rep_char_description,
                            prompt=rep_char_prompt,
                            negative_prompt=rep_negative_prompt,
                            style_preset=selected_style
                        )
                        rep_library.select_character(new_lib_id)
                        st.session_state["rep_char_mode"] = "view"
                        st.success(f"✅ 새 대표 캐릭터 '{rep_char_name}'이(가) 라이브러리에 저장되었습니다!")
                    else:
                        # 기존 캐릭터 업데이트
                        rep_library.update_character(
                            char_id=selected_lib_id,
                            name=rep_char_name,
                            description=rep_char_description,
                            prompt=rep_char_prompt,
                            negative_prompt=rep_negative_prompt,
                            style_preset=selected_style
                        )
                        st.success("✅ 대표 캐릭터가 업데이트되었습니다!")

                    # 프로젝트 매니저에도 동기화
                    character = RepresentativeCharacter(
                        id=selected_lib_id if selected_lib_id else str(uuid.uuid4()),
                        name=rep_char_name,
                        description=rep_char_description,
                        base_prompt=rep_char_prompt,
                        style_preset=selected_style,
                        negative_prompt=rep_negative_prompt
                    )
                    rep_manager.set_character(character)

                    time.sleep(0.5)
                    st.rerun()

        with col_save2:
            # 새 캐릭터 모드에서는 취소 버튼
            if is_new_char and all_characters:
                if st.button("취소", use_container_width=True, key="cancel_rep_char"):
                    st.session_state["rep_char_mode"] = "view"
                    st.rerun()
            elif existing_char and st.button("🗑️ 프로젝트에서 제거", use_container_width=True, key="delete_rep_char"):
                rep_manager.delete_character()
                st.warning("프로젝트에서 대표 캐릭터가 제거되었습니다. (라이브러리에는 유지됨)")
                time.sleep(0.5)
                st.rerun()

    # ============================================================
    # 2️⃣ 기본 이미지 생성
    # ============================================================
    st.markdown("---")
    st.markdown("### 2️⃣ 대표 캐릭터 기본 이미지 생성")

    rep_char = rep_manager.get_character()

    if not rep_char:
        st.warning("먼저 대표 캐릭터를 정의해주세요.")
    else:
        with st.container(border=True):
            col_img1, col_img2 = st.columns([1, 2])

            with col_img1:
                st.markdown("**생성된 기본 이미지:**")

                if rep_char.base_images:
                    img_cols = st.columns(2)
                    for idx, (img_type, img_path) in enumerate(rep_char.base_images.items()):
                        if os.path.exists(img_path):
                            with img_cols[idx % 2]:
                                render_lightbox_image(
                                    img_path,
                                    caption=BASE_IMAGE_TYPES.get(img_type, {}).get("name", img_type),
                                    width=150,
                                    key=f"base_img_{img_type}"
                                )
                else:
                    st.info("아직 생성된 이미지가 없습니다.")

            with col_img2:
                st.markdown("**생성 옵션:**")

                selected_base_types = []
                base_type_cols = st.columns(3)

                for idx, (key, info) in enumerate(BASE_IMAGE_TYPES.items()):
                    with base_type_cols[idx % 3]:
                        if st.checkbox(info["name"], value=(key in ["front", "smile"]), key=f"base_img_{key}"):
                            selected_base_types.append(key)

                # API 선택
                from utils.image_api_manager import API_MODELS
                base_api_options = list(API_MODELS.keys())

                base_selected_api = st.selectbox(
                    "이미지 생성 API",
                    options=base_api_options,
                    index=0,
                    key="base_image_api"
                )

                # ===== 프롬프트 미리보기 =====
                if selected_base_types:
                    from utils.prompt_builder import PromptBuilder
                    from utils.representative_character import STYLE_PRESETS

                    st.markdown("---")

                    with st.expander("최종 프롬프트 미리보기 및 수정", expanded=False):
                        # 첫 번째 선택된 타입에 대한 예시 프롬프트 표시
                        example_type = selected_base_types[0]
                        example_name = BASE_IMAGE_TYPES[example_type]["name"]

                        st.caption(f"'{example_name}' 이미지 프롬프트 구조 (다른 옵션도 동일한 구조)")

                        # 프롬프트 빌더로 구성 요소 표시
                        builder = PromptBuilder()

                        # 1. 캐릭터 기본 프롬프트
                        if rep_char.base_prompt:
                            builder.add(
                                name="캐릭터 프롬프트",
                                content=rep_char.base_prompt,
                                source=f"대표 캐릭터 > {rep_char.name}",
                                order=0
                            )

                        # 2. 표정/포즈 프롬프트
                        pose_prompt = BASE_IMAGE_TYPES[example_type]["prompt_prefix"]
                        builder.add(
                            name="표정/포즈",
                            content=pose_prompt,
                            source=f"기본 이미지 옵션 > {example_name}",
                            order=1
                        )

                        # 3. 스타일 Suffix
                        if rep_char.style_preset and rep_char.style_preset in STYLE_PRESETS:
                            style_suffix = STYLE_PRESETS[rep_char.style_preset]["suffix"]
                            builder.add(
                                name="스타일 Suffix",
                                content=style_suffix,
                                source=f"스타일 프리셋 > {STYLE_PRESETS[rep_char.style_preset]['name']}",
                                order=2
                            )

                        # 4. 네거티브 프롬프트
                        if rep_char.negative_prompt:
                            builder.add_negative(
                                name="캐릭터 네거티브",
                                content=rep_char.negative_prompt,
                                source=f"대표 캐릭터 > {rep_char.name}"
                            )

                        if rep_char.style_preset and rep_char.style_preset in STYLE_PRESETS:
                            style_neg = STYLE_PRESETS[rep_char.style_preset].get("negative", "")
                            if style_neg:
                                builder.add_negative(
                                    name="스타일 네거티브",
                                    content=style_neg,
                                    source=f"스타일 프리셋 > {STYLE_PRESETS[rep_char.style_preset]['name']}"
                                )

                        build_result = builder.build()

                        # 구성 요소 테이블
                        for i, comp in enumerate(build_result.components, 1):
                            st.markdown(f"**{i}. {comp.name}** ({comp.source})")
                            st.code(comp.content, language=None)

                        st.info("위 요소들이 쉼표(,)로 연결되어 최종 프롬프트가 됩니다.")

                        st.markdown("---")
                        st.markdown("#### 최종 프롬프트 (수정 가능)")

                        # 세션 상태로 수정된 프롬프트 관리
                        if "base_img_edited_prompt" not in st.session_state:
                            st.session_state["base_img_edited_prompt"] = {}

                        edited_prompt = st.text_area(
                            f"'{example_name}' 프롬프트",
                            value=build_result.final_prompt,
                            height=100,
                            key="base_img_prompt_edit",
                            help="생성 전에 프롬프트를 직접 수정할 수 있습니다."
                        )
                        st.session_state["base_img_edited_prompt"]["main"] = edited_prompt

                        # 프롬프트 통계
                        col_s1, col_s2, col_s3 = st.columns(3)
                        with col_s1:
                            st.metric("문자 수", f"{len(edited_prompt):,}")
                        with col_s2:
                            st.metric("단어 수", f"{len(edited_prompt.split()):,}")
                        with col_s3:
                            approx_tokens = len(edited_prompt) // 4
                            token_status = "적정" if approx_tokens < 200 else "주의" if approx_tokens < 300 else "초과"
                            st.metric("예상 토큰", f"~{approx_tokens} ({token_status})")

                        # 네거티브 프롬프트
                        edited_negative = st.text_input(
                            "네거티브 프롬프트",
                            value=build_result.final_negative,
                            key="base_img_negative_edit"
                        )
                        st.session_state["base_img_edited_prompt"]["negative"] = edited_negative

                        st.caption("수정된 프롬프트는 첫 번째 옵션에만 적용됩니다. 나머지는 기본 프롬프트가 사용됩니다.")

                st.markdown("---")

                if st.button(
                    f"기본 이미지 생성 ({len(selected_base_types)}개)",
                    type="primary",
                    disabled=len(selected_base_types) == 0,
                    use_container_width=True,
                    key="gen_base_images"
                ):
                    from utils.image_api_manager import ImageAPIManager

                    api_manager = ImageAPIManager()
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    generated_count = 0

                    # 수정된 프롬프트 가져오기
                    edited_prompts = st.session_state.get("base_img_edited_prompt", {})

                    for idx, img_type in enumerate(selected_base_types):
                        status_text.text(f"생성 중: {BASE_IMAGE_TYPES[img_type]['name']}...")

                        # 첫 번째 옵션은 수정된 프롬프트 사용
                        if idx == 0 and edited_prompts.get("main"):
                            prompt = edited_prompts["main"]
                            negative = edited_prompts.get("negative", rep_manager.get_negative_prompt())
                        else:
                            prompt = rep_manager.get_base_image_prompt(img_type)
                            negative = rep_manager.get_negative_prompt()

                        result = api_manager.generate_image(
                            prompt=prompt,
                            api_provider=base_selected_api,
                            negative_prompt=negative
                        )

                        if result.success and result.image_data:
                            output_path = rep_manager.images_folder / f"base_{img_type}.png"
                            with open(output_path, "wb") as f:
                                f.write(result.image_data)

                            rep_manager.add_base_image(img_type, str(output_path))
                            generated_count += 1

                            # 라이브러리에도 이미지 추가
                            if selected_lib_id:
                                rep_library.add_base_image(selected_lib_id, str(output_path), img_type)

                        progress_bar.progress((idx + 1) / len(selected_base_types))

                    status_text.empty()
                    progress_bar.empty()
                    st.success(f"✅ {generated_count}개 기본 이미지 생성 완료!")
                    st.rerun()

    # ============================================================
    # 3️⃣ 씬별 액션 프롬프트 생성
    # ============================================================
    st.markdown("---")
    st.markdown("### 3️⃣ 씬별 캐릭터 액션 프롬프트 생성 (AI)")

    rep_char = rep_manager.get_character()

    if not rep_char:
        st.warning("먼저 대표 캐릭터를 정의해주세요.")
    else:
        # 씬 데이터 로드 (새로고침 지원 - v2.0)
        cache_key = f"scene_data_{project_path}"

        if st.session_state.get('force_refresh_scene_data', False) or cache_key not in st.session_state:
            scene_data, mtime_str = load_scene_analysis_data(force_refresh=True)
            st.session_state[cache_key] = scene_data
            st.session_state['force_refresh_scene_data'] = False
        else:
            scene_data = st.session_state.get(cache_key, [])
            mtime_str = st.session_state.get('scene_file_mtime', None)

        if not scene_data:
            st.warning("씬 분석 결과가 없습니다. 씬 분석을 먼저 진행해주세요.")
        else:
            with st.container(border=True):
                # 씬 정보 + 새로고침 버튼 (v2.0: 파일 정보 표시)
                col_info, col_refresh = st.columns([5, 1])

                with col_info:
                    file_name = st.session_state.get('scene_file_name', 'scenes.json')
                    file_mtime = st.session_state.get('scene_file_mtime', '')
                    info_text = f"📊 분석된 씬: **{len(scene_data)}개** ({file_name})"
                    if file_mtime:
                        info_text += f"\n🕐 수정: {file_mtime}"
                    st.info(info_text)

                with col_refresh:
                    if st.button("🔄", key="refresh_scene_data_btn", help="최신 씬 분석 결과 다시 불러오기"):
                        # ⭐ v2.0: 캐시 완전 삭제
                        if cache_key in st.session_state:
                            del st.session_state[cache_key]
                        st.session_state['force_refresh_scene_data'] = True
                        st.toast("씬 데이터 새로고침 중...")
                        st.rerun()

                col_ai1, col_ai2 = st.columns(2)

                with col_ai1:
                    ai_models = get_action_ai_models()
                    ai_model_options = {m["id"]: m["name"] for m in ai_models}

                    selected_ai_model = st.selectbox(
                        "🤖 AI 모델",
                        options=list(ai_model_options.keys()),
                        format_func=lambda x: ai_model_options[x],
                        key="action_ai_model"
                    )

                with col_ai2:
                    st.markdown("**생성 옵션:**")
                    opt_expression = st.checkbox("씬 내용 기반 표정 자동 결정", value=True, key="opt_expression")
                    opt_pose = st.checkbox("씬 내용 기반 포즈/제스처 자동 결정", value=True, key="opt_pose")
                    opt_mood = st.checkbox("씬 분위기 반영", value=True, key="opt_mood")
                    opt_props = st.checkbox("소품 추가 (차트, 노트북 등)", value=False, key="opt_props")

                # ============================================================
                # 📍 구간 선택 UI
                # ============================================================
                st.markdown("---")
                st.markdown("#### 📍 생성 구간 선택")

                total_scenes = len(scene_data)

                range_mode = st.radio(
                    "구간 선택 방식",
                    options=["전체", "구간 지정", "빠른 선택"],
                    horizontal=True,
                    key="action_range_mode"
                )

                if range_mode == "전체":
                    start_scene = 1
                    end_scene = total_scenes
                    st.caption(f"📌 전체 {total_scenes}개 씬에 대해 프롬프트를 생성합니다.")

                elif range_mode == "구간 지정":
                    col_start, col_end = st.columns(2)

                    with col_start:
                        start_scene = st.number_input(
                            "시작 씬",
                            min_value=1,
                            max_value=total_scenes,
                            value=1,
                            step=1,
                            key="action_start_scene_input"
                        )

                    with col_end:
                        end_scene = st.number_input(
                            "끝 씬",
                            min_value=1,
                            max_value=total_scenes,
                            value=min(50, total_scenes),
                            step=1,
                            key="action_end_scene_input"
                        )

                    if start_scene > end_scene:
                        st.error("❌ 시작 씬이 끝 씬보다 클 수 없습니다.")
                    else:
                        selected_count = end_scene - start_scene + 1
                        st.caption(f"📌 씬 {start_scene} ~ {end_scene} ({selected_count}개 씬) 선택됨")

                else:  # 빠른 선택
                    quick_options = {
                        "처음 50개": (1, min(50, total_scenes)),
                        "처음 25개 (테스트용)": (1, min(25, total_scenes)),
                        "처음 100개": (1, min(100, total_scenes)),
                    }

                    # 동적 옵션 추가
                    if total_scenes > 50:
                        quick_options["씬 51-100"] = (51, min(100, total_scenes))
                    if total_scenes > 100:
                        quick_options["씬 101-150"] = (101, min(150, total_scenes))
                    if total_scenes > 150:
                        quick_options["씬 151-200"] = (151, min(200, total_scenes))

                    quick_options["마지막 50개"] = (max(1, total_scenes - 49), total_scenes)

                    selected_quick = st.selectbox(
                        "빠른 구간 선택",
                        options=list(quick_options.keys()),
                        key="action_quick_range_select"
                    )

                    start_scene, end_scene = quick_options[selected_quick]
                    selected_count = end_scene - start_scene + 1
                    st.caption(f"📌 씬 {start_scene} ~ {end_scene} ({selected_count}개 씬) 선택됨")

                # 세션에 저장
                st.session_state['action_start_scene'] = start_scene
                st.session_state['action_end_scene'] = end_scene

                # ============================================================
                # ⚙️ 병합 옵션 (v2.0)
                # ============================================================
                existing_actions = rep_manager.get_scene_actions()
                if existing_actions:
                    st.markdown("---")
                    st.markdown("#### ⚙️ 기존 프롬프트 처리")

                    existing_count = len(existing_actions)
                    merge_option = st.radio(
                        f"기존에 생성된 프롬프트가 {existing_count}개 있습니다. 어떻게 처리할까요?",
                        options=[
                            "덮어쓰기",
                            "병합",
                            "선택 구간만 업데이트"
                        ],
                        format_func=lambda x: {
                            "덮어쓰기": f"🔄 덮어쓰기 (기존 {existing_count}개 삭제)",
                            "병합": f"➕ 병합 (기존 프롬프트 유지 + 새로 생성)",
                            "선택 구간만 업데이트": f"📝 선택 구간만 업데이트 (씬 {start_scene}~{end_scene} 교체)"
                        }[x],
                        horizontal=True,
                        key="action_merge_option"
                    )
                    st.session_state['action_merge_mode'] = merge_option
                else:
                    st.session_state['action_merge_mode'] = "덮어쓰기"

                st.markdown("---")

                # 버튼 텍스트에 구간 표시
                selected_count = end_scene - start_scene + 1
                button_text = f"🤖 AI로 씬별 액션 프롬프트 자동 생성 (씬 {start_scene}~{end_scene}, {selected_count}개)"

                if st.button(
                    button_text,
                    type="primary",
                    use_container_width=True,
                    key="gen_action_prompts"
                ):
                    generator = CharacterActionGenerator(model_id=selected_ai_model)

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def update_progress(current, total, message):
                        progress_bar.progress(current / total if total > 0 else 0)
                        status_text.text(message)

                    # ✅ 수정: 씬 데이터를 생성기에 맞는 형식으로 변환
                    # 버그 수정: script_text 필드 사용 (이전: script 필드 없어서 title만 전달됨)
                    # ✅ v2.0: 선택된 구간만 필터링
                    scenes_for_gen = [
                        {
                            "scene_num": s.get("scene_number", i + 1),
                            "script": (
                                s.get("script_text") or  # 씬 분석 데이터의 실제 필드
                                s.get("script") or
                                s.get("narration") or
                                s.get("description") or  # 설명도 포함
                                s.get("title", f"씬 {i + 1}")
                            )
                        }
                        for i, s in enumerate(scene_data)
                        if start_scene <= s.get("scene_number", i + 1) <= end_scene
                    ]

                    # 디버그: 실제 전달되는 씬 내용 확인
                    print(f"[ActionGenerator] 선택 범위: 씬 {start_scene}~{end_scene}, 총 {len(scenes_for_gen)}개")
                    print(f"[ActionGenerator] 씬 데이터 샘플: {scenes_for_gen[0] if scenes_for_gen else 'empty'}")

                    new_actions = generator.generate_batch_actions(
                        character_prompt=rep_char.base_prompt,
                        scenes=scenes_for_gen,
                        options={
                            "expression": opt_expression,
                            "pose": opt_pose,
                            "mood": opt_mood,
                            "props": opt_props
                        },
                        progress_callback=update_progress
                    )

                    # ⭐ v2.0: 병합 옵션에 따른 저장
                    merge_mode = st.session_state.get('action_merge_mode', '덮어쓰기')
                    existing_actions = rep_manager.get_scene_actions()

                    if merge_mode == "병합" and existing_actions:
                        # 기존 프롬프트와 병합 (새로 생성된 씬은 추가, 기존은 유지)
                        existing_scene_nums = {a.scene_num for a in existing_actions}
                        merged = list(existing_actions)

                        for new_action in new_actions:
                            if new_action.scene_num not in existing_scene_nums:
                                merged.append(new_action)

                        # scene_num으로 정렬
                        merged.sort(key=lambda x: x.scene_num)
                        rep_manager.set_scene_actions(merged)
                        final_count = len(merged)
                        result_msg = f"✅ 병합 완료! (기존 {len(existing_actions)}개 + 새로 {len(new_actions)}개 → 총 {final_count}개)"

                    elif merge_mode == "선택 구간만 업데이트" and existing_actions:
                        # 선택 구간만 교체 (나머지 유지)
                        kept = [a for a in existing_actions if not (start_scene <= a.scene_num <= end_scene)]
                        merged = kept + list(new_actions)

                        # scene_num으로 정렬
                        merged.sort(key=lambda x: x.scene_num)
                        rep_manager.set_scene_actions(merged)
                        final_count = len(merged)
                        result_msg = f"✅ 구간 업데이트 완료! 씬 {start_scene}~{end_scene} ({len(new_actions)}개) 교체됨 (총 {final_count}개)"

                    else:
                        # 덮어쓰기
                        rep_manager.set_scene_actions(new_actions)
                        result_msg = f"✅ 씬 {start_scene}~{end_scene} 범위 ({len(new_actions)}개) 액션 프롬프트 생성 완료!"

                    progress_bar.empty()
                    status_text.empty()
                    st.success(result_msg)
                    st.rerun()

                # 생성된 액션 표시
                st.markdown("---")
                st.markdown("**📋 생성된 씬별 액션 프롬프트:**")

                actions = rep_manager.get_scene_actions()

                if not actions:
                    st.info("아직 생성된 액션 프롬프트가 없습니다.")
                else:
                    show_count = st.selectbox(
                        "표시 개수",
                        options=[10, 20, 50, len(actions)],
                        format_func=lambda x: f"{x}개" if x != len(actions) else "전체",
                        key="action_show_count"
                    )

                    for action in actions[:show_count]:
                        with st.expander(
                            f"씬 {action.scene_num}: {action.scene_content[:40]}...",
                            expanded=False
                        ):
                            col_act1, col_act2 = st.columns([1, 1])

                            with col_act1:
                                st.markdown(f"**표정:** {action.expression}")
                                st.markdown(f"**포즈:** {action.pose}")
                                st.markdown(f"**분위기:** {action.mood}")

                                if action.props and action.props != ["none"]:
                                    st.markdown(f"**소품:** {', '.join(action.props)}")

                                st.markdown(f"**상태:** {action.generation_status}")

                            with col_act2:
                                st.markdown("**액션 프롬프트:**")
                                st.code(action.action_prompt, language=None)

    # ============================================================
    # 4️⃣ 씬별 캐릭터 이미지 일괄 생성
    # ============================================================
    st.markdown("---")
    st.markdown("### 4️⃣ 씬별 캐릭터 이미지 일괄 생성")

    rep_char = rep_manager.get_character()
    actions = rep_manager.get_scene_actions()

    if not rep_char:
        st.warning("대표 캐릭터를 먼저 정의해주세요.")
    elif not actions:
        st.warning("씬별 액션 프롬프트를 먼저 생성해주세요.")
    else:
        with st.container(border=True):
            stats = rep_manager.get_stats()

            st.info(f"""
            📊 **생성 현황**
            - 전체 씬: {stats['total_scenes']}개
            - 완료: {stats['completed']}개
            - 대기: {stats['pending']}개
            - 실패: {stats['failed']}개
            """)

            # 씬 선택
            col_sel1, col_sel2, col_sel3 = st.columns(3)

            with col_sel1:
                if st.button("✅ 전체 선택", key="batch_select_all"):
                    st.session_state["batch_selected_scenes"] = [a.scene_num for a in actions]

            with col_sel2:
                batch_range_start = st.number_input("시작", min_value=1, value=1, key="batch_range_start")
                batch_range_end = st.number_input("끝", min_value=1, value=min(20, len(actions)), key="batch_range_end")

                if st.button("범위 선택", key="batch_select_range"):
                    st.session_state["batch_selected_scenes"] = list(range(batch_range_start, batch_range_end + 1))

            with col_sel3:
                if st.button("⬜ 미생성만 선택", key="batch_select_pending"):
                    st.session_state["batch_selected_scenes"] = [
                        a.scene_num for a in actions if a.generation_status == "pending"
                    ]

            selected_scenes = st.session_state.get("batch_selected_scenes", [])
            st.caption(f"선택됨: {len(selected_scenes)}개 씬")

            # API 선택
            from utils.image_api_manager import API_MODELS
            batch_api_options = list(API_MODELS.keys())

            batch_selected_api = st.selectbox(
                "이미지 생성 API",
                options=batch_api_options,
                index=0,
                key="batch_image_api"
            )

            # 프롬프트 미리보기 및 수정
            with st.expander("최종 프롬프트 미리보기 및 수정", expanded=False):
                from utils.prompt_builder import PromptBuilder
                from utils.representative_character import STYLE_PRESETS

                if actions:
                    # 첫 번째 씬에 대한 예시 프롬프트 빌드
                    sample_action = actions[0]

                    builder = PromptBuilder()

                    # 1. 캐릭터 기본 프롬프트
                    if rep_char.base_prompt:
                        builder.add(
                            name="캐릭터 프롬프트",
                            content=rep_char.base_prompt,
                            source=f"대표 캐릭터 > {rep_char.name}",
                            order=0
                        )

                    # 2. 씬별 액션 프롬프트
                    builder.add(
                        name="씬별 액션",
                        content=sample_action.action_prompt,
                        source=f"씬 {sample_action.scene_num} AI 생성 액션",
                        order=1
                    )

                    # 3. 스타일 Suffix
                    if rep_char.style_preset and rep_char.style_preset in STYLE_PRESETS:
                        style_suffix = STYLE_PRESETS[rep_char.style_preset]["suffix"]
                        builder.add(
                            name="스타일 Suffix",
                            content=style_suffix,
                            source=f"스타일 프리셋 > {STYLE_PRESETS[rep_char.style_preset]['name']}",
                            order=2
                        )

                    # 4. 네거티브 프롬프트
                    if rep_char.negative_prompt:
                        builder.add_negative(
                            name="캐릭터 네거티브",
                            content=rep_char.negative_prompt,
                            source=f"대표 캐릭터 > {rep_char.name}"
                        )

                    build_result = builder.build()

                    st.caption(f"씬 {sample_action.scene_num} 프롬프트 구조 예시")

                    # 구성 요소 표시
                    for i, comp in enumerate(build_result.components, 1):
                        st.markdown(f"**{i}. {comp.name}** ({comp.source})")
                        st.code(comp.content, language=None)

                    st.info("위 구조가 모든 씬에 동일하게 적용됩니다. 씬마다 '씬별 액션' 부분만 달라집니다.")

                    st.markdown("---")
                    st.markdown("#### 프롬프트 수정 (선택 씬에 적용)")

                    # 수정 모드 선택
                    edit_mode = st.radio(
                        "수정 범위",
                        ["기본 프롬프트 사용", "스타일 일괄 변경", "특정 씬 개별 수정"],
                        horizontal=True,
                        key="action_edit_mode"
                    )

                    if edit_mode == "스타일 일괄 변경":
                        col_e1, col_e2 = st.columns(2)
                        with col_e1:
                            edited_style_suffix = st.text_area(
                                "스타일 Suffix (모든 씬 적용)",
                                value=STYLE_PRESETS.get(rep_char.style_preset, {}).get("suffix", ""),
                                height=80,
                                key="action_style_suffix"
                            )
                        with col_e2:
                            edited_negative = st.text_area(
                                "네거티브 (모든 씬 적용)",
                                value=build_result.final_negative,
                                height=80,
                                key="action_negative"
                            )

                        st.session_state["action_batch_edits"] = {
                            "mode": "style",
                            "suffix": edited_style_suffix,
                            "negative": edited_negative
                        }

                    elif edit_mode == "특정 씬 개별 수정":
                        st.caption("선택한 씬 중 처음 3개의 프롬프트를 개별 수정할 수 있습니다.")

                        scene_edits = {}
                        for i, scene_num in enumerate(selected_scenes[:3]):
                            action = rep_manager.get_scene_action(scene_num)
                            if action:
                                default_prompt = rep_manager.build_full_prompt(action.action_prompt)
                                scene_edits[scene_num] = st.text_area(
                                    f"씬 {scene_num} 프롬프트",
                                    value=default_prompt,
                                    height=80,
                                    key=f"scene_edit_{scene_num}"
                                )

                        st.session_state["action_batch_edits"] = {
                            "mode": "individual",
                            "scenes": scene_edits
                        }

                    else:
                        st.session_state["action_batch_edits"] = {"mode": "default"}

            # 생성 버튼
            if st.button(
                f"씬 캐릭터 이미지 일괄 생성 ({len(selected_scenes)}개)",
                type="primary",
                disabled=len(selected_scenes) == 0,
                use_container_width=True,
                key="batch_gen_images"
            ):
                from utils.image_api_manager import ImageAPIManager
                from utils.representative_character import STYLE_PRESETS

                api_manager = ImageAPIManager()
                progress_bar = st.progress(0)
                status_text = st.empty()

                success_count = 0
                fail_count = 0

                # 수정된 프롬프트 가져오기
                batch_edits = st.session_state.get("action_batch_edits", {"mode": "default"})

                for idx, scene_num in enumerate(selected_scenes):
                    action = rep_manager.get_scene_action(scene_num)

                    if not action:
                        fail_count += 1
                        continue

                    status_text.text(f"씬 {scene_num} 이미지 생성 중...")

                    # 상태 업데이트
                    rep_manager.update_scene_action(scene_num, generation_status="generating")

                    try:
                        # 수정 모드에 따른 프롬프트 생성
                        if batch_edits.get("mode") == "individual" and scene_num in batch_edits.get("scenes", {}):
                            full_prompt = batch_edits["scenes"][scene_num]
                            negative = rep_manager.get_negative_prompt()
                        elif batch_edits.get("mode") == "style":
                            # 스타일만 변경
                            parts = [rep_char.base_prompt, action.action_prompt, batch_edits.get("suffix", "")]
                            full_prompt = ", ".join(p.strip().rstrip(',') for p in parts if p)
                            negative = batch_edits.get("negative", rep_manager.get_negative_prompt())
                        else:
                            # 기본 프롬프트 생성
                            full_prompt = rep_manager.build_full_prompt(action.action_prompt)
                            negative = rep_manager.get_negative_prompt()

                        # 이미지 생성
                        result = api_manager.generate_image(
                            prompt=full_prompt,
                            api_provider=batch_selected_api,
                            negative_prompt=negative
                        )

                        if result.success and result.image_data:
                            output_path = rep_manager.scene_images_folder / f"scene_{scene_num:03d}_character.png"
                            with open(output_path, "wb") as f:
                                f.write(result.image_data)

                            rep_manager.update_scene_action(
                                scene_num,
                                generated_image_path=str(output_path),
                                generation_status="completed"
                            )
                            success_count += 1
                        else:
                            rep_manager.update_scene_action(
                                scene_num,
                                generation_status="failed",
                                error_message=result.error or "이미지 생성 실패"
                            )
                            fail_count += 1

                    except Exception as e:
                        rep_manager.update_scene_action(
                            scene_num,
                            generation_status="failed",
                            error_message=str(e)
                        )
                        fail_count += 1

                    progress_bar.progress((idx + 1) / len(selected_scenes))

                progress_bar.empty()
                status_text.empty()
                st.success(f"✅ 완료: {success_count}개 성공, {fail_count}개 실패")
                st.rerun()

            # 생성된 이미지 미리보기
            st.markdown("---")
            st.markdown("**🖼️ 생성된 캐릭터 이미지:**")

            completed_actions = rep_manager.get_completed_actions()

            if not completed_actions:
                st.info("아직 생성된 이미지가 없습니다.")
            else:
                img_cols = st.columns(5)
                for idx, action in enumerate(completed_actions[:20]):
                    if action.generated_image_path and os.path.exists(action.generated_image_path):
                        with img_cols[idx % 5]:
                            render_lightbox_image(
                                action.generated_image_path,
                                caption=f"씬 {action.scene_num}",
                                width=120,
                                key=f"action_img_{action.scene_num}_{idx}"
                            )

                if len(completed_actions) > 20:
                    st.caption(f"... 외 {len(completed_actions) - 20}개 더 있음")

# 다음 단계 안내
st.divider()
st.info("👉 캐릭터 설정이 완료되면 4단계 TTS 생성으로 이동하세요.")
st.page_link("pages/4_🎤_TTS_생성.py", label="🎤 4단계: TTS 생성", icon="➡️")
