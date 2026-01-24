# -*- coding: utf-8 -*-
"""
components/nano_banana_composite.py
나노바나나 배경+캐릭터 합성 이미지 생성 컴포넌트

워크플로우:
1. 캐릭터가 있는 씬 필터링 (character_prompt_en 존재)
2. 배경 이미지 생성 (background_prompt_en 사용)
3. 캐릭터 이미지 생성 (character_prompt_en 사용)
4. 합성 이미지 생성 (image_prompt_en + 배경/캐릭터 레퍼런스)

작성: 2026-01
"""

import streamlit as st
from pathlib import Path
from typing import List, Dict, Optional, Callable, Tuple, Set
import time
import json
import os

from utils.gemini_image_generator import (
    GeminiImageGenerator,
    GeminiGenerationResult,
    GEMINI_IMAGE_MODELS,
    check_gemini_api_key
)


# ═══════════════════════════════════════════════════════════════════════════════
# v2.0: 씬 이미지 경로 캐시 (성능 최적화)
# ═══════════════════════════════════════════════════════════════════════════════
_scene_image_paths_cache = {}
_scene_image_paths_cache_time = {}
SCENE_IMAGE_PATHS_CACHE_TTL = 60  # 초


def _clear_scene_image_paths_cache():
    """씬 이미지 경로 캐시 초기화"""
    global _scene_image_paths_cache, _scene_image_paths_cache_time
    _scene_image_paths_cache.clear()
    _scene_image_paths_cache_time.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# 씬 필터링 헬퍼 함수
# ═══════════════════════════════════════════════════════════════════════════════

def get_scene_number(scene: Dict) -> int:
    """씬 번호 추출 (다양한 키 지원)"""
    return (
        scene.get('scene_id') or
        scene.get('scene_number') or
        scene.get('scene_num') or
        0
    )


def has_character_prompt(scene: Dict) -> bool:
    """씬에 캐릭터 프롬프트가 있는지 확인 (v1.1: 더 정확한 필터링)"""
    char_prompt = (
        scene.get('character_prompt_en') or
        scene.get('character_prompt') or
        ""
    )
    # 빈 프롬프트 제외
    if not char_prompt.strip():
        return False

    lower = char_prompt.lower().strip()

    # v1.1: 더 엄격한 제외 키워드 (완전한 문구만 제외)
    # "no text"는 제외하지 않음 (이미지 생성 지시사항일 뿐)
    skip_keywords = [
        "없음",
        "no character",
        "no characters",
        "n/a",
        "none",
        "no people in scene",
        "empty scene",
        "no human"
    ]

    # 정확한 매칭 (부분 문자열이 아닌 완전한 단어/문구)
    for kw in skip_keywords:
        # 키워드가 문장 시작이거나 전체인 경우만 제외
        if lower == kw or lower.startswith(kw + ".") or lower.startswith(kw + ",") or lower.startswith(kw + " "):
            scene_num = get_scene_number(scene)
            print(f"[NanoComposite] 씬 {scene_num} 캐릭터 프롬프트 제외됨: '{char_prompt[:50]}...' (키워드: {kw})")
            return False

    return True


def get_character_scenes(scenes: List[Dict]) -> List[Dict]:
    """캐릭터가 있는 씬 목록 반환 (v1.1: 씬 번호순 정렬)"""
    character_scenes = [s for s in scenes if has_character_prompt(s)]

    # 씬 번호순 정렬
    character_scenes.sort(key=lambda s: get_scene_number(s))

    # 디버깅 로그
    scene_nums = [get_scene_number(s) for s in character_scenes]
    print(f"[NanoComposite] 캐릭터 씬 {len(character_scenes)}개 (번호: {scene_nums[:20]}{'...' if len(scene_nums) > 20 else ''})")

    return character_scenes


# ═══════════════════════════════════════════════════════════════════════════════
# v3.36: 배치 선택 헬퍼 함수
# ═══════════════════════════════════════════════════════════════════════════════

def parse_scene_numbers(input_str: str) -> List[int]:
    """
    다중 씬 번호 입력 파싱 (v3.36)

    지원 형식:
    - 단일: "5"
    - 쉼표 구분: "1,3,5,7"
    - 범위: "1-10"
    - 혼합: "1,3,5-10,15,20-25"

    Returns:
        정렬된 씬 번호 리스트
    """
    if not input_str or not input_str.strip():
        return []

    scene_numbers: Set[int] = set()

    # 공백 제거 및 쉼표로 분리
    parts = input_str.replace(' ', '').split(',')

    for part in parts:
        if not part:
            continue

        # 범위 형식 (예: "1-10")
        if '-' in part:
            try:
                range_parts = part.split('-')
                if len(range_parts) == 2:
                    start = int(range_parts[0])
                    end = int(range_parts[1])
                    if start <= end:
                        scene_numbers.update(range(start, end + 1))
            except ValueError:
                continue
        else:
            # 단일 숫자
            try:
                scene_numbers.add(int(part))
            except ValueError:
                continue

    return sorted(list(scene_numbers))


def validate_scene_numbers_for_composite(
    scene_numbers: List[int],
    character_scenes: List[Dict],
    project_path: str
) -> Dict:
    """
    합성용 씬 번호 유효성 검사 (v3.36)

    Args:
        scene_numbers: 파싱된 씬 번호
        character_scenes: 캐릭터가 있는 씬 목록
        project_path: 프로젝트 경로

    Returns:
        {
            'valid': 합성 가능한 씬 번호,
            'no_background': 배경 없는 씬 번호,
            'no_character': 캐릭터 이미지 없는 씬 번호,
            'invalid': 존재하지 않는 씬 번호,
            'scenes_data': 유효한 씬의 데이터 딕셔너리
        }
    """
    result = {
        'valid': [],
        'no_background': [],
        'no_character': [],
        'invalid': [],
        'scenes_data': {}
    }

    # 캐릭터 씬 번호 맵
    char_scene_map = {get_scene_number(s): s for s in character_scenes}
    valid_scene_nums = set(char_scene_map.keys())

    for num in scene_numbers:
        if num not in valid_scene_nums:
            result['invalid'].append(num)
            continue

        scene = char_scene_map[num]
        paths = get_scene_image_paths(scene, project_path)

        has_bg = bool(paths.get("background"))
        has_char = bool(paths.get("character"))

        if has_bg and has_char:
            result['valid'].append(num)
            result['scenes_data'][num] = {
                'scene': scene,
                'paths': paths
            }
        elif not has_bg:
            result['no_background'].append(num)
        else:
            result['no_character'].append(num)

    return result


def get_scene_prompts(scene: Dict) -> Dict[str, str]:
    """씬에서 프롬프트 추출

    Note: scenes.json 구조
    - image_prompt_en: 배경 전용 프롬프트 ("no people, no characters" 포함)
    - character_prompt_en: 캐릭터 전용 프롬프트 ("white background" 포함)
    - 합성 시에는 배경 + 캐릭터를 조합하여 전체 프롬프트 생성
    """
    # 배경 프롬프트 (씬 분석에서 생성된 image_prompt_en 사용)
    background_en = scene.get('image_prompt_en', '') or scene.get('background_prompt_en', '') or ''
    background_ko = scene.get('image_prompt_ko', '') or scene.get('background_prompt_ko', '') or ''

    # 캐릭터 프롬프트
    character_en = scene.get('character_prompt_en', '') or scene.get('character_prompt', '') or ''
    character_ko = scene.get('character_prompt_ko', '') or ''

    # 전체 프롬프트 (배경 + 캐릭터 조합)
    # 배경에서 "no people, no characters" 제거하고 캐릭터 추가
    def clean_background_for_composite(bg_prompt: str) -> str:
        """배경 프롬프트에서 캐릭터 제외 문구 제거"""
        exclusions = [
            ", no characters, no people",
            ", no people, no characters",
            ", no characters",
            ", no people",
            "no characters, no people",
            "no people, no characters",
            "no characters",
            "no people"
        ]
        result = bg_prompt
        for ex in exclusions:
            result = result.replace(ex, "")
        return result.strip().rstrip(',').strip()

    def clean_character_for_composite(char_prompt: str) -> str:
        """캐릭터 프롬프트에서 배경 제외 문구 제거"""
        exclusions = [
            ", white background",
            ", transparent background",
            "white background",
            "transparent background"
        ]
        result = char_prompt
        for ex in exclusions:
            result = result.replace(ex, "")
        return result.strip().rstrip(',').strip()

    # 합성용 전체 프롬프트 생성
    clean_bg = clean_background_for_composite(background_en)
    clean_char = clean_character_for_composite(character_en)
    full_en = f"{clean_bg}, {clean_char}" if clean_bg and clean_char else (clean_bg or clean_char)

    clean_bg_ko = clean_background_for_composite(background_ko)
    clean_char_ko = clean_character_for_composite(character_ko)
    full_ko = f"{clean_bg_ko}, {clean_char_ko}" if clean_bg_ko and clean_char_ko else (clean_bg_ko or clean_char_ko)

    return {
        "full_en": full_en,
        "full_ko": full_ko,
        "background_en": background_en,
        "background_ko": background_ko,
        "character_en": character_en,
        "character_ko": character_ko,
    }


def get_scene_image_paths(scene: Dict, project_path: str, use_cache: bool = True) -> Dict[str, Optional[str]]:
    """
    씬의 이미지 경로들 반환 (v2.0: 캐싱 지원)

    v2.0 변경사항:
    - 결과 캐싱 추가 (60초 TTL)
    - 중복 호출 방지

    v3.34 변경사항:
    - 캐릭터 이미지 조회 시 CharacterImageManager를 먼저 확인
    - characters.json의 appearance_scenes 기반 자동 연동 지원
    - 캐릭터 관리에서 생성된 이미지가 스토리보드에 자동 표시
    """
    scene_id = get_scene_number(scene)

    # v2.0: 캐시 확인
    cache_key = f"{project_path}_{scene_id}"
    if use_cache and cache_key in _scene_image_paths_cache:
        cache_time = _scene_image_paths_cache_time.get(cache_key, 0)
        if time.time() - cache_time < SCENE_IMAGE_PATHS_CACHE_TTL:
            # 캐시 히트
            return _scene_image_paths_cache[cache_key]

    project = Path(project_path)

    # 배경 이미지 경로 확인
    background_path = scene.get('background_image_path') or scene.get('background_image')
    if background_path and Path(background_path).exists():
        background_path = str(background_path)
    else:
        # 가능한 경로들 확인
        possible_bg_paths = [
            project / "images" / "backgrounds" / f"bg_scene_{scene_id:03d}.png",
            project / "images" / "backgrounds" / f"background_{scene_id:03d}.png",
            project / "images" / f"scene_{scene_id:03d}_bg.png",
        ]
        background_path = None
        for p in possible_bg_paths:
            if p.exists():
                background_path = str(p)
                break

    # ═══════════════════════════════════════════════════════════════
    # v3.34: 캐릭터 이미지 - CharacterImageManager 자동 연동 우선
    # ═══════════════════════════════════════════════════════════════
    character_path = None

    # Step 1: 씬 데이터에 이미 저장된 경로 확인
    saved_path = scene.get('character_image_path') or scene.get('character_image')
    if saved_path and Path(saved_path).exists():
        character_path = str(saved_path)

    # Step 2: CharacterImageManager로 appearance_scenes 기반 자동 연동 (v2.0: 캐시 사용)
    if not character_path:
        try:
            from utils.character_image_manager import CharacterImageManager
            # v2.0: 싱글톤 인스턴스 사용 (중복 생성 방지)
            char_manager = CharacterImageManager.get_instance(project_path)

            # appearance_scenes 기반으로 이 씬에 등장하는 캐릭터 찾기
            char_images = char_manager.get_all_characters_for_scene(scene)
            if char_images:
                # 첫 번째 캐릭터 이미지 사용
                img_path = char_images[0].get('path')
                if img_path and Path(img_path).exists():
                    character_path = str(img_path)
                    # 디버그 로그는 get_all_characters_for_scene에서 이미 출력됨
        except Exception as e:
            # CharacterImageManager 오류 시 폴백
            pass

    # Step 3: 폴백 - 하드코딩된 경로 확인
    if not character_path:
        possible_char_paths = [
            project / "images" / "characters" / f"char_scene_{scene_id:03d}.png",
            project / "images" / "characters" / f"character_{scene_id:03d}.png",
            project / "images" / f"scene_{scene_id:03d}_char.png",
        ]
        for p in possible_char_paths:
            if p.exists():
                character_path = str(p)
                break

    # 합성 이미지 경로 확인
    composite_path = scene.get('composite_image_path') or scene.get('nano_composite_image')
    if composite_path and Path(composite_path).exists():
        composite_path = str(composite_path)
    else:
        # 가능한 경로들 확인
        possible_comp_paths = [
            project / "images" / "nano_composite" / f"composite_scene_{scene_id:03d}.png",
            project / "images" / "composites" / f"composite_{scene_id:03d}.png",
        ]
        composite_path = None
        for p in possible_comp_paths:
            if p.exists():
                composite_path = str(p)
                break

    result = {
        "background": background_path,
        "character": character_path,
        "composite": composite_path
    }

    # v2.0: 캐시에 저장
    _scene_image_paths_cache[cache_key] = result
    _scene_image_paths_cache_time[cache_key] = time.time()

    return result


def can_generate_composite(scene: Dict, project_path: str) -> Tuple[bool, str]:
    """합성 이미지 생성 가능 여부 확인"""
    if not has_character_prompt(scene):
        return False, "캐릭터 프롬프트 없음"

    paths = get_scene_image_paths(scene, project_path)

    missing = []
    if not paths["background"]:
        missing.append("배경 이미지")
    if not paths["character"]:
        missing.append("캐릭터 이미지")

    if missing:
        return False, f"필요: {', '.join(missing)}"

    return True, "합성 가능"


# ═══════════════════════════════════════════════════════════════════════════════
# v3.35: 상세 로깅 함수
# ═══════════════════════════════════════════════════════════════════════════════

def log_reference_image_details(image_path: str, label: str = "이미지") -> Dict:
    """
    레퍼런스 이미지 상세 정보 로깅 (v3.35)

    파일 존재 여부, 크기, 해상도, 포맷 등을 상세히 로깅합니다.

    Args:
        image_path: 이미지 파일 경로
        label: 로그에 표시할 레이블 (예: "배경", "캐릭터")

    Returns:
        {
            "exists": bool,
            "path": str,
            "size_bytes": int,
            "size_readable": str,
            "dimensions": (width, height),
            "format": str,
            "valid": bool,
            "error": str or None
        }
    """
    result = {
        "exists": False,
        "path": image_path,
        "size_bytes": 0,
        "size_readable": "0 B",
        "dimensions": (0, 0),
        "format": "unknown",
        "valid": False,
        "error": None
    }

    path = Path(image_path) if image_path else None

    # 1. 파일 존재 확인
    if not path or not path.exists():
        result["error"] = "파일 없음"
        print(f"[NanoComposite] ❌ {label} 레퍼런스: 파일 없음 - {image_path}")
        return result

    result["exists"] = True

    # 2. 파일 크기 확인
    try:
        stat = path.stat()
        result["size_bytes"] = stat.st_size

        # 읽기 쉬운 크기 포맷
        size = stat.st_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                result["size_readable"] = f"{size:.1f} {unit}"
                break
            size /= 1024

        if stat.st_size < 1000:  # 1KB 미만
            result["error"] = f"파일 너무 작음 ({result['size_readable']})"
            print(f"[NanoComposite] ⚠️ {label} 레퍼런스: 파일 크기 너무 작음 - {result['size_readable']}")
    except Exception as e:
        result["error"] = f"파일 읽기 오류: {e}"
        print(f"[NanoComposite] ❌ {label} 레퍼런스: 파일 읽기 오류 - {e}")
        return result

    # 3. 이미지 해상도 및 포맷 확인
    try:
        from PIL import Image
        with Image.open(path) as img:
            result["dimensions"] = img.size
            result["format"] = img.format or path.suffix.upper().replace('.', '')

            # 해상도 검증
            w, h = img.size
            if w < 64 or h < 64:
                result["error"] = f"해상도 너무 낮음 ({w}x{h})"
                print(f"[NanoComposite] ⚠️ {label} 레퍼런스: 해상도 낮음 - {w}x{h}")
            else:
                result["valid"] = True

    except Exception as e:
        result["error"] = f"이미지 읽기 오류: {e}"
        print(f"[NanoComposite] ❌ {label} 레퍼런스: 이미지 읽기 오류 - {e}")
        return result

    # 4. 상세 로그 출력
    w, h = result["dimensions"]
    print(f"[NanoComposite] {'✅' if result['valid'] else '⚠️'} {label} 레퍼런스 상세:")
    print(f"[NanoComposite]    경로: {image_path}")
    print(f"[NanoComposite]    존재: {'예' if result['exists'] else '아니오'}")
    print(f"[NanoComposite]    크기: {result['size_readable']} ({result['size_bytes']:,} bytes)")
    print(f"[NanoComposite]    해상도: {w}x{h} px")
    print(f"[NanoComposite]    포맷: {result['format']}")
    if result["error"]:
        print(f"[NanoComposite]    오류: {result['error']}")

    return result


def log_full_prompt(prompt: str, label: str = "프롬프트", max_line_length: int = 120):
    """
    전체 프롬프트 로깅 (v3.35)

    프롬프트를 잘리지 않게 전체 출력합니다.
    긴 프롬프트는 여러 줄로 나눠서 출력합니다.

    Args:
        prompt: 프롬프트 텍스트
        label: 로그에 표시할 레이블
        max_line_length: 한 줄 최대 길이
    """
    if not prompt:
        print(f"[NanoComposite] {label}: (빈 프롬프트)")
        return

    prompt = prompt.strip()
    total_len = len(prompt)

    print(f"[NanoComposite] ═══ {label} ({total_len}자) ═══")

    # 긴 프롬프트는 줄바꿈해서 출력
    if total_len <= max_line_length:
        print(f"[NanoComposite] {prompt}")
    else:
        # 쉼표 또는 마침표 기준으로 나누기
        parts = []
        current = ""

        for char in prompt:
            current += char
            if char in [',', '.', ';'] and len(current) >= max_line_length * 0.7:
                parts.append(current.strip())
                current = ""

        if current.strip():
            parts.append(current.strip())

        # 파트가 없으면 강제 분할
        if not parts:
            for i in range(0, total_len, max_line_length):
                parts.append(prompt[i:i+max_line_length])

        for i, part in enumerate(parts, 1):
            print(f"[NanoComposite]   [{i}/{len(parts)}] {part}")

    print(f"[NanoComposite] ═══════════════════════════════════════")


# ═══════════════════════════════════════════════════════════════════════════════
# 이미지 생성 함수
# ═══════════════════════════════════════════════════════════════════════════════

def generate_background_image(
    scene: Dict,
    project_path: str,
    generator: GeminiImageGenerator,
    model_key: str = "gemini_nano_banana",
    prompt_type: str = "english"
) -> Tuple[bool, Optional[str], str]:
    """
    배경 이미지 생성

    Returns:
        (success, image_path, error_message)
    """
    scene_id = get_scene_number(scene)
    prompts = get_scene_prompts(scene)

    # 프롬프트 선택
    prompt = prompts["background_en"] if prompt_type == "english" else prompts["background_ko"]
    if not prompt.strip():
        return False, None, "배경 프롬프트 없음"

    # 출력 경로
    output_dir = Path(project_path) / "images" / "backgrounds"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)
    output_path = str(output_dir / f"bg_scene_{scene_id:03d}_{timestamp}.png")

    # 이미지 생성
    print(f"[NanoComposite] 🏞️ 씬 {scene_id} 배경 이미지 생성 중...")
    print(f"[NanoComposite]    프롬프트: {prompt[:80]}...")

    result = generator.generate_image(
        prompt=prompt,
        model_key=model_key,
        aspect_ratio="16:9"
    )

    if result.success and result.image_data:
        with open(output_path, 'wb') as f:
            f.write(result.image_data)
        print(f"[NanoComposite] ✅ 배경 이미지 저장: {output_path}")
        return True, output_path, ""
    else:
        error = result.error or "알 수 없는 오류"
        print(f"[NanoComposite] ❌ 배경 이미지 생성 실패: {error}")
        return False, None, error


def generate_character_image(
    scene: Dict,
    project_path: str,
    generator: GeminiImageGenerator,
    model_key: str = "gemini_nano_banana",
    prompt_type: str = "english"
) -> Tuple[bool, Optional[str], str]:
    """
    캐릭터 이미지 생성 (v3.33: 다중 캐릭터 + appearance_scenes 우선 연동)

    ✅ characters.json의 appearance_scenes 기반 자동 연동
    ✅ 캐릭터 관리에서 생성된 이미지를 먼저 확인
    ✅ 기존 이미지가 있으면 재사용 (Gemini API 호출 X)
    ✅ 없을 때만 새로 생성

    Returns:
        (success, image_path, error_message)
    """
    scene_id = get_scene_number(scene)
    prompts = get_scene_prompts(scene)

    # ─────────────────────────────────────────────────────────────
    # Step 1: 캐릭터 관리에서 기존 이미지 확인 (v3.33: appearance_scenes 우선)
    # ─────────────────────────────────────────────────────────────
    try:
        from utils.character_image_manager import CharacterImageManager
        char_manager = CharacterImageManager(project_path)

        # v3.33: 모든 캐릭터 이미지 가져오기 (다중 캐릭터 지원)
        existing_images = char_manager.get_all_characters_for_scene(scene)

        if existing_images:
            # 첫 번째 캐릭터 이미지 사용 (메인 캐릭터)
            existing_image = existing_images[0]
            image_path = existing_image.get('path')

            if image_path and Path(image_path).exists():
                char_name = existing_image.get('name', '알 수 없음')
                match_type = existing_image.get('match_type', 'exact')

                print(f"[NanoComposite] ✅ 씬 {scene_id}: 기존 캐릭터 이미지 연동!")
                print(f"[NanoComposite]    캐릭터: {char_name}")
                print(f"[NanoComposite]    매칭 유형: {match_type}")
                print(f"[NanoComposite]    경로: {image_path}")

                if len(existing_images) > 1:
                    other_chars = [img.get('name', '?') for img in existing_images[1:]]
                    print(f"[NanoComposite]    + 추가 캐릭터: {', '.join(other_chars)}")

                return True, image_path, ""
            else:
                print(f"[NanoComposite] ⚠️ 씬 {scene_id}: 연동된 이미지 파일 없음, 새로 생성")

    except Exception as e:
        print(f"[NanoComposite] ⚠️ 캐릭터 이미지 조회 오류: {e}")

    # ─────────────────────────────────────────────────────────────
    # Step 2: 씬에 이미 저장된 캐릭터 이미지 확인
    # ─────────────────────────────────────────────────────────────
    scene_char_path = scene.get('character_image_path') or scene.get('character_image_url')
    if scene_char_path and Path(scene_char_path).exists():
        print(f"[NanoComposite] ✅ 씬 {scene_id}: 기존 저장된 캐릭터 이미지 사용")
        print(f"[NanoComposite]    경로: {scene_char_path}")
        return True, scene_char_path, ""

    # ─────────────────────────────────────────────────────────────
    # Step 3: 새로 생성 (기존 이미지 없을 때만)
    # ─────────────────────────────────────────────────────────────
    print(f"[NanoComposite] 👤 씬 {scene_id}: 기존 이미지 없음, 새로 생성 중...")

    # 프롬프트 선택
    prompt = prompts["character_en"] if prompt_type == "english" else prompts["character_ko"]
    if not prompt.strip():
        return False, None, "캐릭터 프롬프트 없음"

    # 출력 경로
    output_dir = Path(project_path) / "images" / "characters"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)
    output_path = str(output_dir / f"char_scene_{scene_id:03d}_{timestamp}.png")

    # 이미지 생성
    print(f"[NanoComposite]    프롬프트: {prompt[:80]}...")

    result = generator.generate_image(
        prompt=prompt,
        model_key=model_key,
        aspect_ratio="1:1"  # 캐릭터는 정사각형
    )

    if result.success and result.image_data:
        with open(output_path, 'wb') as f:
            f.write(result.image_data)
        print(f"[NanoComposite] ✅ 캐릭터 이미지 저장: {output_path}")
        return True, output_path, ""
    else:
        error = result.error or "알 수 없는 오류"
        print(f"[NanoComposite] ❌ 캐릭터 이미지 생성 실패: {error}")
        return False, None, error


def generate_composite_image(
    scene: Dict,
    project_path: str,
    generator: GeminiImageGenerator,
    background_path: str,
    character_path: str,
    model_key: str = "gemini_nano_banana",
    prompt_type: str = "english",
    reference_strength: float = 0.8
) -> Tuple[bool, Optional[str], str, Optional[Dict]]:
    """
    배경 + 캐릭터 합성 이미지 생성 (v3.35: 상세 로깅 + composite_info 반환)

    Args:
        scene: 씬 데이터
        project_path: 프로젝트 경로
        generator: Gemini 이미지 생성기
        background_path: 배경 이미지 경로
        character_path: 캐릭터 이미지 경로
        model_key: 모델 키
        prompt_type: "english" 또는 "korean"
        reference_strength: 레퍼런스 강도 (0.0 ~ 1.0)

    Returns:
        (success, image_path, error_message, composite_info)

        composite_info: {
            "used_prompt": str,
            "model": str,
            "reference_strength": float,
            "background_info": dict,
            "character_info": dict,
            "timestamp": str
        }
    """
    scene_id = get_scene_number(scene)
    prompts = get_scene_prompts(scene)

    # composite_info 초기화
    composite_info = {
        "used_prompt": "",
        "model": model_key,
        "reference_strength": reference_strength,
        "background_info": None,
        "character_info": None,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    # 전체 프롬프트 사용 (배경 + 캐릭터가 함께 있는 씬)
    prompt = prompts["full_en"] if prompt_type == "english" else prompts["full_ko"]
    if not prompt.strip():
        return False, None, "전체 프롬프트 없음", composite_info

    composite_info["used_prompt"] = prompt

    print(f"\n[NanoComposite] ═══════════════════════════════════════════════════════")
    print(f"[NanoComposite] 🎨 씬 {scene_id} 합성 이미지 생성 시작")
    print(f"[NanoComposite] ═══════════════════════════════════════════════════════")

    # v3.35: 전체 프롬프트 상세 로깅
    log_full_prompt(prompt, f"씬 {scene_id} 합성 프롬프트")

    # v3.35: 레퍼런스 이미지 상세 검증 및 로깅
    print(f"\n[NanoComposite] --- 레퍼런스 이미지 검증 ---")
    bg_info = log_reference_image_details(background_path, "배경")
    char_info = log_reference_image_details(character_path, "캐릭터")

    composite_info["background_info"] = bg_info
    composite_info["character_info"] = char_info

    # 검증 실패 시 상세 오류 반환
    if not bg_info["valid"]:
        error = f"배경 이미지 오류: {bg_info['error']} - {background_path}"
        print(f"[NanoComposite] ❌ {error}")
        return False, None, error, composite_info

    if not char_info["valid"]:
        error = f"캐릭터 이미지 오류: {char_info['error']} - {character_path}"
        print(f"[NanoComposite] ❌ {error}")
        return False, None, error, composite_info

    # 출력 경로
    output_dir = Path(project_path) / "images" / "nano_composite"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)
    output_path = str(output_dir / f"composite_scene_{scene_id:03d}_{timestamp}.png")

    # 합성 설정 로그
    print(f"\n[NanoComposite] --- 합성 설정 ---")
    print(f"[NanoComposite]    모델: {model_key}")
    print(f"[NanoComposite]    레퍼런스 강도: {reference_strength*100:.0f}%")
    print(f"[NanoComposite]    출력 경로: {output_path}")

    # 2개의 레퍼런스 이미지 사용
    reference_images = [background_path, character_path]

    result = generator.generate_image(
        prompt=prompt,
        model_key=model_key,
        reference_images=reference_images,
        reference_type="composition",  # 구도/합성 참조
        reference_strength=reference_strength,
        aspect_ratio="16:9"
    )

    if result.success and result.image_data:
        with open(output_path, 'wb') as f:
            f.write(result.image_data)

        print(f"\n[NanoComposite] ═══════════════════════════════════════════════════════")
        print(f"[NanoComposite] ✅ 씬 {scene_id} 합성 이미지 생성 완료!")
        print(f"[NanoComposite]    저장: {output_path}")
        print(f"[NanoComposite] ═══════════════════════════════════════════════════════\n")

        return True, output_path, "", composite_info
    else:
        error = result.error or "알 수 없는 오류"
        print(f"\n[NanoComposite] ═══════════════════════════════════════════════════════")
        print(f"[NanoComposite] ❌ 씬 {scene_id} 합성 이미지 생성 실패: {error}")
        print(f"[NanoComposite] ═══════════════════════════════════════════════════════\n")
        return False, None, error, composite_info


# ═══════════════════════════════════════════════════════════════════════════════
# 씬 데이터 업데이트 함수
# ═══════════════════════════════════════════════════════════════════════════════

def update_scene_image_path(
    scene: Dict,
    image_type: str,  # "background", "character", "composite"
    new_path: str,
    all_scenes: List[Dict],
    project_path: str,
    composite_info: Optional[Dict] = None
):
    """
    씬 데이터에 이미지 경로 업데이트 (v3.35: composite_info 저장 지원)

    Args:
        scene: 현재 씬 데이터
        image_type: 이미지 타입 ("background", "character", "composite")
        new_path: 새 이미지 경로
        all_scenes: 전체 씬 목록
        project_path: 프로젝트 경로
        composite_info: 합성 정보 (composite 타입일 때만 사용)
    """
    scene_id = get_scene_number(scene)

    key_mapping = {
        "background": "background_image_path",
        "character": "character_image_path",
        "composite": "nano_composite_image"
    }

    key = key_mapping.get(image_type)
    if not key:
        return

    # 현재 씬 업데이트
    scene[key] = new_path
    scene['last_image_update'] = time.strftime("%Y-%m-%d %H:%M:%S")

    # v3.35: composite_info 저장 (합성 시에만)
    if image_type == "composite" and composite_info:
        scene['composite_info'] = {
            'used_prompt': composite_info.get('used_prompt', ''),
            'model': composite_info.get('model', ''),
            'reference_strength': composite_info.get('reference_strength', 0),
            'timestamp': composite_info.get('timestamp', ''),
            'background_path': composite_info.get('background_info', {}).get('path', ''),
            'character_path': composite_info.get('character_info', {}).get('path', ''),
        }
        print(f"[NanoComposite] 씬 {scene_id}: composite_info 저장됨 (프롬프트 {len(composite_info.get('used_prompt', ''))}자)")

    # all_scenes에서도 업데이트
    if all_scenes:
        for s in all_scenes:
            if get_scene_number(s) == scene_id:
                s[key] = new_path
                s['last_image_update'] = scene['last_image_update']
                if image_type == "composite" and composite_info:
                    s['composite_info'] = scene.get('composite_info')
                break

    # scenes.json 저장
    try:
        scenes_path = Path(project_path) / "analysis" / "scenes.json"
        if scenes_path.exists() and all_scenes:
            with open(scenes_path, 'w', encoding='utf-8') as f:
                json.dump(all_scenes, f, ensure_ascii=False, indent=2)
            print(f"[NanoComposite] 씬 데이터 저장됨: {scenes_path}")
    except Exception as e:
        print(f"[NanoComposite] 씬 데이터 저장 실패: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# UI 렌더링
# ═══════════════════════════════════════════════════════════════════════════════

def render_nano_banana_composite(
    scenes: List[Dict],
    project_path: str,
    on_complete: Callable = None
):
    """
    나노바나나 배경+캐릭터 합성 UI 렌더링

    Args:
        scenes: 전체 씬 목록
        project_path: 프로젝트 경로
        on_complete: 완료 콜백
    """

    st.markdown("### 🎨 나노바나나 배경+캐릭터 합성")
    st.caption("캐릭터가 있는 씬의 배경과 캐릭터 이미지를 합성하여 자연스러운 씬 이미지를 생성합니다.")

    # API 키 확인
    if not check_gemini_api_key():
        st.error("Gemini API 키가 설정되지 않았습니다. `.env` 파일에 `GEMINI_API_KEY`를 추가하세요.")
        return

    # 캐릭터 있는 씬 필터링
    character_scenes = get_character_scenes(scenes)

    if not character_scenes:
        st.info("캐릭터가 있는 씬이 없습니다. 씬 분석에서 캐릭터 프롬프트가 생성된 씬만 대상입니다.")
        return

    # ═══════════════════════════════════════════════════════════════
    # 상태 요약
    # ═══════════════════════════════════════════════════════════════

    # 각 씬의 이미지 상태 확인
    status_summary = {
        "total": len(character_scenes),
        "bg_ready": 0,
        "char_ready": 0,
        "composite_ready": 0
    }

    for scene in character_scenes:
        paths = get_scene_image_paths(scene, project_path)
        if paths["background"]:
            status_summary["bg_ready"] += 1
        if paths["character"]:
            status_summary["char_ready"] += 1
        if paths["composite"]:
            status_summary["composite_ready"] += 1

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("캐릭터 씬", status_summary["total"], help="캐릭터 프롬프트가 있는 씬 수")
    with col2:
        st.metric("🏞️ 배경 이미지", f"{status_summary['bg_ready']}/{status_summary['total']}", help="생성된 배경 이미지 수")
    with col3:
        st.metric("👤 캐릭터 이미지", f"{status_summary['char_ready']}/{status_summary['total']}", help="생성된 캐릭터 이미지 수")
    with col4:
        st.metric("✨ 합성 완료", f"{status_summary['composite_ready']}/{status_summary['total']}", help="합성 이미지 생성 완료 수")

    # v1.1: 캐릭터 이미지 미생성 시 안내 메시지
    if status_summary['char_ready'] == 0 and status_summary['total'] > 0:
        st.warning(
            f"⚠️ 캐릭터 이미지가 없습니다. 합성하려면 먼저 **캐릭터 이미지를 생성**해야 합니다.\n"
            f"캐릭터 프롬프트는 있지만({status_summary['total']}개), 이미지로 생성되지 않았습니다.\n"
            f"아래 '일괄 생성' 탭에서 '캐릭터'를 선택하여 생성하세요."
        )
    elif status_summary['bg_ready'] == 0 and status_summary['total'] > 0:
        st.info(
            f"ℹ️ 배경 이미지가 없습니다. 합성하려면 **배경 이미지와 캐릭터 이미지 모두** 필요합니다.\n"
            f"아래 '일괄 생성' 탭에서 '배경'과 '캐릭터'를 선택하여 생성하세요."
        )

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # 설정
    # ═══════════════════════════════════════════════════════════════

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**모델 선택**")
        model_options = {
            "gemini_nano_banana": "Nano Banana (빠름, ~15원/장)",
            "gemini_nano_banana_pro": "Nano Banana Pro (고품질, ~25원/장)"
        }
        selected_model = st.radio(
            "모델",
            options=list(model_options.keys()),
            format_func=lambda x: model_options[x],
            key="composite_model",
            horizontal=True,
            label_visibility="collapsed"
        )

    with col2:
        st.markdown("**프롬프트 언어**")
        prompt_type = st.radio(
            "프롬프트",
            options=["english", "korean"],
            format_func=lambda x: "영어" if x == "english" else "한글",
            key="composite_prompt_type",
            horizontal=True,
            label_visibility="collapsed"
        )

    # 레퍼런스 강도
    ref_strength = st.slider(
        "레퍼런스 강도 (합성 시)",
        min_value=0.3,
        max_value=1.0,
        value=0.8,
        step=0.1,
        key="composite_ref_strength",
        help="높을수록 배경/캐릭터 원본에 가깝게 합성됩니다."
    )

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # 탭: 개별 생성 / 일괄 생성 / 배치 합성 (v3.36)
    # ═══════════════════════════════════════════════════════════════

    tab1, tab2, tab3, tab4 = st.tabs(["📋 씬별 상태", "🚀 일괄 생성", "🎨 배치 합성", "🎯 개별 생성"])

    # ---- 탭 1: 씬별 상태 ----
    with tab1:
        st.markdown("##### 캐릭터 있는 씬 이미지 상태")

        for scene in character_scenes[:20]:  # 최대 20개 표시
            scene_id = get_scene_number(scene)
            paths = get_scene_image_paths(scene, project_path)
            prompts = get_scene_prompts(scene)

            bg_icon = "✅" if paths["background"] else "❌"
            char_icon = "✅" if paths["character"] else "❌"
            comp_icon = "✅" if paths["composite"] else "⏳"

            can_comp, reason = can_generate_composite(scene, project_path)

            with st.expander(f"씬 {scene_id} | 배경{bg_icon} 캐릭터{char_icon} 합성{comp_icon}", expanded=False):
                # 이미지 미리보기
                img_cols = st.columns(3)

                with img_cols[0]:
                    st.markdown("**배경**")
                    if paths["background"]:
                        st.image(paths["background"], use_container_width=True)
                    else:
                        st.caption("미생성")
                        if prompts["background_en"]:
                            st.caption(f"프롬프트: {prompts['background_en'][:50]}...")

                with img_cols[1]:
                    st.markdown("**캐릭터**")
                    if paths["character"]:
                        st.image(paths["character"], use_container_width=True)
                    else:
                        st.caption("미생성")
                        if prompts["character_en"]:
                            st.caption(f"프롬프트: {prompts['character_en'][:50]}...")

                with img_cols[2]:
                    st.markdown("**합성 결과**")
                    if paths["composite"]:
                        st.image(paths["composite"], use_container_width=True)
                        # v3.35: 합성에 사용된 프롬프트 표시
                        composite_info = scene.get('composite_info', {})
                        if composite_info.get('used_prompt'):
                            with st.popover("🔍 사용된 프롬프트"):
                                st.text_area(
                                    "전체 프롬프트",
                                    value=composite_info['used_prompt'],
                                    height=120,
                                    disabled=True,
                                    key=f"comp_prompt_view_{scene_id}"
                                )
                                if composite_info.get('timestamp'):
                                    st.caption(f"생성: {composite_info['timestamp']}")
                    else:
                        if can_comp:
                            st.caption("합성 대기")
                        else:
                            st.caption(reason)

        if len(character_scenes) > 20:
            st.info(f"... 외 {len(character_scenes) - 20}개 씬")

    # ---- 탭 2: 일괄 생성 ----
    with tab2:
        st.markdown("##### 일괄 이미지 생성")

        # 생성 옵션
        gen_options = st.multiselect(
            "생성할 이미지 타입",
            options=["background", "character", "composite"],
            default=["composite"],
            format_func=lambda x: {"background": "배경", "character": "캐릭터", "composite": "합성"}[x],
            key="batch_gen_options"
        )

        skip_existing = st.checkbox("이미 생성된 이미지 건너뛰기", value=True, key="batch_skip_existing")

        # 대상 씬 수 계산
        target_counts = {"background": 0, "character": 0, "composite": 0}

        for scene in character_scenes:
            paths = get_scene_image_paths(scene, project_path)

            if "background" in gen_options:
                if not skip_existing or not paths["background"]:
                    target_counts["background"] += 1

            if "character" in gen_options:
                if not skip_existing or not paths["character"]:
                    target_counts["character"] += 1

            if "composite" in gen_options:
                can_comp, _ = can_generate_composite(scene, project_path)
                # 합성은 배경+캐릭터가 있어야 가능 (또는 같이 생성)
                if not skip_existing or not paths["composite"]:
                    if can_comp or ("background" in gen_options and "character" in gen_options):
                        target_counts["composite"] += 1

        # 비용 예상
        cost_per_image = 15 if selected_model == "gemini_nano_banana" else 25
        total_images = sum(target_counts.values())
        total_cost = total_images * cost_per_image

        st.markdown("**예상 생성량**")
        cost_cols = st.columns(4)
        with cost_cols[0]:
            st.metric("배경", target_counts["background"])
        with cost_cols[1]:
            st.metric("캐릭터", target_counts["character"])
        with cost_cols[2]:
            st.metric("합성", target_counts["composite"])
        with cost_cols[3]:
            st.metric("예상 비용", f"~{total_cost:,}원")

        st.divider()

        # 실행 버튼
        if st.button(
            f"🚀 일괄 생성 시작 ({total_images}개)",
            type="primary",
            use_container_width=True,
            key="batch_generate",
            disabled=total_images == 0
        ):
            _execute_batch_generation(
                scenes=character_scenes,
                all_scenes=scenes,
                project_path=project_path,
                model_key=selected_model,
                prompt_type=prompt_type,
                ref_strength=ref_strength,
                gen_options=gen_options,
                skip_existing=skip_existing,
                on_complete=on_complete
            )

    # ---- 탭 3: 배치 합성 (v3.36) ----
    with tab3:
        _render_batch_composite_tab(
            character_scenes=character_scenes,
            all_scenes=scenes,
            project_path=project_path,
            selected_model=selected_model,
            prompt_type=prompt_type,
            ref_strength=ref_strength,
            on_complete=on_complete
        )

    # ---- 탭 4: 개별 생성 ----
    with tab4:
        st.markdown("##### 씬 선택하여 개별 생성")

        # v1.2: 새로고침 버튼 추가
        refresh_col1, refresh_col2 = st.columns([4, 1])
        with refresh_col2:
            if st.button("🔄", key="refresh_individual_scenes", help="씬 목록 새로고침"):
                # 캐시 무효화
                for key in list(st.session_state.keys()):
                    if 'composite' in key.lower() or 'character_scenes' in key.lower():
                        del st.session_state[key]
                st.rerun()

        # v1.2: 리스트 기반으로 변경 (중복 scene_id 문제 해결)
        # 씬 번호 + 인덱스를 조합하여 고유 키 생성
        scene_options_list = []
        for idx, s in enumerate(character_scenes):
            scene_num = get_scene_number(s)
            paths = get_scene_image_paths(s, project_path)

            # 상태 아이콘
            bg_icon = "🏞️" if paths.get("background") else "⬜"
            char_icon = "👤" if paths.get("character") else "⬜"
            comp_icon = "✅" if paths.get("composite") else "⏳"

            label = f"씬 {scene_num} {bg_icon}{char_icon}{comp_icon}"
            scene_options_list.append((label, idx, s))

        # 디버깅: 옵션 수 확인
        print(f"[NanoComposite] 드롭다운 옵션 수: {len(scene_options_list)}개")

        if not scene_options_list:
            st.warning("캐릭터 프롬프트가 있는 씬이 없습니다.")
        else:
            # 선택 옵션 (라벨만 추출)
            option_labels = [opt[0] for opt in scene_options_list]

            with refresh_col1:
                selected_idx = st.selectbox(
                    "씬 선택",
                    options=range(len(option_labels)),
                    format_func=lambda i: option_labels[i],
                    key="individual_scene_select",
                    help="🏞️=배경, 👤=캐릭터, ✅=합성완료, ⏳=대기"
                )

            # 선택된 씬 가져오기
            _, _, scene = scene_options_list[selected_idx]
            scene_id = get_scene_number(scene)
            paths = get_scene_image_paths(scene, project_path)
            prompts = get_scene_prompts(scene)

            # 현재 상태
            st.markdown("**현재 이미지 상태**")

            img_cols = st.columns(3)

            with img_cols[0]:
                st.markdown("**배경**")
                # v1.3: 세션에서 방금 생성된 이미지 확인
                new_bg = st.session_state.get(f'_new_bg_{scene_id}')
                display_bg = new_bg or paths["background"]

                if display_bg:
                    st.image(display_bg, use_container_width=True)
                    st.success("생성됨")
                else:
                    st.warning("미생성")

                if st.button("배경 생성", key=f"gen_bg_{scene_id}"):
                    with st.spinner("배경 이미지 생성 중..."):
                        generator = GeminiImageGenerator()
                        success, path, error = generate_background_image(
                            scene, project_path, generator, selected_model, prompt_type
                        )
                        if success:
                            update_scene_image_path(scene, "background", path, scenes, project_path)
                            # v1.3: 세션에 저장하고 즉시 표시 (rerun 최소화)
                            st.session_state[f'_new_bg_{scene_id}'] = path
                            st.success(f"✅ 배경 이미지 생성 완료!")
                            st.image(path, use_container_width=True)
                            # rerun 제거 - 즉시 표시됨
                        else:
                            st.error(f"실패: {error}")

            with img_cols[1]:
                st.markdown("**캐릭터**")
                # v1.3: 세션에서 방금 생성된 이미지 확인
                new_char = st.session_state.get(f'_new_char_{scene_id}')
                display_char = new_char or paths["character"]

                if display_char:
                    st.image(display_char, use_container_width=True)
                    st.success("생성됨")
                else:
                    st.warning("미생성")

                if st.button("캐릭터 생성", key=f"gen_char_{scene_id}"):
                    with st.spinner("캐릭터 이미지 생성 중..."):
                        generator = GeminiImageGenerator()
                        success, path, error = generate_character_image(
                            scene, project_path, generator, selected_model, prompt_type
                        )
                        if success:
                            update_scene_image_path(scene, "character", path, scenes, project_path)
                            # v1.3: 세션에 저장하고 즉시 표시 (rerun 최소화)
                            st.session_state[f'_new_char_{scene_id}'] = path
                            st.success(f"✅ 캐릭터 이미지 생성 완료!")
                            st.image(path, use_container_width=True)
                            # rerun 제거 - 즉시 표시됨
                        else:
                            st.error(f"실패: {error}")

            with img_cols[2]:
                st.markdown("**합성 결과**")
                # v1.3: 세션에서 방금 생성된 이미지 확인
                new_comp = st.session_state.get(f'_new_comp_{scene_id}')
                display_comp = new_comp or paths["composite"]

                if display_comp:
                    st.image(display_comp, use_container_width=True)
                    st.success("생성됨")
                else:
                    can_comp, reason = can_generate_composite(scene, project_path)
                    if can_comp:
                        st.info("합성 대기")
                    else:
                        st.warning(reason)

                # v1.3: 새로 생성된 이미지 경로 사용 (합성 가능 여부 재확인)
                bg_for_comp = st.session_state.get(f'_new_bg_{scene_id}') or paths["background"]
                char_for_comp = st.session_state.get(f'_new_char_{scene_id}') or paths["character"]

                can_comp = bool(bg_for_comp and char_for_comp)
                reason = "" if can_comp else "배경과 캐릭터 이미지가 모두 필요합니다"

                if st.button(
                    "합성 생성",
                    key=f"gen_comp_{scene_id}",
                    disabled=not can_comp,
                    help=reason if not can_comp else "배경+캐릭터를 합성합니다"
                ):
                    with st.spinner("합성 이미지 생성 중..."):
                        generator = GeminiImageGenerator()
                        success, path, error, composite_info = generate_composite_image(
                            scene, project_path, generator,
                            bg_for_comp, char_for_comp,
                            selected_model, prompt_type, ref_strength
                        )
                        if success:
                            update_scene_image_path(scene, "composite", path, scenes, project_path, composite_info)
                            # v1.3: 세션에 저장하고 즉시 표시 (rerun 최소화)
                            st.session_state[f'_new_comp_{scene_id}'] = path
                            st.success(f"✅ 합성 이미지 생성 완료!")
                            st.image(path, use_container_width=True)
                            # v3.35: 사용된 프롬프트 표시
                            if composite_info and composite_info.get('used_prompt'):
                                st.session_state[f'last_composite_prompt_{scene_id}'] = composite_info['used_prompt']
                            # rerun 제거 - 즉시 표시됨
                        else:
                            st.error(f"실패: {error}")

            # 프롬프트 표시
            st.divider()
            st.markdown("**프롬프트**")

            prompt_cols = st.columns(3)
            with prompt_cols[0]:
                st.text_area("배경 프롬프트", value=prompts["background_en"][:200], height=100, disabled=True, key=f"bg_prompt_{scene_id}")
            with prompt_cols[1]:
                st.text_area("캐릭터 프롬프트", value=prompts["character_en"][:200], height=100, disabled=True, key=f"char_prompt_{scene_id}")
            with prompt_cols[2]:
                st.text_area("전체 프롬프트 (합성용)", value=prompts["full_en"][:200], height=100, disabled=True, key=f"full_prompt_{scene_id}")

            # v3.35: 마지막 합성에 사용된 프롬프트 표시 (composite_info에서)
            composite_info = scene.get('composite_info', {})
            used_prompt = composite_info.get('used_prompt', '') or st.session_state.get(f'last_composite_prompt_{scene_id}', '')

            if used_prompt:
                with st.expander("🎨 마지막 합성에 사용된 프롬프트", expanded=False):
                    st.text_area(
                        "사용된 전체 프롬프트",
                        value=used_prompt,
                        height=150,
                        disabled=True,
                        key=f"used_prompt_{scene_id}"
                    )
                    col_copy1, col_copy2 = st.columns([1, 3])
                    with col_copy1:
                        if st.button("📋 복사", key=f"copy_used_prompt_{scene_id}"):
                            st.session_state[f'clipboard_{scene_id}'] = used_prompt
                            st.toast("프롬프트가 복사되었습니다!")
                    with col_copy2:
                        if composite_info.get('timestamp'):
                            st.caption(f"합성 시간: {composite_info['timestamp']}")


# ═══════════════════════════════════════════════════════════════════════════════
# v3.36: 배치 합성 UI 렌더링
# ═══════════════════════════════════════════════════════════════════════════════

def _render_batch_composite_tab(
    character_scenes: List[Dict],
    all_scenes: List[Dict],
    project_path: str,
    selected_model: str,
    prompt_type: str,
    ref_strength: float,
    on_complete: Callable = None
):
    """
    배치 합성 탭 UI 렌더링 (v3.36)

    다중 씬 선택 후 합성만 일괄 실행하는 UI입니다.
    """
    st.markdown("##### 🎨 배치 합성 - 여러 씬 한번에 합성")
    st.caption("배경+캐릭터 이미지가 모두 있는 씬만 대상으로 합성합니다.")

    # 합성 가능한 씬 계산
    scenes_with_both = []  # 배경+캐릭터 모두 있는 씬
    scenes_bg_only = []    # 배경만 있는 씬
    scenes_char_only = []  # 캐릭터만 있는 씬
    scenes_completed = []  # 이미 합성 완료된 씬

    for scene in character_scenes:
        scene_id = get_scene_number(scene)
        paths = get_scene_image_paths(scene, project_path)

        has_bg = bool(paths.get("background"))
        has_char = bool(paths.get("character"))
        has_comp = bool(paths.get("composite"))

        if has_comp:
            scenes_completed.append(scene_id)
        elif has_bg and has_char:
            scenes_with_both.append(scene_id)
        elif has_bg:
            scenes_bg_only.append(scene_id)
        elif has_char:
            scenes_char_only.append(scene_id)

    # 상태 요약
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("합성 가능", len(scenes_with_both), help="배경+캐릭터 모두 있음")
    with col2:
        st.metric("합성 완료", len(scenes_completed))
    with col3:
        st.metric("배경만", len(scenes_bg_only), help="캐릭터 이미지 필요")
    with col4:
        st.metric("캐릭터만", len(scenes_char_only), help="배경 이미지 필요")

    if not scenes_with_both and not scenes_completed:
        st.warning("합성 가능한 씬이 없습니다. 먼저 '일괄 생성' 탭에서 배경과 캐릭터 이미지를 생성하세요.")
        return

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # 씬 선택 UI
    # ═══════════════════════════════════════════════════════════════

    st.markdown("### 🎯 씬 선택")

    selection_mode = st.radio(
        "선택 방식",
        ["📋 단일 선택", "✏️ 직접 입력 (다중)", "✅ 합성 가능한 전체"],
        horizontal=True,
        key="batch_composite_mode"
    )

    selected_scenes: List[int] = []

    # ── 모드 1: 단일 선택 ──
    if selection_mode == "📋 단일 선택":
        all_compositable = scenes_with_both + scenes_completed
        all_compositable.sort()

        if all_compositable:
            scene_options = []
            for scene_id in all_compositable:
                is_done = "✅" if scene_id in scenes_completed else "⏳"
                scene_options.append(f"씬 {scene_id} {is_done}")

            selected_label = st.selectbox(
                "씬 선택",
                scene_options,
                key="batch_single_scene_select"
            )

            if selected_label:
                # "씬 43 ✅" -> 43
                scene_num = int(selected_label.split()[1])
                selected_scenes = [scene_num]
        else:
            st.warning("합성 가능한 씬이 없습니다.")

    # ── 모드 2: 직접 입력 (다중) ──
    elif selection_mode == "✏️ 직접 입력 (다중)":
        st.info("💡 **입력 형식**: `1,3,5,7` 또는 `1-10` 또는 `1,3,5-10,15`")

        # ═══════════════════════════════════════════════════════════════════
        # ⭐ v3.70: Pending 값 처리 (위젯 생성 전에!)
        # Streamlit session_state 위젯 충돌 방지
        # ═══════════════════════════════════════════════════════════════════
        pending_key = '_batch_multi_scene_input_pending'
        if pending_key in st.session_state:
            st.session_state['batch_multi_scene_input'] = st.session_state[pending_key]
            del st.session_state[pending_key]

        col1, col2 = st.columns([3, 1])

        with col1:
            input_str = st.text_input(
                "씬 번호 입력",
                placeholder="예: 1,3,5-10,15,20-25",
                key="batch_multi_scene_input"
            )

        with col2:
            # 빠른 입력 버튼 (callback 방식으로 값 설정)
            def fill_compositable_scenes_callback():
                """합성 가능한 씬 번호를 pending 값으로 설정"""
                st.session_state['_batch_multi_scene_input_pending'] = ','.join(map(str, scenes_with_both))

            if st.button("합성 가능한 씬만", key="fill_compositable_scenes", on_click=fill_compositable_scenes_callback):
                st.rerun()

        if input_str:
            parsed = parse_scene_numbers(input_str)

            # 유효성 검사
            validation = validate_scene_numbers_for_composite(
                parsed, character_scenes, project_path
            )

            # 결과 표시
            result_cols = st.columns(4)
            with result_cols[0]:
                st.metric("✅ 합성 가능", len(validation['valid']))
            with result_cols[1]:
                st.metric("⚠️ 배경 없음", len(validation['no_background']))
            with result_cols[2]:
                st.metric("⚠️ 캐릭터 없음", len(validation['no_character']))
            with result_cols[3]:
                st.metric("❌ 잘못된 번호", len(validation['invalid']))

            if validation['valid']:
                selected_scenes = validation['valid']
                preview = str(selected_scenes[:15])
                if len(selected_scenes) > 15:
                    preview = preview[:-1] + ", ...]"
                st.success(f"선택된 씬: {preview}")

            if validation['no_background']:
                st.warning(f"배경 없는 씬 (스킵됨): {validation['no_background'][:10]}{'...' if len(validation['no_background']) > 10 else ''}")

            if validation['no_character']:
                st.warning(f"캐릭터 없는 씬 (스킵됨): {validation['no_character'][:10]}{'...' if len(validation['no_character']) > 10 else ''}")

    # ── 모드 3: 전체 선택 ──
    elif selection_mode == "✅ 합성 가능한 전체":
        st.info(f"배경+캐릭터 모두 있는 씬: **{len(scenes_with_both)}**개")

        # 제외할 씬 입력
        exclude_input = st.text_input(
            "제외할 씬 (선택사항)",
            placeholder="예: 5,10-15,30",
            key="batch_exclude_scenes_input"
        )

        selected_scenes = scenes_with_both.copy()

        if exclude_input:
            exclude_nums = parse_scene_numbers(exclude_input)
            selected_scenes = [s for s in selected_scenes if s not in exclude_nums]
            st.info(f"제외 후 선택된 씬: **{len(selected_scenes)}**개")

        # 이미 합성된 씬 제외 옵션
        skip_completed = st.checkbox(
            "이미 합성된 씬 제외",
            value=True,
            key="batch_skip_completed"
        )

        if skip_completed:
            before_count = len(selected_scenes)
            selected_scenes = [s for s in selected_scenes if s not in scenes_completed]
            excluded_count = before_count - len(selected_scenes)
            if excluded_count > 0:
                st.info(f"이미 합성된 {excluded_count}개 씬 제외됨")

        if selected_scenes:
            preview = str(selected_scenes[:15])
            if len(selected_scenes) > 15:
                preview = preview[:-1] + ", ...]"
            st.success(f"선택된 씬 ({len(selected_scenes)}개): {preview}")

    # ═══════════════════════════════════════════════════════════════
    # 실행 옵션
    # ═══════════════════════════════════════════════════════════════

    if not selected_scenes:
        st.warning("합성할 씬을 선택하세요.")
        return

    st.divider()

    st.markdown("### ⚙️ 실행 옵션")

    opt_col1, opt_col2 = st.columns(2)

    with opt_col1:
        delay = st.slider(
            "API 호출 간격 (초)",
            min_value=0.5,
            max_value=5.0,
            value=1.5,
            step=0.5,
            key="batch_api_delay",
            help="레이트 리밋 방지를 위한 대기 시간"
        )

    with opt_col2:
        # 비용 예상
        cost_per_image = 15 if selected_model == "gemini_nano_banana" else 25
        total_cost = len(selected_scenes) * cost_per_image
        st.metric(
            "예상 비용",
            f"~{total_cost:,}원",
            help=f"{len(selected_scenes)}개 씬 × {cost_per_image}원"
        )

    st.divider()

    # ═══════════════════════════════════════════════════════════════
    # 실행 버튼
    # ═══════════════════════════════════════════════════════════════

    if len(selected_scenes) == 1:
        button_text = f"🎨 씬 {selected_scenes[0]} 합성"
    else:
        button_text = f"🎨 {len(selected_scenes)}개 씬 배치 합성 시작"

    if st.button(button_text, type="primary", use_container_width=True, key="run_batch_composite"):
        _execute_batch_composite_only(
            selected_scene_nums=selected_scenes,
            character_scenes=character_scenes,
            all_scenes=all_scenes,
            project_path=project_path,
            model_key=selected_model,
            prompt_type=prompt_type,
            ref_strength=ref_strength,
            delay_seconds=delay,
            on_complete=on_complete
        )


# ═══════════════════════════════════════════════════════════════════════════════
# v3.36: 배치 합성 전용 실행 함수
# ═══════════════════════════════════════════════════════════════════════════════

def _execute_batch_composite_only(
    selected_scene_nums: List[int],
    character_scenes: List[Dict],
    all_scenes: List[Dict],
    project_path: str,
    model_key: str,
    prompt_type: str,
    ref_strength: float,
    delay_seconds: float = 1.0,
    on_complete: Callable = None
) -> Dict:
    """
    배치 합성 전용 실행 (v3.36)

    배경+캐릭터 이미지가 모두 있는 씬만 대상으로 합성만 실행합니다.

    Args:
        selected_scene_nums: 선택된 씬 번호 리스트
        character_scenes: 캐릭터가 있는 전체 씬 목록
        all_scenes: 전체 씬 목록
        project_path: 프로젝트 경로
        model_key: Gemini 모델 키
        prompt_type: 프롬프트 언어 ("english" / "korean")
        ref_strength: 레퍼런스 강도
        delay_seconds: API 호출 간 딜레이
        on_complete: 완료 콜백

    Returns:
        {'success': [], 'failed': [], 'skipped': []}
    """
    results = {
        'success': [],
        'failed': [],
        'skipped': []
    }

    # 씬 번호 → 씬 데이터 맵
    scene_map = {get_scene_number(s): s for s in character_scenes}

    total = len(selected_scene_nums)
    if total == 0:
        st.warning("선택된 씬이 없습니다.")
        return results

    st.markdown("### 🎨 배치 합성 진행")

    # UI 요소
    progress_bar = st.progress(0)
    status_text = st.empty()
    current_image_container = st.empty()
    result_container = st.container()

    try:
        generator = GeminiImageGenerator()

        for idx, scene_num in enumerate(selected_scene_nums):
            # 진행 상황 업데이트
            progress = (idx + 1) / total
            progress_bar.progress(progress)
            status_text.markdown(f"**🎨 씬 {scene_num} 합성 중... ({idx + 1}/{total})**")

            # 씬 데이터 찾기
            scene = scene_map.get(scene_num)
            if not scene:
                results['skipped'].append({'scene': scene_num, 'reason': '씬 데이터 없음'})
                print(f"[배치합성] ⏭️ 씬 {scene_num} 스킵: 씬 데이터 없음")
                continue

            # 이미지 경로 확인
            paths = get_scene_image_paths(scene, project_path)

            bg_path = paths.get("background")
            char_path = paths.get("character")

            if not bg_path or not os.path.exists(bg_path):
                results['skipped'].append({'scene': scene_num, 'reason': '배경 이미지 없음'})
                print(f"[배치합성] ⏭️ 씬 {scene_num} 스킵: 배경 이미지 없음")
                continue

            if not char_path or not os.path.exists(char_path):
                results['skipped'].append({'scene': scene_num, 'reason': '캐릭터 이미지 없음'})
                print(f"[배치합성] ⏭️ 씬 {scene_num} 스킵: 캐릭터 이미지 없음")
                continue

            # 합성 실행
            try:
                print(f"[배치합성] 🎨 씬 {scene_num} 합성 시작...")

                success, result_path, error, composite_info = generate_composite_image(
                    scene=scene,
                    project_path=project_path,
                    generator=generator,
                    background_path=bg_path,
                    character_path=char_path,
                    model_key=model_key,
                    prompt_type=prompt_type,
                    reference_strength=ref_strength
                )

                if success and result_path and os.path.exists(result_path):
                    # 씬 데이터 업데이트
                    update_scene_image_path(scene, "composite", result_path, all_scenes, project_path, composite_info)

                    results['success'].append(scene_num)
                    print(f"[배치합성] ✅ 씬 {scene_num} 완료: {result_path}")

                    # 결과 이미지 미리보기
                    current_image_container.image(result_path, caption=f"씬 {scene_num} 합성 완료", width=400)
                else:
                    results['failed'].append({'scene': scene_num, 'reason': error or '이미지 생성 실패'})
                    print(f"[배치합성] ❌ 씬 {scene_num} 실패: {error}")

            except Exception as e:
                results['failed'].append({'scene': scene_num, 'reason': str(e)})
                print(f"[배치합성] ❌ 씬 {scene_num} 에러: {e}")

            # API 레이트 리밋 방지
            if idx < total - 1:
                time.sleep(delay_seconds)

        # 완료
        progress_bar.progress(1.0)
        status_text.markdown("**✅ 배치 합성 완료!**")
        current_image_container.empty()

        # 결과 표시
        with result_container:
            st.markdown("### 📊 결과 요약")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("✅ 성공", len(results['success']))
            with col2:
                st.metric("❌ 실패", len(results['failed']))
            with col3:
                st.metric("⏭️ 스킵", len(results['skipped']))

            # 상세 정보
            if results['success']:
                with st.expander(f"✅ 성공한 씬 ({len(results['success'])}개)", expanded=False):
                    st.write(f"씬 번호: {results['success']}")

            if results['failed']:
                with st.expander(f"❌ 실패한 씬 ({len(results['failed'])}개)", expanded=True):
                    for item in results['failed']:
                        st.write(f"- 씬 {item['scene']}: {item['reason']}")

            if results['skipped']:
                with st.expander(f"⏭️ 스킵된 씬 ({len(results['skipped'])}개)", expanded=False):
                    for item in results['skipped']:
                        st.write(f"- 씬 {item['scene']}: {item['reason']}")

        if on_complete:
            on_complete(results)

    except Exception as e:
        st.error(f"배치 합성 중 오류: {e}")
        print(f"[배치합성] 오류: {e}")
        import traceback
        traceback.print_exc()

    return results


def _execute_batch_generation(
    scenes: List[Dict],
    all_scenes: List[Dict],
    project_path: str,
    model_key: str,
    prompt_type: str,
    ref_strength: float,
    gen_options: List[str],
    skip_existing: bool,
    on_complete: Callable = None
):
    """일괄 생성 실행"""

    st.markdown("### 🚀 일괄 생성 진행")

    progress_bar = st.progress(0)
    status_text = st.empty()
    result_container = st.container()

    results = {
        "background": {"success": 0, "failed": 0, "skipped": 0},
        "character": {"success": 0, "failed": 0, "skipped": 0},
        "composite": {"success": 0, "failed": 0, "skipped": 0}
    }

    try:
        generator = GeminiImageGenerator()
        total_scenes = len(scenes)

        for idx, scene in enumerate(scenes):
            scene_id = get_scene_number(scene) or (idx + 1)
            paths = get_scene_image_paths(scene, project_path)

            progress = (idx + 1) / total_scenes
            progress_bar.progress(progress)
            status_text.text(f"씬 {scene_id} 처리 중... ({idx + 1}/{total_scenes})")

            # 배경 생성
            if "background" in gen_options:
                if skip_existing and paths["background"]:
                    results["background"]["skipped"] += 1
                else:
                    success, path, error = generate_background_image(
                        scene, project_path, generator, model_key, prompt_type
                    )
                    if success:
                        update_scene_image_path(scene, "background", path, all_scenes, project_path)
                        paths["background"] = path  # 합성에 사용
                        results["background"]["success"] += 1
                    else:
                        results["background"]["failed"] += 1
                    time.sleep(1.5)  # Rate limit

            # 캐릭터 생성
            if "character" in gen_options:
                if skip_existing and paths["character"]:
                    results["character"]["skipped"] += 1
                else:
                    success, path, error = generate_character_image(
                        scene, project_path, generator, model_key, prompt_type
                    )
                    if success:
                        update_scene_image_path(scene, "character", path, all_scenes, project_path)
                        paths["character"] = path  # 합성에 사용
                        results["character"]["success"] += 1
                    else:
                        results["character"]["failed"] += 1
                    time.sleep(1.5)  # Rate limit

            # 합성 생성
            if "composite" in gen_options:
                if skip_existing and paths["composite"]:
                    results["composite"]["skipped"] += 1
                elif paths["background"] and paths["character"]:
                    success, path, error, composite_info = generate_composite_image(
                        scene, project_path, generator,
                        paths["background"], paths["character"],
                        model_key, prompt_type, ref_strength
                    )
                    if success:
                        update_scene_image_path(scene, "composite", path, all_scenes, project_path, composite_info)
                        results["composite"]["success"] += 1
                    else:
                        results["composite"]["failed"] += 1
                    time.sleep(1.5)  # Rate limit
                else:
                    results["composite"]["skipped"] += 1

        # 완료
        progress_bar.progress(1.0)
        status_text.text("완료!")

        # 결과 표시
        with result_container:
            st.markdown("### 결과")

            for img_type, counts in results.items():
                if img_type in gen_options:
                    type_name = {"background": "배경", "character": "캐릭터", "composite": "합성"}[img_type]
                    cols = st.columns(4)
                    cols[0].markdown(f"**{type_name}**")
                    cols[1].metric("성공", counts["success"])
                    cols[2].metric("실패", counts["failed"])
                    cols[3].metric("스킵", counts["skipped"])

            total_success = sum(r["success"] for r in results.values())
            if total_success > 0:
                st.success(f"총 {total_success}개 이미지 생성 완료!")

        if on_complete:
            on_complete(results)

    except Exception as e:
        st.error(f"오류 발생: {e}")
        print(f"[NanoComposite] 오류: {e}")
        import traceback
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════════════
# v3.34: 캐릭터 자동 연동 함수 (페이지 로드 시 호출)
# ═══════════════════════════════════════════════════════════════════════════════

def auto_link_characters_to_scenes(scenes: List[Dict], project_path: str) -> Dict:
    """
    모든 씬에 캐릭터 이미지 자동 연동 (v3.34)

    - 캐릭터 관리에서 생성된 이미지를 각 씬에 자동 연동
    - characters.json의 appearance_scenes 기반 매핑
    - 페이지 로드 시 한 번 호출하여 씬 데이터 업데이트

    Args:
        scenes: 씬 목록
        project_path: 프로젝트 경로

    Returns:
        {
            "linked_count": 연동된 씬 수,
            "total_characters": 연동된 총 캐릭터 수,
            "scenes_updated": [업데이트된 씬 ID 목록]
        }
    """
    result = {
        "linked_count": 0,
        "total_characters": 0,
        "scenes_updated": []
    }

    try:
        from utils.character_image_manager import CharacterImageManager
        char_manager = CharacterImageManager(project_path)
    except ImportError:
        print("[NanoComposite] ⚠️ CharacterImageManager import 실패")
        return result

    print(f"[NanoComposite] 🔗 캐릭터 자동 연동 시작 ({len(scenes)}개 씬)")

    for scene in scenes:
        scene_id = get_scene_number(scene)

        # 이미 연동된 캐릭터가 있고 파일이 존재하면 스킵
        existing_path = scene.get('character_image_path') or scene.get('character_image')
        if existing_path and Path(existing_path).exists():
            continue

        # CharacterImageManager로 이 씬에 등장하는 캐릭터 찾기
        char_images = char_manager.get_all_characters_for_scene(scene)

        if char_images:
            # 첫 번째 캐릭터 이미지를 대표로 설정
            main_char = char_images[0]
            img_path = main_char.get('path')

            if img_path and Path(img_path).exists():
                # 씬 데이터에 캐릭터 정보 저장
                scene['character_image_path'] = img_path
                scene['character_image'] = img_path

                # 모든 캐릭터 정보 저장 (다중 캐릭터 지원)
                scene['linked_characters'] = char_images
                scene['character_images'] = [c.get('path') for c in char_images if c.get('path')]

                result["linked_count"] += 1
                result["total_characters"] += len(char_images)
                result["scenes_updated"].append(scene_id)

                char_names = [c.get('name', '?') for c in char_images]
                print(f"[NanoComposite] ✅ 씬 {scene_id}: {len(char_images)}명 자동 연동 ({', '.join(char_names)})")

    print(f"[NanoComposite] 🔗 자동 연동 완료: {result['linked_count']}개 씬, {result['total_characters']}명 캐릭터")
    return result


def get_auto_linked_character_count(scenes: List[Dict], project_path: str) -> int:
    """
    자동 연동 가능한 캐릭터 수 반환 (미리보기용)

    Args:
        scenes: 씬 목록
        project_path: 프로젝트 경로

    Returns:
        연동 가능한 캐릭터 수
    """
    try:
        from utils.character_image_manager import CharacterImageManager
        char_manager = CharacterImageManager(project_path)
    except ImportError:
        return 0

    count = 0
    for scene in scenes:
        # 이미 연동된 경우 제외
        existing_path = scene.get('character_image_path') or scene.get('character_image')
        if existing_path and Path(existing_path).exists():
            continue

        char_images = char_manager.get_all_characters_for_scene(scene)
        if char_images:
            count += 1

    return count


# 내보내기
__all__ = [
    'render_nano_banana_composite',
    'has_character_prompt',
    'get_character_scenes',
    'get_scene_number',
    'get_scene_image_paths',
    'generate_background_image',
    'generate_character_image',
    'generate_composite_image',
    'auto_link_characters_to_scenes',
    'get_auto_linked_character_count',
    # v3.35: 상세 로깅 함수
    'log_reference_image_details',
    'log_full_prompt',
    # v3.36: 배치 선택 헬퍼 함수
    'parse_scene_numbers',
    'validate_scene_numbers_for_composite'
]
