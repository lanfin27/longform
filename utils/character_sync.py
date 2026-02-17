"""
캐릭터 데이터 동기화 유틸리티
character_prompt ↔ characters 배열 동기화

v1.0 - 2026-01-31
"""
import json
from pathlib import Path
from typing import Optional, List, Dict, Tuple


def parse_character_from_prompt(
    character_prompt: str,
    character_prompt_en: str = ""
) -> Optional[dict]:
    """
    character_prompt 문자열에서 캐릭터 정보 파싱

    Args:
        character_prompt: 한글 캐릭터 프롬프트
            예: "이재용 회장, 깊은 생각에 잠긴 표정, 정장 차림."
        character_prompt_en: 영문 캐릭터 프롬프트
            예: "Lee Jae-yong, a confident businessman, middle-aged, dark suit, no text, no logos..."

    Returns:
        파싱된 캐릭터 딕셔너리 또는 None
    """
    if not character_prompt or not character_prompt.strip():
        return None

    # 한글 프롬프트 파싱
    kr_parts = [p.strip() for p in character_prompt.split(",")]
    if not kr_parts or len(kr_parts[0]) > 30 or len(kr_parts[0]) < 1:
        return None

    name = kr_parts[0]

    # 영문 프롬프트 파싱
    en_parts = []
    if character_prompt_en:
        # "no text, no logos..." 부분 제거
        clean_en = character_prompt_en
        no_text_idx = clean_en.lower().find(", no text")
        if no_text_idx > 0:
            clean_en = clean_en[:no_text_idx]
        en_parts = [p.strip() for p in clean_en.split(",")]

    name_en = en_parts[0] if en_parts else ""
    visual_prompt = ", ".join(en_parts[1:]) if len(en_parts) > 1 else ""

    return {
        "name": name,
        "name_en": name_en,
        "visual_prompt": visual_prompt
    }


def sync_character_prompt_to_array(scene: dict) -> dict:
    """
    단일 씬의 character_prompt를 characters 배열로 동기화

    Args:
        scene: 씬 데이터 딕셔너리

    Returns:
        동기화된 씬 데이터 (원본 수정됨)
    """
    character_prompt = (scene.get("character_prompt") or "").strip()
    character_prompt_en = (scene.get("character_prompt_en") or "").strip()
    current_characters = scene.get("characters", [])

    # character_prompt가 있고 characters가 비어있는 경우에만 동기화
    if character_prompt and not current_characters:
        parsed = parse_character_from_prompt(character_prompt, character_prompt_en)

        if parsed:
            scene["characters"] = [parsed]
            scene_num = scene.get("scene_number", scene.get("scene_id", "?"))
            print(f"[동기화] 씬 {scene_num}: '{parsed['name']}' 캐릭터 추가됨")

    return scene


def sync_all_scenes_characters(scenes: list) -> Tuple[list, int]:
    """
    모든 씬의 character_prompt -> characters 동기화

    Args:
        scenes: 씬 데이터 리스트

    Returns:
        (수정된 씬 리스트, 동기화된 씬 수)
    """
    synced_count = 0

    for scene in scenes:
        had_characters = bool(scene.get("characters"))
        original_prompt = scene.get("character_prompt") or ""

        sync_character_prompt_to_array(scene)

        # 동기화가 발생했는지 확인
        if not had_characters and scene.get("characters") and original_prompt:
            synced_count += 1

    return scenes, synced_count


def get_sync_status(scenes: list) -> dict:
    """
    현재 동기화 상태 확인

    Returns:
        {
            "total": 총 씬 수,
            "has_prompt": character_prompt 있는 씬 수,
            "has_array": characters 배열 있는 씬 수,
            "needs_sync": 동기화 필요한 씬 수,
            "mismatch_scenes": 불일치 씬 번호 리스트
        }
    """
    total = len(scenes)
    has_prompt = 0
    has_array = 0
    mismatch_scenes = []

    for scene in scenes:
        prompt = (scene.get("character_prompt") or "").strip()
        array = scene.get("characters", [])
        scene_num = scene.get("scene_number", scene.get("scene_id", 0))

        if prompt:
            has_prompt += 1
        if array:
            has_array += 1
        if prompt and not array:
            mismatch_scenes.append(scene_num)

    return {
        "total": total,
        "has_prompt": has_prompt,
        "has_array": has_array,
        "needs_sync": len(mismatch_scenes),
        "mismatch_scenes": mismatch_scenes
    }


def extract_all_characters_from_scenes(scenes: list) -> list:
    """
    모든 씬에서 캐릭터 정보 추출 (characters.json 생성용)

    Returns:
        고유 캐릭터 리스트 (등장 씬 정보 포함)
    """
    characters_dict: Dict[str, dict] = {}

    for scene in scenes:
        scene_num = scene.get("scene_number", scene.get("scene_id", 0))

        # 1. characters 배열에서 추출
        for char in scene.get("characters", []):
            if isinstance(char, dict):
                name = char.get("name", "")
            elif isinstance(char, str):
                name = char
            else:
                continue

            if not name or name.lower() in ('narrator', '나레이터', 'unknown'):
                continue

            if name not in characters_dict:
                if isinstance(char, dict):
                    characters_dict[name] = {
                        "name": name,
                        "name_en": char.get("name_en", ""),
                        "visual_prompt": char.get("visual_prompt", ""),
                        "scenes": []
                    }
                else:
                    characters_dict[name] = {
                        "name": name,
                        "name_en": "",
                        "visual_prompt": "",
                        "scenes": []
                    }

            if scene_num not in characters_dict[name]["scenes"]:
                characters_dict[name]["scenes"].append(scene_num)

        # 2. character_prompt에서 추출 (characters 배열이 비어있는 경우 보완)
        if not scene.get("characters"):
            char_prompt = (scene.get("character_prompt") or "").strip()
            char_prompt_en = (scene.get("character_prompt_en") or "").strip()

            if char_prompt:
                parsed = parse_character_from_prompt(char_prompt, char_prompt_en)
                if parsed:
                    name = parsed["name"]
                    if name not in characters_dict:
                        characters_dict[name] = {
                            "name": name,
                            "name_en": parsed.get("name_en", ""),
                            "visual_prompt": parsed.get("visual_prompt", ""),
                            "scenes": []
                        }
                    if scene_num not in characters_dict[name]["scenes"]:
                        characters_dict[name]["scenes"].append(scene_num)

    # 리스트로 변환 및 등장 횟수로 정렬
    result = list(characters_dict.values())
    result.sort(key=lambda x: len(x["scenes"]), reverse=True)

    return result


def update_characters_json(scenes: list, characters_path: Path) -> int:
    """
    scenes.json의 캐릭터 정보로 characters.json 업데이트

    Args:
        scenes: 씬 데이터 리스트
        characters_path: characters.json 파일 경로

    Returns:
        추가된 캐릭터 수
    """
    # 기존 characters.json 로드
    existing = []
    if characters_path.exists():
        try:
            with open(characters_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception as e:
            print(f"[경고] characters.json 로드 실패: {e}")
            existing = []

    existing_names = set()
    for c in existing:
        name = c.get("name") if isinstance(c, dict) else str(c)
        if name:
            existing_names.add(name)

    # scenes에서 캐릭터 추출
    extracted = extract_all_characters_from_scenes(scenes)

    # 새 캐릭터 추가
    added_count = 0
    for char in extracted:
        name = char.get("name")
        if name and name not in existing_names:
            existing.append({
                "name": name,
                "name_en": char.get("name_en", ""),
                "description": char.get("visual_prompt", ""),
                "visual_prompt": char.get("visual_prompt", ""),
                "scenes": char.get("scenes", [])
            })
            existing_names.add(name)
            added_count += 1
            print(f"[캐릭터 추가] {name} (등장: {len(char.get('scenes', []))}개 씬)")
        elif name:
            # 기존 캐릭터의 씬 정보 업데이트
            for ec in existing:
                ec_name = ec.get("name") if isinstance(ec, dict) else None
                if ec_name == name:
                    for scene_num in char.get("scenes", []):
                        if scene_num not in ec.get("scenes", []):
                            ec.setdefault("scenes", []).append(scene_num)
                    break

    # 저장
    characters_path.parent.mkdir(parents=True, exist_ok=True)
    with open(characters_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"[OK] characters.json 업데이트: 총 {len(existing)}명 (신규 {added_count}명)")

    return added_count
