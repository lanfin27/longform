"""
씬별 캐릭터 이미지 갤러리 UI 컴포넌트 v1.0

씬 번호순으로 캐릭터 이미지를 표시하고,
개별/일괄 재생성을 지원합니다.

작성: 2026-01
"""

import streamlit as st
import os
from typing import List, Dict, Callable, Optional
from pathlib import Path

# 타입 힌트용 (런타임에는 사용 안함)
try:
    from utils.character_gallery import CharacterImage, SceneCharacters
except ImportError:
    pass


def render_scene_character_gallery(
    scenes: List,  # List[SceneCharacters]
    project_path: str,
    on_regenerate: Callable[[str, str, int], None] = None,
    on_delete: Callable[[str, str], None] = None,
    columns_per_row: int = 4,
    thumbnail_size: int = 150
):
    """
    씬별 캐릭터 갤러리 렌더링

    Args:
        scenes: SceneCharacters 목록
        project_path: 프로젝트 경로
        on_regenerate: 재생성 콜백 함수 (char_name, pose, scene_num)
        on_delete: 삭제 콜백 함수 (char_name, pose)
        columns_per_row: 한 줄당 캐릭터 수
        thumbnail_size: 썸네일 크기 (px)
    """
    if not scenes:
        st.info("표시할 캐릭터가 있는 씬이 없습니다.")
        st.caption("캐릭터 관리에서 캐릭터 이미지를 생성하면 여기에 표시됩니다.")
        return

    # 통계 표시
    _render_gallery_stats(scenes)

    st.divider()

    # 필터 옵션
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1, 1, 1, 1])

    with filter_col1:
        show_only_with_chars = st.checkbox(
            "캐릭터 있는 씬만",
            value=True,
            key="gallery_filter_has_chars"
        )

    with filter_col2:
        show_only_needs_regen = st.checkbox(
            "재생성 필요만",
            value=False,
            key="gallery_filter_needs_regen"
        )

    with filter_col3:
        show_incomplete = st.checkbox(
            "미완성 씬만",
            value=False,
            key="gallery_filter_incomplete"
        )

    with filter_col4:
        auto_expand = st.checkbox(
            "모두 펼치기",
            value=False,
            key="gallery_auto_expand"
        )

    # 필터 적용
    filtered_scenes = scenes

    if show_only_with_chars:
        filtered_scenes = [s for s in filtered_scenes if s.characters]

    if show_only_needs_regen:
        filtered_scenes = [s for s in filtered_scenes
                          if any(c.needs_regeneration for c in s.characters)]

    if show_incomplete:
        filtered_scenes = [s for s in filtered_scenes if not s.is_complete]

    st.caption(f"{len(filtered_scenes)}개 씬 표시 중 (전체 {len(scenes)}개)")

    if not filtered_scenes:
        st.info("필터 조건에 맞는 씬이 없습니다.")
        return

    # 일괄 재생성 섹션 (재생성 필요한 경우만)
    needs_regen_count = sum(
        sum(1 for c in s.characters if c.needs_regeneration)
        for s in filtered_scenes
    )
    if needs_regen_count > 0:
        _render_batch_regeneration_section(filtered_scenes, on_regenerate)

    st.divider()

    # 씬별로 렌더링
    for scene in filtered_scenes:
        _render_scene_card(
            scene=scene,
            project_path=project_path,
            on_regenerate=on_regenerate,
            on_delete=on_delete,
            columns_per_row=columns_per_row,
            thumbnail_size=thumbnail_size,
            auto_expand=auto_expand
        )


def _render_gallery_stats(scenes: List):
    """갤러리 통계 표시"""
    total_scenes = len(scenes)
    scenes_with_chars = sum(1 for s in scenes if s.characters)
    total_chars = sum(len(s.characters) for s in scenes)
    needs_regen = sum(sum(1 for c in s.characters if c.needs_regeneration) for s in scenes)
    complete = sum(1 for s in scenes if s.is_complete)

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("총 씬", total_scenes)

    with col2:
        st.metric("캐릭터 있음", scenes_with_chars)

    with col3:
        st.metric("총 캐릭터", total_chars)

    with col4:
        delta = f"-{needs_regen}" if needs_regen > 0 else None
        st.metric("재생성 필요", needs_regen, delta=delta, delta_color="inverse")

    with col5:
        completion = (complete / total_scenes * 100) if total_scenes > 0 else 0
        st.metric("완성률", f"{completion:.0f}%")


def _render_batch_regeneration_section(scenes: List, on_regenerate: Callable):
    """일괄 재생성 섹션"""
    # 재생성 필요한 캐릭터 수집
    needs_regen = []

    for scene in scenes:
        for char in scene.characters:
            if char.needs_regeneration:
                needs_regen.append({
                    'scene': scene.scene_number,
                    'character': char.character_name,
                    'pose': char.pose,
                    'reason': char.regeneration_reason
                })

    if not needs_regen:
        return

    with st.expander(f"재생성 권장 목록 ({len(needs_regen)}개)", expanded=False):
        st.warning(f"{len(needs_regen)}개 캐릭터의 재생성이 권장됩니다")

        # 목록 표시
        for item in needs_regen[:10]:  # 최대 10개만 표시
            st.markdown(f"- 씬 {item['scene']}: **{item['character']}** ({item['pose']}) - {item['reason']}")

        if len(needs_regen) > 10:
            st.caption(f"... 외 {len(needs_regen) - 10}개")

        # 일괄 재생성은 세션 상태로 처리
        if st.button(
            f"재생성 필요 목록 저장",
            key="save_regen_list",
            help="배치 생성 탭에서 재생성할 수 있습니다"
        ):
            st.session_state['regen_needed_chars'] = needs_regen
            st.success(f"{len(needs_regen)}개 캐릭터가 재생성 목록에 저장되었습니다.")
            st.info("배치 생성 탭에서 재생성하세요.")


def _render_scene_card(
    scene,  # SceneCharacters
    project_path: str,
    on_regenerate: Callable,
    on_delete: Callable,
    columns_per_row: int,
    thumbnail_size: int,
    auto_expand: bool
):
    """개별 씬 카드 렌더링"""
    scene_num = scene.scene_number
    characters = scene.characters

    # 상태 아이콘
    if scene.is_complete:
        status_icon = "+"
        status_text = "완성"
    elif characters:
        status_icon = "~"
        status_text = f"캐릭터 {len(characters)}개"
    else:
        status_icon = "-"
        status_text = "캐릭터 없음"

    # 재생성 필요 여부
    needs_regen_count = sum(1 for c in characters if c.needs_regeneration)

    # 헤더 텍스트
    header = f"씬 {scene_num} [{status_icon}] | {status_text}"
    if needs_regen_count > 0:
        header += f" | {needs_regen_count}개 재생성 권장"

    # 씬 카드 헤더
    should_expand = auto_expand or needs_regen_count > 0

    with st.expander(header, expanded=should_expand):
        if not characters:
            st.warning("이 씬에 연결된 캐릭터 이미지가 없습니다.")

            # 씬의 캐릭터 프롬프트 표시 (있는 경우)
            _show_scene_character_info(scene_num, project_path)
            return

        # 캐릭터 그리드
        num_chars = len(characters)
        cols_to_use = min(num_chars, columns_per_row)

        cols = st.columns(cols_to_use)

        for i, char in enumerate(characters):
            col_idx = i % cols_to_use

            with cols[col_idx]:
                _render_character_thumbnail(
                    char=char,
                    scene_num=scene_num,
                    thumbnail_size=thumbnail_size,
                    on_regenerate=on_regenerate,
                    on_delete=on_delete
                )


def _show_scene_character_info(scene_num: int, project_path: str):
    """씬의 캐릭터 정보 표시 (이미지 없는 경우)"""
    scenes_json = Path(project_path) / 'analysis' / 'scenes.json'

    if not scenes_json.exists():
        return

    try:
        with open(scenes_json, 'r', encoding='utf-8') as f:
            scenes_data = json.load(f)

        # 해당 씬 찾기
        for scene in scenes_data:
            sid = scene.get('scene_id') or scene.get('scene_number', 0)
            if sid == scene_num:
                char_prompt = scene.get('character_prompt_en', '') or scene.get('character_prompt', '')
                if char_prompt and char_prompt.lower() not in ['n/a', 'none', '없음']:
                    st.caption(f"캐릭터 프롬프트: {char_prompt[:100]}...")
                break
    except Exception:
        pass


def _render_character_thumbnail(
    char,  # CharacterImage
    scene_num: int,
    thumbnail_size: int,
    on_regenerate: Callable,
    on_delete: Callable
):
    """개별 캐릭터 썸네일 렌더링"""
    from PIL import Image

    # 컨테이너
    with st.container():
        # 이미지 표시
        if char.image_path and os.path.exists(char.image_path):
            try:
                img = Image.open(char.image_path)
                st.image(img, width=thumbnail_size, caption=None)
            except Exception as e:
                st.error(f"로드 실패")
                _render_placeholder_image(thumbnail_size)
        else:
            _render_placeholder_image(thumbnail_size)

        # 캐릭터 정보
        st.markdown(f"**{char.character_name}**")
        st.caption(f"포즈: {char.pose}")

        if char.dimensions[0] > 0:
            st.caption(f"{char.dimensions[0]}x{char.dimensions[1]}")

        # 재생성 필요 경고
        if char.needs_regeneration:
            st.warning(f"{char.regeneration_reason}")

        # 버튼들
        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if on_regenerate:
                # 고유 키 생성 (이름 정규화)
                safe_name = char.character_name.replace(' ', '_').replace('/', '_')
                btn_key = f"regen_{safe_name}_{char.pose}_{scene_num}"

                if st.button(
                    "재생성",
                    key=btn_key,
                    use_container_width=True
                ):
                    on_regenerate(char.character_name, char.pose, scene_num)

        with btn_col2:
            if on_delete:
                safe_name = char.character_name.replace(' ', '_').replace('/', '_')
                del_key = f"del_{safe_name}_{char.pose}_{scene_num}"

                if st.button(
                    "삭제",
                    key=del_key,
                    use_container_width=True
                ):
                    on_delete(char.character_name, char.pose)

        st.markdown("---")


def _render_placeholder_image(size: int):
    """플레이스홀더 이미지"""
    st.markdown(
        f"""
        <div style="
            width: {size}px;
            height: {size}px;
            background-color: #f0f0f0;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px dashed #ccc;
            border-radius: 8px;
            margin: 0 auto;
        ">
            <span style="color: #999; font-size: 24px;">?</span>
        </div>
        """,
        unsafe_allow_html=True
    )


# JSON import
import json

# 내보내기
__all__ = [
    'render_scene_character_gallery'
]
