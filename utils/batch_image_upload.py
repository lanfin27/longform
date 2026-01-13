# -*- coding: utf-8 -*-
"""
배치 이미지 업로드 유틸리티 (v1.0)

파일명에서 씬 번호를 인식하여 배경 이미지를 일괄 대체하는 기능

지원 파일명 형식:
- 1.jpg, 2.png, 100.jpeg (순수 숫자)
- 001.jpg, 005.png (앞에 0 패딩)
- scene_1.jpg, scene_10.png (scene_ 접두사)
- 씬1.jpg, 씬_5.png (한글 접두사)
"""

import re
import shutil
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class BatchUploadItem:
    """배치 업로드 항목"""
    filename: str
    file_data: bytes
    scene_number: Optional[int]
    status: str  # "success", "out_of_range", "invalid_name", "invalid_format", "duplicate"
    message: str
    current_image_path: Optional[str] = None


# ============================================================
# 파일명 파싱 함수
# ============================================================

def extract_scene_number_from_filename(filename: str) -> Optional[int]:
    """파일명에서 씬 번호 추출

    지원 형식:
    - 1.jpg, 2.png, 100.jpeg (숫자만)
    - 001.jpg, 005.png (앞에 0 패딩)
    - scene_1.jpg, scene_5.png (scene_ 접두사)
    - 씬1.jpg, 씬_5.png (한글 접두사)
    - bg_scene_001.jpg (기존 형식)

    Args:
        filename: 파일명 (확장자 포함)

    Returns:
        씬 번호 (int) 또는 None (인식 실패)
    """

    # 확장자 제거
    stem = Path(filename).stem  # "1.jpg" -> "1"

    # 패턴 1: 순수 숫자 (1, 01, 001, 100)
    if stem.isdigit():
        return int(stem)

    # 패턴 2: scene_숫자, scene숫자, scene-숫자
    match = re.match(r'^scene[_\-]?(\d+)$', stem, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # 패턴 3: 씬_숫자, 씬숫자
    match = re.match(r'^씬[_\-]?(\d+)$', stem)
    if match:
        return int(match.group(1))

    # 패턴 4: bg_scene_숫자 (기존 형식)
    match = re.match(r'^bg_scene_(\d+)', stem)
    if match:
        return int(match.group(1))

    # 패턴 5: seg_숫자
    match = re.match(r'^seg[_\-]?(\d+)', stem, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # 패턴 6: 파일명 시작 부분의 숫자 (5_something.jpg -> 5)
    match = re.match(r'^(\d+)[_\-]', stem)
    if match:
        return int(match.group(1))

    return None


def validate_image_file(filename: str) -> bool:
    """이미지 파일 확장자 검증

    Args:
        filename: 파일명

    Returns:
        유효한 이미지 파일 여부
    """
    valid_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    ext = Path(filename).suffix.lower()
    return ext in valid_extensions


# ============================================================
# 배치 분석 함수
# ============================================================

def analyze_batch_upload(
    uploaded_files: list,
    total_scenes: int,
    existing_images: Dict[int, str] = None
) -> List[BatchUploadItem]:
    """업로드된 파일들 분석

    Args:
        uploaded_files: Streamlit file_uploader에서 반환된 파일 목록
        total_scenes: 전체 씬 개수
        existing_images: 씬별 현재 이미지 경로 딕셔너리 {scene_id: image_path}

    Returns:
        분석 결과 리스트
    """

    if existing_images is None:
        existing_images = {}

    results = []
    seen_scene_numbers = set()  # 중복 검사용

    for file in uploaded_files:
        filename = file.name
        file_data = file.read()
        file.seek(0)  # 파일 포인터 리셋

        # 1. 확장자 검증
        if not validate_image_file(filename):
            results.append(BatchUploadItem(
                filename=filename,
                file_data=file_data,
                scene_number=None,
                status="invalid_format",
                message=f"지원하지 않는 파일 형식: {Path(filename).suffix}"
            ))
            continue

        # 2. 씬 번호 추출
        scene_num = extract_scene_number_from_filename(filename)

        if scene_num is None:
            results.append(BatchUploadItem(
                filename=filename,
                file_data=file_data,
                scene_number=None,
                status="invalid_name",
                message="파일명에서 씬 번호를 인식할 수 없습니다"
            ))
            continue

        # 3. 씬 범위 검증
        if scene_num < 1 or scene_num > total_scenes:
            results.append(BatchUploadItem(
                filename=filename,
                file_data=file_data,
                scene_number=scene_num,
                status="out_of_range",
                message=f"씬 범위 초과 (1~{total_scenes})"
            ))
            continue

        # 4. 중복 검사
        if scene_num in seen_scene_numbers:
            results.append(BatchUploadItem(
                filename=filename,
                file_data=file_data,
                scene_number=scene_num,
                status="duplicate",
                message=f"씬 {scene_num}에 대한 중복 파일"
            ))
            continue

        seen_scene_numbers.add(scene_num)

        # 5. 성공
        current_path = existing_images.get(scene_num, "")
        results.append(BatchUploadItem(
            filename=filename,
            file_data=file_data,
            scene_number=scene_num,
            status="success",
            message="대체" if current_path else "새로 추가",
            current_image_path=current_path
        ))

    # 씬 번호로 정렬
    results.sort(key=lambda x: (x.scene_number or 9999, x.filename))

    return results


def get_batch_upload_stats(results: List[BatchUploadItem]) -> Dict[str, Any]:
    """배치 업로드 통계

    Args:
        results: 분석 결과 리스트

    Returns:
        통계 딕셔너리
    """

    success = [r for r in results if r.status == "success"]
    out_of_range = [r for r in results if r.status == "out_of_range"]
    invalid_name = [r for r in results if r.status == "invalid_name"]
    invalid_format = [r for r in results if r.status == "invalid_format"]
    duplicate = [r for r in results if r.status == "duplicate"]

    return {
        "total": len(results),
        "success": len(success),
        "out_of_range": len(out_of_range),
        "invalid_name": len(invalid_name),
        "invalid_format": len(invalid_format),
        "duplicate": len(duplicate),
        "success_items": success,
        "failed_items": out_of_range + invalid_name + invalid_format + duplicate
    }


# ============================================================
# 이미지 적용 함수
# ============================================================

def apply_batch_images(
    results: List[BatchUploadItem],
    backgrounds_folder: Path,
    backup: bool = True,
    scene_image_manager = None
) -> Dict[str, Any]:
    """배치 이미지 적용

    Args:
        results: 분석 결과 (success 상태만 처리)
        backgrounds_folder: 배경 이미지 저장 폴더
        backup: 기존 이미지 백업 여부
        scene_image_manager: SceneImageManager 인스턴스 (옵션)

    Returns:
        적용 결과 통계
    """

    success_items = [r for r in results if r.status == "success"]

    applied = 0
    failed = 0
    backed_up = 0
    backup_folder = None

    # 배경 폴더 생성
    backgrounds_folder = Path(backgrounds_folder)
    backgrounds_folder.mkdir(parents=True, exist_ok=True)

    # 백업 폴더 생성
    if backup:
        backup_folder = backgrounds_folder / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    for item in success_items:
        try:
            scene_num = item.scene_number

            # 기존 이미지 백업
            if backup and item.current_image_path:
                current_path = Path(item.current_image_path)
                if current_path.exists():
                    if backup_folder:
                        backup_folder.mkdir(parents=True, exist_ok=True)
                        backup_path = backup_folder / current_path.name
                        shutil.copy2(current_path, backup_path)
                        backed_up += 1

            # 새 이미지 저장
            timestamp = int(datetime.now().timestamp() * 1000)
            ext = Path(item.filename).suffix.lower()
            new_filename = f"bg_scene_{scene_num:03d}_{timestamp}{ext}"
            new_path = backgrounds_folder / new_filename

            with open(new_path, 'wb') as f:
                f.write(item.file_data)

            # SceneImageManager로 씬 데이터 업데이트 (있는 경우)
            if scene_image_manager:
                scene_image_manager.update_background_image(scene_num, str(new_path))

            applied += 1

        except Exception as e:
            print(f"[BatchUpload] 에러: {item.filename} - {e}")
            failed += 1

    return {
        "applied": applied,
        "failed": failed,
        "backed_up": backed_up,
        "backup_folder": str(backup_folder) if backup_folder and backed_up > 0 else None
    }


# ============================================================
# 헬퍼 함수
# ============================================================

def get_existing_background_images(scenes: List[Dict]) -> Dict[int, str]:
    """씬 데이터에서 현재 배경 이미지 경로 추출

    Args:
        scenes: 씬 데이터 리스트

    Returns:
        {scene_id: background_image_path} 딕셔너리
    """

    result = {}

    for scene in scenes:
        scene_id = scene.get("scene_id") or scene.get("scene_num")
        if scene_id:
            bg_path = scene.get("background_image", "")
            if bg_path and Path(bg_path).exists():
                result[scene_id] = bg_path

    return result
