# -*- coding: utf-8 -*-
"""
오디오 유틸리티 - librosa 없이 pydub만 사용

파형 시각화 기능은 제거됨 (불필요)
간단한 구간 추출 및 길이 확인 기능만 제공
"""
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Dict
from pydub import AudioSegment


class WaveformVisualizer:
    """간단한 오디오 유틸리티 (파형 시각화 제거됨, librosa 불필요)"""

    def __init__(self):
        print("[WaveformVisualizer] 초기화 (pydub 모드)")

    def get_audio_duration(self, audio_path: str) -> float:
        """
        오디오 길이 반환 (초)
        librosa 대신 pydub 사용
        """
        try:
            audio = AudioSegment.from_file(audio_path)
            duration = len(audio) / 1000.0  # 밀리초 → 초
            return duration
        except Exception as e:
            print(f"[WaveformVisualizer] 오디오 길이 확인 실패: {e}")
            return 0.0

    def load_audio(self, audio_path: str) -> Tuple[Optional[AudioSegment], Optional[int]]:
        """
        오디오 로드 - pydub 사용
        반환: (AudioSegment, sample_rate)
        """
        try:
            audio = AudioSegment.from_file(audio_path)
            return audio, audio.frame_rate
        except Exception as e:
            print(f"[WaveformVisualizer] 오디오 로드 실패: {e}")
            return None, None

    def extract_segment(
        self,
        audio_path: str,
        start_sec: float,
        end_sec: float,
        output_path: str = None
    ) -> Optional[str]:
        """
        오디오 구간 추출

        Args:
            audio_path: 원본 오디오 경로
            start_sec: 시작 시간 (초)
            end_sec: 끝 시간 (초)
            output_path: 출력 경로 (None이면 임시 파일)

        Returns:
            출력 파일 경로
        """
        try:
            audio = AudioSegment.from_file(audio_path)
            start_ms = int(start_sec * 1000)
            end_ms = int(end_sec * 1000)
            segment = audio[start_ms:end_ms]

            if output_path is None:
                output_path = os.path.join(
                    tempfile.gettempdir(),
                    f"segment_{int(start_sec)}_{int(end_sec)}.mp3"
                )

            segment.export(output_path, format="mp3", bitrate="192k")
            return output_path

        except Exception as e:
            print(f"[WaveformVisualizer] 구간 추출 실패: {e}")
            return None

    def analyze_segment_quality(
        self,
        audio_path: str,
        start_sec: float,
        end_sec: float
    ) -> Dict:
        """
        선택 구간의 간단한 품질 분석 (pydub 기반)

        Returns:
            품질 분석 결과
        """
        try:
            audio = AudioSegment.from_file(audio_path)
            start_ms = int(start_sec * 1000)
            end_ms = int(end_sec * 1000)
            segment = audio[start_ms:end_ms]

            duration = (end_sec - start_sec)
            dBFS = segment.dBFS

            # 간단한 품질 점수 계산
            quality_score = 100
            warnings = []

            # 음량 기반 점수
            if dBFS < -40:
                quality_score -= 30
                warnings.append("음성이 너무 작습니다")
            elif dBFS < -30:
                quality_score -= 15
                warnings.append("음성이 다소 작습니다")
            elif dBFS > -5:
                quality_score -= 20
                warnings.append("음성이 너무 큽니다 (클리핑 위험)")

            # 길이 기반 점수
            if duration < 10:
                quality_score -= 20
                warnings.append("구간이 너무 짧습니다 (10초 이상 권장)")
            elif duration < 15:
                quality_score -= 10
                warnings.append("구간이 다소 짧습니다 (15초 이상 권장)")
            elif duration > 30:
                quality_score -= 10
                warnings.append("구간이 너무 깁니다 (30초 이하 권장)")

            quality_score = max(0, min(100, quality_score))

            return {
                "duration": duration,
                "dBFS": dBFS,
                "quality_score": quality_score,
                "warnings": warnings if warnings else ["품질 양호"]
            }

        except Exception as e:
            print(f"[WaveformVisualizer] 품질 분석 실패: {e}")
            return {
                "duration": 0,
                "dBFS": -100,
                "quality_score": 0,
                "warnings": [f"분석 실패: {e}"]
            }

    def create_waveform_plot(self, *args, **kwargs):
        """파형 이미지 생성 - 비활성화됨 (librosa 필요)"""
        print("[WaveformVisualizer] ⚠️ 파형 시각화는 비활성화되었습니다.")
        return None

    def extract_segment_audio(
        self,
        audio_path: str,
        start_sec: float,
        end_sec: float,
        output_path: Optional[str] = None,
        normalize: bool = True,
        noise_reduce: bool = False  # 무시됨 (librosa 필요)
    ) -> Optional[str]:
        """
        선택 구간을 새 파일로 추출 (기존 호환성 유지)

        Args:
            audio_path: 원본 오디오 경로
            start_sec: 시작 시간(초)
            end_sec: 끝 시간(초)
            output_path: 출력 경로 (None이면 자동 생성)
            normalize: 정규화 여부
            noise_reduce: 무시됨 (librosa 필요)

        Returns:
            저장된 파일 경로
        """
        try:
            import time

            audio = AudioSegment.from_file(audio_path)

            # 구간 추출 (밀리초)
            start_ms = int(start_sec * 1000)
            end_ms = int(end_sec * 1000)
            segment = audio[start_ms:end_ms]

            # 정규화
            if normalize:
                target_dBFS = -20.0
                change_in_dBFS = target_dBFS - segment.dBFS
                segment = segment.apply_gain(change_in_dBFS)

            # 출력 경로 생성
            if output_path is None:
                input_path = Path(audio_path)
                timestamp = int(time.time() * 1000)
                output_path = str(input_path.parent / f"{input_path.stem}_manual_{timestamp}.wav")

            # 저장
            segment.export(output_path, format="wav")

            return output_path

        except Exception as e:
            print(f"[WaveformVisualizer] 구간 추출 실패: {e}")
            return None

    def clear_cache(self):
        """캐시 클리어 (호환성)"""
        pass


# 싱글톤 인스턴스
_visualizer_instance: Optional[WaveformVisualizer] = None


def get_waveform_visualizer() -> WaveformVisualizer:
    """WaveformVisualizer 싱글톤 인스턴스 반환"""
    global _visualizer_instance
    if _visualizer_instance is None:
        _visualizer_instance = WaveformVisualizer()
    return _visualizer_instance
