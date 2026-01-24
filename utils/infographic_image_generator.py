# -*- coding: utf-8 -*-
"""
인포그래픽용 이미지 생성기 (v2.0)

기능:
- 모서리/가장자리에 요소 배치
- 가운데 공간 확보 (인포그래픽용)
- 다양한 레이아웃 지원
- 인포그래픽 + 이미지 합성

v2.0: 한글/아시아 텍스트 생성 방지 강화
- prompt_sanitizer 사용하여 텍스트 키워드 제거
- 강력한 텍스트 차단 프롬프트 추가
"""

import gc
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum

from utils.prompt_sanitizer import (
    sanitize_scene_prompt,
    get_text_blocking_suffix,
    get_text_blocking_negative
)


class InfographicLayout(Enum):
    """인포그래픽 이미지 레이아웃"""

    # 모서리 배치
    CORNERS = "corners"              # 4모서리에 요소 배치
    TOP_BOTTOM = "top_bottom"        # 상단/하단에 배치
    LEFT_RIGHT = "left_right"        # 좌/우에 배치

    # 특정 위치 배치
    TOP_LEFT = "top_left"            # 좌상단에 집중
    TOP_RIGHT = "top_right"          # 우상단에 집중
    BOTTOM_LEFT = "bottom_left"      # 좌하단에 집중
    BOTTOM_RIGHT = "bottom_right"    # 우하단에 집중

    # 프레임 형태
    FRAME = "frame"                  # 테두리 전체
    L_SHAPE = "l_shape"              # L자 형태


# 레이아웃별 프롬프트 지시어
LAYOUT_PROMPTS = {
    InfographicLayout.CORNERS: {
        "position": "elements positioned in all four corners, center area empty and clean",
        "composition": "corner-focused composition with clear center space for text overlay",
        "negative": "centered subject, subject in middle, text in center"
    },
    InfographicLayout.TOP_BOTTOM: {
        "position": "elements at top and bottom edges only, middle area completely empty",
        "composition": "horizontal band composition at top and bottom, clear center",
        "negative": "vertically centered subject, middle focus"
    },
    InfographicLayout.LEFT_RIGHT: {
        "position": "elements on left and right sides only, center column empty",
        "composition": "side-focused composition with clear center vertical space",
        "negative": "centered subject, horizontally centered"
    },
    InfographicLayout.TOP_LEFT: {
        "position": "main subject concentrated in top-left corner area",
        "composition": "top-left weighted composition, rest of image clean",
        "negative": "centered subject, bottom-right focus, full coverage"
    },
    InfographicLayout.TOP_RIGHT: {
        "position": "main subject concentrated in top-right corner area",
        "composition": "top-right weighted composition, rest of image clean",
        "negative": "centered subject, bottom-left focus, full coverage"
    },
    InfographicLayout.BOTTOM_LEFT: {
        "position": "main subject concentrated in bottom-left corner area",
        "composition": "bottom-left weighted composition, rest of image clean",
        "negative": "centered subject, top-right focus, full coverage"
    },
    InfographicLayout.BOTTOM_RIGHT: {
        "position": "main subject concentrated in bottom-right corner area",
        "composition": "bottom-right weighted composition, rest of image clean",
        "negative": "centered subject, top-left focus, full coverage"
    },
    InfographicLayout.FRAME: {
        "position": "elements around all edges forming a decorative frame, center completely empty",
        "composition": "frame-like border composition with hollow center for content",
        "negative": "centered subject, filled center, middle elements"
    },
    InfographicLayout.L_SHAPE: {
        "position": "elements in L-shape along bottom and left edges only",
        "composition": "L-shaped composition, top-right area completely empty",
        "negative": "centered subject, full coverage, right-top focus"
    }
}


class InfographicImageGenerator:
    """인포그래픽용 이미지 생성기"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.output_dir = self.project_path / "images" / "infographic"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_prompt(
        self,
        base_prompt: str,
        layout: InfographicLayout,
        style_prefix: str = "",
        style_suffix: str = "",
        additional_elements: List[str] = None
    ) -> Tuple[str, str]:
        """
        인포그래픽용 프롬프트 생성

        Args:
            base_prompt: 기본 이미지 프롬프트
            layout: 레이아웃 타입
            style_prefix: 스타일 프롬프트 prefix
            style_suffix: 스타일 프롬프트 suffix
            additional_elements: 추가 요소들

        Returns:
            (positive_prompt, negative_prompt)
        """

        layout_info = LAYOUT_PROMPTS.get(layout, LAYOUT_PROMPTS[InfographicLayout.CORNERS])

        # Positive 프롬프트 구성
        prompt_parts = []

        # v2.0: 텍스트 차단 지시 (맨 앞에 배치)
        prompt_parts.append("IMPORTANT: All surfaces must be completely blank with no text, signs, or writing of any kind")

        # 1. 스타일 prefix
        if style_prefix:
            prompt_parts.append(style_prefix.strip())

        # 2. 레이아웃 지시
        prompt_parts.append(layout_info["position"])
        prompt_parts.append(layout_info["composition"])

        # 3. 기본 프롬프트 - v2.0: 텍스트 키워드 제거
        if base_prompt:
            sanitized_base = sanitize_scene_prompt(base_prompt.strip())
            prompt_parts.append(sanitized_base)

        # 4. 추가 요소 - v2.0: 텍스트 키워드 제거
        if additional_elements:
            sanitized_elements = [sanitize_scene_prompt(elem) for elem in additional_elements]
            filtered_elements = [e for e in sanitized_elements if e.strip()]
            prompt_parts.extend(filtered_elements)

        # 5. 스타일 suffix
        if style_suffix:
            prompt_parts.append(style_suffix.strip())

        # 6. 인포그래픽 합성용 공통 지시
        prompt_parts.extend([
            "clean composition for overlay",
            "space for text overlay in center",
            "professional presentation style",
            "high quality"
        ])

        # v2.0: 텍스트 차단 suffix 추가
        prompt_parts.append(get_text_blocking_suffix())

        positive_prompt = ", ".join(filter(None, prompt_parts))

        # Negative 프롬프트 - v2.0: 강화된 텍스트 차단
        negative_parts = [
            layout_info["negative"],
            get_text_blocking_negative(),
            "cluttered center",
            "busy composition",
            "low quality",
            "blurry"
        ]

        negative_prompt = ", ".join(negative_parts)

        return positive_prompt, negative_prompt

    def generate_image(
        self,
        scene_id: int,
        prompt: str,
        layout: InfographicLayout,
        style: dict = None,
        api_type: str = "together",
        width: int = 1280,
        height: int = 720
    ) -> Optional[str]:
        """
        인포그래픽용 이미지 생성

        Args:
            scene_id: 씬 ID
            prompt: 기본 프롬프트
            layout: 레이아웃
            style: 스타일 설정 (prompt_prefix, prompt_suffix, negative_prompt)
            api_type: API 타입 ("together", "imagefx")
            width: 이미지 너비
            height: 이미지 높이

        Returns:
            생성된 이미지 경로
        """

        import streamlit as st

        # 스타일에서 프롬프트 추출
        style_prefix = ""
        style_suffix = ""
        style_negative = ""

        if style:
            style_prefix = style.get("prompt_prefix", "")
            style_suffix = style.get("prompt_suffix", "")
            style_negative = style.get("negative_prompt", "")

        # 프롬프트 생성
        positive_prompt, negative_prompt = self.generate_prompt(
            base_prompt=prompt,
            layout=layout,
            style_prefix=style_prefix,
            style_suffix=style_suffix
        )

        # 스타일의 negative prompt 추가
        if style_negative:
            negative_prompt = f"{style_negative}, {negative_prompt}"

        print(f"\n[InfographicGenerator] ========== 씬 {scene_id} ==========")
        print(f"[InfographicGenerator] 레이아웃: {layout.value}")
        print(f"[InfographicGenerator] 프롬프트: {positive_prompt[:150]}...")
        print(f"[InfographicGenerator] 네거티브: {negative_prompt[:100]}...")

        # 파일명
        timestamp = int(datetime.now().timestamp() * 1000)
        filename = f"infographic_scene_{scene_id:03d}_{layout.value}_{timestamp}.png"
        output_path = self.output_dir / filename

        try:
            if api_type == "imagefx":
                # ImageFX API 사용
                result = self._generate_with_imagefx(positive_prompt, output_path, width, height)
            else:
                # Together.ai API 사용 (기본)
                result = self._generate_with_together(positive_prompt, negative_prompt, output_path, width, height)

            if result:
                print(f"[InfographicGenerator] 생성 완료: {filename}")
                return str(output_path)

        except Exception as e:
            print(f"[InfographicGenerator] 생성 실패: {e}")

        return None

    def _generate_with_together(
        self,
        prompt: str,
        negative_prompt: str,
        output_path: Path,
        width: int,
        height: int
    ) -> bool:
        """Together.ai API로 이미지 생성"""

        try:
            from core.image.together_client import TogetherImageClient
            from config.settings import TOGETHER_DEFAULT_MODEL
            import streamlit as st

            client = TogetherImageClient()
            model = st.session_state.get("flux_model") or TOGETHER_DEFAULT_MODEL or "black-forest-labs/FLUX.2-dev"

            img_data = client.generate_image(
                prompt=prompt,
                model=model,
                width=width,
                height=height
            )

            if img_data:
                with open(output_path, "wb") as f:
                    f.write(img_data)
                return True

        except Exception as e:
            print(f"[InfographicGenerator] Together API 오류: {e}")

        return False

    def _generate_with_imagefx(
        self,
        prompt: str,
        output_path: Path,
        width: int,
        height: int
    ) -> bool:
        """
        Google ImageFX API로 이미지 생성

        v2.0: 최적화된 Worker Manager 사용
        """

        try:
            from utils.imagefx_client import get_optimized_imagefx_client
            from config.settings import load_imagefx_cookie
            import streamlit as st

            imagefx_cookie = st.session_state.get("imagefx_cookie", "") or load_imagefx_cookie()
            if not imagefx_cookie:
                print("[InfographicGenerator] ImageFX 쿠키 없음")
                return False

            print("[InfographicGenerator v2.0] ⚡ 최적화된 워커 사용")

            # v2.0: 최적화된 클라이언트 사용 (싱글톤 워커 재사용)
            manager = get_optimized_imagefx_client(imagefx_cookie)

            # 비율 결정
            if width > height:
                aspect_ratio = "LANDSCAPE"
            elif height > width:
                aspect_ratio = "PORTRAIT"
            else:
                aspect_ratio = "SQUARE"

            # v2.0: 이미지 생성 (워커 재사용)
            result = manager.generate_image(
                prompt=prompt,
                output_path=str(output_path),
                aspect_ratio=aspect_ratio
            )

            if result.get("success"):
                print(f"[InfographicGenerator v2.0] ✅ 이미지 저장: {output_path}")
                return True
            else:
                print(f"[InfographicGenerator v2.0] ❌ 생성 실패: {result.get('error')}")
                return False

        except Exception as e:
            print(f"[InfographicGenerator] ImageFX API 오류: {e}")

        return False

    def batch_generate(
        self,
        scenes: List[Dict],
        layout: InfographicLayout,
        style: dict = None,
        api_type: str = "together",
        on_progress=None
    ) -> Dict[int, str]:
        """
        인포그래픽 이미지 일괄 생성

        Returns:
            {scene_id: image_path}
        """

        results = {}
        total = len(scenes)

        print(f"\n{'='*60}")
        print(f"[InfographicGenerator] 일괄 생성 시작: {total}개 씬")
        print(f"[InfographicGenerator] 레이아웃: {layout.value}")
        print(f"{'='*60}\n")

        for idx, scene in enumerate(scenes, 1):
            scene_id = scene.get("scene_id", idx)

            # 프롬프트 우선순위: image_prompt_en > image_prompt > description
            prompt = (
                scene.get("image_prompt_en", "") or
                scene.get("image_prompt", "") or
                scene.get("prompts", {}).get("image_prompt_en", "") or
                scene.get("description", "")
            )

            if on_progress:
                on_progress(idx, total, f"씬 {scene_id} 생성 중...")

            image_path = self.generate_image(
                scene_id=scene_id,
                prompt=prompt,
                layout=layout,
                style=style,
                api_type=api_type
            )

            if image_path:
                results[scene_id] = image_path

                # 씬 데이터 업데이트
                scene["infographic_image"] = image_path

            # API 속도 제한
            import time
            time.sleep(1)

            # 메모리 정리 (Out of Memory 방지)
            gc.collect()

        print(f"\n{'='*60}")
        print(f"[InfographicGenerator] 완료: {len(results)}/{total}개 생성됨")
        print(f"{'='*60}\n")

        return results


# ============================================================
# 인포그래픽 + 이미지 합성기
# ============================================================

class InfographicCompositor:
    """인포그래픽과 이미지 합성"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.output_dir = self.project_path / "images" / "infographic_composite"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def composite(
        self,
        infographic_path: str,
        background_image_path: str,
        blend_mode: str = "normal",
        opacity: float = 1.0,
        output_path: str = None
    ) -> Optional[str]:
        """
        인포그래픽 + 배경 이미지 합성

        Args:
            infographic_path: 인포그래픽 이미지 (가운데 컨텐츠)
            background_image_path: 인포그래픽용 배경 이미지 (모서리 요소)
            blend_mode: 블렌드 모드
            opacity: 투명도
            output_path: 출력 경로

        Returns:
            합성된 이미지 경로
        """

        from PIL import Image

        if not os.path.exists(infographic_path):
            print(f"[InfographicCompositor] 인포그래픽 없음: {infographic_path}")
            return None

        if not os.path.exists(background_image_path):
            print(f"[InfographicCompositor] 배경 이미지 없음: {background_image_path}")
            return None

        try:
            # 이미지 로드
            infographic = Image.open(infographic_path).convert("RGBA")
            background = Image.open(background_image_path).convert("RGBA")

            # 크기 맞추기 (배경 크기에 맞춤)
            if infographic.size != background.size:
                infographic = infographic.resize(background.size, Image.LANCZOS)

            # 투명도 적용
            if opacity < 1.0:
                alpha = infographic.split()[3]
                alpha = alpha.point(lambda p: int(p * opacity))
                infographic.putalpha(alpha)

            # 합성 (배경 위에 인포그래픽)
            result = Image.alpha_composite(background, infographic)

            # 저장
            if not output_path:
                timestamp = int(datetime.now().timestamp() * 1000)
                output_path = self.output_dir / f"infographic_composite_{timestamp}.png"

            result.save(str(output_path), "PNG")

            print(f"[InfographicCompositor] 합성 완료: {output_path}")
            return str(output_path)

        except Exception as e:
            print(f"[InfographicCompositor] 합성 실패: {e}")
            return None

    def batch_composite(
        self,
        pairs: List[Tuple[str, str]],
        blend_mode: str = "normal",
        opacity: float = 1.0,
        on_progress=None
    ) -> List[str]:
        """
        일괄 합성

        Args:
            pairs: [(infographic_path, background_path), ...]

        Returns:
            합성된 이미지 경로 리스트
        """

        results = []
        total = len(pairs)

        for idx, (infographic_path, background_path) in enumerate(pairs, 1):
            if on_progress:
                on_progress(idx, total, f"합성 중... ({idx}/{total})")

            output_path = self.composite(
                infographic_path=infographic_path,
                background_image_path=background_path,
                blend_mode=blend_mode,
                opacity=opacity
            )

            if output_path:
                results.append(output_path)

        return results


# ============================================================
# 헬퍼 함수
# ============================================================

def get_available_layouts() -> List[Dict]:
    """사용 가능한 레이아웃 목록 반환"""

    return [
        {
            "id": InfographicLayout.CORNERS.value,
            "name": "모서리 배치",
            "name_en": "Corners",
            "description": "4개 모서리에 요소 배치, 가운데 비움",
            "icon": "⬛"
        },
        {
            "id": InfographicLayout.TOP_BOTTOM.value,
            "name": "상하 배치",
            "name_en": "Top-Bottom",
            "description": "상단/하단에 요소 배치, 중앙 비움",
            "icon": "⬆️"
        },
        {
            "id": InfographicLayout.LEFT_RIGHT.value,
            "name": "좌우 배치",
            "name_en": "Left-Right",
            "description": "좌/우측에 요소 배치, 중앙 비움",
            "icon": "↔️"
        },
        {
            "id": InfographicLayout.TOP_LEFT.value,
            "name": "좌상단 집중",
            "name_en": "Top-Left",
            "description": "좌상단에 요소 집중 배치",
            "icon": "↖️"
        },
        {
            "id": InfographicLayout.TOP_RIGHT.value,
            "name": "우상단 집중",
            "name_en": "Top-Right",
            "description": "우상단에 요소 집중 배치",
            "icon": "↗️"
        },
        {
            "id": InfographicLayout.BOTTOM_LEFT.value,
            "name": "좌하단 집중",
            "name_en": "Bottom-Left",
            "description": "좌하단에 요소 집중 배치",
            "icon": "↙️"
        },
        {
            "id": InfographicLayout.BOTTOM_RIGHT.value,
            "name": "우하단 집중",
            "name_en": "Bottom-Right",
            "description": "우하단에 요소 집중 배치",
            "icon": "↘️"
        },
        {
            "id": InfographicLayout.FRAME.value,
            "name": "프레임 형태",
            "name_en": "Frame",
            "description": "테두리 전체에 요소 배치, 가운데 완전히 비움",
            "icon": "🖼️"
        },
        {
            "id": InfographicLayout.L_SHAPE.value,
            "name": "L자 형태",
            "name_en": "L-Shape",
            "description": "하단+좌측에 L자로 요소 배치",
            "icon": "📐"
        }
    ]


def get_layout_by_id(layout_id: str) -> InfographicLayout:
    """ID로 레이아웃 Enum 반환"""

    for layout in InfographicLayout:
        if layout.value == layout_id:
            return layout

    return InfographicLayout.CORNERS  # 기본값


def get_layout_preview_html(layout_id: str) -> str:
    """레이아웃 미리보기 HTML"""

    previews = {
        "corners": """
            <div style="width:80px;height:60px;border:2px solid #667eea;position:relative;margin:10px auto;background:#f8f9fa;">
                <div style="position:absolute;top:2px;left:2px;width:15px;height:15px;background:#667eea;border-radius:2px;"></div>
                <div style="position:absolute;top:2px;right:2px;width:15px;height:15px;background:#667eea;border-radius:2px;"></div>
                <div style="position:absolute;bottom:2px;left:2px;width:15px;height:15px;background:#667eea;border-radius:2px;"></div>
                <div style="position:absolute;bottom:2px;right:2px;width:15px;height:15px;background:#667eea;border-radius:2px;"></div>
            </div>
        """,
        "top_bottom": """
            <div style="width:80px;height:60px;border:2px solid #667eea;position:relative;margin:10px auto;background:#f8f9fa;">
                <div style="position:absolute;top:0;left:0;right:0;height:12px;background:#667eea;"></div>
                <div style="position:absolute;bottom:0;left:0;right:0;height:12px;background:#667eea;"></div>
            </div>
        """,
        "left_right": """
            <div style="width:80px;height:60px;border:2px solid #667eea;position:relative;margin:10px auto;background:#f8f9fa;">
                <div style="position:absolute;top:0;left:0;bottom:0;width:15px;background:#667eea;"></div>
                <div style="position:absolute;top:0;right:0;bottom:0;width:15px;background:#667eea;"></div>
            </div>
        """,
        "top_left": """
            <div style="width:80px;height:60px;border:2px solid #667eea;position:relative;margin:10px auto;background:#f8f9fa;">
                <div style="position:absolute;top:2px;left:2px;width:30px;height:25px;background:#667eea;border-radius:2px;"></div>
            </div>
        """,
        "top_right": """
            <div style="width:80px;height:60px;border:2px solid #667eea;position:relative;margin:10px auto;background:#f8f9fa;">
                <div style="position:absolute;top:2px;right:2px;width:30px;height:25px;background:#667eea;border-radius:2px;"></div>
            </div>
        """,
        "bottom_left": """
            <div style="width:80px;height:60px;border:2px solid #667eea;position:relative;margin:10px auto;background:#f8f9fa;">
                <div style="position:absolute;bottom:2px;left:2px;width:30px;height:25px;background:#667eea;border-radius:2px;"></div>
            </div>
        """,
        "bottom_right": """
            <div style="width:80px;height:60px;border:2px solid #667eea;position:relative;margin:10px auto;background:#f8f9fa;">
                <div style="position:absolute;bottom:2px;right:2px;width:30px;height:25px;background:#667eea;border-radius:2px;"></div>
            </div>
        """,
        "frame": """
            <div style="width:80px;height:60px;border:8px solid #667eea;margin:10px auto;background:#f8f9fa;"></div>
        """,
        "l_shape": """
            <div style="width:80px;height:60px;border:2px solid #667eea;position:relative;margin:10px auto;background:#f8f9fa;">
                <div style="position:absolute;bottom:0;left:0;right:0;height:15px;background:#667eea;"></div>
                <div style="position:absolute;top:0;left:0;bottom:15px;width:15px;background:#667eea;"></div>
            </div>
        """
    }

    return previews.get(layout_id, previews["corners"])


# ============================================================
# 인포그래픽 기본 스타일
# ============================================================

DEFAULT_INFOGRAPHIC_STYLES = [
    {
        "id": "infographic_minimal",
        "name": "Minimal",
        "name_ko": "미니멀",
        "segment": "infographic",
        "description": "깔끔하고 단순한 인포그래픽 배경",
        "is_default": True,
        "prompt_prefix": "minimal clean design, simple geometric shapes, flat colors, modern aesthetic",
        "prompt_suffix": "professional infographic background, edge-focused decorative elements",
        "negative_prompt": "cluttered, busy, complex patterns, realistic photo"
    },
    {
        "id": "infographic_corporate",
        "name": "Corporate",
        "name_ko": "비즈니스",
        "segment": "infographic",
        "description": "비즈니스/기업용 인포그래픽 배경",
        "is_default": False,
        "prompt_prefix": "corporate business style, professional, clean lines, blue and gray tones",
        "prompt_suffix": "business presentation background, modern office aesthetic, subtle gradients",
        "negative_prompt": "casual, playful, bright colors, cartoon"
    },
    {
        "id": "infographic_creative",
        "name": "Creative",
        "name_ko": "크리에이티브",
        "segment": "infographic",
        "description": "창의적이고 역동적인 인포그래픽 배경",
        "is_default": False,
        "prompt_prefix": "creative dynamic style, colorful abstract shapes, artistic elements, vibrant",
        "prompt_suffix": "creative infographic background, artistic flair, modern design",
        "negative_prompt": "boring, monochrome, corporate, plain"
    },
    {
        "id": "infographic_tech",
        "name": "Tech",
        "name_ko": "테크/IT",
        "segment": "infographic",
        "description": "기술/IT 관련 인포그래픽 배경",
        "is_default": False,
        "prompt_prefix": "technology style, digital elements, circuit patterns, futuristic, neon accents",
        "prompt_suffix": "tech infographic background, cyber aesthetic, modern digital design",
        "negative_prompt": "organic, natural, vintage, rustic"
    },
    {
        "id": "infographic_education",
        "name": "Education",
        "name_ko": "교육/학습",
        "segment": "infographic",
        "description": "교육/학습 콘텐츠용 인포그래픽 배경",
        "is_default": False,
        "prompt_prefix": "educational style, books, learning icons, friendly approachable design, warm colors",
        "prompt_suffix": "educational infographic background, school theme, knowledge elements",
        "negative_prompt": "dark, scary, complex, corporate"
    },
    {
        "id": "infographic_webtoon",
        "name": "Webtoon",
        "name_ko": "웹툰/만화",
        "segment": "infographic",
        "description": "웹툰/만화 스타일 인포그래픽 배경",
        "is_default": False,
        "prompt_prefix": "Korean webtoon manhwa style, comic illustration, bold outlines, cel shading",
        "prompt_suffix": "webtoon style infographic background, cartoon aesthetic, manga influence",
        "negative_prompt": "realistic, photo, 3D render, dark"
    }
]
