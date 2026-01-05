# -*- coding: utf-8 -*-
"""
인포그래픽 HTML 배경 이미지 대체 유틸리티

기능:
- HTML 파싱 및 배경 스타일 식별
- 이미지를 base64로 변환하여 삽입
- 투명도 조절 기능
- 씬별 개별 배경 지원
"""

import os
import re
import base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from PIL import Image
import io


# ============================================================
# 배경 크기 옵션 상수
# ============================================================

BACKGROUND_SIZE_OPTIONS = {
    "cover": {
        "value": "cover",
        "name": "전체 채움 (cover)",
        "description": "이미지가 전체 화면을 채웁니다. 비율 유지, 일부 잘릴 수 있음",
        "css": "cover"
    },
    "contain": {
        "value": "contain",
        "name": "비율 유지 (contain)",
        "description": "이미지 전체가 보입니다. 비율 유지, 여백 발생 가능",
        "css": "contain"
    },
    "stretch": {
        "value": "100% 100%",
        "name": "늘려서 채움 (stretch)",
        "description": "이미지를 늘려서 전체를 채웁니다. 비율 무시",
        "css": "100% 100%"
    },
    "original": {
        "value": "auto",
        "name": "원본 크기",
        "description": "이미지 원본 크기 유지",
        "css": "auto"
    },
    "width_100": {
        "value": "100% auto",
        "name": "가로 채움",
        "description": "가로를 채우고 세로는 비율에 맞춤",
        "css": "100% auto"
    },
    "height_100": {
        "value": "auto 100%",
        "name": "세로 채움",
        "description": "세로를 채우고 가로는 비율에 맞춤",
        "css": "auto 100%"
    }
}


def get_background_size_options():
    """UI용 배경 크기 옵션 목록 반환"""
    return [
        {"id": k, **v}
        for k, v in BACKGROUND_SIZE_OPTIONS.items()
    ]


def get_size_css(size_key: str) -> str:
    """크기 키를 CSS 값으로 변환"""
    if size_key in BACKGROUND_SIZE_OPTIONS:
        return BACKGROUND_SIZE_OPTIONS[size_key]["css"]
    # 이미 CSS 값인 경우 그대로 반환
    return size_key


class HTMLBackgroundReplacer:
    """인포그래픽 HTML 배경 대체기 (HTML 구조 보존)"""

    def __init__(self, html_content: str):
        """
        Args:
            html_content: 원본 HTML 문자열
        """
        self.original_html = html_content
        self.modified_html = None

        # HTML 정규화
        normalized_html = self._normalize_html(html_content)

        # BeautifulSoup은 파싱용으로만 사용 (수정용 X)
        self.soup = BeautifulSoup(normalized_html, 'html.parser')
        self.scenes = self._parse_scenes()

    def _normalize_html(self, html_content: str) -> str:
        """HTML 정규화 - 파싱 전 전처리"""

        html = html_content.strip()

        # BOM 제거
        if html.startswith('\ufeff'):
            html = html[1:]

        return html

    def _parse_scenes(self) -> List[Dict]:
        """HTML에서 씬 정보 파싱 - 여러 방법 시도"""

        scenes = []

        # ============================================================
        # 방법 1: class="scene" 찾기
        # ============================================================
        scene_elements = self.soup.find_all(class_='scene')

        if scene_elements:
            print(f"[HTMLParser] 방법 1 성공: {len(scene_elements)}개 씬 (class='scene')")
            for idx, scene_el in enumerate(scene_elements, 1):
                scenes.append(self._extract_scene_info(scene_el, idx))
            return scenes

        # ============================================================
        # 방법 2: id="scene1", id="scene2" 패턴으로 찾기
        # ============================================================
        scene_by_id = []
        for i in range(1, 100):
            el = self.soup.find(id=f'scene{i}')
            if el:
                scene_by_id.append(el)
            else:
                break

        if scene_by_id:
            print(f"[HTMLParser] 방법 2 성공: {len(scene_by_id)}개 씬 (id='sceneN')")
            for idx, scene_el in enumerate(scene_by_id, 1):
                scenes.append(self._extract_scene_info(scene_el, idx))
            return scenes

        # ============================================================
        # 방법 3: CSS 선택자로 찾기
        # ============================================================
        try:
            scene_by_css = self.soup.select('div.scene, section.scene, [class*="scene"]')
            if scene_by_css:
                print(f"[HTMLParser] 방법 3 성공: {len(scene_by_css)}개 씬 (CSS 선택자)")
                for idx, scene_el in enumerate(scene_by_css, 1):
                    scenes.append(self._extract_scene_info(scene_el, idx))
                return scenes
        except Exception as e:
            print(f"[HTMLParser] 방법 3 실패: {e}")

        # ============================================================
        # 방법 4: 정규식으로 직접 파싱
        # ============================================================
        print("[HTMLParser] 방법 4 시도: 정규식 파싱")

        # class="scene" 또는 class='scene' 둘 다 찾기
        scene_pattern = r'<div[^>]*(?:class=["\'][^"\']*scene[^"\']*["\'])[^>]*(?:id=["\']?(scene\d+)["\']?)?[^>]*>'
        matches = re.findall(scene_pattern, self.original_html, re.IGNORECASE)

        if matches:
            print(f"[HTMLParser] 방법 4 성공: {len(matches)}개 씬 (정규식)")
            for idx, scene_id in enumerate(matches, 1):
                scenes.append({
                    "index": idx,
                    "id": scene_id if scene_id else f"scene{idx}",
                    "title": f"씬 {idx}",
                    "element": None
                })
            return scenes

        # 모든 방법 실패
        print("[HTMLParser] 모든 파싱 방법 실패")
        return []

    def _extract_scene_info(self, element, idx: int) -> Dict:
        """씬 요소에서 정보 추출"""

        scene_id = element.get('id', f'scene{idx}')

        # 제목 추출
        title = ""
        h1 = element.find('h1')
        h2 = element.find('h2')
        if h1:
            title = h1.get_text(strip=True)[:50]
        elif h2:
            title = h2.get_text(strip=True)[:50]

        return {
            "index": idx,
            "id": scene_id,
            "title": title or f"씬 {idx}",
            "element": element
        }

    def get_scene_count(self) -> int:
        """씬 개수 반환"""
        return len(self.scenes)

    def get_scenes_info(self) -> List[Dict]:
        """씬 정보 목록 반환 (element 제외)"""
        return [
            {"index": s["index"], "id": s["id"], "title": s["title"]}
            for s in self.scenes
        ]

    # ============================================================
    # 배경 이미지 대체 메서드
    # ============================================================

    def replace_global_background(
        self,
        image_path: str,
        opacity: float = 0.3,
        blend_mode: str = "normal",
        position: str = "center",
        size: str = "cover"
    ) -> str:
        """
        전체 배경 이미지 대체

        Args:
            image_path: 배경 이미지 경로
            opacity: 투명도 (0.0 ~ 1.0)
            blend_mode: CSS mix-blend-mode
            position: background-position
            size: background-size

        Returns:
            수정된 HTML 문자열
        """

        # 이미지를 base64로 변환
        base64_image = self._image_to_base64(image_path)

        if not base64_image:
            print(f"[HTMLBackgroundReplacer] 이미지 변환 실패: {image_path}")
            return self.original_html

        # 이미지 MIME 타입
        mime_type = self._get_mime_type(image_path)

        # 배경 CSS 생성
        background_css = self._generate_background_css(
            base64_image=base64_image,
            mime_type=mime_type,
            opacity=opacity,
            blend_mode=blend_mode,
            position=position,
            size=size,
            target_selector="#video-canvas"
        )

        # HTML에 CSS 삽입
        modified_html = self._inject_css(background_css)

        print(f"[HTMLBackgroundReplacer] 전체 배경 대체 완료 (투명도: {opacity})")

        return modified_html

    def replace_scene_backgrounds(
        self,
        scene_images: Dict[int, str],
        opacity: float = 0.3,
        blend_mode: str = "normal",
        size: str = "cover"
    ) -> str:
        """
        씬별 개별 배경 이미지 대체

        Args:
            scene_images: {씬_인덱스: 이미지_경로} 딕셔너리
            opacity: 기본 투명도
            blend_mode: CSS mix-blend-mode
            size: 배경 크기 ("cover", "contain", "stretch" 등)

        Returns:
            수정된 HTML 문자열
        """

        css_parts = []

        for scene_idx, image_path in scene_images.items():
            if not os.path.exists(image_path):
                continue

            base64_image = self._image_to_base64(image_path)
            mime_type = self._get_mime_type(image_path)

            if not base64_image:
                continue

            # 씬별 CSS
            scene_css = self._generate_scene_background_css(
                scene_index=scene_idx,
                base64_image=base64_image,
                mime_type=mime_type,
                opacity=opacity,
                blend_mode=blend_mode,
                size=size
            )

            css_parts.append(scene_css)

        # HTML에 CSS 삽입
        combined_css = "\n".join(css_parts)
        modified_html = self._inject_css(combined_css)

        print(f"[HTMLBackgroundReplacer] {len(scene_images)}개 씬 배경 대체 완료")

        return modified_html

    # ============================================================
    # 내부 헬퍼 메서드
    # ============================================================

    def _image_to_base64(self, image_path: str) -> Optional[str]:
        """이미지를 base64 문자열로 변환"""

        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            print(f"[HTMLBackgroundReplacer] Base64 변환 오류: {e}")
            return None

    def _get_mime_type(self, image_path: str) -> str:
        """파일 확장자에서 MIME 타입 추출"""

        ext = Path(image_path).suffix.lower()
        mime_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        return mime_map.get(ext, 'image/png')

    def _generate_background_css(
        self,
        base64_image: str,
        mime_type: str,
        opacity: float,
        blend_mode: str,
        position: str,
        size: str,
        target_selector: str
    ) -> str:
        """
        전체 배경용 CSS 생성

        Args:
            size: "cover", "contain", "stretch", "original", "width_100", "height_100"
                  또는 직접 CSS 값 ("100% 100%", "auto" 등)
        """

        # 크기 키를 CSS 값으로 변환
        size_css = get_size_css(size)

        return f'''
/* ========== 인포그래픽 배경 이미지 (자동 생성) ========== */
{target_selector} {{
    position: relative !important;
}}

{target_selector}::before {{
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100%;
    height: 100%;
    background-image: url('data:{mime_type};base64,{base64_image}');
    background-size: {size_css};
    background-position: {position};
    background-repeat: no-repeat;
    opacity: {opacity};
    mix-blend-mode: {blend_mode};
    z-index: 0;
    pointer-events: none;
}}

/* 콘텐츠가 배경 위에 표시되도록 */
{target_selector} > * {{
    position: relative;
    z-index: 1;
}}

{target_selector} .safe-area {{
    position: relative;
    z-index: 1;
}}

{target_selector} .scene {{
    position: relative;
    z-index: 1;
}}
/* ========== 배경 이미지 끝 ========== */
'''

    def _generate_scene_background_css(
        self,
        scene_index: int,
        base64_image: str,
        mime_type: str,
        opacity: float,
        blend_mode: str,
        size: str = "cover"
    ) -> str:
        """
        씬별 배경용 CSS 생성

        Args:
            size: "cover", "contain", "stretch", "original", "width_100", "height_100"
                  또는 직접 CSS 값
        """

        # 크기 키를 CSS 값으로 변환
        size_css = get_size_css(size)

        return f'''
/* 씬 {scene_index} 배경 */
#scene{scene_index} {{
    position: relative !important;
}}

#scene{scene_index}::before {{
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100%;
    height: 100%;
    background-image: url('data:{mime_type};base64,{base64_image}');
    background-size: {size_css};
    background-position: center;
    background-repeat: no-repeat;
    opacity: {opacity};
    mix-blend-mode: {blend_mode};
    z-index: 0;
    pointer-events: none;
}}

#scene{scene_index} > * {{
    position: relative;
    z-index: 1;
}}
'''

    def _inject_css(self, css_content: str) -> str:
        """
        HTML에 CSS 삽입 (문자열 조작으로 구조 보존)

        BeautifulSoup의 str()을 사용하면 HTML 구조가 변경될 수 있으므로
        정규식 기반 문자열 조작 사용
        """

        html = self.original_html

        # ============================================================
        # 방법 1: 기존 </style> 태그 앞에 CSS 삽입
        # ============================================================
        style_end_pattern = r'(</style>)'
        if re.search(style_end_pattern, html, re.IGNORECASE):
            modified = re.sub(
                style_end_pattern,
                f'\n{css_content}\n\\1',
                html,
                count=1,  # 첫 번째 </style>에만 적용
                flags=re.IGNORECASE
            )
            self.modified_html = modified
            return modified

        # ============================================================
        # 방법 2: </head> 태그 앞에 새 <style> 태그 삽입
        # ============================================================
        head_end_pattern = r'(</head>)'
        if re.search(head_end_pattern, html, re.IGNORECASE):
            style_tag = f'<style type="text/css">\n{css_content}\n</style>'
            modified = re.sub(
                head_end_pattern,
                f'{style_tag}\n\\1',
                html,
                count=1,
                flags=re.IGNORECASE
            )
            self.modified_html = modified
            return modified

        # ============================================================
        # 방법 3: <body> 태그 뒤에 <style> 태그 삽입
        # ============================================================
        body_start_pattern = r'(<body[^>]*>)'
        if re.search(body_start_pattern, html, re.IGNORECASE):
            style_tag = f'<style type="text/css">\n{css_content}\n</style>'
            modified = re.sub(
                body_start_pattern,
                f'\\1\n{style_tag}',
                html,
                count=1,
                flags=re.IGNORECASE
            )
            self.modified_html = modified
            return modified

        # ============================================================
        # 방법 4: 맨 앞에 <style> 태그 추가
        # ============================================================
        style_tag = f'<style type="text/css">\n{css_content}\n</style>\n'
        modified = style_tag + html
        self.modified_html = modified
        return modified

    def get_modified_html(self) -> str:
        """수정된 HTML 반환"""
        return self.modified_html if self.modified_html else self.original_html

    # ============================================================
    # 고급 기능
    # ============================================================

    def add_background_controls(self) -> str:
        """
        런타임 배경 조절 컨트롤 추가
        (HTML에 JavaScript 컨트롤 삽입)
        """

        control_html = '''
<!-- 배경 조절 컨트롤 -->
<div id="bg-controls" style="
    position: fixed;
    bottom: 20px;
    left: 20px;
    background: rgba(0,0,0,0.8);
    padding: 15px;
    border-radius: 10px;
    z-index: 9999;
    color: white;
    font-family: sans-serif;
    font-size: 14px;
">
    <div style="margin-bottom: 10px;">
        <label>배경 투명도: <span id="opacity-value">30%</span></label>
        <input type="range" id="bg-opacity" min="0" max="100" value="30"
               style="width: 150px;"
               oninput="updateBgOpacity(this.value)">
    </div>
    <div>
        <label>블렌드 모드:</label>
        <select id="bg-blend" onchange="updateBgBlend(this.value)" style="margin-left: 5px;">
            <option value="normal">Normal</option>
            <option value="multiply">Multiply</option>
            <option value="screen">Screen</option>
            <option value="overlay">Overlay</option>
            <option value="soft-light">Soft Light</option>
        </select>
    </div>
    <button onclick="document.getElementById('bg-controls').style.display='none'"
            style="margin-top: 10px; padding: 5px 10px;">닫기</button>
</div>

<script>
function updateBgOpacity(value) {
    document.getElementById('opacity-value').textContent = value + '%';
    var canvas = document.getElementById('video-canvas');
    if (canvas) {
        document.documentElement.style.setProperty('--bg-opacity', value / 100);
    }
}

function updateBgBlend(value) {
    document.documentElement.style.setProperty('--bg-blend', value);
}
</script>
'''

        # </body> 앞에 삽입 (문자열 조작으로 구조 보존)
        html = self.modified_html if self.modified_html else self.original_html

        body_end_pattern = r'(</body>)'
        if re.search(body_end_pattern, html, re.IGNORECASE):
            modified = re.sub(
                body_end_pattern,
                f'{control_html}\n\\1',
                html,
                count=1,
                flags=re.IGNORECASE
            )
            self.modified_html = modified
            return modified

        # </body>가 없으면 맨 뒤에 추가
        self.modified_html = html + control_html
        return self.modified_html

    def export_with_embedded_images(self, output_path: str) -> bool:
        """
        모든 이미지가 임베딩된 단일 HTML 파일 내보내기
        """

        try:
            html_to_export = self.modified_html if self.modified_html else self.original_html

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_to_export)

            print(f"[HTMLBackgroundReplacer] 내보내기 완료: {output_path}")
            return True

        except Exception as e:
            print(f"[HTMLBackgroundReplacer] 내보내기 실패: {e}")
            return False


# ============================================================
# 헬퍼 함수
# ============================================================

def replace_html_background(
    html_content: str,
    image_path: str,
    opacity: float = 0.3
) -> str:
    """
    간편한 배경 대체 함수

    Args:
        html_content: 원본 HTML
        image_path: 배경 이미지 경로
        opacity: 투명도

    Returns:
        수정된 HTML
    """

    replacer = HTMLBackgroundReplacer(html_content)
    return replacer.replace_global_background(image_path, opacity)


def replace_scene_backgrounds(
    html_content: str,
    scene_images: Dict[int, str],
    opacity: float = 0.3,
    size: str = "cover"
) -> str:
    """
    씬별 배경 대체 함수

    Args:
        html_content: 원본 HTML
        scene_images: {씬_인덱스: 이미지_경로} 딕셔너리
        opacity: 기본 투명도
        size: 배경 크기 ("cover", "contain", "stretch" 등)
    """

    replacer = HTMLBackgroundReplacer(html_content)
    return replacer.replace_scene_backgrounds(scene_images, opacity, size=size)


def preview_background_replacement(
    html_content: str,
    image_path: str,
    opacity: float = 0.3
) -> Tuple[str, str]:
    """
    배경 대체 미리보기

    Returns:
        (수정된 HTML, 미리보기용 CSS만)
    """

    replacer = HTMLBackgroundReplacer(html_content)
    modified_html = replacer.replace_global_background(image_path, opacity)

    # CSS만 추출
    soup = BeautifulSoup(modified_html, 'html.parser')
    style = soup.find('style')
    css_only = style.string if style else ""

    return modified_html, css_only


def get_project_images(project_path: str, limit: int = 50) -> List[str]:
    """프로젝트 내 이미지 목록 로드"""

    images_dir = Path(project_path) / "images"

    if not images_dir.exists():
        return []

    all_images = []

    # 모든 하위 디렉토리 포함
    for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
        all_images.extend(images_dir.rglob(ext))

    # 최신순 정렬
    all_images.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    return [str(p) for p in all_images[:limit]]


def get_infographic_images(project_path: str) -> List[str]:
    """인포그래픽용 이미지 목록 로드"""

    infographic_dir = Path(project_path) / "images" / "infographic"

    if not infographic_dir.exists():
        return []

    images = list(infographic_dir.glob("*.png"))
    images.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    return [str(p) for p in images]
