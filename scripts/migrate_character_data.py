"""
기존 프로젝트의 character_prompt -> characters 일괄 마이그레이션

사용법:
    python scripts/migrate_character_data.py
"""
import json
from pathlib import Path
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.character_sync import (
    sync_all_scenes_characters,
    get_sync_status,
    update_characters_json
)


def migrate_project(project_path: Path) -> dict:
    """단일 프로젝트 마이그레이션"""

    # scenes.json 경로 탐색: data/scenes.json 또는 analysis/scenes.json
    scenes_path = None
    for candidate in [
        project_path / "data" / "scenes.json",
        project_path / "analysis" / "scenes.json",
    ]:
        if candidate.exists():
            scenes_path = candidate
            break

    if not scenes_path:
        return {"status": "skip", "reason": "scenes.json not found"}

    # 씬 데이터 로드
    try:
        with open(scenes_path, 'r', encoding='utf-8') as f:
            scenes = json.load(f)
    except Exception as e:
        return {"status": "error", "reason": str(e)}

    if not scenes:
        return {"status": "skip", "reason": "empty scenes"}

    # 동기화 필요 여부 확인
    status = get_sync_status(scenes)

    if status["needs_sync"] == 0:
        return {
            "status": "ok",
            "message": f"이미 동기화됨 (prompt: {status['has_prompt']}, array: {status['has_array']})"
        }

    print(f"  - {status['needs_sync']}개 씬 동기화 필요")

    # 동기화 실행
    scenes, synced_count = sync_all_scenes_characters(scenes)

    # scenes.json 저장
    with open(scenes_path, 'w', encoding='utf-8') as f:
        json.dump(scenes, f, ensure_ascii=False, indent=2)

    # characters.json 업데이트
    characters_path = scenes_path.parent / "characters.json"
    added = update_characters_json(scenes, characters_path)

    return {
        "status": "migrated",
        "synced_scenes": synced_count,
        "added_characters": added
    }


def migrate_all_projects(base_path: Path):
    """모든 프로젝트 마이그레이션"""

    projects_dir = base_path / "data" / "projects"

    if not projects_dir.exists():
        print(f"프로젝트 디렉토리 없음: {projects_dir}")
        return

    results = []

    # 각 채널/프로젝트 순회
    for channel_dir in sorted(projects_dir.iterdir()):
        if not channel_dir.is_dir():
            continue

        videos_dir = channel_dir / "videos"
        if not videos_dir.exists():
            continue

        for video_dir in sorted(videos_dir.iterdir()):
            if not video_dir.is_dir():
                continue

            print(f"\n[마이그레이션] {channel_dir.name}/{video_dir.name}")

            result = migrate_project(video_dir)
            result["project"] = f"{channel_dir.name}/{video_dir.name}"
            results.append(result)

    # 결과 요약
    print("\n" + "=" * 50)
    print("[마이그레이션 결과 요약]")

    migrated = [r for r in results if r["status"] == "migrated"]
    ok = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skip"]
    errors = [r for r in results if r["status"] == "error"]

    print(f"  - 마이그레이션 완료: {len(migrated)}개 프로젝트")
    print(f"  - 이미 동기화됨: {len(ok)}개 프로젝트")
    print(f"  - 스킵: {len(skipped)}개 프로젝트")
    if errors:
        print(f"  - 오류: {len(errors)}개 프로젝트")

    if migrated:
        total_scenes = sum(r.get("synced_scenes", 0) for r in migrated)
        total_chars = sum(r.get("added_characters", 0) for r in migrated)
        print(f"  - 총 동기화된 씬: {total_scenes}개")
        print(f"  - 총 추가된 캐릭터: {total_chars}명")

    if errors:
        print("\n[오류 상세]")
        for r in errors:
            print(f"  - {r['project']}: {r['reason']}")


if __name__ == "__main__":
    # 프로젝트 루트 경로
    base_path = Path(__file__).parent.parent

    print("=" * 50)
    print("[캐릭터 데이터 마이그레이션 시작]")
    print("=" * 50)

    migrate_all_projects(base_path)

    print("\n[완료]")
