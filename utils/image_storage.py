"""
이미지 저장 유틸리티

배경, 캐릭터, 합성 이미지를 세션 상태와 프로젝트 파일에 저장
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st


def save_background_image(scene_id: int, result: Dict, project_path: Path = None):
    """
    배경 이미지 저장

    Args:
        scene_id: 씬 ID
        result: 생성 결과 {"image_path": ..., "prompt": ..., ...}
        project_path: 프로젝트 경로
    """
    # 세션 상태에 저장
    if "background_images" not in st.session_state:
        st.session_state["background_images"] = {}

    st.session_state["background_images"][scene_id] = result

    # 프로젝트 파일에도 저장
    if project_path:
        project_path = Path(project_path)
        backgrounds_file = project_path / "images" / "backgrounds" / "backgrounds.json"
        backgrounds_file.parent.mkdir(parents=True, exist_ok=True)

        # 기존 데이터 로드
        existing = {}
        if backgrounds_file.exists():
            try:
                with open(backgrounds_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        # 업데이트
        existing[str(scene_id)] = result

        # 저장
        with open(backgrounds_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"[저장] 씬 {scene_id} 배경 이미지 저장됨")


def load_background_images(project_path: Path) -> Dict[int, Dict]:
    """
    배경 이미지 로드

    Args:
        project_path: 프로젝트 경로

    Returns:
        {scene_id: {"image_path": ..., ...}}
    """
    # 세션 상태에서 먼저 확인
    if "background_images" in st.session_state and st.session_state["background_images"]:
        return st.session_state["background_images"]

    # 파일에서 로드
    project_path = Path(project_path)
    backgrounds_file = project_path / "images" / "backgrounds" / "backgrounds.json"

    if backgrounds_file.exists():
        try:
            with open(backgrounds_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 키를 int로 변환
                result = {int(k): v for k, v in data.items()}
                st.session_state["background_images"] = result
                return result
        except Exception:
            pass

    return {}


def save_character_image(character_name: str, result: Dict, project_path: Path = None):
    """
    캐릭터 이미지 저장

    Args:
        character_name: 캐릭터 이름
        result: 생성 결과 {"image_path": ..., "pose": ..., ...}
        project_path: 프로젝트 경로
    """
    # 세션 상태에 저장
    if "character_images" not in st.session_state:
        st.session_state["character_images"] = {}

    st.session_state["character_images"][character_name] = result

    # characters 리스트에도 업데이트
    if "characters" in st.session_state:
        for char in st.session_state["characters"]:
            if char.get("name") == character_name:
                char["image_url"] = result.get("image_url") or result.get("image_path")
                char["image_path"] = result.get("image_path")
                break

    # 프로젝트 파일에도 저장
    if project_path:
        project_path = Path(project_path)
        chars_file = project_path / "images" / "characters" / "character_images.json"
        chars_file.parent.mkdir(parents=True, exist_ok=True)

        # 기존 데이터 로드
        existing = {}
        if chars_file.exists():
            try:
                with open(chars_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        # 업데이트
        existing[character_name] = result

        # 저장
        with open(chars_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"[저장] 캐릭터 '{character_name}' 이미지 저장됨")


def load_character_images(project_path: Path) -> Dict[str, Dict]:
    """
    캐릭터 이미지 로드 (여러 소스에서)

    Args:
        project_path: 프로젝트 경로

    Returns:
        {character_name: {"image_path": ..., ...}}
    """
    project_path = Path(project_path)
    result = {}

    # 1. 세션 상태의 character_images에서 확인
    if "character_images" in st.session_state and st.session_state["character_images"]:
        result = st.session_state["character_images"].copy()
        print(f"[load_character_images] 세션 character_images에서 {len(result)}개 로드")

    # 2. 세션 상태의 characters 리스트에서 image_url/image_path 추출
    characters = st.session_state.get("characters", [])
    if not characters:
        # scene_characters 키도 확인
        characters = st.session_state.get("scene_characters", [])

    for char in characters:
        name = char.get("name")
        if not name:
            continue

        # 이미 result에 있으면 스킵
        if name in result and (result[name].get("image_path") or result[name].get("image_url")):
            continue

        # 캐릭터에 이미지 정보가 있으면 추가
        image_path = char.get("image_path") or char.get("image_url")
        if image_path:
            result[name] = {
                "name": name,
                "image_path": image_path,
                "image_url": image_path
            }
            print(f"[load_character_images] characters 리스트에서 '{name}' 이미지 발견")

    # 3. CharacterManager에서 이미지 로드
    try:
        from core.character.character_manager import CharacterManager
        manager = CharacterManager(str(project_path))
        all_chars = manager.get_all_characters()

        for char in all_chars:
            name = char.name
            if name in result and (result[name].get("image_path") or result[name].get("image_url")):
                continue

            # generated_images에서 가장 최근 이미지 사용
            if char.generated_images:
                latest_image = char.generated_images[-1]
                result[name] = {
                    "name": name,
                    "image_path": latest_image,
                    "image_url": latest_image
                }
                print(f"[load_character_images] CharacterManager에서 '{name}' 이미지 발견")
    except Exception as e:
        print(f"[load_character_images] CharacterManager 로드 실패: {e}")

    # 4. 파일에서 로드
    chars_file = project_path / "images" / "characters" / "character_images.json"
    if chars_file.exists():
        try:
            with open(chars_file, "r", encoding="utf-8") as f:
                file_data = json.load(f)
                for name, info in file_data.items():
                    if name not in result or not (result[name].get("image_path") or result[name].get("image_url")):
                        result[name] = info
                        print(f"[load_character_images] 파일에서 '{name}' 이미지 발견")
        except Exception as e:
            print(f"[load_character_images] 파일 로드 실패: {e}")

    # 5. 이미지 폴더에서 직접 스캔
    char_image_dir = project_path / "images" / "characters"
    if char_image_dir.exists():
        for img_path in char_image_dir.glob("*.png"):
            # 파일명에서 캐릭터 이름 추출 시도 (char_이름_pose_timestamp.png)
            filename = img_path.stem
            if filename.startswith("char_"):
                parts = filename.split("_")
                if len(parts) >= 2:
                    # char_NAME_pose_timestamp 형식
                    potential_name = parts[1]
                    # 이미 있는 캐릭터 이름과 매칭 시도
                    for char in characters:
                        char_name = char.get("name", "")
                        # 이름이 파일명에 포함되어 있으면 매칭
                        safe_char_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in char_name)
                        if safe_char_name.lower() == potential_name.lower() or potential_name.lower() in safe_char_name.lower():
                            if char_name not in result or not result[char_name].get("image_path"):
                                result[char_name] = {
                                    "name": char_name,
                                    "image_path": str(img_path),
                                    "image_url": str(img_path)
                                }
                                print(f"[load_character_images] 폴더 스캔으로 '{char_name}' 이미지 발견: {img_path}")
                            break

    # 세션에 저장
    if result:
        st.session_state["character_images"] = result

    print(f"[load_character_images] 총 {len(result)}개 캐릭터 이미지 로드됨")
    for name, info in result.items():
        print(f"  - {name}: {info.get('image_path', 'N/A')[:50]}...")

    return result


def save_composited_image(scene_id: int, result: Dict, project_path: Path = None):
    """
    합성된 이미지 저장

    Args:
        scene_id: 씬 ID
        result: 합성 결과 {"image_path": ..., "characters_used": [...], ...}
        project_path: 프로젝트 경로
    """
    # 세션 상태에 저장
    if "composited_images" not in st.session_state:
        st.session_state["composited_images"] = {}

    st.session_state["composited_images"][scene_id] = result

    # generated_images에도 저장 (스토리보드 호환)
    if "generated_images" not in st.session_state:
        st.session_state["generated_images"] = []

    # 기존 항목 업데이트 또는 추가
    existing_idx = None
    for i, img in enumerate(st.session_state["generated_images"]):
        if img.get("scene_id") == scene_id:
            existing_idx = i
            break

    if existing_idx is not None:
        st.session_state["generated_images"][existing_idx] = result
    else:
        st.session_state["generated_images"].append(result)

    # 프로젝트 파일에도 저장
    if project_path:
        project_path = Path(project_path)
        comp_file = project_path / "images" / "composited" / "composited.json"
        comp_file.parent.mkdir(parents=True, exist_ok=True)

        # 기존 데이터 로드
        existing = {}
        if comp_file.exists():
            try:
                with open(comp_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        # 업데이트
        existing[str(scene_id)] = result

        # 저장
        with open(comp_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"[저장] 씬 {scene_id} 합성 이미지 저장됨")


def load_composited_images(project_path: Path) -> Dict[int, Dict]:
    """
    합성된 이미지 로드

    Args:
        project_path: 프로젝트 경로

    Returns:
        {scene_id: {"image_path": ..., ...}}
    """
    # 세션 상태에서 먼저 확인
    if "composited_images" in st.session_state and st.session_state["composited_images"]:
        return st.session_state["composited_images"]

    # 파일에서 로드
    project_path = Path(project_path)
    comp_file = project_path / "images" / "composited" / "composited.json"

    if comp_file.exists():
        try:
            with open(comp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 키를 int로 변환
                result = {int(k): v for k, v in data.items()}
                st.session_state["composited_images"] = result
                return result
        except Exception:
            pass

    return {}


def get_all_scene_images(project_path: Path) -> Dict[int, Dict]:
    """
    모든 씬 이미지 가져오기 (합성 이미지 우선, 없으면 배경)

    Args:
        project_path: 프로젝트 경로

    Returns:
        {scene_id: {"image_path": ..., "is_composited": bool, ...}}
    """
    composited = load_composited_images(project_path)
    backgrounds = load_background_images(project_path)

    result = {}

    # 모든 씬 ID 수집
    all_scene_ids = set(composited.keys()) | set(backgrounds.keys())

    for scene_id in all_scene_ids:
        if scene_id in composited:
            result[scene_id] = composited[scene_id]
        elif scene_id in backgrounds:
            result[scene_id] = backgrounds[scene_id]

    return result


def sync_characters_to_session(characters: List[Dict], character_images: Dict[str, Dict]):
    """
    캐릭터 이미지 정보를 캐릭터 목록에 동기화

    Args:
        characters: 캐릭터 목록
        character_images: 캐릭터 이미지 정보
    """
    for char in characters:
        name = char.get("name")
        if name and name in character_images:
            img_info = character_images[name]
            char["image_url"] = img_info.get("image_url") or img_info.get("image_path")
            char["image_path"] = img_info.get("image_path")

    st.session_state["characters"] = characters
