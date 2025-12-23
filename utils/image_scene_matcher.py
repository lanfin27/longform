# -*- coding: utf-8 -*-
"""
이미지-씬 자동 매칭 모듈

기능:
1. 이미지 파일명에서 씬 번호 추출
2. 씬 데이터와 이미지 자동 매칭
3. 스토리보드 자동 동기화

파일명 패턴 지원:
- scene_001.png, scene_002.png
- seg_001_xxx.png
- 001.png, 002.png
- image_1.png, image_2.png
- xxx_scene1.png, xxx_scene2.png
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class ImageSceneMatcher:
    """이미지-씬 자동 매칭 클래스"""

    # 씬 번호 추출 패턴 (우선순위 순)
    SCENE_PATTERNS = [
        # scene_001, scene_1, scene001
        r'scene[_-]?(\d+)',
        # seg_001, seg_1
        r'seg[_-]?(\d+)',
        # 001.png (파일명이 숫자로만 구성)
        r'^(\d+)$',
        # image_001, img_1
        r'(?:image|img)[_-]?(\d+)',
        # xxx_001 (끝에 숫자)
        r'[_-](\d+)$',
        # composited_scene_001
        r'composited[_-]?scene[_-]?(\d+)',
        # 001_xxx (시작에 숫자)
        r'^(\d+)[_-]',
    ]

    def __init__(self, project_path: Path):
        """
        Args:
            project_path: 프로젝트 경로
        """
        self.project_path = Path(project_path)
        self.images_dir = self.project_path / "images"
        self.scenes_images_dir = self.images_dir / "scenes"
        self.content_images_dir = self.images_dir / "content"
        self.composited_dir = self.images_dir / "composited"

    def extract_scene_number(self, filename: str) -> Optional[int]:
        """
        파일명에서 씬 번호 추출

        Args:
            filename: 파일명 (확장자 포함/미포함)

        Returns:
            씬 번호 (정수) 또는 None
        """
        # 확장자 제거
        name = Path(filename).stem.lower()

        for pattern in self.SCENE_PATTERNS:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

        return None

    def find_all_images(self) -> List[Dict]:
        """
        프로젝트 내 모든 이미지 찾기

        Returns:
            이미지 정보 목록
            [
                {
                    "path": Path,
                    "filename": str,
                    "scene_number": int or None,
                    "source": "composited" | "scenes" | "content",
                    "created": datetime
                }
            ]
        """
        images = []

        # 디렉토리 우선순위: composited > scenes > content
        dirs_to_search = [
            (self.composited_dir, "composited"),
            (self.scenes_images_dir, "scenes"),
            (self.content_images_dir, "content"),
        ]

        for img_dir, source in dirs_to_search:
            if not img_dir.exists():
                continue

            for img_path in img_dir.glob("*.png"):
                scene_num = self.extract_scene_number(img_path.name)

                images.append({
                    "path": img_path,
                    "filename": img_path.name,
                    "scene_number": scene_num,
                    "source": source,
                    "created": datetime.fromtimestamp(img_path.stat().st_mtime)
                })

            # jpg, webp도 지원
            for ext in ["*.jpg", "*.jpeg", "*.webp"]:
                for img_path in img_dir.glob(ext):
                    scene_num = self.extract_scene_number(img_path.name)
                    images.append({
                        "path": img_path,
                        "filename": img_path.name,
                        "scene_number": scene_num,
                        "source": source,
                        "created": datetime.fromtimestamp(img_path.stat().st_mtime)
                    })

        return images

    def match_images_to_scenes(
        self,
        scenes: List[Dict],
        prefer_composited: bool = True
    ) -> Dict[int, Dict]:
        """
        씬 데이터에 이미지 매칭

        Args:
            scenes: 씬 목록 (scene_id 포함)
            prefer_composited: 합성 이미지 우선 사용

        Returns:
            {
                scene_id: {
                    "matched_image": Path or None,
                    "source": str,
                    "match_type": "exact" | "sequential" | "none",
                    "candidates": List[Path]  # 여러 이미지가 있을 경우
                }
            }
        """
        all_images = self.find_all_images()
        result = {}

        # 씬 번호별 이미지 그룹화
        images_by_scene = {}
        for img in all_images:
            scene_num = img["scene_number"]
            if scene_num is not None:
                if scene_num not in images_by_scene:
                    images_by_scene[scene_num] = []
                images_by_scene[scene_num].append(img)

        # 씬별 정렬 (composited 우선, 최신 우선)
        for scene_num in images_by_scene:
            images_by_scene[scene_num].sort(
                key=lambda x: (
                    0 if x["source"] == "composited" else (1 if x["source"] == "scenes" else 2),
                    -x["created"].timestamp()  # 최신 우선
                )
            )

        # 각 씬에 이미지 매칭
        for scene in scenes:
            scene_id = scene.get("scene_id", 0)
            if isinstance(scene_id, str):
                try:
                    scene_id = int(scene_id)
                except ValueError:
                    scene_id = 0

            match_info = {
                "matched_image": None,
                "source": None,
                "match_type": "none",
                "candidates": []
            }

            if scene_id in images_by_scene:
                candidates = images_by_scene[scene_id]
                match_info["candidates"] = [img["path"] for img in candidates]

                if candidates:
                    best = candidates[0]
                    match_info["matched_image"] = best["path"]
                    match_info["source"] = best["source"]
                    match_info["match_type"] = "exact"

            result[scene_id] = match_info

        # 순차 매칭 (씬 번호가 없는 이미지 처리)
        unmatched_images = [
            img for img in all_images
            if img["scene_number"] is None
        ]

        # 이미지가 없는 씬에 순차 배정
        if unmatched_images:
            unmatched_images.sort(key=lambda x: x["filename"])

            unmatched_scenes = [
                scene_id for scene_id, info in result.items()
                if info["match_type"] == "none"
            ]
            unmatched_scenes.sort()

            for i, scene_id in enumerate(unmatched_scenes):
                if i < len(unmatched_images):
                    img = unmatched_images[i]
                    result[scene_id] = {
                        "matched_image": img["path"],
                        "source": img["source"],
                        "match_type": "sequential",
                        "candidates": [img["path"]]
                    }

        return result

    def copy_matched_to_storyboard(
        self,
        match_results: Dict[int, Dict],
        target_dir: Optional[Path] = None
    ) -> Dict:
        """
        매칭된 이미지를 스토리보드 디렉토리로 복사

        Args:
            match_results: match_images_to_scenes 결과
            target_dir: 대상 디렉토리 (기본: images/scenes)

        Returns:
            {
                "copied": int,
                "skipped": int,
                "errors": List[str]
            }
        """
        if target_dir is None:
            target_dir = self.scenes_images_dir

        target_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        skipped = 0
        errors = []

        for scene_id, info in match_results.items():
            if info["matched_image"] is None:
                skipped += 1
                continue

            source = Path(info["matched_image"])
            if not source.exists():
                errors.append(f"씬 {scene_id}: 소스 파일 없음 ({source.name})")
                continue

            # 대상 파일명: scene_001.png
            target = target_dir / f"scene_{scene_id:03d}{source.suffix}"

            try:
                # 이미 같은 파일이면 스킵
                if target.exists() and target.stat().st_size == source.stat().st_size:
                    skipped += 1
                    continue

                shutil.copy2(source, target)
                copied += 1
            except Exception as e:
                errors.append(f"씬 {scene_id}: 복사 실패 ({str(e)})")

        return {
            "copied": copied,
            "skipped": skipped,
            "errors": errors
        }

    def get_matching_summary(self, scenes: List[Dict]) -> Dict:
        """
        매칭 상태 요약

        Args:
            scenes: 씬 목록

        Returns:
            {
                "total_scenes": int,
                "matched_exact": int,
                "matched_sequential": int,
                "unmatched": int,
                "total_images": int,
                "match_rate": float
            }
        """
        match_results = self.match_images_to_scenes(scenes)
        all_images = self.find_all_images()

        exact = sum(1 for m in match_results.values() if m["match_type"] == "exact")
        sequential = sum(1 for m in match_results.values() if m["match_type"] == "sequential")
        unmatched = sum(1 for m in match_results.values() if m["match_type"] == "none")

        total = len(scenes)
        matched = exact + sequential

        return {
            "total_scenes": total,
            "matched_exact": exact,
            "matched_sequential": sequential,
            "unmatched": unmatched,
            "total_images": len(all_images),
            "match_rate": (matched / total * 100) if total > 0 else 0
        }


def auto_sync_images_to_storyboard(
    project_path: Path,
    scenes: List[Dict],
    copy_to_scenes: bool = True
) -> Dict:
    """
    이미지 자동 동기화 편의 함수

    Args:
        project_path: 프로젝트 경로
        scenes: 씬 목록
        copy_to_scenes: 이미지를 scenes 폴더로 복사

    Returns:
        {
            "match_results": Dict,
            "copy_results": Dict or None,
            "summary": Dict
        }
    """
    matcher = ImageSceneMatcher(project_path)

    # 매칭 수행
    match_results = matcher.match_images_to_scenes(scenes)

    # 요약
    summary = matcher.get_matching_summary(scenes)

    result = {
        "match_results": match_results,
        "copy_results": None,
        "summary": summary
    }

    # 복사 수행
    if copy_to_scenes:
        copy_results = matcher.copy_matched_to_storyboard(match_results)
        result["copy_results"] = copy_results

    return result
