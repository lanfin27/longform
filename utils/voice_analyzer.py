# -*- coding: utf-8 -*-
"""
참조 음성 분석기 v2.0 - 텍스트 기반 정확 측정

핵심 변경:
- 텍스트가 있으면 정확한 발화속도 계산 (글자수/시간)
- 텍스트가 없으면 기존 추정 방식 사용 (음성 밀도)
- 분석 결과 캐싱 (재분석 방지)

사용:
    # 텍스트와 함께 분석 (정확)
    result = analyze_voice_with_text("voice.mp3", "안녕하세요...")

    # 텍스트 없이 분석 (추정)
    result = analyze_voice_and_get_params("voice.mp3")
"""

import os
import re
import json
import numpy as np
from typing import Dict, Optional, Tuple, List
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from pathlib import Path
import warnings

warnings.filterwarnings("ignore")


class VoiceProfileManager:
    """
    음성 프로필 관리자

    기능:
    1. 음성 프로필 로드/저장
    2. 텍스트 연결 (.txt 파일 또는 voice_profiles.json)
    3. 분석 결과 캐싱
    """

    def __init__(self, base_path: str = None):
        if base_path is None:
            # 기본 경로 설정
            self.base_path = Path("data/voice_samples")
        else:
            self.base_path = Path(base_path)

        self.profiles_file = self.base_path / "voice_profiles.json"
        self.profiles: Dict[str, Dict] = {}

        self._load_profiles()

        print(f"[VoiceProfileManager] 초기화")
        print(f"  경로: {self.base_path}")
        print(f"  프로필 수: {len(self.profiles)}")

    def _load_profiles(self):
        """프로필 로드"""

        # 1. 통합 프로필 파일 확인
        if self.profiles_file.exists():
            try:
                with open(self.profiles_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    voices = data.get("voices", [])
                    for voice in voices:
                        voice_id = voice.get("id") or voice.get("name", "").lower().replace(" ", "_")
                        self.profiles[voice_id] = voice
                print(f"  ✅ 통합 프로필 로드: {len(self.profiles)}개")
                return
            except Exception as e:
                print(f"  ⚠️ 프로필 로드 오류: {e}")

        # 2. 개별 파일에서 프로필 생성
        self._scan_voice_files()

    def _scan_voice_files(self):
        """음성 파일 스캔 및 프로필 자동 생성"""

        audio_extensions = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}

        for folder in ["default", "library", "custom", ""]:
            folder_path = self.base_path / folder if folder else self.base_path

            if not folder_path.exists():
                continue

            for audio_file in folder_path.iterdir():
                if audio_file.suffix.lower() not in audio_extensions:
                    continue

                # 프로필 생성
                voice_id = audio_file.stem.lower().replace(" ", "_")

                if voice_id in self.profiles:
                    continue

                # 텍스트 파일 찾기
                transcript = self._find_transcript(audio_file)

                self.profiles[voice_id] = {
                    "id": voice_id,
                    "name": audio_file.stem,
                    "audio_file": str(audio_file.relative_to(self.base_path)),
                    "audio_path": str(audio_file),
                    "transcript": transcript,
                    "language": "ko",
                    "analyzed": False,
                }

        print(f"  📁 스캔 완료: {len(self.profiles)}개 음성")

    def _find_transcript(self, audio_file: Path) -> Optional[str]:
        """
        텍스트 파일 찾기

        우선순위:
        1. 같은 이름의 .txt 파일
        2. 같은 이름의 .json 파일
        3. None
        """

        # .txt 파일
        txt_file = audio_file.with_suffix(".txt")
        if txt_file.exists():
            try:
                with open(txt_file, "r", encoding="utf-8") as f:
                    transcript = f.read().strip()
                    if transcript:
                        print(f"    ✅ 텍스트 발견: {txt_file.name}")
                        return transcript
            except:
                pass

        # .json 파일
        json_file = audio_file.with_suffix(".json")
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    transcript = data.get("transcript", "")
                    if transcript:
                        print(f"    ✅ 텍스트 발견: {json_file.name}")
                        return transcript
            except:
                pass

        return None

    def get_profile(self, voice_id_or_path: str) -> Optional[Dict]:
        """프로필 가져오기 (ID 또는 경로로)"""

        # ID로 검색
        voice_id_lower = voice_id_or_path.lower().replace(" ", "_")
        if voice_id_lower in self.profiles:
            return self.profiles[voice_id_lower]

        # 경로로 검색
        for profile in self.profiles.values():
            if profile.get("audio_path") == voice_id_or_path:
                return profile
            if profile.get("audio_file") and voice_id_or_path.endswith(profile["audio_file"]):
                return profile
            # 파일명으로 검색
            if os.path.basename(voice_id_or_path) == os.path.basename(profile.get("audio_path", "")):
                return profile

        # 새 프로필 생성
        if os.path.exists(voice_id_or_path):
            return self._create_profile_from_path(voice_id_or_path)

        return None

    def _create_profile_from_path(self, audio_path: str) -> Dict:
        """경로에서 프로필 생성"""

        audio_file = Path(audio_path)
        voice_id = audio_file.stem.lower().replace(" ", "_")

        transcript = self._find_transcript(audio_file)

        profile = {
            "id": voice_id,
            "name": audio_file.stem,
            "audio_file": audio_file.name,
            "audio_path": str(audio_file),
            "transcript": transcript,
            "language": "ko",
            "analyzed": False,
        }

        self.profiles[voice_id] = profile

        return profile

    def set_transcript(self, voice_id: str, transcript: str):
        """텍스트 설정"""

        voice_id_lower = voice_id.lower().replace(" ", "_")

        if voice_id_lower in self.profiles:
            self.profiles[voice_id_lower]["transcript"] = transcript
            self.profiles[voice_id_lower]["analyzed"] = False  # 재분석 필요
            self.save_profiles()

            # .txt 파일로도 저장
            audio_path = self.profiles[voice_id_lower].get("audio_path")
            if audio_path:
                txt_path = Path(audio_path).with_suffix(".txt")
                try:
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(transcript)
                    print(f"  📝 텍스트 파일 저장: {txt_path}")
                except Exception as e:
                    print(f"  ⚠️ 텍스트 파일 저장 실패: {e}")

    def save_profiles(self):
        """프로필 저장"""

        try:
            # 디렉토리 확인
            self.profiles_file.parent.mkdir(parents=True, exist_ok=True)

            data = {"voices": list(self.profiles.values())}

            with open(self.profiles_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"[VoiceProfileManager] 프로필 저장 완료: {self.profiles_file}")

        except Exception as e:
            print(f"[VoiceProfileManager] 저장 오류: {e}")

    def list_voices(self) -> List[Dict]:
        """모든 음성 목록"""
        return list(self.profiles.values())

    def update_analysis(self, voice_id: str, analysis: Dict, params: Dict):
        """분석 결과 저장"""

        voice_id_lower = voice_id.lower().replace(" ", "_")

        if voice_id_lower in self.profiles:
            self.profiles[voice_id_lower]["analysis"] = analysis
            self.profiles[voice_id_lower]["recommended_params"] = params
            self.profiles[voice_id_lower]["analyzed"] = True
            self.save_profiles()


class VoiceAnalyzer:
    """
    참조 음성 분석기 v2.0

    핵심 기능:
    1. 텍스트가 있으면 → 정확한 발화속도 계산 (글자수/시간)
    2. 텍스트가 없으면 → 음성 밀도로 추정
    3. 분석 결과 캐싱
    """

    def __init__(self, profile_manager: VoiceProfileManager = None):
        self.profile_manager = profile_manager or VoiceProfileManager()

        # 기준값
        self.reference_speed = 8.5  # 글자/초 (표준 한국어)
        self.reference_lufs = -16.0  # LUFS

        print("[VoiceAnalyzer v2.0] 초기화 완료")
        print("  ⭐ 텍스트 기반 정확 측정 지원")

    def analyze(
        self,
        audio_path: str,
        transcript: str = None,
        force_reanalyze: bool = False
    ) -> Dict:
        """
        참조 음성 분석

        Args:
            audio_path: 음성 파일 경로
            transcript: 텍스트 (없으면 프로필에서 가져옴)
            force_reanalyze: 캐시 무시하고 재분석

        Returns:
            {
                "duration_sec": float,
                "char_count": int,           # 글자 수 (텍스트 있을 때)
                "speech_rate": float,        # 발화 속도
                "speech_rate_accurate": bool, # 정확한 측정 여부
                "avg_lufs": float,
                "tempo": str,
                ...
            }
        """

        print(f"\n[VoiceAnalyzer] 분석 시작: {os.path.basename(audio_path)}")

        # 1. 프로필 확인 (캐시)
        profile = self.profile_manager.get_profile(audio_path)

        if profile and profile.get("analyzed") and not force_reanalyze:
            if "analysis" in profile:
                print(f"  ✅ 캐시된 분석 결과 사용")
                return profile["analysis"]

        # 2. 텍스트 확인
        if transcript is None and profile:
            transcript = profile.get("transcript")

        has_transcript = bool(transcript and len(transcript.strip()) > 0)

        if has_transcript:
            print(f"  ✅ 텍스트 있음: {len(transcript)}자")
        else:
            print(f"  ⚠️ 텍스트 없음 - 추정 모드")

        # 3. 오디오 로드
        if not os.path.exists(audio_path):
            print(f"  ❌ 파일 없음")
            return self._get_default_analysis()

        try:
            audio = AudioSegment.from_file(audio_path)
        except Exception as e:
            print(f"  ❌ 로드 실패: {e}")
            return self._get_default_analysis()

        # 4. 기본 분석
        duration_sec = len(audio) / 1000
        avg_lufs = self._measure_lufs(audio)
        energy_variation = self._measure_energy_variation(audio)
        speech_ratio, _ = self._analyze_speech_segments(audio)

        print(f"  길이: {duration_sec:.2f}초")
        print(f"  음량: {avg_lufs:.1f} LUFS")

        # 5. ⭐ 발화 속도 계산 (핵심!)
        if has_transcript:
            # 정확한 계산
            char_count = self._count_chars(transcript)
            speech_rate = char_count / duration_sec if duration_sec > 0 else 8.5
            speech_rate_accurate = True

            print(f"  ⭐ 정확한 측정: {char_count}자 / {duration_sec:.2f}초 = {speech_rate:.2f} 글자/초")
        else:
            # 추정
            char_count = 0
            speech_rate = self._estimate_speech_rate(audio, speech_ratio, duration_sec)
            speech_rate_accurate = False

            print(f"  📊 추정 측정: {speech_rate:.2f} 글자/초 (음성 밀도 기반)")

        # 6. 템포 분류
        tempo = self._classify_tempo(speech_rate)
        print(f"  템포: {tempo}")

        # 7. 분석 결과
        analysis = {
            "duration_sec": round(duration_sec, 2),
            "char_count": char_count,
            "speech_rate": round(speech_rate, 2),
            "speech_rate_accurate": speech_rate_accurate,
            "avg_lufs": round(avg_lufs, 1),
            "energy_variation": round(energy_variation, 3),
            "speech_ratio": round(speech_ratio, 2),
            "tempo": tempo,
            "has_transcript": has_transcript,
        }

        print(f"[VoiceAnalyzer] 분석 완료")

        return analysis

    def _count_chars(self, text: str) -> int:
        """
        발화 글자 수 계산

        제외: 공백, 줄바꿈, 일부 특수문자
        포함: 한글, 숫자, 영문
        """

        # 공백, 줄바꿈 제거
        text = text.replace(" ", "").replace("\n", "").replace("\t", "")

        # 일부 특수문자 제거 (선택적)
        text = re.sub(r'[.,!?…·\-\[\](){}""''「」『』:;\'\"<>]', '', text)

        return len(text)

    def recommend_params(self, analysis: Dict) -> Dict:
        """
        분석 결과 기반 TTS 파라미터 추천

        ⭐ 정확한 측정일 때 더 정밀한 추천
        """

        print(f"\n[VoiceAnalyzer] 파라미터 추천")

        speech_rate = analysis.get("speech_rate", self.reference_speed)
        energy_var = analysis.get("energy_variation", 0.1)
        tempo = analysis.get("tempo", "normal")
        accurate = analysis.get("speech_rate_accurate", False)

        if accurate:
            print(f"  ⭐ 정확한 측정 기반 추천")
        else:
            print(f"  📊 추정 기반 추천 (정확도 제한)")

        # 1. Speed 파라미터 계산
        speed_ratio = speech_rate / self.reference_speed

        if accurate:
            # 정확한 측정: 더 세밀한 조정
            recommended_speed = speed_ratio
            recommended_speed = max(0.70, min(1.30, recommended_speed))
        else:
            # 추정: 보수적 조정
            if tempo == "slow":
                recommended_speed = max(0.80, min(0.95, speed_ratio * 0.95))
            elif tempo == "fast":
                recommended_speed = max(1.05, min(1.20, speed_ratio * 1.05))
            else:
                recommended_speed = max(0.90, min(1.10, speed_ratio))

        print(f"  발화속도: {speech_rate:.2f} → speed: {recommended_speed:.2f}")

        # 2. CFG Weight
        if energy_var > 0.15:
            cfg_weight = 0.4
        elif energy_var < 0.08:
            cfg_weight = 0.6
        else:
            cfg_weight = 0.5

        # 3. Exaggeration
        exaggeration = max(0.3, min(0.7, 0.3 + energy_var * 2))

        # 4. Temperature
        if tempo == "slow":
            temperature = 0.7
        elif tempo == "fast":
            temperature = 0.9
        else:
            temperature = 0.8

        # 5. 목표 발화속도 (정규화용)
        # 정확한 측정이면 해당 속도 사용, 아니면 기준값 사용
        target_speed = speech_rate if accurate else self.reference_speed

        params = {
            "speed": round(recommended_speed, 2),
            "cfg_weight": round(cfg_weight, 2),
            "exaggeration": round(exaggeration, 2),
            "temperature": round(temperature, 2),
            "target_speed": round(target_speed, 2),
            "based_on_accurate": accurate,
        }

        print(f"[VoiceAnalyzer] 추천: {params}")

        return params

    def analyze_and_recommend(
        self,
        audio_path: str,
        transcript: str = None,
        force_reanalyze: bool = False
    ) -> Dict:
        """분석 + 추천 통합"""

        analysis = self.analyze(audio_path, transcript, force_reanalyze)
        params = self.recommend_params(analysis)

        # 캐시 저장
        profile = self.profile_manager.get_profile(audio_path)
        if profile:
            self.profile_manager.update_analysis(profile["id"], analysis, params)

        return {
            "analysis": analysis,
            "recommended_params": params,
        }

    # ============================================================
    # 측정 함수들
    # ============================================================

    def _measure_lufs(self, audio: AudioSegment) -> float:
        """LUFS 측정"""
        try:
            samples = np.array(audio.get_array_of_samples()).astype(np.float32)
            samples = samples / (2**15)
            rms = np.sqrt(np.mean(samples**2))
            lufs = 20 * np.log10(rms + 1e-10) - 3
            return max(-60, min(0, lufs))
        except:
            return -23.0

    def _analyze_speech_segments(self, audio: AudioSegment) -> Tuple[float, list]:
        """음성 구간 분석"""
        try:
            nonsilent = detect_nonsilent(audio, min_silence_len=100, silence_thresh=-40)
            if not nonsilent:
                return 1.0, []
            speech_ms = sum(end - start for start, end in nonsilent)
            speech_ratio = speech_ms / len(audio)
            return speech_ratio, nonsilent
        except:
            return 1.0, []

    def _estimate_speech_rate(self, audio, speech_ratio, duration_sec) -> float:
        """음성 밀도 기반 발화속도 추정"""
        base_rate = 8.5
        base_ratio = 0.70
        if speech_ratio > 0:
            estimated_rate = base_rate * (speech_ratio / base_ratio)
        else:
            estimated_rate = base_rate
        return max(5.0, min(12.0, estimated_rate))

    def _measure_energy_variation(self, audio: AudioSegment) -> float:
        """에너지 변화량 측정 (감정 표현 정도)"""
        try:
            samples = np.array(audio.get_array_of_samples()).astype(np.float32)
            frame_size = int(len(samples) / 100)
            if frame_size < 100:
                return 0.1
            energies = []
            for i in range(0, len(samples) - frame_size, frame_size):
                frame = samples[i:i + frame_size]
                energy = np.sqrt(np.mean(frame**2))
                energies.append(energy)
            if not energies:
                return 0.1
            mean_energy = np.mean(energies)
            std_energy = np.std(energies)
            if mean_energy > 0:
                variation = std_energy / mean_energy
            else:
                variation = 0.1
            return max(0.0, min(0.5, variation))
        except:
            return 0.1

    def _classify_tempo(self, speech_rate: float) -> str:
        """템포 분류"""
        if speech_rate < 7.0:
            return "slow"
        elif speech_rate > 9.5:
            return "fast"
        else:
            return "normal"

    def _get_default_analysis(self) -> Dict:
        """기본 분석 결과"""
        return {
            "duration_sec": 0,
            "char_count": 0,
            "speech_rate": self.reference_speed,
            "speech_rate_accurate": False,
            "avg_lufs": self.reference_lufs,
            "energy_variation": 0.1,
            "speech_ratio": 0.7,
            "tempo": "normal",
            "has_transcript": False,
        }


# ============================================================
# 싱글톤 및 간편 함수
# ============================================================

_analyzer = None
_profile_manager = None

def get_profile_manager() -> VoiceProfileManager:
    """프로필 관리자 싱글톤"""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = VoiceProfileManager()
    return _profile_manager

def get_analyzer() -> VoiceAnalyzer:
    """분석기 싱글톤"""
    global _analyzer
    if _analyzer is None:
        _analyzer = VoiceAnalyzer(get_profile_manager())
    return _analyzer


def analyze_voice_with_text(
    audio_path: str,
    transcript: str = None,
    force_reanalyze: bool = False
) -> Dict:
    """
    참조 음성 분석 (텍스트 포함)

    사용 예:
        result = analyze_voice_with_text(
            "path/to/voice.mp3",
            "안녕하세요, 오늘은..."
        )
        print(result["analysis"]["speech_rate"])  # 정확한 값!
        print(result["recommended_params"]["speed"])
    """
    return get_analyzer().analyze_and_recommend(audio_path, transcript, force_reanalyze)


def analyze_voice_and_get_params(audio_path: str) -> Dict:
    """
    참조 음성 분석 후 추천 파라미터 반환 (하위 호환)

    텍스트가 프로필에 있으면 자동으로 사용
    """
    return get_analyzer().analyze_and_recommend(audio_path)


def set_voice_transcript(voice_path: str, transcript: str):
    """음성에 텍스트 연결"""
    profile_manager = get_profile_manager()
    profile = profile_manager.get_profile(voice_path)
    if profile:
        profile_manager.set_transcript(profile["id"], transcript)
        print(f"[VoiceAnalyzer] 텍스트 설정 완료: {len(transcript)}자")
    else:
        print(f"[VoiceAnalyzer] 프로필을 찾을 수 없음: {voice_path}")


def get_voice_transcript(voice_path: str) -> Optional[str]:
    """음성의 텍스트 가져오기"""
    profile_manager = get_profile_manager()
    profile = profile_manager.get_profile(voice_path)
    if profile:
        return profile.get("transcript")
    return None


def get_recommended_speed(audio_path: str) -> float:
    """참조 음성에서 추천 speed 값만 반환"""
    result = analyze_voice_and_get_params(audio_path)
    return result.get("recommended_params", {}).get("speed", 1.0)


def get_recommended_target_speed(audio_path: str) -> float:
    """참조 음성에서 목표 발화속도 반환"""
    result = analyze_voice_and_get_params(audio_path)
    return result.get("recommended_params", {}).get("target_speed", 8.5)


# ============================================================
# VoiceOptimizer - 참조 음성 최적화 (Voice Cloning용)
# ============================================================

class VoiceOptimizer:
    """
    참조 음성 최적화기

    긴 음성에서 voice cloning에 최적인 구간(15~30초) 추출
    - 음성이 연속적인 구간 선택
    - 음량이 안정적인 구간 선택
    - 시작보다 중간 부분 선호
    """

    # 최적 구간 설정
    OPTIMAL_MIN_SEC = 15   # 최소 15초
    OPTIMAL_MAX_SEC = 30   # 최대 30초
    OPTIMAL_TARGET_SEC = 20  # 목표 20초

    def __init__(self):
        self.cache_dir = Path("data/voice_samples/optimized")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        print("[VoiceOptimizer] 초기화")
        print(f"  최적 구간: {self.OPTIMAL_MIN_SEC}~{self.OPTIMAL_MAX_SEC}초")

    def optimize_for_cloning(
        self,
        audio_path: str,
        force: bool = False
    ) -> str:
        """
        Voice cloning을 위한 최적 구간 추출

        Args:
            audio_path: 원본 음성 경로
            force: 캐시 무시하고 재추출

        Returns:
            최적화된 음성 경로 (15~30초)
        """

        if not os.path.exists(audio_path):
            print(f"[VoiceOptimizer] ❌ 파일 없음: {audio_path}")
            return audio_path

        # 캐시 확인
        cache_path = self._get_cache_path(audio_path)
        if cache_path.exists() and not force:
            print(f"[VoiceOptimizer] ✅ 캐시 사용: {cache_path.name}")
            return str(cache_path)

        # 오디오 로드
        try:
            audio = AudioSegment.from_file(audio_path)
        except Exception as e:
            print(f"[VoiceOptimizer] ❌ 로드 실패: {e}")
            return audio_path

        duration_sec = len(audio) / 1000
        print(f"\n[VoiceOptimizer] 원본 길이: {duration_sec:.1f}초")

        # 이미 최적 범위면 그대로 사용
        if self.OPTIMAL_MIN_SEC <= duration_sec <= self.OPTIMAL_MAX_SEC:
            print(f"[VoiceOptimizer] ✅ 이미 최적 범위")
            return audio_path

        # 너무 짧으면 그대로 사용
        if duration_sec < self.OPTIMAL_MIN_SEC:
            print(f"[VoiceOptimizer] ⚠️ 너무 짧음, 원본 사용")
            return audio_path

        # 최적 구간 추출
        print(f"[VoiceOptimizer] 🔍 최적 구간 추출 중...")

        optimized = self._extract_best_segment(audio)

        # 저장
        optimized.export(
            str(cache_path),
            format="mp3",
            parameters=["-q:a", "2"]  # 고품질
        )

        new_duration = len(optimized) / 1000
        print(f"[VoiceOptimizer] ✅ 최적화 완료: {duration_sec:.1f}초 → {new_duration:.1f}초")
        print(f"[VoiceOptimizer] 📁 저장: {cache_path.name}")

        return str(cache_path)

    def _extract_best_segment(self, audio: AudioSegment) -> AudioSegment:
        """
        최적 구간 추출

        기준:
        1. 음성이 연속적인 구간 (묵음 적음)
        2. 음량이 안정적인 구간
        3. 시작 부분보다 중간 부분 선호 (워밍업 후)
        """

        duration_ms = len(audio)
        target_ms = self.OPTIMAL_TARGET_SEC * 1000

        # 후보 구간들의 품질 점수 계산
        best_score = -1
        best_start = 0

        # 1초 단위로 스캔
        step_ms = 1000

        for start_ms in range(0, duration_ms - target_ms, step_ms):
            segment = audio[start_ms:start_ms + target_ms]
            score = self._calculate_segment_quality(segment, start_ms, duration_ms)

            if score > best_score:
                best_score = score
                best_start = start_ms

        print(f"  최적 구간: {best_start/1000:.1f}초 ~ {(best_start + target_ms)/1000:.1f}초")
        print(f"  품질 점수: {best_score:.3f}")

        return audio[best_start:best_start + target_ms]

    def _calculate_segment_quality(
        self,
        segment: AudioSegment,
        start_ms: int,
        total_ms: int
    ) -> float:
        """
        구간 품질 점수 계산

        점수 = 음성비율(40%) + 음량안정성(30%) + 위치점수(30%)
        """

        # 1. 음성 비율 (묵음이 적을수록 좋음)
        try:
            nonsilent = detect_nonsilent(
                segment,
                min_silence_len=100,
                silence_thresh=-40
            )
            speech_ms = sum(end - start for start, end in nonsilent) if nonsilent else len(segment)
            speech_ratio = speech_ms / len(segment)
        except:
            speech_ratio = 0.7

        # 2. 음량 안정성 (변화가 적을수록 좋음)
        try:
            samples = np.array(segment.get_array_of_samples()).astype(np.float32)

            # 프레임별 RMS
            frame_size = len(samples) // 20
            if frame_size > 0:
                rms_values = []
                for i in range(0, len(samples) - frame_size, frame_size):
                    frame = samples[i:i + frame_size]
                    rms = np.sqrt(np.mean(frame**2))
                    rms_values.append(rms)

                if rms_values:
                    mean_rms = np.mean(rms_values)
                    std_rms = np.std(rms_values)
                    stability = 1.0 - min(1.0, std_rms / (mean_rms + 1e-10))
                else:
                    stability = 0.5
            else:
                stability = 0.5
        except:
            stability = 0.5

        # 3. 위치 점수 (시작보다 중간 선호)
        position = start_ms / total_ms
        # 10%~50% 구간 선호
        if 0.1 <= position <= 0.5:
            position_score = 1.0
        elif position < 0.1:
            position_score = position * 10  # 0~0.1 → 0~1
        else:
            position_score = max(0, 1.0 - (position - 0.5))  # 0.5~1 → 1~0

        # 종합 점수
        score = (
            speech_ratio * 0.4 +
            stability * 0.3 +
            position_score * 0.3
        )

        return score

    def _get_cache_path(self, audio_path: str) -> Path:
        """캐시 경로 생성"""
        import hashlib

        # 파일 해시로 고유 이름 생성
        with open(audio_path, "rb") as f:
            file_hash = hashlib.md5(f.read()[:10000]).hexdigest()[:8]

        original_name = Path(audio_path).stem
        cache_name = f"{original_name}_opt_{file_hash}.mp3"

        return self.cache_dir / cache_name


# VoiceOptimizer 싱글톤
_voice_optimizer = None

def get_voice_optimizer() -> VoiceOptimizer:
    """VoiceOptimizer 싱글톤"""
    global _voice_optimizer
    if _voice_optimizer is None:
        _voice_optimizer = VoiceOptimizer()
    return _voice_optimizer


def optimize_voice_for_cloning(audio_path: str, force: bool = False) -> str:
    """
    Voice cloning을 위해 참조 음성 최적화 (간편 함수)

    사용 예:
        optimized_path = optimize_voice_for_cloning("path/to/long_voice.mp3")
        # 15~30초 구간으로 최적화된 경로 반환
    """
    return get_voice_optimizer().optimize_for_cloning(audio_path, force)
