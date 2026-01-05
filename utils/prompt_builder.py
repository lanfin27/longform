# -*- coding: utf-8 -*-
"""
이미지 프롬프트 빌더
- 여러 소스에서 프롬프트 조합
- 최종 프롬프트 미리보기
- 프롬프트 구성 요소 분해
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import streamlit as st


@dataclass
class PromptComponent:
    """프롬프트 구성 요소"""
    name: str           # 구성 요소 이름 (예: "스타일 Prefix")
    source: str         # 출처 (예: "스타일 관리 > 애니메이션")
    content: str        # 실제 프롬프트 내용
    editable: bool = True  # 수정 가능 여부
    order: int = 0      # 조합 순서


@dataclass
class PromptBuildResult:
    """프롬프트 빌드 결과"""
    final_prompt: str           # 최종 프롬프트
    final_negative: str         # 최종 네거티브 프롬프트
    components: List[PromptComponent] = field(default_factory=list)
    negative_components: List[PromptComponent] = field(default_factory=list)

    def get_breakdown(self) -> str:
        """프롬프트 구성 분해 텍스트 반환"""
        lines = ["프롬프트 구성:"]
        for i, comp in enumerate(self.components, 1):
            preview = comp.content[:50] + "..." if len(comp.content) > 50 else comp.content
            lines.append(f"  {i}. [{comp.name}] ({comp.source})")
            lines.append(f"     -> {preview}")
        return "\n".join(lines)


class PromptBuilder:
    """프롬프트 빌더"""

    def __init__(self):
        self.components: List[PromptComponent] = []
        self.negative_components: List[PromptComponent] = []

    def add(
        self,
        name: str,
        content: str,
        source: str = "",
        editable: bool = True,
        order: int = None
    ) -> 'PromptBuilder':
        """프롬프트 구성 요소 추가"""
        if not content or not content.strip():
            return self

        if order is None:
            order = len(self.components)

        self.components.append(PromptComponent(
            name=name,
            source=source,
            content=content.strip(),
            editable=editable,
            order=order
        ))
        return self

    def add_negative(
        self,
        name: str,
        content: str,
        source: str = ""
    ) -> 'PromptBuilder':
        """네거티브 프롬프트 구성 요소 추가"""
        if not content or not content.strip():
            return self

        self.negative_components.append(PromptComponent(
            name=name,
            source=source,
            content=content.strip(),
            editable=True,
            order=len(self.negative_components)
        ))
        return self

    def build(self, separator: str = ", ") -> PromptBuildResult:
        """최종 프롬프트 빌드"""

        # 순서대로 정렬
        sorted_components = sorted(self.components, key=lambda x: x.order)
        sorted_negative = sorted(self.negative_components, key=lambda x: x.order)

        # 조합
        final_prompt = separator.join(c.content for c in sorted_components if c.content)
        final_negative = separator.join(c.content for c in sorted_negative if c.content)

        return PromptBuildResult(
            final_prompt=final_prompt,
            final_negative=final_negative,
            components=sorted_components,
            negative_components=sorted_negative
        )

    def clear(self):
        """초기화"""
        self.components = []
        self.negative_components = []
        return self


# ===== Streamlit UI 컴포넌트 =====

def render_prompt_preview(
    build_result: PromptBuildResult,
    key_prefix: str = "prompt",
    allow_edit: bool = True,
    show_breakdown: bool = True,
    title: str = "최종 프롬프트 미리보기"
) -> Dict[str, str]:
    """
    프롬프트 미리보기 UI 렌더링

    Args:
        build_result: 프롬프트 빌드 결과
        key_prefix: Streamlit 위젯 키 접두사
        allow_edit: 수정 허용 여부
        show_breakdown: 구성 요소 분해 표시 여부
        title: 섹션 제목

    Returns:
        {"final_prompt": str, "final_negative": str} - 수정된 프롬프트
    """

    st.markdown(f"### {title}")

    # 프롬프트 구성 분해 표시
    if show_breakdown and build_result.components:
        with st.expander("프롬프트 구성 요소 (클릭하여 펼치기)", expanded=False):
            for i, comp in enumerate(build_result.components, 1):
                col1, col2 = st.columns([1, 3])
                with col1:
                    st.markdown(f"**{i}. {comp.name}**")
                    st.caption(f"출처: {comp.source}")
                with col2:
                    st.code(comp.content, language=None)

            st.markdown("---")
            st.info("위 요소들이 쉼표(,)로 연결되어 최종 프롬프트가 됩니다.")

    # 최종 프롬프트 (수정 가능)
    st.markdown("#### 최종 프롬프트")

    if allow_edit:
        final_prompt = st.text_area(
            "프롬프트 (수정 가능)",
            value=build_result.final_prompt,
            height=120,
            key=f"{key_prefix}_final_prompt",
            help="생성 전에 프롬프트를 직접 수정할 수 있습니다."
        )
    else:
        final_prompt = build_result.final_prompt
        st.code(final_prompt, language=None)

    # 프롬프트 길이 표시
    char_count = len(final_prompt)
    word_count = len(final_prompt.split())

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("문자 수", f"{char_count:,}")
    with col2:
        st.metric("단어 수", f"{word_count:,}")
    with col3:
        # 대략적인 토큰 수 (영어 기준 약 4자 = 1토큰)
        approx_tokens = char_count // 4
        if approx_tokens < 200:
            token_status = "적정"
        elif approx_tokens < 300:
            token_status = "주의"
        else:
            token_status = "초과"
        st.metric("예상 토큰", f"~{approx_tokens} ({token_status})")

    # 네거티브 프롬프트
    if build_result.final_negative or build_result.negative_components:
        st.markdown("#### 네거티브 프롬프트")

        if allow_edit:
            final_negative = st.text_input(
                "네거티브 (수정 가능)",
                value=build_result.final_negative,
                key=f"{key_prefix}_final_negative"
            )
        else:
            final_negative = build_result.final_negative
            st.code(final_negative, language=None)
    else:
        final_negative = ""

    return {
        "final_prompt": final_prompt,
        "final_negative": final_negative
    }


def render_prompt_preview_compact(
    build_result: PromptBuildResult,
    key_prefix: str = "prompt",
    expanded: bool = False
) -> Dict[str, str]:
    """
    컴팩트한 프롬프트 미리보기 (expander로 감싸짐)

    Args:
        build_result: 프롬프트 빌드 결과
        key_prefix: Streamlit 위젯 키 접두사
        expanded: 기본 펼침 여부

    Returns:
        {"final_prompt": str, "final_negative": str} - 수정된 프롬프트
    """

    with st.expander("최종 프롬프트 미리보기 및 수정", expanded=expanded):
        return render_prompt_preview(
            build_result,
            key_prefix,
            allow_edit=True,
            show_breakdown=True,
            title="프롬프트 상세"
        )


def render_prompt_breakdown_table(components: List[PromptComponent]) -> None:
    """프롬프트 구성 요소 테이블로 표시"""

    if not components:
        st.info("프롬프트 구성 요소가 없습니다.")
        return

    # 테이블 헤더
    cols = st.columns([0.5, 2, 3])
    cols[0].markdown("**#**")
    cols[1].markdown("**구성 요소**")
    cols[2].markdown("**내용 미리보기**")

    st.markdown("---")

    # 각 구성 요소
    for i, comp in enumerate(components, 1):
        cols = st.columns([0.5, 2, 3])
        cols[0].write(str(i))
        cols[1].markdown(f"**{comp.name}**")
        cols[1].caption(comp.source)

        preview = comp.content[:80] + "..." if len(comp.content) > 80 else comp.content
        cols[2].code(preview, language=None)


def build_background_prompt(
    scene_prompt: str,
    style_prefix: str = "",
    style_suffix: str = "",
    style_negative: str = "",
    style_name: str = "기본"
) -> PromptBuildResult:
    """
    배경 이미지용 프롬프트 빌드

    Args:
        scene_prompt: 씬 이미지 프롬프트
        style_prefix: 스타일 Prefix
        style_suffix: 스타일 Suffix
        style_negative: 네거티브 프롬프트
        style_name: 스타일 이름 (출처 표시용)

    Returns:
        PromptBuildResult
    """
    builder = PromptBuilder()

    if style_prefix:
        builder.add(
            name="스타일 Prefix",
            content=style_prefix,
            source=f"스타일 관리 > {style_name}",
            order=0
        )

    if scene_prompt:
        builder.add(
            name="씬 이미지 프롬프트",
            content=scene_prompt,
            source="씬 분석",
            order=1
        )

    if style_suffix:
        builder.add(
            name="스타일 Suffix",
            content=style_suffix,
            source=f"스타일 관리 > {style_name}",
            order=2
        )

    if style_negative:
        builder.add_negative(
            name="스타일 네거티브",
            content=style_negative,
            source=f"스타일 관리 > {style_name}"
        )

    return builder.build()


def build_character_prompt(
    character_prompt: str,
    pose_prompt: str = "",
    style_prefix: str = "",
    style_suffix: str = "",
    negative_prompt: str = "",
    character_name: str = "캐릭터",
    pose_name: str = "기본"
) -> PromptBuildResult:
    """
    캐릭터 이미지용 프롬프트 빌드

    Args:
        character_prompt: 캐릭터 기본 프롬프트
        pose_prompt: 포즈/표정 프롬프트
        style_prefix: 스타일 Prefix
        style_suffix: 스타일 Suffix
        negative_prompt: 네거티브 프롬프트
        character_name: 캐릭터 이름 (출처 표시용)
        pose_name: 포즈 이름 (출처 표시용)

    Returns:
        PromptBuildResult
    """
    builder = PromptBuilder()

    if style_prefix:
        builder.add(
            name="스타일 Prefix",
            content=style_prefix,
            source="스타일 프리셋",
            order=0
        )

    if character_prompt:
        builder.add(
            name="캐릭터 프롬프트",
            content=character_prompt,
            source=f"대표 캐릭터 > {character_name}",
            order=1
        )

    if pose_prompt:
        builder.add(
            name="표정/포즈",
            content=pose_prompt,
            source=f"생성 옵션 > {pose_name}",
            order=2
        )

    if style_suffix:
        builder.add(
            name="스타일 Suffix",
            content=style_suffix,
            source="스타일 프리셋",
            order=3
        )

    if negative_prompt:
        builder.add_negative(
            name="네거티브",
            content=negative_prompt,
            source=f"대표 캐릭터 > {character_name}"
        )

    return builder.build()


def build_composite_prompt(
    scene_prompt: str,
    character_action: str = "",
    style_prefix: str = "",
    style_suffix: str = "",
    negative_prompt: str = "",
    scene_id: int = 0,
    style_name: str = "기본"
) -> PromptBuildResult:
    """
    씬 합성 이미지용 프롬프트 빌드

    Args:
        scene_prompt: 씬 이미지 프롬프트
        character_action: 캐릭터 액션 프롬프트
        style_prefix: 스타일 Prefix
        style_suffix: 스타일 Suffix
        negative_prompt: 네거티브 프롬프트
        scene_id: 씬 번호
        style_name: 스타일 이름

    Returns:
        PromptBuildResult
    """
    builder = PromptBuilder()

    if style_prefix:
        builder.add(
            name="씬 합성 Prefix",
            content=style_prefix,
            source=f"스타일 관리 > 씬 합성 > {style_name}",
            order=0
        )

    if scene_prompt:
        builder.add(
            name="씬 이미지 프롬프트",
            content=scene_prompt,
            source=f"씬 분석 > 씬 {scene_id}",
            order=1
        )

    if character_action:
        builder.add(
            name="캐릭터 액션",
            content=character_action,
            source=f"대표 캐릭터 > 씬 {scene_id} 액션",
            order=2
        )

    if style_suffix:
        builder.add(
            name="씬 합성 Suffix",
            content=style_suffix,
            source=f"스타일 관리 > 씬 합성 > {style_name}",
            order=3
        )

    if negative_prompt:
        builder.add_negative(
            name="네거티브",
            content=negative_prompt,
            source=f"스타일 관리 > {style_name}"
        )

    return builder.build()
