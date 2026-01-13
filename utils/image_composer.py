# -*- coding: utf-8 -*-
"""
실사 이미지 합성 유틸리티
- 배경 이미지 + 실사 이미지 합성
- 정중앙 배치
- 크기 조절
- 투명도 설정
"""

from PIL import Image, ImageFilter
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import io


# 캔버스 크기 (유튜브 16:9)
CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720


# 실사 이미지 크기 프리셋
IMAGE_SIZE_PRESETS = {
    'small': {
        'name': '작게 (40%)',
        'scale': 0.4,
        'max_width': 512,
        'max_height': 288
    },
    'medium': {
        'name': '보통 (60%)',
        'scale': 0.6,
        'max_width': 768,
        'max_height': 432
    },
    'large': {
        'name': '크게 (80%)',
        'scale': 0.8,
        'max_width': 1024,
        'max_height': 576
    },
    'full': {
        'name': '전체 (100%)',
        'scale': 1.0,
        'max_width': 1280,
        'max_height': 720
    },
    'custom': {
        'name': '사용자 지정',
        'scale': None,
        'max_width': None,
        'max_height': None
    }
}


class ImageComposer:
    """실사 이미지 + 배경 합성 클래스"""

    def __init__(
        self,
        canvas_width: int = CANVAS_WIDTH,
        canvas_height: int = CANVAS_HEIGHT
    ):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height

    def resize_image_to_fit(
        self,
        image: Image.Image,
        max_width: int,
        max_height: int,
        maintain_aspect: bool = True
    ) -> Image.Image:
        """
        이미지를 지정된 크기에 맞게 리사이즈 (비율 유지)
        """
        if not maintain_aspect:
            return image.resize((max_width, max_height), Image.Resampling.LANCZOS)

        # 비율 유지하며 리사이즈
        orig_width, orig_height = image.size

        # 가로/세로 중 더 큰 비율로 스케일 결정
        width_ratio = max_width / orig_width
        height_ratio = max_height / orig_height
        scale = min(width_ratio, height_ratio)

        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)

        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def resize_by_preset(
        self,
        image: Image.Image,
        preset: str = 'medium',
        custom_width: Optional[int] = None,
        custom_height: Optional[int] = None
    ) -> Image.Image:
        """
        프리셋 또는 사용자 지정 크기로 리사이즈
        """
        if preset == 'custom' and custom_width and custom_height:
            max_width = custom_width
            max_height = custom_height
        elif preset in IMAGE_SIZE_PRESETS:
            preset_data = IMAGE_SIZE_PRESETS[preset]
            max_width = preset_data['max_width']
            max_height = preset_data['max_height']
        else:
            # 기본값: medium
            max_width = 768
            max_height = 432

        return self.resize_image_to_fit(image, max_width, max_height)

    def apply_opacity(
        self,
        image: Image.Image,
        opacity: float
    ) -> Image.Image:
        """
        이미지에 투명도 적용

        Args:
            image: 원본 이미지
            opacity: 0.0 (완전 투명) ~ 1.0 (불투명)
        """
        if opacity >= 1.0:
            return image

        # RGBA로 변환
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # 알파 채널 조정
        r, g, b, a = image.split()
        a = a.point(lambda x: int(x * opacity))

        return Image.merge('RGBA', (r, g, b, a))

    def center_image_on_canvas(
        self,
        foreground: Image.Image,
        background: Optional[Image.Image] = None,
        bg_opacity: float = 1.0,
        bg_color: Tuple[int, int, int] = (255, 255, 255)
    ) -> Image.Image:
        """
        실사 이미지를 캔버스 정중앙에 배치

        Args:
            foreground: 실사 이미지 (이미 리사이즈됨)
            background: 배경 이미지 (없으면 단색 배경)
            bg_opacity: 배경 이미지 투명도
            bg_color: 배경 단색 (배경 이미지 없을 때)
        """
        # 캔버스 생성
        canvas = Image.new('RGBA', (self.canvas_width, self.canvas_height), (*bg_color, 255))

        # 배경 이미지 적용
        if background:
            # 배경 이미지를 캔버스 크기에 맞게 리사이즈
            bg_resized = background.resize(
                (self.canvas_width, self.canvas_height),
                Image.Resampling.LANCZOS
            )

            # RGBA로 변환
            if bg_resized.mode != 'RGBA':
                bg_resized = bg_resized.convert('RGBA')

            # 투명도 적용
            if bg_opacity < 1.0:
                bg_resized = self.apply_opacity(bg_resized, bg_opacity)

            # 배경 합성
            canvas = Image.alpha_composite(canvas, bg_resized)

        # 실사 이미지 정중앙 배치
        fg_width, fg_height = foreground.size
        x = (self.canvas_width - fg_width) // 2
        y = (self.canvas_height - fg_height) // 2

        # 실사 이미지 RGBA 변환
        if foreground.mode != 'RGBA':
            foreground = foreground.convert('RGBA')

        # 실사 이미지 합성
        canvas.paste(foreground, (x, y), foreground)

        return canvas

    def compose_scene_image(
        self,
        real_image_path: str,
        background_image_path: Optional[str] = None,
        size_preset: str = 'medium',
        custom_width: Optional[int] = None,
        custom_height: Optional[int] = None,
        bg_opacity: float = 0.3,
        bg_color: Tuple[int, int, int] = (30, 30, 30),
        add_shadow: bool = True,
        add_border: bool = True,
        border_width: int = 3,
        border_color: Tuple[int, int, int] = (50, 50, 50)
    ) -> Image.Image:
        """
        씬용 최종 이미지 합성

        Args:
            real_image_path: 실사 이미지 경로
            background_image_path: 배경 이미지 경로 (선택)
            size_preset: 크기 프리셋 ('small', 'medium', 'large', 'full', 'custom')
            custom_width: 사용자 지정 너비 (preset='custom'일 때)
            custom_height: 사용자 지정 높이 (preset='custom'일 때)
            bg_opacity: 배경 투명도 (0.0~1.0)
            bg_color: 배경 기본 색상 (배경 이미지 없을 때)
            add_shadow: 실사 이미지에 그림자 효과 추가
            add_border: 실사 이미지에 테두리 추가
            border_width: 테두리 두께
            border_color: 테두리 색상
        """
        # 실사 이미지 로드
        real_image = Image.open(real_image_path)
        if real_image.mode != 'RGBA':
            real_image = real_image.convert('RGBA')

        # 크기 조절
        real_image = self.resize_by_preset(
            real_image,
            size_preset,
            custom_width,
            custom_height
        )

        # 테두리 추가
        if add_border and border_width > 0:
            real_image = self._add_border(real_image, border_width, border_color)

        # 그림자 효과
        if add_shadow:
            real_image = self._add_shadow(real_image)

        # 배경 이미지 로드
        background = None
        if background_image_path and Path(background_image_path).exists():
            background = Image.open(background_image_path)
            if background.mode != 'RGBA':
                background = background.convert('RGBA')

        # 합성
        result = self.center_image_on_canvas(
            foreground=real_image,
            background=background,
            bg_opacity=bg_opacity,
            bg_color=bg_color
        )

        # RGB로 변환 (저장용)
        if result.mode == 'RGBA':
            # 배경색으로 알파 채널 제거
            rgb_result = Image.new('RGB', result.size, bg_color)
            rgb_result.paste(result, mask=result.split()[3])
            return rgb_result

        return result

    def _add_border(
        self,
        image: Image.Image,
        width: int = 3,
        color: Tuple[int, int, int] = (50, 50, 50)
    ) -> Image.Image:
        """이미지에 테두리 추가"""
        # 테두리를 위한 새 이미지 (기존 크기 + 테두리)
        new_width = image.size[0] + width * 2
        new_height = image.size[1] + width * 2

        bordered = Image.new('RGBA', (new_width, new_height), (*color, 255))

        if image.mode == 'RGBA':
            bordered.paste(image, (width, width), image)
        else:
            bordered.paste(image, (width, width))

        return bordered

    def _add_shadow(
        self,
        image: Image.Image,
        offset: Tuple[int, int] = (8, 8),
        blur_radius: int = 15,
        shadow_color: Tuple[int, int, int, int] = (0, 0, 0, 100)
    ) -> Image.Image:
        """이미지에 그림자 효과 추가"""
        # 그림자용 새 캔버스
        shadow_canvas = Image.new('RGBA',
            (image.size[0] + abs(offset[0]) + blur_radius * 2,
             image.size[1] + abs(offset[1]) + blur_radius * 2),
            (0, 0, 0, 0)
        )

        # 그림자 생성
        shadow = Image.new('RGBA', image.size, shadow_color)

        # 이미지가 RGBA면 알파 채널을 그림자에 적용
        if image.mode == 'RGBA':
            shadow.putalpha(image.split()[3])

        # 그림자 위치
        shadow_x = blur_radius + max(0, offset[0])
        shadow_y = blur_radius + max(0, offset[1])
        shadow_canvas.paste(shadow, (shadow_x, shadow_y))

        # 블러 적용
        shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(blur_radius))

        # 원본 이미지 위치
        image_x = blur_radius + max(0, -offset[0])
        image_y = blur_radius + max(0, -offset[1])

        # 원본 이미지 합성
        if image.mode == 'RGBA':
            shadow_canvas.paste(image, (image_x, image_y), image)
        else:
            shadow_canvas.paste(image, (image_x, image_y))

        return shadow_canvas


def compose_real_image_scene(
    real_image_path: str,
    output_path: str,
    background_image_path: Optional[str] = None,
    size_preset: str = 'medium',
    custom_width: Optional[int] = None,
    custom_height: Optional[int] = None,
    bg_opacity: float = 0.3,
    bg_color: Tuple[int, int, int] = (30, 30, 30),
    add_shadow: bool = True,
    add_border: bool = True,
    border_width: int = 3,
    quality: int = 95
) -> str:
    """
    실사 이미지 씬 합성 및 저장 (편의 함수)

    Returns:
        저장된 파일 경로
    """
    composer = ImageComposer()

    result = composer.compose_scene_image(
        real_image_path=real_image_path,
        background_image_path=background_image_path,
        size_preset=size_preset,
        custom_width=custom_width,
        custom_height=custom_height,
        bg_opacity=bg_opacity,
        bg_color=bg_color,
        add_shadow=add_shadow,
        add_border=add_border,
        border_width=border_width
    )

    # 저장
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    result.save(output, quality=quality)

    return str(output)


def batch_compose_real_images(
    mappings: dict,
    image_folder: str,
    output_folder: str,
    background_image_path: Optional[str] = None,
    size_preset: str = 'medium',
    bg_opacity: float = 0.3,
    progress_callback=None,
    **kwargs
) -> dict:
    """
    여러 씬의 실사 이미지 일괄 합성

    Args:
        mappings: {씬번호: {'image': 파일명, ...}} 딕셔너리
        image_folder: 원본 실사 이미지 폴더
        output_folder: 합성 결과 저장 폴더
        background_image_path: 일괄 적용할 배경 이미지
        size_preset: 크기 프리셋
        bg_opacity: 배경 투명도
        progress_callback: 진행률 콜백 (current, total)

    Returns:
        {씬번호: {'output_path': 경로, 'status': 상태}} 딕셔너리
    """
    results = {}
    composer = ImageComposer()

    image_folder = Path(image_folder)
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    total = len(mappings)

    for idx, (scene_num, data) in enumerate(sorted(mappings.items()), 1):
        image_name = data.get('image')
        if not image_name:
            continue

        real_image_path = image_folder / image_name

        # 진행률 콜백
        if progress_callback:
            progress_callback(idx, total)

        if not real_image_path.exists():
            results[scene_num] = {
                'status': 'error',
                'message': f'파일 없음: {image_name}'
            }
            continue

        try:
            # 출력 파일명: 씬번호_scene_composed.jpg
            output_filename = f"{int(scene_num):03d}_scene_composed.jpg"
            output_path = output_folder / output_filename

            result = composer.compose_scene_image(
                real_image_path=str(real_image_path),
                background_image_path=background_image_path,
                size_preset=size_preset,
                bg_opacity=bg_opacity,
                **kwargs
            )

            result.save(output_path, quality=95)

            results[scene_num] = {
                'status': 'success',
                'output_path': str(output_path),
                'source_image': image_name
            }

            print(f"[ImageComposer] 씬 {scene_num} 합성 완료: {output_filename}", flush=True)

        except Exception as e:
            results[scene_num] = {
                'status': 'error',
                'message': str(e)
            }
            print(f"[ImageComposer] 씬 {scene_num} 합성 실패: {e}", flush=True)

    return results


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """HEX 색상 코드를 RGB 튜플로 변환"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


# 테스트용
if __name__ == "__main__":
    composer = ImageComposer()
    print("ImageComposer 테스트 완료")
    print(f"캔버스 크기: {composer.canvas_width}x{composer.canvas_height}")
    print(f"크기 프리셋: {list(IMAGE_SIZE_PRESETS.keys())}")
