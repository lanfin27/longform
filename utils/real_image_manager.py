# -*- coding: utf-8 -*-
"""
실사 이미지 관리 유틸리티 (v1.0)

AI 생성 이미지를 실사 이미지로 대체하고 관리하는 기능
"""

import re
import shutil
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class RealImageItem:
    """실사 이미지 업로드 항목"""
    filename: str
    scene_number: Optional[int]
    status: str  # "success", "out_of_range", "invalid_name", "invalid_format", "duplicate"
    message: str
    file_index: int = -1
    current_ai_image: Optional[str] = None


# ============================================================
# 파일명 파싱 함수
# ============================================================

def extract_scene_number_from_image_filename(filename: str) -> Optional[int]:
    """파일명에서 씬 번호 추출

    지원 형식:
    - 1.png, 2.jpg, 100.webp (숫자만)
    - 001.png, 005.jpg (앞에 0 패딩)
    - scene_1.png, scene_5.jpg (scene_ 접두사)
    - 씬1.png, 씬_5.jpg (한글 접두사)
    - bg_scene_001.png (기존 형식)

    Args:
        filename: 파일명 (확장자 포함)

    Returns:
        씬 번호 (int) 또는 None (인식 실패)
    """

    # 확장자 제거
    stem = Path(filename).stem

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

    # 패턴 6: 파일명 시작 부분의 숫자 (5_something.png -> 5)
    match = re.match(r'^(\d+)[_\-]', stem)
    if match:
        return int(match.group(1))

    return None


def validate_image_file(filename: str) -> bool:
    """이미지 파일 확장자 검증"""
    valid_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
    ext = Path(filename).suffix.lower()
    return ext in valid_extensions


# ============================================================
# 분석 함수
# ============================================================

def quick_analyze_real_images(
    uploaded_files: list,
    total_scenes: int,
    existing_images: Dict[int, str] = None
) -> List[RealImageItem]:
    """업로드된 실사 이미지 파일들 빠른 분석

    Args:
        uploaded_files: Streamlit file_uploader에서 반환된 파일 목록
        total_scenes: 전체 씬 개수
        existing_images: 씬별 현재 AI 이미지 경로 딕셔너리 {scene_id: image_path}

    Returns:
        분석 결과 리스트
    """

    if existing_images is None:
        existing_images = {}

    results = []
    seen_scene_numbers = set()

    for idx, file in enumerate(uploaded_files):
        filename = file.name

        # 1. 확장자 검증
        if not validate_image_file(filename):
            results.append(RealImageItem(
                filename=filename,
                scene_number=None,
                status="invalid_format",
                message=f"지원하지 않는 파일 형식: {Path(filename).suffix}",
                file_index=idx
            ))
            continue

        # 2. 씬 번호 추출
        scene_num = extract_scene_number_from_image_filename(filename)

        if scene_num is None:
            results.append(RealImageItem(
                filename=filename,
                scene_number=None,
                status="invalid_name",
                message="파일명에서 씬 번호를 인식할 수 없습니다",
                file_index=idx
            ))
            continue

        # 3. 씬 범위 검증
        if scene_num < 1 or scene_num > total_scenes:
            results.append(RealImageItem(
                filename=filename,
                scene_number=scene_num,
                status="out_of_range",
                message=f"씬 범위 초과 (1~{total_scenes})",
                file_index=idx
            ))
            continue

        # 4. 중복 검사
        if scene_num in seen_scene_numbers:
            results.append(RealImageItem(
                filename=filename,
                scene_number=scene_num,
                status="duplicate",
                message=f"씬 {scene_num}에 대한 중복 파일",
                file_index=idx
            ))
            continue

        seen_scene_numbers.add(scene_num)

        # 5. 성공
        current_ai = existing_images.get(scene_num, "")
        results.append(RealImageItem(
            filename=filename,
            scene_number=scene_num,
            status="success",
            message="대체" if current_ai else "새로 추가",
            file_index=idx,
            current_ai_image=current_ai
        ))

    # 씬 번호로 정렬
    results.sort(key=lambda x: (x.scene_number or 9999, x.filename))

    return results


def get_real_image_stats(results: List[RealImageItem]) -> Dict[str, Any]:
    """실사 이미지 업로드 통계"""

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

def apply_real_images(
    uploaded_files: list,
    results: List[RealImageItem],
    images_folder: Path,
    backup_ai: bool = True,
    progress_callback = None
) -> Dict[str, Any]:
    """실사 이미지 적용

    AI 이미지를 백업하고 실사 이미지로 대체합니다.

    Args:
        uploaded_files: Streamlit file_uploader에서 반환된 파일 목록
        results: quick_analyze_real_images 결과 (success 상태만 처리)
        images_folder: 이미지 저장 폴더 (backgrounds 폴더)
        backup_ai: 기존 AI 이미지 백업 여부
        progress_callback: 진행률 콜백 함수

    Returns:
        적용 결과 통계
    """

    success_items = [r for r in results if r.status == "success"]

    applied = 0
    failed = 0
    backed_up = 0
    backup_folder = None
    total = len(success_items)

    # 이미지 폴더 확인
    images_folder = Path(images_folder)
    images_folder.mkdir(parents=True, exist_ok=True)

    # 백업 폴더 생성
    if backup_ai:
        backup_folder = images_folder / "backup_ai" / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 실사 이미지 저장 폴더
    real_folder = images_folder / "real"
    real_folder.mkdir(parents=True, exist_ok=True)

    for idx, item in enumerate(success_items):
        try:
            scene_num = item.scene_number
            file_index = item.file_index

            # 진행률 콜백
            if progress_callback:
                progress_callback(idx + 1, total, item.filename)

            # 원본 파일 찾기
            if file_index < 0 or file_index >= len(uploaded_files):
                print(f"[RealImageManager] 잘못된 파일 인덱스: {file_index}", flush=True)
                failed += 1
                continue

            uploaded_file = uploaded_files[file_index]

            # 기존 AI 이미지 백업
            if backup_ai and item.current_ai_image:
                current_path = Path(item.current_ai_image)
                if current_path.exists():
                    if backup_folder:
                        backup_folder.mkdir(parents=True, exist_ok=True)
                        backup_path = backup_folder / current_path.name
                        shutil.copy2(current_path, backup_path)
                        backed_up += 1

            # 새 실사 이미지 저장
            ext = Path(item.filename).suffix.lower()
            if ext not in ['.png', '.jpg', '.jpeg', '.webp']:
                ext = '.png'

            # 실사 이미지 파일명
            real_filename = f"real_scene_{scene_num:03d}{ext}"
            real_path = real_folder / real_filename

            # 파일 저장
            with open(real_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())

            print(f"[RealImageManager] ✅ 씬 {scene_num}: {real_filename}", flush=True)

            # 기존 AI 이미지 위치에 실사 이미지 복사 (활성화)
            if item.current_ai_image:
                current_path = Path(item.current_ai_image)
                # AI 이미지 이름 변경 (비활성화)
                if current_path.exists():
                    inactive_name = current_path.stem + "_ai_backup" + current_path.suffix
                    inactive_path = current_path.parent / inactive_name
                    if not inactive_path.exists():  # 이미 백업 안 된 경우만
                        current_path.rename(inactive_path)
                # 실사 이미지를 기존 위치에 복사
                shutil.copy2(real_path, current_path)

            applied += 1

        except Exception as e:
            print(f"[RealImageManager] ❌ 에러: {item.filename} - {e}", flush=True)
            failed += 1

    return {
        "applied": applied,
        "failed": failed,
        "backed_up": backed_up,
        "backup_folder": str(backup_folder) if backup_folder and backed_up > 0 else None,
        "real_folder": str(real_folder)
    }


def save_single_real_image(
    uploaded_file,
    images_folder: Path,
    scene_num: int,
    current_ai_image: Optional[str] = None,
    backup_ai: bool = True
) -> Dict[str, Any]:
    """단일 실사 이미지 저장

    Args:
        uploaded_file: Streamlit file_uploader에서 반환된 단일 파일
        images_folder: 이미지 저장 폴더 (backgrounds 폴더)
        scene_num: 대상 씬 번호
        current_ai_image: 현재 AI 이미지 경로
        backup_ai: AI 이미지 백업 여부

    Returns:
        저장 결과
    """

    result = {
        'success': False,
        'scene_num': scene_num,
        'real_image_path': None,
        'ai_backup_path': None,
        'error': None
    }

    try:
        images_folder = Path(images_folder)
        images_folder.mkdir(parents=True, exist_ok=True)

        # 실사 이미지 폴더
        real_folder = images_folder / "real"
        real_folder.mkdir(parents=True, exist_ok=True)

        # 확장자
        ext = Path(uploaded_file.name).suffix.lower()
        if ext not in ['.png', '.jpg', '.jpeg', '.webp']:
            ext = '.png'

        # 실사 이미지 저장
        real_filename = f"real_scene_{scene_num:03d}{ext}"
        real_path = real_folder / real_filename

        with open(real_path, 'wb') as f:
            f.write(uploaded_file.getbuffer())

        result['real_image_path'] = str(real_path)

        # AI 이미지 백업 및 대체
        if current_ai_image and backup_ai:
            current_path = Path(current_ai_image)
            if current_path.exists():
                # AI 이미지 이름 변경 (비활성화)
                inactive_name = current_path.stem + "_ai_backup" + current_path.suffix
                inactive_path = current_path.parent / inactive_name
                if not inactive_path.exists():
                    current_path.rename(inactive_path)
                    result['ai_backup_path'] = str(inactive_path)
                # 실사 이미지를 기존 위치에 복사
                shutil.copy2(real_path, current_path)

        result['success'] = True
        print(f"[RealImageManager] ✅ 단일 업로드 - 씬 {scene_num}: {real_filename}", flush=True)

    except Exception as e:
        result['error'] = str(e)
        print(f"[RealImageManager] ❌ 단일 업로드 실패 - 씬 {scene_num}: {e}", flush=True)

    return result


def restore_ai_image(
    images_folder: Path,
    scene_num: int,
    current_image: Optional[str] = None
) -> Dict[str, Any]:
    """AI 이미지 복원 (실사 이미지 비활성화)

    Args:
        images_folder: 이미지 폴더
        scene_num: 씬 번호
        current_image: 현재 활성 이미지 경로

    Returns:
        복원 결과
    """

    result = {
        'success': False,
        'scene_num': scene_num,
        'restored_path': None,
        'error': None
    }

    try:
        images_folder = Path(images_folder)

        # AI 백업 이미지 찾기
        patterns = [
            f"*scene_{scene_num:03d}*_ai_backup*",
            f"*seg_{scene_num:03d}*_ai_backup*",
            f"bg_scene_{scene_num:03d}*_ai_backup*"
        ]

        ai_backup_path = None
        for pattern in patterns:
            matches = list(images_folder.glob(pattern))
            if matches:
                ai_backup_path = matches[0]
                break

        if not ai_backup_path:
            result['error'] = "백업된 AI 이미지를 찾을 수 없습니다"
            return result

        # 현재 이미지 (실사)가 있으면 비활성화
        if current_image:
            current_path = Path(current_image)
            if current_path.exists():
                inactive_name = current_path.stem + "_real_inactive" + current_path.suffix
                inactive_path = current_path.parent / inactive_name
                current_path.rename(inactive_path)

        # AI 이미지 복원 (백업 이름에서 _ai_backup 제거)
        original_name = ai_backup_path.name.replace("_ai_backup", "")
        restored_path = ai_backup_path.parent / original_name
        ai_backup_path.rename(restored_path)

        result['success'] = True
        result['restored_path'] = str(restored_path)
        print(f"[RealImageManager] ✅ AI 복원 - 씬 {scene_num}", flush=True)

    except Exception as e:
        result['error'] = str(e)
        print(f"[RealImageManager] ❌ AI 복원 실패 - 씬 {scene_num}: {e}", flush=True)

    return result


# ============================================================
# 상태 조회 함수
# ============================================================

def get_scene_image_status(images_folder: Path, scene_num: int) -> Dict[str, Any]:
    """씬의 이미지 상태 조회

    Returns:
        {
            'has_ai': bool,
            'has_real': bool,
            'active_type': 'ai' | 'real' | None,
            'ai_path': str | None,
            'real_path': str | None
        }
    """

    images_folder = Path(images_folder)
    real_folder = images_folder / "real"

    result = {
        'has_ai': False,
        'has_real': False,
        'active_type': None,
        'ai_path': None,
        'real_path': None
    }

    # AI 이미지 찾기
    ai_patterns = [
        f"bg_scene_{scene_num:03d}*.png",
        f"bg_scene_{scene_num:03d}*.jpg",
        f"*scene_{scene_num:03d}*.png",
        f"*scene_{scene_num:03d}*.jpg",
        f"*seg_{scene_num:03d}*.png",
        f"*seg_{scene_num:03d}*.jpg"
    ]

    for pattern in ai_patterns:
        matches = [f for f in images_folder.glob(pattern) if "_ai_backup" not in f.name and "_real" not in f.name]
        if matches:
            result['has_ai'] = True
            result['ai_path'] = str(matches[0])
            break

    # AI 백업 찾기 (비활성화된 AI)
    ai_backup_patterns = [f"*scene_{scene_num:03d}*_ai_backup*"]
    for pattern in ai_backup_patterns:
        if list(images_folder.glob(pattern)):
            result['has_ai'] = True
            break

    # 실사 이미지 찾기
    if real_folder.exists():
        real_patterns = [f"real_scene_{scene_num:03d}*"]
        for pattern in real_patterns:
            matches = list(real_folder.glob(pattern))
            if matches:
                result['has_real'] = True
                result['real_path'] = str(matches[0])
                break

    # 활성 타입 판별
    if result['ai_path']:
        # 현재 활성 이미지가 실사인지 AI인지 확인
        active_path = Path(result['ai_path'])
        if "_real" in active_path.name or (result['has_real'] and not list(images_folder.glob(f"*scene_{scene_num:03d}*_ai_backup*"))):
            result['active_type'] = 'real'
        else:
            result['active_type'] = 'ai'
    elif result['has_real']:
        result['active_type'] = 'real'

    return result


def get_all_scene_image_statuses(images_folder: Path, total_scenes: int) -> Dict[int, Dict[str, Any]]:
    """모든 씬의 이미지 상태 조회"""

    statuses = {}
    for scene_num in range(1, total_scenes + 1):
        statuses[scene_num] = get_scene_image_status(images_folder, scene_num)
    return statuses


def get_existing_ai_images(images_folder: Path, scenes: list) -> Dict[int, str]:
    """씬별 현재 AI 이미지 경로 추출

    Args:
        images_folder: 이미지 폴더
        scenes: 씬 데이터 리스트

    Returns:
        {scene_id: image_path} 딕셔너리
    """

    result = {}
    images_folder = Path(images_folder)

    for scene in scenes:
        scene_id = scene.get("scene_id") or scene.get("scene_num") or scene.get("id")
        if not scene_id:
            continue

        # 이미지 경로 찾기
        patterns = [
            f"bg_scene_{scene_id:03d}*.png",
            f"bg_scene_{scene_id:03d}*.jpg",
            f"*scene_{scene_id:03d}*.png",
            f"*scene_{scene_id:03d}*.jpg",
            f"*seg_{scene_id:03d}*.png",
            f"*seg_{scene_id:03d}*.jpg"
        ]

        for pattern in patterns:
            matches = [f for f in images_folder.glob(pattern) if "_ai_backup" not in f.name and "_inactive" not in f.name]
            if matches:
                result[scene_id] = str(matches[0])
                break

    return result
