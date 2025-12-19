"""
6단계: 이미지 생성

Together.ai FLUX를 활용한 이미지 생성
세그먼트 그룹 기준 / 씬 기반 이미지 생성 지원
"""
import streamlit as st
from pathlib import Path
import sys
import time
import json

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
from config.constants import IMAGE_STYLE_PREFIXES
from components.interactive_canvas import interactive_composite_canvas, render_composite_preview, save_composite_image
from components.canvas_state_manager import CanvasStateManager
from components.post_composite_editor import post_composite_editor
from utils.api_helper import (
    require_api_key,
    show_api_status_sidebar
)
from utils.progress_ui import render_api_selector, StreamlitProgressUI
from core.api.api_manager import get_api_manager
from utils.style_manager import get_style_manager
from components.style_selector import style_radio_selector, get_selected_style
from core.prompt.preset_manager import PromptPresetManager
from utils.style_selector import render_style_selector

# 페이지 설정
st.set_page_config(
    page_title="이미지 생성",
    page_icon="🎨",
    layout="wide"
)

render_project_sidebar()
show_api_status_sidebar()

if not ensure_project_selected():
    st.stop()

project_path = get_current_project()

# === 데이터 동기화 (페이지 로드 시 실행) ===
def sync_all_data():
    """페이지 로드 시 모든 데이터 동기화"""
    # 씬 데이터 로드
    scenes = load_scenes(project_path)
    if scenes and "scenes" not in st.session_state:
        st.session_state["scenes"] = scenes
        print(f"[데이터 동기화] scenes 로드: {len(scenes)}개")

    # 캐릭터 데이터 로드 (CharacterManager에서)
    try:
        from core.character.character_manager import CharacterManager
        manager = CharacterManager(str(project_path))
        all_chars = manager.get_all_characters()
        if all_chars and "characters" not in st.session_state:
            # Character 객체를 딕셔너리로 변환
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
                # 이미지가 있으면 image_path 추가
                if c.generated_images:
                    char_data["image_path"] = c.generated_images[-1]
                    char_data["image_url"] = c.generated_images[-1]
                chars_dict.append(char_data)
            st.session_state["characters"] = chars_dict
            print(f"[데이터 동기화] characters 로드: {len(chars_dict)}명")
    except Exception as e:
        print(f"[데이터 동기화] CharacterManager 로드 실패: {e}")

    # 배경 이미지 로드
    bg_json = project_path / "images" / "backgrounds" / "backgrounds.json"
    if bg_json.exists() and "background_images" not in st.session_state:
        try:
            with open(bg_json, "r", encoding="utf-8") as f:
                bg_data = json.load(f)
                st.session_state["background_images"] = {int(k): v for k, v in bg_data.items()}
                print(f"[데이터 동기화] background_images 로드: {len(bg_data)}개")
        except Exception as e:
            print(f"[데이터 동기화] 배경 이미지 로드 실패: {e}")

sync_all_data()

st.title("🎨 6단계: 이미지 생성")
st.caption("Together.ai FLUX + 세그먼트 그룹 기준")

# API 키 확인
if not require_api_key("TOGETHER_API_KEY", "Together.ai API"):
    st.stop()

st.divider()

# === 탭 구성 ===
tab_scene, tab_background, tab_composite, tab_generate, tab_manual, tab_gallery, tab_regenerate = st.tabs([
    "🎬 씬+캐릭터 생성",
    "🏞️ 배경만 생성",
    "🎨 합성",
    "✨ 세그먼트 기반",
    "✏️ 수동 생성",
    "🖼️ 갤러리",
    "🔄 재생성"
])

# === 씬 기반 생성 탭 ===
with tab_scene:
    st.subheader("🎬 씬 기반 이미지 생성")

    st.info("""
    💡 **씬 기반 생성이란?**
    - 씬 분석 결과의 연출가이드를 활용
    - 각 씬에 등장하는 캐릭터 프롬프트 자동 포함
    - 배경 + 캐릭터가 조화롭게 통합된 이미지 생성

    **사전 조건:**
    1. 3.5단계에서 씬 분석 완료
    2. 3.6단계에서 캐릭터 등록 완료 (선택사항)
    """)

    # 씬 분석 결과 확인
    scenes = load_scenes(project_path)

    if not scenes:
        st.error("❌ 씬 분석 결과가 없습니다. 3.5단계에서 씬 분석을 먼저 실행하세요.")
        st.page_link("pages/3.5_🎬_씬_분석.py", label="🎬 3.5단계: 씬 분석으로 이동", icon="➡️")
    else:
        st.success(f"✅ {len(scenes)}개의 씬이 로드되었습니다.")

        # 캐릭터 정보 로드 (자동 동기화 포함)
        from core.character.character_manager import CharacterManager
        char_manager = CharacterManager(str(project_path))

        # 자동 동기화: CharacterManager에 캐릭터가 없으면 세션/분석 파일에서 가져오기
        def auto_sync_characters_for_image():
            """이미지 생성 페이지용 캐릭터 자동 동기화"""
            existing = char_manager.get_all_characters()
            if existing:
                return  # 이미 캐릭터가 있으면 skip

            # 1. 세션 상태에서 캐릭터 확인
            session_chars = None
            for key in ["characters", "scene_characters", "extracted_characters"]:
                if key in st.session_state and st.session_state[key]:
                    session_chars = st.session_state[key]
                    print(f"[이미지생성] 세션 '{key}'에서 {len(session_chars)}개 캐릭터 발견")
                    break

            # 2. 분석 파일에서 캐릭터 확인
            if not session_chars:
                analysis_path = project_path / "analysis" / "characters.json"
                if analysis_path.exists():
                    try:
                        with open(analysis_path, "r", encoding="utf-8") as f:
                            session_chars = json.load(f)
                            print(f"[이미지생성] 분석 파일에서 {len(session_chars)}개 캐릭터 발견")
                    except Exception as e:
                        print(f"[이미지생성] 분석 파일 로드 실패: {e}")

            # 3. 캐릭터 자동 가져오기
            if session_chars:
                imported = char_manager.import_from_analysis(session_chars)
                if imported > 0:
                    print(f"[이미지생성] {imported}개 캐릭터 자동 가져오기 완료")

        auto_sync_characters_for_image()
        characters = char_manager.get_all_characters()

        if characters:
            char_names = [c.name for c in characters[:5]]
            st.info(f"👤 등록된 캐릭터: {len(characters)}명 ({', '.join(char_names)}{'...' if len(characters) > 5 else ''})")
        else:
            st.warning("⚠️ 등록된 캐릭터가 없습니다. 캐릭터 없이 배경만 생성됩니다.")

        st.divider()

        # 생성 설정
        st.markdown("### ⚙️ 생성 설정")

        # 스타일 선택 (StyleManager - scene_composite 세그먼트)
        style_manager = get_style_manager(str(project_path))
        selected_style = style_radio_selector(
            segment="scene_composite",
            key="scene_gen",
            project_path=str(project_path),
            horizontal=True
        )

        # 스타일 프롬프트 가져오기
        style_prefix = selected_style.prompt_prefix if selected_style else ""
        style_suffix = selected_style.prompt_suffix if selected_style else ""

        # 스타일 상세 표시
        if selected_style:
            with st.expander("선택된 스타일 상세"):
                st.markdown(f"**{selected_style.name_ko}** ({selected_style.name})")
                st.code(f"Prefix: {selected_style.prompt_prefix}", language=None)
                st.code(f"Suffix: {selected_style.prompt_suffix}", language=None)

        col1, col2 = st.columns(2)

        with col1:
            include_characters = st.checkbox("캐릭터 프롬프트 포함", value=True,
                                             help="씬에 등장하는 캐릭터 정보를 프롬프트에 포함")

        with col2:
            width = st.selectbox("너비", [1280, 1024, 768], index=0, key="scene_width")
            height = st.selectbox("높이", [720, 576, 512], index=0, key="scene_height")

            st.markdown("#### 🤖 이미지 생성 AI")
            selected_api = render_api_selector(
                task="image_generation",
                label="이미지 모델",
                key_prefix="scene_image"
            )

            # 모델 ID 결정 (API 선택에서)
            api_manager_temp = get_api_manager()
            api_config = api_manager_temp.get_selected_api("image_generation")
            model_id = api_config.model_id if api_config else "black-forest-labs/FLUX.1-schnell-Free"

        st.divider()

        # 씬 범위 선택
        st.markdown("### 📍 생성 범위")

        col1, col2 = st.columns(2)
        with col1:
            start_scene = st.number_input("시작 씬", min_value=1, max_value=len(scenes), value=1)
        with col2:
            end_scene = st.number_input("끝 씬", min_value=1, max_value=len(scenes), value=min(5, len(scenes)))

        scenes_to_generate = [s for s in scenes if start_scene <= s.get("scene_id", 0) <= end_scene]

        st.info(f"📊 생성할 씬: {len(scenes_to_generate)}개 (씬 {start_scene} ~ {end_scene})")

        # 예상 시간/비용
        is_free = "Free" in model_id
        time_per_image = 20 if is_free else 5
        total_time = len(scenes_to_generate) * time_per_image

        st.caption(f"⏱️ 예상 소요 시간: 약 {total_time // 60}분 {total_time % 60}초")

        st.divider()

        # 씬 미리보기
        st.markdown("### 👁️ 생성할 씬 미리보기")

        with st.expander("씬 목록 보기", expanded=False):
            for scene in scenes_to_generate:
                scene_id = scene.get("scene_id", 0)
                script = scene.get("script_text", "")[:100]
                chars = scene.get("characters", [])
                direction = scene.get("direction_guide", "")[:100]

                st.markdown(f"""
                **씬 {scene_id}**: {script}...
                - 👤 캐릭터: {', '.join(chars) if chars else '없음'}
                - 🎬 연출: {direction}...
                """)
                st.divider()

        # 생성 버튼
        st.markdown("### 🚀 생성 실행")

        if st.button("🎬 씬 이미지 생성 시작", type="primary", use_container_width=True):
            from core.image.scene_image_generator import SceneImageGenerator, SceneImageConfig

            api_manager = get_api_manager()
            total_scenes = len(scenes_to_generate)

            # 프로그레스 UI
            progress = StreamlitProgressUI(
                task_name="씬 이미지 생성",
                total_steps=total_scenes,
                show_logs=True
            )

            config = SceneImageConfig(
                style_prefix=style_prefix,
                width=width,
                height=height,
                model=model_id,
                include_characters=include_characters
            )

            generator = SceneImageGenerator(str(project_path))
            image_preview = st.empty()

            progress.info(f"총 {total_scenes}개 씬 이미지를 생성합니다.")
            progress.info(f"모델: {model_id}")

            def on_progress(current, total, result):
                scene_id = result.get("scene_id", current)
                success = result.get("success", False)
                gen_time = result.get("generation_time", 0)
                chars = result.get("characters", [])

                progress.update(current, f"씬 {scene_id} 생성 중...")

                if success:
                    progress.success(f"씬 {scene_id} 완료! ({gen_time:.1f}초) - 캐릭터: {', '.join(chars) if chars else '없음'}")

                    # 이미지 미리보기
                    if result.get("saved_path"):
                        image_preview.image(result["saved_path"], caption=f"씬 {scene_id}", width=400)

                    # 사용량 기록
                    api_manager.record_usage(
                        provider="together",
                        model_id=model_id,
                        function="image_generation",
                        units_used=1,
                        duration_seconds=gen_time,
                        success=True,
                        project_name=project_path.name,
                        step_name="scene_image"
                    )
                else:
                    progress.error(f"씬 {scene_id} 실패: {result.get('error', 'Unknown')}")

                    # 에러 기록
                    api_manager.record_usage(
                        provider="together",
                        model_id=model_id,
                        function="image_generation",
                        units_used=1,
                        duration_seconds=gen_time,
                        success=False,
                        error_message=result.get('error', 'Unknown'),
                        project_name=project_path.name,
                        step_name="scene_image"
                    )

            try:
                results = generator.generate_all_scene_images(
                    config=config,
                    start_scene=start_scene,
                    end_scene=end_scene,
                    on_progress=on_progress
                )

                success_count = sum(1 for r in results if r.get("success"))

                progress.complete(f"씬 이미지 생성 완료! 성공: {success_count}/{len(results)}")

                # === 세션 상태에 저장 (스토리보드/갤러리 연동용) ===
                if "generated_images" not in st.session_state:
                    st.session_state["generated_images"] = []

                from datetime import datetime
                for r in results:
                    if r.get("success"):
                        image_data = {
                            "scene_id": r.get("scene_id"),
                            "prompt": r.get("prompt", ""),
                            "image_path": r.get("saved_path", ""),
                            "image_url": "",  # 로컬 파일은 URL 없음
                            "characters": r.get("characters", []),
                            "created_at": datetime.now().isoformat(),
                            "model": model_id
                        }

                        # 기존에 같은 scene_id가 있으면 업데이트, 없으면 추가
                        existing_idx = None
                        for idx, img in enumerate(st.session_state["generated_images"]):
                            if img.get("scene_id") == r.get("scene_id"):
                                existing_idx = idx
                                break

                        if existing_idx is not None:
                            st.session_state["generated_images"][existing_idx] = image_data
                        else:
                            st.session_state["generated_images"].append(image_data)

                print(f"[이미지 생성] 세션에 {len(st.session_state['generated_images'])}개 이미지 저장됨")

                if success_count > 0:
                    st.balloons()
                    update_project_step(6)

            except Exception as e:
                progress.fail(str(e))
                import traceback
                st.code(traceback.format_exc())

        # 생성된 씬 이미지 갤러리
        st.markdown("### 🖼️ 생성된 씬 이미지")

        scene_images = list_scene_images(project_path)
        if scene_images:
            cols = st.columns(4)
            for i, img_path in enumerate(scene_images[:8]):
                with cols[i % 4]:
                    st.image(str(img_path), caption=img_path.stem, use_container_width=True)

            if len(scene_images) > 8:
                st.caption(f"... 외 {len(scene_images) - 8}개 이미지 (갤러리 탭에서 전체 확인)")
        else:
            st.info("아직 생성된 씬 이미지가 없습니다.")

# === 배경만 생성 탭 ===
with tab_background:
    st.subheader("🏞️ 배경 이미지 생성")

    st.info("""
    **배경 이미지 생성이란?**
    - 씬의 배경/환경만 생성합니다 (주인공 캐릭터 제외)
    - 엑스트라/군중은 선택적으로 포함할 수 있습니다
    - 생성된 배경은 '합성' 탭에서 캐릭터와 합성됩니다

    💡 **사전 조건:** 3.5단계에서 씬 분석 완료 필요
    """)

    # 씬 분석 결과 확인
    bg_scenes = load_scenes(project_path)

    if not bg_scenes:
        st.error("❌ 씬 분석 결과가 없습니다. 3.5단계에서 씬 분석을 먼저 실행하세요.")
        st.page_link("pages/3.5_🎬_씬_분석.py", label="🎬 3.5단계: 씬 분석으로 이동", icon="➡️")
    else:
        st.success(f"✅ {len(bg_scenes)}개의 씬이 로드되었습니다.")

        st.divider()

        # 생성 설정
        st.markdown("### ⚙️ 생성 설정")

        # 스타일 선택 (StyleManager - background 세그먼트)
        bg_style_manager = get_style_manager(str(project_path))
        bg_selected_style = style_radio_selector(
            segment="background",
            key="bg_gen",
            project_path=str(project_path),
            horizontal=True
        )

        # 스타일 이름 가져오기
        bg_style = bg_selected_style.name if bg_selected_style else "animation"
        bg_style_prefix = bg_selected_style.prompt_prefix if bg_selected_style else ""
        bg_style_suffix = bg_selected_style.prompt_suffix if bg_selected_style else ""

        # 스타일 상세 표시
        if bg_selected_style:
            with st.expander("선택된 스타일 상세"):
                st.markdown(f"**{bg_selected_style.name_ko}** ({bg_selected_style.name})")
                st.code(f"Prefix: {bg_selected_style.prompt_prefix}", language=None)
                st.code(f"Suffix: {bg_selected_style.prompt_suffix}", language=None)

        col1, col2 = st.columns(2)

        with col1:
            include_extras = st.checkbox(
                "엑스트라/보조 인물 포함",
                value=True,
                help="배경에 군중, 엑스트라 등 보조 인물을 포함합니다",
                key="bg_include_extras"
            )

        with col2:
            bg_size_option = st.selectbox(
                "이미지 크기",
                ["1280x720", "1920x1080", "1024x576"],
                key="bg_size_option"
            )
            bg_width, bg_height = map(int, bg_size_option.split("x"))

            st.markdown("#### 🤖 이미지 생성 AI")
            bg_selected_api = render_api_selector(
                task="image_generation",
                label="이미지 모델",
                key_prefix="bg_image"
            )

        st.divider()

        # 생성 범위
        st.markdown("### 📍 생성 범위")

        col1, col2 = st.columns(2)
        with col1:
            bg_start_scene = st.number_input("시작 씬", min_value=1, max_value=len(bg_scenes), value=1, key="bg_start")
        with col2:
            bg_end_scene = st.number_input("끝 씬", min_value=1, max_value=len(bg_scenes), value=min(5, len(bg_scenes)), key="bg_end")

        bg_scenes_to_generate = [s for s in bg_scenes if bg_start_scene <= s.get("scene_id", 0) <= bg_end_scene]

        st.info(f"📊 생성할 배경: {len(bg_scenes_to_generate)}개 (씬 {bg_start_scene} ~ {bg_end_scene})")

        # 예상 시간
        bg_time_per_image = 20
        bg_total_time = len(bg_scenes_to_generate) * bg_time_per_image
        st.caption(f"⏱️ 예상 소요 시간: 약 {bg_total_time // 60}분 {bg_total_time % 60}초")

        st.divider()

        # 생성 버튼
        st.markdown("### 🚀 생성 실행")

        if st.button("🏞️ 배경 이미지 생성 시작", type="primary", use_container_width=True, key="bg_gen_btn"):
            from core.image.background_image_generator import BackgroundImageGenerator, BackgroundImageConfig
            from utils.image_storage import save_background_image

            api_manager = get_api_manager()
            total_bg = len(bg_scenes_to_generate)

            # 프로그레스 UI
            progress = StreamlitProgressUI(
                task_name="배경 이미지 생성",
                total_steps=total_bg,
                show_logs=True
            )

            # 이미지 미리보기
            image_preview = st.empty()

            # 설정
            bg_config = BackgroundImageConfig(
                style=bg_style,
                include_extras=include_extras,
                width=bg_width,
                height=bg_height,
                model="black-forest-labs/FLUX.1-schnell-Free",
                style_prefix=bg_style_prefix,
                style_suffix=bg_style_suffix
            )

            generator = BackgroundImageGenerator(str(project_path))

            progress.info(f"총 {total_bg}개 배경 이미지를 생성합니다.")
            progress.info(f"스타일: {bg_style}, 엑스트라 포함: {include_extras}")

            success_count = 0
            fail_count = 0

            for i, scene in enumerate(bg_scenes_to_generate):
                scene_id = scene.get("scene_id", i + 1)
                start_time = time.time()

                progress.update(i + 1, f"씬 {scene_id} 배경 생성 중...")

                result = generator.generate_background(
                    scene=scene,
                    config=bg_config
                )

                elapsed = time.time() - start_time

                if result.get("success"):
                    success_count += 1
                    progress.success(f"씬 {scene_id} 배경 완료! ({elapsed:.1f}초)")

                    # 저장
                    save_background_image(scene_id, result, project_path)

                    # 이미지 미리보기
                    if result.get("image_path"):
                        image_preview.image(result["image_path"], caption=f"씬 {scene_id} 배경", width=500)

                    # 사용량 기록
                    api_manager.record_usage(
                        provider="together",
                        model_id=bg_config.model,
                        function="image_generation",
                        units_used=1,
                        duration_seconds=elapsed,
                        success=True,
                        project_name=project_path.name,
                        step_name="background_generation"
                    )
                else:
                    fail_count += 1
                    progress.error(f"씬 {scene_id} 실패: {result.get('error', 'Unknown')}")

            progress.complete(f"배경 이미지 생성 완료! 성공: {success_count}/{total_bg}")

            if success_count > 0:
                st.balloons()
                st.info("💡 '합성' 탭에서 캐릭터와 배경을 합성하세요.")

        # 생성된 배경 이미지 갤러리
        st.markdown("### 🖼️ 생성된 배경 이미지")

        bg_image_dir = project_path / "images" / "backgrounds"
        if bg_image_dir.exists():
            bg_images = list(bg_image_dir.glob("*.png"))
            if bg_images:
                cols = st.columns(4)
                for i, img_path in enumerate(bg_images[:8]):
                    with cols[i % 4]:
                        st.image(str(img_path), caption=img_path.stem, use_container_width=True)
                if len(bg_images) > 8:
                    st.caption(f"... 외 {len(bg_images) - 8}개")
            else:
                st.info("아직 생성된 배경 이미지가 없습니다.")
        else:
            st.info("배경 이미지 폴더가 없습니다.")

# === 합성 탭 ===
with tab_composite:
    st.subheader("🎨 씬 합성 (배경 + 캐릭터)")

    st.info("""
    **씬 합성이란?**
    - 생성된 배경 이미지 위에 캐릭터 이미지를 배치합니다
    - **AI 합성**: 씬 분석 정보(연출 가이드, 카메라 등)를 AI가 분석하여 자동 배치
    - **단순 합성**: 수동으로 캐릭터 위치/크기 지정

    💡 **사전 조건:**
    1. '캐릭터 관리'에서 캐릭터 이미지 생성 완료
    2. '배경만 생성'에서 배경 이미지 생성 완료
    """)

    # 데이터 로드
    from utils.image_storage import load_background_images, load_character_images, save_composited_image

    comp_scenes = load_scenes(project_path)
    background_images = load_background_images(project_path)
    character_images = load_character_images(project_path)

    # 상태 확인
    if not comp_scenes:
        st.warning("씬 분석 결과가 없습니다.")
    elif not background_images:
        st.warning("배경 이미지가 없습니다. '배경만 생성' 탭에서 먼저 배경을 생성하세요.")
    else:
        st.success(f"✅ 씬 {len(comp_scenes)}개, 배경 {len(background_images)}개")

        # 캐릭터 이미지 확인
        if character_images:
            st.success(f"✅ 캐릭터 이미지: {len(character_images)}개")
            # 캐릭터 이미지 목록 표시
            with st.expander("📷 캐릭터 이미지 목록"):
                for name, info in character_images.items():
                    img_path = info.get("image_path") or info.get("image_url")
                    st.write(f"- **{name}**: `{img_path[:60] if img_path else 'N/A'}...`")
        else:
            st.warning("⚠️ 캐릭터 이미지가 없습니다. '캐릭터 관리'에서 이미지를 생성하세요.")

            # 디버그 정보
            with st.expander("🔍 디버그 정보"):
                st.write("**세션 상태 확인:**")

                # character_images 키
                ci = st.session_state.get("character_images", {})
                st.write(f"- `character_images`: {len(ci)}개")

                # characters 리스트
                chars = st.session_state.get("characters", [])
                st.write(f"- `characters`: {len(chars)}명")
                if chars:
                    for c in chars[:5]:
                        has_img = bool(c.get("image_path") or c.get("image_url"))
                        st.write(f"  - {c.get('name')}: image={has_img}")

                # CharacterManager 확인
                st.write("**CharacterManager 확인:**")
                try:
                    from core.character.character_manager import CharacterManager
                    cm = CharacterManager(str(project_path))
                    all_chars = cm.get_all_characters()
                    st.write(f"- 등록된 캐릭터: {len(all_chars)}명")
                    for c in all_chars[:5]:
                        has_img = bool(c.generated_images)
                        st.write(f"  - {c.name}: images={len(c.generated_images) if c.generated_images else 0}")
                except Exception as e:
                    st.write(f"- 오류: {e}")

                # 이미지 폴더 확인
                st.write("**이미지 폴더 확인:**")
                char_img_dir = project_path / "images" / "characters"
                st.write(f"- 경로: `{char_img_dir}`")
                st.write(f"- 존재: {char_img_dir.exists()}")
                if char_img_dir.exists():
                    pngs = list(char_img_dir.glob("*.png"))
                    st.write(f"- PNG 파일: {len(pngs)}개")
                    for p in pngs[:5]:
                        st.write(f"  - {p.name}")

            st.page_link("pages/3.6_👤_캐릭터_관리.py", label="👤 캐릭터 관리로 이동", icon="➡️")

        st.divider()

        # 합성 방식 선택: AI vs 단순 vs 인터랙티브
        st.markdown("### 🤖 합성 방식")
        comp_method = st.radio(
            "합성 방식",
            ["🤖 AI 합성 (씬 분석 기반 자동 배치)", "📐 단순 합성 (수동 레이아웃)", "🖱️ 인터랙티브 (드래그 앤 드롭)"],
            horizontal=True,
            key="comp_method"
        )

        use_ai_composition = "AI 합성" in comp_method
        use_interactive = "인터랙티브" in comp_method

        # AI 합성 시 추가 설정
        if use_ai_composition:
            st.caption("AI가 씬의 연출 가이드, 카메라 앵글, 분위기 등을 분석하여 캐릭터를 자동 배치합니다.")

            col1, col2 = st.columns(2)
            with col1:
                ai_provider = st.selectbox(
                    "AI 제공자",
                    ["anthropic", "gemini"],
                    format_func=lambda x: "Claude (Anthropic)" if x == "anthropic" else "Gemini (Google)",
                    key="comp_ai_provider"
                )
            with col2:
                st.info(f"선택: {ai_provider.upper()}")

        # ===== 인터랙티브 캔버스 모드 =====
        if use_interactive:
            st.caption("🖱️ 드래그 앤 드롭으로 캐릭터를 자유롭게 배치하세요. 크기 조절과 레이어 순서 변경도 가능합니다.")

            st.divider()

            st.markdown("### 🎯 인터랙티브 합성")

            # 배경이 있는 씬만 표시
            interactive_scenes = [s for s in comp_scenes if s.get("scene_id") in background_images]

            if not interactive_scenes:
                st.warning("배경 이미지가 있는 씬이 없습니다.")
            else:
                # 씬 선택
                int_scene_options = {f"씬 {s.get('scene_id')}": s.get("scene_id") for s in interactive_scenes}
                int_selected_scene_label = st.selectbox("편집할 씬", list(int_scene_options.keys()), key="int_scene_select")
                int_selected_scene_id = int_scene_options[int_selected_scene_label]

                # 선택된 씬 정보
                int_selected_scene = next((s for s in comp_scenes if s.get("scene_id") == int_selected_scene_id), None)

                if int_selected_scene:
                    # 배경 정보
                    int_bg_info = background_images.get(int_selected_scene_id, {})
                    int_bg_path = int_bg_info.get("image_path") or int_bg_info.get("image_url")

                    if int_bg_path and Path(int_bg_path).exists():
                        # 캐릭터 목록 준비
                        scene_char_names = int_selected_scene.get("characters", [])
                        canvas_characters = []

                        if character_images:
                            for char_name in scene_char_names:
                                if char_name in character_images:
                                    char_info = character_images[char_name]
                                    char_img_path = char_info.get("image_path") or char_info.get("image_url")
                                    if char_img_path and Path(char_img_path).exists():
                                        canvas_characters.append({
                                            "name": char_name,
                                            "image_path": char_img_path
                                        })

                        if not canvas_characters:
                            st.warning("이 씬에 사용할 수 있는 캐릭터 이미지가 없습니다.")

                            # 수동으로 캐릭터 추가
                            st.markdown("**수동 캐릭터 추가:**")
                            if character_images:
                                for char_name, char_info in character_images.items():
                                    if st.checkbox(f"➕ {char_name}", key=f"int_add_{int_selected_scene_id}_{char_name}"):
                                        char_img_path = char_info.get("image_path") or char_info.get("image_url")
                                        if char_img_path and Path(char_img_path).exists():
                                            canvas_characters.append({
                                                "name": char_name,
                                                "image_path": char_img_path
                                            })

                        # 레이아웃 프리셋
                        st.markdown("**레이아웃 프리셋:**")
                        layout_presets = {
                            "선택 안함": None,
                            "중앙": "center",
                            "균등 분배": "spread",
                            "왼쪽 집중": "left_focus",
                            "오른쪽 집중": "right_focus",
                            "대화 배치 (2인)": "dialogue",
                            "그룹 배치": "group"
                        }
                        selected_preset = st.selectbox(
                            "프리셋 적용",
                            list(layout_presets.keys()),
                            key=f"int_preset_{int_selected_scene_id}"
                        )

                        if layout_presets[selected_preset]:
                            CanvasStateManager.apply_preset_layout(int_selected_scene_id, layout_presets[selected_preset])
                            st.info(f"✅ '{selected_preset}' 레이아웃이 적용되었습니다.")

                        # 캔버스 상태 초기화
                        from PIL import Image as PILImage
                        try:
                            bg_img = PILImage.open(int_bg_path)
                            bg_width, bg_height = bg_img.size
                        except:
                            bg_width, bg_height = 1920, 1080

                        CanvasStateManager.init_placements_for_scene(
                            scene_id=int_selected_scene_id,
                            characters=canvas_characters,
                            background_size=(bg_width, bg_height)
                        )

                        # 현재 배치 가져오기
                        placements = CanvasStateManager.get_placements(int_selected_scene_id)

                        st.divider()

                        # 인터랙티브 캔버스 렌더링
                        st.markdown("### 🎨 캔버스 편집")

                        # 캔버스 크기 설정
                        canvas_display_width = 800
                        canvas_display_height = int(800 * bg_height / bg_width)

                        # 캔버스 컴포넌트 호출
                        canvas_result = interactive_composite_canvas(
                            background_url=int_bg_path,
                            characters=placements,
                            canvas_width=canvas_display_width,
                            canvas_height=canvas_display_height,
                            key=f"canvas_{int_selected_scene_id}"
                        )

                        # 캔버스 결과 적용
                        if canvas_result:
                            CanvasStateManager.apply_canvas_result(int_selected_scene_id, canvas_result)
                            placements = CanvasStateManager.get_placements(int_selected_scene_id)

                        st.divider()

                        # 캐릭터 수동 조절 UI
                        st.markdown("### 🎛️ 캐릭터 세부 조절")

                        for i, p in enumerate(placements):
                            with st.expander(f"📌 {p['name']}", expanded=False):
                                col1, col2, col3 = st.columns(3)

                                with col1:
                                    new_x = st.slider(
                                        "X 위치",
                                        0.0, 1.0, float(p.get("x", 0.5)),
                                        key=f"int_x_{int_selected_scene_id}_{i}"
                                    )
                                    if new_x != p.get("x"):
                                        CanvasStateManager.update_character_position(
                                            int_selected_scene_id, p["id"], new_x, p.get("y", 0.5)
                                        )

                                with col2:
                                    new_y = st.slider(
                                        "Y 위치",
                                        0.0, 1.0, float(p.get("y", 0.5)),
                                        key=f"int_y_{int_selected_scene_id}_{i}"
                                    )
                                    if new_y != p.get("y"):
                                        CanvasStateManager.update_character_position(
                                            int_selected_scene_id, p["id"], p.get("x", 0.5), new_y
                                        )

                                with col3:
                                    new_scale = st.slider(
                                        "크기",
                                        0.1, 2.0, float(p.get("scale", 0.5)),
                                        step=0.05,
                                        key=f"int_scale_{int_selected_scene_id}_{i}"
                                    )
                                    if new_scale != p.get("scale"):
                                        CanvasStateManager.update_character_scale(
                                            int_selected_scene_id, p["id"], new_scale
                                        )

                                # 레이어 순서
                                layer_col1, layer_col2, layer_col3 = st.columns(3)
                                with layer_col1:
                                    if st.button("⬆️ 앞으로", key=f"int_front_{int_selected_scene_id}_{i}"):
                                        CanvasStateManager.bring_to_front(int_selected_scene_id, p["id"])
                                        st.rerun()
                                with layer_col2:
                                    if st.button("⬇️ 뒤로", key=f"int_back_{int_selected_scene_id}_{i}"):
                                        CanvasStateManager.send_to_back(int_selected_scene_id, p["id"])
                                        st.rerun()
                                with layer_col3:
                                    visible = p.get("visible", True)
                                    if st.checkbox("표시", value=visible, key=f"int_vis_{int_selected_scene_id}_{i}"):
                                        if not visible:
                                            CanvasStateManager.toggle_character_visibility(int_selected_scene_id, p["id"])
                                    else:
                                        if visible:
                                            CanvasStateManager.toggle_character_visibility(int_selected_scene_id, p["id"])

                        st.divider()

                        # 미리보기 및 저장
                        st.markdown("### 📸 미리보기 및 저장")

                        col1, col2 = st.columns(2)

                        with col1:
                            if st.button("👁️ 미리보기 생성", type="secondary", use_container_width=True, key="int_preview_btn"):
                                final_placements = CanvasStateManager.get_visible_placements(int_selected_scene_id)
                                preview_img = render_composite_preview(
                                    background_path=int_bg_path,
                                    placements=final_placements
                                )
                                if preview_img:
                                    st.session_state[f"int_preview_{int_selected_scene_id}"] = preview_img
                                    st.success("✅ 미리보기 생성 완료!")

                        with col2:
                            if st.button("💾 합성 이미지 저장", type="primary", use_container_width=True, key="int_save_btn"):
                                final_placements = CanvasStateManager.get_visible_placements(int_selected_scene_id)
                                composite_img = render_composite_preview(
                                    background_path=int_bg_path,
                                    placements=final_placements
                                )

                                if composite_img:
                                    output_dir = project_path / "images" / "composited"
                                    output_path = output_dir / f"scene_{int_selected_scene_id:04d}_interactive.png"

                                    saved_path = save_composite_image(
                                        image=composite_img,
                                        output_path=str(output_path)
                                    )

                                    if saved_path:
                                        st.success(f"✅ 저장 완료: {saved_path}")

                                        # 저장 정보 기록
                                        from utils.image_storage import save_composited_image
                                        result = {
                                            "success": True,
                                            "image_path": saved_path,
                                            "characters_used": [p["name"] for p in final_placements],
                                            "method": "interactive"
                                        }
                                        save_composited_image(int_selected_scene_id, result, project_path)
                                    else:
                                        st.error("저장 실패")

                        # 미리보기 이미지 표시
                        preview_key = f"int_preview_{int_selected_scene_id}"
                        if preview_key in st.session_state and st.session_state[preview_key]:
                            st.image(st.session_state[preview_key], caption=f"씬 {int_selected_scene_id} 합성 미리보기", use_container_width=True)
                    else:
                        st.warning("배경 이미지를 찾을 수 없습니다.")

            st.divider()

        # 합성 모드 선택 (인터랙티브 모드가 아닐 때만 표시)
        if not use_interactive:
            comp_mode = st.radio(
                "합성 범위",
                ["개별 씬 합성", "일괄 자동 합성"],
                horizontal=True,
                key="comp_mode"
            )

            if comp_mode == "개별 씬 합성":
                st.markdown("### 🎯 개별 씬 합성")

                # 배경이 있는 씬만 표시
                available_scenes = [s for s in comp_scenes if s.get("scene_id") in background_images]

                if not available_scenes:
                    st.warning("배경 이미지가 있는 씬이 없습니다.")
                else:
                    # 씬 선택
                    scene_options = {f"씬 {s.get('scene_id')}": s.get("scene_id") for s in available_scenes}
                    selected_scene_label = st.selectbox("합성할 씬", list(scene_options.keys()), key="comp_scene_select")
                    selected_scene_id = scene_options[selected_scene_label]

                    # 선택된 씬 정보
                    selected_scene = next((s for s in comp_scenes if s.get("scene_id") == selected_scene_id), None)

                    if selected_scene:
                        col1, col2 = st.columns([1, 1])

                        with col1:
                            st.markdown("**배경 미리보기**")
                            bg_info = background_images.get(selected_scene_id, {})
                            bg_path = bg_info.get("image_path") or bg_info.get("image_url")
                            if bg_path and Path(bg_path).exists():
                                st.image(bg_path, use_container_width=True)
                            else:
                                st.warning("배경 이미지를 찾을 수 없습니다.")

                        with col2:
                            st.markdown("**캐릭터 선택**")

                            # 씬에 등장하는 캐릭터
                            scene_char_names = selected_scene.get("characters", [])
                            st.caption(f"씬에 등장: {', '.join(scene_char_names) if scene_char_names else '없음'}")

                            # 캐릭터 선택
                            selected_chars_for_comp = []

                            if character_images:
                                for char_name, char_info in character_images.items():
                                    # 기본적으로 씬에 등장하는 캐릭터 선택
                                    default = char_name in scene_char_names

                                    if st.checkbox(char_name, value=default, key=f"comp_char_{selected_scene_id}_{char_name}"):
                                        # 크기 선택
                                        size = st.select_slider(
                                            f"{char_name} 크기",
                                            options=["tiny", "small", "medium", "large"],
                                            value="medium",
                                            key=f"comp_size_{selected_scene_id}_{char_name}"
                                        )

                                        selected_chars_for_comp.append({
                                            "name": char_name,
                                            "image_path": char_info.get("image_path") or char_info.get("image_url"),
                                            "size": size
                                        })
                            else:
                                st.info("캐릭터 이미지가 없습니다.")

                        # 합성 버튼
                        btn_label = f"🤖 씬 {selected_scene_id} AI 합성" if use_ai_composition else f"🎨 씬 {selected_scene_id} 합성"

                        if st.button(btn_label, type="primary", disabled=not bg_path, key="comp_single_btn"):
                            from core.image.scene_compositor import SceneCompositor

                            compositor = SceneCompositor(str(project_path))

                            with st.spinner("합성 중..." if not use_ai_composition else "AI 분석 및 합성 중..."):
                                if use_ai_composition:
                                    # AI 합성 모드
                                    bg_info_for_ai = background_images.get(selected_scene_id, {})
                                    bg_prompt = bg_info_for_ai.get("prompt", "")

                                    result = compositor.composite_scene_with_ai(
                                        background_path=bg_path,
                                        characters=selected_chars_for_comp,
                                        scene=selected_scene,
                                        background_prompt=bg_prompt,
                                        api_provider=ai_provider
                                    )
                                else:
                                    # 단순 합성 모드
                                    result = compositor.composite_scene(
                                        background_path=bg_path,
                                        characters=selected_chars_for_comp,
                                        scene_id=selected_scene_id
                                    )

                            if result.get("success"):
                                st.success("✅ 합성 완료!")
                                st.image(result["image_path"], caption=f"씬 {selected_scene_id} 합성 결과", use_container_width=True)

                                # 저장
                                save_composited_image(selected_scene_id, result, project_path)

                                # AI 분석 정보 표시
                                if use_ai_composition and result.get("scene_type"):
                                    with st.expander("🔍 AI 분석 결과"):
                                        st.write(f"**씬 타입:** {result.get('scene_type', 'N/A')}")
                                        st.write(f"**카메라 앵글:** {result.get('camera_angle', 'N/A')}")
                                        st.write(f"**구도 노트:** {result.get('composition_notes', 'N/A')}")

                                st.info(f"사용된 캐릭터: {', '.join(result.get('characters_used', []))}")

                                # ⭐ 합성 후 편집용 세션 저장
                                # 캐릭터 레이어 정보 구성
                                char_layers = []
                                placements = result.get("placements", [])
                                for i, char in enumerate(selected_chars_for_comp):
                                    # AI 합성인 경우 placements에서 위치 가져오기
                                    if placements and i < len(placements):
                                        p = placements[i]
                                        pos_x = p.get("x", 0.5)
                                        pos_y = p.get("y", 0.7)
                                        width = p.get("scale", 0.3)
                                    else:
                                        # 기본값
                                        pos_x = 0.3 + (i * 0.2)
                                        pos_y = 0.7
                                        width = 0.3

                                    char_layers.append({
                                        "id": char["name"],
                                        "name": char["name"],
                                        "image_url": char.get("image_path"),
                                        "x": pos_x,
                                        "y": pos_y,
                                        "width": width,
                                        "height": width * 1.3,
                                        "z_index": i + 1,
                                        "flip_x": False
                                    })

                                st.session_state["post_composite_result"] = {
                                    "scene_id": selected_scene_id,
                                    "background_url": bg_path,
                                    "character_layers": char_layers,
                                    "composite_image": result["image_path"],
                                    "timestamp": time.time()
                                }

                                st.info("💡 아래 '합성 후 편집' 섹션에서 캐릭터 위치를 조정할 수 있습니다.")
                            else:
                                st.error(f"합성 실패: {result.get('error', 'Unknown')}")

            else:  # 일괄 자동 합성
                st.markdown("### 🚀 일괄 자동 합성")

                if use_ai_composition:
                    st.caption("""
                    🤖 **AI 합성 모드**: 각 씬의 연출 가이드, 카메라 앵글 등을 AI가 분석하여
                    캐릭터를 자동으로 최적의 위치에 배치합니다.
                    """)
                else:
                    st.caption("""
                    📐 **단순 합성 모드**: 각 씬에 등장하는 캐릭터를 기본 레이아웃으로 합성합니다.
                    캐릭터 이미지가 없는 캐릭터는 건너뜁니다.
                    """)

                # 합성 가능한 씬 수 계산
                available_for_batch = [s for s in comp_scenes if s.get("scene_id") in background_images]

                st.info(f"📊 합성 가능한 씬: {len(available_for_batch)}개")

                btn_text = "🤖 모든 씬 AI 합성" if use_ai_composition else "📦 모든 씬 자동 합성"

                if st.button(btn_text, type="primary", use_container_width=True, key="comp_batch_btn"):
                    from core.image.scene_compositor import SceneCompositor

                    compositor = SceneCompositor(str(project_path))

                    # 프로그레스
                    task_name = "AI 일괄 합성" if use_ai_composition else "일괄 합성"
                    progress = StreamlitProgressUI(
                        task_name=task_name,
                        total_steps=len(available_for_batch),
                        show_logs=True
                    )

                    results = []

                    for i, scene in enumerate(available_for_batch):
                        scene_id = scene.get("scene_id")
                        progress.update(i + 1, f"씬 {scene_id} {'AI 분석 및 ' if use_ai_composition else ''}합성 중...")

                        # 배경 정보
                        bg_info = background_images.get(scene_id, {})
                        bg_path = bg_info.get("image_path") or bg_info.get("image_url")
                        bg_prompt = bg_info.get("prompt", "")

                        if not bg_path:
                            progress.error(f"씬 {scene_id}: 배경 없음")
                            continue

                        # 씬에 등장하는 캐릭터
                        scene_char_names = scene.get("characters", [])
                        chars_for_scene = []

                        for char_name in scene_char_names:
                            if char_name in character_images:
                                char_info = character_images[char_name]
                                chars_for_scene.append({
                                    "name": char_name,
                                    "image_path": char_info.get("image_path") or char_info.get("image_url"),
                                    "size": "medium"
                                })

                        # 합성 실행
                        if use_ai_composition:
                            # AI 합성
                            result = compositor.composite_scene_with_ai(
                                background_path=bg_path,
                                characters=chars_for_scene,
                                scene=scene,
                                background_prompt=bg_prompt,
                                api_provider=ai_provider
                            )
                        else:
                            # 단순 합성
                            result = compositor.composite_scene(
                                background_path=bg_path,
                                characters=chars_for_scene,
                                scene_id=scene_id
                            )

                        results.append(result)

                        if result.get("success"):
                            extra_info = ""
                            if use_ai_composition and result.get("scene_type"):
                                extra_info = f" (타입: {result.get('scene_type')})"
                            progress.success(f"씬 {scene_id} 합성 완료! 캐릭터: {len(chars_for_scene)}명{extra_info}")
                            save_composited_image(scene_id, result, project_path)
                        else:
                            progress.error(f"씬 {scene_id} 실패: {result.get('error', 'Unknown')}")

                    success_count = sum(1 for r in results if r.get("success"))
                    progress.complete(f"{'AI ' if use_ai_composition else ''}일괄 합성 완료! 성공: {success_count}/{len(available_for_batch)}")

                    # AI 분석 결과 요약
                    if use_ai_composition and success_count > 0:
                        with st.expander("🔍 AI 분석 결과 요약"):
                            for r in results:
                                if r.get("success") and r.get("scene_type"):
                                    st.write(f"- **씬 {r.get('scene_id')}**: {r.get('scene_type')} / {r.get('camera_angle', 'N/A')}")

                    if success_count > 0:
                        st.balloons()
                        update_project_step(6)

        # ==========================================
        # ⭐ 합성 후 편집 섹션
        # ==========================================
        st.markdown("---")
        st.markdown("## ✏️ 합성 후 편집")

        if "post_composite_result" in st.session_state and st.session_state["post_composite_result"]:
            post_result = st.session_state["post_composite_result"]
            post_scene_id = post_result.get("scene_id")
            post_bg_url = post_result.get("background_url")
            post_char_layers = post_result.get("character_layers", [])

            st.info("💡 캐릭터를 드래그하여 위치/크기를 조정한 후, '재합성'을 클릭하세요.")

            # 탭으로 드래그 편집 / 수동 입력 구분
            edit_tab_drag, edit_tab_manual = st.tabs(["🖱️ 드래그 편집", "🔢 수동 입력"])

            with edit_tab_drag:
                if post_bg_url and Path(post_bg_url).exists():
                    # 캔버스 크기 계산
                    from PIL import Image as PILImage
                    try:
                        bg_img_for_size = PILImage.open(post_bg_url)
                        bg_w, bg_h = bg_img_for_size.size
                        aspect = bg_h / bg_w
                        edit_canvas_width = 900
                        edit_canvas_height = int(edit_canvas_width * aspect)
                    except:
                        edit_canvas_width = 900
                        edit_canvas_height = 506

                    # 배경 제거 처리 안내 (처음 로드 시)
                    st.caption("캐릭터 배경을 자동으로 투명 처리합니다 (첫 로드 시 시간이 걸릴 수 있습니다)")

                    # 인터랙티브 편집기 렌더링 (내부에서 배경 제거 처리)
                    post_composite_editor(
                        background_url=post_bg_url,
                        character_layers=post_char_layers,
                        canvas_width=edit_canvas_width,
                        canvas_height=edit_canvas_height,
                        editor_id=f"post_scene_{post_scene_id}"
                    )

                    st.caption("1️⃣ 캐릭터 드래그로 위치 조정 → 2️⃣ '위치 저장' 클릭 → 3️⃣ 아래 '재합성' 버튼 클릭")
                else:
                    st.warning("배경 이미지를 찾을 수 없습니다.")

            with edit_tab_manual:
                st.caption("드래그가 안 되면 여기서 직접 수치를 입력하세요.")

                updated_layers = []
                for i, layer in enumerate(post_char_layers):
                    st.markdown(f"**{layer.get('name', f'캐릭터 {i+1}')}**")

                    mcols = st.columns(5)

                    with mcols[0]:
                        new_x = st.slider(
                            "X 위치", 0.0, 1.0, float(layer.get('x', 0.5)),
                            key=f"post_edit_x_{post_scene_id}_{layer.get('name', i)}"
                        )

                    with mcols[1]:
                        new_y = st.slider(
                            "Y 위치", 0.0, 1.0, float(layer.get('y', 0.7)),
                            key=f"post_edit_y_{post_scene_id}_{layer.get('name', i)}"
                        )

                    with mcols[2]:
                        new_width = st.slider(
                            "크기", 0.1, 1.0, float(layer.get('width', 0.3)),
                            key=f"post_edit_w_{post_scene_id}_{layer.get('name', i)}"
                        )

                    with mcols[3]:
                        new_z = st.number_input(
                            "레이어", 1, 10, int(layer.get('z_index', i+1)),
                            key=f"post_edit_z_{post_scene_id}_{layer.get('name', i)}"
                        )

                    with mcols[4]:
                        new_flip = st.checkbox(
                            "반전",
                            value=layer.get('flip_x', False),
                            key=f"post_edit_flip_{post_scene_id}_{layer.get('name', i)}"
                        )

                    updated_layers.append({
                        **layer,
                        "x": new_x,
                        "y": new_y,
                        "width": new_width,
                        "height": new_width * 1.3,
                        "z_index": new_z,
                        "flip_x": new_flip
                    })

                    st.markdown("---")

                if st.button("✅ 수동 조정 적용", key="post_edit_manual_apply"):
                    st.session_state["post_composite_result"]["character_layers"] = updated_layers
                    st.success("적용됨!")
                    st.rerun()

            # 재합성 버튼
            st.markdown("---")
            st.markdown("### 🔄 재합성")

            recomp_col1, recomp_col2, recomp_col3 = st.columns([1, 2, 1])

            with recomp_col2:
                if st.button("🔄 재합성 (조정된 위치로)", type="primary", use_container_width=True, key="post_recomposite_btn"):
                    st.info("💡 '위치 저장' 버튼을 먼저 클릭했는지 확인하세요!")

                    # 재합성 실행
                    with st.spinner("재합성 중..."):
                        from utils.composite_utils import composite_with_placements, save_composite_result
                        from PIL import Image as PILImage

                        # 현재 캐릭터 레이어 정보 가져오기
                        current_layers = st.session_state["post_composite_result"]["character_layers"]

                        # composite_with_placements 용 형식으로 변환
                        placements_for_composite = []
                        for layer in current_layers:
                            placements_for_composite.append({
                                "image_path": layer.get("image_url") or layer.get("image_path"),
                                "x": layer.get("x", 0.5),
                                "y": layer.get("y", 0.7),
                                "scale": layer.get("width", 0.3),
                                "z_index": layer.get("z_index", 1),
                                "visible": True
                            })

                        # 합성 실행
                        recomp_image = composite_with_placements(
                            background_path=post_bg_url,
                            placements=placements_for_composite,
                            output_size=(1920, 1080)
                        )

                        if recomp_image:
                            # 저장
                            recomp_output_dir = project_path / "images" / "composited"
                            recomp_output_dir.mkdir(parents=True, exist_ok=True)
                            recomp_filename = f"scene_{post_scene_id:04d}_recomposite_{int(time.time())}.png"
                            recomp_output_path = recomp_output_dir / recomp_filename

                            save_success = save_composite_result(
                                image=recomp_image,
                                output_path=str(recomp_output_path),
                                format="PNG"
                            )

                            if save_success:
                                st.success(f"✅ 재합성 완료!")
                                st.image(str(recomp_output_path), caption="재합성 결과", use_container_width=True)

                                # 세션 업데이트
                                st.session_state["post_composite_result"]["composite_image"] = str(recomp_output_path)

                                # 다운로드 버튼
                                with open(recomp_output_path, "rb") as f:
                                    st.download_button(
                                        "💾 다운로드",
                                        data=f,
                                        file_name=recomp_filename,
                                        mime="image/png",
                                        key="post_recomp_download"
                                    )
                            else:
                                st.error("저장 실패")
                        else:
                            st.error("재합성 실패")

            # 편집 초기화
            edit_ctrl_col1, edit_ctrl_col2 = st.columns(2)
            with edit_ctrl_col1:
                if st.button("🗑️ 편집 초기화", key="post_edit_clear"):
                    del st.session_state["post_composite_result"]
                    st.rerun()
            with edit_ctrl_col2:
                if st.button("✅ 편집 완료", key="post_edit_done"):
                    st.session_state["final_composite"] = st.session_state["post_composite_result"]
                    del st.session_state["post_composite_result"]
                    st.success("저장됨!")
                    st.rerun()

        else:
            st.caption("합성을 먼저 실행하면 여기서 캐릭터 위치를 조정할 수 있습니다.")

        # 합성된 이미지 갤러리
        st.markdown("---")
        st.markdown("### 🖼️ 합성된 이미지")

        comp_image_dir = project_path / "images" / "composited"
        if comp_image_dir.exists():
            comp_images = list(comp_image_dir.glob("*.png"))
            if comp_images:
                cols = st.columns(4)
                for i, img_path in enumerate(comp_images[:8]):
                    with cols[i % 4]:
                        st.image(str(img_path), caption=img_path.stem, use_container_width=True)
                if len(comp_images) > 8:
                    st.caption(f"... 외 {len(comp_images) - 8}개")
            else:
                st.info("아직 합성된 이미지가 없습니다.")
        else:
            st.info("합성 이미지 폴더가 없습니다.")

# === 세그먼트 기반 생성 탭 ===
with tab_generate:
    st.subheader("이미지 생성 설정")

    # 프롬프트 로드
    prompts = load_image_prompts(project_path)

    if not prompts:
        st.warning("이미지 프롬프트가 없습니다. 5단계에서 먼저 생성하세요.")
        st.stop()

    st.success(f"✅ {len(prompts)}개 프롬프트 로드됨")

    col1, col2 = st.columns(2)

    with col1:
        # 모델 선택
        model_options = {m["name"]: m["id"] for m in IMAGE_MODELS}
        selected_model_name = st.selectbox(
            "모델 선택",
            list(model_options.keys()),
            help="Free 모델은 10장/분 제한이 있습니다."
        )
        selected_model = model_options[selected_model_name]

        # 비용 정보
        model_info = next((m for m in IMAGE_MODELS if m["id"] == selected_model), None)
        if model_info:
            estimated_cost = model_info["price"] * len(prompts)
            st.caption(f"예상 비용: ${estimated_cost:.2f}")

    with col2:
        # 이미지 크기 (FLUX 모델 제한: 64~1792)
        width = st.selectbox("너비", [1792, 1280, 1024], index=0, help="FLUX 모델 최대: 1792")
        height = st.selectbox("높이", [1024, 720, 576], index=0, help="16:9 비율에 맞춤")

    # 스타일 선택 (프리셋 또는 기본 옵션)
    st.markdown("### 🎨 스타일 선택")

    style_method = st.radio("스타일 방식", ["프리셋 사용", "기본 옵션"], horizontal=True, key="seg_style_method")

    if style_method == "프리셋 사용":
        if "preset_manager" not in st.session_state:
            st.session_state.preset_manager = PromptPresetManager()
        preset_manager = st.session_state.preset_manager

        selected_preset, seg_style_prompt = render_style_selector(
            preset_manager,
            category="styles",
            key_prefix="seg_gen",
            show_preview=False,
            show_prompt=True,
            allow_custom=True,
            default_index=1
        )
        style_prefix = "custom"  # 플래그로 사용
    else:
        # 기본 스타일 프리픽스
        style_prefix = st.selectbox(
            "스타일 프리픽스",
            list(IMAGE_STYLE_PREFIXES.keys()),
            format_func=lambda x: f"{x}: {IMAGE_STYLE_PREFIXES[x][:50]}..."
        )
        seg_style_prompt = None

    # 시드 설정
    use_seed = st.checkbox("고정 시드 사용", value=False)
    seed = st.number_input("시드 값", value=42, disabled=not use_seed) if use_seed else None

    st.divider()

    # 생성 범위 선택
    st.subheader("생성 범위")

    col1, col2 = st.columns(2)
    with col1:
        start_idx = st.number_input("시작 인덱스", min_value=0, max_value=len(prompts)-1, value=0)
    with col2:
        end_idx = st.number_input("끝 인덱스", min_value=0, max_value=len(prompts)-1, value=len(prompts)-1)

    selected_prompts = prompts[start_idx:end_idx+1]
    st.caption(f"선택된 프롬프트: {len(selected_prompts)}개")

    st.divider()

    # 예상 시간 표시
    from core.image.together_client import TogetherImageClient
    client_for_estimate = TogetherImageClient()
    estimated_time = client_for_estimate.estimate_time(len(selected_prompts), selected_model)

    st.info(f"""
    **예상 정보**
    - 이미지 수: {len(selected_prompts)}개
    - 예상 시간: {estimated_time // 60}분 {estimated_time % 60}초
    - Free 모델은 분당 10개 제한으로 인해 이미지당 ~20초 소요됩니다.
    """)

    # 생성 버튼
    if st.button("🎨 이미지 생성 시작", type="primary", use_container_width=True):
        output_dir = get_content_images_dir(project_path)

        # UI 요소
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.empty()
        time_info = st.empty()

        logs = []
        start_time = time.time()

        def add_log(message):
            """로그 추가 및 표시"""
            timestamp = time.strftime("%H:%M:%S")
            logs.append(f"[{timestamp}] {message}")
            # 최근 8개 로그만 표시
            log_container.code("\n".join(logs[-8:]), language=None)

        def on_progress(current, total):
            """진행 상황 업데이트"""
            progress_bar.progress(current / total)
            elapsed = time.time() - start_time
            avg_time = elapsed / current if current > 0 else 0
            remaining = avg_time * (total - current)
            status_text.text(f"진행: {current}/{total} | 경과: {elapsed:.0f}초 | 남은 시간: ~{remaining:.0f}초")

        results = []

        try:
            from core.image.together_client import TogetherImageClient

            client = TogetherImageClient()

            add_log(f"이미지 생성 시작 (총 {len(selected_prompts)}개)")
            add_log(f"모델: {selected_model}")
            add_log(f"크기: {width}x{height}")

            # 스타일 프롬프트 결정
            if style_prefix == "custom" and seg_style_prompt:
                final_style_prefix = seg_style_prompt
                add_log(f"스타일: 커스텀 프리셋")
            else:
                final_style_prefix = IMAGE_STYLE_PREFIXES.get(style_prefix, "")
                add_log(f"스타일: {style_prefix}")

            results = client.generate_batch(
                prompts=selected_prompts,
                output_dir=str(output_dir),
                model=selected_model,
                style_prefix=final_style_prefix,
                width=width,
                height=height,
                seed=seed,
                on_progress=on_progress
            )

            # 로그 저장
            save_image_generation_log(project_path, results)

            # === 세션 상태에 저장 (세그먼트 기반 생성) ===
            if "generated_images" not in st.session_state:
                st.session_state["generated_images"] = []

            from datetime import datetime
            for idx, r in enumerate(results):
                if r.get("status") == "success":
                    image_data = {
                        "scene_id": idx + 1,  # 세그먼트 기반이므로 순서대로 번호 부여
                        "prompt": r.get("prompt", ""),
                        "image_path": str(output_dir / r.get("filename", "")),
                        "image_url": "",
                        "created_at": datetime.now().isoformat(),
                        "model": selected_model,
                        "filename": r.get("filename", "")
                    }
                    st.session_state["generated_images"].append(image_data)

            print(f"[이미지 생성] 세그먼트 기반: 세션에 {len(st.session_state['generated_images'])}개 이미지 저장됨")

            # 결과 요약
            success_count = sum(1 for r in results if r["status"] == "success")
            failed_count = len(results) - success_count
            total_time = time.time() - start_time

            progress_bar.progress(1.0)
            status_text.empty()

            add_log(f"완료! {success_count}/{len(results)} 성공")
            add_log(f"총 소요 시간: {total_time:.1f}초 (평균: {total_time/len(results):.1f}초/개)")

            if failed_count == 0:
                st.success(f"✅ {success_count}개 이미지 생성 완료! ({total_time:.0f}초)")
                update_project_step(6)
            else:
                st.warning(f"⚠️ {success_count}개 성공, {failed_count}개 실패 ({total_time:.0f}초)")

                # 실패한 항목 표시
                with st.expander("실패 상세"):
                    for r in results:
                        if r["status"] == "failed":
                            st.error(f"{r['filename']}: {r.get('error', 'Unknown error')}")

        except Exception as e:
            add_log(f"오류 발생: {str(e)}")
            st.error(f"생성 실패: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# === 수동 생성 탭 ===
with tab_manual:
    st.subheader("✏️ 수동 이미지 생성")

    st.info("""
    💡 **수동 생성 모드**
    - 프롬프트를 직접 입력하여 이미지 생성
    - 외부 프롬프트 파일 업로드 지원
    - 개별 또는 일괄 생성 가능
    """)

    # 입력 방식 선택
    manual_input_method = st.radio(
        "입력 방식",
        ["✏️ 직접 입력", "📁 파일 업로드"],
        horizontal=True,
        key="manual_img_input_method"
    )

    manual_prompts = []

    if manual_input_method == "✏️ 직접 입력":
        st.markdown("#### 프롬프트 입력")
        manual_prompt_text = st.text_area(
            "프롬프트 (여러 개 입력시 줄바꿈으로 구분)",
            height=200,
            placeholder="A beautiful sunset over mountains, digital art style\nA cat sitting on a windowsill, watercolor painting\n...",
            key="manual_img_prompt_text"
        )

        if manual_prompt_text.strip():
            manual_prompts = [p.strip() for p in manual_prompt_text.strip().split("\n") if p.strip()]
            st.info(f"📝 {len(manual_prompts)}개 프롬프트 감지됨")

    else:  # 파일 업로드
        st.markdown("#### 파일 업로드")
        uploaded_file = st.file_uploader(
            "프롬프트 파일",
            type=["txt", "json", "csv"],
            help="txt: 줄바꿈 구분, json: [{\"prompt\": \"...\"}] 형식, csv: prompt 컬럼 필요",
            key="manual_img_file_upload"
        )

        if uploaded_file:
            try:
                content = uploaded_file.read().decode("utf-8")

                if uploaded_file.name.endswith(".txt"):
                    manual_prompts = [p.strip() for p in content.split("\n") if p.strip()]

                elif uploaded_file.name.endswith(".json"):
                    data = json.loads(content)
                    if isinstance(data, list):
                        manual_prompts = [item.get("prompt", item) if isinstance(item, dict) else str(item) for item in data]
                    else:
                        st.error("JSON은 배열 형식이어야 합니다.")

                elif uploaded_file.name.endswith(".csv"):
                    import csv
                    import io
                    reader = csv.DictReader(io.StringIO(content))
                    manual_prompts = [row.get("prompt", "") for row in reader if row.get("prompt")]

                if manual_prompts:
                    st.success(f"✅ {len(manual_prompts)}개 프롬프트 로드됨")
                    with st.expander("프롬프트 미리보기"):
                        for i, p in enumerate(manual_prompts[:10]):
                            st.text(f"{i+1}. {p[:100]}...")
                        if len(manual_prompts) > 10:
                            st.caption(f"... 외 {len(manual_prompts) - 10}개")

            except Exception as e:
                st.error(f"파일 파싱 오류: {str(e)}")

    st.divider()

    # 생성 설정
    st.markdown("### ⚙️ 생성 설정")

    col1, col2 = st.columns(2)

    with col1:
        # 스타일 선택
        st.markdown("#### 🎨 스타일")
        use_style_prefix = st.checkbox("스타일 프리픽스 추가", value=True, key="manual_use_style")

        if use_style_prefix:
            if "preset_manager" not in st.session_state:
                st.session_state.preset_manager = PromptPresetManager()
            preset_manager = st.session_state.preset_manager

            manual_preset, manual_style_prompt = render_style_selector(
                preset_manager,
                category="styles",
                key_prefix="manual_gen",
                show_preview=False,
                show_prompt=True,
                allow_custom=True,
                default_index=1
            )
        else:
            manual_style_prompt = ""

    with col2:
        # 이미지 크기
        st.markdown("#### 📐 이미지 크기")
        manual_width = st.selectbox("너비", [1792, 1280, 1024, 768], index=1, key="manual_width")
        manual_height = st.selectbox("높이", [1024, 720, 576, 512], index=0, key="manual_height")

        # 모델 선택
        st.markdown("#### 🤖 모델")
        manual_model_options = {m["name"]: m["id"] for m in IMAGE_MODELS}
        manual_model_name = st.selectbox(
            "모델",
            list(manual_model_options.keys()),
            key="manual_model_select"
        )
        manual_model = manual_model_options[manual_model_name]

    st.divider()

    # 생성 버튼
    if manual_prompts:
        st.markdown("### 🚀 생성 실행")

        # 예상 시간
        is_free_model = "Free" in manual_model
        time_per_image = 20 if is_free_model else 5
        total_est_time = len(manual_prompts) * time_per_image

        st.info(f"""
        **예상 정보**
        - 이미지 수: {len(manual_prompts)}개
        - 예상 시간: 약 {total_est_time // 60}분 {total_est_time % 60}초
        """)

        if st.button("🎨 수동 이미지 생성 시작", type="primary", use_container_width=True, key="manual_gen_btn"):
            from core.image.together_client import TogetherImageClient

            output_dir = get_content_images_dir(project_path)
            client = TogetherImageClient()

            progress_bar = st.progress(0)
            status_text = st.empty()
            log_container = st.empty()
            image_preview = st.empty()

            logs = []
            start_time = time.time()
            success_count = 0

            def add_log(msg):
                timestamp = time.strftime("%H:%M:%S")
                logs.append(f"[{timestamp}] {msg}")
                log_container.code("\n".join(logs[-8:]), language=None)

            add_log(f"수동 이미지 생성 시작 (총 {len(manual_prompts)}개)")
            add_log(f"모델: {manual_model}")

            for i, prompt in enumerate(manual_prompts):
                progress_bar.progress((i + 1) / len(manual_prompts))

                # 스타일 프리픽스 적용
                if use_style_prefix and manual_style_prompt:
                    final_prompt = f"{manual_style_prompt}, {prompt}"
                else:
                    final_prompt = prompt

                add_log(f"[{i+1}/{len(manual_prompts)}] 생성 중...")
                status_text.text(f"진행: {i+1}/{len(manual_prompts)}")

                try:
                    img_data = client.generate_image(
                        prompt=final_prompt,
                        model=manual_model,
                        width=manual_width,
                        height=manual_height
                    )

                    # 파일 저장
                    timestamp = int(time.time() * 1000)
                    filename = f"manual_{i+1:04d}_{timestamp}.png"
                    filepath = output_dir / filename

                    with open(filepath, "wb") as f:
                        f.write(img_data)

                    add_log(f"✅ {filename} 저장 완료")
                    image_preview.image(str(filepath), caption=f"생성됨: {filename}", width=400)
                    success_count += 1

                except Exception as e:
                    add_log(f"❌ 이미지 {i+1} 실패: {str(e)}")

            total_time = time.time() - start_time
            progress_bar.progress(1.0)
            status_text.empty()

            if success_count == len(manual_prompts):
                st.success(f"✅ 수동 이미지 생성 완료! {success_count}/{len(manual_prompts)} 성공 ({total_time:.0f}초)")
                st.balloons()
                update_project_step(6)
            elif success_count > 0:
                st.warning(f"⚠️ 일부 완료: {success_count}/{len(manual_prompts)} 성공 ({total_time:.0f}초)")
            else:
                st.error("❌ 모든 이미지 생성 실패")
    else:
        st.warning("⚠️ 프롬프트를 입력하거나 파일을 업로드하세요.")

# === 갤러리 탭 ===
with tab_gallery:
    st.subheader("🖼️ 생성된 이미지")

    # 씬 이미지와 컨텐츠 이미지 모두 표시
    scene_images = list_scene_images(project_path)
    content_images = list_content_images(project_path)

    # 이미지 소스 선택
    image_source = st.radio(
        "이미지 소스",
        ["씬 이미지", "세그먼트 이미지", "전체"],
        horizontal=True
    )

    if image_source == "씬 이미지":
        images = scene_images
    elif image_source == "세그먼트 이미지":
        images = content_images
    else:
        images = scene_images + content_images

    if images:
        st.caption(f"총 {len(images)}개 이미지")

        # 그리드 표시
        cols_per_row = 4
        for i in range(0, len(images), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(images):
                    with col:
                        st.image(str(images[idx]), use_container_width=True)
                        st.caption(images[idx].name)

        st.divider()

        # 다음 단계
        st.success("✅ 6단계 완료!")
        col1, col2 = st.columns(2)
        with col1:
            st.page_link("pages/7_📦_Vrew_Export.py", label="📦 7단계: Vrew Export로 이동", icon="➡️")
        with col2:
            st.page_link("pages/8_📋_스토리보드.py", label="📋 8단계: 스토리보드 확인", icon="➡️")

    else:
        st.info("생성된 이미지가 없습니다. '씬 기반 생성' 또는 '세그먼트 기반' 탭에서 이미지를 생성하세요.")

        # 디버그 정보
        with st.expander("🔍 디버그 정보"):
            st.write("**이미지 디렉토리 확인:**")
            scenes_dir = project_path / "images" / "scenes"
            content_dir = project_path / "images" / "content"

            st.write(f"- 씬 이미지 폴더: `{scenes_dir}`")
            st.write(f"  - 존재: {scenes_dir.exists()}")
            if scenes_dir.exists():
                scene_pngs = list(scenes_dir.glob("*.png"))
                st.write(f"  - PNG 파일 수: {len(scene_pngs)}")

            st.write(f"- 세그먼트 이미지 폴더: `{content_dir}`")
            st.write(f"  - 존재: {content_dir.exists()}")
            if content_dir.exists():
                content_pngs = list(content_dir.glob("*.png"))
                st.write(f"  - PNG 파일 수: {len(content_pngs)}")

            st.write("**세션 상태:**")
            session_images = st.session_state.get("generated_images", [])
            st.write(f"- generated_images: {len(session_images)}개")

            if session_images:
                st.write("**세션에 저장된 이미지:**")
                for img in session_images[:5]:
                    st.write(f"  - 씬 {img.get('scene_id')}: {img.get('image_path', 'N/A')[:50]}...")

# === 재생성 탭 ===
with tab_regenerate:
    st.subheader("🔄 개별 이미지 재생성")

    prompts = load_image_prompts(project_path)

    if prompts:
        # 프롬프트 선택
        prompt_options = {f"{p['filename']} (세그먼트 {p['segment_indices'][0]}-{p['segment_indices'][-1]})": i for i, p in enumerate(prompts)}
        selected_prompt_key = st.selectbox("재생성할 이미지", list(prompt_options.keys()))
        selected_idx = prompt_options[selected_prompt_key]
        selected_prompt = prompts[selected_idx]

        # 현재 프롬프트 표시
        st.text_area("현재 프롬프트", selected_prompt["prompt"], height=100)

        # 수정된 프롬프트
        modified_prompt = st.text_area(
            "수정된 프롬프트 (선택)",
            selected_prompt["prompt"],
            height=100,
            key="modified_prompt"
        )

        if st.button("🔄 재생성", type="primary"):
            with st.spinner("이미지 재생성 중..."):
                try:
                    from core.image.together_client import TogetherImageClient

                    client = TogetherImageClient()
                    output_dir = get_content_images_dir(project_path)

                    img_data = client.generate_image(
                        prompt=modified_prompt,
                        model=selected_model if 'selected_model' in dir() else "black-forest-labs/FLUX.1-schnell-Free"
                    )

                    filepath = output_dir / selected_prompt["filename"]
                    with open(filepath, "wb") as f:
                        f.write(img_data)

                    st.success(f"✅ {selected_prompt['filename']} 재생성 완료!")
                    st.image(str(filepath))

                except Exception as e:
                    st.error(f"재생성 실패: {str(e)}")

    else:
        st.info("프롬프트가 없습니다.")
