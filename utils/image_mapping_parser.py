# -*- coding: utf-8 -*-
"""
AI 씬-이미지 매핑 결과 파서
다양한 입력 형식을 표준화된 딕셔너리로 변환

지원 형식:
- JSON: {"mapping": [{"scene": 1, "image": "file.jpg", "reason": "..."}, ...]}
- CSV: scene,image,reason
- Text: Scene 1: file.jpg 또는 Scene 1 ... 이미지: file.jpg
"""

import re
import json
import csv
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


class ImageMappingParser:
    """AI 매핑 결과를 파싱하는 클래스"""

    def __init__(self):
        self.supported_formats = ['json', 'csv', 'text']

    def detect_format(self, content: str) -> str:
        """입력 내용의 형식 자동 감지"""
        content = content.strip()

        # JSON 감지
        if content.startswith('{') or content.startswith('['):
            try:
                json.loads(content)
                return 'json'
            except json.JSONDecodeError:
                pass

        # CSV 감지 (첫 줄에 scene,image 포함)
        first_line = content.split('\n')[0].lower()
        if 'scene' in first_line and 'image' in first_line and ',' in first_line:
            return 'csv'

        # 텍스트 형식 감지
        if re.search(r'scene\s*\d+', content, re.IGNORECASE):
            return 'text'

        # 씬 번호만 있는 간단한 형식
        if re.search(r'^\d+\s*[:\-]', content, re.MULTILINE):
            return 'text'

        return 'unknown'

    def parse(self, content: str, format_type: Optional[str] = None) -> Dict[int, Dict[str, Any]]:
        """
        매핑 내용을 파싱하여 표준 딕셔너리로 반환

        Args:
            content: AI 매핑 결과 문자열
            format_type: 'json', 'csv', 'text' 또는 None (자동 감지)

        Returns:
            {씬번호: {'image': 파일명, 'reason': 이유}} 딕셔너리
        """
        if format_type is None:
            format_type = self.detect_format(content)

        if format_type == 'json':
            return self._parse_json(content)
        elif format_type == 'csv':
            return self._parse_csv(content)
        elif format_type == 'text':
            return self._parse_text(content)
        else:
            raise ValueError(f"지원하지 않는 형식입니다: {format_type}")

    def _parse_json(self, content: str) -> Dict[int, Dict[str, Any]]:
        """JSON 형식 파싱"""
        data = json.loads(content)
        result = {}

        # 배열 형식
        if isinstance(data, list):
            mappings = data
        # 객체 형식 (mapping 키 포함)
        elif isinstance(data, dict) and 'mapping' in data:
            mappings = data['mapping']
        else:
            raise ValueError("JSON 형식이 올바르지 않습니다. 'mapping' 배열이 필요합니다.")

        for item in mappings:
            scene_num = int(item.get('scene', 0))
            image = item.get('image') or item.get('filename') or item.get('file')
            reason = item.get('reason', '')

            if scene_num > 0:
                # null, None, 빈 문자열, "(비워둠)" 처리
                if image and str(image).lower() not in ['null', 'none', '', '(비워둠)', '비워둠']:
                    result[scene_num] = {
                        'image': str(image).strip(),
                        'reason': reason if reason else ''
                    }

        return result

    def _parse_csv(self, content: str) -> Dict[int, Dict[str, Any]]:
        """CSV 형식 파싱"""
        result = {}
        reader = csv.DictReader(StringIO(content))

        for row in reader:
            # 다양한 컬럼명 지원
            scene_num = int(row.get('scene') or row.get('Scene') or row.get('씬') or 0)
            image = row.get('image') or row.get('Image') or row.get('이미지') or row.get('filename') or ''
            reason = row.get('reason') or row.get('Reason') or row.get('이유') or ''

            if scene_num > 0 and image and image.strip():
                if image.lower() not in ['null', 'none', '(비워둠)', '비워둠']:
                    result[scene_num] = {
                        'image': image.strip(),
                        'reason': reason.strip()
                    }

        return result

    def _parse_text(self, content: str) -> Dict[int, Dict[str, Any]]:
        """텍스트 형식 파싱 (AI 출력 원본 형식)"""
        result = {}

        lines = content.split('\n')
        current_scene = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Scene 번호 추출 (Scene 1, 씬 1, 1: 등)
            scene_match = re.search(r'(?:Scene|씬)\s*(\d+)', line, re.IGNORECASE)
            if scene_match:
                current_scene = int(scene_match.group(1))

                # 같은 줄에 이미지 파일명이 있는지 확인 (Scene 1: file.jpg)
                inline_image = re.search(r'(?:Scene|씬)\s*\d+\s*[:\-\s]+\s*([^\s\n]+\.(jpg|jpeg|png|gif|webp))', line, re.IGNORECASE)
                if inline_image:
                    image_name = inline_image.group(1).strip()
                    if image_name.lower() not in ['(비워둠)', '비워둠', 'null', 'none', '']:
                        result[current_scene] = {
                            'image': image_name,
                            'reason': ''
                        }
                continue

            # 이미지 파일명 추출
            if current_scene is not None:
                # "• 이미지: filename.jpg" 또는 "이미지: filename.jpg"
                image_match = re.search(r'(?:•\s*)?(?:이미지|image|파일)\s*[:\s]\s*([^\n]+)', line, re.IGNORECASE)
                if image_match:
                    image = image_match.group(1).strip()
                    if image and image.lower() not in ['(비워둠)', '비워둠', 'null', 'none', '']:
                        result[current_scene] = {
                            'image': image,
                            'reason': ''
                        }
                    continue

                # "• 이유: ..." 추출
                reason_match = re.search(r'(?:•\s*)?(?:이유|reason)\s*[:\s]\s*([^\n]+)', line, re.IGNORECASE)
                if reason_match and current_scene in result:
                    result[current_scene]['reason'] = reason_match.group(1).strip()

        # 대안 패턴으로 재시도 (간단한 형식: "1: file.jpg")
        if not result:
            simple_pattern = re.findall(r'^(\d+)\s*[:\-]\s*([^\s\n]+\.(jpg|jpeg|png|gif|webp))', content, re.IGNORECASE | re.MULTILINE)
            for match in simple_pattern:
                scene_num = int(match[0])
                image = match[1].strip()
                if image.lower() not in ['(비워둠)', '비워둠', 'null', 'none', '']:
                    result[scene_num] = {
                        'image': image,
                        'reason': ''
                    }

        return result

    def validate_mapping(
        self,
        mapping: Dict[int, Dict[str, Any]],
        image_folder: str,
        total_scenes: Optional[int] = None
    ) -> Tuple[Dict[int, Dict[str, Any]], List[str]]:
        """
        매핑 결과 검증 및 파일 존재 여부 확인

        Returns:
            (유효한 매핑, 경고 메시지 리스트)
        """
        valid_mapping = {}
        warnings = []
        folder_path = Path(image_folder)

        if not folder_path.exists():
            warnings.append(f"이미지 폴더가 존재하지 않습니다: {image_folder}")
            return mapping, warnings

        # 폴더 내 파일 목록 (대소문자 무시 매칭용)
        existing_files = {f.name.lower(): f.name for f in folder_path.iterdir() if f.is_file()}

        for scene_num, data in mapping.items():
            image_name = data['image']

            # 파일 존재 확인 (대소문자 무시)
            if image_name.lower() in existing_files:
                # 실제 파일명으로 교체
                actual_filename = existing_files[image_name.lower()]
                valid_mapping[scene_num] = {
                    'image': actual_filename,
                    'reason': data.get('reason', ''),
                    'path': str(folder_path / actual_filename)
                }
            else:
                warnings.append(f"씬 {scene_num}: 파일을 찾을 수 없음 - {image_name}")

        # 씬 범위 검증
        if total_scenes and valid_mapping:
            max_scene = max(valid_mapping.keys())
            if max_scene > total_scenes:
                warnings.append(f"매핑된 최대 씬 번호({max_scene})가 총 씬 수({total_scenes})를 초과합니다.")

        return valid_mapping, warnings


def parse_ai_mapping(content: str, image_folder: str, total_scenes: Optional[int] = None) -> Tuple[Dict[int, Dict[str, Any]], List[str]]:
    """
    AI 매핑 결과를 파싱하고 검증하는 편의 함수

    Args:
        content: AI 매핑 결과 문자열
        image_folder: 이미지 파일이 있는 폴더 경로
        total_scenes: 총 씬 수 (선택)

    Returns:
        (검증된 매핑 딕셔너리, 경고 메시지 리스트)
    """
    parser = ImageMappingParser()
    mapping = parser.parse(content)
    return parser.validate_mapping(mapping, image_folder, total_scenes)


def generate_mapping_template(total_scenes: int, format_type: str = 'json') -> str:
    """
    AI에게 제공할 매핑 템플릿 생성

    Args:
        total_scenes: 총 씬 수
        format_type: 'json', 'csv', 'text'

    Returns:
        템플릿 문자열
    """
    if format_type == 'json':
        template = {
            "mapping": [
                {"scene": i, "image": f"씬{i}에_맞는_이미지파일명.jpg", "reason": "선택 이유"}
                if i <= 3 else {"scene": i, "image": None}
                for i in range(1, min(total_scenes + 1, 6))
            ],
            "total_scenes": total_scenes
        }
        return json.dumps(template, ensure_ascii=False, indent=2)

    elif format_type == 'csv':
        lines = ["scene,image,reason"]
        for i in range(1, min(total_scenes + 1, 6)):
            if i <= 3:
                lines.append(f'{i},씬{i}에_맞는_이미지파일명.jpg,선택 이유')
            else:
                lines.append(f'{i},,')
        return '\n'.join(lines)

    else:  # text
        lines = []
        for i in range(1, min(total_scenes + 1, 6)):
            if i <= 3:
                lines.append(f'Scene {i}: 씬{i}에_맞는_이미지파일명.jpg')
            else:
                lines.append(f'Scene {i}: (비워둠)')
        return '\n'.join(lines)


def get_image_folder_listing(folder_path: str) -> str:
    """이미지 폴더 파일 목록을 AI 프롬프트용 텍스트로 변환"""
    folder = Path(folder_path)
    if not folder.exists():
        return "폴더가 존재하지 않습니다."

    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
    files = [f.name for f in folder.iterdir()
             if f.is_file() and f.suffix.lower() in image_extensions]

    if not files:
        return "이미지 파일이 없습니다."

    # 파일명 목록 생성
    listing = f"총 {len(files)}개 이미지:\n"
    for f in sorted(files):
        listing += f"- {f}\n"

    return listing
