"""
SRT 세그먼트 그룹화 모듈

⚠️ Critical: 이미지 생성은 '시간 간격'이 아닌 '자막 세그먼트 그룹' 기준

Vrew는 문장(자막 클립) 단위로 작동하므로,
시간 기준으로 이미지를 만들면 싱크가 맞지 않습니다.
"""
import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import (
    DEFAULT_SEGMENTS_PER_GROUP,
    MIN_GROUP_DURATION_SEC,
    MAX_GROUP_DURATION_SEC
)


class SRTSegmentGrouper:
    """
    SRT 자막을 의미 단위(문단)로 그룹화

    핵심: 이미지 1장 = 자막 세그먼트 N개 (보통 3~5개)

    파일명 규칙: {그룹번호}_seg_{시작세그먼트}-{끝세그먼트}.png
    예: 001_seg_001-004.png
    """

    def __init__(
        self,
        segments_per_group: int = None,
        min_duration: float = None,
        max_duration: float = None
    ):
        """
        Args:
            segments_per_group: 그룹당 자막 세그먼트 수 (기본: 4)
            min_duration: 최소 그룹 길이 (초, 기본: 8.0)
            max_duration: 최대 그룹 길이 (초, 기본: 25.0)
        """
        self.segments_per_group = segments_per_group or DEFAULT_SEGMENTS_PER_GROUP
        self.min_duration = min_duration or MIN_GROUP_DURATION_SEC
        self.max_duration = max_duration or MAX_GROUP_DURATION_SEC

    def parse_srt(self, srt_path: str) -> List[Dict]:
        """
        SRT 파일 파싱 (다양한 형식 지원)

        Args:
            srt_path: SRT 파일 경로

        Returns:
            세그먼트 딕셔너리 리스트
        """
        import re

        segments = []
        srt_path = Path(srt_path)

        if not srt_path.exists():
            print(f"[ERROR] SRT 파일이 없습니다: {srt_path}")
            return segments

        # 파일 읽기 (인코딩 처리)
        try:
            content = srt_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = srt_path.read_text(encoding="utf-8-sig")
            except:
                content = srt_path.read_text(encoding="cp949")

        # 빈 파일 체크
        if not content or not content.strip():
            print(f"[ERROR] SRT 파일이 비어있습니다: {srt_path}")
            return segments

        # WEBVTT 헤더 제거
        content = re.sub(r'^WEBVTT\s*\n', '', content, flags=re.MULTILINE)

        # 다양한 줄바꿈 정규화
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # 블록 분리 (빈 줄 기준)
        blocks = re.split(r'\n\s*\n', content.strip())

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            lines = block.split('\n')

            # 타임코드 찾기
            timecode_line = None
            timecode_idx = -1
            text_lines = []

            for idx, line in enumerate(lines):
                line = line.strip()
                if '-->' in line:
                    timecode_line = line
                    timecode_idx = idx
                    break

            if timecode_line is None:
                continue

            # 타임코드 이후의 줄은 텍스트
            for line in lines[timecode_idx + 1:]:
                line = line.strip()
                if line and not line.isdigit():
                    text_lines.append(line)

            # 텍스트가 없으면 건너뛰기
            if not text_lines:
                continue

            # 타임코드 파싱
            try:
                times = timecode_line.split('-->')
                start_str = times[0].strip()
                end_str = times[1].strip()

                start_ms = self._time_to_ms(start_str)
                end_ms = self._time_to_ms(end_str)
                text = ' '.join(text_lines)

                segments.append({
                    "index": len(segments) + 1,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "start_time": start_str.replace(",", "."),
                    "end_time": end_str.replace(",", "."),
                    "text": text
                })
            except Exception as e:
                print(f"[WARNING] 타임코드 파싱 실패: {e}")
                continue

        print(f"[INFO] SRT 파싱 완료: {len(segments)}개 세그먼트")
        return segments

    def _time_to_ms(self, time_str: str) -> int:
        """
        시간 문자열을 밀리초로 변환 (다양한 형식 지원)

        Args:
            time_str: "HH:MM:SS,mmm" 또는 "HH:MM:SS.mmm" 또는 "MM:SS.mmm"

        Returns:
            밀리초
        """
        import re

        # 쉼표를 점으로 통일
        time_str = time_str.replace(",", ".").strip()

        # HH:MM:SS.mmm 형식
        match = re.match(r'(\d+):(\d+):(\d+)[.,](\d+)', time_str)
        if match:
            hours, minutes, seconds, ms = match.groups()
            ms = ms.ljust(3, '0')[:3]  # 밀리초를 3자리로 맞춤
            return (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000 + int(ms)

        # HH:MM:SS 형식 (밀리초 없음)
        match = re.match(r'(\d+):(\d+):(\d+)$', time_str)
        if match:
            hours, minutes, seconds = match.groups()
            return (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000

        # MM:SS.mmm 형식 (시간 없음)
        match = re.match(r'(\d+):(\d+)[.,](\d+)', time_str)
        if match:
            minutes, seconds, ms = match.groups()
            ms = ms.ljust(3, '0')[:3]
            return (int(minutes) * 60 + int(seconds)) * 1000 + int(ms)

        # MM:SS 형식 (시간, 밀리초 없음)
        match = re.match(r'(\d+):(\d+)$', time_str)
        if match:
            minutes, seconds = match.groups()
            return (int(minutes) * 60 + int(seconds)) * 1000

        print(f"[WARNING] 타임코드 형식 인식 실패: {time_str}")
        return 0

    def group_segments(
        self,
        segments: List[Dict],
        paragraph_breaks: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        자막 세그먼트를 의미 단위 그룹으로 묶기

        그룹화 전략:
        1. 문단 구분 정보가 있으면 우선 사용
        2. 없으면 segments_per_group 개수로 균등 분할
        3. 최소/최대 길이 제한 적용

        Args:
            segments: SRT 세그먼트 리스트
            paragraph_breaks: 문단 구분 정보 (4단계 TTS에서 생성)

        Returns:
            그룹 딕셔너리 리스트
        """
        if not segments:
            return []

        # 문단 구분 시간 추출
        break_times = []
        if paragraph_breaks:
            break_times = [b["time_ms"] for b in paragraph_breaks]

        groups = []
        current_group = []
        group_id = 1

        for seg in segments:
            current_group.append(seg)

            # 그룹 종료 조건 확인
            should_close = False

            # 조건 1: 문단 구분점에 도달 (±3초 허용)
            if any(
                seg["end_ms"] >= bt and seg["end_ms"] < bt + 3000
                for bt in break_times
            ):
                should_close = True

            # 조건 2: 최대 세그먼트 수 도달 (최소 길이 확보 시)
            elif len(current_group) >= self.segments_per_group:
                group_duration = (
                    current_group[-1]["end_ms"] - current_group[0]["start_ms"]
                ) / 1000

                if group_duration >= self.min_duration:
                    should_close = True

            # 조건 3: 최대 길이 초과
            group_duration = (
                current_group[-1]["end_ms"] - current_group[0]["start_ms"]
            ) / 1000

            if group_duration >= self.max_duration:
                should_close = True

            # 그룹 종료
            if should_close and current_group:
                groups.append(self._create_group(group_id, current_group))
                group_id += 1
                current_group = []

        # 마지막 그룹 처리
        if current_group:
            groups.append(self._create_group(group_id, current_group))

        return groups

    def _create_group(self, group_id: int, segments: List[Dict]) -> Dict:
        """
        그룹 객체 생성

        Args:
            group_id: 그룹 ID
            segments: 세그먼트 리스트

        Returns:
            그룹 딕셔너리
        """
        return {
            "group_id": group_id,
            "segment_indices": [s["index"] for s in segments],
            "start_ms": segments[0]["start_ms"],
            "end_ms": segments[-1]["end_ms"],
            "start_time": self._ms_to_time(segments[0]["start_ms"]),
            "end_time": self._ms_to_time(segments[-1]["end_ms"]),
            "duration_sec": round(
                (segments[-1]["end_ms"] - segments[0]["start_ms"]) / 1000, 1
            ),
            "combined_text": " ".join(s["text"] for s in segments),
            "segment_count": len(segments)
        }

    def _ms_to_time(self, ms: int) -> str:
        """
        밀리초를 시간 문자열로 변환

        Args:
            ms: 밀리초

        Returns:
            "HH:MM:SS.mmm" 형식 문자열
        """
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        milliseconds = ms % 1000

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    def generate_filename(self, group: Dict) -> str:
        """
        Vrew 친화적인 파일명 생성

        형식: {그룹번호}_seg_{시작세그먼트}-{끝세그먼트}.png
        예시: 001_seg_001-004.png

        Args:
            group: 그룹 딕셔너리

        Returns:
            파일명 문자열
        """
        indices = group["segment_indices"]
        return f"{group['group_id']:03d}_seg_{indices[0]:03d}-{indices[-1]:03d}.png"

    def save_groups(self, groups: List[Dict], output_path: str):
        """
        그룹 정보 JSON 저장

        Args:
            groups: 그룹 리스트
            output_path: 출력 파일 경로
        """
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(groups, f, ensure_ascii=False, indent=2)

    def create_mapping_excel(self, groups: List[Dict], output_path: str):
        """
        이미지-자막 매핑 Excel 생성

        Args:
            groups: 그룹 리스트
            output_path: 출력 파일 경로
        """
        data = []

        for g in groups:
            data.append({
                "이미지 파일": self.generate_filename(g),
                "시작 자막": g["segment_indices"][0],
                "끝 자막": g["segment_indices"][-1],
                "시작 시간": g["start_time"],
                "끝 시간": g["end_time"],
                "길이(초)": g["duration_sec"],
                "내용": g["combined_text"][:60] + "..." if len(g["combined_text"]) > 60 else g["combined_text"]
            })

        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)

    def get_summary(self, groups: List[Dict]) -> Dict:
        """
        그룹화 요약 정보

        Args:
            groups: 그룹 리스트

        Returns:
            요약 딕셔너리
        """
        if not groups:
            return {
                "total_groups": 0,
                "total_segments": 0,
                "total_duration_sec": 0
            }

        total_segments = sum(g["segment_count"] for g in groups)
        total_duration = sum(g["duration_sec"] for g in groups)
        avg_duration = total_duration / len(groups)
        avg_segments = total_segments / len(groups)

        return {
            "total_groups": len(groups),
            "total_segments": total_segments,
            "total_duration_sec": round(total_duration, 1),
            "avg_group_duration_sec": round(avg_duration, 1),
            "avg_segments_per_group": round(avg_segments, 1),
            "min_duration_sec": min(g["duration_sec"] for g in groups),
            "max_duration_sec": max(g["duration_sec"] for g in groups)
        }
