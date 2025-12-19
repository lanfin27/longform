"""
합성 유틸리티 함수들

이미지 합성, 변환, 저장 관련 유틸리티

사용법:
    from utils.composite_utils import (
        composite_with_placements,
        save_composite_result,
        load_and_resize_image
    )
"""

import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
from PIL import Image
import io
import base64


def load_and_resize_image(
    image_path: str,
    max_size: Optional[Tuple[int, int]] = None
) -> Optional[Image.Image]:
    """
    이미지 로드 및 리사이즈

    Args:
        image_path: 이미지 경로
        max_size: 최대 크기 (width, height)

    Returns:
        PIL Image 또는 None
    """
    try:
        if not os.path.exists(image_path):
            return None

        img = Image.open(image_path)

        # RGBA로 변환 (투명도 유지)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # 리사이즈
        if max_size:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        return img
    except Exception as e:
        print(f"이미지 로드 실패: {image_path} - {e}")
        return None


def composite_with_placements(
    background_path: str,
    placements: List[Dict],
    output_size: Optional[Tuple[int, int]] = None
) -> Optional[Image.Image]:
    """
    배치 정보를 기반으로 이미지 합성

    Args:
        background_path: 배경 이미지 경로
        placements: 캐릭터 배치 정보 리스트
            [{"image_path": str, "x": float, "y": float, "scale": float, "z_index": int}, ...]
        output_size: 출력 크기 (None이면 배경 크기 유지)

    Returns:
        합성된 PIL Image
    """
    # 배경 로드
    try:
        background = Image.open(background_path)
        if background.mode != 'RGBA':
            background = background.convert('RGBA')
    except Exception as e:
        print(f"배경 로드 실패: {e}")
        return None

    # 출력 크기 설정
    if output_size:
        background = background.resize(output_size, Image.Resampling.LANCZOS)

    bg_width, bg_height = background.size

    # z_index 순으로 정렬 (낮은 것부터)
    sorted_placements = sorted(
        [p for p in placements if p.get("visible", True)],
        key=lambda p: p.get("z_index", 0)
    )

    # 캐릭터 합성
    for placement in sorted_placements:
        char_path = placement.get("image_path", "")
        if not char_path or not os.path.exists(char_path):
            continue

        try:
            char_img = Image.open(char_path)
            if char_img.mode != 'RGBA':
                char_img = char_img.convert('RGBA')

            # 크기 조정
            scale = placement.get("scale", 1.0)
            new_width = int(char_img.width * scale)
            new_height = int(char_img.height * scale)

            if new_width > 0 and new_height > 0:
                char_img = char_img.resize(
                    (new_width, new_height),
                    Image.Resampling.LANCZOS
                )

            # 좌우 반전 (flip_x)
            if placement.get("flip_x", False):
                char_img = char_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

            # 위치 계산 (비율 -> 픽셀, 중앙 기준)
            x = placement.get("x", 0.5)
            y = placement.get("y", 0.5)

            paste_x = int(x * bg_width - new_width / 2)
            paste_y = int(y * bg_height - new_height / 2)

            # 합성 (알파 채널 유지)
            background.paste(char_img, (paste_x, paste_y), char_img)

        except Exception as e:
            print(f"캐릭터 합성 실패: {char_path} - {e}")
            continue

    return background


def save_composite_result(
    image: Image.Image,
    output_path: str,
    format: str = "PNG",
    quality: int = 95
) -> bool:
    """
    합성 결과 저장

    Args:
        image: PIL Image
        output_path: 저장 경로
        format: 이미지 포맷 (PNG, JPEG, WEBP)
        quality: JPEG/WEBP 품질 (1-100)

    Returns:
        성공 여부
    """
    try:
        # 디렉토리 생성
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 포맷에 따른 저장
        if format.upper() == "JPEG":
            # JPEG는 RGBA 불가 -> RGB 변환
            if image.mode == 'RGBA':
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[3])
                image = rgb_image
            image.save(output_path, format="JPEG", quality=quality)
        elif format.upper() == "WEBP":
            image.save(output_path, format="WEBP", quality=quality)
        else:
            image.save(output_path, format="PNG")

        return True
    except Exception as e:
        print(f"저장 실패: {output_path} - {e}")
        return False


def image_to_data_uri(image: Union[Image.Image, str]) -> str:
    """
    이미지를 data URI로 변환

    Args:
        image: PIL Image 또는 이미지 경로

    Returns:
        data URI 문자열
    """
    try:
        if isinstance(image, str):
            image = Image.open(image)

        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        b64 = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"Data URI 변환 실패: {e}")
        return ""


def create_thumbnail(
    image_path: str,
    size: Tuple[int, int] = (200, 200)
) -> Optional[Image.Image]:
    """
    썸네일 생성

    Args:
        image_path: 이미지 경로
        size: 썸네일 크기

    Returns:
        썸네일 이미지
    """
    try:
        img = Image.open(image_path)
        img.thumbnail(size, Image.Resampling.LANCZOS)
        return img
    except Exception:
        return None


def calculate_fit_scale(
    image_size: Tuple[int, int],
    container_size: Tuple[int, int],
    mode: str = "contain"
) -> float:
    """
    이미지가 컨테이너에 맞는 스케일 계산

    Args:
        image_size: 이미지 크기 (width, height)
        container_size: 컨테이너 크기 (width, height)
        mode: "contain" (전체 표시) 또는 "cover" (꽉 채우기)

    Returns:
        스케일 값
    """
    w_scale = container_size[0] / image_size[0]
    h_scale = container_size[1] / image_size[1]

    if mode == "contain":
        return min(w_scale, h_scale)
    else:  # cover
        return max(w_scale, h_scale)


def get_character_bounds(
    placement: Dict,
    background_size: Tuple[int, int],
    character_size: Tuple[int, int]
) -> Tuple[int, int, int, int]:
    """
    캐릭터의 실제 경계 박스 계산

    Args:
        placement: 배치 정보
        background_size: 배경 크기
        character_size: 원본 캐릭터 이미지 크기

    Returns:
        (left, top, right, bottom)
    """
    scale = placement.get("scale", 1.0)
    x = placement.get("x", 0.5)
    y = placement.get("y", 0.5)

    scaled_width = int(character_size[0] * scale)
    scaled_height = int(character_size[1] * scale)

    center_x = int(x * background_size[0])
    center_y = int(y * background_size[1])

    left = center_x - scaled_width // 2
    top = center_y - scaled_height // 2
    right = left + scaled_width
    bottom = top + scaled_height

    return (left, top, right, bottom)


def check_overlap(
    bounds1: Tuple[int, int, int, int],
    bounds2: Tuple[int, int, int, int]
) -> bool:
    """
    두 경계 박스의 겹침 여부 확인

    Args:
        bounds1: (left, top, right, bottom)
        bounds2: (left, top, right, bottom)

    Returns:
        겹치면 True
    """
    return not (
        bounds1[2] < bounds2[0] or  # 1이 2의 왼쪽
        bounds1[0] > bounds2[2] or  # 1이 2의 오른쪽
        bounds1[3] < bounds2[1] or  # 1이 2의 위
        bounds1[1] > bounds2[3]     # 1이 2의 아래
    )


def auto_adjust_overlapping(
    placements: List[Dict],
    background_size: Tuple[int, int],
    min_gap: int = 20
) -> List[Dict]:
    """
    겹치는 캐릭터 자동 조정

    Args:
        placements: 배치 정보 리스트
        background_size: 배경 크기
        min_gap: 최소 간격 (픽셀)

    Returns:
        조정된 배치 리스트
    """
    # 간단한 구현: 겹치면 좌우로 분산
    adjusted = [p.copy() for p in placements]
    n = len(adjusted)

    if n <= 1:
        return adjusted

    # 각 캐릭터를 균등 분배
    for i, p in enumerate(adjusted):
        p["x"] = 0.15 + (0.7 * i / (n - 1)) if n > 1 else 0.5

    return adjusted
