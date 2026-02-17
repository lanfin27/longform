# -*- coding: utf-8 -*-
"""
14_🧹_배경_제거.py
배경 제거 독립 도구

어떤 이미지든 업로드하여 배경을 깔끔하게 제거합니다.
AI가 생성한 가짜 투명(체커보드) 배경도 실제 투명으로 변환합니다.

의존성: pip install rembg
GPU 가속: pip install rembg[gpu]
"""
import streamlit as st
import io
from PIL import Image
from pathlib import Path

# ════════════════════════════════════════════════════════════════════════════
# 페이지 설정
# ════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="배경 제거",
    page_icon="🧹",
    layout="wide"
)

st.title("🧹 배경 제거")
st.caption("이미지를 업로드하면 AI가 피사체만 분리하여 투명 PNG를 생성합니다.")

# ════════════════════════════════════════════════════════════════════════════
# rembg 세션 캐싱 (모델 로드 1회만)
# ════════════════════════════════════════════════════════════════════════════
@st.cache_resource
def get_rembg_session(model_name: str):
    """rembg 세션을 캐싱하여 모델을 매번 로드하지 않음"""
    try:
        from rembg import new_session
        return new_session(model_name)
    except Exception as e:
        st.error(f"모델 로드 실패: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════
# 메인 레이아웃
# ════════════════════════════════════════════════════════════════════════════
col_upload, col_settings = st.columns([2, 1])

# ── 설정 패널 ──
with col_settings:
    st.subheader("⚙️ 설정")

    bg_model = st.selectbox(
        "모델 선택",
        options=["u2net", "u2netp", "u2net_human_seg", "isnet-general-use"],
        index=0,
        help="""
        - **u2net**: 범용 (정확도 높음, 속도 보통)
        - **u2netp**: 경량 (빠름, 정확도 약간 낮음)
        - **u2net_human_seg**: 인물 특화
        - **isnet-general-use**: 최신 범용 모델
        """
    )

    st.markdown("---")

    alpha_matting = st.checkbox(
        "알파 매팅 (부드러운 가장자리)",
        value=True,
        help="가장자리를 부드럽게 처리합니다. 머리카락 등 섬세한 디테일에 효과적입니다."
    )

    if alpha_matting:
        with st.expander("알파 매팅 세부 설정", expanded=False):
            fg_threshold = st.slider(
                "전경 임계값",
                min_value=200,
                max_value=270,
                value=240,
                help="높을수록 전경으로 판단하는 기준이 엄격해집니다."
            )
            bg_threshold = st.slider(
                "배경 임계값",
                min_value=5,
                max_value=40,
                value=10,
                help="낮을수록 배경으로 판단하는 기준이 엄격해집니다."
            )
            erode_size = st.slider(
                "침식 크기",
                min_value=1,
                max_value=20,
                value=10,
                help="가장자리 침식 정도입니다."
            )
    else:
        fg_threshold = 240
        bg_threshold = 10
        erode_size = 10

    st.markdown("---")

    # 첫 실행 안내
    with st.expander("ℹ️ 사용 안내", expanded=False):
        st.markdown("""
        **첫 실행 시 모델 다운로드**
        - u2net: ~170MB
        - 다운로드는 한 번만 진행됩니다.

        **지원 형식**
        - 입력: PNG, JPG, JPEG, WebP
        - 출력: 투명 PNG

        **팁**
        - 체커보드 패턴 배경도 자동 제거됩니다.
        - 인물 사진은 `u2net_human_seg` 모델 추천
        """)


# ── 업로드 패널 ──
with col_upload:
    st.subheader("📎 이미지 업로드")

    # 다중 파일 업로드 지원
    uploaded_files = st.file_uploader(
        "배경을 제거할 이미지를 업로드하세요 (여러 장 가능)",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="bg_remove_files"
    )

    if uploaded_files:
        st.info(f"📁 {len(uploaded_files)}개 파일 선택됨")

        # 미리보기 (최대 4개)
        preview_count = min(len(uploaded_files), 4)
        preview_cols = st.columns(preview_count)
        for i, uploaded in enumerate(uploaded_files[:preview_count]):
            with preview_cols[i]:
                img = Image.open(uploaded)
                st.image(img, caption=uploaded.name[:20], use_container_width=True)

        if len(uploaded_files) > 4:
            st.caption(f"... 외 {len(uploaded_files) - 4}개 파일")


# ════════════════════════════════════════════════════════════════════════════
# 배경 제거 실행
# ════════════════════════════════════════════════════════════════════════════
st.markdown("---")

if uploaded_files:
    if st.button("🧹 배경 제거 실행", type="primary", use_container_width=True):
        try:
            # rembg 임포트 확인
            try:
                from rembg import remove
            except ImportError:
                st.error("""
                ❌ **rembg가 설치되지 않았습니다.**

                터미널에서 다음 명령어를 실행하세요:
                ```bash
                pip install rembg
                ```

                GPU 가속이 필요한 경우:
                ```bash
                pip install rembg[gpu]
                ```
                """)
                st.stop()

            # 세션 로드
            with st.spinner(f"🔄 모델 로딩 중... ({bg_model})"):
                session = get_rembg_session(bg_model)

            if session is None:
                st.error("모델 세션을 로드할 수 없습니다.")
                st.stop()

            # 진행률 표시
            progress = st.progress(0, text="배경 제거 준비 중...")
            results = []

            for i, uploaded in enumerate(uploaded_files):
                progress.progress(
                    (i + 1) / len(uploaded_files),
                    text=f"🔄 {i+1}/{len(uploaded_files)} 처리 중... ({uploaded.name})"
                )

                # 이미지 로드
                input_img = Image.open(uploaded).convert("RGBA")

                # rembg 옵션 구성
                kwargs = {"session": session}
                if alpha_matting:
                    kwargs.update({
                        "alpha_matting": True,
                        "alpha_matting_foreground_threshold": fg_threshold,
                        "alpha_matting_background_threshold": bg_threshold,
                        "alpha_matting_erode_size": erode_size
                    })

                # 배경 제거 실행
                output_img = remove(input_img, **kwargs)
                results.append((uploaded.name, input_img, output_img))

            progress.empty()
            st.success(f"✅ {len(results)}개 이미지 배경 제거 완료!")

            # ════════════════════════════════════════════════════════════════
            # 결과 표시
            # ════════════════════════════════════════════════════════════════
            st.markdown("---")
            st.subheader("📤 결과")

            for idx, (name, original, result) in enumerate(results):
                st.markdown(f"### 📄 {name}")

                col_before, col_after = st.columns(2)

                with col_before:
                    st.markdown("**원본**")
                    st.image(original, use_container_width=True)

                with col_after:
                    st.markdown("**배경 제거됨**")
                    # 투명 배경 위에 체커보드 패턴 표시 (시각적 확인용)
                    st.image(result, use_container_width=True)

                # 다운로드 버튼
                buf = io.BytesIO()
                result.save(buf, format="PNG")
                buf.seek(0)

                # 파일명에서 확장자 제거 후 _transparent.png 추가
                base_name = Path(name).stem
                output_name = f"{base_name}_transparent.png"

                st.download_button(
                    label=f"💾 {output_name} 다운로드",
                    data=buf.getvalue(),
                    file_name=output_name,
                    mime="image/png",
                    key=f"download_{idx}_{name}"
                )

                if idx < len(results) - 1:
                    st.markdown("---")

            # 전체 다운로드 (ZIP) - 여러 장일 경우
            if len(results) > 1:
                st.markdown("---")
                st.subheader("📦 전체 다운로드")

                import zipfile

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for name, _, result in results:
                        base_name = Path(name).stem
                        output_name = f"{base_name}_transparent.png"

                        img_buf = io.BytesIO()
                        result.save(img_buf, format="PNG")
                        zf.writestr(output_name, img_buf.getvalue())

                zip_buffer.seek(0)

                st.download_button(
                    label=f"📦 전체 다운로드 (ZIP, {len(results)}개)",
                    data=zip_buffer.getvalue(),
                    file_name="transparent_images.zip",
                    mime="application/zip",
                    key="download_all_zip"
                )

        except Exception as e:
            st.error(f"❌ 오류 발생: {str(e)}")
            import traceback
            with st.expander("상세 오류"):
                st.code(traceback.format_exc())

else:
    st.info("👆 위에서 이미지를 업로드하세요.")


# ════════════════════════════════════════════════════════════════════════════
# 푸터
# ════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.caption("Powered by [rembg](https://github.com/danielgatis/rembg) | U²-Net 기반 배경 제거")
