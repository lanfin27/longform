# -*- coding: utf-8 -*-
"""
이미지 뷰어 컴포넌트

기능:
- 이미지 클릭 시 확대 팝업 (Lightbox)
- 그리드 형태의 이미지 갤러리
- 이미지 메타데이터 표시
"""

import streamlit as st
import base64
import os
from pathlib import Path
from typing import Optional, List, Dict, Union, Tuple
from PIL import Image
import io


@st.cache_data(ttl=300, show_spinner=False, max_entries=100)
def _get_image_info_cached(image_path: str, _mtime: float) -> Dict:
    """
    이미지 파일의 메타데이터 추출 (캐싱됨)

    Args:
        image_path: 이미지 파일 경로
        _mtime: 파일 수정 시간 (캐시 무효화 키)
    """
    info = {
        "filename": os.path.basename(image_path) if image_path else "",
        "size_kb": 0,
        "width": 0,
        "height": 0,
        "format": "",
        "exists": True
    }

    try:
        info["size_kb"] = round(os.path.getsize(image_path) / 1024, 1)

        with Image.open(image_path) as img:
            info["width"] = img.width
            info["height"] = img.height
            info["format"] = img.format or "Unknown"

    except Exception:
        # 성능 최적화: 에러 로그 제거
        pass

    return info


def get_image_info(image_path: str) -> Dict:
    """
    이미지 파일의 메타데이터 추출

    Args:
        image_path: 이미지 파일 경로

    Returns:
        {
            "filename": "image.png",
            "size_kb": 256.5,
            "width": 1024,
            "height": 768,
            "format": "PNG",
            "exists": True
        }
    """
    if not image_path or not os.path.exists(image_path):
        return {
            "filename": os.path.basename(image_path) if image_path else "",
            "size_kb": 0,
            "width": 0,
            "height": 0,
            "format": "",
            "exists": False
        }

    try:
        mtime = os.path.getmtime(image_path)
        return _get_image_info_cached(image_path, mtime)
    except (OSError, IOError):
        return {
            "filename": os.path.basename(image_path) if image_path else "",
            "size_kb": 0,
            "width": 0,
            "height": 0,
            "format": "",
            "exists": False
        }


@st.cache_data(ttl=300, show_spinner=False, max_entries=100)
def _encode_image_base64_cached(image_path: str, _mtime: float) -> Optional[str]:
    """
    이미지를 Base64로 인코딩 (캐싱됨)

    Args:
        image_path: 이미지 경로
        _mtime: 파일 수정 시간 (캐시 무효화 키)
    """
    try:
        with open(image_path, "rb") as f:
            data = f.read()

        # MIME 타입 결정
        ext = Path(image_path).suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp"
        }
        mime = mime_types.get(ext, "image/png")

        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{encoded}"

    except Exception as e:
        # 성능 최적화: 에러 로그 제거
        return None


def _encode_image_base64(image_path: str) -> Optional[str]:
    """이미지를 Base64로 인코딩 (캐싱 래퍼)"""
    if not image_path or not os.path.exists(image_path):
        return None

    try:
        mtime = os.path.getmtime(image_path)
        return _encode_image_base64_cached(image_path, mtime)
    except (OSError, IOError):
        return None


def _get_lightbox_css() -> str:
    """Lightbox용 CSS 스타일"""
    return """
    <style>
    /* Lightbox 오버레이 */
    .lightbox-overlay {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0, 0, 0, 0.9);
        z-index: 9999;
        justify-content: center;
        align-items: center;
        cursor: pointer;
    }

    .lightbox-overlay.active {
        display: flex;
    }

    /* Lightbox 이미지 */
    .lightbox-image {
        max-width: 90%;
        max-height: 90%;
        object-fit: contain;
        border-radius: 8px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    }

    /* 닫기 버튼 */
    .lightbox-close {
        position: absolute;
        top: 20px;
        right: 30px;
        color: white;
        font-size: 40px;
        font-weight: bold;
        cursor: pointer;
        z-index: 10000;
        transition: color 0.2s;
    }

    .lightbox-close:hover {
        color: #ff6b6b;
    }

    /* 이미지 정보 */
    .lightbox-info {
        position: absolute;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        color: white;
        background: rgba(0, 0, 0, 0.7);
        padding: 10px 20px;
        border-radius: 8px;
        font-size: 14px;
        text-align: center;
    }

    /* 썸네일 컨테이너 */
    .thumbnail-container {
        position: relative;
        cursor: pointer;
        overflow: hidden;
        border-radius: 8px;
        transition: transform 0.2s, box-shadow 0.2s;
    }

    .thumbnail-container:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }

    .thumbnail-container img {
        width: 100%;
        height: auto;
        display: block;
    }

    /* 확대 아이콘 오버레이 */
    .zoom-icon {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: rgba(0, 0, 0, 0.6);
        color: white;
        width: 50px;
        height: 50px;
        border-radius: 50%;
        display: flex;
        justify-content: center;
        align-items: center;
        font-size: 24px;
        opacity: 0;
        transition: opacity 0.2s;
    }

    .thumbnail-container:hover .zoom-icon {
        opacity: 1;
    }

    /* 갤러리 그리드 */
    .image-gallery {
        display: grid;
        gap: 16px;
    }

    .gallery-cols-2 { grid-template-columns: repeat(2, 1fr); }
    .gallery-cols-3 { grid-template-columns: repeat(3, 1fr); }
    .gallery-cols-4 { grid-template-columns: repeat(4, 1fr); }
    .gallery-cols-5 { grid-template-columns: repeat(5, 1fr); }
    </style>
    """


def _get_lightbox_js() -> str:
    """Lightbox용 JavaScript (v3.28: 이벤트 위임 방식으로 개선)"""
    return """
    <script>
    // v3.28: 기존 함수 유지 (하위 호환성)
    function openLightbox(imgSrc, info) {
        const overlay = document.getElementById('lightbox-overlay');
        const lightboxImg = document.getElementById('lightbox-img');
        const lightboxInfo = document.getElementById('lightbox-info');

        if (overlay && lightboxImg) {
            lightboxImg.src = imgSrc;
            if (lightboxInfo) {
                lightboxInfo.textContent = info || '';
            }
            overlay.classList.add('active');
            document.body.style.overflow = 'hidden';
        }
    }

    function closeLightbox() {
        const overlay = document.getElementById('lightbox-overlay');
        if (overlay) {
            overlay.classList.remove('active');
            document.body.style.overflow = 'auto';
        }
    }

    // ESC 키로 닫기
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeLightbox();
        }
    });

    // v3.28: 이벤트 위임으로 썸네일 클릭 처리 (대용량 이미지 지원)
    document.addEventListener('click', function(e) {
        // 썸네일 컨테이너 또는 그 자식 요소 클릭 시
        const container = e.target.closest('.thumbnail-container');
        if (container) {
            // 컨테이너 내의 이미지 찾기
            const img = container.querySelector('img');
            if (img && img.src) {
                // 이미지 정보 가져오기 (data 속성에서)
                const info = container.dataset.info || '';
                openLightbox(img.src, info);
            }
        }
    });
    </script>
    """


def render_lightbox_container():
    """
    Lightbox 컨테이너 렌더링 (페이지당 한 번만 호출)

    반드시 이미지 렌더링 전에 호출해야 함
    """
    html = f"""
    {_get_lightbox_css()}

    <!-- Lightbox 오버레이 -->
    <div id="lightbox-overlay" class="lightbox-overlay" onclick="closeLightbox()">
        <span class="lightbox-close">&times;</span>
        <img id="lightbox-img" class="lightbox-image" src="" alt="확대 이미지">
        <div id="lightbox-info" class="lightbox-info"></div>
    </div>

    {_get_lightbox_js()}
    """

    st.markdown(html, unsafe_allow_html=True)


def render_lightbox_image(
    image_path: str,
    caption: str = "",
    width: Optional[int] = None,
    show_info: bool = True,
    key: str = ""
) -> bool:
    """
    클릭 시 확대되는 이미지 렌더링 (v3.28: 이벤트 위임 방식으로 개선)

    Args:
        image_path: 이미지 파일 경로
        caption: 이미지 캡션
        width: 썸네일 너비 (픽셀)
        show_info: Lightbox에서 이미지 정보 표시 여부
        key: 고유 키 (같은 페이지에 여러 이미지 있을 때)

    Returns:
        이미지 렌더링 성공 여부
    """
    if not image_path or not os.path.exists(image_path):
        st.warning(f"이미지를 찾을 수 없습니다: {image_path}")
        return False

    base64_img = _encode_image_base64(image_path)
    if not base64_img:
        st.error("이미지 인코딩 실패")
        return False

    # 이미지 정보
    info = get_image_info(image_path)
    info_text = f"{info['filename']} | {info['width']}x{info['height']} | {info['size_kb']}KB"

    # 스타일
    width_style = f"width: {width}px;" if width else "width: 100%;"

    # HTML 생성 (v3.28: onclick 제거, data 속성 사용)
    # 이벤트 위임 방식으로 클릭 처리 - JavaScript에서 .thumbnail-container 클릭 감지
    unique_id = f"thumb_{key}_{hash(image_path) % 10000}"

    # info_text에서 따옴표 이스케이프 처리
    safe_info_text = info_text.replace('"', '&quot;').replace("'", "&#39;") if show_info else ""

    html = f"""
    <div class="thumbnail-container"
         data-info="{safe_info_text}"
         style="{width_style} cursor: pointer;">
        <img src="{base64_img}" alt="{caption}" style="width: 100%; height: auto;">
        <div class="zoom-icon">🔍</div>
    </div>
    """

    if caption:
        html += f'<p style="text-align: center; margin-top: 8px; color: #666; font-size: 14px;">{caption}</p>'

    st.markdown(html, unsafe_allow_html=True)
    return True


def render_lightbox_grid(
    images: List[Union[str, Dict]],
    columns: int = 3,
    show_captions: bool = True,
    show_info: bool = True,
    key_prefix: str = "gallery"
):
    """
    그리드 형태의 이미지 갤러리 렌더링

    Args:
        images: 이미지 경로 리스트 또는 {"path": "...", "caption": "..."} 딕셔너리 리스트
        columns: 열 개수 (2-5)
        show_captions: 캡션 표시 여부
        show_info: Lightbox에서 이미지 정보 표시 여부
        key_prefix: 고유 키 접두사
    """
    if not images:
        st.info("표시할 이미지가 없습니다.")
        return

    # 열 개수 제한
    columns = max(2, min(5, columns))

    # 이미지 데이터 정규화
    normalized_images = []
    for i, img in enumerate(images):
        if isinstance(img, str):
            normalized_images.append({"path": img, "caption": ""})
        elif isinstance(img, dict):
            normalized_images.append({
                "path": img.get("path", ""),
                "caption": img.get("caption", "")
            })

    # 유효한 이미지만 필터링
    valid_images = [
        img for img in normalized_images
        if img["path"] and os.path.exists(img["path"])
    ]

    if not valid_images:
        st.warning("표시할 유효한 이미지가 없습니다.")
        return

    # 그리드 HTML 생성
    grid_items = []
    for i, img in enumerate(valid_images):
        base64_img = _encode_image_base64(img["path"])
        if not base64_img:
            continue

        info = get_image_info(img["path"])
        info_text = f"{info['filename']} | {info['width']}x{info['height']} | {info['size_kb']}KB"
        caption = img["caption"] if show_captions else ""

        # v3.28: 이벤트 위임 방식 적용 (onclick 제거)
        safe_info_text = info_text.replace('"', '&quot;').replace("'", "&#39;") if show_info else ""
        item_html = f"""
        <div class="thumbnail-container"
             data-info="{safe_info_text}">
            <img src="{base64_img}" alt="{caption}" style="width: 100%; height: auto;">
            <div class="zoom-icon">🔍</div>
        </div>
        """

        if caption:
            item_html += f'<p style="text-align: center; margin-top: 4px; color: #666; font-size: 12px;">{caption}</p>'

        grid_items.append(f'<div>{item_html}</div>')

    # 그리드 렌더링
    grid_html = f"""
    <div class="image-gallery gallery-cols-{columns}">
        {''.join(grid_items)}
    </div>
    """

    st.markdown(grid_html, unsafe_allow_html=True)


def clickable_image(
    image_path: str,
    caption: str = "",
    width: Optional[int] = None,
    use_column_width: bool = False,
    key: str = ""
) -> bool:
    """
    st.image() 대체 함수 - 클릭 시 확대 기능

    사용법:
        # 기존: st.image("image.png", caption="My Image")
        # 변경: clickable_image("image.png", caption="My Image")

    Args:
        image_path: 이미지 파일 경로
        caption: 이미지 캡션
        width: 이미지 너비 (픽셀)
        use_column_width: True면 컬럼 너비에 맞춤 (width 무시)
        key: 고유 키

    Returns:
        성공 여부
    """
    if not image_path or not os.path.exists(image_path):
        st.warning(f"이미지를 찾을 수 없습니다.")
        return False

    # use_column_width 처리
    actual_width = None if use_column_width else width

    return render_lightbox_image(
        image_path=image_path,
        caption=caption,
        width=actual_width,
        show_info=True,
        key=key
    )


def render_image_with_actions(
    image_path: str,
    caption: str = "",
    width: Optional[int] = None,
    actions: List[Dict] = None,
    key_prefix: str = ""
) -> Optional[str]:
    """
    이미지와 액션 버튼들을 함께 렌더링

    Args:
        image_path: 이미지 경로
        caption: 캡션
        width: 이미지 너비
        actions: [{"label": "버튼 텍스트", "key": "action_key", "type": "primary/secondary"}]
        key_prefix: 키 접두사

    Returns:
        클릭된 액션의 key 또는 None
    """
    # 이미지 렌더링
    render_lightbox_image(image_path, caption, width, key=key_prefix)

    if not actions:
        return None

    # 버튼 렌더링
    clicked_action = None
    cols = st.columns(len(actions))

    for i, action in enumerate(actions):
        with cols[i]:
            btn_type = "primary" if action.get("type") == "primary" else "secondary"
            if st.button(
                action["label"],
                key=f"{key_prefix}_{action['key']}",
                type=btn_type,
                use_container_width=True
            ):
                clicked_action = action["key"]

    return clicked_action


# ============================================================
# PIL Image 지원
# ============================================================

def render_pil_image(
    image: Image.Image,
    caption: str = "",
    width: Optional[int] = None,
    key: str = ""
) -> bool:
    """
    PIL Image 객체를 Lightbox로 렌더링

    Args:
        image: PIL Image 객체
        caption: 캡션
        width: 너비
        key: 고유 키

    Returns:
        성공 여부
    """
    if image is None:
        st.warning("이미지 객체가 없습니다.")
        return False

    try:
        # PIL Image를 Base64로 변환
        buffer = io.BytesIO()
        img_format = image.format or "PNG"
        image.save(buffer, format=img_format)
        buffer.seek(0)

        encoded = base64.b64encode(buffer.read()).decode("utf-8")
        mime = f"image/{img_format.lower()}"
        base64_img = f"data:{mime};base64,{encoded}"

        # 정보
        info_text = f"{image.width}x{image.height} | {img_format}"

        # 스타일
        width_style = f"width: {width}px;" if width else "width: 100%;"

        # v3.28: 이벤트 위임 방식 적용 (onclick 제거)
        safe_info_text = info_text.replace('"', '&quot;').replace("'", "&#39;")
        html = f"""
        <div class="thumbnail-container"
             data-info="{safe_info_text}"
             style="{width_style}">
            <img src="{base64_img}" alt="{caption}" style="width: 100%; height: auto;">
            <div class="zoom-icon">🔍</div>
        </div>
        """

        if caption:
            html += f'<p style="text-align: center; margin-top: 8px; color: #666; font-size: 14px;">{caption}</p>'

        st.markdown(html, unsafe_allow_html=True)
        return True

    except Exception as e:
        st.error(f"PIL 이미지 렌더링 실패: {e}")
        return False


# ============================================================
# Streamlit 네이티브 이미지 확대 (v2.0)
# ============================================================

def render_image_with_zoom_button(
    image_path: str,
    caption: str = "",
    width: int = None,
    key: str = "",
    show_prompt_button: bool = True
) -> None:
    """
    이미지 + 확대/프롬프트 버튼 렌더링 (Streamlit 네이티브)

    JavaScript가 동작하지 않을 때를 위한 대안

    Args:
        image_path: 이미지 파일 경로
        caption: 캡션
        width: 이미지 너비
        key: 고유 키
        show_prompt_button: 프롬프트 버튼 표시 여부
    """
    if not image_path or not os.path.exists(image_path):
        st.info("🖼️ 이미지 없음")
        return

    # 이미지 표시
    st.image(image_path, width=width, use_container_width=(width is None))

    # 버튼 행
    btn_cols = st.columns(3 if show_prompt_button else 2)

    with btn_cols[0]:
        if st.button("🔍 확대", key=f"zoom_btn_{key}", use_container_width=True):
            st.session_state[f"show_zoom_{key}"] = True

    if show_prompt_button:
        with btn_cols[1]:
            if st.button("📝 프롬프트", key=f"prompt_btn_{key}", use_container_width=True):
                st.session_state[f"show_prompt_{key}"] = True

    with btn_cols[-1]:
        if st.button("📋 경로 복사", key=f"copy_btn_{key}", use_container_width=True):
            st.code(str(Path(image_path).resolve()), language=None)

    # 확대 다이얼로그
    if st.session_state.get(f"show_zoom_{key}", False):
        _show_zoom_dialog(image_path, caption, key)

    # 프롬프트 다이얼로그
    if show_prompt_button and st.session_state.get(f"show_prompt_{key}", False):
        _show_prompt_dialog(image_path, key)


def _show_zoom_dialog(image_path: str, caption: str, key: str):
    """이미지 확대 다이얼로그 (expander 사용)"""
    with st.expander(f"🔍 이미지 확대 보기 - {caption or Path(image_path).name}", expanded=True):
        # 큰 이미지
        st.image(image_path, use_container_width=True)

        # 이미지 정보
        info = get_image_info(image_path)
        st.caption(f"📏 {info['width']}x{info['height']} | {info['size_kb']}KB | {info['format']}")

        # 프롬프트 정보 (있으면)
        try:
            from utils.image_prompt_metadata import get_image_prompt_info
            prompt_info = get_image_prompt_info(image_path)
            if prompt_info:
                prompts = prompt_info.get('prompts', {})
                final_prompt = prompts.get('final', '')
                if final_prompt:
                    st.markdown("**📝 이미지 프롬프트:**")
                    st.code(final_prompt[:500] + "..." if len(final_prompt) > 500 else final_prompt, language=None)
        except:
            pass

        if st.button("✖️ 닫기", key=f"close_zoom_{key}"):
            st.session_state[f"show_zoom_{key}"] = False
            st.rerun()


def _show_prompt_dialog(image_path: str, key: str):
    """프롬프트 상세 다이얼로그"""
    with st.expander("📝 프롬프트 상세 정보", expanded=True):
        try:
            from utils.image_prompt_metadata import get_image_prompt_info
            prompt_info = get_image_prompt_info(image_path)

            if not prompt_info:
                st.info("프롬프트 메타데이터가 없습니다.")
            else:
                prompts = prompt_info.get('prompts', {})
                gen = prompt_info.get('generation', {})
                style = prompt_info.get('style', {})

                # 생성 정보
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**API:** {gen.get('api_provider', 'N/A')}")
                with col2:
                    st.markdown(f"**Model:** {gen.get('model_name', gen.get('model', 'N/A'))}")
                with col3:
                    st.markdown(f"**Size:** {gen.get('width', 0)}x{gen.get('height', 0)}")

                st.markdown("---")

                # 원본 프롬프트
                original = prompts.get('original', '')
                if original:
                    st.markdown("**🇰🇷 원본 프롬프트 (씬 분석):**")
                    st.text_area("원본", original, height=80, disabled=True, label_visibility="collapsed", key=f"orig_{key}")

                # 스타일 정보
                if style.get('name'):
                    st.markdown(f"**🎨 스타일:** {style.get('name')}")

                # 최종 프롬프트
                final = prompts.get('final', '')
                if final:
                    st.markdown("**🌐 최종 프롬프트 (API 전송):**")
                    st.text_area("최종", final, height=120, disabled=True, label_visibility="collapsed", key=f"final_{key}")

                # 네거티브
                negative = prompts.get('negative', '')
                if negative:
                    st.markdown("**❌ 네거티브 프롬프트:**")
                    st.text_area("네거티브", negative, height=60, disabled=True, label_visibility="collapsed", key=f"neg_{key}")

        except ImportError:
            st.warning("프롬프트 메타데이터 모듈을 불러올 수 없습니다.")
        except Exception as e:
            st.error(f"프롬프트 로드 오류: {e}")

        if st.button("✖️ 닫기", key=f"close_prompt_{key}"):
            st.session_state[f"show_prompt_{key}"] = False
            st.rerun()


def render_image_card_with_prompt(
    image_path: str,
    scene_id: int,
    scene_data: Dict = None,
    key_prefix: str = "card"
) -> Optional[str]:
    """
    이미지 카드 (확대 + 프롬프트 뷰) 렌더링

    스토리보드 및 이미지 생성 탭에서 사용

    Args:
        image_path: 이미지 파일 경로
        scene_id: 씬 ID
        scene_data: 씬 데이터 (프롬프트 정보 포함 가능)
        key_prefix: 고유 키 접두사

    Returns:
        클릭된 액션 또는 None
    """
    unique_key = f"{key_prefix}_{scene_id}"

    if not image_path or not os.path.exists(image_path):
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 8px;
            padding: 40px 20px;
            text-align: center;
            color: #666;
        ">
            🖼️ 이미지 없음<br>
            <small>씬 {scene_id}</small>
        </div>
        """, unsafe_allow_html=True)
        return None

    # 썸네일 (라이트박스 사용 시도)
    render_lightbox_image(image_path, caption=f"씬 {scene_id}", key=unique_key)

    # 액션 버튼
    col1, col2, col3 = st.columns(3)

    clicked_action = None

    with col1:
        if st.button("🔍", key=f"zoom_{unique_key}", help="확대 보기"):
            st.session_state[f"show_zoom_{unique_key}"] = True

    with col2:
        if st.button("📝", key=f"prompt_{unique_key}", help="프롬프트 보기"):
            st.session_state[f"show_prompt_{unique_key}"] = True

    with col3:
        if st.button("📋", key=f"copy_{unique_key}", help="경로 복사"):
            clicked_action = "copy"
            st.toast(f"경로: {image_path}")

    # 확대 모달
    if st.session_state.get(f"show_zoom_{unique_key}", False):
        with st.container(border=True):
            st.markdown(f"#### 🔍 씬 {scene_id} 확대 보기")
            st.image(image_path, use_container_width=True)

            # 프롬프트도 함께 표시
            prompt_text = _get_prompt_text(image_path, scene_data)
            if prompt_text:
                st.markdown("**📝 프롬프트:**")
                st.code(prompt_text[:300] + "..." if len(prompt_text) > 300 else prompt_text, language=None)

            if st.button("닫기", key=f"close_zoom_{unique_key}"):
                st.session_state[f"show_zoom_{unique_key}"] = False
                st.rerun()

    # 프롬프트 모달
    if st.session_state.get(f"show_prompt_{unique_key}", False):
        with st.container(border=True):
            st.markdown(f"#### 📝 씬 {scene_id} 프롬프트")
            _render_prompt_details(image_path, scene_data, unique_key)

            if st.button("닫기", key=f"close_prompt_{unique_key}"):
                st.session_state[f"show_prompt_{unique_key}"] = False
                st.rerun()

    return clicked_action


def _get_prompt_text(image_path: str, scene_data: Dict = None) -> str:
    """이미지 또는 씬 데이터에서 프롬프트 텍스트 추출"""
    # 메타데이터에서 먼저 시도
    try:
        from utils.image_prompt_metadata import get_image_prompt_info
        prompt_info = get_image_prompt_info(image_path)
        if prompt_info:
            prompts = prompt_info.get('prompts', {})
            return prompts.get('final', '') or prompts.get('original', '')
    except:
        pass

    # 씬 데이터에서 시도
    if scene_data:
        return (
            scene_data.get('image_prompt_en', '') or
            scene_data.get('image_prompt', '') or
            scene_data.get('prompt', '')
        )

    return ""


def _render_prompt_details(image_path: str, scene_data: Dict, key: str):
    """프롬프트 상세 정보 렌더링"""
    # 메타데이터에서 로드
    try:
        from utils.image_prompt_metadata import get_image_prompt_info
        prompt_info = get_image_prompt_info(image_path)
    except:
        prompt_info = None

    has_metadata = prompt_info is not None

    # 원본 프롬프트
    original = ""
    final = ""
    negative = ""

    if has_metadata:
        prompts = prompt_info.get('prompts', {})
        original = prompts.get('original', '')
        final = prompts.get('final', '')
        negative = prompts.get('negative', '')

    # 씬 데이터에서 보완
    if scene_data:
        if not original:
            original = scene_data.get('image_prompt', '') or scene_data.get('prompt', '')
        if not final:
            final = scene_data.get('image_prompt_en', '')

    # 표시
    if original:
        st.markdown("**🇰🇷 원본 프롬프트:**")
        st.text_area("원본", original, height=80, disabled=True, label_visibility="collapsed", key=f"orig_d_{key}")

    if final and final != original:
        st.markdown("**🌐 최종 프롬프트 (API):**")
        st.text_area("최종", final, height=100, disabled=True, label_visibility="collapsed", key=f"final_d_{key}")

    if negative:
        st.markdown("**❌ 네거티브:**")
        st.text_area("네거티브", negative, height=50, disabled=True, label_visibility="collapsed", key=f"neg_d_{key}")

    # 생성 정보
    if has_metadata:
        gen = prompt_info.get('generation', {})
        style = prompt_info.get('style', {})

        info_parts = []
        if gen.get('api_provider'):
            info_parts.append(f"API: {gen.get('api_provider')}")
        if gen.get('model_name') or gen.get('model'):
            info_parts.append(f"Model: {gen.get('model_name', gen.get('model'))}")
        if style.get('name'):
            info_parts.append(f"Style: {style.get('name')}")
        if gen.get('width') and gen.get('height'):
            info_parts.append(f"Size: {gen.get('width')}x{gen.get('height')}")

        if info_parts:
            st.caption(" | ".join(info_parts))

    if not original and not final:
        st.info("프롬프트 정보가 없습니다. 이미지 재생성 시 저장됩니다.")


# ============================================================
# Streamlit @st.dialog 기반 이미지 확대 뷰어 (v3.0)
# ============================================================

def _init_image_zoom_state():
    """이미지 확대 상태 초기화"""
    if 'image_zoom_path' not in st.session_state:
        st.session_state.image_zoom_path = None
    if 'image_zoom_caption' not in st.session_state:
        st.session_state.image_zoom_caption = ""


def open_image_zoom(image_path: str, caption: str = ""):
    """이미지 확대 모달 열기"""
    st.session_state.image_zoom_path = image_path
    st.session_state.image_zoom_caption = caption


def close_image_zoom():
    """이미지 확대 모달 닫기"""
    st.session_state.image_zoom_path = None
    st.session_state.image_zoom_caption = ""


def render_zoomable_image(
    image_path: str,
    caption: str = "",
    width: Optional[int] = None,
    key: str = "",
    show_zoom_button: bool = True,
    use_container_width: bool = False
) -> bool:
    """
    확대 가능한 이미지 렌더링 (Streamlit 네이티브 - 버튼 클릭 방식)

    JavaScript 의존성 없이 100% Streamlit 기능으로 동작

    Args:
        image_path: 이미지 파일 경로
        caption: 이미지 캡션
        width: 이미지 너비 (픽셀)
        key: 고유 키
        show_zoom_button: 확대 버튼 표시 여부
        use_container_width: 컨테이너 너비에 맞춤

    Returns:
        이미지 표시 성공 여부
    """
    _init_image_zoom_state()

    if not image_path or not os.path.exists(image_path):
        st.info("🖼️ 이미지 없음")
        return False

    # 고유 키 생성
    unique_key = key or f"img_{hash(image_path) % 100000}"

    # 이미지 컨테이너
    img_container = st.container()

    with img_container:
        # 썸네일 이미지 표시
        if width and not use_container_width:
            st.image(image_path, width=width)
        else:
            st.image(image_path, use_container_width=True)

        # 확대 버튼 (이미지 아래에 작은 버튼)
        if show_zoom_button:
            if st.button("🔍 확대", key=f"zoom_btn_{unique_key}", use_container_width=True):
                open_image_zoom(image_path, caption or Path(image_path).name)
                st.rerun()

        # 캡션 표시
        if caption:
            st.caption(caption)

    return True


def render_image_zoom_modal():
    """
    이미지 확대 모달 렌더링 (페이지 최상단에서 호출)

    Usage:
        # 페이지 최상단에서 한 번만 호출
        render_image_zoom_modal()

        # 이후 render_zoomable_image() 사용
        render_zoomable_image("path/to/image.png", caption="My Image")
    """
    _init_image_zoom_state()

    if st.session_state.image_zoom_path and os.path.exists(st.session_state.image_zoom_path):
        image_path = st.session_state.image_zoom_path
        caption = st.session_state.image_zoom_caption

        # 모달 대신 expander 또는 컨테이너 사용
        st.markdown("---")
        with st.container(border=True):
            # 헤더
            header_col1, header_col2 = st.columns([6, 1])
            with header_col1:
                st.markdown(f"### 🔍 이미지 확대 보기")
                if caption:
                    st.caption(caption)
            with header_col2:
                if st.button("✖️ 닫기", key="close_zoom_modal", type="primary"):
                    close_image_zoom()
                    st.rerun()

            # 확대된 이미지
            st.image(image_path, use_container_width=True)

            # 이미지 정보
            info = get_image_info(image_path)
            info_col1, info_col2, info_col3 = st.columns(3)
            with info_col1:
                st.metric("해상도", f"{info['width']}x{info['height']}")
            with info_col2:
                st.metric("파일 크기", f"{info['size_kb']} KB")
            with info_col3:
                st.metric("형식", info['format'])

            # 파일 경로
            st.code(str(Path(image_path).resolve()), language=None)

        st.markdown("---")


# @st.dialog 데코레이터 사용 버전 (Streamlit 1.33+)
try:
    @st.dialog("🔍 이미지 확대 보기", width="large")
    def _image_zoom_dialog(image_path: str, caption: str = ""):
        """이미지 확대 다이얼로그 (Streamlit 1.33+)"""
        if not image_path or not os.path.exists(image_path):
            st.error("이미지를 찾을 수 없습니다.")
            return

        # 확대된 이미지
        st.image(image_path, use_container_width=True)

        # 캡션
        if caption:
            st.markdown(f"**{caption}**")

        # 이미지 정보
        info = get_image_info(image_path)
        st.caption(f"📏 {info['width']}x{info['height']} | {info['size_kb']}KB | {info['format']}")

        # 파일 경로
        with st.expander("📂 파일 경로"):
            st.code(str(Path(image_path).resolve()), language=None)

    DIALOG_AVAILABLE = True

except Exception:
    # @st.dialog가 지원되지 않는 버전
    DIALOG_AVAILABLE = False

    def _image_zoom_dialog(image_path: str, caption: str = ""):
        """Fallback: 다이얼로그 미지원 시 session_state 방식 사용"""
        open_image_zoom(image_path, caption)


def render_clickable_thumbnail(
    image_path: str,
    caption: str = "",
    width: int = 150,
    key: str = ""
) -> bool:
    """
    클릭 가능한 썸네일 이미지 (확대 버튼 포함)

    JavaScript 없이 동작하는 확대 기능 제공

    Args:
        image_path: 이미지 파일 경로
        caption: 캡션
        width: 썸네일 너비
        key: 고유 키

    Returns:
        이미지 표시 성공 여부
    """
    if not image_path or not os.path.exists(image_path):
        st.markdown(f"""
        <div style="
            width: {width}px;
            height: {width}px;
            background: linear-gradient(135deg, #f0f0f0, #e0e0e0);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #999;
            font-size: 24px;
        ">🖼️</div>
        """, unsafe_allow_html=True)
        if caption:
            st.caption(caption)
        return False

    unique_key = key or f"thumb_{hash(image_path) % 100000}"

    # 이미지 + 확대 버튼을 컨테이너에 배치
    with st.container():
        # 썸네일 이미지
        st.image(image_path, width=width)

        # 확대 버튼
        if st.button("🔍", key=f"zoom_{unique_key}", help="이미지 확대 보기"):
            if DIALOG_AVAILABLE:
                _image_zoom_dialog(image_path, caption or Path(image_path).name)
            else:
                open_image_zoom(image_path, caption or Path(image_path).name)
                st.rerun()

        # 캡션
        if caption:
            st.caption(caption)

    return True


def render_image_grid_with_zoom(
    images: List[Union[str, Dict]],
    columns: int = 4,
    thumbnail_width: int = 150,
    show_captions: bool = True,
    key_prefix: str = "grid"
):
    """
    확대 기능이 있는 이미지 그리드 (Streamlit 네이티브)

    Args:
        images: 이미지 경로 리스트 또는 {"path": "...", "caption": "..."} 딕셔너리 리스트
        columns: 열 개수
        thumbnail_width: 썸네일 너비
        show_captions: 캡션 표시 여부
        key_prefix: 키 접두사
    """
    if not images:
        st.info("표시할 이미지가 없습니다.")
        return

    # 이미지 데이터 정규화
    normalized_images = []
    for i, img in enumerate(images):
        if isinstance(img, str):
            normalized_images.append({
                "path": img,
                "caption": Path(img).name if show_captions else ""
            })
        elif isinstance(img, dict):
            normalized_images.append({
                "path": img.get("path", ""),
                "caption": img.get("caption", Path(img.get("path", "")).name if show_captions else "")
            })

    # 유효한 이미지만 필터링
    valid_images = [
        img for img in normalized_images
        if img["path"] and os.path.exists(img["path"])
    ]

    if not valid_images:
        st.warning("표시할 유효한 이미지가 없습니다.")
        return

    # 그리드 렌더링
    cols = st.columns(columns)

    for idx, img_data in enumerate(valid_images):
        with cols[idx % columns]:
            render_clickable_thumbnail(
                image_path=img_data["path"],
                caption=img_data["caption"] if show_captions else "",
                width=thumbnail_width,
                key=f"{key_prefix}_{idx}"
            )
