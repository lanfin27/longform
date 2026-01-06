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
            # ⭐ 절대 경로 사용 (Chatter 서버에서 인식 가능하도록)
            project_root = Path(__file__).parent.parent.resolve()
            self.base_path = project_root / "data" / "voice_samples"
        else:
            self.base_path = Path(base_path).resolve()

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

    def list_voices_grouped(self) -> Dict[str, List[Dict]]:
        """
        최적화 상태별로 그룹화된 음성 목록

        Returns:
            {
                "optimized": [...],   # 최적화된 음성
                "original": [...]     # 원본 음성
            }
        """
        optimized = []
        original = []

        for profile in self.profiles.values():
            if profile.get("is_optimized", False):
                optimized.append(profile)
            else:
                original.append(profile)

        return {
            "optimized": optimized,
            "original": original
        }

    def add_profile(
        self,
        voice_id: str,
        name: str,
        audio_path: str,
        transcript: str = None,
        is_optimized: bool = False,
        original_id: str = None,
        analysis: Dict = None,
        params: Dict = None
    ) -> Dict:
        """
        새 음성 프로필 추가

        Args:
            voice_id: 음성 고유 ID
            name: 표시 이름
            audio_path: 오디오 파일 경로
            transcript: 텍스트
            is_optimized: 최적화된 음성인지
            original_id: 원본 음성 ID (최적화 음성인 경우)
            analysis: 분석 결과
            params: 추천 파라미터

        Returns:
            생성된 프로필
        """

        # 기존 프로필 확인
        voice_id_lower = voice_id.lower().replace(" ", "_")

        profile = {
            "id": voice_id_lower,
            "name": name,
            "audio_file": os.path.basename(audio_path),
            "audio_path": audio_path,
            "transcript": transcript,
            "language": "ko",
            "analyzed": analysis is not None,
            "is_optimized": is_optimized,
        }

        if original_id:
            profile["original_id"] = original_id

        if analysis:
            profile["analysis"] = analysis

        if params:
            profile["recommended_params"] = params

        # 프로필 저장
        self.profiles[voice_id_lower] = profile
        self.save_profiles()

        print(f"[VoiceProfileManager] 프로필 추가: {name}")
        if is_optimized:
            print(f"  ⭐ 최적화된 음성 (원본: {original_id})")

        return profile

    def get_optimized_version(self, voice_id: str) -> Optional[Dict]:
        """
        원본 음성의 최적화 버전 찾기

        Returns:
            최적화된 프로필 또는 None
        """
        voice_id_lower = voice_id.lower().replace(" ", "_")

        # 해당 음성의 최적화 버전 검색
        for profile in self.profiles.values():
            if profile.get("original_id") == voice_id_lower and profile.get("is_optimized"):
                return profile

        return None

    def is_voice_optimized(self, voice_id: str) -> bool:
        """음성이 이미 최적화되었는지 확인"""
        voice_id_lower = voice_id.lower().replace(" ", "_")

        # 자체가 최적화된 음성인지
        profile = self.profiles.get(voice_id_lower)
        if profile and profile.get("is_optimized"):
            return True

        # 최적화 버전이 존재하는지
        if self.get_optimized_version(voice_id):
            return True

        return False

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

        ⭐ Voice Clone 품질 최적화
        - cfg_weight: 0.7 (참조 특성 강화)
        - temperature: 0.5 (안정적인 발음)
        """

        print(f"\n[VoiceAnalyzer] ⭐ Voice Clone 최적화 파라미터 추천")

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

        # ⭐⭐⭐ Voice Clone 최적화 파라미터 (자연스러움 강화) ⭐⭐⭐
        # 🔴 기존: 너무 보수적 → 딱딱한 음성
        # ✅ 수정: 표현력+자연스러움 증가, 참조 특성 강화

        # 2. CFG Weight - 참조 음성 특성 강화
        cfg_weight = 0.85  # ⭐⭐⭐ 0.75 → 0.85 (참조 특성 최대 강화!)

        # 3. Exaggeration - 감정 표현 (⭐ 핵심 수정!)
        exaggeration = 0.70  # ⭐ 0.55 → 0.70 (표현력 +27%!)

        # 4. Temperature - 자연스러운 변화 허용
        temperature = 0.65  # ⭐ 0.5 → 0.65 (자연스러움 +30%!)

        # 5. 목표 발화속도 (정규화용)
        # 정확한 측정이면 해당 속도 사용, 아니면 기준값 사용
        target_speed = speech_rate if accurate else self.reference_speed

        # ⭐⭐⭐ speed 1.0 고정 - 후처리 가속 방지! ⭐⭐⭐
        # 🔴 기존: recommended_speed 사용 → 0.75~0.85 → 후처리에서 46%+ 가속
        # ✅ 수정: 1.0 고정 → 후처리 가속 최소화 → 자연스러운 음성
        fixed_speed = 1.0

        params = {
            "speed": fixed_speed,  # ⭐ 1.0 고정! (recommended_speed 대신)
            "cfg_weight": cfg_weight,
            "exaggeration": exaggeration,
            "temperature": temperature,
            "target_speed": round(target_speed, 2),
            "based_on_accurate": accurate,
            "_original_recommended_speed": round(recommended_speed, 2),  # 참고용
        }

        print(f"[VoiceAnalyzer] ⭐⭐⭐ Voice Clone 최적화 (후처리 가속 방지):")
        print(f"  speed: {fixed_speed} (⭐ 1.0 고정! 원래 추천: {recommended_speed:.2f})")
        print(f"  cfg_weight: {cfg_weight} (참조 특성 ↑↑)")
        print(f"  exaggeration: {exaggeration} (표현력 ↑)")
        print(f"  temperature: {temperature} (자연스러움 ↑)")

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
    참조 음성 최적화기 v2.3

    긴 음성에서 voice cloning에 최적인 구간(15~30초) 추출
    - 음성이 연속적인 구간 선택
    - 음량이 안정적인 구간 선택
    - 시작보다 중간 부분 선호
    - ⭐ 품질 점수 기반 구간 선택 강화
    - ⭐ 최적화된 음성을 새 프로필로 등록
    """

    # 최적 구간 설정
    OPTIMAL_MIN_SEC = 15   # 최소 15초
    OPTIMAL_MAX_SEC = 30   # 최대 30초
    OPTIMAL_TARGET_SEC = 20  # 목표 20초
    OPTIMIZATION_THRESHOLD_SEC = 60  # 60초 이상일 때만 최적화
    MIN_QUALITY_SCORE = 0.6  # ⭐ 최소 품질 점수 (이하면 경고)

    def __init__(self, profile_manager: VoiceProfileManager = None):
        # ⭐ 절대 경로 사용 (Chatter 서버에서 인식 가능하도록)
        project_root = Path(__file__).parent.parent.resolve()

        self.default_dir = project_root / "data" / "voice_samples" / "default"
        self.default_dir.mkdir(parents=True, exist_ok=True)

        # 기존 캐시 디렉토리도 유지 (하위호환)
        self.cache_dir = project_root / "data" / "voice_samples" / "optimized"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.profile_manager = profile_manager

        print("[VoiceOptimizer v2.2] 초기화")
        print(f"  최적 구간: {self.OPTIMAL_MIN_SEC}~{self.OPTIMAL_MAX_SEC}초")
        print(f"  최적화 기준: {self.OPTIMIZATION_THRESHOLD_SEC}초 이상")
        print(f"  캐시 경로: {self.cache_dir}")

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
        최적 구간 추출 (품질 점수 기반)

        기준:
        1. 음성이 연속적인 구간 (묵음 적음)
        2. 음량이 안정적인 구간
        3. 억양 다양성 (표현력)
        4. 시작 부분보다 중간 부분 선호 (워밍업 후)
        """

        duration_ms = len(audio)
        target_ms = self.OPTIMAL_TARGET_SEC * 1000

        # 후보 구간들의 품질 점수 계산
        best_score = -1
        best_start = 0
        all_scores = []

        # 2초 단위로 스캔 (더 정밀)
        step_ms = 2000

        for start_ms in range(0, duration_ms - target_ms, step_ms):
            segment = audio[start_ms:start_ms + target_ms]
            score = self._calculate_segment_quality(segment, start_ms, duration_ms)
            all_scores.append((start_ms, score))

            if score > best_score:
                best_score = score
                best_start = start_ms

        # ⭐ 점수 통계 및 품질 경고
        scores_only = [s[1] for s in all_scores]
        avg_score = np.mean(scores_only) if scores_only else 0
        min_score = min(scores_only) if scores_only else 0
        max_score = max(scores_only) if scores_only else 0

        print(f"[VoiceOptimizer] 구간 탐색 완료:")
        print(f"  탐색 구간 수: {len(all_scores)}")
        print(f"  점수 범위: {min_score:.3f} ~ {max_score:.3f}")
        print(f"  평균 점수: {avg_score:.3f}")
        print(f"  최적 구간: {best_start/1000:.1f}초 ~ {(best_start + target_ms)/1000:.1f}초")
        print(f"  📊 품질 점수: {best_score:.3f}")

        # ⭐ 품질 경고
        if best_score < self.MIN_QUALITY_SCORE:
            print(f"[VoiceOptimizer] ⚠️ 경고: 품질 점수가 낮습니다 ({best_score:.3f} < {self.MIN_QUALITY_SCORE})")
            print(f"[VoiceOptimizer] ⚠️ 더 깨끗한 참조 음성을 권장합니다.")
            # 상위 3개 후보 표시
            top_candidates = sorted(all_scores, key=lambda x: x[1], reverse=True)[:3]
            print(f"[VoiceOptimizer] 📋 상위 후보 구간:")
            for i, (start, score) in enumerate(top_candidates):
                print(f"  {i+1}. {start/1000:.1f}~{(start+target_ms)/1000:.1f}초 (점수: {score:.3f})")
        elif best_score >= 0.7:
            print(f"[VoiceOptimizer] ✅ 좋은 품질의 구간 발견!")

        return audio[best_start:best_start + target_ms]

    def _calculate_segment_quality(
        self,
        segment: AudioSegment,
        start_ms: int,
        total_ms: int
    ) -> float:
        """
        구간 품질 점수 계산 (개선된 알고리즘)

        점수 구성:
        - 음성비율(35%): 묵음이 적을수록 좋음
        - 에너지 적절성(20%): 너무 작거나 크지 않아야 함
        - 억양 다양성(25%): 표현력이 풍부할수록 좋음
        - 위치점수(20%): 시작보다 중간 선호
        """

        # 1. 음성 비율 (35%)
        try:
            nonsilent = detect_nonsilent(
                segment,
                min_silence_len=100,
                silence_thresh=-40
            )
            speech_ms = sum(end - start for start, end in nonsilent) if nonsilent else len(segment)
            speech_ratio = speech_ms / len(segment)
            speech_score = min(speech_ratio / 0.7, 1.0)  # 70% 이상이면 만점
        except:
            speech_score = 0.7

        # 2. 에너지 적절성 (20%)
        try:
            samples = np.array(segment.get_array_of_samples()).astype(np.float32)
            samples = samples / 32768.0  # 정규화

            # 프레임별 RMS
            frame_size = len(samples) // 40  # 40개 프레임
            if frame_size > 0:
                rms_values = []
                for i in range(0, len(samples) - frame_size, frame_size):
                    frame = samples[i:i + frame_size]
                    rms = np.sqrt(np.mean(frame**2))
                    rms_values.append(rms)

                if rms_values:
                    mean_rms = np.mean(rms_values)
                    # 이상적 범위: 0.02 ~ 0.15
                    if 0.02 < mean_rms < 0.15:
                        energy_score = 1.0
                    elif 0.01 < mean_rms < 0.25:
                        energy_score = 0.7
                    else:
                        energy_score = 0.3
                else:
                    energy_score = 0.5
            else:
                energy_score = 0.5
        except:
            energy_score = 0.5

        # 3. 억양 다양성 (25%) - 에너지 변화량
        try:
            if 'rms_values' in dir() and rms_values and len(rms_values) > 1:
                energy_std = np.std(rms_values)
                variance_score = min(energy_std * 25, 1.0)
            else:
                variance_score = 0.5
        except:
            variance_score = 0.5

        # 4. 위치 점수 (20%) - 시작보다 중간 선호
        position = start_ms / total_ms
        # 10%~50% 구간 선호
        if 0.1 <= position <= 0.5:
            position_score = 1.0
        elif position < 0.1:
            position_score = position * 10  # 0~0.1 → 0~1
        else:
            position_score = max(0, 1.0 - (position - 0.5) * 2)  # 0.5~1 → 1~0

        # 종합 점수
        score = (
            speech_score * 0.35 +
            energy_score * 0.20 +
            variance_score * 0.25 +
            position_score * 0.20
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

    def is_optimization_needed(self, audio_path: str) -> Tuple[bool, str]:
        """
        최적화 필요 여부 확인

        Returns:
            (needed: bool, reason: str)
        """

        if not os.path.exists(audio_path):
            return False, "파일 없음"

        # 이미 최적화된 음성인지 확인
        if self.profile_manager:
            profile = self.profile_manager.get_profile(audio_path)
            if profile and profile.get("is_optimized"):
                return False, "이미 최적화된 음성"

            # 최적화 버전이 있는지 확인
            if profile:
                opt_profile = self.profile_manager.get_optimized_version(profile["id"])
                if opt_profile:
                    return False, f"최적화 버전 있음: {opt_profile['name']}"

        # 길이 확인
        try:
            audio = AudioSegment.from_file(audio_path)
            duration_sec = len(audio) / 1000

            if duration_sec < self.OPTIMIZATION_THRESHOLD_SEC:
                return False, f"충분히 짧음 ({duration_sec:.0f}초)"

            return True, f"최적화 필요 ({duration_sec:.0f}초 → {self.OPTIMAL_TARGET_SEC}초)"

        except Exception as e:
            return False, f"분석 실패: {e}"

    def get_optimized_path_if_exists(self, audio_path: str) -> Optional[str]:
        """
        이미 최적화된 버전이 있으면 그 경로 반환

        Returns:
            최적화된 음성 경로 또는 None
        """

        # 프로필 관리자에서 최적화 버전 확인
        if self.profile_manager:
            profile = self.profile_manager.get_profile(audio_path)
            if profile:
                # 자체가 최적화된 음성이면 그대로 반환
                if profile.get("is_optimized"):
                    return profile.get("audio_path")

                # 최적화 버전 찾기
                opt_profile = self.profile_manager.get_optimized_version(profile["id"])
                if opt_profile and os.path.exists(opt_profile.get("audio_path", "")):
                    return opt_profile["audio_path"]

        # 캐시에서 확인 (하위호환)
        cache_path = self._get_cache_path(audio_path)
        if cache_path.exists():
            return str(cache_path)

        return None

    def optimize_and_register(
        self,
        audio_path: str,
        original_transcript: str = None,
        custom_name: str = None
    ) -> Dict:
        """
        음성 최적화 후 새 프로필로 등록

        1. 최적 구간 추출
        2. 텍스트 구간도 추출 (있는 경우)
        3. default 폴더에 저장
        4. 새 프로필로 등록

        Args:
            audio_path: 원본 음성 경로
            original_transcript: 원본 텍스트 (없으면 프로필에서 가져옴)
            custom_name: 커스텀 이름 (없으면 "원본명_최적화")

        Returns:
            {
                "success": bool,
                "optimized_path": str,
                "optimized_transcript": str,  # 추출된 구간의 텍스트
                "profile": Dict,              # 새 프로필
                "original_duration": float,
                "optimized_duration": float,
            }
        """

        print(f"\n[VoiceOptimizer] 최적화 및 등록 시작")

        if not os.path.exists(audio_path):
            return {"success": False, "error": "파일 없음"}

        # 프로필 확인
        original_profile = None
        if self.profile_manager:
            original_profile = self.profile_manager.get_profile(audio_path)

        # 텍스트 확인
        if original_transcript is None and original_profile:
            original_transcript = original_profile.get("transcript")

        # 오디오 로드
        try:
            audio = AudioSegment.from_file(audio_path)
        except Exception as e:
            return {"success": False, "error": f"로드 실패: {e}"}

        original_duration = len(audio) / 1000
        print(f"  원본 길이: {original_duration:.1f}초")

        # 최적화 불필요 확인
        if self.OPTIMAL_MIN_SEC <= original_duration <= self.OPTIMAL_MAX_SEC:
            print(f"  ✅ 이미 최적 범위, 프로필만 업데이트")

            if original_profile and self.profile_manager:
                # is_optimized 플래그만 추가
                original_profile["is_optimized"] = True
                self.profile_manager.save_profiles()

            return {
                "success": True,
                "optimized_path": audio_path,
                "optimized_transcript": original_transcript,
                "profile": original_profile,
                "original_duration": original_duration,
                "optimized_duration": original_duration,
                "already_optimal": True,
            }

        # 최적 구간 추출 (품질 점수 포함)
        best_start_ms, best_segment, quality_score = self._extract_best_segment_with_position(audio)
        optimized_duration = len(best_segment) / 1000
        best_end_ms = best_start_ms + len(best_segment)

        # 텍스트 구간 추출 (비율 기반)
        optimized_transcript = None
        if original_transcript:
            optimized_transcript = self._extract_transcript_segment(
                original_transcript,
                best_start_ms,
                len(best_segment),
                len(audio)
            )
            print(f"  텍스트 추출: {len(original_transcript)}자 → {len(optimized_transcript)}자")

        # 저장 경로 결정
        original_name = Path(audio_path).stem
        if custom_name:
            new_name = custom_name
        else:
            new_name = f"{original_name}_최적화"

        save_path = self.default_dir / f"{new_name}.mp3"

        # 중복 방지
        counter = 1
        while save_path.exists():
            save_path = self.default_dir / f"{new_name}_{counter}.mp3"
            counter += 1

        # 저장
        best_segment.export(
            str(save_path),
            format="mp3",
            parameters=["-q:a", "2"]
        )

        # ⭐ 메타데이터 저장 (OptimizedVersionManager 연동)
        try:
            version_manager = get_version_manager()
            version_manager.save_version_metadata(
                filename=save_path.name,
                start_time=best_start_ms / 1000,
                end_time=best_end_ms / 1000,
                quality_score=quality_score,
                source_file=audio_path
            )
        except Exception as e:
            print(f"  ⚠️ 메타데이터 저장 실패: {e}")

        print(f"  ✅ 저장: {save_path.name}")
        print(f"  길이: {original_duration:.1f}초 → {optimized_duration:.1f}초")

        # 프로필 등록
        new_profile = None
        if self.profile_manager:
            original_id = original_profile["id"] if original_profile else None

            new_profile = self.profile_manager.add_profile(
                voice_id=new_name.lower().replace(" ", "_"),
                name=new_name,
                audio_path=str(save_path),
                transcript=optimized_transcript,
                is_optimized=True,
                original_id=original_id,
            )

            # 텍스트 파일도 저장
            if optimized_transcript:
                txt_path = save_path.with_suffix(".txt")
                try:
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(optimized_transcript)
                    print(f"  📝 텍스트 저장: {txt_path.name}")
                except:
                    pass

        return {
            "success": True,
            "optimized_path": str(save_path),
            "optimized_transcript": optimized_transcript,
            "profile": new_profile,
            "original_duration": original_duration,
            "optimized_duration": optimized_duration,
            "quality_score": quality_score,
            "start_time": best_start_ms / 1000,
            "end_time": best_end_ms / 1000,
        }

    def _extract_best_segment_with_position(
        self,
        audio: AudioSegment
    ) -> Tuple[int, AudioSegment, float]:
        """
        최적 구간 추출 (시작 위치, 세그먼트, 품질 점수 함께 반환)

        Returns:
            (best_start_ms, segment, quality_score)
        """

        duration_ms = len(audio)
        target_ms = self.OPTIMAL_TARGET_SEC * 1000

        best_score = -1
        best_start = 0

        step_ms = 1000

        for start_ms in range(0, duration_ms - target_ms, step_ms):
            segment = audio[start_ms:start_ms + target_ms]
            score = self._calculate_segment_quality(segment, start_ms, duration_ms)

            if score > best_score:
                best_score = score
                best_start = start_ms

        print(f"  최적 구간: {best_start/1000:.1f}초 ~ {(best_start + target_ms)/1000:.1f}초")
        print(f"  품질 점수: {best_score:.3f}")

        return best_start, audio[best_start:best_start + target_ms], best_score

    def _extract_transcript_segment(
        self,
        original_text: str,
        start_ms: int,
        segment_ms: int,
        total_ms: int
    ) -> str:
        """
        텍스트에서 해당 구간 추출

        비율 기반으로 추정 (정확하지 않을 수 있음)
        """

        if not original_text:
            return ""

        start_ratio = start_ms / total_ms
        end_ratio = (start_ms + segment_ms) / total_ms

        # 글자 위치 계산
        total_chars = len(original_text)
        start_char = int(total_chars * start_ratio)
        end_char = int(total_chars * end_ratio)

        # 문장 경계 조정 (가능하면)
        # 시작점: 앞쪽 문장 시작으로
        while start_char > 0 and original_text[start_char - 1] not in ".!?\n":
            start_char -= 1

        # 끝점: 뒤쪽 문장 끝으로
        while end_char < total_chars and original_text[end_char - 1] not in ".!?\n":
            end_char += 1

        return original_text[start_char:end_char].strip()


# VoiceOptimizer 싱글톤
_voice_optimizer = None

def get_voice_optimizer() -> VoiceOptimizer:
    """VoiceOptimizer 싱글톤"""
    global _voice_optimizer
    if _voice_optimizer is None:
        _voice_optimizer = VoiceOptimizer(get_profile_manager())
    return _voice_optimizer


def optimize_voice_for_cloning(audio_path: str, force: bool = False) -> str:
    """
    Voice cloning을 위해 참조 음성 최적화 (간편 함수)

    사용 예:
        optimized_path = optimize_voice_for_cloning("path/to/long_voice.mp3")
        # 15~30초 구간으로 최적화된 경로 반환
    """
    return get_voice_optimizer().optimize_for_cloning(audio_path, force)


def optimize_and_register_voice(
    audio_path: str,
    transcript: str = None,
    custom_name: str = None
) -> Dict:
    """
    음성 최적화 후 새 프로필로 등록 (간편 함수)

    사용 예:
        result = optimize_and_register_voice("path/to/long_voice.mp3")
        if result["success"]:
            print(f"새 음성: {result['optimized_path']}")
            print(f"새 프로필: {result['profile']['name']}")
    """
    return get_voice_optimizer().optimize_and_register(audio_path, transcript, custom_name)


def is_voice_optimization_needed(audio_path: str) -> Tuple[bool, str]:
    """
    최적화 필요 여부 확인 (간편 함수)

    Returns:
        (needed: bool, reason: str)
    """
    return get_voice_optimizer().is_optimization_needed(audio_path)


def get_optimized_voice_path(audio_path: str) -> Optional[str]:
    """
    이미 최적화된 버전이 있으면 그 경로 반환 (간편 함수)

    Returns:
        최적화된 음성 경로 또는 None
    """
    return get_voice_optimizer().get_optimized_path_if_exists(audio_path)


# ============================================================
# OptimizedVersionManager - 최적화 버전 관리자
# ============================================================

class OptimizedVersionManager:
    """
    최적화된 음성 버전 관리자

    기능:
    1. 특정 음성의 모든 최적화 버전 스캔
    2. 버전 메타데이터 관리 (구간, 품질 점수, 생성일 등)
    3. 추천 버전 반환 (품질 점수 기준)
    """

    def __init__(self, voice_samples_path: str = None):
        if voice_samples_path is None:
            project_root = Path(__file__).parent.parent.resolve()
            self.voice_samples_path = project_root / "data" / "voice_samples"
        else:
            self.voice_samples_path = Path(voice_samples_path)

        self.optimized_path = self.voice_samples_path / "optimized"
        self.default_path = self.voice_samples_path / "default"
        self.metadata_file = self.optimized_path / "versions_metadata.json"

        # 디렉토리 생성
        self.optimized_path.mkdir(parents=True, exist_ok=True)

        # 메타데이터 로드
        self.metadata = self._load_metadata()

        print(f"[OptimizedVersionManager] 초기화")
        print(f"  경로: {self.voice_samples_path}")

    def _load_metadata(self) -> dict:
        """메타데이터 파일 로드"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[OptimizedVersionManager] 메타데이터 로드 오류: {e}")
        return {"versions": {}}

    def _save_metadata(self):
        """메타데이터 저장"""
        try:
            self.optimized_path.mkdir(parents=True, exist_ok=True)
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[OptimizedVersionManager] 메타데이터 저장 오류: {e}")

    def scan_optimized_versions(self, voice_name: str) -> List[Dict]:
        """
        특정 음성의 모든 최적화 버전 스캔

        Args:
            voice_name: 원본 음성 이름 (확장자 제외)

        Returns:
            List[Dict]: 버전 정보 리스트 (최신 순 정렬)
            [
                {
                    "filename": "세모지__opt_0a9f615c.mp3",
                    "filepath": "C:\\...\\optimized\\세모지__opt_0a9f615c.mp3",
                    "start_time": 54.0,
                    "end_time": 74.0,
                    "duration": 20.0,
                    "quality_score": 1.000,
                    "created_at": "2026-01-05 12:34:56",
                    "is_latest": True
                },
                ...
            ]
        """
        versions = []

        # 음성 이름 정규화 (확장자 제거, 언더스코어 처리)
        voice_name_clean = Path(voice_name).stem.replace(" ", "_")
        # 이미 _최적화가 포함된 경우 원본 이름 추출
        if "_최적화" in voice_name_clean:
            voice_name_clean = voice_name_clean.split("_최적화")[0]
        if "_opt_" in voice_name_clean:
            voice_name_clean = voice_name_clean.split("_opt_")[0]
        if "__manual_" in voice_name_clean:
            voice_name_clean = voice_name_clean.split("__manual_")[0]
        # ⭐ 끝의 연속 언더스코어 제거
        voice_name_clean = voice_name_clean.rstrip('_')

        print(f"[OptimizedVersionManager] 버전 스캔: '{voice_name}' → '{voice_name_clean}'")

        # 1. optimized 폴더 스캔 (⭐ _opt_, __manual_ 패턴 모두 인식)
        if self.optimized_path.exists():
            for filepath in self.optimized_path.iterdir():
                if filepath.suffix.lower() in ['.mp3', '.wav', '.m4a']:
                    filename = filepath.stem
                    # ⭐ 파일명도 정규화하여 비교
                    filename_base = filename
                    if "_opt_" in filename_base:
                        filename_base = filename_base.split("_opt_")[0]
                    elif "__manual_" in filename_base:
                        filename_base = filename_base.split("__manual_")[0]
                    filename_base = filename_base.rstrip('_')

                    # 매칭 조건: 정규화된 이름이 일치하고 _opt_ 또는 __manual_ 포함
                    if filename_base == voice_name_clean and ("_opt_" in filename or "__manual_" in filename):
                        version_info = self._get_version_info(filepath)
                        if version_info:
                            versions.append(version_info)

        # 2. default 폴더에서 _최적화 파일 스캔
        if self.default_path.exists():
            for filepath in self.default_path.iterdir():
                if filepath.suffix.lower() in ['.mp3', '.wav', '.m4a']:
                    filename = filepath.stem
                    # ⭐ 파일명도 정규화하여 비교
                    filename_base = filename
                    if "_최적화" in filename_base:
                        filename_base = filename_base.split("_최적화")[0]
                    filename_base = filename_base.rstrip('_')

                    # 매칭 조건: 정규화된 이름이 일치하고 _최적화 포함
                    if filename_base == voice_name_clean and "_최적화" in filename:
                        version_info = self._get_version_info(filepath)
                        if version_info:
                            versions.append(version_info)

        # 3. 생성일 기준 정렬 (최신 순)
        versions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        # 4. 최신 버전 표시
        if versions:
            versions[0]["is_latest"] = True

        print(f"[OptimizedVersionManager] 발견된 버전: {len(versions)}개")
        for v in versions[:5]:  # 상위 5개만 로그
            opt_type = "📌수동" if v.get("is_manual") else "🤖자동"
            print(f"  - {v['filename']} ({opt_type}, 품질: {v.get('quality_score', 0):.3f})")

        return versions

    def _get_version_info(self, filepath: Path) -> Optional[Dict]:
        """개별 버전 정보 추출"""
        try:
            from datetime import datetime
            import re

            filename = filepath.name

            # 파일 수정 시간
            stat = filepath.stat()
            created_at = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

            # 오디오 길이 확인
            try:
                audio = AudioSegment.from_file(str(filepath))
                duration = len(audio) / 1000
            except:
                duration = 0

            # 메타데이터에서 추가 정보 로드
            meta_key = filepath.name
            meta = self.metadata.get("versions", {}).get(meta_key, {})

            # ⭐ 파일명에서도 is_manual 판단 (메타데이터 없을 경우 대비)
            is_manual_from_filename = "__manual_" in filename
            is_manual = meta.get("is_manual", is_manual_from_filename)

            # ⭐ 파일명에서 구간 정보 추출 (예: _120-140s_)
            start_time = meta.get("start_time", 0)
            end_time = meta.get("end_time", duration)
            time_match = re.search(r'_(\d+)-(\d+)s_', filename)
            if time_match and start_time == 0:
                start_time = float(time_match.group(1))
                end_time = float(time_match.group(2))

            # ⭐ 발화속도 정보
            speaking_rate = meta.get("speaking_rate")

            return {
                "filename": filename,
                "filepath": str(filepath),
                "start_time": start_time,
                "end_time": end_time,
                "duration": duration,
                "quality_score": meta.get("quality_score", 0.0),
                "created_at": created_at,
                "is_latest": False,
                "source_file": meta.get("source_file", ""),
                "is_manual": is_manual,  # ⭐ 수동/자동 구분
                "speaking_rate": speaking_rate,  # ⭐ 발화속도
            }
        except Exception as e:
            print(f"[OptimizedVersionManager] 버전 정보 로드 실패: {filepath.name} - {e}")
            return None

    def save_version_metadata(
        self,
        filename: str,
        start_time: float = 0,
        end_time: float = 0,
        quality_score: float = 0,
        source_file: str = "",
        **kwargs
    ):
        """
        버전 메타데이터 저장

        Args:
            filename: 최적화된 파일명
            start_time: 원본에서의 시작 시간 (초)
            end_time: 원본에서의 종료 시간 (초)
            quality_score: 품질 점수 (0~1)
            source_file: 원본 파일 경로
        """
        from datetime import datetime

        metadata = {
            "start_time": start_time,
            "end_time": end_time,
            "quality_score": quality_score,
            "source_file": source_file,
            "created_at": datetime.now().isoformat(),
            **kwargs
        }

        self.metadata.setdefault("versions", {})[filename] = metadata
        self._save_metadata()

        print(f"[OptimizedVersionManager] 메타데이터 저장: {filename}")
        print(f"  구간: {start_time:.1f}~{end_time:.1f}초, 품질: {quality_score:.3f}")

    def get_recommended_version(self, voice_name: str) -> Optional[Dict]:
        """
        추천 버전 반환 (품질 점수 기준)

        품질 점수가 같으면 최신 버전 우선
        """
        versions = self.scan_optimized_versions(voice_name)
        if not versions:
            return None

        # 품질 점수 기준 정렬 (품질 > 최신)
        sorted_versions = sorted(
            versions,
            key=lambda x: (x.get("quality_score", 0), x.get("created_at", "")),
            reverse=True
        )

        return sorted_versions[0]

    def delete_version(self, filepath: str) -> bool:
        """버전 삭제"""
        try:
            path = Path(filepath)
            if path.exists():
                path.unlink()

                # 메타데이터에서도 삭제
                filename = path.name
                if filename in self.metadata.get("versions", {}):
                    del self.metadata["versions"][filename]
                    self._save_metadata()

                print(f"[OptimizedVersionManager] 삭제됨: {filename}")
                return True
        except Exception as e:
            print(f"[OptimizedVersionManager] 삭제 실패: {e}")
        return False


# OptimizedVersionManager 싱글톤
_version_manager = None

def get_version_manager() -> OptimizedVersionManager:
    """OptimizedVersionManager 싱글톤"""
    global _version_manager
    if _version_manager is None:
        _version_manager = OptimizedVersionManager()
    return _version_manager


def scan_optimized_versions(voice_name: str) -> List[Dict]:
    """
    특정 음성의 모든 최적화 버전 스캔 (간편 함수)

    Args:
        voice_name: 원본 음성 이름 (경로 또는 파일명)

    Returns:
        List[Dict]: 버전 정보 리스트
    """
    return get_version_manager().scan_optimized_versions(voice_name)


def get_recommended_optimized_version(voice_name: str) -> Optional[Dict]:
    """
    추천 최적화 버전 반환 (간편 함수)

    Returns:
        추천 버전 정보 또는 None
    """
    return get_version_manager().get_recommended_version(voice_name)


def create_manual_optimized_voice(
    audio_path: str,
    start_sec: float,
    end_sec: float,
    quality_score: float = 0,
    normalize: bool = True,
    noise_reduce: bool = True
) -> Dict:
    """
    수동으로 선택한 구간으로 최적화 버전 생성

    Args:
        audio_path: 원본 음성 경로
        start_sec: 시작 시간 (초)
        end_sec: 끝 시간 (초)
        quality_score: 품질 점수 (0-100)
        normalize: 정규화 여부
        noise_reduce: 노이즈 제거 여부

    Returns:
        {
            "success": bool,
            "optimized_path": str,
            "start_sec": float,
            "end_sec": float,
            "duration": float,
            "quality_score": float,
            "is_manual": True,
            "error": str (실패 시)
        }
    """
    try:
        import time
        import hashlib

        audio_path = Path(audio_path)
        if not audio_path.exists():
            return {"success": False, "error": f"파일 없음: {audio_path}"}

        # 구간 유효성 검사
        duration = end_sec - start_sec
        if duration < 5:
            return {"success": False, "error": "최소 5초 이상 필요"}
        if duration > 30:
            return {"success": False, "error": "최대 30초까지 가능"}

        print(f"\n[ManualOptimize] 수동 최적화 시작")
        print(f"  원본: {audio_path.name}")
        print(f"  구간: {start_sec:.1f}~{end_sec:.1f}초 ({duration:.1f}초)")

        # 원본 오디오 로드
        audio = AudioSegment.from_file(str(audio_path))

        # 구간 추출 (밀리초)
        start_ms = int(start_sec * 1000)
        end_ms = int(end_sec * 1000)
        segment = audio[start_ms:end_ms]

        # 정규화
        if normalize:
            target_dBFS = -20.0
            change = target_dBFS - segment.dBFS
            segment = segment.apply_gain(change)
            print(f"[ManualOptimize] 정규화 적용: {change:.1f}dB")

        # 출력 경로 생성
        timestamp = int(time.time() * 1000)
        hash_suffix = hashlib.md5(f"{start_sec}_{end_sec}_{timestamp}".encode()).hexdigest()[:8]
        voice_name = audio_path.stem.replace(" ", "_")
        # 원본 이름에서 이전 최적화 접미사 제거
        if "_최적화" in voice_name:
            voice_name = voice_name.split("_최적화")[0]
        if "_opt_" in voice_name:
            voice_name = voice_name.split("_opt_")[0]

        output_filename = f"{voice_name}_opt_{hash_suffix}.mp3"

        # optimized 폴더 경로
        voices_dir = Path("voices")
        optimized_dir = voices_dir / "optimized"
        optimized_dir.mkdir(parents=True, exist_ok=True)

        output_path = optimized_dir / output_filename

        # 저장
        segment.export(str(output_path), format="mp3", bitrate="192k")
        print(f"[ManualOptimize] 저장: {output_path}")

        # 노이즈 제거 (비활성화 - librosa 필요)
        if noise_reduce:
            print(f"[ManualOptimize] ⚠️ 노이즈 제거는 비활성화됨 (librosa 필요)")

        # 메타데이터 저장
        normalized_quality = quality_score / 100.0  # 0-100 → 0-1 변환
        get_version_manager().save_version_metadata(
            filename=output_filename,
            start_time=start_sec,
            end_time=end_sec,
            quality_score=normalized_quality,
            source_file=str(audio_path),
            is_manual=True  # ⭐ 수동 선택 표시
        )

        print(f"[ManualOptimize] ✅ 완료!")

        return {
            "success": True,
            "optimized_path": str(output_path),
            "start_sec": start_sec,
            "end_sec": end_sec,
            "duration": duration,
            "quality_score": normalized_quality,
            "is_manual": True
        }

    except Exception as e:
        import traceback
        print(f"[ManualOptimize] ❌ 실패: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}
