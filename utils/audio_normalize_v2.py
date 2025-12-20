# -*- coding: utf-8 -*-
"""
오디오 정규화 V2 - 정밀 일관성 버전

목표:
- 발화속도 편차: ±3% 이내
- 음량 편차: ±2dB 이내
"""

import os
import io
import tempfile
import subprocess
from typing import List, Dict, Tuple, Optional, Callable
import numpy as np

try:
    from pydub import AudioSegment
    from pydub.effects import normalize
    from pydub.silence import detect_leading_silence
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("[AudioNormalizer] Warning: pydub not installed")


def _check_ffmpeg():
    """FFmpeg 사용 가능 여부 확인"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


class AudioNormalizer:
    """
    완전한 오디오 정규화 클래스

    기능:
    - 발화속도 분석 및 조정 (FFmpeg atempo)
    - 음량 정규화 (RMS/LUFS)
    - 무음 표준화
    - 피크 리미팅
    """

    def __init__(
        self,
        target_rate: Optional[float] = None,
        target_dbfs: float = -20.0,
        max_speed_adjust: float = 0.12,
        silence_ms: Tuple[int, int] = (80, 80)
    ):
        """
        Args:
            target_rate: 목표 발화속도 (글자/초). None이면 자동 계산
            target_dbfs: 목표 음량 (dBFS)
            max_speed_adjust: 최대 속도 조정 비율 (0.12 = ±12%)
            silence_ms: (앞 무음, 뒤 무음) 밀리초
        """
        self.target_rate = target_rate
        self.target_dbfs = target_dbfs
        self.max_speed_adjust = max_speed_adjust
        self.silence_ms = silence_ms
        self.ffmpeg_available = _check_ffmpeg()

    def normalize_all(
        self,
        scenes: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """
        모든 씬 일괄 정규화

        Args:
            scenes: 씬 리스트 (audio_data 포함)
            progress_callback: (current, total, message) 콜백

        Returns:
            정규화된 씬 리스트
        """

        if not PYDUB_AVAILABLE:
            print("[Normalizer] pydub 미설치 - 정규화 스킵")
            return scenes

        print("\n" + "=" * 60)
        print("[Normalizer] 완전 정규화 시작")
        print("=" * 60)

        # 1단계: 분석
        print("\n[Step 1] 씬 분석")
        analysis = self._analyze_scenes(scenes)

        if not analysis:
            print("[Normalizer] 분석할 씬 없음")
            return scenes

        # 2단계: 목표값 계산
        print("\n[Step 2] 목표값 계산")
        target_rate = self._calculate_target_rate(analysis)

        # 3단계: 정규화 적용
        print("\n[Step 3] 정규화 적용")
        normalized = self._apply_normalization(analysis, target_rate, progress_callback)

        # 4단계: 결과 검증
        print("\n[Step 4] 결과 검증")
        self._verify_results(normalized)

        # 원본 scenes에 결과 반영
        result_map = {n["scene_id"]: n for n in normalized}
        for scene in scenes:
            scene_id = scene.get("scene_id")
            if scene_id in result_map:
                norm_data = result_map[scene_id]
                scene["audio_data"] = norm_data.get("audio_data", scene.get("audio_data"))
                scene["final_duration"] = norm_data.get("final_duration")
                scene["final_rate"] = norm_data.get("final_rate")
                scene["final_dbfs"] = norm_data.get("final_dbfs")
                scene["speed_adjusted"] = norm_data.get("speed_adjusted", False)
                scene["volume_change"] = norm_data.get("volume_change", 0)
                scene["normalized"] = True

        print("\n" + "=" * 60)
        print("[Normalizer] 정규화 완료")
        print("=" * 60)

        return scenes

    def _analyze_scenes(self, scenes: List[Dict]) -> List[Dict]:
        """씬 분석"""

        analysis = []

        for scene in scenes:
            if not scene.get("success") or not scene.get("audio_data"):
                continue

            audio_data = scene.get("audio_data")
            if not audio_data:
                continue

            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
                duration = len(audio) / 1000
                text = scene.get("text", "")
                char_count = len(text.replace(" ", "").replace("\n", ""))

                rate = char_count / duration if duration > 0 else 0
                dbfs = audio.dBFS if audio.dBFS != float('-inf') else -60

                analysis.append({
                    **scene,
                    "audio": audio,
                    "original_duration": duration,
                    "char_count": char_count,
                    "rate": rate,
                    "dbfs": dbfs
                })

                print(f"  씬 {scene['scene_id']}: {rate:.2f} 글자/초, {dbfs:.1f} dBFS, {duration:.2f}초")

            except Exception as e:
                print(f"  씬 {scene.get('scene_id', '?')}: 분석 실패 - {e}")

        return analysis

    def _calculate_target_rate(self, analysis: List[Dict]) -> float:
        """목표 발화속도 계산 (중간값 사용)"""

        rates = [a["rate"] for a in analysis if a["rate"] > 0]

        if not rates:
            return 9.0  # 기본값

        if self.target_rate:
            target = self.target_rate
        else:
            # 중간값 사용 (이상치 영향 최소화)
            target = float(np.median(rates))

        rate_range = max(rates) - min(rates)
        rate_mean = np.mean(rates)
        current_deviation = (rate_range / 2 / rate_mean * 100) if rate_mean > 0 else 0

        print(f"  현재 범위: {min(rates):.2f} ~ {max(rates):.2f} 글자/초")
        print(f"  현재 편차: ±{current_deviation:.1f}%")
        print(f"  목표 속도: {target:.2f} 글자/초")
        print(f"  목표 편차: ±3% 이내")

        return target

    def _apply_normalization(
        self,
        analysis: List[Dict],
        target_rate: float,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """정규화 적용"""

        results = []
        total = len(analysis)

        for idx, item in enumerate(analysis):
            scene_id = item["scene_id"]

            if progress_callback:
                progress_callback(idx, total, f"씬 {scene_id} 정규화 중...")

            print(f"\n  [씬 {scene_id}]")

            audio = item["audio"]
            current_rate = item["rate"]
            char_count = item["char_count"]

            speed_adjusted = False
            volume_change = 0.0

            # 1. 속도 조정
            if current_rate > 0 and target_rate > 0:
                audio, speed_adjusted = self._adjust_speed(
                    audio, current_rate, target_rate
                )

            # 2. 무음 표준화
            audio = self._standardize_silence(audio)

            # 3. 음량 정규화
            audio, volume_change = self._normalize_volume(audio)

            # 4. 피크 제한
            audio = normalize(audio, headroom=1.0)

            # 최종 분석
            final_duration = len(audio) / 1000
            final_rate = char_count / final_duration if final_duration > 0 else 0
            final_dbfs = audio.dBFS if audio.dBFS != float('-inf') else -60

            print(f"    → {final_rate:.2f} 글자/초, {final_dbfs:.1f} dBFS, {final_duration:.2f}초")

            # 바이트로 변환
            output = io.BytesIO()
            audio.export(output, format="wav")
            output.seek(0)

            results.append({
                **item,
                "audio_data": output.read(),
                "audio": None,  # 메모리 해제
                "final_duration": final_duration,
                "final_rate": final_rate,
                "final_dbfs": final_dbfs,
                "speed_adjusted": speed_adjusted,
                "volume_change": volume_change
            })

        if progress_callback:
            progress_callback(total, total, "정규화 완료")

        return results

    def _adjust_speed(
        self,
        audio: AudioSegment,
        current_rate: float,
        target_rate: float
    ) -> Tuple[AudioSegment, bool]:
        """속도 조정 (FFmpeg atempo)"""

        ratio = current_rate / target_rate

        # 조정 범위 제한
        ratio = max(1 - self.max_speed_adjust, min(1 + self.max_speed_adjust, ratio))

        # 3% 미만 차이는 무시
        if abs(ratio - 1.0) < 0.03:
            print(f"    속도: 조정 불필요 (차이 {abs(ratio-1)*100:.1f}%)")
            return audio, False

        print(f"    속도: {ratio:.3f}x 조정 ({current_rate:.2f} → {target_rate:.2f} 글자/초)")

        if not self.ffmpeg_available:
            print(f"    ⚠️ FFmpeg 미설치 - 속도 조정 스킵")
            return audio, False

        # FFmpeg로 속도 조정 (피치 유지)
        try:
            temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

            audio.export(temp_in, format="wav")

            # atempo 범위: 0.5 ~ 2.0
            atempo = max(0.5, min(2.0, ratio))

            cmd = [
                "ffmpeg", "-y", "-i", temp_in,
                "-af", f"atempo={atempo}",
                "-ar", "24000",
                temp_out
            ]

            subprocess.run(cmd, check=True, capture_output=True)

            result = AudioSegment.from_file(temp_out)

            # 정리
            for f in [temp_in, temp_out]:
                try:
                    os.remove(f)
                except:
                    pass

            return result, True

        except Exception as e:
            print(f"    ⚠️ 속도 조정 실패: {e}")
            return audio, False

    def _standardize_silence(self, audio: AudioSegment) -> AudioSegment:
        """무음 표준화"""

        try:
            # 앞쪽 무음 감지 및 제거
            start_trim = detect_leading_silence(audio, silence_threshold=-50)
            start_trim = min(start_trim, 500)  # 최대 500ms

            # 뒤쪽 무음 감지 및 제거
            end_trim = detect_leading_silence(audio.reverse(), silence_threshold=-50)
            end_trim = min(end_trim, 500)

            # 트리밍 (안전 체크)
            if start_trim + end_trim < len(audio) - 100:
                audio = audio[start_trim:len(audio) - end_trim]

            # 표준 무음 추가
            leading = AudioSegment.silent(duration=self.silence_ms[0], frame_rate=audio.frame_rate)
            trailing = AudioSegment.silent(duration=self.silence_ms[1], frame_rate=audio.frame_rate)

            return leading + audio + trailing

        except Exception as e:
            print(f"    ⚠️ 무음 표준화 실패: {e}")
            return audio

    def _normalize_volume(self, audio: AudioSegment) -> Tuple[AudioSegment, float]:
        """음량 정규화"""

        current_dbfs = audio.dBFS

        if current_dbfs == float('-inf'):
            return audio, 0.0

        change = self.target_dbfs - current_dbfs

        # 최대 조정 범위 제한 (±15dB)
        change = max(-15, min(15, change))

        if abs(change) > 0.5:
            audio = audio.apply_gain(change)
            print(f"    음량: {change:+.1f} dB 조정 ({current_dbfs:.1f} → {audio.dBFS:.1f} dBFS)")

        return audio, change

    def _verify_results(self, results: List[Dict]):
        """결과 검증"""

        rates = [r["final_rate"] for r in results if r.get("final_rate")]
        dbfs_values = [r["final_dbfs"] for r in results if r.get("final_dbfs")]

        if rates:
            rate_min, rate_max = min(rates), max(rates)
            rate_mean = np.mean(rates)
            rate_deviation = (rate_max - rate_min) / 2 / rate_mean * 100 if rate_mean > 0 else 0

            print(f"\n  📊 발화속도 결과:")
            print(f"     범위: {rate_min:.2f} ~ {rate_max:.2f} 글자/초")
            print(f"     편차: ±{rate_deviation:.1f}%")

            if rate_deviation <= 3:
                print(f"     ✅ 목표 달성! (±3% 이내)")
            elif rate_deviation <= 5:
                print(f"     ⚠️ 양호 (±5% 이내)")
            else:
                print(f"     ❌ 추가 조정 필요")

        if dbfs_values:
            dbfs_min, dbfs_max = min(dbfs_values), max(dbfs_values)
            dbfs_range = dbfs_max - dbfs_min

            print(f"\n  📊 음량 결과:")
            print(f"     범위: {dbfs_min:.1f} ~ {dbfs_max:.1f} dBFS")
            print(f"     편차: {dbfs_range:.1f} dB")

            if dbfs_range <= 4:
                print(f"     ✅ 목표 달성! (±2dB 이내)")
            else:
                print(f"     ⚠️ 추가 조정 필요")


# ============================================================
# 편의 함수
# ============================================================

def normalize_scenes_v2(
    scenes: List[Dict],
    target_rate: Optional[float] = None,
    target_dbfs: float = -20.0,
    max_speed_adjust: float = 0.12,
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    씬 정규화 편의 함수

    Args:
        scenes: 씬 리스트
        target_rate: 목표 발화속도 (None이면 자동)
        target_dbfs: 목표 음량
        max_speed_adjust: 최대 속도 조정
        progress_callback: 진행 콜백

    Returns:
        정규화된 씬 리스트
    """

    normalizer = AudioNormalizer(
        target_rate=target_rate,
        target_dbfs=target_dbfs,
        max_speed_adjust=max_speed_adjust
    )

    return normalizer.normalize_all(scenes, progress_callback)


def analyze_scenes_stats(scenes: List[Dict]) -> Dict:
    """
    씬 통계 분석

    Args:
        scenes: 씬 리스트

    Returns:
        통계 정보 dict
    """

    if not PYDUB_AVAILABLE:
        return {"error": "pydub not installed"}

    rates = []
    dbfs_values = []
    durations = []

    for scene in scenes:
        if not scene.get("audio_data"):
            continue

        try:
            audio = AudioSegment.from_file(
                io.BytesIO(scene["audio_data"]), format="wav"
            )
            duration = len(audio) / 1000
            text = scene.get("text", "")
            char_count = len(text.replace(" ", ""))

            rate = char_count / duration if duration > 0 else 0
            dbfs = audio.dBFS if audio.dBFS != float('-inf') else -60

            rates.append(rate)
            dbfs_values.append(dbfs)
            durations.append(duration)

        except:
            pass

    if not rates:
        return {"error": "no valid scenes"}

    return {
        "scene_count": len(rates),
        "rate_min": min(rates),
        "rate_max": max(rates),
        "rate_mean": np.mean(rates),
        "rate_std": np.std(rates),
        "rate_deviation_pct": (max(rates) - min(rates)) / 2 / np.mean(rates) * 100,
        "dbfs_min": min(dbfs_values),
        "dbfs_max": max(dbfs_values),
        "dbfs_range": max(dbfs_values) - min(dbfs_values),
        "total_duration": sum(durations)
    }
