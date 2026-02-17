"""
씬별 캐릭터 이미지 갤러리 UI 컴포넌트 v1.2

씬 번호순으로 캐릭터 이미지를 표시하고,
개별/일괄 재생성을 지원합니다.

v1.2: 컴팩트 3열 레이아웃
- 가로에 3개 씬 표시 (이전: 1개)
- 버튼 아이콘화 (🔄, 🗑️)
- 캐릭터 이미지 크게 (use_container_width=True)
- CSS 컴팩트 스타일링
- 전체적으로 더 많은 씬을 한 화면에 표시

v1.1: 카드 스타일 갤러리 UI
- 씬별 캐릭터가 펼치지 않아도 바로 보이는 카드 스타일
- 모두 펼치기 기본값 True로 변경
- 이미지 없는 캐릭터에 생성 버튼 추가
- 이미지 경로 해상도 개선

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
    columns_per_row: int = 2,  # v1.2: 씬 내 캐릭터 열 수 (컴팩트)
    thumbnail_size: int = 150,
    scenes_per_row: int = 3  # v1.2: 가로당 씬 개수 (기본 3)
):
    """
    씬별 캐릭터 갤러리 렌더링 v1.2

    Args:
        scenes: SceneCharacters 목록
        project_path: 프로젝트 경로
        on_regenerate: 재생성 콜백 함수 (char_name, pose, scene_num)
        on_delete: 삭제 콜백 함수 (char_name, pose)
        columns_per_row: 씬 내 캐릭터 열 수
        thumbnail_size: 썸네일 크기 (px)
        scenes_per_row: 가로당 씬 개수 (v1.2)
    """
    if not scenes:
        st.info("표시할 캐릭터가 있는 씬이 없습니다.")
        st.caption("캐릭터 관리에서 캐릭터 이미지를 생성하면 여기에 표시됩니다.")
        return

    # v1.2: 컴팩트 CSS 스타일 적용
    _apply_compact_gallery_css()

    # 통계 표시
    _render_gallery_stats(scenes)

    st.divider()

    # 필터 옵션 (v1.2: 더 컴팩트하게)
    filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([1, 1, 1, 1, 1])

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
            value=True,
            key="gallery_auto_expand"
        )

    with filter_col5:
        # v1.2: 행당 씬 수 조절 슬라이더
        scenes_per_row = st.selectbox(
            "행당 씬",
            options=[2, 3, 4, 5],
            index=1,  # 기본값 3
            key="gallery_scenes_per_row"
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

    # v1.2: 씬을 가로로 여러 개 배치 (3열 또는 사용자 선택)
    for row_start in range(0, len(filtered_scenes), scenes_per_row):
        row_scenes = filtered_scenes[row_start:row_start + scenes_per_row]
        cols = st.columns(scenes_per_row)

        for col_idx, scene in enumerate(row_scenes):
            with cols[col_idx]:
                _render_scene_card_compact(
                    scene=scene,
                    project_path=project_path,
                    on_regenerate=on_regenerate,
                    on_delete=on_delete,
                    columns_per_row=columns_per_row,
                    thumbnail_size=thumbnail_size,
                    auto_expand=auto_expand
                )


def _apply_compact_gallery_css():
    """v1.2: 컴팩트 갤러리 CSS 스타일"""
    st.markdown("""
    <style>
    /* 컬럼 간격 줄이기 */
    [data-testid="column"] {
        padding-left: 4px !important;
        padding-right: 4px !important;
    }

    /* 버튼 패딩 줄이기 */
    .compact-gallery .stButton > button {
        padding: 2px 6px !important;
        min-height: 28px !important;
        font-size: 14px !important;
    }

    /* 캡션 크기 줄이기 */
    .compact-gallery .stCaption {
        font-size: 11px !important;
        margin-top: 2px !important;
        margin-bottom: 2px !important;
    }

    /* 구분선 여백 줄이기 */
    .compact-gallery hr {
        margin: 6px 0 !important;
    }

    /* 헤더 크기 조정 */
    .compact-gallery h5 {
        font-size: 13px !important;
        margin-bottom: 4px !important;
    }

    /* 메트릭 컴팩트 */
    [data-testid="stMetricValue"] {
        font-size: 18px !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 11px !important;
    }
    </style>
    """, unsafe_allow_html=True)


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


def _render_scene_card_compact(
    scene,  # SceneCharacters
    project_path: str,
    on_regenerate: Callable,
    on_delete: Callable,
    columns_per_row: int,
    thumbnail_size: int,
    auto_expand: bool
):
    """
    개별 씬 카드 렌더링 v1.2 - 컴팩트 버전

    v1.2 변경사항:
    - 헤더 간소화 (씬 번호 + 상태 아이콘만)
    - 이미지 크게 (use_container_width=True)
    - 버튼 아이콘화 (🔄, 🗑️)
    - 공간 최소화
    """
    scene_num = scene.scene_number
    characters = scene.characters

    # 상태 아이콘
    if scene.is_complete:
        status_icon = "✅"
    elif characters:
        status_icon = "👤"
    else:
        status_icon = "⚪"

    # 재생성 필요 여부
    needs_regen_count = sum(1 for c in characters if c.needs_regeneration)

    # v1.2: 컴팩트 카드 컨테이너
    with st.container():
        # 헤더: 씬 번호 + 상태 (작게)
        header_text = f"##### {status_icon} 씬 {scene_num}"
        if needs_regen_count > 0:
            header_text += f" ⚠️"
        st.markdown(header_text)

        # 배경 있음 표시 (있는 경우만)
        if scene.has_background:
            st.caption("🖼️ 배경")

        # 캐릭터 이미지들
        if not characters:
            st.caption("캐릭터 없음")
        else:
            # v1.2: 캐릭터 이미지를 크게 표시
            num_chars = len(characters)
            char_cols = st.columns(min(num_chars, 2))  # 최대 2열

            for i, char in enumerate(characters):
                col_idx = i % len(char_cols)

                with char_cols[col_idx]:
                    _render_character_thumbnail_compact(
                        char=char,
                        scene_num=scene_num,
                        on_regenerate=on_regenerate,
                        on_delete=on_delete
                    )

        # v1.2: 구분선 (작게)
        st.markdown("---")


def _render_scene_card(
    scene,  # SceneCharacters
    project_path: str,
    on_regenerate: Callable,
    on_delete: Callable,
    columns_per_row: int,
    thumbnail_size: int,
    auto_expand: bool
):
    """
    개별 씬 카드 렌더링 v1.1 (레거시 - 호환성 유지)

    카드 스타일: 펼치지 않아도 캐릭터 이미지가 바로 보이는 UI
    """
    scene_num = scene.scene_number
    characters = scene.characters

    # 상태 아이콘 및 색상
    if scene.is_complete:
        status_icon = "✅"
        status_color = "#28a745"
        status_text = "완성"
    elif characters:
        status_icon = "👤"
        status_color = "#ffc107"
        status_text = f"캐릭터 {len(characters)}개"
    else:
        status_icon = "⚪"
        status_color = "#6c757d"
        status_text = "캐릭터 없음"

    # 재생성 필요 여부
    needs_regen_count = sum(1 for c in characters if c.needs_regeneration)

    # ═══════════════════════════════════════════════════════════════
    # v1.1: 카드 스타일 컨테이너 (expander 대신 container 사용)
    # ═══════════════════════════════════════════════════════════════

    # 씬 카드 컨테이너
    with st.container():
        # 카드 헤더 (항상 표시)
        header_col1, header_col2, header_col3 = st.columns([1, 3, 1])

        with header_col1:
            st.markdown(f"### {status_icon} 씬 {scene_num}")

        with header_col2:
            status_parts = [status_text]
            if needs_regen_count > 0:
                status_parts.append(f"⚠️ {needs_regen_count}개 재생성 권장")
            st.caption(" | ".join(status_parts))

        with header_col3:
            if scene.has_background:
                st.caption("🖼️ 배경 있음")

        # ═══════════════════════════════════════════════════════════════
        # 캐릭터 그리드 (항상 표시 - expander 없음)
        # ═══════════════════════════════════════════════════════════════
        if not characters:
            st.info("이 씬에 연결된 캐릭터 이미지가 없습니다.")
            # 씬의 캐릭터 프롬프트 표시 (있는 경우)
            _show_scene_character_info(scene_num, project_path)
        else:
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

        # 카드 구분선
        st.divider()


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


def _render_character_thumbnail_compact(
    char,  # CharacterImage
    scene_num: int,
    on_regenerate: Callable,
    on_delete: Callable
):
    """
    개별 캐릭터 썸네일 렌더링 v1.2 - 컴팩트 버전

    v1.2 변경사항:
    - 이미지 크게 (use_container_width=True)
    - 버튼 아이콘화 (🔄, 🗑️)
    - 캐릭터 이름만 표시 (포즈, 크기 생략)
    - 공간 최소화
    """
    from PIL import Image

    # 고유 키 생성
    safe_name = char.character_name.replace(' ', '_').replace('/', '_').replace('\\', '_')

    # 이미지 존재 여부
    has_image = char.image_path and os.path.exists(char.image_path)

    # v1.2: 이미지 크게 표시 (컨테이너 너비에 맞춤)
    if has_image:
        try:
            img = Image.open(char.image_path)
            st.image(img, use_container_width=True)
        except Exception:
            has_image = False
            _render_placeholder_compact(char.character_name)
    else:
        _render_placeholder_compact(char.character_name)

    # v1.2: 캐릭터 이름만 (간결하게)
    st.caption(f"**{char.character_name}**")

    # v1.2: 아이콘 버튼 (작게, 한 줄에)
    if has_image:
        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if on_regenerate:
                if st.button(
                    "🔄",
                    key=f"regen_c_{safe_name}_{scene_num}",
                    help="재생성",
                    use_container_width=True
                ):
                    on_regenerate(char.character_name, char.pose, scene_num)

        with btn_col2:
            if on_delete:
                if st.button(
                    "🗑️",
                    key=f"del_c_{safe_name}_{scene_num}",
                    help="삭제",
                    use_container_width=True
                ):
                    on_delete(char.character_name, char.pose)
    else:
        # 이미지 없을 때: 생성 버튼
        if on_regenerate:
            if st.button(
                "🎨",
                key=f"gen_c_{safe_name}_{scene_num}",
                help="이미지 생성",
                use_container_width=True,
                type="primary"
            ):
                on_regenerate(char.character_name, char.pose, scene_num)


def _render_placeholder_compact(char_name: str = ""):
    """v1.2: 컴팩트 플레이스홀더"""
    initial = char_name[0].upper() if char_name else "?"

    st.markdown(
        f"""
        <div style="
            width: 100%;
            aspect-ratio: 1;
            background: linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px dashed #7986cb;
            border-radius: 8px;
        ">
            <span style="color: #3f51b5; font-size: 28px; font-weight: bold;">{initial}</span>
        </div>
        """,
        unsafe_allow_html=True
    )


def _render_character_thumbnail(
    char,  # CharacterImage
    scene_num: int,
    thumbnail_size: int,
    on_regenerate: Callable,
    on_delete: Callable
):
    """
    개별 캐릭터 썸네일 렌더링 v1.1 (레거시 - 호환성 유지)

    v1.1: 이미지 없는 경우 생성 버튼 포함 플레이스홀더
    """
    from PIL import Image

    # 컨테이너
    with st.container():
        # 고유 키 생성 (이름 정규화)
        safe_name = char.character_name.replace(' ', '_').replace('/', '_').replace('\\', '_')

        # 이미지 존재 여부 확인
        has_image = char.image_path and os.path.exists(char.image_path)

        # 이미지 표시
        if has_image:
            try:
                img = Image.open(char.image_path)
                st.image(img, width=thumbnail_size, caption=None)
            except Exception as e:
                has_image = False
                _render_placeholder_image(thumbnail_size, char.character_name)
        else:
            # v1.1: 이미지 없을 때 생성 버튼 포함 플레이스홀더
            _render_placeholder_image(thumbnail_size, char.character_name)

        # 캐릭터 정보
        st.markdown(f"**{char.character_name}**")
        st.caption(f"포즈: {char.pose}")

        if char.dimensions[0] > 0:
            st.caption(f"{char.dimensions[0]}x{char.dimensions[1]}")

        # 재생성 필요 경고
        if char.needs_regeneration:
            st.warning(f"{char.regeneration_reason}")

        # v1.1: 버튼 레이아웃 개선
        if has_image:
            # 이미지 있는 경우: 재생성 + 삭제
            btn_col1, btn_col2 = st.columns(2)

            with btn_col1:
                if on_regenerate:
                    btn_key = f"regen_{safe_name}_{char.pose}_{scene_num}"

                    if st.button(
                        "재생성",
                        key=btn_key,
                        use_container_width=True
                    ):
                        on_regenerate(char.character_name, char.pose, scene_num)

            with btn_col2:
                if on_delete:
                    del_key = f"del_{safe_name}_{char.pose}_{scene_num}"

                    if st.button(
                        "삭제",
                        key=del_key,
                        use_container_width=True
                    ):
                        on_delete(char.character_name, char.pose)
        else:
            # v1.1: 이미지 없는 경우: 생성 버튼만 (강조)
            if on_regenerate:
                gen_key = f"gen_{safe_name}_{char.pose}_{scene_num}"

                if st.button(
                    "🎨 이미지 생성",
                    key=gen_key,
                    use_container_width=True,
                    type="primary"
                ):
                    on_regenerate(char.character_name, char.pose, scene_num)

        st.markdown("---")


def _render_placeholder_image(size: int, char_name: str = ""):
    """
    플레이스홀더 이미지 v1.1

    v1.1: 캐릭터 이름 표시 및 시각적 개선
    """
    # 캐릭터 이름의 첫 글자 추출 (한글/영문 모두 지원)
    initial = char_name[0].upper() if char_name else "?"

    st.markdown(
        f"""
        <div style="
            width: {size}px;
            height: {size}px;
            background: linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            border: 2px dashed #7986cb;
            border-radius: 12px;
            margin: 0 auto;
        ">
            <span style="color: #3f51b5; font-size: 36px; font-weight: bold;">{initial}</span>
            <span style="color: #7986cb; font-size: 11px; margin-top: 4px;">이미지 없음</span>
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
