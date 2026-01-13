# -*- coding: utf-8 -*-
"""
SRT 자막 파일 파서 모듈 v1.0

Vrew 등에서 생성된 SRT 파일을 씬 데이터로 변환

기능:
- SRT 파일 파싱 (다양한 인코딩 지원)
- 시간 코드 → 초 단위 변환
- 짧은 씬 자동 병합 옵션
- 씬 분석 입력 형식으로 변환
"""

import re
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class SRTParser:
    """SRT 파일 파서"""

    # SRT 시간 형식: 00:00:00,000 또는 00:00:00.000
    TIME_PATTERN = re.compile(
        r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})'
    )

    @classmethod
    def parse_file(cls, file_path: str, encoding: str = 'utf-8') -> List[Dict]:
        """
        SRT 파일 파싱

        Args:
            file_path: SRT 파일 경로
            encoding: 파일 인코딩 (기본: utf-8)

        Returns:
            씬 데이터 리스트
        """
        # 파일 읽기 (여러 인코딩 시도)
        content = None
        encodings = [encoding, 'utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'latin-1']

        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                print(f"[SRT Parser] 파일 읽기 성공 (인코딩: {enc})")
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if content is None:
            raise ValueError(f"파일을 읽을 수 없습니다: {file_path}")

        return cls.parse_content(content)

    @classmethod
    def parse_content(cls, content: str) -> List[Dict]:
        """
        SRT 내용 파싱

        Args:
            content: SRT 파일 내용

        Returns:
            씬 데이터 리스트
        """
        scenes = []

        # BOM 제거
        content = content.lstrip('\ufeff')

        # 줄바꿈 정규화
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # 블록 단위로 분리 (빈 줄로 구분)
        blocks = re.split(r'\n\n+', content.strip())

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            scene = cls._parse_block(block)
            if scene:
                scenes.append(scene)

        # 씬 번호 재정렬
        for i, scene in enumerate(scenes):
            scene['scene_id'] = i + 1

        print(f"[SRT Parser] {len(scenes)}개 씬 파싱 완료")

        return scenes

    @classmethod
    def _parse_block(cls, block: str) -> Optional[Dict]:
        """단일 SRT 블록 파싱"""
        lines = block.strip().split('\n')

        if len(lines) < 2:
            return None

        # 첫 번째 줄: 씬 번호 (숫자만)
        try:
            scene_num = int(lines[0].strip())
        except ValueError:
            # 숫자가 아니면 시간 코드인지 확인
            if '-->' in lines[0]:
                # 씬 번호가 없는 형식
                lines.insert(0, '0')
                scene_num = 0
            else:
                return None

        # 두 번째 줄: 시간 코드
        time_line = lines[1].strip()
        time_match = re.match(
            r'(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{3})',
            time_line
        )

        if not time_match:
            return None

        start_time = time_match.group(1)
        end_time = time_match.group(2)

        # 나머지 줄: 자막 텍스트
        text_lines = lines[2:]
        text = '\n'.join(text_lines).strip()

        # 빈 텍스트 무시
        if not text:
            return None

        # HTML 스타일 태그 제거 (<font>, <b>, <i> 등)
        text = re.sub(r'<[^>]+>', '', text)

        # >> 마커 제거 (화자 구분용)
        text = re.sub(r'^>>\s*', '', text, flags=re.MULTILINE)

        # ♪ 음악 표시 제거
        text = re.sub(r'[♪♫]', '', text)

        # 특수 마커 제거 ([음악], [박수] 등)
        text = re.sub(r'\[[^\]]+\]', '', text)

        # 공백 정리
        text = ' '.join(text.split())

        if not text.strip():
            return None

        # 시간을 초 단위로 변환
        start_seconds = cls._time_to_seconds(start_time)
        end_seconds = cls._time_to_seconds(end_time)
        duration = end_seconds - start_seconds

        return {
            'scene_id': scene_num,
            'start_time': cls._normalize_time_format(start_time),
            'end_time': cls._normalize_time_format(end_time),
            'start_seconds': round(start_seconds, 3),
            'end_seconds': round(end_seconds, 3),
            'duration': round(duration, 3),
            'narration': text.strip(),
            'script_text': text.strip(),  # 호환성을 위해 추가
            'source': 'srt'
        }

    @classmethod
    def _time_to_seconds(cls, time_str: str) -> float:
        """시간 문자열을 초 단위로 변환"""
        # 쉼표를 마침표로 변환
        time_str = time_str.replace(',', '.')

        match = cls.TIME_PATTERN.match(time_str)
        if not match:
            return 0.0

        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        milliseconds = int(match.group(4))

        total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000

        return total_seconds

    @classmethod
    def _normalize_time_format(cls, time_str: str) -> str:
        """시간 형식 정규화 (00:00:00,000 형식으로)"""
        time_str = time_str.replace('.', ',')

        # 시간 부분이 1자리인 경우 2자리로
        match = cls.TIME_PATTERN.match(time_str.replace(',', '.'))
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            milliseconds = int(match.group(4))
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

        return time_str

    @classmethod
    def merge_short_scenes(
        cls,
        scenes: List[Dict],
        min_duration: float = 3.0,
        max_merged_duration: float = 15.0,
        max_merged_chars: int = 300
    ) -> List[Dict]:
        """
        짧은 씬들을 병합

        Args:
            scenes: 씬 데이터 리스트
            min_duration: 최소 씬 길이 (초)
            max_merged_duration: 병합된 씬의 최대 길이 (초)
            max_merged_chars: 병합된 씬의 최대 글자 수

        Returns:
            병합된 씬 데이터 리스트
        """
        if not scenes:
            return []

        merged = []
        current = scenes[0].copy()

        for scene in scenes[1:]:
            # 현재 씬이 너무 짧고, 병합 가능한지 확인
            merged_duration = scene['end_seconds'] - current['start_seconds']
            merged_text = current['narration'] + ' ' + scene['narration']

            can_merge = (
                current['duration'] < min_duration and
                merged_duration <= max_merged_duration and
                len(merged_text) <= max_merged_chars
            )

            if can_merge:
                # 병합
                current['end_time'] = scene['end_time']
                current['end_seconds'] = scene['end_seconds']
                current['duration'] = current['end_seconds'] - current['start_seconds']
                current['narration'] = merged_text
                current['script_text'] = merged_text
            else:
                # 저장하고 새 씬 시작
                merged.append(current)
                current = scene.copy()

        # 마지막 씬 추가
        merged.append(current)

        # 씬 번호 재정렬
        for i, scene in enumerate(merged):
            scene['scene_id'] = i + 1

        original_count = len(scenes)
        merged_count = len(merged)
        print(f"[SRT Parser] 씬 병합: {original_count}개 -> {merged_count}개")

        return merged

    @classmethod
    def to_script_format(cls, scenes: List[Dict], include_time: bool = True) -> str:
        """
        씬 데이터를 스크립트 형식으로 변환

        Args:
            scenes: 씬 데이터 리스트
            include_time: 시간 정보 포함 여부

        Returns:
            스크립트 텍스트
        """
        lines = []

        for scene in scenes:
            if include_time:
                lines.append(f"[씬 {scene['scene_id']}] ({scene['start_time']} - {scene['end_time']})")
            else:
                lines.append(f"[씬 {scene['scene_id']}]")

            lines.append(scene['narration'])
            lines.append("")

        return '\n'.join(lines)

    @classmethod
    def get_total_duration(cls, scenes: List[Dict]) -> Tuple[float, str]:
        """
        전체 영상 길이 계산

        Returns:
            (총 초, 포맷된 문자열 "MM:SS")
        """
        if not scenes:
            return 0.0, "00:00"

        total_seconds = scenes[-1]['end_seconds']
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)

        return total_seconds, f"{minutes:02d}:{seconds:02d}"

    @classmethod
    def validate_srt(cls, content: str) -> Tuple[bool, str, int]:
        """
        SRT 내용 유효성 검사

        Returns:
            (유효 여부, 오류 메시지, 파싱된 씬 수)
        """
        try:
            scenes = cls.parse_content(content)

            if not scenes:
                return False, "파싱된 씬이 없습니다. SRT 형식을 확인하세요.", 0

            # 시간 순서 검증
            for i in range(len(scenes) - 1):
                if scenes[i]['end_seconds'] > scenes[i + 1]['start_seconds']:
                    return False, f"씬 {i + 1}과 {i + 2}의 시간이 겹칩니다.", len(scenes)

            return True, "", len(scenes)

        except Exception as e:
            return False, f"파싱 오류: {str(e)}", 0


def convert_srt_to_analysis_input(srt_scenes: List[Dict]) -> str:
    """
    SRT 씬 데이터를 씬 분석용 스크립트로 변환

    Args:
        srt_scenes: SRT 파서에서 반환된 씬 데이터

    Returns:
        씬 분석용 스크립트 텍스트
    """
    script_parts = []

    for scene in srt_scenes:
        narration = scene.get('narration', '').strip()
        if narration:
            script_parts.append(narration)

    return '\n\n'.join(script_parts)


def convert_srt_to_scene_structure(srt_scenes: List[Dict]) -> List[Dict]:
    """
    SRT 씬 데이터를 씬 분석 결과 구조로 변환
    (시간 코드 기반 씬 구분 유지)

    Args:
        srt_scenes: SRT 파서에서 반환된 씬 데이터

    Returns:
        씬 분석용 씬 구조 리스트
    """
    analysis_scenes = []

    for scene in srt_scenes:
        analysis_scene = {
            'scene_id': scene['scene_id'],
            'scene_number': scene['scene_id'],

            # 시간 정보 (SRT에서 가져옴)
            'start_time': scene['start_time'],
            'end_time': scene['end_time'],
            'start_seconds': scene['start_seconds'],
            'end_seconds': scene['end_seconds'],
            'duration': scene['duration'],
            'duration_estimate': int(scene['duration']),

            # 나레이션 (SRT 텍스트)
            'narration': scene['narration'],
            'script_text': scene['narration'],
            'char_count': len(scene['narration']),

            # 분석 대상 필드 (AI가 채울 부분)
            'image_prompt': '',
            'image_prompt_en': '',
            'character_prompt': '',
            'character_prompt_en': '',
            'visual_elements': [],
            'direction_guide': '',
            'camera_suggestion': '',
            'video_prompt_character': '',
            'video_prompt_full': '',
            'characters': [],
            'location': '',
            'mood': '',

            # 메타 정보
            'source': 'srt',
            'needs_analysis': True
        }

        analysis_scenes.append(analysis_scene)

    return analysis_scenes


def prepare_srt_for_batch_analysis(srt_scenes: List[Dict]) -> Dict:
    """
    SRT 씬들을 일괄 AI 분석용으로 준비

    Returns:
        {
            'full_script': str,          # 전체 스크립트
            'scene_structure': List,     # 씬 구조 (시간 코드 포함)
            'scene_count': int,          # 씬 수
            'total_duration': str        # 전체 길이
        }
    """
    full_script = convert_srt_to_analysis_input(srt_scenes)
    scene_structure = convert_srt_to_scene_structure(srt_scenes)
    _, total_duration = SRTParser.get_total_duration(srt_scenes)

    return {
        'full_script': full_script,
        'scene_structure': scene_structure,
        'scene_count': len(srt_scenes),
        'total_duration': total_duration
    }


# ============================================================
# 발화속도 분석기 (SRT 기반 정확 측정)
# ============================================================

class SpeakingRateAnalyzer:
    """SRT 기반 정확한 발화속도 분석기"""

    def __init__(self, scenes: List[Dict]):
        """
        Args:
            scenes: SRTParser.parse_content()의 결과
        """
        self.scenes = scenes

    def analyze(self) -> Dict:
        """
        종합 발화속도 분석

        Returns:
            분석 결과 딕셔너리
        """
        import numpy as np

        if not self.scenes:
            return self._empty_result()

        # 각 세그먼트의 발화속도 계산
        rates = []
        for scene in self.scenes:
            duration = scene.get('duration', 0)
            text = scene.get('narration', '')
            # 공백 제외 글자 수
            char_count = len(text.replace(" ", "").replace("\n", ""))

            if duration > 0.1 and char_count > 0:
                rate = char_count / duration
                rates.append({
                    'scene_id': scene.get('scene_id'),
                    'duration': duration,
                    'char_count': char_count,
                    'rate': rate,
                    'text': text[:50] + "..." if len(text) > 50 else text
                })

        if not rates:
            return self._empty_result()

        # 통계 계산
        rate_values = np.array([r['rate'] for r in rates])

        # 이상치 제거 (IQR 방식)
        q1 = np.percentile(rate_values, 25)
        q3 = np.percentile(rate_values, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        filtered_rates = rate_values[
            (rate_values >= lower_bound) & (rate_values <= upper_bound)
        ]

        if len(filtered_rates) == 0:
            filtered_rates = rate_values

        # 총 글자수와 총 발화시간
        total_chars = sum(r['char_count'] for r in rates)
        total_duration = sum(r['duration'] for r in rates)

        # 가중 평균 (긴 세그먼트에 더 가중치)
        weighted_average = total_chars / total_duration if total_duration > 0 else 0

        result = {
            "average_rate": float(np.mean(filtered_rates)),
            "weighted_average_rate": round(weighted_average, 2),
            "median_rate": float(np.median(filtered_rates)),
            "min_rate": float(np.min(filtered_rates)),
            "max_rate": float(np.max(filtered_rates)),
            "std_dev": float(np.std(filtered_rates)),
            "total_duration": round(total_duration, 2),
            "total_chars": total_chars,
            "segment_count": len(self.scenes),
            "valid_segment_count": len(filtered_rates),
            "outliers_removed": len(rate_values) - len(filtered_rates),
            "percentiles": {
                "p10": float(np.percentile(filtered_rates, 10)),
                "p25": float(np.percentile(filtered_rates, 25)),
                "p50": float(np.percentile(filtered_rates, 50)),
                "p75": float(np.percentile(filtered_rates, 75)),
                "p90": float(np.percentile(filtered_rates, 90)),
            },
            "segments": rates
        }

        print(f"[SpeakingRateAnalyzer] ⭐ 분석 완료:")
        print(f"  평균: {result['average_rate']:.2f} 글자/초")
        print(f"  가중 평균: {result['weighted_average_rate']:.2f} 글자/초")
        print(f"  중앙값: {result['median_rate']:.2f} 글자/초")
        print(f"  범위: {result['min_rate']:.2f} ~ {result['max_rate']:.2f}")
        print(f"  총 {result['segment_count']}개 세그먼트, {result['total_chars']}자")

        return result

    def _empty_result(self) -> Dict:
        return {
            "average_rate": 0.0,
            "weighted_average_rate": 0.0,
            "median_rate": 0.0,
            "min_rate": 0.0,
            "max_rate": 0.0,
            "std_dev": 0.0,
            "total_duration": 0.0,
            "total_chars": 0,
            "segment_count": 0,
            "valid_segment_count": 0,
            "outliers_removed": 0,
            "percentiles": {},
            "segments": []
        }

    def get_speed_recommendation(self, base_tts_rate: float = 8.5) -> float:
        """
        TTS speed 파라미터 추천값 계산

        Args:
            base_tts_rate: 기본 TTS 발화속도 (글자/초)

        Returns:
            추천 speed 값 (0.5 ~ 1.5)
        """
        analysis = self.analyze()

        # 가중 평균 사용 (더 정확함)
        measured_rate = analysis.get("weighted_average_rate", 6.0)

        # speed = 목표속도 / 기본속도
        speed = measured_rate / base_tts_rate

        # 범위 제한
        speed = max(0.5, min(1.5, speed))

        print(f"[SpeakingRateAnalyzer] Speed 추천: {speed:.2f}")
        print(f"  측정된 발화속도: {measured_rate:.2f} 글자/초")
        print(f"  기본 TTS 속도: {base_tts_rate:.2f} 글자/초")

        return round(speed, 2)


def analyze_speaking_rate_from_srt(srt_content: str) -> Dict:
    """
    SRT 내용에서 발화속도 분석 (헬퍼 함수)

    Args:
        srt_content: SRT 파일 내용

    Returns:
        분석 결과 딕셔너리
    """
    scenes = SRTParser.parse_content(srt_content)
    if not scenes:
        return {"error": "SRT 파싱 실패"}

    analyzer = SpeakingRateAnalyzer(scenes)
    return analyzer.analyze()


# ============================================================
# 묶음(Bundle) 씬 분석 지원
# ============================================================

def create_bundles(scenes: List[Dict], bundle_size: int = 2) -> List[Dict]:
    """
    씬 목록을 묶음 단위로 그룹화

    묶음 씬분석 기능:
    - N개의 씬을 하나의 묶음으로 그룹화
    - 묶음 내 첫 번째 씬이 대표 씬(primary)이 됨
    - AI 분석 시 묶음 단위로 분석하여 일관성 확보

    Args:
        scenes: 씬 데이터 리스트
        bundle_size: 묶음 크기 (1-5, 기본 2)

    Returns:
        묶음 메타데이터가 추가된 씬 리스트
    """
    if not scenes:
        return []

    # bundle_size 범위 제한
    bundle_size = max(1, min(5, bundle_size))

    if bundle_size <= 1:
        # 묶음 없음 (개별 분석)
        for scene in scenes:
            scene['bundle_id'] = scene['scene_id']
            scene['bundle_size'] = 1
            scene['bundle_scenes'] = [scene['scene_id']]
            scene['bundle_text'] = scene.get('narration', '')
            scene['bundle_start_time'] = scene.get('start_time', '')
            scene['bundle_end_time'] = scene.get('end_time', '')
            scene['bundle_start_seconds'] = scene.get('start_seconds', 0)
            scene['bundle_end_seconds'] = scene.get('end_seconds', 0)
            scene['bundle_duration'] = scene.get('duration', 0)
            scene['is_bundle_primary'] = True
        return scenes

    bundle_id = 1

    for i in range(0, len(scenes), bundle_size):
        bundle_scenes_list = scenes[i:i + bundle_size]

        # 묶음 정보 계산
        bundle_scene_ids = [s['scene_id'] for s in bundle_scenes_list]
        bundle_text = ' '.join([s.get('narration', '') for s in bundle_scenes_list])
        bundle_start_time = bundle_scenes_list[0].get('start_time', '')
        bundle_end_time = bundle_scenes_list[-1].get('end_time', '')
        bundle_start_seconds = bundle_scenes_list[0].get('start_seconds', 0)
        bundle_end_seconds = bundle_scenes_list[-1].get('end_seconds', 0)
        bundle_duration = bundle_end_seconds - bundle_start_seconds

        # 묶음 내 각 씬에 메타데이터 추가
        for j, scene in enumerate(bundle_scenes_list):
            scene['bundle_id'] = bundle_id
            scene['bundle_size'] = len(bundle_scenes_list)
            scene['bundle_scenes'] = bundle_scene_ids
            scene['bundle_text'] = bundle_text
            scene['bundle_start_time'] = bundle_start_time
            scene['bundle_end_time'] = bundle_end_time
            scene['bundle_start_seconds'] = bundle_start_seconds
            scene['bundle_end_seconds'] = bundle_end_seconds
            scene['bundle_duration'] = bundle_duration
            scene['is_bundle_primary'] = (j == 0)  # 첫 번째 씬이 대표

        bundle_id += 1

    total_bundles = bundle_id - 1
    print(f"[Bundle] {len(scenes)}개 씬 → {total_bundles}개 묶음 (묶음 크기: {bundle_size})")

    return scenes


def get_bundle_primary_scenes(scenes: List[Dict]) -> List[Dict]:
    """
    묶음의 대표 씬들만 반환 (AI 분석용)

    Args:
        scenes: 묶음 메타데이터가 포함된 씬 리스트

    Returns:
        대표 씬 리스트 (is_bundle_primary=True인 씬들)
    """
    return [s for s in scenes if s.get('is_bundle_primary', True)]


def apply_bundle_analysis_result(scenes: List[Dict], analyzed_primary: Dict) -> None:
    """
    대표 씬의 분석 결과를 묶음 내 모든 씬에 적용

    Args:
        scenes: 전체 씬 리스트
        analyzed_primary: 분석된 대표 씬 데이터
    """
    bundle_id = analyzed_primary.get('bundle_id')
    if bundle_id is None:
        return

    # 분석 결과 필드들
    analysis_fields = [
        'image_prompt', 'image_prompt_en',
        'character_prompt', 'character_prompt_en',
        'visual_elements', 'direction_guide',
        'camera_suggestion', 'video_prompt_character',
        'video_prompt_full', 'characters', 'location', 'mood'
    ]

    # 동일 묶음의 모든 씬에 결과 적용
    for scene in scenes:
        if scene.get('bundle_id') == bundle_id:
            for field in analysis_fields:
                if field in analyzed_primary:
                    scene[field] = analyzed_primary[field]
            scene['needs_analysis'] = False


def get_bundle_summary(scenes: List[Dict]) -> Dict:
    """
    묶음 현황 요약

    Returns:
        {
            'total_scenes': int,
            'total_bundles': int,
            'bundle_size': int,
            'bundles': [{bundle_id, scene_ids, duration, char_count}, ...]
        }
    """
    if not scenes:
        return {'total_scenes': 0, 'total_bundles': 0, 'bundle_size': 1, 'bundles': []}

    # 묶음별로 그룹화
    bundles_map = {}
    for scene in scenes:
        bid = scene.get('bundle_id', scene['scene_id'])
        if bid not in bundles_map:
            bundles_map[bid] = {
                'bundle_id': bid,
                'scene_ids': scene.get('bundle_scenes', [scene['scene_id']]),
                'duration': scene.get('bundle_duration', scene.get('duration', 0)),
                'char_count': len(scene.get('bundle_text', scene.get('narration', ''))),
                'start_time': scene.get('bundle_start_time', scene.get('start_time', '')),
                'end_time': scene.get('bundle_end_time', scene.get('end_time', '')),
            }

    bundles_list = sorted(bundles_map.values(), key=lambda x: x['bundle_id'])
    bundle_size = scenes[0].get('bundle_size', 1) if scenes else 1

    return {
        'total_scenes': len(scenes),
        'total_bundles': len(bundles_list),
        'bundle_size': bundle_size,
        'bundles': bundles_list
    }


# 헬퍼 함수들
def parse_srt_file(file_path: str, merge_short: bool = False, min_duration: float = 3.0) -> List[Dict]:
    """
    SRT 파일 파싱 (헬퍼 함수)

    Args:
        file_path: SRT 파일 경로
        merge_short: 짧은 씬 병합 여부
        min_duration: 최소 씬 길이 (초)

    Returns:
        씬 데이터 리스트
    """
    scenes = SRTParser.parse_file(file_path)

    if merge_short:
        scenes = SRTParser.merge_short_scenes(scenes, min_duration=min_duration)

    return scenes


def parse_srt_content(content: str, merge_short: bool = False, min_duration: float = 3.0) -> List[Dict]:
    """
    SRT 내용 파싱 (헬퍼 함수)

    Args:
        content: SRT 파일 내용
        merge_short: 짧은 씬 병합 여부
        min_duration: 최소 씬 길이 (초)

    Returns:
        씬 데이터 리스트
    """
    scenes = SRTParser.parse_content(content)

    if merge_short:
        scenes = SRTParser.merge_short_scenes(scenes, min_duration=min_duration)

    return scenes
