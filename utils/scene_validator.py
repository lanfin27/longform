# -*- coding: utf-8 -*-
"""
utils/scene_validator.py
씬 데이터 검증 및 자동 수정 유틸리티

주요 기능:
- background_prompt_en 검증 및 자동 수정
- 인물 없는 씬: background_prompt_en = image_prompt_en (100% 동일)
"""

from typing import List, Dict, Set


# 인물 관련 키워드 목록
PERSON_KEYWORDS = [
    # 직함/역할
    'ceo', 'engineer', 'worker', 'employee', 'businessman', 'manager',
    'presenter', 'executive', 'director', 'founder', 'leader', 'expert',
    'developer', 'designer', 'analyst', 'scientist', 'researcher',
    'doctor', 'professor', 'teacher', 'student', 'journalist',
    # 일반 인물
    'man', 'woman', 'person', 'people', 'figure', 'character', 'human',
    'guy', 'lady', 'gentleman', 'individual', 'someone', 'anybody',
    'male', 'female', 'boy', 'girl', 'child', 'adult',
    # 인물 동작
    'presenting', 'standing', 'walking', 'sitting', 'monitoring', 'working',
    'talking', 'speaking', 'looking', 'holding', 'pointing', 'gesturing',
    'typing', 'writing', 'reading', 'watching', 'listening',
    # 인물 묘사
    'confident expression', 'wearing suit', 'middle-aged', 'young', 'elderly',
    'professional attire', 'business casual', 'formal wear',
    'face', 'hand', 'hands', 'arm', 'arms', 'body',
    # 그룹 표현
    'executives', 'team', 'audience', 'crowd', 'employees', 'staff',
    'colleagues', 'workers', 'group of people', 'members',
]


def has_person_in_scene(scene: Dict) -> bool:
    """
    씬에 인물이 존재하는지 판단

    판단 기준:
    1. characters 배열에 데이터가 있는 경우
    2. character_prompt_en에 내용이 있는 경우
    3. image_prompt_en에 인물 관련 키워드가 있는 경우

    Args:
        scene: 씬 데이터 딕셔너리

    Returns:
        인물 존재 여부
    """
    # 1. characters 배열 확인
    characters = scene.get('characters', [])
    if characters and len(characters) > 0:
        return True

    # 2. character_prompt_en 확인
    character_prompt_en = scene.get('character_prompt_en', '')
    if character_prompt_en and character_prompt_en.strip():
        return True

    # 3. image_prompt_en에서 인물 키워드 확인
    image_prompt_en = scene.get('image_prompt_en', '')
    if image_prompt_en:
        image_prompt_lower = image_prompt_en.lower()
        for keyword in PERSON_KEYWORDS:
            # 단어 경계 체크 (부분 일치 방지)
            keyword_lower = keyword.lower()
            if f' {keyword_lower} ' in f' {image_prompt_lower} ':
                return True
            if image_prompt_lower.startswith(f'{keyword_lower} '):
                return True
            if image_prompt_lower.endswith(f' {keyword_lower}'):
                return True
            if f', {keyword_lower},' in image_prompt_lower:
                return True
            if f', {keyword_lower} ' in image_prompt_lower:
                return True

    return False


def validate_and_fix_background_prompts(scenes: List[Dict], verbose: bool = True) -> List[Dict]:
    """
    background_prompt_en 검증 및 자동 수정

    규칙:
    - 인물이 없는 씬: background_prompt_en = image_prompt_en (100% 동일해야 함)
    - 인물이 있는 씬: background_prompt_en에서 인물 관련 표현만 제거 (AI 처리)

    Args:
        scenes: 씬 데이터 리스트
        verbose: 상세 로그 출력 여부

    Returns:
        검증/수정된 씬 리스트
    """
    fixed_count = 0
    warning_count = 0

    for scene in scenes:
        scene_id = scene.get('scene_id', scene.get('id', 'unknown'))
        image_prompt_en = scene.get('image_prompt_en', '')
        background_prompt_en = scene.get('background_prompt_en', '')

        # 인물 존재 여부 판단
        has_person = has_person_in_scene(scene)

        # === 검증 및 수정 ===

        if not has_person:
            # 🔴 인물 없음: background_prompt_en = image_prompt_en (100% 동일해야 함)
            if background_prompt_en != image_prompt_en:
                if verbose:
                    print(f"[Background 수정] 씬 {scene_id}: 인물 없음 → background_prompt_en을 image_prompt_en으로 교체")
                    if background_prompt_en:
                        print(f"  기존: {background_prompt_en[:100]}...")
                    print(f"  수정: {image_prompt_en[:100]}...")

                scene['background_prompt_en'] = image_prompt_en
                fixed_count += 1

                # 한국어 background_prompt도 동일하게 처리
                image_prompt = scene.get('image_prompt', '')
                background_prompt = scene.get('background_prompt', '')
                if background_prompt != image_prompt:
                    scene['background_prompt'] = image_prompt
        else:
            # 🟡 인물 있음: background_prompt_en에서 인물 관련 표현이 제거되었는지 확인
            if background_prompt_en == image_prompt_en:
                if verbose:
                    print(f"[Background 경고] 씬 {scene_id}: 인물 있는데 background와 image가 동일함")
                warning_count += 1

    if verbose:
        print(f"\n[Background 검증 완료] 수정: {fixed_count}개, 경고: {warning_count}개")

    return scenes


def validate_scenes_before_save(scenes: List[Dict], verbose: bool = True) -> List[Dict]:
    """
    씬 데이터 저장 전 종합 검증

    현재 포함된 검증:
    - background_prompt_en 검증 및 자동 수정

    Args:
        scenes: 씬 데이터 리스트
        verbose: 상세 로그 출력 여부

    Returns:
        검증/수정된 씬 리스트
    """
    if verbose:
        print(f"\n[씬 검증] {len(scenes)}개 씬 검증 시작...")

    # 1. background_prompt_en 검증
    scenes = validate_and_fix_background_prompts(scenes, verbose=verbose)

    # TODO: 추가 검증 로직 추가 가능

    return scenes


def fix_background_prompts_in_file(scenes_json_path: str, backup: bool = True) -> int:
    """
    기존 scenes.json 파일의 background_prompt_en 수정

    Args:
        scenes_json_path: scenes.json 파일 경로
        backup: 백업 파일 생성 여부

    Returns:
        수정된 씬 개수
    """
    import json
    import shutil
    from pathlib import Path

    scenes_path = Path(scenes_json_path)
    if not scenes_path.exists():
        print(f"[오류] 파일 없음: {scenes_json_path}")
        return 0

    print(f"\n[파일 수정] {scenes_json_path}")

    # 백업
    if backup:
        backup_path = scenes_path.with_suffix('.json.bak')
        shutil.copy2(scenes_path, backup_path)
        print(f"  백업 생성: {backup_path}")

    # 로드
    with open(scenes_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # scenes가 리스트인지 dict 내부에 있는지 확인
    if isinstance(data, list):
        scenes = data
        is_list = True
    elif isinstance(data, dict) and 'scenes' in data:
        scenes = data['scenes']
        is_list = False
    else:
        print(f"  [경고] 알 수 없는 데이터 형식")
        return 0

    # 수정 전 카운트
    original_fixed = 0
    for scene in scenes:
        scene_id = scene.get('scene_id', scene.get('id', 'unknown'))
        image_prompt_en = scene.get('image_prompt_en', '')
        background_prompt_en = scene.get('background_prompt_en', '')
        has_person = has_person_in_scene(scene)

        if not has_person and background_prompt_en != image_prompt_en:
            scene['background_prompt_en'] = image_prompt_en

            # 한국어도 동일하게
            image_prompt = scene.get('image_prompt', '')
            scene['background_prompt'] = image_prompt

            original_fixed += 1
            print(f"  씬 {scene_id}: 수정됨")

    # 저장
    if original_fixed > 0:
        with open(scenes_path, 'w', encoding='utf-8') as f:
            if is_list:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            else:
                data['scenes'] = scenes
                json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  → {original_fixed}개 씬 수정 완료")
    return original_fixed


def fix_all_scenes_in_directory(base_dir: str, backup: bool = True) -> int:
    """
    디렉토리 내 모든 scenes.json 파일 수정

    Args:
        base_dir: 검색할 기본 디렉토리
        backup: 백업 파일 생성 여부

    Returns:
        전체 수정된 씬 개수
    """
    from pathlib import Path

    base_path = Path(base_dir)
    total_fixed = 0

    for scenes_file in base_path.rglob('scenes.json'):
        # backup 파일은 건너뛰기
        if '.bak' in str(scenes_file):
            continue

        fixed = fix_background_prompts_in_file(str(scenes_file), backup=backup)
        total_fixed += fixed

    print(f"\n{'='*60}")
    print(f"[전체 완료] 총 {total_fixed}개 씬 수정됨")
    print(f"{'='*60}")

    return total_fixed


# CLI 실행용
if __name__ == "__main__":
    import sys
    import os

    # 기본 프로젝트 디렉토리
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_dir, "data")

    if len(sys.argv) > 1:
        # 특정 파일 지정
        target_path = sys.argv[1]
        if os.path.isfile(target_path):
            fix_background_prompts_in_file(target_path)
        elif os.path.isdir(target_path):
            fix_all_scenes_in_directory(target_path)
        else:
            print(f"파일/디렉토리 없음: {target_path}")
    else:
        # 전체 data 디렉토리 수정
        print(f"전체 data 디렉토리 수정: {data_dir}")
        fix_all_scenes_in_directory(data_dir)
