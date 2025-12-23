# -*- coding: utf-8 -*-
"""
인포그래픽 HTML 파서 v2.1

HTML 파일에서 인포그래픽 데이터 추출

지원 형식:
- 형식 A: JavaScript sceneData 배열 (동적 생성)
  const sceneData = [{ id: 1, text: "...", sub: "..." }, ...]

- 형식 B: 순수 HTML <div class="scene"> 요소 (정적 정의)
  <div class="scene" id="scene1">...</div>
"""

import re
import json
from typing import Dict, List, Optional, Any, Tuple

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("[InfographicParser] BeautifulSoup 미설치. 형식 B 파싱 불가. pip install beautifulsoup4")

from utils.models.infographic import InfographicScene, InfographicData


class InfographicParser:
    """
    인포그래픽 HTML 파서

    지원 형식:
    - 형식 A: JavaScript sceneData 배열
    - 형식 B: 순수 HTML <div class="scene"> 요소
    """

    # 형식 A: sceneData 패턴들
    SCENE_DATA_PATTERNS = [
        r'(?:const|let|var)\s+sceneData\s*=\s*\[([\s\S]*?)\];',
        r'window\.sceneData\s*=\s*\[([\s\S]*?)\];',
        r'sceneData\s*:\s*\[([\s\S]*?)\]',
    ]

    def __init__(self):
        self.last_error: Optional[str] = None
        self.parse_format: Optional[str] = None

    def parse_html_code(
        self,
        html_code: str,
        source_path: str = ""
    ) -> Optional[InfographicData]:
        """
        HTML 코드에서 인포그래픽 데이터 파싱

        Args:
            html_code: 전체 HTML 코드
            source_path: 원본 파일 경로 (메타데이터용)

        Returns:
            InfographicData 또는 None
        """
        try:
            # 1차 시도: sceneData 배열 파싱 (형식 A)
            scenes = self._parse_scene_data_array(html_code)
            if scenes:
                self.parse_format = "format_a_scenedata"
                print(f"✅ 형식 A: {len(scenes)}개 씬 파싱 완료 (sceneData 배열)")
                return InfographicData(
                    html_code=html_code,
                    source_path=source_path,
                    total_scenes=len(scenes),
                    scenes=scenes,
                    parse_format=self.parse_format
                )

            # 2차 시도: HTML 요소 파싱 (형식 B)
            if BS4_AVAILABLE:
                scenes = self._parse_html_elements(html_code)
                if scenes:
                    self.parse_format = "format_b_html_elements"
                    print(f"✅ 형식 B: {len(scenes)}개 씬 파싱 완료 (HTML 요소)")
                    return InfographicData(
                        html_code=html_code,
                        source_path=source_path,
                        total_scenes=len(scenes),
                        scenes=scenes,
                        parse_format=self.parse_format
                    )
            else:
                self.last_error = "BeautifulSoup 미설치로 HTML 요소 파싱 불가"

            # 둘 다 실패
            if not self.last_error:
                self.last_error = "파싱 실패: sceneData 배열도, <div class='scene'> 요소도 찾을 수 없습니다."
            return None

        except Exception as e:
            self.last_error = str(e)
            return None

    # =========================================
    # 형식 A: sceneData 배열 파싱
    # =========================================

    def _parse_scene_data_array(self, html_code: str) -> Optional[List[InfographicScene]]:
        """JavaScript sceneData 배열 파싱"""
        try:
            # sceneData 배열 추출
            array_content = self._extract_scene_data(html_code)
            if not array_content:
                return None

            # JSON 파싱
            scene_list = self._parse_json_array(array_content)
            if not scene_list:
                return None

            # 씬 객체 생성
            scenes = self._create_scenes_from_scenedata(scene_list)
            return scenes if scenes else None

        except Exception as e:
            print(f"[Parser] 형식 A 파싱 실패: {e}")
            return None

    def _extract_scene_data(self, html_code: str) -> Optional[str]:
        """HTML에서 sceneData 배열 문자열 추출"""
        for pattern in self.SCENE_DATA_PATTERNS:
            match = re.search(pattern, html_code, re.MULTILINE)
            if match:
                return match.group(1)

        # 더 간단한 패턴으로 마지막 시도
        simple_match = re.search(r'sceneData\s*=\s*\[([\s\S]*?)\]', html_code)
        if simple_match:
            return simple_match.group(1)

        return None

    def _parse_json_array(self, array_content: str) -> Optional[List[Dict]]:
        """JSON 배열 문자열 파싱 (오류 복구 포함)"""

        # 1차 시도: 직접 파싱
        try:
            return json.loads(f"[{array_content}]")
        except json.JSONDecodeError:
            pass

        # 2차 시도: JavaScript → JSON 변환
        cleaned = self._convert_js_to_json(array_content)
        try:
            return json.loads(f"[{cleaned}]")
        except json.JSONDecodeError:
            pass

        # 3차 시도: 개별 객체 추출
        return self._extract_individual_objects(array_content)

    def _convert_js_to_json(self, js_str: str) -> str:
        """JavaScript 객체 문법을 JSON으로 변환"""
        result = js_str

        # 키에 따옴표 추가: { id: 1 } → { "id": 1 }
        result = re.sub(r'(\w+)\s*:', r'"\1":', result)

        # 중복 따옴표 제거
        result = re.sub(r'""(\w+)""', r'"\1"', result)

        # 작은따옴표 → 큰따옴표
        result = result.replace("'", '"')

        # 후행 쉼표 제거
        result = re.sub(r',(\s*[}\]])', r'\1', result)

        # undefined → null
        result = re.sub(r'\bundefined\b', 'null', result)

        return result

    def _extract_individual_objects(self, content: str) -> Optional[List[Dict]]:
        """개별 객체를 추출하여 배열 구성"""
        objects = []
        brace_pattern = re.compile(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}')

        for match in brace_pattern.finditer(content):
            obj_str = match.group()
            try:
                cleaned = self._convert_js_to_json(obj_str)
                obj = json.loads(cleaned)
                if isinstance(obj, dict):
                    objects.append(obj)
            except:
                continue

        return objects if objects else None

    def _create_scenes_from_scenedata(self, scene_list: List[Dict]) -> List[InfographicScene]:
        """sceneData에서 씬 객체 생성"""
        scenes = []

        for i, data in enumerate(scene_list):
            scene = InfographicScene(
                scene_id=data.get("id", i + 1),
                text=data.get("text", ""),
                sub=data.get("sub", ""),
                pattern=data.get("pattern", 1),
                icon=data.get("icon"),
                icon2=data.get("icon2"),
                color=data.get("color"),
                val1=data.get("val1"),
                val2=data.get("val2"),
                num=data.get("num"),
                data=data.get("data"),
                del_items=data.get("del"),
                ok_item=data.get("ok"),
                has_animation=True  # sceneData 형식은 보통 애니메이션 포함
            )

            # 키워드 추출
            scene.keywords = self._extract_keywords(data)

            # 차트 타입 감지
            scene.chart_type = self._detect_chart_type(data)

            scenes.append(scene)

        return scenes

    def _extract_keywords(self, data: Dict) -> List[str]:
        """씬 데이터에서 키워드 추출"""
        keywords = []

        # num 필드
        if data.get("num"):
            keywords.append(str(data["num"]))

        # data 필드 (숫자 배열)
        if data.get("data"):
            keywords.extend([str(d) for d in data["data"][:5]])

        # val1, val2 필드
        if data.get("val1"):
            keywords.append(str(data["val1"]))
        if data.get("val2"):
            keywords.append(str(data["val2"]))

        # text에서 숫자 추출
        text = data.get("text", "")
        percents = re.findall(r'\d+(?:\.\d+)?%', text)
        keywords.extend(percents)

        return list(set(keywords))[:10]

    def _detect_chart_type(self, data: Dict) -> Optional[str]:
        """차트 타입 감지"""
        pattern = data.get("pattern", 0)

        # 패턴 번호 기반 추론
        pattern_map = {
            5: "bar",       # 막대 그래프
            6: "bar",       # 막대 비교
            7: "timeline",  # 타임라인
            8: "table",     # 표
            9: "checklist", # 체크리스트
            10: "flow",     # 플로우
            11: "pie",      # 파이 차트
            12: "map"       # 맵
        }

        return pattern_map.get(pattern)

    # =========================================
    # 형식 B: HTML 요소 파싱
    # =========================================

    def _parse_html_elements(self, html_code: str) -> Optional[List[InfographicScene]]:
        """
        <div class="scene"> 요소 파싱

        대상 HTML 구조:
        ```html
        <!-- 씬 1: 브랜드 오프닝 -->
        <div class="scene active" id="scene1">
            <h1>메인 텍스트</h1>
            <p>서브 텍스트</p>
            <i class="fa-solid fa-fish"></i>
        </div>
        ```
        """
        if not BS4_AVAILABLE:
            return None

        try:
            soup = BeautifulSoup(html_code, 'html.parser')

            # <div class="scene"> 요소 찾기
            scene_divs = soup.find_all('div', class_='scene')

            if not scene_divs:
                # 대체 패턴: id가 scene으로 시작하는 요소
                scene_divs = soup.find_all('div', id=lambda x: x and x.lower().startswith('scene'))

            if not scene_divs:
                print("[Parser] 형식 B: <div class='scene'> 요소를 찾을 수 없음")
                return None

            # HTML 주석 추출 (씬 설명용)
            comments = self._extract_comments(html_code)

            result = []
            for div in scene_divs:
                scene = self._parse_single_scene_div(div, comments)
                if scene:
                    result.append(scene)

            # scene_id 순으로 정렬
            result.sort(key=lambda s: s.scene_id)

            return result if result else None

        except Exception as e:
            print(f"[Parser] 형식 B 파싱 실패: {e}")
            return None

    def _parse_single_scene_div(self, div, comments: dict) -> Optional[InfographicScene]:
        """단일 씬 div 파싱"""
        try:
            # 1. scene_id 추출
            div_id = div.get('id', '')
            scene_id = self._extract_scene_id_from_div(div_id)

            if scene_id == 0:
                # id 속성이 없으면 순서대로 번호 부여 (나중에 처리)
                return None

            # 2. 메인 텍스트 추출 (h1 우선, 없으면 h2)
            text = self._extract_main_text(div)

            # 3. 서브 텍스트 추출 (첫 번째 p 또는 .label)
            sub = self._extract_sub_text(div)

            # 4. 애니메이션 클래스 확인
            has_animation = self._has_animation_class(div)

            # 5. Font Awesome 아이콘 수집
            icons = self._extract_icons(div)

            # 6. HTML 주석 (씬 설명)
            comment = comments.get(scene_id, "")

            # 7. 원본 HTML 보존 (동영상 녹화용)
            html_content = str(div)

            return InfographicScene(
                scene_id=scene_id,
                text=text,
                sub=sub,
                html_content=html_content,
                has_animation=has_animation,
                icons=icons,
                comment=comment
            )

        except Exception as e:
            print(f"[Parser] 씬 파싱 오류: {e}")
            return None

    def _extract_scene_id_from_div(self, div_id: str) -> int:
        """id 속성에서 숫자 추출: 'scene1' → 1"""
        if not div_id:
            return 0
        match = re.search(r'scene(\d+)', div_id, re.IGNORECASE)
        if match:
            return int(match.group(1))
        # 숫자만 있는 경우
        match = re.search(r'(\d+)', div_id)
        if match:
            return int(match.group(1))
        return 0

    def _extract_main_text(self, div) -> str:
        """메인 텍스트 추출 (h1 > h2 > 가장 큰 텍스트)"""

        # h1 찾기
        h1 = div.find('h1')
        if h1:
            return self._clean_text(h1.get_text())

        # h2 찾기
        h2 = div.find('h2')
        if h2:
            return self._clean_text(h2.get_text())

        # 가장 긴 텍스트 찾기
        texts = [t for t in div.stripped_strings if len(t) > 2]
        if texts:
            return max(texts, key=len)

        return ""

    def _extract_sub_text(self, div) -> str:
        """서브 텍스트 추출"""

        # h1/h2가 아닌 첫 번째 p 태그
        for p in div.find_all('p'):
            text = self._clean_text(p.get_text())
            if text and len(text) > 2:
                return text

        # .label 클래스
        label = div.find(class_='label')
        if label:
            return self._clean_text(label.get_text())

        # .sub 클래스
        sub_elem = div.find(class_='sub')
        if sub_elem:
            return self._clean_text(sub_elem.get_text())

        return ""

    def _clean_text(self, text: str) -> str:
        """텍스트 정리"""
        # 여러 공백을 하나로
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _has_animation_class(self, div) -> bool:
        """애니메이션 클래스 포함 여부"""
        html_str = str(div)
        animation_patterns = [
            'animate-subtle',
            'animate-spin-slow',
            'animate-pulse-red',
            'animate-draw',
            'animate-',
            'animation',
            'transition',
            '@keyframes'
        ]
        return any(p in html_str for p in animation_patterns)

    def _extract_icons(self, div) -> List[str]:
        """Font Awesome 아이콘 추출"""
        icons = []

        for i_tag in div.find_all('i'):
            classes = i_tag.get('class', [])
            for cls in classes:
                if cls.startswith('fa-') and cls not in ('fa-solid', 'fa-brands', 'fa-regular'):
                    icons.append(cls)

        return list(set(icons))  # 중복 제거

    def _extract_comments(self, html_code: str) -> dict:
        """
        HTML 주석 추출

        예: <!-- 씬 1: 브랜드 오프닝 --> → {1: "브랜드 오프닝"}
        """
        comments = {}

        # 다양한 주석 형식 지원
        patterns = [
            r'<!--\s*씬\s*(\d+)\s*[:：]\s*([^-]+)\s*-->',
            r'<!--\s*Scene\s*(\d+)\s*[:：]\s*([^-]+)\s*-->',
            r'<!--\s*(\d+)\s*[:：]\s*([^-]+)\s*-->',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html_code, re.IGNORECASE)
            for scene_num, description in matches:
                comments[int(scene_num)] = description.strip()

        return comments


# =========================================
# 헬퍼 함수
# =========================================

def parse_infographic_html(html_code: str, source_path: str = "") -> Optional[InfographicData]:
    """
    인포그래픽 HTML 파싱 (헬퍼 함수)

    Args:
        html_code: 전체 HTML 코드
        source_path: 원본 파일 경로

    Returns:
        InfographicData 또는 None
    """
    parser = InfographicParser()
    return parser.parse_html_code(html_code, source_path)


def get_parsing_info(html_code: str) -> dict:
    """
    파싱 정보 반환 (디버깅/UI용)

    Returns:
        {
            "success": bool,
            "format": "format_a_scenedata" | "format_b_html_elements" | None,
            "format_name": str,  # 한글 형식 이름
            "scene_count": int,
            "message": str,
            "scenes": List[InfographicScene] | None,
            "animated_count": int,  # 애니메이션 포함 씬 수
        }
    """
    parser = InfographicParser()
    result = parser.parse_html_code(html_code)

    format_names = {
        "format_a_scenedata": "JavaScript sceneData 배열",
        "format_b_html_elements": "HTML <div class='scene'> 요소"
    }

    if result:
        animated_count = sum(1 for s in result.scenes if s.has_animation)
        return {
            "success": True,
            "format": parser.parse_format,
            "format_name": format_names.get(parser.parse_format, parser.parse_format),
            "scene_count": result.total_scenes,
            "message": f"{result.total_scenes}개 씬 파싱 완료",
            "scenes": result.scenes,
            "animated_count": animated_count,
            "data": result
        }
    else:
        return {
            "success": False,
            "format": None,
            "format_name": None,
            "scene_count": 0,
            "message": parser.last_error or "알 수 없는 오류",
            "scenes": None,
            "animated_count": 0,
            "data": None
        }


def get_scene_count(html_code: str) -> int:
    """HTML에서 씬 개수만 빠르게 확인"""
    result = parse_infographic_html(html_code)
    return result.total_scenes if result else 0


def get_infographic_parser() -> InfographicParser:
    """파서 인스턴스 생성"""
    return InfographicParser()
