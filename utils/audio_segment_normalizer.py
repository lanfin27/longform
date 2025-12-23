# -*- coding: utf-8 -*-
"""
구간별 발화속도 정규화

문제: TTS 모델이 긴 텍스트를 처리할 때 뒤로 갈수록 빨라짐
해결: 구간별로 분석하고 개별 정규화하여 일관된 속도 유지
"""

import os
import io
import subprocess
import tempfile
import warnings
from typing import List, Dict, Tuple, Optional
from pydub import AudioSegment
from pydub.silence import split_on_silence

warnings.filterwarnings("ignore")


class SegmentSpeedNormalizer:
    """
    구간별 발화속도 정규화

    처리 방식:
    1. 오디오를 구간별로 분할 (묵음 기준)
    2. 각 구간의 발화속도 추정
    3. 빠른 구간은 느리게, 느린 구간은 빠르게 조정
    4. 자연스럽게 합치기
    """

    def __init__(
        self,
        target_rate: float = 8.5,
        tolerance: float = 0.10,  # ±10%
        min_segment_ms: int = 300,  # 최소 구간 길이
    ):
        self.target_rate = target_rate
        self.tolerance = tolerance
        self.min_segment_ms = min_segment_ms
        self.ffmpeg_available = self._check_ffmpeg()

        print(f"\n[SegmentNorm] 초기화")
        print(f"  목표 발화속도: {target_rate} 글자/초")
        print(f"  허용 편차: ±{tolerance*100:.0f}%")

    def _check_ffmpeg(self) -> bool:
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def normalize_scene_bytes(
        self,
        audio_data: bytes,
        text: str,
        scene_id: int = 0
    ) -> Tuple[bytes, float]:
        """
        바이트 데이터로 씬 정규화

        Args:
            audio_data: WAV 바이트 데이터
            text: 씬 텍스트
            scene_id: 씬 ID

        Returns:
            (정규화된 오디오 바이트, 새 duration)
        """

        if not audio_data:
            return audio_data, 0

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
        except Exception as e:
            print(f"  [Scene {scene_id}] ❌ 오디오 로드 실패: {e}")
            return audio_data, 0

        # 전체 분석
        total_duration = len(audio) / 1000
        char_count = len(text.replace(" ", "").replace("\n", ""))

        if total_duration <= 0 or char_count <= 0:
            return audio_data, total_duration

        overall_rate = char_count / total_duration

        print(f"\n[SegmentNorm] 씬 {scene_id}")
        print(f"  전체: {char_count}자, {total_duration:.2f}초, {overall_rate:.2f} 글자/초")

        # 구간 분할
        segments = self._split_into_segments(audio)

        if len(segments) < 2:
            # 구간 분할 불가 시 전체 정규화만
            normalized_audio = self._normalize_whole_audio(audio, overall_rate)
            output = io.BytesIO()
            normalized_audio.export(output, format="wav", parameters=["-ar", "24000", "-ac", "1"])
            output.seek(0)
            new_duration = len(normalized_audio) / 1000
            return output.read(), new_duration

        print(f"  {len(segments)}개 구간 분할")

        # 구간별 속도 분석 (비율 기반 추정)
        segment_analysis = self._analyze_segments(segments, text)

        # 구간별 속도 편차 확인
        rates = [s["estimated_rate"] for s in segment_analysis if s["estimated_rate"] > 0]

        if rates:
            min_rate = min(rates)
            max_rate = max(rates)
            rate_mean = sum(rates) / len(rates)
            rate_range = (max_rate - min_rate) / rate_mean if rate_mean > 0 else 0

            print(f"  구간별 속도: {min_rate:.2f} ~ {max_rate:.2f} (평균: {rate_mean:.2f})")

            # 편차가 크면 구간별 정규화
            if rate_range > 0.15:  # 15% 이상 편차
                print(f"  🔧 구간별 정규화 적용 (편차: {rate_range*100:.1f}%)")
                normalized_segments = self._normalize_segments(segment_analysis)
                audio = self._merge_segments(normalized_segments)
            else:
                print(f"  ✅ 편차 양호, 전체 정규화만")
                audio = self._normalize_whole_audio(audio, overall_rate)

        # 최종 결과
        output = io.BytesIO()
        audio.export(output, format="wav", parameters=["-ar", "24000", "-ac", "1"])
        output.seek(0)

        new_duration = len(audio) / 1000
        new_rate = char_count / new_duration if new_duration > 0 else 0
        print(f"  → 결과: {new_rate:.2f} 글자/초 ({new_duration:.2f}초)")

        return output.read(), new_duration

    def _split_into_segments(self, audio: AudioSegment) -> List[AudioSegment]:
        """묵음 기준으로 구간 분할"""

        try:
            # 묵음 기준 분할
            segments = split_on_silence(
                audio,
                min_silence_len=150,  # 150ms 이상 묵음
                silence_thresh=-40,   # -40dB 이하를 묵음으로
                keep_silence=80       # 앞뒤 80ms 유지
            )

            if not segments:
                return [audio]

            # 너무 짧은 구간 병합
            merged = []
            current = None

            for seg in segments:
                if current is None:
                    current = seg
                elif len(current) < self.min_segment_ms:
                    current = current + seg
                else:
                    merged.append(current)
                    current = seg

            if current is not None:
                merged.append(current)

            return merged if merged else [audio]

        except Exception as e:
            print(f"  ⚠️ 구간 분할 오류: {e}")
            return [audio]

    def _analyze_segments(
        self,
        segments: List[AudioSegment],
        text: str
    ) -> List[Dict]:
        """구간별 분석 (비율 기반 추정)"""

        analysis = []
        total_duration = sum(len(s) for s in segments) / 1000
        char_count = len(text.replace(" ", "").replace("\n", ""))

        for idx, seg in enumerate(segments):
            seg_duration = len(seg) / 1000
            seg_ratio = seg_duration / total_duration if total_duration > 0 else 0
            estimated_chars = int(char_count * seg_ratio)
            estimated_rate = estimated_chars / seg_duration if seg_duration > 0 else 0

            analysis.append({
                "index": idx,
                "segment": seg,
                "duration": seg_duration,
                "estimated_chars": estimated_chars,
                "estimated_rate": estimated_rate,
            })

        return analysis

    def _normalize_segments(self, segment_analysis: List[Dict]) -> List[AudioSegment]:
        """구간별 속도 정규화"""

        normalized = []

        for item in segment_analysis:
            seg = item["segment"]
            current_rate = item["estimated_rate"]

            if current_rate <= 0:
                normalized.append(seg)
                continue

            # 목표 속도와의 비율
            atempo = self.target_rate / current_rate
            atempo = max(0.85, min(1.20, atempo))  # ±20% 제한

            # 8% 이상 차이날 때만 조정
            if abs(atempo - 1.0) >= 0.08:
                direction = "⬆️" if atempo > 1.0 else "⬇️"
                print(f"    구간 {item['index']+1}: {direction} {atempo:.2f}x")
                seg = self._apply_atempo(seg, atempo)

            normalized.append(seg)

        return normalized

    def _normalize_whole_audio(self, audio: AudioSegment, current_rate: float) -> AudioSegment:
        """전체 오디오 속도 정규화"""

        if current_rate <= 0:
            return audio

        atempo = self.target_rate / current_rate
        atempo = max(0.85, min(1.20, atempo))

        if abs(atempo - 1.0) >= 0.05:
            direction = "⬆️ 빠르게" if atempo > 1.0 else "⬇️ 느리게"
            print(f"  전체 조정: {direction} ({atempo:.2f}x)")
            return self._apply_atempo(audio, atempo)

        return audio

    def _apply_atempo(self, audio: AudioSegment, atempo: float) -> AudioSegment:
        """FFmpeg atempo 적용"""

        if not self.ffmpeg_available or abs(atempo - 1.0) < 0.01:
            return audio

        try:
            temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

            audio.export(temp_in, format="wav")

            # atempo 체이닝 (범위 제한: 0.5~2.0)
            atempo_filters = []
            remaining = atempo

            while remaining > 2.0:
                atempo_filters.append("atempo=2.0")
                remaining /= 2.0
            while remaining < 0.5:
                atempo_filters.append("atempo=0.5")
                remaining /= 0.5

            atempo_filters.append(f"atempo={remaining:.4f}")
            filter_str = ",".join(atempo_filters)

            cmd = [
                "ffmpeg", "-y", "-i", temp_in,
                "-af", filter_str,
                "-ar", "24000", "-ac", "1",
                temp_out
            ]

            subprocess.run(cmd, capture_output=True, timeout=30)

            if os.path.exists(temp_out):
                result = AudioSegment.from_file(temp_out)
            else:
                result = audio

            for f in [temp_in, temp_out]:
                try:
                    os.remove(f)
                except:
                    pass

            return result

        except Exception as e:
            print(f"  ⚠️ atempo 적용 실패: {e}")
            return audio

    def _merge_segments(self, segments: List[AudioSegment]) -> AudioSegment:
        """구간 합치기 (크로스페이드)"""

        if not segments:
            return AudioSegment.empty()

        result = segments[0]

        for seg in segments[1:]:
            # 15ms 크로스페이드로 자연스럽게 연결
            if len(result) > 15 and len(seg) > 15:
                result = result.append(seg, crossfade=15)
            else:
                result = result + seg

        return result


# ============================================================
# 전체 씬 처리 함수
# ============================================================

def normalize_segments_all(
    scenes: List[Dict],
    target_rate: float = 8.5,
    progress_callback: Optional[callable] = None
) -> List[Dict]:
    """
    모든 씬의 구간별 속도 정규화

    Args:
        scenes: 씬 리스트 [{scene_id, text, audio_data, ...}, ...]
        target_rate: 목표 발화속도 (글자/초)
        progress_callback: 진행 콜백

    Returns:
        정규화된 씬 리스트
    """

    normalizer = SegmentSpeedNormalizer(
        target_rate=target_rate,
        tolerance=0.10
    )

    results = []
    total = len(scenes)
    valid_scenes = [s for s in scenes if s.get("audio_data") and s.get("success")]

    if not valid_scenes:
        print("[SegmentNorm] 정규화할 씬 없음")
        return scenes

    print(f"\n{'='*60}")
    print(f"[SegmentNorm] {len(valid_scenes)}개 씬 구간별 정규화 시작")
    print(f"{'='*60}")

    for idx, scene in enumerate(scenes):
        if progress_callback:
            progress_callback(idx, total, f"구간 정규화: 씬 {scene.get('scene_id', idx+1)}")

        # 오디오가 없거나 실패한 씬은 그대로 유지
        if not scene.get("audio_data") or not scene.get("success"):
            results.append(scene)
            continue

        text = scene.get("text", "")
        scene_id = scene.get("scene_id", idx + 1)

        # 구간별 정규화
        normalized_audio, new_duration = normalizer.normalize_scene_bytes(
            scene.get("audio_data"),
            text,
            scene_id
        )

        results.append({
            **scene,
            "audio_data": normalized_audio,
            "duration": new_duration,
            "segment_normalized": True
        })

    print(f"\n{'='*60}")
    print(f"[SegmentNorm] 완료!")
    print(f"{'='*60}")

    if progress_callback:
        progress_callback(total, total, "구간 정규화 완료")

    return results
