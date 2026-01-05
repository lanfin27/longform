# -*- coding: utf-8 -*-
"""
이미지 프롬프트 메타데이터 관리 (v1.0)

이미지 생성 시 사용된 프롬프트를 JSON 파일로 저장하고 관리합니다.

기능:
- 이미지 파일과 함께 프롬프트 메타데이터 JSON 저장
- 원본 프롬프트, 최종 프롬프트, 네거티브 프롬프트 저장
- 스타일, 모델, API 정보 저장
- 메타데이터 조회 및 UI 표시 지원
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime
import streamlit as st


class ImagePromptMetadata:
    """이미지 프롬프트 메타데이터 관리 클래스"""

    def __init__(self):
        self.version = "1.0"

    @staticmethod
    def get_metadata_path(image_path: str) -> Path:
        """
        이미지 경로에서 메타데이터 JSON 경로 생성

        예: bg_scene_001_1234567890.png -> bg_scene_001_1234567890.json
        """
        image_path = Path(image_path)
        return image_path.with_suffix('.json')

    def save_metadata(
        self,
        image_path: str,
        original_prompt: str,
        final_prompt: str,
        negative_prompt: str = "",
        style_id: str = "",
        style_name: str = "",
        style_prefix: str = "",
        style_suffix: str = "",
        api_provider: str = "",
        model: str = "",
        model_name: str = "",
        width: int = 0,
        height: int = 0,
        scene_id: int = None,
        extra_info: Dict[str, Any] = None
    ) -> bool:
        """
        이미지 프롬프트 메타데이터 저장

        Args:
            image_path: 이미지 파일 경로
            original_prompt: 원본 프롬프트 (씬 분석에서 생성된)
            final_prompt: 최종 API에 전달된 프롬프트
            negative_prompt: 네거티브 프롬프트
            style_id: 스타일 ID
            style_name: 스타일 이름
            style_prefix: 스타일 prefix
            style_suffix: 스타일 suffix
            api_provider: API 제공자 (Google ImageFX, Together.ai FLUX)
            model: 모델 ID
            model_name: 모델 표시 이름
            width: 이미지 너비
            height: 이미지 높이
            scene_id: 씬 ID
            extra_info: 추가 정보 (seed, 치환 정보 등)

        Returns:
            bool: 저장 성공 여부
        """
        try:
            metadata_path = self.get_metadata_path(image_path)

            metadata = {
                "version": self.version,
                "created_at": datetime.now().isoformat(),
                "image_file": os.path.basename(image_path),
                "scene_id": scene_id,

                # 프롬프트 정보
                "prompts": {
                    "original": original_prompt,
                    "final": final_prompt,
                    "negative": negative_prompt
                },

                # 스타일 정보
                "style": {
                    "id": style_id,
                    "name": style_name,
                    "prefix": style_prefix,
                    "suffix": style_suffix
                },

                # 생성 설정
                "generation": {
                    "api_provider": api_provider,
                    "model": model,
                    "model_name": model_name,
                    "width": width,
                    "height": height
                },

                # 추가 정보
                "extra": extra_info or {}
            }

            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            print(f"[ImagePromptMetadata] 메타데이터 저장됨: {metadata_path}")
            return True

        except Exception as e:
            print(f"[ImagePromptMetadata] 메타데이터 저장 실패: {e}")
            return False

    def load_metadata(self, image_path: str) -> Optional[Dict[str, Any]]:
        """
        이미지 프롬프트 메타데이터 로드

        Args:
            image_path: 이미지 파일 경로

        Returns:
            메타데이터 딕셔너리 또는 None
        """
        try:
            metadata_path = self.get_metadata_path(image_path)

            if not metadata_path.exists():
                return None

            with open(metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)

        except Exception as e:
            print(f"[ImagePromptMetadata] 메타데이터 로드 실패: {e}")
            return None

    def has_metadata(self, image_path: str) -> bool:
        """메타데이터 존재 여부 확인"""
        metadata_path = self.get_metadata_path(image_path)
        return metadata_path.exists()


# 싱글톤 인스턴스
_metadata_manager = None

def get_metadata_manager() -> ImagePromptMetadata:
    """메타데이터 관리자 인스턴스 반환"""
    global _metadata_manager
    if _metadata_manager is None:
        _metadata_manager = ImagePromptMetadata()
    return _metadata_manager


# =====================================================
# 헬퍼 함수
# =====================================================

def save_image_with_prompt(
    image_path: str,
    original_prompt: str,
    final_prompt: str,
    negative_prompt: str = "",
    style_id: str = "",
    style_name: str = "",
    style_prefix: str = "",
    style_suffix: str = "",
    api_provider: str = "",
    model: str = "",
    model_name: str = "",
    width: int = 0,
    height: int = 0,
    scene_id: int = None,
    extra_info: Dict[str, Any] = None
) -> bool:
    """
    이미지 저장 후 프롬프트 메타데이터도 함께 저장

    이 함수는 이미지 생성 함수에서 이미지 저장 직후에 호출합니다.
    """
    manager = get_metadata_manager()
    return manager.save_metadata(
        image_path=image_path,
        original_prompt=original_prompt,
        final_prompt=final_prompt,
        negative_prompt=negative_prompt,
        style_id=style_id,
        style_name=style_name,
        style_prefix=style_prefix,
        style_suffix=style_suffix,
        api_provider=api_provider,
        model=model,
        model_name=model_name,
        width=width,
        height=height,
        scene_id=scene_id,
        extra_info=extra_info
    )


def get_image_prompt_info(image_path: str) -> Optional[Dict[str, Any]]:
    """
    이미지의 프롬프트 정보 조회

    Args:
        image_path: 이미지 파일 경로

    Returns:
        프롬프트 정보 딕셔너리 또는 None
    """
    manager = get_metadata_manager()
    return manager.load_metadata(image_path)


def has_prompt_metadata(image_path: str) -> bool:
    """이미지에 프롬프트 메타데이터가 있는지 확인"""
    manager = get_metadata_manager()
    return manager.has_metadata(image_path)


# =====================================================
# UI 컴포넌트
# =====================================================

def render_prompt_info_button(image_path: str, key_prefix: str = "prompt_info"):
    """
    프롬프트 정보 보기 버튼 렌더링

    이미지 옆에 작은 버튼을 추가하여 클릭 시 프롬프트 정보를 표시합니다.
    """
    if not image_path:
        return

    # 메타데이터 확인
    metadata = get_image_prompt_info(image_path)

    if metadata:
        btn_key = f"{key_prefix}_{hash(image_path) % 10000}"
        if st.button("View Prompt", key=btn_key, help="생성에 사용된 프롬프트 보기"):
            st.session_state[f"show_prompt_{btn_key}"] = True

        # 모달처럼 표시
        if st.session_state.get(f"show_prompt_{btn_key}", False):
            render_prompt_info_modal(metadata, btn_key)


def render_prompt_info_modal(metadata: Dict[str, Any], key: str):
    """프롬프트 정보 모달/확장 패널 렌더링"""
    with st.expander("Prompt Details", expanded=True):
        prompts = metadata.get("prompts", {})
        style = metadata.get("style", {})
        gen = metadata.get("generation", {})

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
        st.markdown("**Original Prompt (Scene Analysis):**")
        st.code(prompts.get("original", "N/A"), language=None)

        # 스타일 정보
        if style.get("name"):
            st.markdown(f"**Style:** {style.get('name')} (`{style.get('id', '')}`)")

        if style.get("prefix"):
            st.markdown("**Style Prefix:**")
            st.code(style.get("prefix"), language=None)

        if style.get("suffix"):
            st.markdown("**Style Suffix:**")
            st.code(style.get("suffix"), language=None)

        # 최종 프롬프트
        st.markdown("**Final Prompt (Sent to API):**")
        st.code(prompts.get("final", "N/A"), language=None)

        # 네거티브 프롬프트
        if prompts.get("negative"):
            st.markdown("**Negative Prompt:**")
            st.code(prompts.get("negative"), language=None)

        # 추가 정보
        extra = metadata.get("extra", {})
        if extra:
            with st.expander("Additional Info"):
                st.json(extra)

        # 닫기 버튼
        if st.button("Close", key=f"close_{key}"):
            st.session_state[f"show_prompt_{key}"] = False
            st.rerun()


def render_prompt_info_expander(image_path: str, key_prefix: str = "prompt_exp"):
    """
    프롬프트 정보를 expander로 직접 렌더링

    스토리보드 등에서 이미지 아래에 바로 표시할 때 사용합니다.
    """
    if not image_path:
        return

    metadata = get_image_prompt_info(image_path)

    if not metadata:
        return

    prompts = metadata.get("prompts", {})
    style = metadata.get("style", {})
    gen = metadata.get("generation", {})

    unique_key = f"{key_prefix}_{hash(image_path) % 100000}"

    with st.expander("View Prompt Details", expanded=False):
        # 생성 정보 한 줄 요약
        api = gen.get('api_provider', 'N/A')
        model = gen.get('model_name', gen.get('model', 'N/A'))
        size = f"{gen.get('width', 0)}x{gen.get('height', 0)}"

        st.caption(f"{api} | {model} | {size}")

        # 원본 프롬프트
        original = prompts.get("original", "")
        if original:
            st.markdown("**Original:**")
            st.text_area(
                "Original prompt",
                original,
                height=60,
                disabled=True,
                label_visibility="collapsed",
                key=f"{unique_key}_orig"
            )

        # 최종 프롬프트
        final = prompts.get("final", "")
        if final:
            st.markdown("**Final:**")
            st.text_area(
                "Final prompt",
                final,
                height=100,
                disabled=True,
                label_visibility="collapsed",
                key=f"{unique_key}_final"
            )

        # 네거티브
        negative = prompts.get("negative", "")
        if negative:
            st.markdown("**Negative:**")
            st.text_area(
                "Negative prompt",
                negative,
                height=40,
                disabled=True,
                label_visibility="collapsed",
                key=f"{unique_key}_neg"
            )


# =====================================================
# 마이그레이션 유틸리티
# =====================================================

def migrate_existing_images(project_path: str) -> Dict[str, int]:
    """
    기존 이미지에 대해 빈 메타데이터 파일 생성

    이미 생성된 이미지에 대해 placeholder 메타데이터를 생성합니다.
    실제 프롬프트 정보는 없지만, 구조는 만들어둡니다.

    Returns:
        {"migrated": 개수, "skipped": 개수, "error": 개수}
    """
    project_path = Path(project_path)
    result = {"migrated": 0, "skipped": 0, "error": 0}

    # 이미지 폴더들
    image_dirs = [
        project_path / "images" / "backgrounds",
        project_path / "images" / "composited",
        project_path / "images" / "characters",
        project_path / "images" / "scenes"
    ]

    manager = get_metadata_manager()

    for img_dir in image_dirs:
        if not img_dir.exists():
            continue

        for img_file in img_dir.glob("*.png"):
            try:
                if manager.has_metadata(str(img_file)):
                    result["skipped"] += 1
                    continue

                # 파일명에서 씬 ID 추출 시도
                scene_id = None
                filename = img_file.stem
                parts = filename.split("_")
                for i, part in enumerate(parts):
                    if part == "scene" and i + 1 < len(parts):
                        try:
                            scene_id = int(parts[i + 1])
                        except ValueError:
                            pass
                        break

                # placeholder 메타데이터 생성
                manager.save_metadata(
                    image_path=str(img_file),
                    original_prompt="[Migrated - Original prompt not available]",
                    final_prompt="[Migrated - Final prompt not available]",
                    negative_prompt="",
                    scene_id=scene_id,
                    extra_info={"migrated": True, "migration_date": datetime.now().isoformat()}
                )
                result["migrated"] += 1

            except Exception as e:
                print(f"[Migration] Error migrating {img_file}: {e}")
                result["error"] += 1

    return result
