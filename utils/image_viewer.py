# -*- coding: utf-8 -*-
"""
이미지 뷰어 및 프롬프트 관리 (v1.0)

기능:
1. 이미지 확대 모달 (st.dialog 사용)
2. 이미지 프롬프트 메타데이터 저장/로드
3. 씬 분석 데이터에서 프롬프트 추출
"""

import os
import json
import base64
import streamlit as st
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any, List, Tuple


class ImagePromptManager:
    """이미지 프롬프트 메타데이터 관리"""

    @staticmethod
    def get_metadata_path(image_path: str) -> str:
        """이미지 경로에서 메타데이터 JSON 경로 생성"""
        if not image_path:
            return None
        base = os.path.splitext(image_path)[0]
        return f"{base}_meta.json"

    @staticmethod
    def save_metadata(image_path: str,
                      scene_id: int,
                      original_prompt: str = None,
                      final_prompt: str = None,
                      negative_prompt: str = None,
                      model: str = None,
                      style: str = None,
                      seed: int = None,
                      **extra) -> bool:
        """이미지 메타데이터 저장"""
        if not image_path:
            return False

        json_path = ImagePromptManager.get_metadata_path(image_path)

        metadata = {
            'version': '1.0',
            'created_at': datetime.now().isoformat(),
            'image_path': os.path.basename(image_path),
            'scene_id': scene_id,
            'prompts': {
                'original': original_prompt,
                'final': final_prompt,
                'negative': negative_prompt
            },
            'generation': {
                'model': model,
                'style': style,
                'seed': seed,
                **extra
            }
        }

        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ImagePromptManager] 저장 실패: {e}")
            return False

    @staticmethod
    def load_metadata(image_path: str) -> Optional[Dict]:
        """이미지 메타데이터 로드"""
        if not image_path:
            return None

        json_path = ImagePromptManager.get_metadata_path(image_path)

        if not os.path.exists(json_path):
            # 기존 메타데이터 시스템과 호환 (.json 파일)
            alt_json_path = str(Path(image_path).with_suffix('.json'))
            if os.path.exists(alt_json_path):
                json_path = alt_json_path
            else:
                return None

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None

    @staticmethod
    def get_prompt_from_scene(scene: Dict) -> Dict[str, str]:
        """씬 분석 데이터에서 프롬프트 추출"""
        if not scene:
            return {}

        # 다양한 필드명 지원
        image_prompt = (
            scene.get('image_prompt') or
            scene.get('imagePrompt') or
            scene.get('이미지_프롬프트') or
            scene.get('image_generation_prompt') or
            scene.get('image_prompt_en') or
            scene.get('prompt') or
            ''
        )

        video_prompt = (
            scene.get('video_prompt') or
            scene.get('videoPrompt') or
            scene.get('비디오_프롬프트') or
            scene.get('video_prompt_en') or
            ''
        )

        direction_guide = (
            scene.get('direction_guide') or
            scene.get('연출가이드') or
            scene.get('directionGuide') or
            scene.get('direction') or
            ''
        )

        return {
            'image_prompt': image_prompt,
            'video_prompt': video_prompt,
            'direction_guide': direction_guide
        }


def show_image_modal(image_path: str,
                     scene_id: int = None,
                     scene: Dict = None,
                     title: str = None):
    """
    이미지 확대 모달 표시 (st.dialog 사용)

    Args:
        image_path: 이미지 파일 경로
        scene_id: 씬 번호
        scene: 씬 분석 데이터 (프롬프트 추출용)
        title: 모달 제목
    """

    if not image_path or not os.path.exists(image_path):
        st.error("이미지를 찾을 수 없습니다.")
        return

    modal_title = title or (f"씬 {scene_id}" if scene_id else "이미지 확대")

    @st.dialog(modal_title, width="large")
    def _image_dialog():
        # 이미지 표시 (전체 너비)
        st.image(image_path, use_container_width=True)

        # 프롬프트 정보 가져오기
        metadata = ImagePromptManager.load_metadata(image_path)
        scene_prompts = ImagePromptManager.get_prompt_from_scene(scene) if scene else {}

        # 프롬프트 결정 (메타데이터 > 씬 데이터)
        final_prompt = None
        original_prompt = None

        if metadata:
            prompts = metadata.get('prompts', {})
            final_prompt = prompts.get('final')
            original_prompt = prompts.get('original')

        if not final_prompt and not original_prompt:
            final_prompt = scene_prompts.get('image_prompt', '')

        # 프롬프트 섹션
        st.markdown("---")

        if final_prompt or original_prompt or scene_prompts.get('image_prompt'):
            st.markdown("### 이미지 생성 프롬프트")

            # 탭으로 프롬프트 종류 구분
            prompt_tabs = st.tabs(["이미지 프롬프트", "연출가이드", "비디오 프롬프트"])

            with prompt_tabs[0]:
                prompt_to_show = final_prompt or original_prompt or scene_prompts.get('image_prompt', '')
                if prompt_to_show:
                    st.text_area(
                        "프롬프트",
                        value=prompt_to_show,
                        height=150,
                        disabled=True,
                        label_visibility="collapsed"
                    )

                    # 복사 버튼
                    if st.button("프롬프트 복사", key="copy_prompt_modal"):
                        st.code(prompt_to_show)
                        st.success("위 텍스트를 선택하여 복사하세요!")
                else:
                    st.info("이미지 프롬프트 정보가 없습니다.")

            with prompt_tabs[1]:
                direction = scene_prompts.get('direction_guide', '')
                if direction:
                    st.text_area(
                        "연출가이드",
                        value=direction,
                        height=100,
                        disabled=True,
                        label_visibility="collapsed"
                    )
                else:
                    st.info("연출가이드 정보가 없습니다.")

            with prompt_tabs[2]:
                video = scene_prompts.get('video_prompt', '')
                if video:
                    st.text_area(
                        "비디오 프롬프트",
                        value=video,
                        height=100,
                        disabled=True,
                        label_visibility="collapsed"
                    )
                else:
                    st.info("비디오 프롬프트 정보가 없습니다.")
        else:
            st.info("프롬프트 정보가 저장되지 않았습니다.")

        # 메타데이터 정보
        if metadata:
            generation = metadata.get('generation', {})
            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.caption(f"**모델:** {generation.get('model', 'N/A')}")
            with col2:
                st.caption(f"**스타일:** {generation.get('style', 'N/A')}")
            with col3:
                st.caption(f"**시드:** {generation.get('seed', 'N/A')}")

        # 닫기 버튼
        st.markdown("---")
        if st.button("닫기", type="primary", use_container_width=True):
            st.rerun()

    _image_dialog()


def render_image_card_with_zoom(image_path: str,
                                 scene_id: int,
                                 scene: Dict = None,
                                 show_prompt_button: bool = True,
                                 card_key: str = None):
    """
    확대 및 프롬프트 기능이 포함된 이미지 카드 렌더링

    Args:
        image_path: 이미지 파일 경로
        scene_id: 씬 번호
        scene: 씬 분석 데이터
        show_prompt_button: 프롬프트 버튼 표시 여부
        card_key: Streamlit 키 (중복 방지)
    """

    key_prefix = card_key or f"img_{scene_id}"

    if not image_path or not os.path.exists(image_path):
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #f5f5f5, #e0e0e0);
            border-radius: 12px;
            padding: 60px 20px;
            text-align: center;
            color: #999;
            border: 2px dashed #ccc;
        ">
            <div style="font-size: 48px; margin-bottom: 10px;">🖼️</div>
            <div>이미지 없음</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # 이미지 표시 (썸네일)
    st.image(image_path, use_container_width=True)

    # 버튼 행
    col1, col2 = st.columns(2)

    with col1:
        # 확대 버튼
        if st.button("🔍 확대", key=f"{key_prefix}_zoom", use_container_width=True):
            st.session_state[f'{key_prefix}_show_modal'] = True

    with col2:
        # 프롬프트 버튼
        if show_prompt_button:
            if st.button("📝 프롬프트", key=f"{key_prefix}_prompt", use_container_width=True):
                st.session_state[f'{key_prefix}_show_prompt'] = True

    # 모달 표시
    if st.session_state.get(f'{key_prefix}_show_modal', False):
        show_image_modal(image_path, scene_id, scene, f"씬 {scene_id}")
        st.session_state[f'{key_prefix}_show_modal'] = False

    # 프롬프트 팝업 (expander 방식)
    if st.session_state.get(f'{key_prefix}_show_prompt', False):
        with st.expander("📝 프롬프트 정보", expanded=True):
            # 프롬프트 가져오기
            metadata = ImagePromptManager.load_metadata(image_path)
            scene_prompts = ImagePromptManager.get_prompt_from_scene(scene) if scene else {}

            prompt = None
            if metadata:
                prompts = metadata.get('prompts', {})
                prompt = prompts.get('final') or prompts.get('original')

            if not prompt:
                prompt = scene_prompts.get('image_prompt', '')

            if prompt:
                st.text_area(
                    "이미지 프롬프트",
                    value=prompt,
                    height=100,
                    disabled=True,
                    key=f"{key_prefix}_prompt_text",
                    label_visibility="collapsed"
                )
            else:
                st.info("프롬프트 정보가 없습니다.")

            if st.button("닫기", key=f"{key_prefix}_close_prompt"):
                st.session_state[f'{key_prefix}_show_prompt'] = False
                st.rerun()


def render_image_grid_with_zoom(images: List[Dict],
                                 columns: int = 4,
                                 show_prompt_button: bool = True):
    """
    확대 기능이 포함된 이미지 그리드 렌더링

    Args:
        images: [{'path': str, 'scene_id': int, 'scene': Dict}, ...]
        columns: 열 개수
        show_prompt_button: 프롬프트 버튼 표시 여부
    """

    for i in range(0, len(images), columns):
        cols = st.columns(columns)

        for j, col in enumerate(cols):
            idx = i + j
            if idx < len(images):
                img_data = images[idx]

                with col:
                    render_image_card_with_zoom(
                        image_path=img_data.get('path'),
                        scene_id=img_data.get('scene_id', idx + 1),
                        scene=img_data.get('scene'),
                        show_prompt_button=show_prompt_button,
                        card_key=f"grid_{idx}"
                    )

                    # 씬 번호 표시
                    st.caption(f"씬 {img_data.get('scene_id', idx + 1)}")


def render_clickable_image(image_path: str,
                            scene_id: int = 0,
                            scene: Dict = None,
                            prompt: str = "",
                            width: str = "100%",
                            key_prefix: str = None):
    """
    클릭 시 확대되는 이미지 렌더링 (Streamlit 네이티브 방식)

    JavaScript 라이트박스 대신 st.dialog 사용으로 안정성 향상

    Args:
        image_path: 이미지 파일 경로
        scene_id: 씬 번호
        scene: 씬 데이터 (프롬프트 추출용)
        prompt: 이미지 프롬프트 (직접 전달)
        width: 이미지 너비 (CSS)
        key_prefix: 버튼 키 접두사
    """

    if not image_path or not os.path.exists(image_path):
        st.markdown(f"""
        <div style="
            background: #f0f0f0;
            border-radius: 8px;
            padding: 40px;
            text-align: center;
            color: #999;
        ">
            🖼️ 이미지 없음
        </div>
        """, unsafe_allow_html=True)
        return

    key = key_prefix or f"clickable_{scene_id}_{hash(image_path) % 10000}"

    # 이미지 표시
    st.image(image_path, use_container_width=True)

    # 확대/프롬프트 버튼
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button("🔍 확대", key=f"{key}_zoom_btn", use_container_width=True):
            st.session_state[f'{key}_show_zoom'] = True

    with btn_col2:
        if st.button("📝 프롬프트", key=f"{key}_prompt_btn", use_container_width=True):
            st.session_state[f'{key}_show_prompt_ex'] = not st.session_state.get(f'{key}_show_prompt_ex', False)

    # 확대 모달
    if st.session_state.get(f'{key}_show_zoom', False):
        show_image_modal(image_path, scene_id, scene, f"씬 {scene_id}")
        st.session_state[f'{key}_show_zoom'] = False

    # 프롬프트 expander
    if st.session_state.get(f'{key}_show_prompt_ex', False):
        with st.expander("📝 이미지 프롬프트", expanded=True):
            # 프롬프트 결정
            final_prompt = prompt
            if not final_prompt:
                metadata = ImagePromptManager.load_metadata(image_path)
                if metadata:
                    prompts = metadata.get('prompts', {})
                    final_prompt = prompts.get('final') or prompts.get('original')
            if not final_prompt and scene:
                scene_prompts = ImagePromptManager.get_prompt_from_scene(scene)
                final_prompt = scene_prompts.get('image_prompt', '')

            if final_prompt:
                st.text_area(
                    "프롬프트",
                    value=final_prompt,
                    height=100,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"{key}_prompt_area"
                )
            else:
                st.info("프롬프트 정보가 없습니다.")

            if st.button("닫기", key=f"{key}_close_ex"):
                st.session_state[f'{key}_show_prompt_ex'] = False
                st.rerun()


def inject_lightbox_assets():
    """
    라이트박스 CSS/JS를 페이지에 주입 (components/image_viewer.py와 호환)

    이 함수는 components/image_viewer.py의 render_lightbox_container()와
    동일한 역할을 하며, 호환성을 위해 제공됩니다.
    """
    try:
        from components.image_viewer import render_lightbox_container
        render_lightbox_container()
    except ImportError:
        # 폴백: 기본 CSS만 주입
        st.markdown("""
        <style>
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
        </style>
        """, unsafe_allow_html=True)


# ============================================================
# 편의 함수 (기존 코드와의 호환성)
# ============================================================

def get_image_prompt_info(image_path: str) -> Optional[Dict]:
    """
    이미지 프롬프트 정보 반환 (utils/image_prompt_metadata.py와 호환)
    """
    return ImagePromptManager.load_metadata(image_path)


def has_prompt_metadata(image_path: str) -> bool:
    """프롬프트 메타데이터 존재 여부"""
    return ImagePromptManager.load_metadata(image_path) is not None


def render_prompt_info_expander(image_path: str, scene_data: Dict = None, key: str = ""):
    """
    프롬프트 정보 expander 렌더링 (기존 함수와 호환)
    """
    metadata = ImagePromptManager.load_metadata(image_path)
    scene_prompts = ImagePromptManager.get_prompt_from_scene(scene_data) if scene_data else {}

    has_info = bool(metadata or scene_prompts.get('image_prompt'))

    if not has_info:
        return

    with st.expander("📝 프롬프트 정보", expanded=False):
        # 원본 프롬프트
        original = ""
        final = ""

        if metadata:
            prompts = metadata.get('prompts', {})
            original = prompts.get('original', '')
            final = prompts.get('final', '')

        # 씬 데이터에서 보완
        if not original and scene_data:
            original = scene_prompts.get('image_prompt', '')

        if original:
            st.markdown("**원본 프롬프트:**")
            st.text_area("원본", original, height=80, disabled=True,
                        label_visibility="collapsed", key=f"orig_{key}")

        if final and final != original:
            st.markdown("**최종 프롬프트 (API):**")
            st.text_area("최종", final, height=80, disabled=True,
                        label_visibility="collapsed", key=f"final_{key}")

        # 생성 정보
        if metadata:
            gen = metadata.get('generation', {})
            style_info = metadata.get('style', {})

            info_parts = []
            if gen.get('api_provider'):
                info_parts.append(f"API: {gen.get('api_provider')}")
            if gen.get('model_name') or gen.get('model'):
                info_parts.append(f"Model: {gen.get('model_name', gen.get('model'))}")
            if style_info.get('name'):
                info_parts.append(f"Style: {style_info.get('name')}")

            if info_parts:
                st.caption(" | ".join(info_parts))
