# -*- coding: utf-8 -*-
"""
utils/download_manager.py
씬별 이미지/동영상 일괄 다운로드 관리
"""

import os
import io
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import base64


class SceneDownloadManager:
    """씬별 자료 다운로드 관리자"""

    def __init__(self, project_path: str = None, video_path: str = None):
        """
        Args:
            project_path: 프로젝트 루트 경로
            video_path: 영상 폴더 경로
        """
        self.project_path = Path(project_path) if project_path else None
        self.video_path = Path(video_path) if video_path else None

    # ============================================================
    # 이미지 수집
    # ============================================================

    def collect_scene_images(
        self,
        scenes: List[Dict],
        image_type: str = "all"
    ) -> List[Dict]:
        """
        씬에서 이미지 경로 수집

        Args:
            scenes: 씬 데이터 리스트
            image_type: "all", "ai", "infographic", "composite", "background", "selected"

        Returns:
            [
                {"scene_num": 1, "image_path": "/path/to/image.png", "type": "ai"},
                ...
            ]
        """

        collected = []

        for idx, scene in enumerate(scenes):
            scene_num = scene.get("scene_id") or scene.get("scene_num") or scene.get("index") or (idx + 1)
            if isinstance(scene_num, str) and scene_num.isdigit():
                scene_num = int(scene_num)

            # AI 이미지 / 배경
            if image_type in ["all", "ai", "background"]:
                ai_image = (
                    scene.get("ai_image_path") or
                    scene.get("generated_image") or
                    scene.get("image_path") or
                    scene.get("background_path") or
                    scene.get("image")
                )
                if ai_image and os.path.exists(str(ai_image)):
                    collected.append({
                        "scene_num": scene_num,
                        "image_path": str(ai_image),
                        "type": "ai"
                    })

            # 인포그래픽
            if image_type in ["all", "infographic"]:
                infographic = (
                    scene.get("infographic_path") or
                    scene.get("infographic_image") or
                    scene.get("infographic")
                )
                if infographic and os.path.exists(str(infographic)):
                    collected.append({
                        "scene_num": scene_num,
                        "image_path": str(infographic),
                        "type": "infographic"
                    })

            # 캐릭터 합성
            if image_type in ["all", "composite"]:
                composite = (
                    scene.get("composite_image") or
                    scene.get("composited_path") or
                    scene.get("composited_image")
                )
                if composite and os.path.exists(str(composite)):
                    collected.append({
                        "scene_num": scene_num,
                        "image_path": str(composite),
                        "type": "composite"
                    })

            # 선택된 이미지 (스토리보드용)
            if image_type in ["all", "selected"]:
                selected = scene.get("selected_image") or scene.get("final_image")
                if selected and os.path.exists(str(selected)):
                    collected.append({
                        "scene_num": scene_num,
                        "image_path": str(selected),
                        "type": "selected"
                    })

        # 씬 번호순 정렬
        collected.sort(key=lambda x: x["scene_num"])

        return collected

    def collect_scene_videos(self, scenes: List[Dict]) -> List[Dict]:
        """씬에서 동영상 경로 수집"""

        collected = []

        for idx, scene in enumerate(scenes):
            scene_num = scene.get("scene_id") or scene.get("scene_num") or scene.get("index") or (idx + 1)
            if isinstance(scene_num, str) and scene_num.isdigit():
                scene_num = int(scene_num)

            video_path = (
                scene.get("video_path") or
                scene.get("video") or
                scene.get("recorded_video")
            )

            if video_path and os.path.exists(str(video_path)):
                collected.append({
                    "scene_num": scene_num,
                    "video_path": str(video_path),
                    "type": "video"
                })

        collected.sort(key=lambda x: x["scene_num"])
        return collected

    def collect_images_from_paths(self, image_paths: List[str]) -> List[Dict]:
        """
        경로 리스트에서 이미지 정보 수집

        Args:
            image_paths: 이미지 경로 리스트

        Returns:
            [{"scene_num": N, "image_path": "path", "type": "gallery"}, ...]
        """
        collected = []

        for idx, path in enumerate(image_paths):
            if not os.path.exists(path):
                continue

            # 파일명에서 씬 번호 추출 시도
            filename = Path(path).stem
            scene_num = idx + 1

            # 패턴: scene_001, 001_scene, composited_001 등
            import re
            match = re.search(r'_(\d{2,3})|^(\d{2,3})_', filename)
            if match:
                scene_num = int(match.group(1) or match.group(2))

            collected.append({
                "scene_num": scene_num,
                "image_path": path,
                "type": "gallery"
            })

        collected.sort(key=lambda x: x["scene_num"])
        return collected

    # ============================================================
    # 프로젝트 폴더에 저장
    # ============================================================

    def save_to_project_folder(
        self,
        images: List[Dict],
        subfolder: str = "scene_images",
        naming_pattern: str = "{num}"
    ) -> Tuple[bool, str, List[str]]:
        """
        프로젝트 폴더에 이미지 저장

        Args:
            images: collect_scene_images() 결과
            subfolder: 저장할 하위 폴더명
            naming_pattern: 파일명 패턴 (예: "scene_{num:03d}")

        Returns:
            (성공여부, 저장경로, 저장된파일목록)
        """

        if not self.video_path:
            return False, "영상 경로가 설정되지 않았습니다.", []

        # 저장 폴더 생성
        save_dir = self.video_path / subfolder
        save_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []

        for item in images:
            scene_num = item["scene_num"]
            src_path = Path(item["image_path"])

            if not src_path.exists():
                continue

            # 파일명 생성
            ext = src_path.suffix
            filename = naming_pattern.format(num=scene_num) + ext
            dst_path = save_dir / filename

            # 복사
            try:
                shutil.copy2(src_path, dst_path)
                saved_files.append(str(dst_path))
            except Exception as e:
                print(f"[Download] 복사 실패: {src_path} → {dst_path}: {e}")

        return True, str(save_dir), saved_files

    def save_videos_to_project_folder(
        self,
        videos: List[Dict],
        subfolder: str = "scene_videos",
        naming_pattern: str = "{num}"
    ) -> Tuple[bool, str, List[str]]:
        """프로젝트 폴더에 동영상 저장"""

        if not self.video_path:
            return False, "영상 경로가 설정되지 않았습니다.", []

        save_dir = self.video_path / subfolder
        save_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []

        for item in videos:
            scene_num = item["scene_num"]
            src_path = Path(item["video_path"])

            if not src_path.exists():
                continue

            ext = src_path.suffix
            filename = naming_pattern.format(num=scene_num) + ext
            dst_path = save_dir / filename

            try:
                shutil.copy2(src_path, dst_path)
                saved_files.append(str(dst_path))
            except Exception as e:
                print(f"[Download] 복사 실패: {src_path} → {dst_path}: {e}")

        return True, str(save_dir), saved_files

    # ============================================================
    # ZIP 다운로드
    # ============================================================

    def create_zip_buffer(
        self,
        images: List[Dict] = None,
        videos: List[Dict] = None,
        naming_pattern: str = "{num}"
    ) -> io.BytesIO:
        """
        ZIP 파일 버퍼 생성 (Streamlit 다운로드용)

        Returns:
            BytesIO 객체 (st.download_button에서 사용)
        """

        zip_buffer = io.BytesIO()

        # ✅ 중복 파일명 추적
        added_files = set()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 이미지 추가
            if images:
                for item in images:
                    scene_num = item["scene_num"]
                    src_path = Path(item["image_path"])

                    if not src_path.exists():
                        continue

                    ext = src_path.suffix
                    img_type = item.get("type", "image")

                    # ZIP 내 경로
                    if img_type == "ai":
                        folder = "ai_images"
                    elif img_type == "infographic":
                        folder = "infographics"
                    elif img_type == "composite":
                        folder = "composites"
                    elif img_type == "background":
                        folder = "backgrounds"
                    else:
                        folder = "images"

                    filename = naming_pattern.format(num=scene_num) + ext
                    arcname = f"{folder}/{filename}"

                    # ✅ 중복 체크
                    if arcname in added_files:
                        continue
                    added_files.add(arcname)

                    zf.write(src_path, arcname)

            # 동영상 추가
            if videos:
                for item in videos:
                    scene_num = item["scene_num"]
                    src_path = Path(item["video_path"])

                    if not src_path.exists():
                        continue

                    ext = src_path.suffix
                    filename = naming_pattern.format(num=scene_num) + ext
                    arcname = f"videos/{filename}"

                    # ✅ 중복 체크
                    if arcname in added_files:
                        continue
                    added_files.add(arcname)

                    zf.write(src_path, arcname)

        zip_buffer.seek(0)
        return zip_buffer

    def get_zip_filename(self, prefix: str = "scene_assets") -> str:
        """ZIP 파일명 생성"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if self.video_path:
            video_name = self.video_path.name
            return f"{video_name}_{prefix}_{timestamp}.zip"
        else:
            return f"{prefix}_{timestamp}.zip"

    # ============================================================
    # 개별 이미지 다운로드
    # ============================================================

    @staticmethod
    def get_image_download_data(image_path: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        개별 이미지 다운로드 데이터 반환

        Returns:
            (바이트데이터, 파일명)
        """

        path = Path(image_path)

        if not path.exists():
            return None, None

        with open(path, 'rb') as f:
            data = f.read()

        return data, path.name

    @staticmethod
    def get_image_base64(image_path: str) -> Optional[str]:
        """이미지를 base64로 인코딩"""

        path = Path(image_path)

        if not path.exists():
            return None

        with open(path, 'rb') as f:
            data = f.read()

        return base64.b64encode(data).decode('utf-8')


# ============================================================
# 헬퍼 함수
# ============================================================

def get_download_manager(project_path: str = None, video_path: str = None) -> SceneDownloadManager:
    """SceneDownloadManager 인스턴스 생성"""
    return SceneDownloadManager(project_path, video_path)


def create_images_zip(image_paths: List[str], zip_filename: str = None) -> Tuple[io.BytesIO, str]:
    """
    이미지 경로 리스트로 ZIP 생성 (간편 함수)

    Args:
        image_paths: 이미지 경로 리스트
        zip_filename: ZIP 파일명 (None이면 자동 생성)

    Returns:
        (ZIP BytesIO, 파일명)
    """
    manager = SceneDownloadManager()
    images = manager.collect_images_from_paths(image_paths)
    zip_buffer = manager.create_zip_buffer(images=images)

    if not zip_filename:
        zip_filename = manager.get_zip_filename("images")

    return zip_buffer, zip_filename
