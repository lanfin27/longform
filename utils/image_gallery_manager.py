# -*- coding: utf-8 -*-
"""
utils/image_gallery_manager.py
이미지 갤러리 관리 유틸리티 (중복 분석, 최신 이미지 추출 등)
"""

import os
import re
import io
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class ImageInfo:
    """이미지 정보"""
    path: str
    filename: str
    scene_id: str
    image_type: str  # composited, background, scene
    created: float  # timestamp
    size_bytes: int

    @property
    def scene_num(self) -> int:
        """씬 번호 (정수)"""
        try:
            return int(self.scene_id) if self.scene_id.isdigit() else 0
        except:
            return 0

    @property
    def created_datetime(self) -> datetime:
        """생성 시간"""
        return datetime.fromtimestamp(self.created)

    @property
    def size_kb(self) -> float:
        return self.size_bytes / 1024

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


class ImageGalleryManager:
    """이미지 갤러리 관리자"""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.images_dir = self.project_path / "images"

        # ⭐ v2.0: 글로벌 이미지 폴더 (ImageFX 등)
        root_dir = Path(__file__).parent.parent
        self.global_images_dir = root_dir / "data" / "images"

    # ============================================================
    # 이미지 스캔
    # ============================================================

    def scan_all_images(self, include_global: bool = True) -> List[ImageInfo]:
        """
        모든 이미지 스캔

        Args:
            include_global: 글로벌 폴더(data/images/imagefx 등) 포함 여부

        Returns:
            이미지 정보 목록
        """
        images = []

        # 프로젝트 폴더 이미지
        comp_dir = self.images_dir / "composited"
        if comp_dir.exists():
            images.extend(self._scan_folder(comp_dir, "composited"))

        scene_dir = self.images_dir / "scenes"
        if scene_dir.exists():
            images.extend(self._scan_folder(scene_dir, "scene"))

        bg_dir = self.images_dir / "backgrounds"
        if bg_dir.exists():
            images.extend(self._scan_folder(bg_dir, "background"))

        # ⭐ v2.0: 글로벌 폴더 이미지 (ImageFX 등)
        if include_global and self.global_images_dir.exists():
            imagefx_dir = self.global_images_dir / "imagefx"
            if imagefx_dir.exists():
                images.extend(self._scan_folder(imagefx_dir, "imagefx"))

            generated_dir = self.global_images_dir / "generated"
            if generated_dir.exists():
                images.extend(self._scan_folder(generated_dir, "generated"))

            global_bg_dir = self.global_images_dir / "backgrounds"
            if global_bg_dir.exists():
                images.extend(self._scan_folder(global_bg_dir, "global_background"))

        # 시간순 정렬
        images.sort(key=lambda x: x.created, reverse=True)

        return images

    def _scan_folder(self, folder: Path, image_type: str) -> List[ImageInfo]:
        """폴더 내 이미지 스캔"""

        images = []

        for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
            for f in folder.glob(ext):
                try:
                    stat = f.stat()
                    images.append(ImageInfo(
                        path=str(f),
                        filename=f.name,
                        scene_id=self._extract_scene_id(f.name),
                        image_type=image_type,
                        created=stat.st_mtime,
                        size_bytes=stat.st_size
                    ))
                except Exception as e:
                    print(f"[ImageGalleryManager] 스캔 실패: {f} - {e}")

        return images

    def _extract_scene_id(self, filename: str) -> str:
        """파일명에서 씬 ID 추출"""

        # scene_001, scene-001, scene001
        match = re.search(r'scene[_\-]?(\d+)', filename, re.IGNORECASE)
        if match:
            return match.group(1)

        # composited_001, background_001
        match = re.search(r'(?:composited|background)[_\-]?(\d+)', filename, re.IGNORECASE)
        if match:
            return match.group(1)

        # 001_xxx.png
        match = re.search(r'^(\d+)[_\-]', filename)
        if match:
            return match.group(1)

        return "0"

    # ============================================================
    # 씬별 그룹화
    # ============================================================

    def group_by_scene(self, images: List[ImageInfo] = None) -> Dict[str, List[ImageInfo]]:
        """씬별로 이미지 그룹화"""

        if images is None:
            images = self.scan_all_images()

        groups = defaultdict(list)

        for img in images:
            groups[img.scene_id].append(img)

        # 각 그룹 내에서 시간순 정렬 (최신이 마지막)
        for scene_id in groups:
            groups[scene_id].sort(key=lambda x: x.created)

        return dict(groups)

    # ============================================================
    # 중복 분석
    # ============================================================

    def analyze_duplicates(self, images: List[ImageInfo] = None) -> Dict:
        """중복 분석"""

        if images is None:
            images = self.scan_all_images()

        groups = self.group_by_scene(images)

        total_images = len(images)
        total_scenes = len([g for g in groups.keys() if g != "0"])  # 씬 번호 없는 것 제외

        # 중복 통계
        duplicates_count = 0
        duplicates_size = 0

        scene_stats = []

        for scene_id, scene_images in sorted(groups.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999):
            count = len(scene_images)

            if count > 1 and scene_id != "0":
                # 최신 제외 나머지는 중복
                old_images = scene_images[:-1]  # 마지막(최신) 제외
                dup_count = len(old_images)
                dup_size = sum(img.size_bytes for img in old_images)

                duplicates_count += dup_count
                duplicates_size += dup_size

                scene_stats.append({
                    "scene_id": scene_id,
                    "total": count,
                    "keep": 1,
                    "delete": dup_count,
                    "delete_size_mb": dup_size / (1024 * 1024)
                })

        unique_count = total_scenes if total_scenes > 0 else total_images

        return {
            "total_images": total_images,
            "total_scenes": total_scenes,
            "unique_images": unique_count,
            "duplicates_count": duplicates_count,
            "duplicates_size_bytes": duplicates_size,
            "duplicates_size_mb": duplicates_size / (1024 * 1024),
            "savings_percent": (duplicates_count / total_images * 100) if total_images > 0 else 0,
            "scene_stats": scene_stats
        }

    # ============================================================
    # 최신 이미지 추출
    # ============================================================

    def get_latest_per_scene(self, images: List[ImageInfo] = None) -> Dict[str, ImageInfo]:
        """씬별 최신 이미지만 추출"""

        groups = self.group_by_scene(images)
        latest = {}

        for scene_id, scene_images in groups.items():
            if scene_images and scene_id != "0":
                # 타임스탬프 기준 가장 최신 (마지막)
                latest[scene_id] = scene_images[-1]

        return latest

    def get_latest_images_list(self, images: List[ImageInfo] = None) -> List[ImageInfo]:
        """최신 이미지 리스트 반환 (씬 번호순)"""

        latest = self.get_latest_per_scene(images)
        return [latest[scene_id] for scene_id in sorted(latest.keys(), key=lambda x: int(x) if x.isdigit() else 999)]

    # ============================================================
    # ZIP 다운로드
    # ============================================================

    def create_zip_buffer(
        self,
        images: List[ImageInfo],
        naming_pattern: str = "{num}"
    ) -> io.BytesIO:
        """ZIP 파일 버퍼 생성"""

        zip_buffer = io.BytesIO()

        # ✅ 중복 파일명 추적
        added_files = set()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for img in images:
                src_path = Path(img.path)

                if not src_path.exists():
                    continue

                ext = src_path.suffix

                # 파일명 생성
                filename = naming_pattern.format(num=img.scene_num) + ext

                # ✅ 중복 체크
                if filename in added_files:
                    continue
                added_files.add(filename)

                zf.write(src_path, filename)

        zip_buffer.seek(0)
        return zip_buffer

    def create_zip_with_timestamp(
        self,
        images: List[ImageInfo],
        naming_pattern: str = "{num}_{ts}"
    ) -> io.BytesIO:
        """타임스탬프 포함 ZIP 생성"""

        zip_buffer = io.BytesIO()

        # ✅ 중복 파일명 추적
        added_files = set()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for img in images:
                src_path = Path(img.path)

                if not src_path.exists():
                    continue

                ext = src_path.suffix
                ts = img.created_datetime.strftime("%H%M%S")

                # 파일명 생성
                filename = naming_pattern.format(num=img.scene_num, ts=ts) + ext

                # ✅ 중복 체크
                if filename in added_files:
                    continue
                added_files.add(filename)

                zf.write(src_path, filename)

        zip_buffer.seek(0)
        return zip_buffer

    def get_zip_filename(self, prefix: str = "images") -> str:
        """ZIP 파일명 생성"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}.zip"

    # ============================================================
    # 프로젝트 폴더 저장
    # ============================================================

    def save_latest_to_folder(
        self,
        images: List[ImageInfo] = None,
        subfolder: str = "scene_images"
    ) -> Tuple[bool, str, int]:
        """최신 이미지를 프로젝트 폴더에 저장"""

        if images is None:
            images = self.get_latest_images_list()

        save_dir = self.project_path / subfolder
        save_dir.mkdir(parents=True, exist_ok=True)

        saved_count = 0

        for img in images:
            src_path = Path(img.path)

            if not src_path.exists():
                continue

            ext = src_path.suffix
            filename = f"{img.scene_num}{ext}"
            dst_path = save_dir / filename

            try:
                shutil.copy2(src_path, dst_path)
                saved_count += 1
            except Exception as e:
                print(f"[ImageGalleryManager] 복사 실패: {src_path} - {e}")

        return True, str(save_dir), saved_count

    # ============================================================
    # 중복 삭제
    # ============================================================

    def delete_old_images(self, images: List[ImageInfo] = None, dry_run: bool = True) -> Dict:
        """
        최신 제외 모든 이미지 삭제

        Args:
            images: 이미지 목록 (None이면 스캔)
            dry_run: True면 실제 삭제 안하고 시뮬레이션만

        Returns:
            삭제 결과 통계
        """

        groups = self.group_by_scene(images)

        deleted_files = []
        deleted_size = 0
        errors = []

        for scene_id, scene_images in groups.items():
            if len(scene_images) <= 1 or scene_id == "0":
                continue  # 1개 이하이거나 씬 번호 없으면 삭제할 것 없음

            # 최신 제외 나머지 삭제
            old_images = scene_images[:-1]

            for img in old_images:
                try:
                    if not dry_run:
                        os.remove(img.path)

                    deleted_files.append({
                        "path": img.path,
                        "filename": img.filename,
                        "scene_id": img.scene_id,
                        "created": img.created_datetime.isoformat(),
                        "size_kb": img.size_kb
                    })
                    deleted_size += img.size_bytes

                except Exception as e:
                    errors.append({
                        "path": img.path,
                        "error": str(e)
                    })

        return {
            "dry_run": dry_run,
            "deleted_count": len(deleted_files),
            "deleted_size_mb": deleted_size / (1024 * 1024),
            "deleted_files": deleted_files,
            "errors": errors
        }

    def move_old_to_archive(self, images: List[ImageInfo] = None, archive_folder: str = None) -> Dict:
        """
        최신 제외 이미지를 아카이브 폴더로 이동
        """

        if archive_folder is None:
            archive_folder = self.images_dir / "archive"

        archive_path = Path(archive_folder)
        archive_path.mkdir(parents=True, exist_ok=True)

        groups = self.group_by_scene(images)

        moved_files = []
        moved_size = 0
        errors = []

        for scene_id, scene_images in groups.items():
            if len(scene_images) <= 1 or scene_id == "0":
                continue

            old_images = scene_images[:-1]

            for img in old_images:
                try:
                    dst_path = archive_path / img.filename
                    shutil.move(img.path, dst_path)

                    moved_files.append({
                        "from": img.path,
                        "to": str(dst_path),
                        "scene_id": img.scene_id
                    })
                    moved_size += img.size_bytes

                except Exception as e:
                    errors.append({
                        "path": img.path,
                        "error": str(e)
                    })

        return {
            "moved_count": len(moved_files),
            "moved_size_mb": moved_size / (1024 * 1024),
            "archive_folder": str(archive_path),
            "moved_files": moved_files,
            "errors": errors
        }


# ============================================================
# 헬퍼 함수
# ============================================================

def get_gallery_manager(project_path: str = None):
    """ImageGalleryManager 인스턴스 생성"""

    if project_path is None:
        import streamlit as st
        project_path = st.session_state.get("current_project_path", "")

    return ImageGalleryManager(project_path)
