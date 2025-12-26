# -*- coding: utf-8 -*-
"""
캐릭터 드래그 에디터 모듈 v2.0

인포그래픽/배경 이미지 위에 캐릭터를 배치할 때
위치와 크기를 시각적으로 조정하는 UI 컴포넌트

v2.0 업데이트:
- 9개 위치 프리셋 (3x3 그리드)
- 크기 슬라이더 (10-60%) + 프리셋
- 스마트 배치 기능 (빈 공간 자동 감지)
- 배경 제거 자동 설치 지원

기능:
- 슬라이더로 X/Y 위치 조절
- 슬라이더로 크기 조절 (10-60%)
- 3x3 빠른 위치 버튼 (9개 위치)
- 스마트 배치 (자동 빈 공간 감지)
- 실시간 미리보기
- 합성 결과 저장
"""

import streamlit as st
from PIL import Image
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import io
import numpy as np


def find_empty_space(
    background: Image.Image,
    char_width: int,
    char_height: int,
    prefer_side: str = "any",
    grid_size: int = 3
) -> Tuple[int, int]:
    """
    배경 이미지에서 캐릭터를 배치하기 좋은 빈 공간 찾기

    밝기 분산이 낮은 (균일한) 영역을 찾아 캐릭터 배치 위치로 추천

    Args:
        background: 배경 PIL Image
        char_width: 캐릭터 너비
        char_height: 캐릭터 높이
        prefer_side: 선호하는 측면 ("left", "right", "any")
        grid_size: 탐색 그리드 크기

    Returns:
        (x, y) 최적 좌표
    """
    try:
        # 그레이스케일로 변환
        gray = background.convert('L')
        img_array = np.array(gray)

        height, width = img_array.shape
        margin = 20

        # 후보 영역 생성
        candidates = []

        for row in range(grid_size):
            for col in range(grid_size):
                # 영역 좌표 계산
                x = margin + (col * (width - char_width - 2 * margin)) // max(1, grid_size - 1)
                y = margin + (row * (height - char_height - 2 * margin)) // max(1, grid_size - 1)

                # 경계 체크
                x = max(margin, min(x, width - char_width - margin))
                y = max(margin, min(y, height - char_height - margin))

                # 해당 영역의 밝기 분석
                x1 = max(0, x)
                y1 = max(0, y)
                x2 = min(width, x + char_width)
                y2 = min(height, y + char_height)

                if x2 > x1 and y2 > y1:
                    region = img_array[y1:y2, x1:x2]

                    # 밝기 분산 계산 (낮을수록 균일한 영역 = 좋은 위치)
                    variance = float(np.var(region))
                    mean_brightness = float(np.mean(region))

                    # 점수 계산
                    score = variance

                    # 측면 선호도 반영
                    if prefer_side == "right" and col == grid_size - 1:
                        score *= 0.6  # 오른쪽 선호
                    elif prefer_side == "left" and col == 0:
                        score *= 0.6  # 왼쪽 선호

                    # 하단 선호 (캐릭터는 보통 하단에 배치)
                    if row == grid_size - 1:
                        score *= 0.7

                    # 너무 어두우면 페널티
                    if mean_brightness < 30:
                        score *= 1.5

                    candidates.append({
                        'x': x,
                        'y': y,
                        'score': score,
                        'variance': variance,
                        'row': row,
                        'col': col
                    })

        # 최적 위치 선택 (가장 낮은 점수)
        if candidates:
            best = min(candidates, key=lambda c: c['score'])
            return best['x'], best['y']

        # 기본값: 오른쪽 하단
        return width - char_width - margin, height - char_height - margin

    except Exception as e:
        print(f"[SmartPlacement] 빈 공간 찾기 실패: {e}")
        # 기본값: 오른쪽 하단
        bg_w, bg_h = background.size
        return bg_w - char_width - 20, bg_h - char_height - 20


def get_rembg_status() -> Tuple[bool, str]:
    """rembg 설치 상태 확인"""
    try:
        import rembg
        return True, "✅ rembg 사용 가능"
    except ImportError:
        return False, "❌ rembg 미설치"


def remove_background_if_needed(
    image: Image.Image,
    force_remove: bool = True
) -> Image.Image:
    """
    필요시 배경 제거

    Args:
        image: PIL Image (RGBA)
        force_remove: True면 강제 배경 제거

    Returns:
        배경 제거된 이미지 또는 원본
    """
    if not force_remove:
        return image

    # 이미 투명 배경인지 확인
    if image.mode == 'RGBA':
        alpha = image.split()[-1]
        extrema = alpha.getextrema()
        # 알파 채널에 완전 투명(0)이 5% 이상이면 이미 투명
        alpha_data = list(alpha.getdata())
        transparent_count = sum(1 for a in alpha_data if a < 10)
        if transparent_count / len(alpha_data) > 0.05:
            return image

    # rembg로 배경 제거
    try:
        from rembg import remove
        # PIL Image를 직접 전달
        result = remove(image)
        return result
    except ImportError:
        st.warning("⚠️ rembg가 설치되지 않아 배경 제거를 건너뜁니다.")
        return image
    except Exception as e:
        st.error(f"배경 제거 오류: {e}")
        return image


def render_character_editor(
    background_path: str,
    character_path: str,
    initial_position: Tuple[int, int] = None,
    initial_size: int = 25,
    remove_background: bool = True,
    key: str = "char_editor"
) -> Optional[Dict[str, Any]]:
    """
    캐릭터 위치/크기 조정 에디터 렌더링

    Args:
        background_path: 배경 이미지 경로 (인포그래픽/배경)
        character_path: 캐릭터 이미지 경로
        initial_position: 초기 위치 (x, y)
        initial_size: 초기 크기 (% of background height)
        remove_background: 배경 제거 여부
        key: Streamlit 위젯 고유 키

    Returns:
        {
            'position_x': int,
            'position_y': int,
            'size_percent': int,
            'composite_image': PIL.Image,
            'character_image': PIL.Image (배경 제거된)
        }
        또는 None (오류 시)
    """

    # 이미지 로드
    if not Path(background_path).exists():
        st.error(f"배경 이미지를 찾을 수 없습니다: {background_path}")
        return None

    if not Path(character_path).exists():
        st.error(f"캐릭터 이미지를 찾을 수 없습니다: {character_path}")
        return None

    try:
        background = Image.open(background_path).convert('RGBA')
        character_original = Image.open(character_path).convert('RGBA')
    except Exception as e:
        st.error(f"이미지 로드 오류: {e}")
        return None

    bg_width, bg_height = background.size

    # 세션 상태 초기화
    if f'{key}_pos_x' not in st.session_state:
        if initial_position:
            st.session_state[f'{key}_pos_x'] = initial_position[0]
            st.session_state[f'{key}_pos_y'] = initial_position[1]
        else:
            # 기본값: 오른쪽 하단
            st.session_state[f'{key}_pos_x'] = int(bg_width * 0.75)
            st.session_state[f'{key}_pos_y'] = int(bg_height * 0.6)

    if f'{key}_size' not in st.session_state:
        st.session_state[f'{key}_size'] = initial_size

    if f'{key}_remove_bg' not in st.session_state:
        st.session_state[f'{key}_remove_bg'] = remove_background

    # ========== 배경 제거 상태 ==========
    st.markdown("#### 🎭 배경 제거")

    rembg_available, rembg_msg = get_rembg_status()

    col_bg1, col_bg2 = st.columns([2, 3])

    with col_bg1:
        if rembg_available:
            st.success(rembg_msg)
            do_remove_bg = st.checkbox(
                "배경 제거 적용",
                value=st.session_state[f'{key}_remove_bg'],
                key=f'{key}_remove_bg_checkbox'
            )
            st.session_state[f'{key}_remove_bg'] = do_remove_bg
        else:
            st.error(rembg_msg)
            st.code("pip install rembg --break-system-packages")
            do_remove_bg = False

    with col_bg2:
        if rembg_available and do_remove_bg:
            st.info("💡 캐릭터 배경이 자동으로 제거됩니다.")
        elif not rembg_available:
            st.warning("⚠️ 배경 제거 없이 합성됩니다. 캐릭터 이미지가 이미 투명 배경이어야 합니다.")

    # 배경 제거 처리
    if do_remove_bg and rembg_available:
        with st.spinner("배경 제거 중..."):
            character = remove_background_if_needed(character_original, True)
    else:
        character = character_original

    st.divider()

    # ========== 컨트롤 UI ==========
    st.markdown("#### 🎯 캐릭터 위치 및 크기 조정")

    # === 크기 조절 영역 ===
    st.markdown("##### 📏 캐릭터 크기")
    size_col1, size_col2 = st.columns([2, 3])

    with size_col1:
        # 크기 슬라이더 (10-60%)
        size_percent = st.slider(
            "크기 (%)",
            min_value=10,
            max_value=60,
            value=st.session_state[f'{key}_size'],
            step=1,
            key=f'{key}_size_slider',
            help="배경 높이 대비 캐릭터 높이 비율 (10-60%)"
        )
        st.session_state[f'{key}_size'] = size_percent

    with size_col2:
        # 크기 프리셋 버튼
        st.caption("빠른 크기 선택")
        preset_cols = st.columns(6)
        size_presets = [
            ("10%", 10), ("20%", 20), ("30%", 30),
            ("40%", 40), ("50%", 50), ("60%", 60)
        ]
        for i, (label, val) in enumerate(size_presets):
            with preset_cols[i]:
                if st.button(label, key=f'{key}_size_preset_{i}', use_container_width=True):
                    st.session_state[f'{key}_size'] = val
                    st.rerun()

    # 캐릭터 크기 계산 (미리보기용)
    target_height = int(bg_height * size_percent / 100)
    char_w, char_h = character.size
    if char_h > 0:
        scale = target_height / char_h
        new_width = int(char_w * scale)
        new_height = target_height
    else:
        new_width, new_height = 100, 100

    st.divider()

    # === 위치 조절 영역 ===
    pos_col1, pos_col2 = st.columns(2)

    with pos_col1:
        # X 위치
        pos_x = st.slider(
            "↔️ X 위치 (가로)",
            min_value=0,
            max_value=max(1, bg_width - new_width),
            value=min(st.session_state[f'{key}_pos_x'], bg_width - new_width),
            step=10,
            key=f'{key}_pos_x_slider'
        )
        st.session_state[f'{key}_pos_x'] = pos_x

    with pos_col2:
        # Y 위치
        pos_y = st.slider(
            "↕️ Y 위치 (세로)",
            min_value=0,
            max_value=max(1, bg_height - new_height),
            value=min(st.session_state[f'{key}_pos_y'], bg_height - new_height),
            step=10,
            key=f'{key}_pos_y_slider'
        )
        st.session_state[f'{key}_pos_y'] = pos_y

    # === 3x3 빠른 위치 버튼 ===
    st.markdown("##### ⚡ 빠른 위치 선택 (3x3 그리드)")

    margin = 20

    # 3x3 그리드로 위치 프리셋 배열
    position_grid = [
        [("↖️", margin, margin),
         ("⬆️", (bg_width - new_width) // 2, margin),
         ("↗️", bg_width - new_width - margin, margin)],
        [("⬅️", margin, (bg_height - new_height) // 2),
         ("⏺️", (bg_width - new_width) // 2, (bg_height - new_height) // 2),
         ("➡️", bg_width - new_width - margin, (bg_height - new_height) // 2)],
        [("↙️", margin, bg_height - new_height - margin),
         ("⬇️", (bg_width - new_width) // 2, bg_height - new_height - margin),
         ("↘️", bg_width - new_width - margin, bg_height - new_height - margin)]
    ]

    for row_idx, row in enumerate(position_grid):
        pos_cols = st.columns(3)
        for col_idx, (label, px, py) in enumerate(row):
            with pos_cols[col_idx]:
                if st.button(label, key=f'{key}_grid_{row_idx}_{col_idx}', use_container_width=True):
                    st.session_state[f'{key}_pos_x'] = max(0, min(px, bg_width - new_width))
                    st.session_state[f'{key}_pos_y'] = max(0, min(py, bg_height - new_height))
                    st.rerun()

    # === 스마트 배치 버튼 ===
    st.markdown("##### 🧠 스마트 배치")
    smart_col1, smart_col2, smart_col3 = st.columns(3)

    with smart_col1:
        if st.button("🎯 자동 배치 (빈 공간)", key=f'{key}_smart_auto', use_container_width=True):
            smart_x, smart_y = find_empty_space(background, new_width, new_height)
            st.session_state[f'{key}_pos_x'] = smart_x
            st.session_state[f'{key}_pos_y'] = smart_y
            st.rerun()

    with smart_col2:
        if st.button("➡️ 오른쪽 빈 공간", key=f'{key}_smart_right', use_container_width=True):
            smart_x, smart_y = find_empty_space(background, new_width, new_height, prefer_side="right")
            st.session_state[f'{key}_pos_x'] = smart_x
            st.session_state[f'{key}_pos_y'] = smart_y
            st.rerun()

    with smart_col3:
        if st.button("⬅️ 왼쪽 빈 공간", key=f'{key}_smart_left', use_container_width=True):
            smart_x, smart_y = find_empty_space(background, new_width, new_height, prefer_side="left")
            st.session_state[f'{key}_pos_x'] = smart_x
            st.session_state[f'{key}_pos_y'] = smart_y
            st.rerun()

    st.divider()

    # ========== 합성 미리보기 생성 ==========
    # 캐릭터 리사이즈
    character_resized = character.resize((new_width, new_height), Image.LANCZOS)

    # 위치 경계 체크
    paste_x = max(0, min(st.session_state[f'{key}_pos_x'], bg_width - new_width))
    paste_y = max(0, min(st.session_state[f'{key}_pos_y'], bg_height - new_height))

    # 합성
    composite = background.copy()
    composite.paste(character_resized, (paste_x, paste_y), character_resized)

    # ========== 미리보기 표시 ==========
    st.markdown("#### 👁️ 미리보기")

    preview_col1, preview_col2 = st.columns([3, 1])

    with preview_col1:
        st.image(composite, use_container_width=True, caption="합성 결과 미리보기")

    with preview_col2:
        st.markdown("**현재 설정**")
        st.write(f"- 크기: {size_percent}%")
        st.write(f"- X: {paste_x}px")
        st.write(f"- Y: {paste_y}px")
        st.write(f"- 캐릭터 크기: {new_width}x{new_height}")
        st.write(f"- 배경 제거: {'✅' if do_remove_bg else '❌'}")

    return {
        'position_x': paste_x,
        'position_y': paste_y,
        'size_percent': size_percent,
        'composite_image': composite,
        'character_image': character_resized,
        'background_removed': do_remove_bg
    }


def render_character_preview_only(
    background_path: str,
    character_path: str,
    position_x: int,
    position_y: int,
    size_percent: int,
    remove_background: bool = True
) -> Optional[Image.Image]:
    """
    캐릭터 합성 결과 미리보기 이미지만 생성 (컨트롤 없음)

    Returns:
        합성된 PIL Image 또는 None
    """
    try:
        background = Image.open(background_path).convert('RGBA')
        character = Image.open(character_path).convert('RGBA')
    except Exception as e:
        return None

    bg_width, bg_height = background.size

    # 배경 제거
    if remove_background:
        character = remove_background_if_needed(character, True)

    # 크기 조절
    target_height = int(bg_height * size_percent / 100)
    char_w, char_h = character.size
    if char_h > 0:
        scale = target_height / char_h
        new_width = int(char_w * scale)
        new_height = target_height
        character = character.resize((new_width, new_height), Image.LANCZOS)

    # 합성
    composite = background.copy()
    composite.paste(character, (position_x, position_y), character)

    return composite


def save_composite_result(
    composite_image: Image.Image,
    output_path: str,
    format: str = 'PNG'
) -> str:
    """
    합성 결과 저장

    Args:
        composite_image: 합성된 PIL Image
        output_path: 저장 경로
        format: 이미지 포맷 ('PNG', 'JPEG')

    Returns:
        저장된 파일 경로
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    composite_image.save(output_path, format)
    return output_path


# 편의 함수들
def get_position_from_preset(
    preset: str,
    bg_size: Tuple[int, int],
    char_size: Tuple[int, int],
    margin: int = 20
) -> Tuple[int, int]:
    """
    위치 프리셋에서 좌표 계산 (3x3 그리드 지원)

    Args:
        preset: 위치 프리셋 이름 (한글 또는 영문)
        bg_size: (width, height) 배경 크기
        char_size: (width, height) 캐릭터 크기
        margin: 여백 픽셀

    Returns:
        (x, y) 좌표
    """
    bg_w, bg_h = bg_size
    char_w, char_h = char_size

    # 한글 프리셋
    presets = {
        # 상단 행
        "좌상단": (margin, margin),
        "상단 중앙": ((bg_w - char_w) // 2, margin),
        "우상단": (bg_w - char_w - margin, margin),
        # 중간 행
        "좌측 중앙": (margin, (bg_h - char_h) // 2),
        "정중앙": ((bg_w - char_w) // 2, (bg_h - char_h) // 2),
        "우측 중앙": (bg_w - char_w - margin, (bg_h - char_h) // 2),
        # 하단 행
        "좌하단": (margin, bg_h - char_h - margin),
        "하단 중앙": ((bg_w - char_w) // 2, bg_h - char_h - margin),
        "우하단": (bg_w - char_w - margin, bg_h - char_h - margin),
        # 레거시 호환
        "왼쪽 상단": (margin, margin),
        "오른쪽 상단": (bg_w - char_w - margin, margin),
        "왼쪽 하단": (margin, bg_h - char_h - margin),
        "오른쪽 하단": (bg_w - char_w - margin, bg_h - char_h - margin),
        "중앙 하단": ((bg_w - char_w) // 2, bg_h - char_h - margin),
        "중앙": ((bg_w - char_w) // 2, (bg_h - char_h) // 2),
        "왼쪽": (margin, (bg_h - char_h) // 2),
        "오른쪽": (bg_w - char_w - margin, (bg_h - char_h) // 2),
    }

    # 영문 프리셋 매핑
    english_presets = {
        "top_left": "좌상단",
        "top_center": "상단 중앙",
        "top_right": "우상단",
        "middle_left": "좌측 중앙",
        "middle_center": "정중앙",
        "middle_right": "우측 중앙",
        "bottom_left": "좌하단",
        "bottom_center": "하단 중앙",
        "bottom_right": "우하단",
        "left": "좌하단",
        "center": "하단 중앙",
        "right": "우하단",
    }

    # 영문이면 한글로 변환
    if preset in english_presets:
        preset = english_presets[preset]

    return presets.get(preset, presets["우하단"])


def get_all_position_presets() -> Dict[str, str]:
    """
    모든 위치 프리셋 목록 반환 (UI 표시용)

    Returns:
        {"top_left": "↖️ 좌상단", ...}
    """
    return {
        "top_left": "↖️ 좌상단",
        "top_center": "⬆️ 상단 중앙",
        "top_right": "↗️ 우상단",
        "middle_left": "⬅️ 좌측 중앙",
        "middle_center": "⏺️ 정중앙",
        "middle_right": "➡️ 우측 중앙",
        "bottom_left": "↙️ 좌하단",
        "bottom_center": "⬇️ 하단 중앙",
        "bottom_right": "↘️ 우하단",
    }


def get_size_presets() -> Dict[str, int]:
    """
    크기 프리셋 목록 반환

    Returns:
        {"아주 작게": 10, "작게": 20, ...}
    """
    return {
        "아주 작게": 10,
        "작게": 20,
        "보통": 30,
        "크게": 40,
        "아주 크게": 50,
        "최대": 60,
    }
