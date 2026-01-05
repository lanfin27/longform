"""
기존 프로젝트 데이터를 새 2단계 구조로 마이그레이션

사용법:
    python scripts/migrate_to_new_structure.py

구조 변환:
    기존: data/projects/{project_name}/script.txt, analysis/, ...
    신규: data/projects/{project_name}/videos/{project_name}/script.txt, analysis/, ...

⚠️ 주의:
- 이미 새 구조(videos/ 폴더 있음)인 프로젝트는 스킵
- 원본 데이터는 이동되며 삭제되지 않음
- 실행 전 백업 권장
"""

import os
import sys
import shutil
import json
from pathlib import Path
from datetime import datetime

# 프로젝트 루트 추가
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import PROJECTS_DIR


def migrate_old_projects(dry_run: bool = False):
    """
    기존 프로젝트를 새 구조로 마이그레이션

    Args:
        dry_run: True면 실제 변경 없이 시뮬레이션만
    """
    print("=" * 60)
    print("프로젝트 구조 마이그레이션")
    print(f"프로젝트 폴더: {PROJECTS_DIR}")
    print(f"모드: {'시뮬레이션 (dry-run)' if dry_run else '실제 마이그레이션'}")
    print("=" * 60)
    print()

    if not PROJECTS_DIR.exists():
        print("[마이그레이션] 프로젝트 폴더가 없습니다.")
        return

    migrated = 0
    skipped = 0
    errors = 0

    for item in PROJECTS_DIR.iterdir():
        if not item.is_dir():
            continue

        if item.name.startswith('.') or item.name.startswith('_'):
            print(f"[스킵] '{item.name}' - 숨김/임시 폴더")
            skipped += 1
            continue

        # 이미 새 구조인지 확인 (videos 폴더가 있으면 스킵)
        if (item / "videos").exists():
            print(f"[스킵] '{item.name}' - 이미 새 구조")
            skipped += 1
            continue

        # 기존 프로젝트 데이터가 있는지 확인
        has_data = any([
            (item / "script.txt").exists(),
            (item / "script.srt").exists(),
            (item / "analysis").exists(),
            (item / "characters").exists(),
            (item / "images").exists(),
            (item / "audio").exists(),
            (item / "config.json").exists(),
        ])

        if not has_data:
            print(f"[스킵] '{item.name}' - 데이터 없음")
            skipped += 1
            continue

        print(f"\n[마이그레이션] '{item.name}' 처리 중...")

        try:
            if not dry_run:
                migrate_single_project(item)
            else:
                print(f"  - [시뮬레이션] videos/{item.name}/ 폴더 생성 예정")
                print(f"  - [시뮬레이션] 기존 데이터 이동 예정")

            migrated += 1
            print(f"[완료] '{item.name}' 마이그레이션 {'예정' if dry_run else '완료'}")

        except Exception as e:
            print(f"[오류] '{item.name}' 마이그레이션 실패: {e}")
            errors += 1

    print()
    print("=" * 60)
    print(f"마이그레이션 {'시뮬레이션' if dry_run else ''} 결과:")
    print(f"  - 마이그레이션: {migrated}개")
    print(f"  - 스킵: {skipped}개")
    print(f"  - 오류: {errors}개")
    print("=" * 60)

    if dry_run and migrated > 0:
        print()
        print("실제 마이그레이션을 실행하려면:")
        print("  python scripts/migrate_to_new_structure.py --execute")


def migrate_single_project(project_path: Path):
    """
    단일 프로젝트 마이그레이션

    Args:
        project_path: 프로젝트 폴더 경로
    """
    project_name = project_path.name

    # 1. videos 폴더 생성
    videos_path = project_path / "videos"
    videos_path.mkdir(exist_ok=True)

    # 2. 첫 번째 영상 폴더 생성 (프로젝트명과 동일)
    video_path = videos_path / project_name
    video_path.mkdir(exist_ok=True)

    # 3. 기존 데이터를 영상 폴더로 이동
    items_to_move = [
        "script.txt",
        "script.srt",
        "analysis",
        "characters",
        "images",
        "audio",
        "output",
        "research",
        "scripts",
        "prompts",
        "export",
        "config.json",  # 레거시 설정
    ]

    for item_name in items_to_move:
        src = project_path / item_name
        if src.exists():
            dest = video_path / item_name
            if src.is_dir():
                if dest.exists():
                    # 기존 폴더가 있으면 내용 병합
                    for child in src.iterdir():
                        shutil.move(str(child), str(dest / child.name))
                    src.rmdir()
                else:
                    shutil.move(str(src), str(dest))
            else:
                shutil.move(str(src), str(dest))
            print(f"  - 이동: {item_name}")

    # 4. 공유 폴더 생성
    (project_path / "shared_characters").mkdir(exist_ok=True)
    (project_path / "shared_styles").mkdir(exist_ok=True)

    # 5. 프로젝트 설정 파일 생성
    project_config = {
        "name": project_name,
        "description": f"마이그레이션됨 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
        "created_at": datetime.now().isoformat(),
        "default_style": None,
        "default_tts_voice": None,
        "settings": {}
    }

    # 레거시 config.json에서 정보 추출
    legacy_config_path = video_path / "config.json"
    if legacy_config_path.exists():
        try:
            with open(legacy_config_path, "r", encoding="utf-8") as f:
                legacy_config = json.load(f)
            project_config["name"] = legacy_config.get("name", project_name)
            project_config["created_at"] = legacy_config.get("created_at", project_config["created_at"])
        except:
            pass

    with open(project_path / "project_config.json", "w", encoding="utf-8") as f:
        json.dump(project_config, f, ensure_ascii=False, indent=2)
    print(f"  - 생성: project_config.json")

    # 6. 영상 설정 파일 생성
    video_config = {
        "title": project_config["name"],
        "description": "",
        "created_at": project_config["created_at"],
        "updated_at": datetime.now().isoformat(),
        "status": "migrated",
        "current_step": 1,
        "settings": {},
        "statistics": {
            "total_scenes": 0,
            "total_characters": 0,
            "generated_images": 0,
            "generated_audio": 0
        }
    }

    # 레거시 config.json에서 추가 정보 추출
    if legacy_config_path.exists():
        try:
            with open(legacy_config_path, "r", encoding="utf-8") as f:
                legacy_config = json.load(f)
            video_config["title"] = legacy_config.get("name", video_config["title"])
            video_config["current_step"] = legacy_config.get("current_step", 1)
            video_config["status"] = legacy_config.get("status", "migrated")
        except:
            pass

    with open(video_path / "video_config.json", "w", encoding="utf-8") as f:
        json.dump(video_config, f, ensure_ascii=False, indent=2)
    print(f"  - 생성: video_config.json")

    # 7. 필요한 하위 폴더 생성 (없으면)
    folders = [
        "analysis",
        "characters",
        "images/backgrounds",
        "images/composited",
        "images/content",
        "audio",
        "output",
        "research/transcripts",
        "scripts",
        "prompts",
    ]

    for folder in folders:
        folder_path = video_path / folder
        folder_path.mkdir(parents=True, exist_ok=True)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="프로젝트 구조 마이그레이션")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="실제 마이그레이션 실행 (기본값: dry-run)"
    )
    parser.add_argument(
        "--project",
        type=str,
        help="특정 프로젝트만 마이그레이션 (폴더명)"
    )

    args = parser.parse_args()

    if args.project:
        # 특정 프로젝트만 마이그레이션
        project_path = PROJECTS_DIR / args.project
        if not project_path.exists():
            print(f"프로젝트를 찾을 수 없습니다: {args.project}")
            return

        if (project_path / "videos").exists():
            print(f"이미 새 구조입니다: {args.project}")
            return

        if args.execute:
            migrate_single_project(project_path)
            print(f"마이그레이션 완료: {args.project}")
        else:
            print(f"시뮬레이션: {args.project}")
            print("실제 실행: --execute 옵션 추가")
    else:
        # 전체 마이그레이션
        migrate_old_projects(dry_run=not args.execute)


if __name__ == "__main__":
    main()
