# -*- coding: utf-8 -*-
"""
오디오 전처리 모듈 (v2.0)

Whisper 음성 인식 누락 방지를 위한 오디오 전처리

기능:
1. 볼륨 정규화 - 전체 볼륨을 일관되게 조정
2. 다이나믹 레인지 압축 - 작은 소리 증폭
3. 구간별 볼륨 분석 - 저볼륨 구간 감지
4. 무음 구간 감지 - pydub silence detection
5. Whisper 인식률 향상을 위한 오디오 향상

v2.0 변경사항:
- Whisper v6.5와 연동 강화
- 극단적 VAD 민감도 지원
- 저볼륨 구간 자동 증폭
"""

import os
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class AudioSegmentInfo:
    """오디오 구간 정보"""
    start: float
    end: float
    volume_db: float
    is_speech: bool


class AudioPreprocessor:
    """
    오디오 전처리 클래스

    Whisper가 놓칠 수 있는 저볼륨 구간을 감지하고
    오디오를 향상시켜 인식률을 높입니다.
    """

    # 무음 판단 임계값 (dBFS)
    SILENCE_THRESHOLD_DB = -40

    # 저볼륨 판단 임계값 (dBFS)
    LOW_VOLUME_THRESHOLD_DB = -35

    def __init__(self, silence_threshold_db: float = -40,
                 low_volume_threshold_db: float = -35):
        """
        초기화

        Args:
            silence_threshold_db: 무음 판단 임계값 (기본: -40dB)
            low_volume_threshold_db: 저볼륨 판단 임계값 (기본: -35dB)
        """
        self.silence_threshold_db = silence_threshold_db
        self.low_volume_threshold_db = low_volume_threshold_db
        print(f"[AudioPreprocessor v2.0] 초기화")
        print(f"[AudioPreprocessor v2.0]   무음 임계값: {silence_threshold_db}dB")
        print(f"[AudioPreprocessor v2.0]   저볼륨 임계값: {low_volume_threshold_db}dB")

    def analyze_volume(self, audio_path: str,
                       segment_duration: float = 1.0) -> List[AudioSegmentInfo]:
        """
        구간별 볼륨 분석

        오디오 파일을 일정 구간으로 나누어 각 구간의
        볼륨(dBFS)을 측정합니다.

        Args:
            audio_path: 오디오 파일 경로
            segment_duration: 분석 구간 길이 (초, 기본: 1초)

        Returns:
            각 구간의 볼륨 정보 리스트
        """
        from pydub import AudioSegment

        print(f"[AudioPreprocessor] 볼륨 분석 시작: {Path(audio_path).name}")

        audio = AudioSegment.from_file(audio_path)
        duration_ms = len(audio)
        segment_ms = int(segment_duration * 1000)

        result = []

        for start_ms in range(0, duration_ms, segment_ms):
            end_ms = min(start_ms + segment_ms, duration_ms)
            segment = audio[start_ms:end_ms]

            # dBFS (데시벨 풀스케일)
            volume_db = segment.dBFS

            # 무음 판단: silence_threshold_db 이하는 무음
            is_speech = volume_db > self.silence_threshold_db

            result.append(AudioSegmentInfo(
                start=start_ms / 1000,
                end=end_ms / 1000,
                volume_db=volume_db,
                is_speech=is_speech
            ))

        speech_count = sum(1 for s in result if s.is_speech)
        silence_count = len(result) - speech_count

        print(f"[AudioPreprocessor] 분석 완료:")
        print(f"  총 구간: {len(result)}개 ({segment_duration}초 단위)")
        print(f"  음성 구간: {speech_count}개")
        print(f"  무음 구간: {silence_count}개")

        return result

    def find_low_volume_gaps(self, audio_path: str,
                             threshold_db: float = None,
                             min_gap_seconds: float = 3.0) -> List[Tuple[float, float]]:
        """
        저볼륨 구간 찾기 (Whisper가 놓칠 수 있는 구간)

        연속된 저볼륨 구간을 찾아 반환합니다.
        이 구간들은 Whisper가 무음으로 오판할 가능성이 높습니다.

        Args:
            audio_path: 오디오 파일 경로
            threshold_db: 저볼륨 판단 임계값 (기본: 클래스 설정값)
            min_gap_seconds: 최소 갭 길이 (초, 기본: 3초)

        Returns:
            (시작, 끝) 튜플 리스트
        """
        if threshold_db is None:
            threshold_db = self.low_volume_threshold_db

        print(f"[AudioPreprocessor] 저볼륨 구간 탐색: threshold={threshold_db}dB, min_gap={min_gap_seconds}초")

        # 더 세밀하게 분석 (0.5초 단위)
        segments = self.analyze_volume(audio_path, segment_duration=0.5)

        gaps = []
        gap_start = None

        for seg in segments:
            if seg.volume_db < threshold_db:
                if gap_start is None:
                    gap_start = seg.start
            else:
                if gap_start is not None:
                    gap_end = seg.start
                    gap_duration = gap_end - gap_start

                    if gap_duration >= min_gap_seconds:
                        gaps.append((gap_start, gap_end))
                        print(f"  발견: {gap_start:.1f}초 ~ {gap_end:.1f}초 ({gap_duration:.1f}초)")

                    gap_start = None

        # 마지막 갭 처리
        if gap_start is not None:
            gap_end = segments[-1].end
            if gap_end - gap_start >= min_gap_seconds:
                gaps.append((gap_start, gap_end))
                print(f"  발견: {gap_start:.1f}초 ~ {gap_end:.1f}초 ({gap_end - gap_start:.1f}초)")

        print(f"[AudioPreprocessor] 총 {len(gaps)}개 저볼륨 구간 발견")

        return gaps

    def normalize_and_enhance(self, audio_path: str,
                              output_path: str = None,
                              target_db: float = -14.0) -> str:
        """
        오디오 정규화 및 향상

        Whisper 인식률을 높이기 위해 오디오를 전처리합니다:
        1. 볼륨 정규화 (목표 볼륨으로 조정)
        2. 다이나믹 레인지 압축 (작은 소리 증폭)
        3. 노이즈 게이트 적용 (선택적)

        Args:
            audio_path: 입력 오디오 파일 경로
            output_path: 출력 파일 경로 (기본: 입력파일_enhanced.wav)
            target_db: 목표 볼륨 (dBFS, 기본: -14dB)

        Returns:
            처리된 오디오 파일 경로
        """
        from pydub import AudioSegment
        from pydub.effects import normalize, compress_dynamic_range

        print(f"[AudioPreprocessor] 오디오 향상 시작: {Path(audio_path).name}")

        audio = AudioSegment.from_file(audio_path)
        original_db = audio.dBFS

        print(f"  원본 볼륨: {original_db:.1f}dB")

        # 1. 전체 볼륨 정규화
        audio = normalize(audio)
        normalized_db = audio.dBFS
        print(f"  정규화 후 볼륨: {normalized_db:.1f}dB")

        # 2. 다이나믹 레인지 압축 (작은 소리 증폭)
        try:
            audio = compress_dynamic_range(
                audio,
                threshold=-25.0,   # -25dB 이하 신호 압축
                ratio=3.0,         # 압축 비율
                attack=5.0,        # ms
                release=50.0       # ms
            )
            print(f"  다이나믹 압축 적용 완료")
        except Exception as e:
            print(f"  다이나믹 압축 스킵: {e}")

        # 3. 목표 볼륨으로 조정
        current_db = audio.dBFS
        if current_db < target_db:
            gain = target_db - current_db
            audio = audio + gain
            print(f"  볼륨 조정: +{gain:.1f}dB → {audio.dBFS:.1f}dB")

        # 출력 경로 결정
        if output_path is None:
            base = Path(audio_path)
            output_path = str(base.parent / f"{base.stem}_enhanced.wav")

        # WAV로 저장 (Whisper 호환성 최적)
        if not output_path.endswith('.wav'):
            output_path = output_path.rsplit('.', 1)[0] + '.wav'

        audio.export(output_path, format="wav")

        print(f"[AudioPreprocessor] ✅ 향상된 오디오 저장: {output_path}")

        return output_path

    def enhance_segment(self, audio_path: str,
                        start_time: float, end_time: float,
                        output_path: str = None) -> str:
        """
        특정 구간만 향상

        전체 오디오에서 특정 구간만 추출하여 향상시킵니다.
        저볼륨으로 감지된 구간에 적용하면 좋습니다.

        Args:
            audio_path: 입력 오디오 파일 경로
            start_time: 시작 시간 (초)
            end_time: 종료 시간 (초)
            output_path: 출력 파일 경로

        Returns:
            향상된 구간 오디오 파일 경로
        """
        from pydub import AudioSegment
        from pydub.effects import normalize, compress_dynamic_range

        print(f"[AudioPreprocessor] 구간 향상: {start_time:.1f}초 ~ {end_time:.1f}초")

        audio = AudioSegment.from_file(audio_path)

        # 구간 추출 (밀리초)
        start_ms = int(start_time * 1000)
        end_ms = int(end_time * 1000)

        # 약간의 여유 추가
        start_ms = max(0, start_ms - 500)
        end_ms = min(len(audio), end_ms + 500)

        segment = audio[start_ms:end_ms]

        original_db = segment.dBFS
        print(f"  원본 볼륨: {original_db:.1f}dB")

        # 정규화
        segment = normalize(segment)

        # 다이나믹 압축 (더 강하게)
        try:
            segment = compress_dynamic_range(
                segment,
                threshold=-20.0,   # 더 적극적인 압축
                ratio=4.0,
                attack=5.0,
                release=50.0
            )
        except:
            pass

        # 출력 경로
        if output_path is None:
            import tempfile
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(
                temp_dir,
                f"enhanced_{start_time:.0f}_{end_time:.0f}.wav"
            )

        segment.export(output_path, format="wav")

        print(f"  향상 후 볼륨: {segment.dBFS:.1f}dB")
        print(f"[AudioPreprocessor] ✅ 구간 향상 완료: {output_path}")

        return output_path

    def get_audio_duration(self, audio_path: str) -> float:
        """
        오디오 길이 반환

        Args:
            audio_path: 오디오 파일 경로

        Returns:
            길이 (초)
        """
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)
        return len(audio) / 1000.0

    def get_audio_info(self, audio_path: str) -> dict:
        """
        오디오 정보 반환

        Args:
            audio_path: 오디오 파일 경로

        Returns:
            정보 딕셔너리
        """
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)

        return {
            'duration': len(audio) / 1000.0,
            'duration_str': f"{len(audio) // 60000}:{(len(audio) // 1000) % 60:02d}",
            'channels': audio.channels,
            'sample_width': audio.sample_width,
            'frame_rate': audio.frame_rate,
            'frame_count': len(audio.get_array_of_samples()),
            'volume_db': audio.dBFS
        }

    def detect_silence_regions(self, audio_path: str,
                               silence_threshold_db: float = None,
                               min_silence_ms: int = 1000) -> List[Tuple[float, float]]:
        """
        무음 구간 감지

        Args:
            audio_path: 오디오 파일 경로
            silence_threshold_db: 무음 임계값 (기본: 클래스 설정값)
            min_silence_ms: 최소 무음 길이 (밀리초, 기본: 1000ms)

        Returns:
            무음 구간 리스트 [(시작초, 끝초), ...]
        """
        from pydub import AudioSegment
        from pydub.silence import detect_silence

        if silence_threshold_db is None:
            silence_threshold_db = self.silence_threshold_db

        print(f"[AudioPreprocessor] 무음 구간 감지: threshold={silence_threshold_db}dB")

        audio = AudioSegment.from_file(audio_path)

        # pydub의 detect_silence 사용
        silence_ranges = detect_silence(
            audio,
            min_silence_len=min_silence_ms,
            silence_thresh=silence_threshold_db
        )

        # 밀리초 → 초로 변환
        result = [(start / 1000, end / 1000) for start, end in silence_ranges]

        print(f"[AudioPreprocessor] {len(result)}개 무음 구간 발견")

        return result


# ============================================================
# 팩토리 함수
# ============================================================

def get_audio_preprocessor(silence_threshold_db: float = -40,
                           low_volume_threshold_db: float = -35) -> AudioPreprocessor:
    """
    AudioPreprocessor 인스턴스 생성

    Args:
        silence_threshold_db: 무음 판단 임계값
        low_volume_threshold_db: 저볼륨 판단 임계값

    Returns:
        AudioPreprocessor 인스턴스
    """
    return AudioPreprocessor(
        silence_threshold_db=silence_threshold_db,
        low_volume_threshold_db=low_volume_threshold_db
    )


# ============================================================
# 유틸리티 함수
# ============================================================

def analyze_audio_for_whisper(audio_path: str) -> dict:
    """
    Whisper 분석 전 오디오 상태 점검

    오디오 파일을 분석하여 Whisper가 문제를 겪을 수 있는
    구간을 미리 파악합니다.

    Args:
        audio_path: 오디오 파일 경로

    Returns:
        분석 결과 딕셔너리
    """
    preprocessor = AudioPreprocessor()

    # 기본 정보
    info = preprocessor.get_audio_info(audio_path)

    # 저볼륨 구간 찾기
    low_volume_gaps = preprocessor.find_low_volume_gaps(audio_path)

    # 무음 구간 찾기
    silence_regions = preprocessor.detect_silence_regions(audio_path)

    return {
        'info': info,
        'low_volume_gaps': low_volume_gaps,
        'silence_regions': silence_regions,
        'has_potential_issues': len(low_volume_gaps) > 0,
        'recommendation': (
            "오디오 향상 권장" if len(low_volume_gaps) > 0
            else "오디오 상태 양호"
        )
    }


def preprocess_audio_for_whisper(audio_path: str,
                                 output_path: str = None) -> Tuple[str, dict]:
    """
    Whisper 분석을 위한 오디오 전처리

    오디오를 분석하고 필요시 향상시킵니다.

    Args:
        audio_path: 입력 오디오 파일 경로
        output_path: 출력 파일 경로 (기본: 자동 생성)

    Returns:
        (처리된 파일 경로, 분석 결과)
    """
    preprocessor = AudioPreprocessor()

    # 분석
    analysis = analyze_audio_for_whisper(audio_path)

    # 문제가 있으면 향상
    if analysis['has_potential_issues']:
        print(f"\n[AudioPreprocessor] ⚠️ 저볼륨 구간 감지됨 - 오디오 향상 진행")
        enhanced_path = preprocessor.normalize_and_enhance(audio_path, output_path)
        analysis['enhanced_path'] = enhanced_path
        analysis['was_enhanced'] = True
        return enhanced_path, analysis
    else:
        analysis['was_enhanced'] = False
        return audio_path, analysis
