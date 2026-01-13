# -*- coding: utf-8 -*-
"""
배치 비디오 업로드 유틸리티 (v1.1)

파일명에서 씬 번호를 인식하여 비디오를 일괄 대체하는 기능

지원 파일명 형식:
- 1.mp4, 2.webm, 100.mov (순수 숫자)
- 001.mp4, 005.webm (앞에 0 패딩)
- scene_1.mp4, scene_10.webm (scene_ 접두사)
- 씬1.mp4, 씬_5.webm (한글 접두사)

v1.1 변경사항:
- quick_analyze_batch_video_upload() 추가: 파일 데이터 읽기 없이 빠르게 분석
- apply_batch_videos_direct() 추가: 파일을 직접 받아서 저장 (메모리 효율)
"""

import re
import shutil
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class BatchVideoItem:
    """배치 비디오 업로드 항목"""
    filename: str
    file_data: bytes  # 하위 호환성 유지 (None 가능)
    scene_number: Optional[int]
    status: str  # "success", "out_of_range", "invalid_name", "invalid_format", "duplicate"
    message: str
    current_video_path: Optional[str] = None
    file_index: int = -1  # 원본 파일 인덱스 (v1.1)


# ============================================================
# 파일명 파싱 함수
# ============================================================

def extract_scene_number_from_filename(filename: str) -> Optional[int]:
    """파일명에서 씬 번호 추출

    지원 형식:
    - 1.mp4, 2.webm, 100.mov (숫자만)
    - 001.mp4, 005.webm (앞에 0 패딩)
    - scene_1.mp4, scene_5.webm (scene_ 접두사)
    - 씬1.mp4, 씬_5.webm (한글 접두사)
    - bg_scene_001.mp4 (기존 형식)

    Args:
        filename: 파일명 (확장자 포함)

    Returns:
        씬 번호 (int) 또는 None (인식 실패)
    """

    # 확장자 제거
    stem = Path(filename).stem  # "1.mp4" -> "1"

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

    # 패턴 6: 파일명 시작 부분의 숫자 (5_something.mp4 -> 5)
    match = re.match(r'^(\d+)[_\-]', stem)
    if match:
        return int(match.group(1))

    return None


def validate_video_file(filename: str) -> bool:
    """비디오 파일 확장자 검증

    Args:
        filename: 파일명

    Returns:
        유효한 비디오 파일 여부
    """
    valid_extensions = {'.mp4', '.webm', '.mov', '.avi', '.mkv'}
    ext = Path(filename).suffix.lower()
    return ext in valid_extensions


# ============================================================
# 배치 분석 함수
# ============================================================

def analyze_batch_video_upload(
    uploaded_files: list,
    total_scenes: int,
    existing_videos: Dict[int, str] = None
) -> List[BatchVideoItem]:
    """업로드된 비디오 파일들 분석

    Args:
        uploaded_files: Streamlit file_uploader에서 반환된 파일 목록
        total_scenes: 전체 씬 개수
        existing_videos: 씬별 현재 비디오 경로 딕셔너리 {scene_id: video_path}

    Returns:
        분석 결과 리스트
    """

    if existing_videos is None:
        existing_videos = {}

    results = []
    seen_scene_numbers = set()  # 중복 검사용

    for file in uploaded_files:
        filename = file.name
        file_data = file.read()
        file.seek(0)  # 파일 포인터 리셋

        # 1. 확장자 검증
        if not validate_video_file(filename):
            results.append(BatchVideoItem(
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
            results.append(BatchVideoItem(
                filename=filename,
                file_data=file_data,
                scene_number=None,
                status="invalid_name",
                message="파일명에서 씬 번호를 인식할 수 없습니다"
            ))
            continue

        # 3. 씬 범위 검증
        if scene_num < 1 or scene_num > total_scenes:
            results.append(BatchVideoItem(
                filename=filename,
                file_data=file_data,
                scene_number=scene_num,
                status="out_of_range",
                message=f"씬 범위 초과 (1~{total_scenes})"
            ))
            continue

        # 4. 중복 검사
        if scene_num in seen_scene_numbers:
            results.append(BatchVideoItem(
                filename=filename,
                file_data=file_data,
                scene_number=scene_num,
                status="duplicate",
                message=f"씬 {scene_num}에 대한 중복 파일"
            ))
            continue

        seen_scene_numbers.add(scene_num)

        # 5. 성공
        current_path = existing_videos.get(scene_num, "")
        results.append(BatchVideoItem(
            filename=filename,
            file_data=file_data,
            scene_number=scene_num,
            status="success",
            message="대체" if current_path else "새로 추가",
            current_video_path=current_path
        ))

    # 씬 번호로 정렬
    results.sort(key=lambda x: (x.scene_number or 9999, x.filename))

    return results


def quick_analyze_batch_video_upload(
    uploaded_files: list,
    total_scenes: int,
    existing_videos: Dict[int, str] = None
) -> List[BatchVideoItem]:
    """업로드된 비디오 파일들 빠른 분석 (파일 데이터 읽지 않음) - v1.1

    파일명만 분석하여 씬 매칭 정보를 빠르게 반환합니다.
    대용량 비디오 파일 업로드 시 UI 블로킹 방지.

    Args:
        uploaded_files: Streamlit file_uploader에서 반환된 파일 목록
        total_scenes: 전체 씬 개수
        existing_videos: 씬별 현재 비디오 경로 딕셔너리 {scene_id: video_path}

    Returns:
        분석 결과 리스트 (file_data=None, file_index로 원본 참조)
    """

    if existing_videos is None:
        existing_videos = {}

    results = []
    seen_scene_numbers = set()  # 중복 검사용

    for idx, file in enumerate(uploaded_files):
        filename = file.name

        # 1. 확장자 검증 (파일 데이터 읽지 않음)
        if not validate_video_file(filename):
            results.append(BatchVideoItem(
                filename=filename,
                file_data=None,
                scene_number=None,
                status="invalid_format",
                message=f"지원하지 않는 파일 형식: {Path(filename).suffix}",
                file_index=idx
            ))
            continue

        # 2. 씬 번호 추출
        scene_num = extract_scene_number_from_filename(filename)

        if scene_num is None:
            results.append(BatchVideoItem(
                filename=filename,
                file_data=None,
                scene_number=None,
                status="invalid_name",
                message="파일명에서 씬 번호를 인식할 수 없습니다",
                file_index=idx
            ))
            continue

        # 3. 씬 범위 검증
        if scene_num < 1 or scene_num > total_scenes:
            results.append(BatchVideoItem(
                filename=filename,
                file_data=None,
                scene_number=scene_num,
                status="out_of_range",
                message=f"씬 범위 초과 (1~{total_scenes})",
                file_index=idx
            ))
            continue

        # 4. 중복 검사
        if scene_num in seen_scene_numbers:
            results.append(BatchVideoItem(
                filename=filename,
                file_data=None,
                scene_number=scene_num,
                status="duplicate",
                message=f"씬 {scene_num}에 대한 중복 파일",
                file_index=idx
            ))
            continue

        seen_scene_numbers.add(scene_num)

        # 5. 성공
        current_path = existing_videos.get(scene_num, "")
        results.append(BatchVideoItem(
            filename=filename,
            file_data=None,
            scene_number=scene_num,
            status="success",
            message="대체" if current_path else "새로 추가",
            current_video_path=current_path,
            file_index=idx
        ))

    # 씬 번호로 정렬
    results.sort(key=lambda x: (x.scene_number or 9999, x.filename))

    return results


def get_batch_video_stats(results: List[BatchVideoItem]) -> Dict[str, Any]:
    """배치 비디오 업로드 통계

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
# 비디오 적용 함수
# ============================================================

def apply_batch_videos(
    results: List[BatchVideoItem],
    videos_folder: Path,
    backup: bool = True,
    update_scene_callback = None
) -> Dict[str, Any]:
    """배치 비디오 적용

    Args:
        results: 분석 결과 (success 상태만 처리)
        videos_folder: 비디오 저장 폴더
        backup: 기존 비디오 백업 여부
        update_scene_callback: 씬 데이터 업데이트 콜백 함수
            callback(scene_num: int, video_path: str) -> None

    Returns:
        적용 결과 통계
    """

    success_items = [r for r in results if r.status == "success"]

    applied = 0
    failed = 0
    backed_up = 0
    backup_folder = None

    # 비디오 폴더 생성
    videos_folder = Path(videos_folder)
    videos_folder.mkdir(parents=True, exist_ok=True)

    # 백업 폴더 생성
    if backup:
        backup_folder = videos_folder / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    for item in success_items:
        try:
            scene_num = item.scene_number

            # 기존 비디오 백업
            if backup and item.current_video_path:
                current_path = Path(item.current_video_path)
                if current_path.exists():
                    if backup_folder:
                        backup_folder.mkdir(parents=True, exist_ok=True)
                        backup_path = backup_folder / current_path.name
                        shutil.copy2(current_path, backup_path)
                        backed_up += 1

            # 새 비디오 저장
            timestamp = int(datetime.now().timestamp() * 1000)
            ext = Path(item.filename).suffix.lower()
            new_filename = f"video_scene_{scene_num:03d}_{timestamp}{ext}"
            new_path = videos_folder / new_filename

            with open(new_path, 'wb') as f:
                f.write(item.file_data)

            # 콜백으로 씬 데이터 업데이트
            if update_scene_callback:
                update_scene_callback(scene_num, str(new_path))

            applied += 1

        except Exception as e:
            print(f"[BatchVideoUpload] ❌ 에러: {item.filename} - {e}", flush=True)
            failed += 1

    return {
        "applied": applied,
        "failed": failed,
        "backed_up": backed_up,
        "backup_folder": str(backup_folder) if backup_folder and backed_up > 0 else None
    }


def apply_batch_videos_direct(
    uploaded_files: list,
    results: List[BatchVideoItem],
    videos_folder: Path,
    backup: bool = True,
    update_scene_callback = None,
    progress_callback = None
) -> Dict[str, Any]:
    """배치 비디오 직접 적용 (v1.1 - 메모리 효율적)

    quick_analyze 결과와 원본 파일 목록을 사용하여 비디오 저장.
    file_index를 통해 원본 파일을 참조하여 메모리 사용 최소화.

    Args:
        uploaded_files: Streamlit file_uploader에서 반환된 파일 목록
        results: quick_analyze_batch_video_upload 결과 (success 상태만 처리)
        videos_folder: 비디오 저장 폴더
        backup: 기존 비디오 백업 여부
        update_scene_callback: 씬 데이터 업데이트 콜백 함수
            callback(scene_num: int, video_path: str) -> None
        progress_callback: 진행률 콜백 함수
            callback(current: int, total: int, filename: str) -> None

    Returns:
        적용 결과 통계
    """

    success_items = [r for r in results if r.status == "success"]

    applied = 0
    failed = 0
    backed_up = 0
    backup_folder = None
    total = len(success_items)

    # 비디오 폴더 생성
    videos_folder = Path(videos_folder)
    videos_folder.mkdir(parents=True, exist_ok=True)

    # 백업 폴더 생성
    if backup:
        backup_folder = videos_folder / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    for idx, item in enumerate(success_items):
        try:
            scene_num = item.scene_number
            file_index = item.file_index

            # 진행률 콜백
            if progress_callback:
                progress_callback(idx + 1, total, item.filename)

            # 원본 파일 찾기
            if file_index < 0 or file_index >= len(uploaded_files):
                print(f"[BatchVideoUpload] 잘못된 파일 인덱스: {file_index}", flush=True)
                failed += 1
                continue

            uploaded_file = uploaded_files[file_index]

            # 기존 비디오 백업
            if backup and item.current_video_path:
                current_path = Path(item.current_video_path)
                if current_path.exists():
                    if backup_folder:
                        backup_folder.mkdir(parents=True, exist_ok=True)
                        backup_path = backup_folder / current_path.name
                        shutil.copy2(current_path, backup_path)
                        backed_up += 1

            # 새 비디오 저장 (직접 getbuffer 사용 - 메모리 효율적)
            timestamp = int(datetime.now().timestamp() * 1000)
            ext = Path(item.filename).suffix.lower()
            new_filename = f"video_scene_{scene_num:03d}_{timestamp}{ext}"
            new_path = videos_folder / new_filename

            # 파일 저장 (getbuffer로 직접 저장)
            with open(new_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())

            print(f"[BatchVideoUpload] ✅ 씬 {scene_num}: {new_filename}", flush=True)

            # 콜백으로 씬 데이터 업데이트
            if update_scene_callback:
                update_scene_callback(scene_num, str(new_path))

            applied += 1

        except Exception as e:
            print(f"[BatchVideoUpload] ❌ 에러: {item.filename} - {e}", flush=True)
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

def get_existing_videos(scenes: List[Dict]) -> Dict[int, str]:
    """씬 데이터에서 현재 비디오 경로 추출

    Args:
        scenes: 씬 데이터 리스트

    Returns:
        {scene_id: video_path} 딕셔너리
    """

    result = {}

    for scene in scenes:
        scene_id = scene.get("scene_id") or scene.get("scene_num")
        if scene_id:
            # 비디오 경로 확인 (media_type이 video인 경우)
            media_type = scene.get("media_type", "image")
            if media_type == "video":
                video_path = scene.get("background_video", "")
                if video_path and Path(video_path).exists():
                    result[scene_id] = video_path

    return result


def get_scene_media_info(scene: Dict) -> Dict[str, Any]:
    """씬의 미디어 정보 추출

    Args:
        scene: 씬 데이터

    Returns:
        미디어 정보 딕셔너리
    """

    media_type = scene.get("media_type", "image")

    if media_type == "video":
        path = scene.get("background_video", "")
    else:
        path = scene.get("background_image", "")

    return {
        "media_type": media_type,
        "path": path,
        "exists": Path(path).exists() if path else False
    }
