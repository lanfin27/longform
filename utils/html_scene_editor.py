# -*- coding: utf-8 -*-
"""
utils/html_scene_editor.py
개별 씬 HTML 편집 유틸리티

주요 기능:
1. HTML에서 개별 씬 추출
2. 씬 HTML 교체/수정
3. 수정 이력 관리
4. 원본 복원
"""

import re
import json
import copy
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


@dataclass
class SceneEditRecord:
    """씬 수정 기록"""
    scene_id: int
    timestamp: str
    original_html: str
    modified_html: str
    description: str = ""


@dataclass
class HTMLSceneData:
    """추출된 씬 데이터"""
    scene_id: int
    scene_index: int  # 0-based index
    html_content: str  # 씬의 HTML 또는 sceneData 객체
    text: str  # 메인 텍스트 (미리보기용)
    sub: str  # 서브 텍스트
    start_pos: int  # HTML 내 시작 위치
    end_pos: int  # HTML 내 끝 위치
    format_type: str  # "scenedata" or "html_element"


class HTMLSceneEditor:
    """HTML 씬 편집기"""

    def __init__(self, html_content: str, source_path: str = ""):
        self.original_html = html_content
        self.current_html = html_content
        self.source_path = source_path
        self.edit_history: List[SceneEditRecord] = []
        self.scenes: List[HTMLSceneData] = []
        self.format_type: str = ""

        # 씬 파싱
        self._parse_scenes()

    # ============================================================
    # 씬 파싱
    # ============================================================

    def _parse_scenes(self) -> bool:
        """HTML에서 씬 파싱"""
        # 1차 시도: sceneData 배열 (형식 A)
        if self._parse_scenedata_format():
            self.format_type = "scenedata"
            return True

        # 2차 시도: HTML 요소 (형식 B)
        if BS4_AVAILABLE and self._parse_html_element_format():
            self.format_type = "html_element"
            return True

        return False

    def _parse_scenedata_format(self) -> bool:
        """sceneData 배열 형식 파싱"""
        # sceneData 배열 찾기
        patterns = [
            r'((?:const|let|var)\s+sceneData\s*=\s*\[)([\s\S]*?)(\];)',
            r'(window\.sceneData\s*=\s*\[)([\s\S]*?)(\];)',
        ]

        for pattern in patterns:
            match = re.search(pattern, self.current_html, re.MULTILINE)
            if match:
                prefix = match.group(1)
                array_content = match.group(2)
                suffix = match.group(3)

                # 배열 시작/끝 위치
                array_start = match.start(2)
                array_end = match.end(2)

                # 개별 객체 추출
                scenes = self._extract_scenedata_objects(array_content, array_start)
                if scenes:
                    self.scenes = scenes
                    return True

        return False

    def _extract_scenedata_objects(self, array_content: str, base_offset: int) -> List[HTMLSceneData]:
        """sceneData 배열에서 개별 객체 추출"""
        scenes = []

        # 객체 경계 찾기: { ... }
        brace_depth = 0
        obj_start = -1
        obj_index = 0

        for i, char in enumerate(array_content):
            if char == '{':
                if brace_depth == 0:
                    obj_start = i
                brace_depth += 1
            elif char == '}':
                brace_depth -= 1
                if brace_depth == 0 and obj_start >= 0:
                    obj_str = array_content[obj_start:i+1]

                    # 객체 파싱
                    obj_data = self._parse_js_object(obj_str)

                    scene_id = obj_data.get('id', obj_index + 1)
                    text = obj_data.get('text', '')
                    sub = obj_data.get('sub', '')

                    scenes.append(HTMLSceneData(
                        scene_id=scene_id,
                        scene_index=obj_index,
                        html_content=obj_str,
                        text=text[:50] if text else f"씬 {scene_id}",
                        sub=sub[:100] if sub else "",
                        start_pos=base_offset + obj_start,
                        end_pos=base_offset + i + 1,
                        format_type="scenedata"
                    ))

                    obj_index += 1
                    obj_start = -1

        return scenes

    def _parse_js_object(self, obj_str: str) -> Dict:
        """JavaScript 객체 문자열을 파싱"""
        try:
            # JavaScript → JSON 변환
            cleaned = obj_str
            cleaned = re.sub(r'(\w+)\s*:', r'"\1":', cleaned)
            cleaned = re.sub(r'""(\w+)""', r'"\1"', cleaned)
            cleaned = cleaned.replace("'", '"')
            cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
            cleaned = re.sub(r'\bundefined\b', 'null', cleaned)

            return json.loads(cleaned)
        except:
            # 정규식으로 주요 필드 추출
            result = {}

            # id 추출
            id_match = re.search(r'id\s*:\s*(\d+)', obj_str)
            if id_match:
                result['id'] = int(id_match.group(1))

            # text 추출
            text_match = re.search(r'text\s*:\s*["\']([^"\']*)["\']', obj_str)
            if text_match:
                result['text'] = text_match.group(1)

            # sub 추출
            sub_match = re.search(r'sub\s*:\s*["\']([^"\']*)["\']', obj_str)
            if sub_match:
                result['sub'] = sub_match.group(1)

            return result

    def _parse_html_element_format(self) -> bool:
        """HTML 요소 형식 파싱 (div.scene)"""
        if not BS4_AVAILABLE:
            return False

        soup = BeautifulSoup(self.current_html, 'html.parser')

        # scene 클래스를 가진 div 찾기
        scene_divs = soup.find_all('div', class_='scene')
        if not scene_divs:
            # id="sceneN" 패턴 시도
            scene_divs = soup.find_all('div', id=re.compile(r'scene\d+', re.I))

        if not scene_divs:
            return False

        for idx, div in enumerate(scene_divs):
            # 씬 ID 추출
            scene_id = idx + 1
            if div.get('id'):
                id_match = re.search(r'(\d+)', div.get('id'))
                if id_match:
                    scene_id = int(id_match.group(1))

            # HTML 문자열
            div_html = str(div)

            # 원본 HTML에서 위치 찾기
            start_pos = self.current_html.find(div_html)
            end_pos = start_pos + len(div_html) if start_pos >= 0 else -1

            # 텍스트 추출
            text = ""
            sub = ""

            h1 = div.find(['h1', 'h2', 'h3'])
            if h1:
                text = h1.get_text(strip=True)

            p = div.find('p')
            if p:
                sub = p.get_text(strip=True)

            self.scenes.append(HTMLSceneData(
                scene_id=scene_id,
                scene_index=idx,
                html_content=div_html,
                text=text[:50] if text else f"씬 {scene_id}",
                sub=sub[:100] if sub else "",
                start_pos=start_pos,
                end_pos=end_pos,
                format_type="html_element"
            ))

        return len(self.scenes) > 0

    # ============================================================
    # 씬 조회
    # ============================================================

    def get_scene_count(self) -> int:
        """전체 씬 수"""
        return len(self.scenes)

    def get_scene_list(self) -> List[Dict]:
        """씬 목록 (UI용)"""
        return [
            {
                "scene_id": s.scene_id,
                "scene_index": s.scene_index,
                "text": s.text,
                "sub": s.sub,
                "format_type": s.format_type
            }
            for s in self.scenes
        ]

    def get_scene(self, scene_id: int) -> Optional[HTMLSceneData]:
        """특정 씬 조회 (scene_id로)"""
        for s in self.scenes:
            if s.scene_id == scene_id:
                return s
        return None

    def get_scene_by_index(self, index: int) -> Optional[HTMLSceneData]:
        """특정 씬 조회 (0-based index로)"""
        if 0 <= index < len(self.scenes):
            return self.scenes[index]
        return None

    def get_scene_html(self, scene_id: int) -> Optional[str]:
        """특정 씬의 HTML 코드 반환"""
        scene = self.get_scene(scene_id)
        return scene.html_content if scene else None

    # ============================================================
    # 씬 수정
    # ============================================================

    def replace_scene(
        self,
        scene_id: int,
        new_html: str,
        description: str = ""
    ) -> Tuple[bool, str]:
        """
        특정 씬의 HTML 교체

        Args:
            scene_id: 씬 ID
            new_html: 새 HTML 코드
            description: 수정 설명 (이력용)

        Returns:
            (성공여부, 메시지)
        """
        scene = self.get_scene(scene_id)
        if not scene:
            return False, f"씬 {scene_id}을(를) 찾을 수 없습니다."

        # 유효성 검사
        if not new_html.strip():
            return False, "새 HTML 코드가 비어있습니다."

        # 형식 맞춤 검사
        if scene.format_type == "scenedata":
            # sceneData 객체 형식 검증
            if not (new_html.strip().startswith('{') and new_html.strip().endswith('}')):
                return False, "sceneData 형식: { } 로 감싸진 객체여야 합니다."

        # 원본 저장
        original_html = scene.html_content

        # 수정 이력 기록
        record = SceneEditRecord(
            scene_id=scene_id,
            timestamp=datetime.now().isoformat(),
            original_html=original_html,
            modified_html=new_html,
            description=description
        )
        self.edit_history.append(record)

        # HTML 교체
        if scene.start_pos >= 0 and scene.end_pos >= 0:
            # 위치 기반 교체 (정확함)
            self.current_html = (
                self.current_html[:scene.start_pos] +
                new_html +
                self.current_html[scene.end_pos:]
            )
        else:
            # 문자열 교체 (폴백)
            self.current_html = self.current_html.replace(original_html, new_html, 1)

        # 씬 데이터 업데이트
        scene.html_content = new_html

        # 위치 재계산 (다른 씬들의 위치도 조정)
        diff = len(new_html) - len(original_html)
        scene_idx = self.scenes.index(scene)

        for i in range(scene_idx + 1, len(self.scenes)):
            self.scenes[i].start_pos += diff
            self.scenes[i].end_pos += diff

        scene.end_pos = scene.start_pos + len(new_html)

        return True, f"씬 {scene_id} 수정 완료"

    def restore_scene(self, scene_id: int) -> Tuple[bool, str]:
        """
        씬을 원래 HTML로 복원

        Args:
            scene_id: 복원할 씬 ID

        Returns:
            (성공여부, 메시지)
        """
        # 이 씬의 수정 이력 찾기 (역순으로)
        for record in reversed(self.edit_history):
            if record.scene_id == scene_id:
                # 원본으로 교체
                success, msg = self.replace_scene(
                    scene_id,
                    record.original_html,
                    "원본 복원"
                )
                if success:
                    # 복원 시 이력에서 제거 (마지막 2개: 수정 + 복원)
                    self.edit_history = self.edit_history[:-2]
                    return True, f"씬 {scene_id}이(가) 원본으로 복원되었습니다."
                return False, msg

        return False, f"씬 {scene_id}의 수정 이력을 찾을 수 없습니다."

    def restore_all(self) -> Tuple[bool, str]:
        """모든 수정 취소, 원본으로 복원"""
        self.current_html = self.original_html
        self.edit_history.clear()
        self._parse_scenes()  # 씬 재파싱
        return True, "모든 수정이 취소되고 원본으로 복원되었습니다."

    # ============================================================
    # 이력 관리
    # ============================================================

    def get_edit_history(self) -> List[Dict]:
        """수정 이력 조회"""
        return [
            {
                "scene_id": r.scene_id,
                "timestamp": r.timestamp,
                "description": r.description
            }
            for r in self.edit_history
        ]

    def get_modified_scenes(self) -> List[int]:
        """수정된 씬 ID 목록"""
        return list(set(r.scene_id for r in self.edit_history))

    def is_scene_modified(self, scene_id: int) -> bool:
        """특정 씬이 수정되었는지 확인"""
        return any(r.scene_id == scene_id for r in self.edit_history)

    # ============================================================
    # HTML 저장/내보내기
    # ============================================================

    def get_current_html(self) -> str:
        """현재 (수정된) HTML 반환"""
        return self.current_html

    def get_original_html(self) -> str:
        """원본 HTML 반환"""
        return self.original_html

    def save_to_file(self, output_path: str = None) -> Tuple[bool, str]:
        """수정된 HTML을 파일로 저장"""
        if not output_path:
            if self.source_path:
                p = Path(self.source_path)
                output_path = str(p.parent / f"{p.stem}_edited{p.suffix}")
            else:
                return False, "저장 경로를 지정해주세요."

        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(self.current_html)
            return True, f"저장 완료: {output_path}"
        except Exception as e:
            return False, f"저장 실패: {e}"

    def get_diff_summary(self) -> Dict:
        """수정 사항 요약"""
        modified_count = len(self.get_modified_scenes())
        total_edits = len(self.edit_history)

        return {
            "total_scenes": len(self.scenes),
            "modified_scenes": modified_count,
            "total_edits": total_edits,
            "has_changes": modified_count > 0,
            "original_size": len(self.original_html),
            "current_size": len(self.current_html),
            "size_diff": len(self.current_html) - len(self.original_html)
        }


# ============================================================
# 세션 기반 편집기 관리
# ============================================================

def get_scene_editor(
    html_content: str = None,
    source_path: str = "",
    force_new: bool = False
) -> Optional[HTMLSceneEditor]:
    """
    세션에서 편집기 인스턴스 가져오기/생성

    Args:
        html_content: HTML 콘텐츠 (새로 생성 시)
        source_path: 소스 경로
        force_new: True면 기존 인스턴스 무시하고 새로 생성

    Returns:
        HTMLSceneEditor 인스턴스
    """
    import streamlit as st

    session_key = "html_scene_editor"

    if force_new or session_key not in st.session_state:
        if html_content:
            editor = HTMLSceneEditor(html_content, source_path)
            st.session_state[session_key] = editor
            return editor
        return None

    return st.session_state.get(session_key)


def clear_scene_editor():
    """세션에서 편집기 제거"""
    import streamlit as st
    if "html_scene_editor" in st.session_state:
        del st.session_state["html_scene_editor"]
