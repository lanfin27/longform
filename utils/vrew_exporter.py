"""
Vrew 최적화 Export 모듈

⚠️ Critical: Vrew에서 바로 사용할 수 있는 폴더 구조 생성

Export 폴더 구조:
- images/              세그먼트 기준 파일명
- audio.mp3            무음 패딩 포함
- subtitles.srt        조정된 타이밍
- script_for_vrew.txt  원고 복사용
- image_mapping.xlsx   이미지-자막 매핑
- thumbnail_text.txt   썸네일 텍스트
- README.txt           사용 가이드
"""
import shutil
import json
import pandas as pd
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class VrewExporter:
    """
    Vrew 최적화 Export

    이미지-자막 싱크가 완벽하게 맞도록 구조화된 폴더 생성
    """

    def export(
        self,
        project_path,
        output_dir: Optional[str] = None,
        include_script: bool = True,
        include_mapping: bool = True,
        include_thumbnail_text: bool = True,
        include_readme: bool = True
    ) -> str:
        """
        Vrew용 Export 실행

        Args:
            project_path: 프로젝트 경로
            output_dir: 출력 디렉토리 (기본: project/export)
            include_script: script_for_vrew.txt 포함 여부
            include_mapping: image_mapping.xlsx 포함 여부
            include_thumbnail_text: thumbnail_text.txt 포함 여부
            include_readme: README.txt 포함 여부

        Returns:
            Export 폴더 경로
        """
        project = Path(project_path)

        if output_dir is None:
            output = project / "export"
        else:
            output = Path(output_dir)

        # 기존 export 폴더 정리
        if output.exists():
            shutil.rmtree(output)

        # 폴더 생성
        images_dir = output / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        image_count = 0

        # 1. 이미지 복사 (세그먼트 기준 파일명 유지)
        src_images = sorted((project / "images" / "content").glob("*.png"))
        for img in src_images:
            shutil.copy(img, images_dir / img.name)
            image_count += 1

        # 2. 오디오 복사
        for audio in (project / "audio").glob("voice_*.mp3"):
            shutil.copy(audio, output / "audio.mp3")
            break

        # 3. 자막 복사
        for srt in (project / "audio").glob("voice_*.srt"):
            shutil.copy(srt, output / "subtitles.srt")
            break

        # 4. script_for_vrew.txt 생성 (원고 복사용)
        if include_script:
            self._create_script_for_vrew(project, output)

        # 5. image_mapping.xlsx 생성
        if include_mapping:
            self._create_image_mapping(project, output)

        # 6. thumbnail_text.txt 생성
        if include_thumbnail_text:
            self._create_thumbnail_text(project, output)

        # 7. README 생성
        if include_readme:
            self._create_readme(output, image_count)

        return str(output)

    def _create_script_for_vrew(self, project: Path, output: Path):
        """
        Vrew 원고 불러오기용 스크립트 생성

        문단별로 줄바꿈하여 복사+붙여넣기가 쉽도록 함
        """
        # 스크립트 파일 찾기 (final 우선, 없으면 draft)
        script_files = list((project / "scripts").glob("final_*.txt"))
        if not script_files:
            script_files = list((project / "scripts").glob("draft_*.txt"))

        if script_files:
            with open(script_files[0], "r", encoding="utf-8") as f:
                script = f.read()

            with open(output / "script_for_vrew.txt", "w", encoding="utf-8") as f:
                f.write("=" * 60 + "\n")
                f.write("Vrew 원고 불러오기용 스크립트\n")
                f.write("이 내용을 복사하여 Vrew에 붙여넣기 하세요.\n")
                f.write("=" * 60 + "\n\n")
                f.write(script)

    def _create_image_mapping(self, project: Path, output: Path):
        """
        이미지-자막 매핑 테이블 생성

        Vrew에서 어떤 자막에 어떤 이미지를 넣어야 하는지 참고용
        """
        groups_path = project / "prompts" / "segment_groups.json"

        if groups_path.exists():
            with open(groups_path, "r", encoding="utf-8") as f:
                groups = json.load(f)

            mapping_data = []
            for g in groups:
                indices = g["segment_indices"]
                mapping_data.append({
                    "이미지 파일": f"{g['group_id']:03d}_seg_{indices[0]:03d}-{indices[-1]:03d}.png",
                    "시작 자막": indices[0],
                    "끝 자막": indices[-1],
                    "시작 시간": g.get("start_time", ""),
                    "끝 시간": g.get("end_time", ""),
                    "길이(초)": g.get("duration_sec", 0),
                    "내용": g.get("combined_text", "")[:50] + "..."
                })

            df = pd.DataFrame(mapping_data)
            df.to_excel(output / "image_mapping.xlsx", index=False)

    def _create_thumbnail_text(self, project: Path, output: Path):
        """
        썸네일 텍스트 복사용 파일 생성

        FLUX는 텍스트 생성이 불안정하므로 텍스트는 별도 합성
        """
        prompts_path = project / "prompts" / "thumbnail_prompts.json"

        if prompts_path.exists():
            with open(prompts_path, "r", encoding="utf-8") as f:
                prompts = json.load(f)

            with open(output / "thumbnail_text.txt", "w", encoding="utf-8") as f:
                f.write("=" * 60 + "\n")
                f.write("썸네일 텍스트 (미리캔버스/Vrew에서 합성용)\n")
                f.write("=" * 60 + "\n\n")

                for p in prompts.get("thumbnail_prompts", []):
                    f.write(f"[버전 {p.get('version', 'A')}]\n")
                    f.write(f"타입: {p.get('type', '')}\n\n")

                    overlay = p.get("overlay_text", {})
                    f.write(f"메인 텍스트: {overlay.get('main', '')}\n")
                    f.write(f"서브 텍스트: {overlay.get('sub', '')}\n")
                    f.write(f"권장 폰트: {overlay.get('font_suggestion', '')}\n")
                    f.write(f"권장 색상: {overlay.get('color_suggestion', '')}\n")
                    f.write("\n" + "-" * 40 + "\n\n")

    def _create_readme(self, output: Path, image_count: int):
        """
        README 파일 생성
        """
        content = f"""
================================================================================
AI 롱폼 유튜브 생성 Tool - Vrew Export
================================================================================

📁 폴더 구조
├─ images/              본문 이미지 ({image_count}개)
├─ audio.mp3            TTS 오디오 (문단 무음 패딩 포함)
├─ subtitles.srt        자막 파일 (조정된 타이밍)
├─ script_for_vrew.txt  원고 (복사+붙여넣기용)
├─ image_mapping.xlsx   이미지-자막 매핑 표
├─ thumbnail_text.txt   썸네일 텍스트 (합성용)
└─ README.txt           이 파일

================================================================================
📌 Vrew Import 방법
================================================================================

1. Vrew 실행 → 새 프로젝트 → "음성으로 영상 만들기"

2. audio.mp3 파일 선택
   - 문단별 1.5초 무음이 이미 포함되어 있습니다.

3. 자막 설정
   - 방법 A: subtitles.srt 파일 직접 import
   - 방법 B: Vrew 자동 생성 후 수정

4. 원고 확인
   - script_for_vrew.txt 내용 참고

5. 이미지 삽입 (⚠️ 중요!)
   - image_mapping.xlsx 파일을 열어 참고하세요.
   - 각 자막 구간에 맞는 이미지를 삽입합니다.

   예시:
   | 이미지 파일          | 자막 구간 |
   |---------------------|----------|
   | 001_seg_001-004.png | 1~4번    |
   | 002_seg_005-008.png | 5~8번    |

6. 썸네일 제작
   - 나노바나나에서 배경 이미지 생성
   - thumbnail_text.txt의 텍스트를 미리캔버스/Vrew에서 합성

7. 최종 편집 후 Export

================================================================================
💡 팁
================================================================================

- 이미지 파일명의 숫자는 해당 자막 세그먼트 번호입니다.
  예: 002_seg_005-008.png = 자막 5~8번 구간용

- 오디오에는 문단 사이 1.5초 무음이 포함되어 있습니다.
  (시니어 시청자가 내용을 소화할 시간 제공)

- 본문 이미지에는 텍스트가 포함되어 있지 않습니다.
  필요시 Vrew에서 텍스트를 추가하세요.

- 썸네일은 FLUX 모델로 배경만 생성됩니다.
  텍스트는 thumbnail_text.txt를 참고하여 수동 합성하세요.

================================================================================
🎬 제작: AI 롱폼 유튜브 생성 Tool v2.1
================================================================================
"""
        with open(output / "README.txt", "w", encoding="utf-8") as f:
            f.write(content.strip())
