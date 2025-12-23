# -*- coding: utf-8 -*-
"""
완벽한 오디오 정규화 - 3-Pass 정규화

목표:
- 발화속도 편차: ±1% 이내
- 음량 편차: ±0.5 dB 이내
"""

import os
import io
import subprocess
import tempfile
import json
from typing import List, Dict, Tuple, Optional
from pydub import AudioSegment


class PerfectAudioNormalizer:
    """
    3-Pass 완벽 정규화

    Pass 1: 분석 (발화속도, 음량 측정)
    Pass 2: 1차 조정 (대략적 정규화)
    Pass 3: 미세 조정 (±1% 이내로 수렴)
    """

    def __init__(
        self,
        target_speech_rate: float = 8.5,  # 글자/초
        target_lufs: float = -16.0,       # LUFS (방송 표준)
        speed_tolerance: float = 0.01,    # ±1%
        lufs_tolerance: float = 0.5,      # ±0.5 dB
        max_iterations: int = 3,          # 최대 반복
        max_speed_factor: float = 1.15,   # 최대 가속 배율 (⭐ 1.2→1.15)
        min_speed_factor: float = 0.85    # 최소 감속 배율
    ):
        """
        Args:
            target_speech_rate: 목표 발화속도 (글자/초)
            target_lufs: 목표 음량 (LUFS)
            speed_tolerance: 속도 허용 오차 (1% = 0.01)
            lufs_tolerance: 음량 허용 오차 (dB)
            max_iterations: 최대 반복 횟수
            max_speed_factor: 최대 가속 배율 (기본 1.15 = 15% 가속 제한)
            min_speed_factor: 최소 감속 배율 (기본 0.85 = 15% 감속 제한)
        """
        self.target_speech_rate = target_speech_rate
        self.target_lufs = target_lufs
        self.speed_tolerance = speed_tolerance
        self.lufs_tolerance = lufs_tolerance
        self.max_iterations = max_iterations
        self.max_speed_factor = max_speed_factor
        self.min_speed_factor = min_speed_factor

        print(f"\n[PerfectNorm] 초기화")
        print(f"  목표 속도: {target_speech_rate} 글자/초 (±{speed_tolerance*100:.0f}%)")
        print(f"  목표 음량: {target_lufs} LUFS (±{lufs_tolerance} dB)")
        print(f"  속도 조정 범위: {min_speed_factor:.2f}x ~ {max_speed_factor:.2f}x")

    def normalize_all(
        self,
        scenes: List[Dict],
        progress_callback: Optional[callable] = None
    ) -> List[Dict]:
        """
        모든 씬 완벽 정규화

        Args:
            scenes: 씬 리스트 [{scene_id, text, audio_data, duration, ...}, ...]
            progress_callback: 진행 콜백 (current, total, message)

        Returns:
            정규화된 씬 리스트 (원본 구조 유지)
        """

        total = len(scenes)
        valid_scenes = [s for s in scenes if s.get("audio_data") and s.get("success")]

        if not valid_scenes:
            print("[PerfectNorm] 정규화할 오디오 없음")
            return scenes

        print(f"\n{'='*60}")
        print(f"[PerfectNorm] {len(valid_scenes)}개 씬 3-Pass 정규화 시작")
        print(f"{'='*60}")

        # Pass 1: 전체 분석
        print(f"\n[Pass 1] 전체 분석 중...")
        analysis_results = []

        for scene in valid_scenes:
            text = scene.get("text", "")
            duration = scene.get("duration", 0)
            char_count = len(text.replace(" ", "").replace("\n", ""))

            if duration > 0:
                current_rate = char_count / duration
            else:
                current_rate = 0

            # LUFS 측정
            current_lufs = self._measure_lufs(scene.get("audio_data"))

            analysis_results.append({
                "scene_id": scene.get("scene_id"),
                "current_rate": current_rate,
                "current_lufs": current_lufs,
                "char_count": char_count,
                "duration": duration
            })

            print(f"  씬 {scene.get('scene_id')}: {current_rate:.2f} 글자/초, {current_lufs:.1f} LUFS")

        # 평균 계산
        avg_rate = sum(a["current_rate"] for a in analysis_results if a["current_rate"] > 0) / len(analysis_results)
        avg_lufs = sum(a["current_lufs"] for a in analysis_results if a["current_lufs"] > -100) / len(analysis_results)

        print(f"\n[Pass 1] 평균: {avg_rate:.2f} 글자/초, {avg_lufs:.1f} LUFS")

        # Pass 2 & 3: 반복 조정
        results = list(scenes)  # 복사

        for iteration in range(1, self.max_iterations + 1):
            print(f"\n[Pass {iteration + 1}] 조정 중...")

            all_converged = True

            for idx, scene in enumerate(results):
                if not scene.get("audio_data") or not scene.get("success"):
                    continue

                scene_id = scene.get("scene_id")
                text = scene.get("text", "")
                char_count = len(text.replace(" ", "").replace("\n", ""))

                # 현재 상태 측정
                current_duration = self._get_audio_duration(scene.get("audio_data"))
                current_rate = char_count / current_duration if current_duration > 0 else 0
                current_lufs = self._measure_lufs(scene.get("audio_data"))

                # 속도 편차 확인
                rate_diff = abs(current_rate - self.target_speech_rate) / self.target_speech_rate
                lufs_diff = abs(current_lufs - self.target_lufs)

                needs_speed_adj = rate_diff > self.speed_tolerance
                needs_lufs_adj = lufs_diff > self.lufs_tolerance

                if not needs_speed_adj and not needs_lufs_adj:
                    print(f"  씬 {scene_id}: ✅ 수렴 완료 ({current_rate:.2f} 글자/초, {current_lufs:.1f} LUFS)")
                    continue

                all_converged = False

                # 조정 필요
                adjusted_audio = scene.get("audio_data")
                new_duration = current_duration

                # 속도 조정
                if needs_speed_adj and current_rate > 0:
                    atempo = self.target_speech_rate / current_rate
                    # ⭐ 속도 조정 범위 제한 (max 1.15x로 가속 제한)
                    atempo = max(self.min_speed_factor, min(self.max_speed_factor, atempo))

                    if abs(atempo - 1.0) >= 0.01:  # 1% 이상 차이
                        adjusted_audio, new_duration = self._adjust_speed(
                            adjusted_audio, atempo
                        )
                        direction = "⬆️" if atempo > 1.0 else "⬇️"
                        print(f"  씬 {scene_id}: {direction} 속도 {atempo:.3f}x ({current_rate:.2f} → {self.target_speech_rate:.2f})")

                # 음량 조정
                if needs_lufs_adj and current_lufs > -100:
                    lufs_adj = self.target_lufs - current_lufs
                    adjusted_audio = self._adjust_loudness(adjusted_audio, lufs_adj)
                    print(f"  씬 {scene_id}: 🔊 음량 {lufs_adj:+.1f} dB ({current_lufs:.1f} → {self.target_lufs:.1f})")

                # 결과 업데이트
                results[idx] = {
                    **scene,
                    "audio_data": adjusted_audio,
                    "duration": new_duration if new_duration > 0 else current_duration,
                    "normalized": True,
                    "final_speech_rate": char_count / new_duration if new_duration > 0 else current_rate
                }

                if progress_callback:
                    progress_callback(idx + 1, len(valid_scenes), f"씬 {scene_id} 정규화 중")

            if all_converged:
                print(f"\n[Pass {iteration + 1}] 모든 씬 수렴 완료!")
                break

        # 최종 결과 출력
        print(f"\n{'='*60}")
        print(f"[PerfectNorm] 정규화 완료")

        final_rates = []
        for scene in results:
            if scene.get("audio_data") and scene.get("success"):
                text = scene.get("text", "")
                char_count = len(text.replace(" ", "").replace("\n", ""))
                duration = scene.get("duration", 0)
                if duration > 0:
                    final_rates.append(char_count / duration)

        if final_rates:
            avg_final = sum(final_rates) / len(final_rates)
            variance = max(abs(r - avg_final) / avg_final for r in final_rates) if len(final_rates) > 1 else 0
            print(f"  최종 평균: {avg_final:.2f} 글자/초")
            print(f"  최대 편차: ±{variance*100:.1f}%")

        print(f"{'='*60}")

        if progress_callback:
            progress_callback(len(valid_scenes), len(valid_scenes), "정규화 완료")

        return results

    def _measure_lufs(self, audio_data: bytes) -> float:
        """LUFS 측정 (FFmpeg loudnorm)"""

        if not audio_data:
            return -100.0

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_data)
                tmp_path = tmp.name

            # FFmpeg loudnorm 분석
            cmd = [
                "ffmpeg", "-i", tmp_path,
                "-af", "loudnorm=print_format=json",
                "-f", "null", "-"
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )

            os.unlink(tmp_path)

            # JSON 파싱
            output = result.stderr
            json_start = output.rfind("{")
            json_end = output.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                loudness_info = json.loads(output[json_start:json_end])
                return float(loudness_info.get("input_i", -100))

            return -100.0

        except Exception as e:
            print(f"  ⚠️ LUFS 측정 실패: {e}")
            return -100.0

    def _get_audio_duration(self, audio_data: bytes) -> float:
        """오디오 길이 측정"""

        if not audio_data:
            return 0.0

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
            return len(audio) / 1000.0
        except:
            return 0.0

    def _adjust_speed(self, audio_data: bytes, atempo: float) -> Tuple[bytes, float]:
        """
        속도 조정 (FFmpeg atempo)

        Args:
            audio_data: 원본 오디오
            atempo: 속도 배율 (>1 = 빠르게, <1 = 느리게)

        Returns:
            (조정된 오디오, 새 길이)
        """

        if not audio_data or abs(atempo - 1.0) < 0.005:
            return audio_data, self._get_audio_duration(audio_data)

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
                tmp_in.write(audio_data)
                input_path = tmp_in.name

            output_path = input_path.replace(".wav", "_adj.wav")

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
                "ffmpeg", "-y", "-i", input_path,
                "-af", filter_str,
                "-ar", "24000",
                output_path
            ]

            subprocess.run(cmd, capture_output=True, timeout=60)

            if os.path.exists(output_path):
                with open(output_path, "rb") as f:
                    adjusted_audio = f.read()

                new_duration = self._get_audio_duration(adjusted_audio)

                os.unlink(input_path)
                os.unlink(output_path)

                return adjusted_audio, new_duration

            os.unlink(input_path)
            return audio_data, self._get_audio_duration(audio_data)

        except Exception as e:
            print(f"  ⚠️ 속도 조정 실패: {e}")
            return audio_data, self._get_audio_duration(audio_data)

    def _adjust_loudness(self, audio_data: bytes, db_change: float) -> bytes:
        """
        음량 조정

        Args:
            audio_data: 원본 오디오
            db_change: dB 변화량 (+/-)

        Returns:
            조정된 오디오
        """

        if not audio_data or abs(db_change) < 0.1:
            return audio_data

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
            adjusted = audio + db_change

            output = io.BytesIO()
            adjusted.export(output, format="wav")
            output.seek(0)

            return output.read()

        except Exception as e:
            print(f"  ⚠️ 음량 조정 실패: {e}")
            return audio_data


# ============================================================
# 간편 함수
# ============================================================

def normalize_perfect(
    scenes: List[Dict],
    target_speech_rate: float = 8.5,
    target_lufs: float = -16.0,
    max_speed_factor: float = 1.15,  # ⭐ 최대 가속 제한 (기존 1.2 → 1.15)
    progress_callback: Optional[callable] = None
) -> List[Dict]:
    """
    완벽 정규화 간편 함수

    기존 normalize_scenes_forced()와 동일한 인터페이스

    Args:
        scenes: 씬 리스트
        target_speech_rate: 목표 발화속도 (글자/초)
        target_lufs: 목표 음량 (LUFS)
        max_speed_factor: 최대 가속 배율 (기본 1.15 = SpeedCorrector 효과 보존)
        progress_callback: 진행 콜백

    Returns:
        정규화된 씬 리스트
    """

    normalizer = PerfectAudioNormalizer(
        target_speech_rate=target_speech_rate,
        target_lufs=target_lufs,
        max_speed_factor=max_speed_factor
    )

    return normalizer.normalize_all(scenes, progress_callback)
