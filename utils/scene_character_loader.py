# -*- coding: utf-8 -*-
"""
씬-캐릭터 통합 로더 (v2.0 - 성능 최적화)

기능:
1. 씬 데이터 로드 (여러 경로 시도)
2. 캐릭터-씬 매핑
3. 세션 상태 캐싱
4. 캐릭터 이름 유효성 검증
5. ✅ v2.0: 로그 출력 최소화 (DEBUG 모드에서만 상세 로그)

Problem 56 수정: 씬 분석 결과가 캐릭터 관리에 연동 안 되는 문제 해결
Problem 49 수정: 문장이 캐릭터로 잘못 추출되는 문제 해결
"""

import os
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ============================================================
# 설정
# ============================================================
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"


# ============================================================
# 🔴 캐릭터 이름 유효성 검증 (Problem 49)
# scene_analyzer.py의 is_valid_person_name과 동일한 로직
# ============================================================

# 잘못된 캐릭터로 추출되면 안 되는 단어 목록
INVALID_CHARACTER_WORDS = {
    # 조사/어미가 붙은 패턴
    '의', '이', '가', '은', '는', '를', '을', '에서', '로', '으로',
    '에게', '한테', '께', '와', '과', '이다', '이고', '이며',

    # 일반 명사
    '회사', '기업', '브랜드', '제품', '서비스', '시장', '산업',
    '경쟁', '성장', '매출', '이익', '수익', '투자', '가치',
    '콘텐츠', '플랫폼', '사업', '전략', '비전', '목표',

    # 직책만 (이름 없이)
    '대표', '회장', '사장', '이사', '임원', '창업자', '설립자',
    'ceo', 'cfo', 'cto', 'coo',

    # 국가/지역
    '한국', '미국', '중국', '일본', '사우디', '유럽', '아시아',

    # 일반 동사/형용사 어근
    '하는', '되는', '있는', '없는', '같은', '다른', '모든',
}


def is_valid_character_name(name: str) -> bool:
    """
    유효한 캐릭터(사람) 이름인지 검증

    Args:
        name: 검증할 이름

    Returns:
        유효하면 True, 무효하면 False
    """
    if not name or len(name) < 2 or len(name) > 10:
        return False

    name_clean = name.strip()
    name_lower = name_clean.lower()

    # 금지 단어 체크
    if name_lower in INVALID_CHARACTER_WORDS:
        return False

    # 문장 어미 패턴 감지
    sentence_endings = [
        '면', '해서', '니까', '으니', '지만', '으면', '어서', '아서',
        '고서', '려고', '으려', '면서', '든지', '거나',
        '다', '요', '습니다', '입니다', '세요', '십시오',
        '네요', '군요', '지요', '죠', '음', '기에', '므로',
    ]

    # 공백이 있고 4글자 이상이면 문장일 가능성 높음
    if ' ' in name_clean and len(name_clean) >= 4:
        for ending in sentence_endings:
            if name_clean.endswith(ending):
                return False

    # 동사/형용사 패턴 감지 (5글자 이상)
    if len(name_clean) >= 5:
        verb_patterns = [
            r'[가-힣]+(하|되|이|지|시|았|었|겠|는|ㄴ|을|를|한|된|인)$',
            r'[가-힣]+(해서|해야|하면|하고|하는|했다|했음|하여)$',
            r'[가-힣]+(으면|면서|니까|지만|어서|아서|라서|려고)$',
        ]
        for pattern in verb_patterns:
            if re.search(pattern, name_clean):
                return False

    # 조사로 끝나는지 체크
    particle_endings = ['의', '이', '가', '은', '는', '를', '을', '에', '로', '과', '와', '도']
    for particle in particle_endings:
        if name_clean.endswith(particle) and len(name_clean) > 2:
            # 예외: "손정의" 같은 실제 이름
            if particle == '의' and len(name_clean) == 3 and re.match(r'^[가-힣]{3}$', name_clean):
                continue
            return False

    # 숫자만 있는지 체크
    if name_clean.isdigit():
        return False

    # 한글 자음/모음만 있는지 체크
    if re.match(r'^[ㄱ-ㅎㅏ-ㅣ]+$', name_clean):
        return False

    # 한글 이름 패턴 (2-4자)
    if re.match(r'^[가-힣]{2,4}$', name_clean):
        return True

    # 영문 이름 패턴
    if re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)+$', name_clean):
        return True

    # 아랍/외래 이름 패턴 (공백 포함 한글)
    if re.match(r'^[가-힣]+(\s+[가-힣]+)+$', name_clean):
        return True

    # 그 외 한글 포함 패턴 (5자 이하)
    if len(name_clean) <= 5 and re.search(r'[가-힣]', name_clean):
        return True

    return False


def safe_print(msg: str):
    """Windows 호환 안전한 출력"""
    try:
        print(msg)
    except UnicodeEncodeError:
        # 이모지 등 인코딩 안 되는 문자 제거
        print(msg.encode('ascii', 'replace').decode('ascii'))


def _debug_log(msg: str):
    """디버그 모드에서만 출력 (Windows 호환)"""
    if DEBUG_MODE:
        safe_print(msg)


def load_scenes_data(project_path: str = None, force_file: bool = False) -> List[Dict]:
    """
    씬 분석 결과 로드 (프로젝트 경로 기반)

    Args:
        project_path: 프로젝트 경로 (없으면 세션에서 가져옴)
        force_file: True면 세션 캐시 무시하고 파일에서 로드

    Returns:
        씬 데이터 리스트

    Note:
        프로젝트 경로가 제공되면 파일을 우선 로드하여
        프로젝트 간 데이터 혼동 방지 (Problem 56 수정)
    """
    import streamlit as st

    # 프로젝트 경로 확인
    if not project_path:
        project_path = st.session_state.get("current_project_path")

    if not project_path:
        safe_print("[Scene Loader] No project path")
        return []

    project_path = Path(project_path)
    project_key = str(project_path)

    # 프로젝트 경로 기반 캐시 키
    cache_key = f"scenes_cache_{hash(project_key) % 100000}"
    cache_path_key = f"scenes_cache_path_{hash(project_key) % 100000}"

    # 1. 캐시된 데이터가 현재 프로젝트의 것인지 확인
    if not force_file:
        cached_path = st.session_state.get(cache_path_key)
        if cached_path == project_key:
            cached_scenes = st.session_state.get(cache_key)
            if cached_scenes and isinstance(cached_scenes, list) and len(cached_scenes) > 0:
                _debug_log(f"[Scene Loader] Cache hit: {len(cached_scenes)} scenes for {project_path.name}")
                return cached_scenes

    # 2. 여러 경로에서 씬 파일 찾기 (파일 우선)
    possible_paths = [
        project_path / "analysis" / "scenes.json",           # 현재 구조 (video 디렉토리)
        project_path / "scenes.json",                        # 루트
        project_path / "data" / "scenes.json",              # data 폴더
    ]

    # 새 구조 (videos 하위)인 경우
    video_name = st.session_state.get("current_video")
    if video_name:
        possible_paths.insert(0, project_path / "videos" / video_name / "analysis" / "scenes.json")

    for path in possible_paths:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    scenes = json.load(f)

                # 리스트가 아니면 변환
                if isinstance(scenes, dict):
                    if "scenes" in scenes:
                        scenes = scenes["scenes"]
                    else:
                        scenes = [scenes]

                if scenes and len(scenes) > 0:
                    _debug_log(f"[Scene Loader] File loaded: {len(scenes)} scenes from {path}")

                    # 프로젝트별 캐시에 저장
                    st.session_state[cache_key] = scenes
                    st.session_state[cache_path_key] = project_key

                    # 기존 세션 키도 업데이트 (호환성)
                    st.session_state.analyzed_scenes = scenes
                    st.session_state.scenes = scenes

                    return scenes

            except Exception as e:
                _debug_log(f"[Scene Loader] File load failed ({path}): {e}")
                continue

    _debug_log(f"[Scene Loader] No scene file found. Tried paths:")
    for p in possible_paths:
        _debug_log(f"  - {p} (exists: {p.exists()})")

    return []


def clear_scene_cache(project_path: str = None):
    """
    특정 프로젝트의 씬 캐시 삭제

    Args:
        project_path: 프로젝트 경로 (없으면 모든 씬 관련 캐시 삭제)
    """
    import streamlit as st

    if project_path:
        project_key = str(Path(project_path))
        cache_key = f"scenes_cache_{hash(project_key) % 100000}"
        cache_path_key = f"scenes_cache_path_{hash(project_key) % 100000}"

        if cache_key in st.session_state:
            del st.session_state[cache_key]
        if cache_path_key in st.session_state:
            del st.session_state[cache_path_key]

        _debug_log(f"[Scene Loader] Cache cleared for {Path(project_path).name}")
    else:
        # 모든 씬 관련 세션 키 삭제
        keys_to_remove = []
        for key in list(st.session_state.keys()):
            if key.startswith("scenes_cache_") or key in ["analyzed_scenes", "scenes", "scene_analysis"]:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del st.session_state[key]

        _debug_log("[Scene Loader] All scene caches cleared")


def load_characters_from_analysis(project_path: str = None) -> List[Dict]:
    """
    분석 결과에서 캐릭터 데이터 로드

    Args:
        project_path: 프로젝트 경로

    Returns:
        캐릭터 데이터 리스트
    """
    import streamlit as st

    # 1. 세션 상태에서 먼저 확인
    session_keys = ["characters", "scene_characters", "extracted_characters"]
    for key in session_keys:
        if key in st.session_state and st.session_state[key]:
            data = st.session_state[key]
            if isinstance(data, list) and len(data) > 0:
                _debug_log(f"[Character Loader] Session {key}: {len(data)} characters")
                return data

    # 2. 프로젝트 경로 확인
    if not project_path:
        project_path = st.session_state.get("current_project_path")

    if not project_path:
        return []

    project_path = Path(project_path)

    # 3. 여러 경로에서 캐릭터 파일 찾기
    possible_paths = [
        project_path / "analysis" / "characters.json",
        project_path / "characters" / "characters.json",
    ]

    for path in possible_paths:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    chars = json.load(f)

                if isinstance(chars, list) and len(chars) > 0:
                    _debug_log(f"[Character Loader] File loaded: {len(chars)} chars from {path}")
                    return chars

            except Exception as e:
                _debug_log(f"[Character Loader] File load failed ({path}): {e}")
                continue

    return []


def get_character_appearances(character_name: str, scenes: List[Dict] = None) -> List[Dict]:
    """
    특정 캐릭터가 등장하는 씬 목록

    Args:
        character_name: 캐릭터 이름
        scenes: 씬 데이터 (없으면 자동 로드)

    Returns:
        캐릭터가 등장하는 씬 리스트 [{"scene_id": 1, "scene": {...}, "matched_name": "..."}, ...]
    """
    if scenes is None:
        scenes = load_scenes_data()

    if not scenes:
        _debug_log(f"[Char-Scene] No scene data")
        return []

    # 캐릭터 이름 정규화
    target_name = character_name.strip().lower().replace(" ", "")

    appearances = []

    for scene in scenes:
        scene_id = scene.get("scene_id", scene.get("id", 0))

        # 여러 키에서 캐릭터 목록 찾기
        scene_characters = []

        for key in ["characters", "character_list", "cast", "persons"]:
            if key in scene:
                chars = scene[key]
                if isinstance(chars, list):
                    for c in chars:
                        if isinstance(c, str):
                            scene_characters.append(c)
                        elif isinstance(c, dict):
                            scene_characters.append(c.get("name", c.get("name_ko", "")))
                break

        # 캐릭터 매칭 (유연하게)
        for sc in scene_characters:
            if not sc:
                continue
            sc_normalized = sc.strip().lower().replace(" ", "")

            # 정확한 매칭 또는 포함 매칭
            if (target_name == sc_normalized or
                target_name in sc_normalized or
                sc_normalized in target_name):
                appearances.append({
                    "scene_id": scene_id,
                    "scene": scene,
                    "matched_name": sc
                })
                break

    _debug_log(f"[Char-Scene] {character_name}: {len(appearances)} appearances")

    return appearances


def get_all_characters_from_scenes(scenes: List[Dict] = None, validate: bool = True) -> List[str]:
    """
    모든 씬에서 등장하는 캐릭터 이름 추출

    Args:
        scenes: 씬 데이터 (없으면 자동 로드)
        validate: True면 유효한 캐릭터 이름만 반환 (Problem 49)

    Returns:
        캐릭터 이름 리스트 (중복 제거)
    """
    if scenes is None:
        scenes = load_scenes_data()

    if not scenes:
        return []

    all_chars = set()
    filtered_count = 0

    for scene in scenes:
        for key in ["characters", "character_list", "cast", "persons"]:
            if key in scene:
                chars = scene[key]
                if isinstance(chars, list):
                    for c in chars:
                        name = None
                        if isinstance(c, str) and c.strip():
                            name = c.strip()
                        elif isinstance(c, dict):
                            name = c.get("name", c.get("name_ko", ""))
                            if name:
                                name = name.strip()

                        if name:
                            # 🔴 유효성 검증 (Problem 49)
                            if validate and not is_valid_character_name(name):
                                filtered_count += 1
                                continue
                            all_chars.add(name)
                break

    if filtered_count > 0:
        _debug_log(f"[Character Loader] Filtered {filtered_count} invalid character names")

    return sorted(list(all_chars))


def build_scene_character_map(scenes: List[Dict] = None, validate: bool = True) -> Dict[int, List[str]]:
    """
    씬별 캐릭터 맵 생성

    Args:
        scenes: 씬 데이터 (없으면 자동 로드)
        validate: True면 유효한 캐릭터 이름만 포함 (Problem 49)

    Returns:
        {scene_id: [character_names], ...}
    """
    if scenes is None:
        scenes = load_scenes_data()

    if not scenes:
        return {}

    scene_char_map = {}

    for scene in scenes:
        scene_id = scene.get("scene_id", scene.get("id", 0))
        if isinstance(scene_id, str) and scene_id.isdigit():
            scene_id = int(scene_id)

        chars = []
        for key in ["characters", "character_list", "cast", "persons"]:
            if key in scene:
                raw_chars = scene[key]
                if isinstance(raw_chars, list):
                    for c in raw_chars:
                        name = None
                        if isinstance(c, str) and c.strip():
                            name = c.strip()
                        elif isinstance(c, dict):
                            name = c.get("name", c.get("name_ko", ""))
                            if name:
                                name = name.strip()

                        if name:
                            # 🔴 유효성 검증 (Problem 49)
                            if validate and not is_valid_character_name(name):
                                continue
                            chars.append(name)
                break

        scene_char_map[scene_id] = chars

    return scene_char_map


def build_character_scene_map(scenes: List[Dict] = None, validate: bool = True) -> Dict[str, List[int]]:
    """
    캐릭터별 등장 씬 맵 생성

    Args:
        scenes: 씬 데이터 (없으면 자동 로드)
        validate: True면 유효한 캐릭터 이름만 포함 (Problem 49)

    Returns:
        {character_name: [scene_ids], ...}
    """
    scene_char_map = build_scene_character_map(scenes, validate=validate)

    char_scene_map = {}

    for scene_id, chars in scene_char_map.items():
        for char_name in chars:
            if char_name not in char_scene_map:
                char_scene_map[char_name] = []
            if scene_id not in char_scene_map[char_name]:
                char_scene_map[char_name].append(scene_id)

    # 정렬
    for char_name in char_scene_map:
        char_scene_map[char_name].sort()

    return char_scene_map


def sync_character_appearance_scenes(project_path: str = None) -> int:
    """
    캐릭터 데이터에 appearance_scenes 동기화

    분석된 씬 데이터에서 캐릭터 등장 정보를 추출하여
    analysis/characters.json의 appearance_scenes 필드 업데이트

    Args:
        project_path: 프로젝트 경로

    Returns:
        업데이트된 캐릭터 수
    """
    import streamlit as st

    if not project_path:
        project_path = st.session_state.get("current_project_path")

    if not project_path:
        return 0

    project_path = Path(project_path)

    # 씬 데이터 로드
    scenes = load_scenes_data(str(project_path))
    if not scenes:
        _debug_log("[동기화] ⚠️ 씬 데이터 없음")
        return 0

    # 캐릭터별 등장 씬 맵 생성
    char_scene_map = build_character_scene_map(scenes)

    if not char_scene_map:
        _debug_log("[Sync] No character info in scenes")
        return 0

    # 분석 캐릭터 파일 업데이트
    analysis_chars_path = project_path / "analysis" / "characters.json"

    if not analysis_chars_path.exists():
        _debug_log(f"[Sync] Analysis chars file not found: {analysis_chars_path}")
        return 0

    try:
        with open(analysis_chars_path, "r", encoding="utf-8") as f:
            chars = json.load(f)
    except Exception as e:
        _debug_log(f"[Sync] Character file load failed: {e}")
        return 0

    updated = 0

    for char in chars:
        if not isinstance(char, dict):
            continue

        name = char.get("name", char.get("name_ko", ""))
        if not name:
            continue

        # 캐릭터 이름으로 등장 씬 찾기 (유연한 매칭)
        appearance_scenes = []
        name_normalized = name.strip().lower().replace(" ", "")

        for char_name, scene_ids in char_scene_map.items():
            char_normalized = char_name.strip().lower().replace(" ", "")
            if (name_normalized == char_normalized or
                name_normalized in char_normalized or
                char_normalized in name_normalized):
                appearance_scenes = scene_ids
                break

        if appearance_scenes:
            old_scenes = char.get("appearance_scenes", [])
            if sorted(old_scenes) != sorted(appearance_scenes):
                char["appearance_scenes"] = appearance_scenes
                updated += 1
                _debug_log(f"[Sync] {name}: {old_scenes} -> {appearance_scenes}")

    if updated > 0:
        # 저장
        try:
            with open(analysis_chars_path, "w", encoding="utf-8") as f:
                json.dump(chars, f, ensure_ascii=False, indent=2)
            _debug_log(f"[Sync] {updated} characters updated")

            # 세션에도 반영
            st.session_state.characters = chars
            st.session_state.scene_characters = chars
            st.session_state.extracted_characters = chars

        except Exception as e:
            _debug_log(f"[Sync] Save failed: {e}")
            return 0

    return updated


def get_scene_info(scene_id: int, scenes: List[Dict] = None) -> Optional[Dict]:
    """
    특정 씬 정보 조회

    Args:
        scene_id: 씬 번호
        scenes: 씬 데이터 (없으면 자동 로드)

    Returns:
        씬 딕셔너리 또는 None
    """
    if scenes is None:
        scenes = load_scenes_data()

    for scene in scenes:
        sid = scene.get("scene_id", scene.get("id", 0))
        if isinstance(sid, str) and sid.isdigit():
            sid = int(sid)
        if sid == scene_id:
            return scene

    return None


def get_scene_script_preview(scene: Dict, max_length: int = 50) -> str:
    """
    씬 스크립트 미리보기 텍스트

    Args:
        scene: 씬 딕셔너리
        max_length: 최대 길이

    Returns:
        미리보기 텍스트
    """
    script = scene.get("script_text", scene.get("narration", scene.get("text", "")))
    if len(script) > max_length:
        return script[:max_length] + "..."
    return script
