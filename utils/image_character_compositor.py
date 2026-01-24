# -*- coding: utf-8 -*-
"""
utils/image_character_compositor.py
이미지에 캐릭터 합성 모듈

기능:
1. 씬 이미지에 대표 캐릭터 합성
2. 위치/크기/투명도 조절
3. 일괄 합성 처리
4. PIL 기반 합성

작성: 2025-01
"""

import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable
from dataclasses import dataclass
from enum import Enum

try:
    from PIL import Image, ImageDraw, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[ImageCharacterCompositor] PIL 없음 - pip install pillow")


class ImagePositionPreset(Enum):
    """이미지 캐릭터 위치 프리셋"""
    LEFT_BOTTOM = "left_bottom"
    RIGHT_BOTTOM = "right_bottom"
    LEFT_CENTER = "left_center"
    RIGHT_CENTER = "right_center"
    CENTER_BOTTOM = "center_bottom"
    CUSTOM = "custom"


@dataclass
class ImageCharacterPosition:
    """캐릭터 위치 및 크기 설정"""
    preset: str = "right_bottom"
    scale: float = 0.3  # 배경 대비 크기 비율 (0.1 ~ 0.6)
    margin_x: int = 20  # 좌우 여백 (픽셀)
    margin_y: int = 20  # 상하 여백 (픽셀)
    custom_x: int = 0   # 커스텀 X 좌표
    custom_y: int = 0   # 커스텀 Y 좌표
    opacity: float = 1.0  # 투명도 (0.0 ~ 1.0)

    def calculate_position(
        self,
        bg_width: int,
        bg_height: int,
        char_width: int,
        char_height: int
    ) -> Tuple[int, int]:
        """
        최종 합성 좌표 계산

        Returns:
            (x, y) 좌표
        """
        # 스케일 적용된 캐릭터 크기
        scaled_w = int(char_width * self.scale)
        scaled_h = int(char_height * self.scale)

        preset = self.preset.lower()

        if preset == "left_bottom":
            x = self.margin_x
            y = bg_height - scaled_h - self.margin_y
        elif preset == "right_bottom":
            x = bg_width - scaled_w - self.margin_x
            y = bg_height - scaled_h - self.margin_y
        elif preset == "left_center":
            x = self.margin_x
            y = (bg_height - scaled_h) // 2
        elif preset == "right_center":
            x = bg_width - scaled_w - self.margin_x
            y = (bg_height - scaled_h) // 2
        elif preset == "center_bottom":
            x = (bg_width - scaled_w) // 2
            y = bg_height - scaled_h - self.margin_y
        elif preset == "custom":
            x = self.custom_x
            y = self.custom_y
        else:
            # 기본값: 오른쪽 하단
            x = bg_width - scaled_w - self.margin_x
            y = bg_height - scaled_h - self.margin_y

        return x, y


@dataclass
class ImageCompositeConfig:
    """합성 설정"""
    background_path: str
    character_path: str
    output_path: str
    position: ImageCharacterPosition = None
    add_shadow: bool = True
    shadow_offset: Tuple[int, int] = (5, 5)
    shadow_blur: int = 10

    def __post_init__(self):
        if self.position is None:
            self.position = ImageCharacterPosition()


class ImageCharacterCompositor:
    """이미지 캐릭터 합성기"""

    def __init__(self, output_dir: str = "outputs/composed_images"):
        """
        Args:
            output_dir: 합성된 이미지 출력 디렉토리
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL 필요: pip install pillow")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        print(f"[ImageCharacterCompositor] 초기화 완료 - 출력 디렉토리: {self.output_dir}")

    def _add_shadow(
        self,
        image: 'Image.Image',
        offset: Tuple[int, int] = (5, 5),
        blur_radius: int = 10,
        shadow_color: Tuple[int, int, int, int] = (0, 0, 0, 100)
    ) -> 'Image.Image':
        """
        이미지에 그림자 추가

        Args:
            image: 원본 이미지 (RGBA)
            offset: 그림자 오프셋 (x, y)
            blur_radius: 블러 반경
            shadow_color: 그림자 색상 (R, G, B, A)

        Returns:
            그림자가 추가된 이미지
        """
        # 그림자 레이어 생성
        shadow = Image.new('RGBA', image.size, (0, 0, 0, 0))

        # 원본의 알파 채널 추출
        if image.mode == 'RGBA':
            alpha = image.split()[3]
        else:
            alpha = Image.new('L', image.size, 255)

        # 그림자 색상으로 채우기
        shadow_fill = Image.new('RGBA', image.size, shadow_color)
        shadow.paste(shadow_fill, mask=alpha)

        # 블러 적용
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

        # 결과 이미지 (그림자 + 원본)
        # 캔버스 크기 확장 (그림자 오프셋 + 블러 반경)
        extra = blur_radius * 2 + max(abs(offset[0]), abs(offset[1]))
        result = Image.new('RGBA', (image.width + extra, image.height + extra), (0, 0, 0, 0))

        # 그림자 배치
        shadow_pos = (extra // 2 + offset[0], extra // 2 + offset[1])
        result.paste(shadow, shadow_pos, shadow)

        # 원본 배치
        img_pos = (extra // 2, extra // 2)
        result.paste(image, img_pos, image)

        # 원본 크기로 크롭 (중앙 정렬)
        crop_x = extra // 2
        crop_y = extra // 2
        result = result.crop((crop_x, crop_y, crop_x + image.width, crop_y + image.height))

        return result

    def compose_single(
        self,
        background_path: str,
        character_path: str,
        output_path: str = None,
        position: ImageCharacterPosition = None,
        add_shadow: bool = True
    ) -> Tuple[bool, str]:
        """
        단일 이미지에 캐릭터 합성

        Args:
            background_path: 배경 이미지 경로
            character_path: 캐릭터 PNG 이미지 경로 (투명 배경)
            output_path: 출력 경로 (None이면 자동 생성)
            position: 위치 설정
            add_shadow: 캐릭터에 그림자 추가

        Returns:
            (success, output_path or error_message)
        """
        # 파일 존재 확인
        if not os.path.exists(background_path):
            return False, f"배경 이미지 없음: {background_path}"

        if not os.path.exists(character_path):
            return False, f"캐릭터 이미지 없음: {character_path}"

        # 기본값 설정
        if position is None:
            position = ImageCharacterPosition()

        if output_path is None:
            bg_name = Path(background_path).stem
            char_name = Path(character_path).stem
            output_path = str(self.output_dir / f"{bg_name}_with_{char_name}.png")

        try:
            # 이미지 로드
            background = Image.open(background_path).convert("RGBA")
            character = Image.open(character_path).convert("RGBA")

            bg_w, bg_h = background.size
            char_w, char_h = character.size

            print(f"[ImageCompositor] 합성 시작:")
            print(f"  배경: {bg_w}x{bg_h}")
            print(f"  캐릭터: {char_w}x{char_h}")

            # 캐릭터 크기 조절
            new_height = int(bg_h * position.scale)
            scale_ratio = new_height / char_h
            new_width = int(char_w * scale_ratio)

            character = character.resize((new_width, new_height), Image.Resampling.LANCZOS)
            char_w, char_h = character.size

            print(f"  스케일 후: {char_w}x{char_h} (비율: {position.scale:.1%})")

            # 그림자 추가
            if add_shadow:
                character = self._add_shadow(character)
                char_w, char_h = character.size

            # 투명도 적용
            if position.opacity < 1.0:
                alpha = character.split()[3]
                alpha = alpha.point(lambda p: int(p * position.opacity))
                character.putalpha(alpha)

            # 위치 계산
            x, y = position.calculate_position(bg_w, bg_h, char_w, char_h)
            print(f"  위치: ({x}, {y})")

            # 합성
            # 배경 복사본 생성
            result = background.copy()

            # 캐릭터 붙이기 (알파 마스크 사용)
            result.paste(character, (x, y), character)

            # 저장
            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # PNG로 저장 (투명도 유지)
            if output_path.lower().endswith('.png'):
                result.save(output_path, "PNG")
            else:
                # JPG 등은 RGB로 변환
                result_rgb = result.convert("RGB")
                result_rgb.save(output_path, quality=95)

            print(f"[ImageCompositor] 합성 완료: {output_path}")
            return True, output_path

        except Exception as e:
            print(f"[ImageCompositor] 합성 실패: {e}")
            return False, str(e)

    def compose_batch(
        self,
        configs: List[ImageCompositeConfig],
        progress_callback: Callable[[int, int, str], None] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        여러 이미지 일괄 합성

        Args:
            configs: 합성 설정 리스트
            progress_callback: 진행 콜백 (current, total, message)

        Returns:
            {background_path: (success, output_path or error), ...}
        """
        results = {}
        total = len(configs)

        for i, config in enumerate(configs):
            if progress_callback:
                progress_callback(i + 1, total, f"합성 중: {Path(config.background_path).name}")

            success, result = self.compose_single(
                background_path=config.background_path,
                character_path=config.character_path,
                output_path=config.output_path,
                position=config.position,
                add_shadow=config.add_shadow
            )

            results[config.background_path] = (success, result)

        if progress_callback:
            success_count = sum(1 for s, _ in results.values() if s)
            progress_callback(total, total, f"완료: {success_count}/{total} 성공")

        return results

    def compose_scene_with_character(
        self,
        scene_id: int,
        scene_image_path: str,
        character_image_path: str,
        position_preset: str = "right_bottom",
        scale: float = 0.3,
        add_shadow: bool = True
    ) -> Tuple[bool, str]:
        """
        특정 씬에 캐릭터 합성 (편의 메서드)

        Args:
            scene_id: 씬 번호
            scene_image_path: 씬 이미지 경로
            character_image_path: 캐릭터 PNG 경로
            position_preset: 위치 프리셋
            scale: 크기 비율
            add_shadow: 그림자 추가

        Returns:
            (success, output_path or error)
        """
        position = ImageCharacterPosition(preset=position_preset, scale=scale)

        # 원본 파일 확장자 유지
        ext = Path(scene_image_path).suffix or ".png"
        output_name = f"scene_{scene_id:03d}_with_char{ext}"
        output_path = str(self.output_dir / output_name)

        return self.compose_single(
            background_path=scene_image_path,
            character_path=character_image_path,
            output_path=output_path,
            position=position,
            add_shadow=add_shadow
        )

    def compose_all_scenes(
        self,
        scenes: List[Dict],
        character_image_path: str,
        image_key: str = "image_path",
        position_preset: str = "right_bottom",
        scale: float = 0.3,
        progress_callback: Callable[[int, int, str], None] = None
    ) -> Dict[int, Tuple[bool, str]]:
        """
        모든 씬에 캐릭터 일괄 합성

        Args:
            scenes: 씬 데이터 리스트
            character_image_path: 캐릭터 이미지 경로
            image_key: 씬 이미지 경로 키
            position_preset: 위치 프리셋
            scale: 크기 비율
            progress_callback: 진행 콜백

        Returns:
            {scene_id: (success, output_path or error), ...}
        """
        results = {}
        total = len(scenes)

        for i, scene in enumerate(scenes):
            scene_id = scene.get("scene_id") or scene.get("id", i + 1)
            image_path = scene.get(image_key) or scene.get("composite_path") or scene.get("background_image")

            if progress_callback:
                progress_callback(i + 1, total, f"씬 {scene_id} 합성 중")

            if not image_path or not os.path.exists(image_path):
                results[scene_id] = (False, "이미지 없음")
                continue

            success, result = self.compose_scene_with_character(
                scene_id=scene_id,
                scene_image_path=image_path,
                character_image_path=character_image_path,
                position_preset=position_preset,
                scale=scale
            )

            results[scene_id] = (success, result)

        if progress_callback:
            success_count = sum(1 for s, _ in results.values() if s)
            progress_callback(total, total, f"완료: {success_count}/{total} 성공")

        return results


# ============================================================
# 유틸리티 함수
# ============================================================

def get_image_position_presets() -> Dict[str, Dict]:
    """위치 프리셋 목록 반환"""
    return {
        "left_bottom": {
            "name": "↙️ 좌하단",
            "desc": "화면 왼쪽 하단에 배치",
            "default": False
        },
        "right_bottom": {
            "name": "↘️ 우하단",
            "desc": "화면 오른쪽 하단에 배치 (기본)",
            "default": True
        },
        "left_center": {
            "name": "⬅️ 좌측 중앙",
            "desc": "화면 왼쪽 중앙에 배치",
            "default": False
        },
        "right_center": {
            "name": "➡️ 우측 중앙",
            "desc": "화면 오른쪽 중앙에 배치",
            "default": False
        },
        "center_bottom": {
            "name": "⬇️ 하단 중앙",
            "desc": "화면 하단 중앙에 배치",
            "default": False
        }
    }


def get_scale_presets() -> Dict[str, float]:
    """크기 프리셋 목록 반환"""
    return {
        "아주 작게 (15%)": 0.15,
        "작게 (20%)": 0.20,
        "보통 (25%)": 0.25,
        "약간 크게 (30%)": 0.30,
        "크게 (35%)": 0.35,
        "아주 크게 (40%)": 0.40,
    }


def analyze_image_for_character_placement(
    image_path: str
) -> Dict:
    """
    이미지 분석하여 캐릭터 배치 최적 위치 추천

    Args:
        image_path: 분석할 이미지 경로

    Returns:
        {
            "recommended_position": "right_bottom",
            "recommended_scale": 0.3,
            "reason": "...",
            "brightness_map": {...}
        }
    """
    if not PIL_AVAILABLE:
        return {
            "recommended_position": "right_bottom",
            "recommended_scale": 0.3,
            "reason": "PIL 없음 - 기본값 사용"
        }

    try:
        import numpy as np

        img = Image.open(image_path).convert("L")  # 그레이스케일
        width, height = img.size

        # 3x3 영역 분석
        regions = {}
        region_names = [
            ["top_left", "top_center", "top_right"],
            ["middle_left", "middle_center", "middle_right"],
            ["bottom_left", "bottom_center", "bottom_right"]
        ]

        img_array = np.array(img)
        h_third = height // 3
        w_third = width // 3

        for row in range(3):
            for col in range(3):
                y1 = row * h_third
                y2 = (row + 1) * h_third
                x1 = col * w_third
                x2 = (col + 1) * w_third

                region = img_array[y1:y2, x1:x2]
                variance = np.var(region)
                brightness = np.mean(region)

                name = region_names[row][col]
                # 점수: 낮은 분산 + 적절한 밝기 = 좋은 위치
                score = variance + abs(brightness - 128) * 0.5

                regions[name] = {
                    "variance": float(variance),
                    "brightness": float(brightness),
                    "score": float(score)
                }

        # 하단 영역 중 최적 위치 선택
        bottom_regions = {
            "left_bottom": regions["bottom_left"],
            "center_bottom": regions["bottom_center"],
            "right_bottom": regions["bottom_right"]
        }

        best_position = min(bottom_regions.items(), key=lambda x: x[1]["score"])

        # 스케일 추천 (이미지 복잡도에 따라)
        avg_variance = np.mean([r["variance"] for r in regions.values()])
        if avg_variance > 3000:
            recommended_scale = 0.25  # 복잡한 배경 -> 작게
        elif avg_variance > 1500:
            recommended_scale = 0.30
        else:
            recommended_scale = 0.35  # 단순한 배경 -> 크게

        return {
            "recommended_position": best_position[0],
            "recommended_scale": recommended_scale,
            "reason": f"하단 영역 중 가장 균일한 곳 (분산: {best_position[1]['variance']:.0f})",
            "regions": regions
        }

    except Exception as e:
        return {
            "recommended_position": "right_bottom",
            "recommended_scale": 0.3,
            "reason": f"분석 실패: {e}"
        }


def quick_compose(
    background_path: str,
    character_path: str,
    output_path: str = None,
    position: str = "right_bottom",
    scale: float = 0.3
) -> Tuple[bool, str]:
    """
    빠른 합성 (단일 함수)

    Args:
        background_path: 배경 이미지 경로
        character_path: 캐릭터 이미지 경로
        output_path: 출력 경로 (None이면 자동)
        position: 위치 프리셋
        scale: 크기 비율

    Returns:
        (success, output_path or error)
    """
    compositor = ImageCharacterCompositor()
    pos = ImageCharacterPosition(preset=position, scale=scale)

    return compositor.compose_single(
        background_path=background_path,
        character_path=character_path,
        output_path=output_path,
        position=pos
    )


if __name__ == "__main__":
    print("이미지 캐릭터 합성 모듈")
    print("=" * 50)
    print("\n위치 프리셋:")
    for key, value in get_image_position_presets().items():
        print(f"  {key}: {value['name']}")

    print("\n크기 프리셋:")
    for key, value in get_scale_presets().items():
        print(f"  {key}: {value}")
