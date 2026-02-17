# -*- coding: utf-8 -*-
"""
배치 분석 결과 병합 유틸리티 v1.0

배치별로 생성된 분석 결과를 scenes.json에 병합:
- 모든 배치 출력 파일 수집
- scene_id 기준으로 병합
- 한 번에 저장 (I/O 최소화)
- 실패한 배치 리포트
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime


# 병합할 출력 필드 (분석 결과)
OUTPUT_FIELDS = [
    "image_prompt",
    "image_prompt_en",
    "image_prompt_korean_text",
    "background_prompt",
    "background_prompt_en",
    "character_prompt",
    "character_prompt_en",
    "video_prompt_character",
    "video_prompt_full",
    "visual_elements",
    "direction_guide",
    "camera_suggestion",
    "location",
    "mood",
    "characters",
]


def load_batch_output(batch_output_path: str) -> Tuple[List[Dict], Optional[str]]:
    """
    배치 출력 파일 로드

    Args:
        batch_output_path: 배치 출력 JSON 파일 경로

    Returns:
        (결과 리스트, 에러 메시지 또는 None)
    """
    path = Path(batch_output_path)

    if not path.exists():
        return [], f"파일 없음: {path}"

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 배열인지 확인
        if not isinstance(data, list):
            # 단일 객체인 경우 배열로 변환
            if isinstance(data, dict):
                data = [data]
            else:
                return [], f"잘못된 형식: {type(data)}"

        return data, None

    except json.JSONDecodeError as e:
        return [], f"JSON 파싱 오류: {e}"
    except Exception as e:
        return [], f"로드 오류: {e}"


def validate_batch_result(result: Dict) -> Tuple[bool, List[str]]:
    """
    배치 결과 유효성 검증

    Args:
        result: 단일 씬 분석 결과

    Returns:
        (유효 여부, 누락된 필드 리스트)
    """
    missing_fields = []

    # scene_id 필수
    if "scene_id" not in result:
        missing_fields.append("scene_id")

    # 핵심 필드 확인 (최소 image_prompt_en과 background_prompt_en은 있어야 함)
    essential_fields = ["image_prompt_en", "background_prompt_en"]
    for field in essential_fields:
        if field not in result or not result[field]:
            missing_fields.append(field)

    return len(missing_fields) == 0, missing_fields


def merge_batch_results_to_scenes(
    scenes_json_path: str,
    batch_output_files: List[str],
    backup: bool = True
) -> dict:
    """
    모든 배치 결과를 scenes.json에 병합

    Args:
        scenes_json_path: scenes.json 파일 경로
        batch_output_files: 배치 출력 파일 경로 리스트
        backup: 병합 전 백업 생성 여부

    Returns:
        병합 결과 정보 딕셔너리
    """
    scenes_path = Path(scenes_json_path)

    if not scenes_path.exists():
        return {
            "success": False,
            "error": f"scenes.json 없음: {scenes_path}"
        }

    # 기존 scenes 로드
    print(f"[Merger] scenes.json 로드: {scenes_path}")
    with open(scenes_path, 'r', encoding='utf-8') as f:
        scenes = json.load(f)

    original_count = len(scenes)

    # 백업 생성
    if backup:
        backup_path = scenes_path.parent / f"scenes_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        print(f"[Merger] 백업 생성: {backup_path}")

    # scene_id 인덱스 생성
    scene_index = {
        s.get("scene_id", i): i
        for i, s in enumerate(scenes)
    }

    # 통계
    merged_count = 0
    skipped_count = 0
    failed_batches = []
    validation_errors = []

    # 각 배치 파일 처리
    for batch_file in batch_output_files:
        batch_name = Path(batch_file).name
        print(f"[Merger] 처리 중: {batch_name}")

        batch_results, error = load_batch_output(batch_file)

        if error:
            print(f"[Merger]   ⚠️ {error}")
            failed_batches.append({
                "file": batch_file,
                "error": error
            })
            continue

        batch_merged = 0
        batch_skipped = 0

        for result in batch_results:
            scene_id = result.get("scene_id")

            if scene_id is None:
                skipped_count += 1
                batch_skipped += 1
                continue

            # 유효성 검증
            is_valid, missing = validate_batch_result(result)
            if not is_valid:
                validation_errors.append({
                    "scene_id": scene_id,
                    "missing_fields": missing,
                    "batch_file": batch_name
                })
                # 경고만 하고 계속 진행 (부분 결과라도 저장)

            if scene_id in scene_index:
                idx = scene_index[scene_id]

                # 결과 필드 업데이트 (기존 데이터 보존)
                for field in OUTPUT_FIELDS:
                    if field in result and result[field] is not None:
                        # 빈 문자열이나 빈 배열도 유효한 값으로 처리
                        scenes[idx][field] = result[field]

                # 분석 완료 메타데이터
                scenes[idx]["analyzed_at"] = datetime.now().isoformat()
                scenes[idx]["analyzed_batch"] = batch_name

                merged_count += 1
                batch_merged += 1
            else:
                skipped_count += 1
                batch_skipped += 1

        print(f"[Merger]   ✅ 병합: {batch_merged}개, 스킵: {batch_skipped}개")

    # 최종 저장 (한 번만!)
    print(f"\n[Merger] scenes.json 저장 중...")
    with open(scenes_path, 'w', encoding='utf-8') as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)

    # 결과 리포트
    result = {
        "success": len(failed_batches) == 0,
        "scenes_json_path": str(scenes_path),
        "original_scenes": original_count,
        "merged_scenes": merged_count,
        "skipped_scenes": skipped_count,
        "total_batches": len(batch_output_files),
        "failed_batches": failed_batches,
        "validation_errors": validation_errors[:10],  # 최대 10개만
        "merged_at": datetime.now().isoformat()
    }

    print(f"\n[Merger] ═══════════════════════════════════════════")
    print(f"[Merger] 📊 병합 완료")
    print(f"[Merger]    원본 씬: {original_count}개")
    print(f"[Merger]    병합된 씬: {merged_count}개")
    print(f"[Merger]    스킵된 씬: {skipped_count}개")
    print(f"[Merger]    실패한 배치: {len(failed_batches)}개")
    if validation_errors:
        print(f"[Merger]    검증 경고: {len(validation_errors)}개")
    print(f"[Merger] ═══════════════════════════════════════════\n")

    return result


def merge_from_batch_meta(batch_meta_path: str, backup: bool = True) -> dict:
    """
    배치 메타 파일을 사용하여 결과 병합

    Args:
        batch_meta_path: batch_meta.json 파일 경로
        backup: 백업 생성 여부

    Returns:
        병합 결과 정보
    """
    meta_path = Path(batch_meta_path)

    if not meta_path.exists():
        return {
            "success": False,
            "error": f"메타 파일 없음: {meta_path}"
        }

    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    scenes_json_path = meta.get("scenes_json_path")
    batch_files = meta.get("batch_files", [])

    # 출력 파일 경로 생성
    batch_output_files = [
        bf.replace("_input.json", "_output.json")
        for bf in batch_files
    ]

    return merge_batch_results_to_scenes(
        scenes_json_path=scenes_json_path,
        batch_output_files=batch_output_files,
        backup=backup
    )


def get_merge_status(batch_dir: str) -> dict:
    """
    병합 상태 확인

    Args:
        batch_dir: 배치 디렉토리 경로

    Returns:
        상태 정보 딕셔너리
    """
    batch_path = Path(batch_dir)
    meta_file = batch_path / "batch_meta.json"

    if not meta_file.exists():
        return {"status": "not_prepared"}

    with open(meta_file, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    # 출력 파일 확인
    batch_files = meta.get("batch_files", [])
    completed = []
    pending = []

    for bf in batch_files:
        output_file = bf.replace("_input.json", "_output.json")
        if Path(output_file).exists():
            completed.append(Path(output_file).name)
        else:
            pending.append(Path(bf).name.replace("_input.json", "_output.json"))

    return {
        "total_batches": len(batch_files),
        "completed": len(completed),
        "pending": len(pending),
        "completed_files": completed,
        "pending_files": pending,
        "ready_to_merge": len(pending) == 0 and len(completed) > 0
    }


def partial_merge(
    scenes_json_path: str,
    batch_output_files: List[str],
    backup: bool = True
) -> dict:
    """
    완료된 배치만 부분 병합

    모든 배치가 완료되지 않아도 완료된 배치만 먼저 병합합니다.
    중간 저장 용도로 사용합니다.
    """
    # 존재하는 출력 파일만 필터링
    existing_files = [
        f for f in batch_output_files
        if Path(f).exists()
    ]

    if not existing_files:
        return {
            "success": False,
            "error": "병합할 출력 파일이 없습니다."
        }

    print(f"[Merger] 부분 병합: {len(existing_files)}/{len(batch_output_files)} 배치")

    return merge_batch_results_to_scenes(
        scenes_json_path=scenes_json_path,
        batch_output_files=existing_files,
        backup=backup
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python batch_result_merger.py <batch_meta.json>")
        print("  python batch_result_merger.py <scenes.json> <output1.json> <output2.json> ...")
        sys.exit(1)

    if sys.argv[1].endswith("batch_meta.json"):
        # 메타 파일 사용
        result = merge_from_batch_meta(sys.argv[1])
    else:
        # 직접 파일 지정
        scenes_path = sys.argv[1]
        output_files = sys.argv[2:]
        result = merge_batch_results_to_scenes(scenes_path, output_files)

    print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False)}")
