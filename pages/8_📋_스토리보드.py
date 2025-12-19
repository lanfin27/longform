"""
8단계: 스토리보드

씬별로 이미지 + 스크립트 + TTS를 한눈에 보고 편집
"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    get_current_project_config,
    render_project_sidebar
)
from utils.api_helper import show_api_status_sidebar

# 페이지 설정
st.set_page_config(
    page_title="스토리보드",
    page_icon="📋",
    layout="wide"
)

render_project_sidebar()
show_api_status_sidebar()

if not ensure_project_selected():
    st.stop()

project_path = get_current_project()
project_config = get_current_project_config()

st.title("📋 8단계: 스토리보드")
st.caption("씬별 이미지, 스크립트, TTS를 한눈에 확인하고 편집")

st.divider()

# === 탭 구성 ===
tab_auto, tab_manual = st.tabs(["🔄 자동 조합", "✏️ 수동 구성"])

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
            # 이미지 파일 목록 (scenes + content 모두 수집)
            image_files = []
            if scenes_images_dir.exists():
                image_files.extend(sorted(scenes_images_dir.glob("*.png")))
            if content_images_dir.exists():
                image_files.extend(sorted(content_images_dir.glob("*.png")))

            # 중복 제거 (같은 이름 파일이 있을 경우 scenes 우선)
            seen_names = set()
            unique_images = []
            for img in image_files:
                if img.stem not in seen_names:
                    unique_images.append(img)
                    seen_names.add(img.stem)
            image_files = unique_images

            image_map = {img.stem: img for img in image_files}
            print(f"[스토리보드] 총 {len(image_files)}개 이미지 로드됨")

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

            # 뷰 모드 선택
            view_mode = st.radio(
                "뷰 모드",
                ["카드 뷰", "테이블 뷰", "타임라인 뷰"],
                horizontal=True
            )

            # === 카드 뷰 ===
            if view_mode == "카드 뷰":
                st.subheader("🎬 스토리보드 (카드 뷰)")

                for i, scene in enumerate(scenes):
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

                                if scene_image and scene_image.exists():
                                    st.image(str(scene_image), width=300)
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

                            # 이미지
                            if idx < len(image_files):
                                st.image(str(image_files[idx]), use_container_width=True)
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
