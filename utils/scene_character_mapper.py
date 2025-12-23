# -*- coding: utf-8 -*-
"""
씬-캐릭터 자동 매핑 모듈 v2

씬 분석 데이터에서 캐릭터 언급을 자동 감지하여 매핑

기능:
- 씬 분석 결과(scene_analysis.json)에서 "등장 캐릭터" 필드 파싱
- 등록된 캐릭터와 정확/부분/유사 매칭
- 자동 매핑 결과 저장/로드
- 매핑 신뢰도 점수 계산
- 매핑 요약 정보 제공
"""

import os
import json
import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class SceneCharacterMapper:
    """
    씬-캐릭터 자동 매핑

    씬 분석 데이터에서 캐릭터 언급을 감지하고
    등록된 캐릭터와 매핑합니다.
    """

    # 매칭 신뢰도 임계값
    EXACT_MATCH_SCORE = 1.0      # 정확히 일치
    PARTIAL_MATCH_SCORE = 0.8   # 부분 일치 (포함)
    FUZZY_THRESHOLD = 0.7       # 유사 매칭 최소 임계값

    def __init__(self, project_path: str):
        """
        Args:
            project_path: 프로젝트 경로 (캐릭터 폴더 포함)
        """
        self.project_path = Path(project_path)
        self.characters_dir = self.project_path / "characters"
        self.data_dir = self.project_path / "data"
        self.mappings_file = self.data_dir / "scene_character_mappings.json"

        # 데이터 디렉토리 생성
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 캐릭터 이름 인덱스 빌드
        self._name_index: Dict[str, dict] = {}
        self._build_name_index()

    def _build_name_index(self) -> Dict[str, dict]:
        """
        등록된 캐릭터의 이름 인덱스 생성

        Returns:
            {이름변형: {id, name, image_path}, ...}
        """
        self._name_index = {}

        if not self.characters_dir.exists():
            return self._name_index

        # 캐릭터 폴더 순회
        for char_path in self.characters_dir.iterdir():
            if not char_path.is_dir():
                continue

            char_folder = char_path.name

            # 캐릭터 메타데이터 로드
            meta_file = char_path / "metadata.json"

            if meta_file.exists():
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta = json.load(f)

                    char_id = char_folder
                    char_name = meta.get('name', char_folder)

                    # 대표 이미지 찾기
                    image_path = self._find_character_image(char_path, meta)

                    char_info = {
                        'id': char_id,
                        'name': char_name,
                        'image_path': image_path,
                        'aliases': meta.get('aliases', []),
                        'metadata': meta
                    }

                    # 이름 변형 등록
                    self._register_name_variants(char_name, char_info)

                    # 별칭도 등록
                    for alias in meta.get('aliases', []):
                        self._register_name_variants(alias, char_info)

                except Exception as e:
                    logger.warning(f"캐릭터 메타 로드 실패 ({char_folder}): {e}")
            else:
                # 메타데이터 없으면 폴더명 사용
                image_path = self._find_character_image(char_path, {})

                char_info = {
                    'id': char_folder,
                    'name': char_folder,
                    'image_path': image_path,
                    'aliases': [],
                    'metadata': {}
                }

                self._register_name_variants(char_folder, char_info)

        logger.info(f"캐릭터 인덱스: {len(set(c['id'] for c in self._name_index.values()))}명, {len(self._name_index)}개 키워드")
        return self._name_index

    def _find_character_image(self, char_path: Path, meta: dict) -> Optional[str]:
        """캐릭터 대표 이미지 찾기"""
        char_path = Path(char_path)

        # 메타에 지정된 이미지
        if meta.get('default_image'):
            img_path = char_path / meta['default_image']
            if img_path.exists():
                return str(img_path)

        # 이미지 파일 검색
        image_exts = ['.png', '.jpg', '.jpeg', '.webp']

        for f in char_path.iterdir():
            if f.suffix.lower() in image_exts:
                return str(f)

        return None

    def _parse_character_field(self, char_field: str) -> List[str]:
        """
        씬 분석의 character 필드 파싱

        예시:
        - "자말 카슈끄지" → ["자말 카슈끄지"]
        - "무함마드, 빈 살만" → ["무함마드", "빈 살만"]
        - "자말 카슈끄지, 무함마드 빈 살만" → ["자말 카슈끄지", "무함마드 빈 살만"]
        """
        if not char_field:
            return []

        # 쉼표로 분리
        parts = [p.strip() for p in char_field.split(',')]

        # 빈 문자열 제거
        return [p for p in parts if p]

    def load_scene_analysis(self) -> List[dict]:
        """
        씬 분석 결과 로드

        여러 가능한 위치에서 데이터 찾기
        (우선순위: analysis 폴더 > data 폴더 > 프로젝트 루트)
        """
        # 분석 폴더 경로
        analysis_dir = self.project_path / "analysis"

        possible_files = [
            # 1순위: 씬 분석 페이지가 저장하는 위치
            analysis_dir / "full_analysis.json",
            analysis_dir / "scenes.json",
            # 2순위: data 폴더
            self.data_dir / "scene_analysis.json",
            self.data_dir / "scenes.json",
            # 3순위: 프로젝트 루트
            self.project_path / "scene_analysis.json",
            self.project_path / "analysis_result.json",
        ]

        for file_path in possible_files:
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # 'scenes' 키가 있으면 사용
                    if 'scenes' in data:
                        scenes = data['scenes']
                    elif isinstance(data, list):
                        scenes = data
                    else:
                        continue

                    logger.info(f"씬 분석 로드: {file_path.name} ({len(scenes)}개 씬)")
                    return scenes

                except Exception as e:
                    logger.warning(f"씬 분석 로드 실패 ({file_path}): {e}")

        logger.warning("씬 분석 데이터 없음")
        return []

    def _register_name_variants(self, name: str, char_info: dict):
        """이름의 다양한 변형을 인덱스에 등록"""
        if not name:
            return

        # 원본
        self._name_index[name.lower()] = char_info

        # 공백 제거
        self._name_index[name.replace(" ", "").lower()] = char_info

        # 특수문자 제거
        clean = re.sub(r'[^\w\s가-힣]', '', name).lower()
        if clean:
            self._name_index[clean] = char_info

    def _find_character_in_text(self, text: str) -> Optional[dict]:
        """
        텍스트에서 캐릭터 찾기

        Args:
            text: 분석할 텍스트 (씬 설명, 대사 등)

        Returns:
            {character_id, character_name, confidence, match_type} 또는 None
        """
        if not text or not self._name_index:
            return None

        text_lower = text.lower()
        text_clean = re.sub(r'[^\w\s가-힣]', '', text).lower()

        best_match = None
        best_score = 0

        for name_variant, char_info in self._name_index.items():
            # 1. 정확 일치 (단어 경계)
            pattern = r'\b' + re.escape(name_variant) + r'\b'
            if re.search(pattern, text_lower):
                score = self.EXACT_MATCH_SCORE
                if score > best_score:
                    best_score = score
                    best_match = {
                        'character_id': char_info['id'],
                        'character_name': char_info['name'],
                        'image_path': char_info['image_path'],
                        'confidence': score,
                        'match_type': 'exact'
                    }
                continue

            # 2. 부분 일치 (포함)
            if name_variant in text_lower or name_variant in text_clean:
                score = self.PARTIAL_MATCH_SCORE
                if score > best_score:
                    best_score = score
                    best_match = {
                        'character_id': char_info['id'],
                        'character_name': char_info['name'],
                        'image_path': char_info['image_path'],
                        'confidence': score,
                        'match_type': 'partial'
                    }
                continue

            # 3. 유사 매칭 (Fuzzy)
            # 텍스트의 각 단어와 비교
            words = text_clean.split()
            for word in words:
                if len(word) < 2:
                    continue

                similarity = SequenceMatcher(None, name_variant, word).ratio()

                if similarity >= self.FUZZY_THRESHOLD:
                    score = similarity * 0.7  # 유사 매칭은 가중치 낮춤
                    if score > best_score:
                        best_score = score
                        best_match = {
                            'character_id': char_info['id'],
                            'character_name': char_info['name'],
                            'image_path': char_info['image_path'],
                            'confidence': score,
                            'match_type': 'fuzzy'
                        }

        return best_match

    def _extract_names_from_scene(self, scene_data: dict) -> Tuple[List[str], str]:
        """
        씬 데이터에서 캐릭터/인물 이름 추출

        다양한 형식 지원:
        - persons: ["이름1", "이름2"] (v2.3 형식)
        - characters: [{"name": "이름", ...}, ...] (v2.3 형식)
        - character: "이름1, 이름2" (구 형식)
        - characters: "이름1, 이름2" (구 형식)

        Returns:
            (이름 리스트, 원본 필드 문자열)
        """
        names = []
        original_field = ""

        # 1. persons 필드 (v2.3 형식: 실제 인물 리스트)
        persons = scene_data.get('persons', [])
        if persons:
            if isinstance(persons, list):
                for p in persons:
                    if isinstance(p, str) and p.strip():
                        names.append(p.strip())
                    elif isinstance(p, dict) and p.get('name'):
                        names.append(p['name'])
                original_field = ", ".join(names)

        # 2. characters 필드 (v2.3 형식: 캐릭터 IP 리스트)
        characters = scene_data.get('characters', [])
        if characters:
            if isinstance(characters, list):
                for c in characters:
                    if isinstance(c, str) and c.strip():
                        names.append(c.strip())
                    elif isinstance(c, dict) and c.get('name'):
                        names.append(c['name'])
                if not original_field:
                    original_field = ", ".join([c.get('name', str(c)) if isinstance(c, dict) else str(c) for c in characters])
                else:
                    original_field += ", " + ", ".join([c.get('name', str(c)) if isinstance(c, dict) else str(c) for c in characters])
            elif isinstance(characters, str) and characters.strip():
                # 구 형식: 쉼표 구분 문자열
                names.extend(self._parse_character_field(characters))
                if not original_field:
                    original_field = characters

        # 3. character 필드 (구 형식: 단일 문자열)
        character = scene_data.get('character', '')
        if character and isinstance(character, str) and character.strip():
            names.extend(self._parse_character_field(character))
            if not original_field:
                original_field = character

        # 4. 등장인물 필드 (한글 키)
        persons_kr = scene_data.get('등장인물', [])
        if persons_kr:
            if isinstance(persons_kr, list):
                for p in persons_kr:
                    if isinstance(p, str) and p.strip():
                        names.append(p.strip())
            elif isinstance(persons_kr, str):
                names.extend(self._parse_character_field(persons_kr))
            if not original_field and names:
                original_field = ", ".join(names[-len(persons_kr):] if isinstance(persons_kr, list) else [persons_kr])

        # 중복 제거 (순서 유지)
        seen = set()
        unique_names = []
        for name in names:
            if name.lower() not in seen:
                seen.add(name.lower())
                unique_names.append(name)

        return unique_names, original_field

    def analyze_scene(self, scene_data: dict) -> Optional[Dict]:
        """
        단일 씬 분석하여 캐릭터 매핑

        Args:
            scene_data: 씬 데이터
                - scene_num 또는 scene_id 또는 number: 씬 번호
                - persons: 인물 이름 리스트 (v2.3)
                - characters: 캐릭터 IP 리스트 (v2.3)
                - character: 구 형식 캐릭터 이름
                - description: 씬 설명
                - narration: 나레이션

        Returns:
            매핑 결과 또는 None
        """
        scene_num = (
            scene_data.get('scene_num') or
            scene_data.get('scene_id') or
            scene_data.get('number', 0)
        )

        # 1단계: persons/characters 필드에서 이름 추출
        char_names, original_field = self._extract_names_from_scene(scene_data)

        if char_names:
            for name in char_names:
                match = self._find_character_in_text(name)
                if match:
                    return {
                        'scene_num': scene_num,
                        'character_id': match['character_id'],
                        'character_name': match['character_name'],
                        'image_path': match['image_path'],
                        'confidence': match['confidence'],
                        'match_type': match['match_type'],
                        'source_field': 'persons/characters',
                        'original_name': original_field,
                        'auto_mapped': True
                    }

        # 2단계: 다른 텍스트 필드에서 캐릭터 찾기
        text_fields = [
            ('character_notes', scene_data.get('character_notes', '')),
            ('script', scene_data.get('script', '')),
            ('description', scene_data.get('description', '')),
            ('narration', scene_data.get('narration', '')),
            ('dialogue', scene_data.get('dialogue', '')),
            ('visual_description', scene_data.get('visual_description', '')),
        ]

        # 각 필드에서 캐릭터 찾기
        for field_name, field_text in text_fields:
            if not field_text:
                continue

            match = self._find_character_in_text(field_text)

            if match:
                return {
                    'scene_num': scene_num,
                    'character_id': match['character_id'],
                    'character_name': match['character_name'],
                    'image_path': match['image_path'],
                    'confidence': match['confidence'],
                    'match_type': match['match_type'],
                    'source_field': field_name,
                    'original_name': original_field or '',
                    'auto_mapped': True
                }

        return None

    def generate_mappings(
        self,
        scenes_data: List[dict] = None,
        default_character_id: str = None
    ) -> List[Dict]:
        """
        여러 씬에 대한 캐릭터 매핑 생성

        Args:
            scenes_data: 씬 데이터 목록 (None이면 씬분석 자동 로드)
            default_character_id: 매핑 없을 때 기본 캐릭터

        Returns:
            매핑 결과 목록
        """
        # 씬 데이터 없으면 자동 로드
        if scenes_data is None:
            scenes_data = self.load_scene_analysis()

        if not scenes_data:
            logger.warning("씬 데이터 없음")
            return []

        mappings = []
        matched_count = 0

        # 기본 캐릭터 정보
        default_char_info = None
        if default_character_id:
            for char_info in self._name_index.values():
                if char_info['id'] == default_character_id:
                    default_char_info = char_info
                    break

        for scene_data in scenes_data:
            mapping = self.analyze_scene(scene_data)

            if mapping:
                mappings.append(mapping)
                matched_count += 1
            elif default_char_info:
                # 매핑 없으면 기본 캐릭터 사용
                scene_num = (
                    scene_data.get('scene_num') or
                    scene_data.get('scene_id') or
                    scene_data.get('number', 0)
                )
                # 원본 이름 정보 추출
                _, original_name = self._extract_names_from_scene(scene_data)
                mappings.append({
                    'scene_num': scene_num,
                    'character_id': default_char_info['id'],
                    'character_name': default_char_info['name'],
                    'image_path': default_char_info['image_path'],
                    'confidence': 0.0,
                    'match_type': 'default',
                    'source_field': None,
                    'original_name': original_name or '없음',
                    'auto_mapped': True
                })

        logger.info(f"매핑 생성: {matched_count}/{len(scenes_data)}개 씬 자동 매칭")
        return mappings

    def save_mappings(self, mappings: List[Dict]) -> bool:
        """매핑 결과 저장"""
        try:
            with open(self.mappings_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'version': '2.0',
                    'auto_generated': True,
                    'source': 'scene_analysis_matcher',
                    'mappings': mappings
                }, f, ensure_ascii=False, indent=2)

            logger.info(f"매핑 저장: {len(mappings)}개 씬 -> {self.mappings_file}")
            return True

        except Exception as e:
            logger.error(f"매핑 저장 실패: {e}")
            return False

    def load_mappings(self) -> List[Dict]:
        """저장된 매핑 로드"""
        if not self.mappings_file.exists():
            return []

        try:
            with open(self.mappings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return data.get('mappings', [])

        except Exception as e:
            logger.error(f"매핑 로드 실패: {e}")
            return []

    def get_mapping_summary(self) -> Dict:
        """
        매핑 요약 정보

        Returns:
            {
                'total': 총 매핑 수,
                'matched': 자동 매칭 수,
                'default': 기본값 사용 수,
                'by_character': {캐릭터명: 등장횟수, ...}
            }
        """
        mappings = self.load_mappings()

        if not mappings:
            return {
                'total': 0,
                'matched': 0,
                'default': 0,
                'by_character': {}
            }

        by_char = {}
        matched = 0
        default = 0

        for m in mappings:
            char_name = m.get('character_name', 'Unknown')
            by_char[char_name] = by_char.get(char_name, 0) + 1

            if m.get('match_type') == 'default':
                default += 1
            else:
                matched += 1

        return {
            'total': len(mappings),
            'matched': matched,
            'default': default,
            'by_character': by_char
        }

    def get_character_for_scene(self, scene_num: int) -> Optional[dict]:
        """
        특정 씬의 캐릭터 정보 조회

        Args:
            scene_num: 씬 번호

        Returns:
            캐릭터 정보 또는 None
        """
        mappings = self.load_mappings()

        for mapping in mappings:
            if mapping.get('scene_num') == scene_num:
                return mapping

        return None

    def get_available_characters(self) -> List[dict]:
        """등록된 캐릭터 목록 반환"""
        # 중복 제거 (id 기준)
        seen_ids = set()
        characters = []

        for char_info in self._name_index.values():
            char_id = char_info['id']
            if char_id not in seen_ids:
                seen_ids.add(char_id)
                characters.append({
                    'id': char_id,
                    'name': char_info['name'],
                    'image_path': char_info['image_path']
                })

        return characters

    def refresh_index(self):
        """캐릭터 인덱스 새로고침"""
        self._build_name_index()


# 편의 함수들

def create_mapper(project_path: str) -> SceneCharacterMapper:
    """매퍼 인스턴스 생성"""
    return SceneCharacterMapper(project_path)


def get_scene_character_matcher(project_path: str) -> SceneCharacterMapper:
    """씬-캐릭터 매처 인스턴스 생성 (별칭)"""
    return SceneCharacterMapper(project_path)


def auto_map_scenes(
    project_path: str,
    scenes_data: List[dict] = None,
    default_character_id: str = None
) -> List[Dict]:
    """
    씬 목록에 캐릭터 자동 매핑

    Args:
        project_path: 프로젝트 경로
        scenes_data: 씬 데이터 목록 (None이면 자동 로드)
        default_character_id: 기본 캐릭터 ID

    Returns:
        매핑 결과 목록
    """
    mapper = SceneCharacterMapper(project_path)
    return mapper.generate_mappings(scenes_data, default_character_id)


def get_scene_character(project_path: str, scene_num: int) -> Optional[dict]:
    """특정 씬의 캐릭터 조회"""
    mapper = SceneCharacterMapper(project_path)
    return mapper.get_character_for_scene(scene_num)


def list_available_characters(project_path: str) -> List[dict]:
    """사용 가능한 캐릭터 목록"""
    mapper = SceneCharacterMapper(project_path)
    return mapper.get_available_characters()


def get_mapping_summary(project_path: str) -> Dict:
    """매핑 요약 정보 조회"""
    mapper = SceneCharacterMapper(project_path)
    return mapper.get_mapping_summary()
