"""
캐릭터 이미지 관리 유틸리티

기능:
- 이미지 목록 조회
- 전체/개별 선택
- 일괄 삭제
- 대표 이미지 관리 (최신 이미지 자동 대표)
"""

import os
import json
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class CharacterImageManager:
    """캐릭터 이미지 관리자"""

    def __init__(self, project_path: str):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path)
        self.characters_dir = self.project_path / "characters"
        self.images_dir = self.project_path / "images" / "characters"
        self.analysis_file = self.project_path / "analysis" / "characters.json"
        self.char_data_file = self.project_path / "characters" / "characters.json"

        # 디렉토리 확인
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def get_all_character_images(self) -> List[Dict]:
        """
        모든 캐릭터 이미지 목록 조회

        Returns:
            [
                {
                    "filename": "char_자말카슈크지_standing_1703001234.png",
                    "path": "full/path/to/image.png",
                    "character_name": "자말 카슈크지",
                    "pose": "standing",
                    "timestamp": 1703001234,
                    "created_at": "2024-12-27 10:30:45",
                    "size_bytes": 123456,
                    "is_representative": True
                },
                ...
            ]
        """
        images = []

        # 여러 디렉토리에서 이미지 검색
        search_dirs = [
            self.images_dir,
            self.characters_dir,
            self.project_path / "images",
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            # char_*.png 패턴 검색
            for img_file in search_dir.glob("char_*.png"):
                img_info = self._parse_image_filename(img_file)
                if img_info:
                    images.append(img_info)

            # 캐릭터 ID 기반 파일 검색 (예: char_001.png)
            for img_file in search_dir.glob("*.png"):
                if img_file.name.startswith("char_"):
                    continue  # 이미 처리됨

                # ID 기반 파일 처리
                img_info = self._parse_id_based_filename(img_file)
                if img_info:
                    images.append(img_info)

        # 중복 제거 (파일 경로 기준)
        seen = set()
        unique_images = []
        for img in images:
            if img["path"] not in seen:
                seen.add(img["path"])
                unique_images.append(img)

        # 타임스탬프 기준 정렬 (최신순)
        unique_images.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        # 대표 이미지 표시
        self._mark_representative_images(unique_images)

        return unique_images

    def _parse_image_filename(self, img_path: Path) -> Optional[Dict]:
        """
        이미지 파일명 파싱

        패턴들:
        - char_{캐릭터명}_{포즈}_{타임스탬프}.png
        - char_{캐릭터명}_{타임스탬프}.png
        """
        filename = img_path.name

        # 패턴 1: char_XXX_YYY_TIMESTAMP.png
        pattern1 = r"char_(.+?)_(\w+)_(\d{10,13})\.png"
        match = re.match(pattern1, filename)

        if match:
            char_name = match.group(1).replace("_", " ")
            pose = match.group(2)
            timestamp = int(match.group(3))
        else:
            # 패턴 2: char_XXX_TIMESTAMP.png
            pattern2 = r"char_(.+?)_(\d{10,13})\.png"
            match2 = re.match(pattern2, filename)

            if match2:
                char_name = match2.group(1).replace("_", " ")
                pose = "default"
                timestamp = int(match2.group(2))
            else:
                # 패턴 3: char_XXX.png (타임스탬프 없음 → 파일 수정 시간 사용)
                pattern3 = r"char_(.+?)\.png"
                match3 = re.match(pattern3, filename)

                if match3:
                    char_name = match3.group(1).replace("_", " ")
                    pose = "default"
                    timestamp = int(img_path.stat().st_mtime * 1000)
                else:
                    return None

        # 파일 정보
        try:
            stat = img_path.stat()
            size_bytes = stat.st_size
        except:
            size_bytes = 0

        # 타임스탬프 변환
        if timestamp > 1e12:  # 밀리초
            created_at = datetime.fromtimestamp(timestamp / 1000)
        else:  # 초
            created_at = datetime.fromtimestamp(timestamp)

        return {
            "filename": filename,
            "path": str(img_path.absolute()),
            "character_name": char_name,
            "pose": pose,
            "timestamp": timestamp,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "size_bytes": size_bytes,
            "is_representative": False
        }

    def _parse_id_based_filename(self, img_path: Path) -> Optional[Dict]:
        """
        ID 기반 파일명 파싱 (예: char_001.png → 캐릭터 데이터에서 이름 조회)
        """
        filename = img_path.name

        # 캐릭터 데이터 로드
        char_data = self._load_character_data()

        # 파일명에서 ID 추출
        stem = img_path.stem  # 확장자 제외

        # ID로 캐릭터 찾기
        char_name = None
        for char in char_data:
            if char.get("id") == stem or char.get("id") == filename:
                char_name = char.get("name", stem)
                break

        if not char_name:
            return None

        try:
            stat = img_path.stat()
            timestamp = int(stat.st_mtime * 1000)
            size_bytes = stat.st_size
        except:
            timestamp = 0
            size_bytes = 0

        created_at = datetime.fromtimestamp(timestamp / 1000)

        return {
            "filename": filename,
            "path": str(img_path.absolute()),
            "character_name": char_name,
            "pose": "default",
            "timestamp": timestamp,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "size_bytes": size_bytes,
            "is_representative": False
        }

    def _load_character_data(self) -> List[Dict]:
        """캐릭터 데이터 로드"""
        # characters/characters.json 먼저 시도
        if self.char_data_file.exists():
            try:
                with open(self.char_data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass

        # analysis/characters.json 시도
        if self.analysis_file.exists():
            try:
                with open(self.analysis_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass

        return []

    def _mark_representative_images(self, images: List[Dict]):
        """각 캐릭터별 최신 이미지를 대표로 표시"""
        # 캐릭터별 그룹화
        char_groups = {}
        for img in images:
            char_name = img["character_name"]
            if char_name not in char_groups:
                char_groups[char_name] = []
            char_groups[char_name].append(img)

        # 각 그룹에서 최신(첫 번째)을 대표로
        for char_name, group in char_groups.items():
            # 이미 timestamp 기준 정렬됨 (최신순)
            if group:
                group[0]["is_representative"] = True

    def get_images_by_character(self, character_name: str) -> List[Dict]:
        """특정 캐릭터의 모든 이미지"""
        all_images = self.get_all_character_images()
        return [img for img in all_images if img["character_name"] == character_name]

    def get_representative_image(self, character_name: str) -> Optional[str]:
        """
        캐릭터의 대표 이미지 경로 반환 (최신 이미지)

        Returns:
            이미지 파일 경로 또는 None
        """
        images = self.get_images_by_character(character_name)
        if not images:
            return None

        # 최신 이미지 (첫 번째)
        return images[0]["path"]

    def delete_images(self, filenames: List[str]) -> Dict:
        """
        이미지 삭제

        Args:
            filenames: 삭제할 파일명 리스트

        Returns:
            {"deleted": [...], "failed": [...]}
        """
        result = {"deleted": [], "failed": []}

        all_images = self.get_all_character_images()
        path_map = {img["filename"]: img["path"] for img in all_images}

        for filename in filenames:
            if filename not in path_map:
                result["failed"].append({"filename": filename, "reason": "파일 없음"})
                continue

            try:
                file_path = Path(path_map[filename])
                if file_path.exists():
                    file_path.unlink()
                    result["deleted"].append(filename)
                    print(f"[캐릭터 이미지] 삭제됨: {filename}")
                else:
                    result["failed"].append({"filename": filename, "reason": "파일 없음"})
            except Exception as e:
                result["failed"].append({"filename": filename, "reason": str(e)})
                print(f"[캐릭터 이미지] 삭제 실패: {filename} - {e}")

        return result

    def delete_all_images(self) -> Dict:
        """모든 캐릭터 이미지 삭제"""
        all_images = self.get_all_character_images()
        filenames = [img["filename"] for img in all_images]
        return self.delete_images(filenames)

    def delete_old_images(self, character_name: str, keep_count: int = 1) -> Dict:
        """
        특정 캐릭터의 오래된 이미지 삭제 (최신 N개만 유지)

        Args:
            character_name: 캐릭터 이름
            keep_count: 유지할 이미지 수 (기본 1 = 대표만)

        Returns:
            삭제 결과
        """
        images = self.get_images_by_character(character_name)

        if len(images) <= keep_count:
            return {"deleted": [], "failed": []}

        # 최신 keep_count개 제외하고 삭제
        to_delete = [img["filename"] for img in images[keep_count:]]
        return self.delete_images(to_delete)

    def set_representative_image(self, character_name: str, filename: str) -> bool:
        """
        대표 이미지 수동 설정
        (파일을 가장 최신 타임스탬프로 복사)
        """
        images = self.get_images_by_character(character_name)

        target = None
        for img in images:
            if img["filename"] == filename:
                target = img
                break

        if not target:
            return False

        # 새 타임스탬프로 복사
        new_timestamp = int(datetime.now().timestamp() * 1000)
        old_path = Path(target["path"])

        # 새 파일명 생성
        safe_name = character_name.replace(" ", "_")
        new_filename = f"char_{safe_name}_{target['pose']}_{new_timestamp}.png"
        new_path = old_path.parent / new_filename

        try:
            shutil.copy2(old_path, new_path)
            print(f"[캐릭터 이미지] 대표 설정: {character_name} → {new_filename}")
            return True
        except Exception as e:
            print(f"[캐릭터 이미지] 대표 설정 실패: {e}")
            return False

    def update_character_data_with_latest_images(self) -> int:
        """
        캐릭터 데이터에 최신 이미지 경로 반영

        Returns:
            업데이트된 캐릭터 수
        """
        updated = 0

        # characters/characters.json 업데이트
        if self.char_data_file.exists():
            updated += self._update_json_file(self.char_data_file)

        return updated

    def _update_json_file(self, json_path: Path) -> int:
        """JSON 파일의 캐릭터 이미지 경로 업데이트"""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                characters = json.load(f)
        except Exception as e:
            print(f"[캐릭터 이미지] JSON 로드 실패: {e}")
            return 0

        updated = 0

        for char in characters:
            char_name = char.get("name", "")
            if not char_name:
                continue

            latest_image = self.get_representative_image(char_name)

            if latest_image:
                # generated_images 리스트 업데이트 (최신을 맨 앞으로)
                if "generated_images" in char:
                    if latest_image not in char["generated_images"]:
                        char["generated_images"].insert(0, latest_image)
                        updated += 1
                else:
                    char["generated_images"] = [latest_image]
                    updated += 1

        if updated > 0:
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(characters, f, ensure_ascii=False, indent=2)
                print(f"[캐릭터 이미지] {updated}개 캐릭터 이미지 경로 업데이트됨")
            except Exception as e:
                print(f"[캐릭터 이미지] JSON 저장 실패: {e}")
                return 0

        return updated

    def get_statistics(self) -> Dict:
        """이미지 통계"""
        all_images = self.get_all_character_images()

        # 캐릭터별 이미지 수
        char_counts = {}
        total_size = 0

        for img in all_images:
            char_name = img["character_name"]
            char_counts[char_name] = char_counts.get(char_name, 0) + 1
            total_size += img.get("size_bytes", 0)

        return {
            "total_images": len(all_images),
            "total_characters": len(char_counts),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "images_per_character": char_counts,
            "duplicates": sum(1 for c in char_counts.values() if c > 1)
        }

    def cleanup_duplicate_images(self, keep_count: int = 1) -> Dict:
        """
        모든 캐릭터의 중복 이미지 정리

        Args:
            keep_count: 캐릭터당 유지할 이미지 수

        Returns:
            삭제 결과
        """
        stats = self.get_statistics()

        total_result = {"deleted": [], "failed": []}

        for char_name, count in stats["images_per_character"].items():
            if count > keep_count:
                result = self.delete_old_images(char_name, keep_count=keep_count)
                total_result["deleted"].extend(result["deleted"])
                total_result["failed"].extend(result["failed"])

        # 대표 이미지 업데이트
        if total_result["deleted"]:
            self.update_character_data_with_latest_images()

        return total_result


def on_character_image_generated(project_path: str, character_name: str, image_path: str):
    """
    캐릭터 이미지 생성 완료 후 호출
    최신 이미지를 대표로 자동 설정
    """
    manager = CharacterImageManager(project_path)
    manager.update_character_data_with_latest_images()
    print(f"[캐릭터 이미지] {character_name} 대표 이미지 자동 업데이트됨")
