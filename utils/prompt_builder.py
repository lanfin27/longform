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


# ===================================================================
# 여러 씬 프롬프트 미리보기 UI (v2.0)
# ===================================================================

@dataclass
class ScenePromptPreview:
    """씬별 프롬프트 미리보기 데이터"""
    scene_id: int
    original_prompt: str
    final_prompt: str
    negative_prompt: str
    style_prefix: str = ""
    style_suffix: str = ""
    style_name: str = ""
    final_length: int = 0


def render_multi_scene_prompt_preview(
    scene_previews: List[ScenePromptPreview],
    max_display: int = 5,
    key_prefix: str = "multi_preview"
) -> None:
    """
    여러 씬의 프롬프트 미리보기 UI

    Args:
        scene_previews: 씬별 프롬프트 미리보기 리스트
        max_display: 최대 표시 씬 수
        key_prefix: Streamlit 위젯 키 접두사
    """
    if not scene_previews:
        st.info("선택된 씬이 없습니다.")
        return

    # 요약 통계
    total_scenes = len(scene_previews)
    avg_length = sum(p.final_length for p in scene_previews) // total_scenes if total_scenes > 0 else 0
    max_length = max(p.final_length for p in scene_previews) if scene_previews else 0
    min_length = min(p.final_length for p in scene_previews) if scene_previews else 0

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("선택된 씬", f"{total_scenes}개")
    with col2:
        st.metric("평균 프롬프트 길이", f"{avg_length:,}자")
    with col3:
        st.metric("최소 길이", f"{min_length:,}자")
    with col4:
        st.metric("최대 길이", f"{max_length:,}자")

    st.markdown("---")

    # 씬별 상세 미리보기
    display_previews = scene_previews[:max_display]

    for i, preview in enumerate(display_previews):
        with st.expander(f"📝 씬 {preview.scene_id} 프롬프트 ({preview.final_length:,}자)", expanded=(i == 0)):
            # 탭으로 구분
            tabs = st.tabs(["📝 원본", "🎨 스타일", "🔗 최종", "🚫 Negative"])

            with tabs[0]:  # 원본 프롬프트
                st.markdown("**씬 분석 결과 프롬프트:**")
                st.code(preview.original_prompt if preview.original_prompt else "(없음)", language=None)

            with tabs[1]:  # 스타일 (Prefix + Suffix)
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Prefix:**")
                    prefix_display = preview.style_prefix[:300] + "..." if len(preview.style_prefix) > 300 else preview.style_prefix
                    st.code(prefix_display if prefix_display else "(없음)", language=None)
                with col2:
                    st.markdown("**Suffix:**")
                    suffix_display = preview.style_suffix[:300] + "..." if len(preview.style_suffix) > 300 else preview.style_suffix
                    st.code(suffix_display if suffix_display else "(없음)", language=None)

            with tabs[2]:  # 최종 프롬프트
                st.markdown("**최종 프롬프트 (API에 전달됨):**")
                st.code(preview.final_prompt, language=None)
                st.caption(f"📏 {preview.final_length:,}자 | ~{preview.final_length // 4} 토큰")

            with tabs[3]:  # Negative Prompt
                st.markdown("**네거티브 프롬프트:**")
                negative_display = preview.negative_prompt[:500] + "..." if len(preview.negative_prompt) > 500 else preview.negative_prompt
                st.code(negative_display if negative_display else "(없음)", language=None)

    # 더 많은 씬이 있는 경우
    if len(scene_previews) > max_display:
        remaining = len(scene_previews) - max_display
        st.info(f"📌 {remaining}개 씬 추가 있음 (처음 {max_display}개만 표시)")

        # 나머지 씬 ID 목록
        remaining_ids = [p.scene_id for p in scene_previews[max_display:]]
        if len(remaining_ids) <= 20:
            st.caption(f"추가 씬: {', '.join(map(str, remaining_ids))}")
        else:
            st.caption(f"추가 씬: {', '.join(map(str, remaining_ids[:20]))}... 외 {len(remaining_ids) - 20}개")


def build_scene_previews(
    scenes: List[Dict],
    selected_scene_ids: List[int],
    style_prefix: str = "",
    style_suffix: str = "",
    negative_prompt: str = "",
    style_name: str = "",
    prompt_key: str = "image_prompt_en"
) -> List[ScenePromptPreview]:
    """
    선택된 씬들의 프롬프트 미리보기 데이터 생성

    Args:
        scenes: 전체 씬 리스트
        selected_scene_ids: 선택된 씬 ID 리스트
        style_prefix: 스타일 Prefix
        style_suffix: 스타일 Suffix
        negative_prompt: 네거티브 프롬프트
        style_name: 스타일 이름
        prompt_key: 프롬프트 키 (image_prompt_en, background_prompt 등)

    Returns:
        ScenePromptPreview 리스트
    """
    previews = []

    # 씬 ID -> 씬 데이터 매핑
    scene_map = {}
    for scene in scenes:
        sid = scene.get("scene_id") or scene.get("id")
        if sid:
            scene_map[sid] = scene

    for scene_id in selected_scene_ids:
        scene = scene_map.get(scene_id)
        if not scene:
            continue

        # 원본 프롬프트 가져오기
        prompts_data = scene.get("prompts", {})
        original_prompt = (
            scene.get(prompt_key, "") or
            prompts_data.get(prompt_key, "") or
            scene.get("image_prompt_ko", "") or
            scene.get("background_prompt", "") or
            scene.get("description", "")
        )

        # 최종 프롬프트 조합
        parts = []
        if style_prefix:
            parts.append(style_prefix.strip())
        if original_prompt:
            parts.append(original_prompt.strip())
        if style_suffix:
            parts.append(style_suffix.strip())

        final_prompt = ", ".join(parts)

        previews.append(ScenePromptPreview(
            scene_id=scene_id,
            original_prompt=original_prompt,
            final_prompt=final_prompt,
            negative_prompt=negative_prompt,
            style_prefix=style_prefix,
            style_suffix=style_suffix,
            style_name=style_name,
            final_length=len(final_prompt)
        ))

    return previews


# ===================================================================
# 생성 결과 저장 및 표시 (v2.0)
# ===================================================================

@dataclass
class GenerationResult:
    """이미지 생성 결과"""
    scene_id: int
    status: str  # "success", "failed", "skipped"
    image_path: Optional[str] = None
    final_prompt: str = ""
    negative_prompt: str = ""
    original_prompt: str = ""
    api_provider: str = ""
    model: str = ""
    duration: float = 0.0
    error_message: str = ""


class GenerationResultTracker:
    """이미지 생성 결과 추적기"""

    def __init__(self):
        self.results: List[GenerationResult] = []
        self.start_time: float = 0
        self.end_time: float = 0

    def start(self):
        """추적 시작"""
        import time
        self.results = []
        self.start_time = time.time()

    def add_success(
        self,
        scene_id: int,
        image_path: str,
        final_prompt: str,
        negative_prompt: str = "",
        original_prompt: str = "",
        api_provider: str = "",
        model: str = "",
        duration: float = 0.0
    ):
        """성공 결과 추가"""
        self.results.append(GenerationResult(
            scene_id=scene_id,
            status="success",
            image_path=image_path,
            final_prompt=final_prompt,
            negative_prompt=negative_prompt,
            original_prompt=original_prompt,
            api_provider=api_provider,
            model=model,
            duration=duration
        ))

    def add_failed(
        self,
        scene_id: int,
        error_message: str,
        final_prompt: str = "",
        negative_prompt: str = "",
        original_prompt: str = ""
    ):
        """실패 결과 추가"""
        self.results.append(GenerationResult(
            scene_id=scene_id,
            status="failed",
            error_message=error_message,
            final_prompt=final_prompt,
            negative_prompt=negative_prompt,
            original_prompt=original_prompt
        ))

    def add_skipped(self, scene_id: int, reason: str):
        """스킵 결과 추가"""
        self.results.append(GenerationResult(
            scene_id=scene_id,
            status="skipped",
            error_message=reason
        ))

    def finish(self):
        """추적 종료"""
        import time
        self.end_time = time.time()

    @property
    def total_time(self) -> float:
        return self.end_time - self.start_time if self.end_time > 0 else 0

    @property
    def success_count(self) -> int:
        return len([r for r in self.results if r.status == "success"])

    @property
    def failed_count(self) -> int:
        return len([r for r in self.results if r.status == "failed"])

    @property
    def skipped_count(self) -> int:
        return len([r for r in self.results if r.status == "skipped"])

    @property
    def avg_duration(self) -> float:
        success_results = [r for r in self.results if r.status == "success" and r.duration > 0]
        if not success_results:
            return 0
        return sum(r.duration for r in success_results) / len(success_results)


def render_generation_results(tracker: GenerationResultTracker, key_prefix: str = "gen_results"):
    """
    이미지 생성 결과 UI 렌더링

    Args:
        tracker: 생성 결과 추적기
        key_prefix: Streamlit 위젯 키 접두사
    """
    if not tracker.results:
        st.info("생성 결과가 없습니다.")
        return

    # 요약 통계
    st.markdown("## 📊 생성 결과 요약")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("✅ 성공", f"{tracker.success_count}개", delta=None)
    with col2:
        st.metric("❌ 실패", f"{tracker.failed_count}개", delta=None)
    with col3:
        st.metric("⏱️ 총 소요 시간", f"{tracker.total_time:.1f}초")
    with col4:
        st.metric("📊 평균 생성 시간", f"{tracker.avg_duration:.1f}초")

    # 상세 결과
    with st.expander("📋 상세 결과 및 사용된 프롬프트", expanded=False):
        for result in tracker.results:
            # 상태에 따른 표시
            if result.status == "success":
                st.success(f"✅ 씬 {result.scene_id}: 성공 ({result.duration:.1f}초)")
            elif result.status == "failed":
                st.error(f"❌ 씬 {result.scene_id}: 실패 - {result.error_message}")
            else:
                st.warning(f"⏭️ 씬 {result.scene_id}: 스킵 - {result.error_message}")

            # 프롬프트 상세 (성공/실패만)
            if result.status != "skipped":
                tabs = st.tabs(["🔗 최종 프롬프트", "📝 원본", "🚫 Negative", "📊 메타데이터"])

                with tabs[0]:
                    st.code(result.final_prompt if result.final_prompt else "(없음)", language=None)

                with tabs[1]:
                    st.code(result.original_prompt if result.original_prompt else "(없음)", language=None)

                with tabs[2]:
                    negative_display = result.negative_prompt[:500] + "..." if len(result.negative_prompt) > 500 else result.negative_prompt
                    st.code(negative_display if negative_display else "(없음)", language=None)

                with tabs[3]:
                    meta_info = {
                        "API": result.api_provider or "N/A",
                        "모델": result.model or "N/A",
                        "소요 시간": f"{result.duration:.2f}초" if result.duration > 0 else "N/A",
                        "프롬프트 길이": f"{len(result.final_prompt):,}자" if result.final_prompt else "N/A",
                    }
                    for key, value in meta_info.items():
                        st.text(f"{key}: {value}")

                    if result.image_path:
                        st.text(f"이미지 경로: {result.image_path}")

            st.divider()


# 전역 결과 추적기 (세션 스테이트에 저장)
def get_generation_tracker() -> GenerationResultTracker:
    """생성 결과 추적기 가져오기 또는 생성"""
    if "generation_result_tracker" not in st.session_state:
        st.session_state["generation_result_tracker"] = GenerationResultTracker()
    return st.session_state["generation_result_tracker"]


def clear_generation_tracker():
    """생성 결과 추적기 초기화"""
    st.session_state["generation_result_tracker"] = GenerationResultTracker()
