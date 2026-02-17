# -*- coding: utf-8 -*-
"""
13단계: 썸네일 이미지 생성

NanoBanana API를 활용한 커스텀 이미지 생성 도구
- 프롬프트 기반 이미지 생성
- 레퍼런스 이미지 스타일 참조
- 다양한 비율 지원 (16:9, 1:1, 9:16 등)
"""
import streamlit as st
import os
import io
from datetime import datetime
from pathlib import Path
from PIL import Image

# 프로젝트 루트 설정
ROOT_DIR = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(ROOT_DIR))

# NanoBanana API 임포트
try:
    from utils.gemini_image_generator import (
        GeminiImageGenerator,
        GeminiGenerationResult,
        GEMINI_IMAGE_MODELS,
        SUPPORTED_ASPECT_RATIOS
    )
    GEMINI_AVAILABLE = True
except ImportError as e:
    GEMINI_AVAILABLE = False
    GEMINI_IMPORT_ERROR = str(e)

# 프로젝트 매니저 임포트
try:
    from utils.project_manager import (
        get_current_project,
        render_project_sidebar
    )
    PROJECT_MANAGER_AVAILABLE = True
except ImportError:
    PROJECT_MANAGER_AVAILABLE = False


# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="썸네일 생성",
    page_icon="🖼️",
    layout="wide"
)

st.title("🖼️ 썸네일 이미지 생성")
st.caption("NanoBanana API를 활용하여 커스텀 이미지를 생성합니다.")

# 사이드바 렌더링
if PROJECT_MANAGER_AVAILABLE:
    render_project_sidebar()

# ============================================================
# API 상태 확인
# ============================================================
if not GEMINI_AVAILABLE:
    st.error(f"❌ Gemini Image API를 불러올 수 없습니다: {GEMINI_IMPORT_ERROR}")
    st.info("💡 `pip install google-genai --upgrade` 로 설치하세요.")
    st.stop()

# ============================================================
# 세션 상태 초기화
# ============================================================
if 'thumbnail_history' not in st.session_state:
    st.session_state.thumbnail_history = []

if 'last_generated_image' not in st.session_state:
    st.session_state.last_generated_image = None

# ============================================================
# 저장 경로 설정
# ============================================================
def get_thumbnail_save_dir():
    """썸네일 저장 디렉토리 가져오기"""
    # 프로젝트가 선택된 경우 프로젝트 폴더에 저장
    if PROJECT_MANAGER_AVAILABLE:
        project = get_current_project()
        if project:
            # get_current_project()는 Path 또는 dict를 반환할 수 있음
            if isinstance(project, (str, Path)):
                project_path = Path(project)
            elif isinstance(project, dict):
                project_path = Path(project.get('path', ''))
            else:
                project_path = Path(str(project))

            if project_path.exists():
                thumb_dir = project_path / "images" / "thumbnails"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                return thumb_dir

    # 기본 경로
    default_dir = ROOT_DIR / "data" / "images" / "thumbnails"
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir


# ============================================================
# 메인 UI
# ============================================================
st.divider()

col_settings, col_preview = st.columns([1, 1])

# ── 설정 영역 ──
with col_settings:
    st.subheader("⚙️ 생성 설정")

    # 1. 모델 선택
    model_options = list(GEMINI_IMAGE_MODELS.keys())
    model_labels = {
        "gemini_nano_banana": "🍌 Nano Banana (빠름, ~15원/장)",
        "gemini_nano_banana_pro": "🍌✨ Nano Banana Pro (고품질, ~25원/장)"
    }

    selected_model = st.radio(
        "생성 모델",
        options=model_options,
        format_func=lambda x: model_labels.get(x, x),
        horizontal=True,
        index=1,  # Pro 기본 선택
        key="thumbnail_model"
    )

    # 모델 정보 표시
    model_info = GEMINI_IMAGE_MODELS.get(selected_model, {})
    st.caption(f"ℹ️ {model_info.get('description', '')}")

    # 2. 이미지 비율 선택
    ratio_col1, ratio_col2 = st.columns(2)

    with ratio_col1:
        # 주요 비율만 표시
        common_ratios = ["16:9", "1:1", "9:16", "4:3", "3:4", "21:9"]
        aspect_ratio = st.selectbox(
            "이미지 비율",
            options=common_ratios,
            index=0,  # 16:9 기본 (썸네일용)
            key="thumbnail_aspect_ratio",
            help="16:9 = 유튜브 썸네일, 1:1 = 인스타그램, 9:16 = 릴스/숏츠"
        )

    with ratio_col2:
        # 비율에 따른 해상도 표시
        ratio_resolutions = {
            "16:9": "1920 x 1080",
            "1:1": "1024 x 1024",
            "9:16": "1080 x 1920",
            "4:3": "1024 x 768",
            "3:4": "768 x 1024",
            "21:9": "2560 x 1080"
        }
        st.text_input(
            "예상 해상도",
            value=ratio_resolutions.get(aspect_ratio, "1024 x 1024"),
            disabled=True,
            key="thumbnail_resolution"
        )

    st.markdown("---")

    # 3. 프롬프트 입력
    st.markdown("**✍️ 이미지 생성 프롬프트**")

    prompt = st.text_area(
        "프롬프트",
        height=180,
        placeholder="""생성할 이미지를 상세히 설명하세요...

예시:
A dramatic YouTube thumbnail showing a glowing AI chip in the center,
with futuristic circuit board patterns in the background,
blue and purple neon lighting,
bold text "AI 혁명" at the top,
high quality, professional design, 4K""",
        help="영어 또는 한국어 프롬프트 모두 지원됩니다. 상세할수록 좋은 결과가 나옵니다.",
        key="thumbnail_prompt",
        label_visibility="collapsed"
    )

    # 프롬프트 길이 표시
    if prompt:
        st.caption(f"📝 {len(prompt)} 문자")

    # 4. 네거티브 프롬프트 (선택사항)
    with st.expander("🚫 네거티브 프롬프트 (선택사항)", expanded=False):
        negative_prompt = st.text_area(
            "제외할 요소",
            height=80,
            placeholder="예: blurry, low quality, watermark, text errors",
            help="생성에서 제외하고 싶은 요소를 입력하세요.",
            key="thumbnail_negative_prompt",
            label_visibility="collapsed"
        )

    st.markdown("---")

    # 5. 레퍼런스 이미지 업로드 (선택사항)
    st.markdown("**📎 레퍼런스 이미지 (선택사항)**")
    st.caption("스타일을 참조할 이미지를 업로드하세요.")

    ref_image = st.file_uploader(
        "레퍼런스 이미지",
        type=["png", "jpg", "jpeg", "webp"],
        help="업로드한 이미지의 스타일을 참조하여 생성합니다.",
        key="thumbnail_ref_image",
        label_visibility="collapsed"
    )

    ref_strength = 0.7  # 기본값

    if ref_image:
        # 레퍼런스 이미지 미리보기
        ref_col1, ref_col2 = st.columns([2, 1])
        with ref_col1:
            st.image(ref_image, caption="레퍼런스 이미지", width=250)
        with ref_col2:
            # 레퍼런스 강도 설정
            ref_strength = st.slider(
                "스타일 강도",
                min_value=0.1,
                max_value=1.0,
                value=0.7,
                step=0.1,
                help="높을수록 레퍼런스 스타일을 더 강하게 반영",
                key="thumbnail_ref_strength"
            )
            st.caption(f"강도: {ref_strength*100:.0f}%")

    st.markdown("---")

    # 6. 생성 버튼
    generate_disabled = not prompt.strip()

    if generate_disabled:
        st.warning("⚠️ 프롬프트를 입력하세요.")

    generate_btn = st.button(
        "🎨 이미지 생성",
        type="primary",
        use_container_width=True,
        disabled=generate_disabled,
        key="thumbnail_generate_btn"
    )


# ── 생성 실행 및 결과 ──
with col_preview:
    st.subheader("🖼️ 생성 결과")

    if generate_btn and prompt.strip():
        with st.spinner("🎨 이미지 생성 중... (약 10-30초 소요)"):
            try:
                # NanoBanana API 초기화
                generator = GeminiImageGenerator()

                # 레퍼런스 이미지 처리
                reference_images = None
                if ref_image:
                    # 파일 포인터 리셋
                    ref_image.seek(0)
                    # PIL Image로 변환
                    ref_pil = Image.open(ref_image)
                    reference_images = [ref_pil]

                # 비율에서 width/height 계산
                ratio_sizes = {
                    "16:9": (1920, 1080),
                    "1:1": (1024, 1024),
                    "9:16": (1080, 1920),
                    "4:3": (1024, 768),
                    "3:4": (768, 1024),
                    "21:9": (2560, 1080)
                }
                width, height = ratio_sizes.get(aspect_ratio, (1920, 1080))

                # 이미지 생성 API 호출
                result: GeminiGenerationResult = generator.generate_image(
                    prompt=prompt,
                    model_key=selected_model,
                    reference_images=reference_images,
                    reference_type="style",
                    reference_strength=ref_strength,
                    width=width,
                    height=height,
                    negative_prompt=negative_prompt if negative_prompt else None,
                    aspect_ratio=aspect_ratio
                )

                if result.success and result.image_data:
                    # 이미지 저장
                    save_dir = get_thumbnail_save_dir()
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"thumbnail_{timestamp}.png"
                    save_path = save_dir / filename

                    # bytes를 파일로 저장
                    with open(save_path, 'wb') as f:
                        f.write(result.image_data)

                    # 세션 상태에 저장
                    st.session_state.last_generated_image = {
                        'path': str(save_path),
                        'prompt': prompt,
                        'model': selected_model,
                        'aspect_ratio': aspect_ratio,
                        'timestamp': timestamp,
                        'elapsed_time': result.elapsed_time
                    }

                    # 히스토리에 추가
                    st.session_state.thumbnail_history.append(
                        st.session_state.last_generated_image
                    )

                    # 결과 이미지 표시
                    st.image(result.image_data, use_container_width=True)

                    # 성공 메시지
                    st.success(f"✅ 생성 완료! ({result.elapsed_time:.1f}초)")

                    # 다운로드 버튼
                    st.download_button(
                        "💾 이미지 다운로드",
                        data=result.image_data,
                        file_name=filename,
                        mime="image/png",
                        use_container_width=True
                    )

                    # 저장 경로 표시
                    st.caption(f"📁 저장: {save_path}")

                else:
                    # 생성 실패
                    error_msg = result.error if result.error else "알 수 없는 오류"
                    st.error(f"❌ 생성 실패: {error_msg}")

                    # 오류 해결 도움말
                    if "SDK" in error_msg or "google" in error_msg.lower():
                        st.info("💡 `pip install google-genai --upgrade` 실행 후 앱을 재시작하세요.")
                    elif "API" in error_msg or "key" in error_msg.lower():
                        st.info("💡 API 관리 페이지에서 Gemini API 키를 확인하세요.")

            except Exception as e:
                st.error(f"❌ 오류: {str(e)}")
                import traceback
                with st.expander("오류 상세"):
                    st.code(traceback.format_exc())

    # 이전 생성 결과 표시 (생성 버튼 클릭하지 않은 경우)
    elif st.session_state.last_generated_image:
        last = st.session_state.last_generated_image
        if os.path.exists(last['path']):
            st.image(last['path'], use_container_width=True)
            st.caption(f"마지막 생성: {last['timestamp']}")

            # 다운로드 버튼
            with open(last['path'], 'rb') as f:
                st.download_button(
                    "💾 이미지 다운로드",
                    data=f.read(),
                    file_name=os.path.basename(last['path']),
                    mime="image/png",
                    use_container_width=True
                )
    else:
        # 생성된 이미지 없음
        st.info("👆 왼쪽에서 프롬프트를 입력하고 '이미지 생성' 버튼을 클릭하세요.")

        # 예시 프롬프트 제공
        with st.expander("💡 프롬프트 예시", expanded=True):
            st.markdown("""
            **유튜브 썸네일:**
            ```
            A professional YouTube thumbnail with bold Korean text "AI 혁명" at the center,
            futuristic technology background with blue and purple gradients,
            glowing circuits and data streams,
            high contrast, eye-catching design, 4K quality
            ```

            **제품 이미지:**
            ```
            A sleek modern smartphone floating in space,
            surrounded by glowing particles,
            soft purple and blue ambient lighting,
            minimalist background, product photography style
            ```

            **캐릭터 일러스트:**
            ```
            A cute anime-style mascot character,
            a small robot with big expressive eyes,
            cheerful expression, pastel colors,
            simple clean background, Pixar-style rendering
            ```
            """)

# ============================================================
# 히스토리 섹션
# ============================================================
if st.session_state.thumbnail_history:
    st.divider()
    st.subheader("📋 생성 히스토리")

    # 최근 5개만 표시
    history = st.session_state.thumbnail_history[-5:]

    cols = st.columns(min(5, len(history)))

    for i, item in enumerate(reversed(history)):
        with cols[i]:
            if os.path.exists(item['path']):
                st.image(item['path'], use_container_width=True)
                st.caption(f"#{len(st.session_state.thumbnail_history)-i}")

                # 프롬프트 일부 표시
                short_prompt = item['prompt'][:30] + "..." if len(item['prompt']) > 30 else item['prompt']
                st.caption(short_prompt)

    # 히스토리 클리어 버튼
    if st.button("🗑️ 히스토리 삭제", key="clear_history"):
        st.session_state.thumbnail_history = []
        st.session_state.last_generated_image = None
        st.rerun()

# ============================================================
# 푸터
# ============================================================
st.divider()
st.caption("💡 **팁**: 영어 프롬프트가 더 정확한 결과를 제공합니다. 한글 텍스트가 필요한 경우 프롬프트에 명시하세요.")
