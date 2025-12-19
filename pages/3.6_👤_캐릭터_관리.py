"""
3.6단계: 캐릭터 관리

캐릭터 생성, 편집, 배치 생성 기능
"""
import streamlit as st
import json
import time
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
    existing = manager.get_all_characters()
    if existing:
        return  # 이미 캐릭터가 있으면 스킵

    # 1. 세션에서 캐릭터 찾기
    session_chars = None
    for key in ["characters", "scene_characters", "extracted_characters"]:
        if key in st.session_state and st.session_state[key]:
            session_chars = st.session_state[key]
            print(f"[캐릭터 관리] 세션 '{key}'에서 {len(session_chars)}명 발견")
            break

    # 2. 분석 파일에서 캐릭터 찾기
    if not session_chars:
        analysis_path = project_path / "analysis" / "characters.json"
        if analysis_path.exists():
            try:
                with open(analysis_path, "r", encoding="utf-8") as f:
                    session_chars = json.load(f)
                print(f"[캐릭터 관리] 분석 파일에서 {len(session_chars)}명 발견")
            except Exception as e:
                print(f"[캐릭터 관리] 분석 파일 로드 실패: {e}")

    # 3. 자동 가져오기
    if session_chars:
        imported = manager.import_from_analysis(session_chars)
        if imported > 0:
            print(f"[캐릭터 관리] {imported}명 자동 가져오기 완료")

auto_sync_characters()

# 탭 구성
tab1, tab2, tab3, tab4 = st.tabs(["📋 캐릭터 목록", "➕ 캐릭터 추가", "🎨 배치 생성", "📥 가져오기"])

# === 탭 1: 캐릭터 목록 ===
with tab1:
    st.subheader("📋 등록된 캐릭터")

    characters = manager.get_all_characters()

    if not characters:
        st.info("등록된 캐릭터가 없습니다. 씬 분석 결과에서 가져오거나 직접 추가하세요.")
    else:
        st.success(f"{len(characters)}명의 캐릭터가 등록되어 있습니다.")

        for idx, char in enumerate(characters):
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

    # 생성 버튼
    st.markdown("### 🚀 생성 실행")

    # 예상 시간
    total_chars = len(selected_chars)
    estimated_time = total_chars * 20  # Free 모델 기준 ~20초
    st.caption(f"⏱️ 예상 소요 시간: 약 {estimated_time // 60}분 {estimated_time % 60}초")

    if st.button("🎨 캐릭터 이미지 배치 생성", type="primary", use_container_width=True, disabled=total_chars==0):
        from core.image.character_image_generator import CharacterImageGenerator, CharacterImageConfig
        from utils.image_storage import save_character_image

        # 출력 디렉토리
        output_dir = project_path / "images" / "characters"
        output_dir.mkdir(parents=True, exist_ok=True)

        api_manager = get_api_manager()

        # 프로그레스 UI
        progress = StreamlitProgressUI(
            task_name="캐릭터 이미지 생성",
            total_steps=total_chars,
            show_logs=True
        )

        # 이미지 미리보기 영역
        image_preview = st.empty()

        success_count = 0
        fail_count = 0

        try:
            # 스타일 정보 가져오기
            style_prefix = selected_style.prompt_prefix if selected_style else ""
            style_suffix = selected_style.prompt_suffix if selected_style else ""
            style_name = selected_style.name if selected_style else "animation"

            # 설정 생성
            config = CharacterImageConfig(
                style=style_name,
                pose=char_pose,
                background=char_background,
                width=char_width,
                height=char_height,
                model="black-forest-labs/FLUX.1-schnell-Free",
                style_prefix=style_prefix,
                style_suffix=style_suffix
            )

            generator = CharacterImageGenerator(str(project_path))

            progress.info(f"총 {total_chars}명의 캐릭터 이미지를 생성합니다.")
            progress.info(f"스타일: {style_name}, 포즈: {char_pose}, 배경: {char_background}")

            for i, char in enumerate(selected_chars):
                start_time = time.time()
                char_name = char.name

                progress.update(i + 1, f"{char_name} 생성 중...")

                # 캐릭터 데이터를 딕셔너리로 변환
                char_dict = {
                    "name": char.name,
                    "name_en": char.name_en,
                    "visual_prompt": char.character_prompt,
                    "character_prompt": char.character_prompt
                }

                # 이미지 생성
                result = generator.generate_character_image(
                    character=char_dict,
                    config=config,
                    output_dir=output_dir
                )

                elapsed = time.time() - start_time

                if result.get("success"):
                    success_count += 1
                    progress.success(f"{char_name} 완료! ({elapsed:.1f}초)")

                    # 캐릭터에 이미지 경로 저장
                    manager.add_generated_image(char.id, result.get("image_path", ""))

                    # 이미지 스토리지에도 저장
                    save_character_image(char_name, result, project_path)

                    # 이미지 미리보기
                    if result.get("image_path"):
                        image_preview.image(result["image_path"], caption=char_name, width=300)

                    # 사용량 기록
                    api_manager.record_usage(
                        provider="together",
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
                    progress.error(f"{char_name} 실패: {result.get('error', 'Unknown')}")

                    # 에러 기록
                    api_manager.record_usage(
                        provider="together",
                        model_id=config.model,
                        function="image_generation",
                        units_used=1,
                        duration_seconds=elapsed,
                        success=False,
                        error_message=result.get('error', 'Unknown'),
                        project_name=project_path.name,
                        step_name="character_compositing"
                    )

            # 완료 메시지
            progress.complete(f"캐릭터 이미지 생성 완료! 성공: {success_count}, 실패: {fail_count}")

            if success_count > 0:
                st.balloons()
                update_project_step(3)
                time.sleep(1)
                st.rerun()

        except Exception as e:
            progress.fail(str(e))
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

# === 탭 4: 가져오기 ===
with tab4:
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

        # 1. 먼저 세션에서 로드 시도 (가장 최신 데이터)
        session_keys = ["characters", "scene_characters", "extracted_characters"]
        for key in session_keys:
            if key in st.session_state and st.session_state[key]:
                analysis_chars = st.session_state[key]
                print(f"[캐릭터 관리] 세션 '{key}'에서 {len(analysis_chars)}개 캐릭터 로드")
                break

        # 2. 세션에 없으면 파일에서 로드
        if not analysis_chars:
            analysis_path = project_path / "analysis" / "characters.json"
            if analysis_path.exists():
                with open(analysis_path, "r", encoding="utf-8") as f:
                    analysis_chars = json.load(f)
                print(f"[캐릭터 관리] 파일에서 {len(analysis_chars)}개 캐릭터 로드")

        if analysis_chars:
            # visual_prompt 통계 계산
            chars_with_prompt = sum(1 for c in analysis_chars if c.get("visual_prompt") or c.get("character_prompt"))
            chars_without_prompt = len(analysis_chars) - chars_with_prompt

            st.success(f"📊 씬 분석에서 **{len(analysis_chars)}명**의 캐릭터가 발견되었습니다.")

            if chars_without_prompt > 0:
                st.warning(f"⚠️ {chars_without_prompt}명의 캐릭터에 visual_prompt가 없습니다.")
            else:
                st.info(f"✅ 모든 캐릭터에 visual_prompt가 있습니다.")

            characters_to_import = analysis_chars

            # 캐릭터 미리보기
            for char in analysis_chars[:5]:  # 최대 5개 미리보기
                name = char.get('name', 'Unknown')
                name_en = char.get('name_en', '')
                has_prompt = bool(char.get('visual_prompt') or char.get('character_prompt'))
                prompt_status = "✅" if has_prompt else "⚠️"

                st.write(f"- {prompt_status} **{name}** ({name_en})")
                if char.get('description'):
                    st.caption(char.get('description', '')[:80])
                if has_prompt:
                    prompt_preview = (char.get('visual_prompt') or char.get('character_prompt', ''))[:100]
                    st.caption(f"🎨 `{prompt_preview}...`")

            if len(analysis_chars) > 5:
                st.caption(f"... 외 {len(analysis_chars) - 5}명 더 있음")
        else:
            st.warning("씬 분석 결과가 없습니다. 3.5단계에서 먼저 씬 분석을 실행하세요.")
            st.page_link("pages/3.5_🎬_씬_분석.py", label="🎬 3.5단계: 씬 분석으로 이동", icon="➡️")

            # 디버그 정보
            with st.expander("🔍 디버그 정보"):
                st.write("**세션 상태 키:**")
                char_keys = [k for k in st.session_state.keys() if "char" in k.lower()]
                st.write(char_keys if char_keys else "캐릭터 관련 키 없음")
                st.write(f"**프로젝트 경로:** {project_path}")

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
