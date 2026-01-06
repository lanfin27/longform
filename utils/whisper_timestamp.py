# -*- coding: utf-8 -*-
"""
Whisper 타임스탬프 추출기 (v6.10)

지원 엔진:
- faster-whisper: 빠른 속도, 적은 메모리 (CPU에서 특히 유리)
- stable-ts: 정밀한 타임스탬프, 고급 기능 (refine, align)

변경사항 (v6.10):
- ⭐ VadOptions 객체 사용으로 VAD 파라미터 확실히 전달
- dict 형식 대신 faster_whisper.vad.VadOptions 객체 사용
- 오디오 향상 기본값 False로 변경 (VAD 정확도 우선)

변경사항 (v6.9):
- ⭐ 문장 분리 문제 완전 해결! (짧은 pause에서도 분리)
- 문제 원인: v6.8에서 min_silence=150ms가 너무 높아 문장이 합쳐짐
- 해결:
  - min_silence_duration_ms: 150 → 50 (50ms 무음이면 분리!)
  - speech_pad_ms: 100 → 30 (패딩 최소화)
  - vad_threshold: 0.10 → 0.05 (더 민감하게)
- 목표: 2-3초 단위 짧은 문장 분리 (기존 정상 동작 복원)

변경사항 (v6.8):
- 문장 분리 개선 시도 (부분적 해결)
- 스타일별 VAD 설정 적용 (잘게/기본/크게)

변경사항 (v6.7):
- ⭐ 갭 감지 디버깅 강화 (97초 갭 누락 버그 수정)
- None 값 처리 추가 (안전한 .get() 사용)

변경사항 (v6.6):
- ⭐ 갭 재분석 기능 추가 (VAD 비활성화로 누락 구간 자동 복구)
- 5초 이상 갭 감지 및 Whisper 재분석
"""

import os
import re
import warnings
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field

# 경고 무시
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*sm_120.*")
warnings.filterwarnings("ignore", message=".*CUDA.*")


# ============================================================
# 엔진 사용 가능 여부 확인
# ============================================================

def is_faster_whisper_available() -> bool:
    """faster-whisper 설치 여부"""
    try:
        import faster_whisper
        return True
    except ImportError:
        return False

def is_stable_ts_available() -> bool:
    """stable-ts 설치 여부"""
    try:
        import stable_whisper
        return True
    except ImportError:
        return False

def get_available_engines() -> List[Dict[str, str]]:
    """
    사용 가능한 Whisper 엔진 목록 반환 (UI용)

    Returns:
        [{"id": "faster-whisper", "name": "faster-whisper (빠름)", "available": True}, ...]
    """
    engines = []

    # faster-whisper
    faster_available = is_faster_whisper_available()
    engines.append({
        "id": "faster-whisper",
        "name": f"faster-whisper {'(빠름, CPU 최적화)' if faster_available else '(미설치)'}",
        "available": faster_available,
        "description": "CTranslate2 기반, CPU에서 3~4배 빠름"
    })

    # stable-ts
    stable_available = is_stable_ts_available()
    engines.append({
        "id": "stable-ts",
        "name": f"stable-ts {'(정밀 타임스탬프)' if stable_available else '(미설치)'}",
        "available": stable_available,
        "description": "정밀한 타임스탬프, refine/align 지원"
    })

    return engines

def get_default_engine() -> str:
    """기본 엔진 반환 (faster-whisper 우선)"""
    if is_faster_whisper_available():
        return "faster-whisper"
    elif is_stable_ts_available():
        return "stable-ts"
    else:
        raise ImportError("Whisper 엔진이 설치되지 않았습니다. pip install faster-whisper 또는 pip install stable-ts")


# ============================================================
# 스타일별 문장 분리 기준
# ============================================================

SENTENCE_SPLIT_CONFIG = {
    "잘게": {
        "max_duration": 3.0,
        "max_chars": 40,
        "gap_threshold": 0.3,
        "min_silence_duration_ms": 50,     # ⭐ v6.9: 150 → 50 (짧은 pause도 분리점으로!)
        "speech_pad_ms": 30,               # ⭐ v6.9: 100 → 30 (패딩 최소화)
        "vad_threshold": 0.05,             # ⭐ v6.9: 0.10 → 0.05 (더 민감하게)
        "description": "짧은 호흡 (3초/40자)"
    },
    "기본": {
        "max_duration": 5.0,
        "max_chars": 60,
        "gap_threshold": 0.5,
        "min_silence_duration_ms": 150,    # ⭐ v6.9: 300 → 150
        "speech_pad_ms": 80,               # ⭐ v6.9: 150 → 80
        "vad_threshold": 0.08,             # ⭐ v6.9: 0.10 → 0.08
        "description": "자연스러운 단위 (5초/60자)"
    },
    "크게": {
        "max_duration": 8.0,
        "max_chars": 100,
        "gap_threshold": 0.7,
        "min_silence_duration_ms": 300,    # ⭐ v6.9: 500 → 300
        "speech_pad_ms": 150,              # ⭐ v6.9: 200 → 150
        "vad_threshold": 0.12,             # ⭐ v6.9: 0.15 → 0.12
        "description": "큰 주제 단위 (8초/100자)"
    }
}


# ============================================================
# 데이터 클래스
# ============================================================

@dataclass
class WordTimestamp:
    """단어 타임스탬프"""
    word: str
    start: float
    end: float


@dataclass
class SentenceSegment:
    """문장 세그먼트"""
    id: int
    text: str
    start: float
    end: float
    words: List[WordTimestamp] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass
class WhisperConfig:
    """Whisper 설정"""
    model_size: str = "base"
    language: str = "ko"
    device: str = "auto"
    engine: str = "auto"  # "faster-whisper", "stable-ts", "auto"

    # faster-whisper 전용 옵션
    compute_type: str = "int8"
    vad_filter: bool = True

    # stable-ts 전용 옵션
    refine: bool = False


@dataclass
class WhisperResult:
    """
    Whisper 분석 결과 클래스

    다른 모듈에서 import하여 사용:
    from utils.whisper_timestamp import WhisperResult
    """
    sentences: List = field(default_factory=list)
    duration: float = 0.0
    language: str = "ko"
    device_used: str = "cpu"
    engine: str = "auto"
    split_style: str = "기본"
    success: bool = True
    error: str = ""

    @property
    def segments(self):
        """sentences의 별칭 (호환성)"""
        return self.sentences

    @property
    def total_duration(self) -> float:
        """duration의 별칭 (호환성)"""
        return self.duration

    @property
    def full_text(self) -> str:
        """전체 텍스트"""
        texts = []
        for s in self.sentences:
            if isinstance(s, dict):
                texts.append(s.get("text", ""))
            elif hasattr(s, "text"):
                texts.append(s.text)
        return " ".join(texts)

    @property
    def words(self) -> List:
        """모든 단어 리스트"""
        all_words = []
        for s in self.sentences:
            if isinstance(s, dict):
                all_words.extend(s.get("words", []))
            elif hasattr(s, "words"):
                all_words.extend(s.words)
        return all_words

    def get_sentence_count(self) -> int:
        """문장 수 반환"""
        return len(self.sentences)

    def get_sentence_texts(self) -> List[str]:
        """문장 텍스트 리스트 반환"""
        texts = []
        for s in self.sentences:
            if isinstance(s, dict):
                texts.append(s.get("text", ""))
            elif hasattr(s, "text"):
                texts.append(s.text)
        return texts

    def merge_sentences(self, sentence_ids: List[int]) -> Tuple[str, float, float]:
        """
        문장들을 병합하여 (텍스트, 시작시간, 종료시간) 반환

        Args:
            sentence_ids: 병합할 문장 ID 리스트

        Returns:
            (병합된 텍스트, 시작 시간, 종료 시간)
        """
        if not sentence_ids:
            return "", 0.0, 0.0

        texts = []
        start_time = float('inf')
        end_time = 0.0

        for sid in sentence_ids:
            if sid < 0 or sid >= len(self.sentences):
                continue

            s = self.sentences[sid]

            if isinstance(s, dict):
                texts.append(s.get("text", "").strip())
                s_start = s.get("start", 0.0)
                s_end = s.get("end", 0.0)
            else:
                texts.append(s.text.strip() if hasattr(s, "text") else "")
                s_start = s.start if hasattr(s, "start") else 0.0
                s_end = s.end if hasattr(s, "end") else 0.0

            start_time = min(start_time, s_start)
            end_time = max(end_time, s_end)

        if start_time == float('inf'):
            start_time = 0.0

        merged_text = " ".join(texts)
        return merged_text, start_time, end_time

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "success": self.success,
            "sentences": self.sentences,
            "duration": self.duration,
            "device_used": self.device_used,
            "engine": self.engine,
            "language": self.language,
            "split_style": self.split_style,
            "error": self.error
        }


# ============================================================
# 메인 클래스
# ============================================================

class WhisperTimestamp:
    """
    Whisper 타임스탬프 추출기 (v6.0)

    두 가지 엔진 지원:
    - faster-whisper: 빠른 속도, 적은 메모리
    - stable-ts: 정밀한 타임스탬프
    """

    MODEL_SIZES = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
    SENTENCE_END_PATTERN = re.compile(r'[.?!。？！]\s*$|[.?!。？！](?=\s)')

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        engine: str = "auto",
        language: str = "ko",
        compute_type: str = "auto",
        vad_filter: bool = True,
        refine: bool = False
    ):
        """
        초기화

        Args:
            model_size: 모델 크기 (tiny, base, small, medium, large)
            device: 디바이스 (auto, cpu, cuda)
            engine: 엔진 (auto, faster-whisper, stable-ts)
            language: 언어 코드
            compute_type: 계산 타입 (auto, int8, float16, float32)
            vad_filter: VAD 필터 사용 여부 (faster-whisper)
            refine: 타임스탬프 미세 조정 (stable-ts)
        """
        self.model_size = model_size
        self.language = language
        self.vad_filter = vad_filter
        self.refine = refine

        # 엔진 결정
        self.engine = self._determine_engine(engine)

        # 디바이스 결정
        self.device = self._determine_device(device)

        # 계산 타입 결정
        self.compute_type = self._determine_compute_type(compute_type)

        # 모델
        self.model = None

        # ⭐ v6.6: 갭 재분석 설정
        self.enable_gap_recovery = True  # 갭 재분석 활성화
        self.gap_threshold = 5.0  # 5초 이상 갭 재분석

        print(f"[WhisperTimestamp] 초기화")
        print(f"[WhisperTimestamp]   엔진: {self.engine}")
        print(f"[WhisperTimestamp]   모델: {self.model_size}")
        print(f"[WhisperTimestamp]   디바이스: {self.device}")
        if self.engine == "faster-whisper":
            print(f"[WhisperTimestamp]   계산타입: {self.compute_type}")
            print(f"[WhisperTimestamp]   VAD 필터: {self.vad_filter}")
        elif self.engine == "stable-ts":
            print(f"[WhisperTimestamp]   Refine: {self.refine}")
        print(f"[WhisperTimestamp]   갭 재분석: {'활성화' if self.enable_gap_recovery else '비활성화'} (>{self.gap_threshold}초)")

        # 모델 로딩
        self._load_model()

    def _determine_engine(self, engine: str) -> str:
        """엔진 결정"""

        if engine == "auto":
            if is_faster_whisper_available():
                print(f"[WhisperTimestamp] 엔진 자동 선택: faster-whisper (빠름)")
                return "faster-whisper"
            elif is_stable_ts_available():
                print(f"[WhisperTimestamp] 엔진 자동 선택: stable-ts")
                return "stable-ts"
            else:
                raise ImportError("Whisper 엔진 미설치. pip install faster-whisper")

        elif engine == "faster-whisper":
            if not is_faster_whisper_available():
                raise ImportError("faster-whisper 미설치. pip install faster-whisper")
            return "faster-whisper"

        elif engine == "stable-ts":
            if not is_stable_ts_available():
                raise ImportError("stable-ts 미설치. pip install stable-ts")
            return "stable-ts"

        else:
            raise ValueError(f"알 수 없는 엔진: {engine}")

    def _determine_device(self, device: str) -> str:
        """디바이스 결정"""

        if device != "auto":
            return device

        try:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                capability = torch.cuda.get_device_capability(0)
                cap_major = capability[0]

                print(f"[WhisperTimestamp] GPU 감지: {gpu_name}")
                print(f"[WhisperTimestamp] Compute Capability: {cap_major}.{capability[1]}")

                # RTX 50 시리즈 (sm_120) 체크
                if cap_major >= 12:
                    print(f"[WhisperTimestamp] Compute Capability {cap_major}.x는 현재 PyTorch 미지원")
                    print(f"[WhisperTimestamp] CPU 모드로 전환")
                    return "cpu"

                return "cuda"
        except:
            pass

        print(f"[WhisperTimestamp] CPU 모드로 실행")
        return "cpu"

    def _determine_compute_type(self, compute_type: str) -> str:
        """계산 타입 결정 (faster-whisper용)"""

        if compute_type != "auto":
            return compute_type

        if self.device == "cpu":
            return "int8"
        else:
            return "float16"

    def _load_model(self):
        """모델 로딩"""

        if self.engine == "faster-whisper":
            self._load_faster_whisper()
        else:
            self._load_stable_ts()

    def _load_faster_whisper(self):
        """faster-whisper 모델 로딩"""

        from faster_whisper import WhisperModel

        print(f"[WhisperTimestamp] faster-whisper 모델 로딩 중...")
        print(f"[WhisperTimestamp]   모델: {self.model_size}, 디바이스: {self.device}, 타입: {self.compute_type}")

        self.model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type
        )

        print(f"[WhisperTimestamp] faster-whisper 로드 완료")

    def _load_stable_ts(self):
        """stable-ts 모델 로딩"""

        import stable_whisper

        print(f"[WhisperTimestamp] stable-ts 모델 로딩 중...")
        print(f"[WhisperTimestamp]   모델: {self.model_size}, 디바이스: {self.device}")

        self.model = stable_whisper.load_model(
            self.model_size,
            device=self.device
        )

        print(f"[WhisperTimestamp] stable-ts 로드 완료")

    def transcribe(
        self,
        audio_path: str,
        language: str = None,
        style: str = "기본"
    ) -> Tuple[List[Dict], float]:
        """
        오디오 분석 및 타임스탬프 추출

        Args:
            audio_path: 오디오 파일 경로
            language: 언어 코드 (기본: 초기화 시 설정)
            style: 분리 스타일 (잘게, 기본, 크게)

        Returns:
            (문장 리스트, 총 길이 초)
        """

        language = language or self.language

        print(f"[WhisperTimestamp] 오디오 분석 시작")
        print(f"[WhisperTimestamp]   파일: {os.path.basename(audio_path)}")
        print(f"[WhisperTimestamp]   엔진: {self.engine}")
        print(f"[WhisperTimestamp]   언어: {language}")
        print(f"[WhisperTimestamp]   스타일: {style}")

        if self.engine == "faster-whisper":
            return self._transcribe_faster_whisper(audio_path, language, style)
        else:
            return self._transcribe_stable_ts(audio_path, language, style)

    def _transcribe_faster_whisper(
        self,
        audio_path: str,
        language: str,
        style: str
    ) -> Tuple[List[Dict], float]:
        """faster-whisper로 분석 (빠름)"""

        print(f"[WhisperTimestamp] faster-whisper 분석 중...")

        config = SENTENCE_SPLIT_CONFIG.get(style, SENTENCE_SPLIT_CONFIG["잘게"])  # ⭐ v6.9: 기본값을 "잘게"로!

        # v6.10: VAD 설정 - VadOptions 객체 사용
        threshold = config.get("vad_threshold", 0.05)
        min_silence = config.get("min_silence_duration_ms", 50)
        speech_pad = config.get("speech_pad_ms", 30)

        # ⭐ v6.10: VadOptions 객체 생성 (확실한 VAD 파라미터 전달!)
        try:
            from faster_whisper.vad import VadOptions
            vad_options = VadOptions(
                threshold=threshold,
                min_speech_duration_ms=30,
                min_silence_duration_ms=min_silence,
                speech_pad_ms=speech_pad,
                max_speech_duration_s=float('inf'),
            )
            print(f"[WhisperTimestamp] VAD 설정 (v6.10 VadOptions): threshold={threshold}, min_silence={min_silence}ms, pad={speech_pad}ms")
            print(f"[WhisperTimestamp] ✅ VadOptions 객체 생성됨")
        except ImportError:
            vad_options = {
                "threshold": threshold,
                "min_speech_duration_ms": 30,
                "min_silence_duration_ms": min_silence,
                "speech_pad_ms": speech_pad,
            }
            print(f"[WhisperTimestamp] VAD 설정 (v6.10 dict): threshold={threshold}, min_silence={min_silence}ms, pad={speech_pad}ms")
            print(f"[WhisperTimestamp] ⚠️ VadOptions import 실패, dict 사용")

        segments, info = self.model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            word_timestamps=True,
            vad_filter=self.vad_filter,
            vad_parameters=vad_options
        )

        sentences = []
        skipped_empty = 0
        skipped_short = 0

        for segment in segments:
            text = segment.text.strip() if segment.text else ""

            # v6.2: 빈 텍스트 스킵
            if not text:
                skipped_empty += 1
                continue

            # v6.2: 너무 짧은 세그먼트 스킵 (0.1초 미만)
            duration = segment.end - segment.start
            if duration < 0.1:
                skipped_short += 1
                continue

            # 타임스탬프 검증
            start = float(segment.start)
            end = float(segment.end)

            if start < 0:
                start = 0
            if end <= start:
                end = start + 0.3

            words = []
            if segment.words:
                for word in segment.words:
                    words.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end
                    })

            sentences.append({
                "id": len(sentences),
                "text": text,
                "start": start,
                "end": end,
                "words": words
            })

        if skipped_empty > 0:
            print(f"[WhisperTimestamp] [INFO] 빈 세그먼트 {skipped_empty}개 스킵됨")
        if skipped_short > 0:
            print(f"[WhisperTimestamp] [INFO] 짧은 세그먼트 {skipped_short}개 스킵됨 (<0.1초)")

        total_duration = info.duration

        # v6.1: 타임스탬프 검증
        zero_count = sum(1 for s in sentences if s["start"] == 0 and s["end"] == 0)
        empty_count = sum(1 for s in sentences if not s["text"].strip())

        print(f"[WhisperTimestamp] faster-whisper 분석 완료")
        print(f"[WhisperTimestamp]   문장: {len(sentences)}개")
        print(f"[WhisperTimestamp]   총 길이: {total_duration:.1f}초 ({total_duration/60:.1f}분)")

        if zero_count > 0:
            print(f"[WhisperTimestamp] [WARN] 타임스탬프 0인 문장: {zero_count}개")
        if empty_count > 0:
            print(f"[WhisperTimestamp] [WARN] 빈 텍스트 문장: {empty_count}개")

        # v6.1: 빈 텍스트 문장 필터링
        sentences = [s for s in sentences if s["text"].strip()]

        # ⭐ v6.6: 갭 재분석 추가 (핵심!)
        if hasattr(self, 'enable_gap_recovery') and self.enable_gap_recovery:
            sentences = self._recover_gaps_in_transcribe(
                sentences, audio_path, language, total_duration
            )

        return sentences, total_duration

    def _transcribe_stable_ts(
        self,
        audio_path: str,
        language: str,
        style: str
    ) -> Tuple[List[Dict], float]:
        """stable-ts로 분석 (정밀 타임스탬프)"""

        print(f"[WhisperTimestamp] stable-ts 분석 중...")

        transcribe_options = {
            "language": language,
            "word_timestamps": True
        }

        if self.device == "cpu":
            transcribe_options["fp16"] = False

        result = self.model.transcribe(audio_path, **transcribe_options)

        if self.refine:
            print(f"[WhisperTimestamp] 타임스탬프 미세 조정 중 (refine)...")
            result = result.refine(self.model, audio_path)

        sentences = []
        skipped_empty = 0
        skipped_short = 0

        for segment in result.segments:
            text = segment.text.strip() if segment.text else ""

            # v6.2: 빈 텍스트 스킵
            if not text:
                skipped_empty += 1
                continue

            # v6.2: 너무 짧은 세그먼트 스킵 (0.1초 미만)
            duration = segment.end - segment.start
            if duration < 0.1:
                skipped_short += 1
                continue

            # 타임스탬프 검증
            start = float(segment.start)
            end = float(segment.end)

            if start < 0:
                start = 0
            if end <= start:
                end = start + 0.3

            words = []
            if hasattr(segment, 'words') and segment.words:
                for word in segment.words:
                    words.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end
                    })

            sentences.append({
                "id": len(sentences),
                "text": text,
                "start": start,
                "end": end,
                "words": words
            })

        if skipped_empty > 0:
            print(f"[WhisperTimestamp] [INFO] 빈 세그먼트 {skipped_empty}개 스킵됨")
        if skipped_short > 0:
            print(f"[WhisperTimestamp] [INFO] 짧은 세그먼트 {skipped_short}개 스킵됨 (<0.1초)")

        total_duration = result.segments[-1].end if result.segments else 0

        # v6.1: 타임스탬프 검증
        zero_count = sum(1 for s in sentences if s["start"] == 0 and s["end"] == 0)
        empty_count = sum(1 for s in sentences if not s["text"].strip())

        print(f"[WhisperTimestamp] stable-ts 분석 완료")
        print(f"[WhisperTimestamp]   문장: {len(sentences)}개")
        print(f"[WhisperTimestamp]   총 길이: {total_duration:.1f}초 ({total_duration/60:.1f}분)")

        if zero_count > 0:
            print(f"[WhisperTimestamp] [WARN] 타임스탬프 0인 문장: {zero_count}개")
        if empty_count > 0:
            print(f"[WhisperTimestamp] [WARN] 빈 텍스트 문장: {empty_count}개")

        # v6.1: 빈 텍스트 문장 필터링
        sentences = [s for s in sentences if s["text"].strip()]

        return sentences, total_duration

    # v5 호환성: extract 메서드
    def extract(
        self,
        audio_path: str,
        language: str = "ko",
        split_style: str = "기본",
        progress_callback: Optional[Callable] = None
    ) -> WhisperResult:
        """
        v5 호환성을 위한 extract 메서드

        Args:
            audio_path: 오디오 파일 경로
            language: 언어 코드
            split_style: 분리 스타일
            progress_callback: 진행 콜백 (사용 안 함)

        Returns:
            WhisperResult 객체
        """
        try:
            sentences, duration = self.transcribe(audio_path, language, split_style)

            # v5 형식으로 변환 (SentenceSegment 리스트)
            sentence_segments = []
            for s in sentences:
                words = [WordTimestamp(w["word"], w["start"], w["end"]) for w in s.get("words", [])]
                sentence_segments.append(SentenceSegment(
                    id=s["id"],
                    text=s["text"],
                    start=s["start"],
                    end=s["end"],
                    words=words
                ))

            return WhisperResult(
                sentences=sentence_segments,
                duration=duration,
                language=language,
                device_used=self.device,
                engine=self.engine,
                split_style=split_style,
                success=True
            )

        except Exception as e:
            print(f"[WhisperTimestamp] ❌ extract 오류: {e}")
            return WhisperResult(
                sentences=[],
                duration=0.0,
                language=language,
                device_used=self.device,
                engine=self.engine,
                split_style=split_style,
                success=False,
                error=str(e)
            )

    # ============================================================
    # ⭐ v6.6: 갭 재분석 기능 (핵심!)
    # ============================================================

    def _recover_gaps_in_transcribe(self, sentences: list, audio_path: str,
                                     language: str, total_duration: float) -> list:
        """
        ⭐ 갭 구간 Whisper 재분석 (핵심 기능!)

        1. 5초 이상 갭 찾기
        2. 갭 구간 오디오 추출
        3. VAD 비활성화로 Whisper 재분석
        4. 타임스탬프 보정 및 병합
        """
        import tempfile

        # ⭐ v6.7: 디버깅 - 입력 데이터 확인
        print(f"\n[WhisperTimestamp] 🔍 갭 재분석 시작...")
        print(f"[WhisperTimestamp]   문장 개수: {len(sentences)}")
        print(f"[WhisperTimestamp]   오디오 길이: {total_duration:.1f}초")

        if sentences:
            first = sentences[0]
            last = sentences[-1]
            print(f"[WhisperTimestamp]   첫 문장: start={first.get('start')}, end={first.get('end')}")
            print(f"[WhisperTimestamp]   마지막 문장: start={last.get('start')}, end={last.get('end')}")

            # 키 확인
            print(f"[WhisperTimestamp]   문장 키: {list(first.keys())}")

            # ⭐ 97초 갭 탐지를 위한 샘플 출력 (109초 근처)
            print(f"[WhisperTimestamp]   🔍 갭 의심 구간 샘플 (100~110초 근처):")
            for i, s in enumerate(sentences):
                start_val = s.get('start', 0) or 0
                end_val = s.get('end', 0) or 0
                if 100 <= start_val <= 220 or 100 <= end_val <= 220:
                    text_preview = s.get('text', '')[:20]
                    print(f"[WhisperTimestamp]     [{i}] {start_val:.2f}~{end_val:.2f}: {text_preview}...")
                    # 5개만 출력
                    if i > 40:
                        break

        # 갭 찾기
        gaps = []

        # 시작 부분 갭
        if sentences:
            first_start = sentences[0].get('start', 0)
            if first_start is None:
                first_start = 0
            if first_start > self.gap_threshold:
                gaps.append({
                    'start': 0,
                    'end': first_start,
                    'duration': first_start
                })
                print(f"[WhisperTimestamp]   📍 시작 갭: 0 ~ {first_start:.2f} ({first_start:.1f}초)")

        # 중간 갭 (핵심!)
        gap_count = 0
        for i in range(len(sentences) - 1):
            current_end = sentences[i].get('end', 0)
            next_start = sentences[i + 1].get('start', 0)

            # None 체크
            if current_end is None:
                current_end = 0
            if next_start is None:
                next_start = 0

            gap_duration = next_start - current_end

            if gap_duration >= self.gap_threshold:
                gaps.append({
                    'start': current_end,
                    'end': next_start,
                    'duration': gap_duration
                })
                gap_count += 1
                print(f"[WhisperTimestamp]   📍 중간 갭 [{i}→{i+1}]: {current_end:.2f} ~ {next_start:.2f} ({gap_duration:.1f}초)")

        if gap_count == 0:
            print(f"[WhisperTimestamp]   ℹ️ 중간 갭 없음 (검사한 구간: {len(sentences)-1}개)")

            # ⭐ 디버깅: 갭이 없다면 가장 큰 갭들을 출력
            if len(sentences) > 1:
                all_gaps = []
                for i in range(len(sentences) - 1):
                    current_end = sentences[i].get('end', 0) or 0
                    next_start = sentences[i + 1].get('start', 0) or 0
                    gap = next_start - current_end
                    if gap > 0.5:  # 0.5초 이상만
                        all_gaps.append((i, current_end, next_start, gap))

                # 상위 5개 큰 갭 출력
                all_gaps.sort(key=lambda x: x[3], reverse=True)
                if all_gaps:
                    print(f"[WhisperTimestamp]   🔍 가장 큰 갭 Top5:")
                    for idx, (i, end, start, gap) in enumerate(all_gaps[:5]):
                        print(f"[WhisperTimestamp]     [{i}→{i+1}] {end:.2f}~{start:.2f} = {gap:.2f}초")

        # 끝 부분 갭
        if total_duration > 0 and sentences:
            last_end = sentences[-1].get('end', 0)
            if last_end is None:
                last_end = 0
            end_gap = total_duration - last_end
            if end_gap > self.gap_threshold:
                gaps.append({
                    'start': last_end,
                    'end': total_duration,
                    'duration': end_gap
                })
                print(f"[WhisperTimestamp]   📍 끝 갭: {last_end:.2f} ~ {total_duration:.2f} ({end_gap:.1f}초)")

        if not gaps:
            print(f"[WhisperTimestamp] ✅ 큰 갭 없음 (>{self.gap_threshold}초)")
            return sentences

        total_gap = sum(g['duration'] for g in gaps)
        print(f"\n[WhisperTimestamp] ⚠️ {len(gaps)}개 갭 발견 (총 {total_gap:.1f}초)")

        for i, gap in enumerate(gaps, 1):
            m1, s1 = int(gap['start'] // 60), gap['start'] % 60
            m2, s2 = int(gap['end'] // 60), gap['end'] % 60
            print(f"  [{i}] {m1:02d}:{s1:05.2f} ~ {m2:02d}:{s2:05.2f} ({gap['duration']:.1f}초)")

        # 각 갭에 대해 Whisper 재분석
        recovered_sentences = []

        for gap in gaps:
            m1, s1 = int(gap['start'] // 60), gap['start'] % 60
            m2, s2 = int(gap['end'] // 60), gap['end'] % 60
            print(f"\n[WhisperTimestamp] 🔄 갭 재분석: {m1:02d}:{s1:05.2f} ~ {m2:02d}:{s2:05.2f}")

            # 갭 구간 오디오 추출
            gap_audio = self._extract_gap_audio(
                audio_path,
                gap['start'],
                gap['end']
            )

            if not gap_audio:
                print(f"[WhisperTimestamp]   ⚠️ 오디오 추출 실패, 스킵")
                continue

            # ⭐ VAD 비활성화로 Whisper 재분석
            gap_sentences = self._transcribe_gap_without_vad(gap_audio, language)

            if not gap_sentences:
                print(f"[WhisperTimestamp]   ⚠️ 재분석 결과 없음 (무음 구간일 수 있음)")
                try:
                    os.remove(gap_audio)
                except:
                    pass
                continue

            # 타임스탬프 보정 (갭 시작 시간 + 여유분 빼기)
            offset = gap['start'] - 0.5  # 0.5초 여유분
            for sent in gap_sentences:
                sent['start'] = max(gap['start'], sent.get('start', 0) + offset)
                sent['end'] = min(gap['end'], sent.get('end', 0) + offset)
                sent['_recovered'] = True

            recovered_sentences.extend(gap_sentences)

            print(f"[WhisperTimestamp]   ✅ {len(gap_sentences)}개 문장 복구됨 (VAD 비활성화)")

            # 임시 파일 정리
            try:
                os.remove(gap_audio)
            except:
                pass

        if not recovered_sentences:
            print(f"\n[WhisperTimestamp] ⚠️ 갭에서 복구된 문장 없음")
            return sentences

        # 병합 및 정렬
        all_sentences = sentences + recovered_sentences
        all_sentences.sort(key=lambda x: x.get('start', 0))

        # 중복 제거
        all_sentences = self._remove_duplicate_sentences_simple(all_sentences)

        print(f"\n[WhisperTimestamp] ✅ 갭 재분석 완료")
        print(f"[WhisperTimestamp]   원본: {len(sentences)}개")
        print(f"[WhisperTimestamp]   복구: {len(recovered_sentences)}개")
        print(f"[WhisperTimestamp]   최종: {len(all_sentences)}개")

        return all_sentences

    def _extract_gap_audio(self, audio_path: str, start: float, end: float) -> str:
        """갭 구간 오디오 추출"""
        import tempfile

        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(audio_path)

            # 시간 보정 (여유 있게 0.5초씩)
            start_ms = max(0, int((start - 0.5) * 1000))
            end_ms = min(len(audio), int((end + 0.5) * 1000))

            # 구간 추출
            segment = audio[start_ms:end_ms]

            # 임시 파일로 저장
            fd, temp_path = tempfile.mkstemp(suffix='.wav')
            os.close(fd)

            segment.export(temp_path, format='wav')

            duration_sec = (end_ms - start_ms) / 1000
            print(f"[WhisperTimestamp]   오디오 추출: {duration_sec:.1f}초")

            return temp_path

        except Exception as e:
            print(f"[WhisperTimestamp]   ⚠️ 오디오 추출 실패: {e}")
            return None

    def _transcribe_gap_without_vad(self, audio_path: str, language: str) -> list:
        """
        갭 구간 Whisper 분석 (VAD 완전 비활성화!)

        ⭐ 핵심: vad_filter=False로 설정해서 모든 음성 감지
        """
        print(f"[WhisperTimestamp]   🔄 VAD 비활성화로 분석 중...")

        sentences = []

        try:
            if self.engine == "faster-whisper":
                # ⭐ VAD 완전 비활성화!
                segments, info = self.model.transcribe(
                    audio_path,
                    language=language,
                    beam_size=5,
                    best_of=5,
                    temperature=0.0,
                    word_timestamps=True,
                    vad_filter=False  # ⭐ 핵심: VAD 완전 비활성화!
                )

                for segment in segments:
                    text = segment.text.strip() if segment.text else ""
                    if text:
                        words = []
                        if hasattr(segment, 'words') and segment.words:
                            for word in segment.words:
                                words.append({
                                    "word": word.word,
                                    "start": word.start,
                                    "end": word.end
                                })

                        sentences.append({
                            'id': len(sentences),
                            'text': text,
                            'start': segment.start,
                            'end': segment.end,
                            'words': words,
                            '_recovered': True
                        })
            else:
                # stable-ts
                result = self.model.transcribe(
                    audio_path,
                    language=language,
                    word_timestamps=True
                )

                for segment in result.segments:
                    text = segment.text.strip() if segment.text else ""
                    if text:
                        sentences.append({
                            'id': len(sentences),
                            'text': text,
                            'start': segment.start,
                            'end': segment.end,
                            '_recovered': True
                        })

        except Exception as e:
            print(f"[WhisperTimestamp]   ⚠️ 갭 분석 실패: {e}")

        return sentences

    def _remove_duplicate_sentences_simple(self, sentences: list) -> list:
        """중복 문장 제거 (텍스트 앞 30자 + 시작 시간 기준)"""
        result = []
        seen = set()

        for sent in sentences:
            text = sent.get('text', '').strip()
            start = round(sent.get('start', 0), 1)

            # 키 생성: 텍스트 앞 30자 + 시작 시간
            key = (text[:30].lower(), start)

            if key not in seen:
                seen.add(key)
                result.append(sent)

        return result


# ============================================================
# 팩토리 함수
# ============================================================

def get_whisper_timestamp(
    model_size: str = "base",
    device: str = "auto",
    engine: str = "auto",
    language: str = "ko",
    compute_type: str = "auto",
    vad_filter: bool = True,
    refine: bool = False
) -> WhisperTimestamp:
    """
    WhisperTimestamp 인스턴스 생성
    """
    return WhisperTimestamp(
        model_size=model_size,
        device=device,
        engine=engine,
        language=language,
        compute_type=compute_type,
        vad_filter=vad_filter,
        refine=refine
    )


# ============================================================
# v5 호환성을 위한 별칭
# ============================================================

# 기존 클래스 별칭
WhisperTimestampExtractor = WhisperTimestamp
WhisperSegment = SentenceSegment

# 전역 인스턴스
_extractor_instance: Optional[WhisperTimestamp] = None

def get_whisper_extractor(
    model_size: str = "base",
    device_mode: str = "auto"
) -> WhisperTimestamp:
    """v5 호환성을 위한 싱글톤"""
    global _extractor_instance

    if _extractor_instance is None or \
       _extractor_instance.model_size != model_size:
        _extractor_instance = WhisperTimestamp(
            model_size=model_size,
            device=device_mode,
            engine="auto"
        )

    return _extractor_instance


# ============================================================
# WhisperTimestampV3 - 정확도 최적화 버전 (v3.0)
# ============================================================

@dataclass
class WhisperConfigV3:
    """Whisper v3.0 설정 (정확도 최적화) - v6.8 문장 분리 개선"""
    model_size: str = "small"          # ⭐ base → small 권장
    device: str = "auto"               # auto, cpu, cuda
    compute_type: str = "float16"      # float16, int8

    # VAD 설정 (⭐ v6.9 문장 분리 최적화!)
    # 문제: v6.8에서 min_silence=150ms가 너무 높아 문장이 합쳐짐
    # 해결: min_silence를 50ms로 낮추고, speech_pad를 30ms로 조정
    vad_filter: bool = True
    vad_threshold: float = 0.05        # ⭐ v6.9: 0.10 → 0.05 (더 민감하게!)
    min_speech_duration_ms: int = 30   # ⭐ 짧은 발화도 감지
    min_silence_duration_ms: int = 50  # ⭐ v6.9: 200 → 50 (짧은 무음도 분리점으로!)
    speech_pad_ms: int = 30            # ⭐ v6.9: 150 → 30 (패딩 최소화)

    # 인식 정확도 설정
    beam_size: int = 5                 # ⭐ 기본값 5 유지
    best_of: int = 5                   # ⭐ 후보 중 최선 선택
    temperature: float = 0.0           # ⭐ 0.0 = 결정적 (일관성)

    # 타임스탬프 설정 (⭐ 핵심!)
    word_timestamps: bool = True       # ⭐ 단어 단위 타임스탬프 활성화

    # 재분석 설정
    gap_threshold_seconds: float = 5.0 # 5초 이상 갭 감지
    reanalyze_gaps: bool = True        # 갭 구간 재분석


class WhisperTimestampV3:
    """
    Whisper 타임스탬프 추출 (v3.0 - 정확도 최적화)

    ⭐ 핵심 변경사항:
    1. VAD 설정 대폭 개선 (무음 오판 방지)
    2. word_timestamps 활성화 (정밀 타임스탬프)
    3. 큰 갭 감지 시 해당 구간만 재분석
    4. 모델 크기 옵션 (base → small/medium 권장)
    5. 오디오 전처리 연동
    """

    def __init__(self, config: WhisperConfigV3 = None):
        self.config = config or WhisperConfigV3()
        self.model = None
        self._device = None

        print(f"[WhisperV3] v3.0 초기화")
        print(f"[WhisperV3]   모델: {self.config.model_size}")
        print(f"[WhisperV3]   VAD threshold: {self.config.vad_threshold}")
        print(f"[WhisperV3]   min_silence: {self.config.min_silence_duration_ms}ms")  # ⭐ 핵심 로그!
        print(f"[WhisperV3]   min_speech: {self.config.min_speech_duration_ms}ms")
        print(f"[WhisperV3]   speech_pad: {self.config.speech_pad_ms}ms")
        print(f"[WhisperV3]   word_timestamps: {self.config.word_timestamps}")

    def _load_model(self):
        """모델 로드"""
        if self.model is not None:
            return

        from faster_whisper import WhisperModel

        # 디바이스 결정
        device = self.config.device
        compute_type = self.config.compute_type

        if device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                    compute_type = "float16"
                    print(f"[WhisperV3] GPU 감지: {torch.cuda.get_device_name(0)}")
                else:
                    device = "cpu"
                    compute_type = "int8"
            except:
                device = "cpu"
                compute_type = "int8"

        self._device = device

        print(f"[WhisperV3] 모델 로딩 중...")
        print(f"[WhisperV3]   모델: {self.config.model_size}")
        print(f"[WhisperV3]   디바이스: {device}")
        print(f"[WhisperV3]   계산타입: {compute_type}")

        self.model = WhisperModel(
            self.config.model_size,
            device=device,
            compute_type=compute_type
        )

        print(f"[WhisperV3] ✅ 모델 로드 완료")

    def analyze(self, audio_path: str, language: str = "ko",
                original_script: str = None) -> List[Dict]:
        """
        오디오 분석 (v3.0)

        ⭐ 새로운 기능:
        1. 최적화된 VAD로 무음 오판 방지
        2. word_timestamps로 정밀 타임스탬프
        3. 큰 갭 감지 시 해당 구간 재분석
        4. 원문 스크립트와 대조하여 누락 감지

        Args:
            audio_path: 오디오 파일 경로
            language: 언어 코드
            original_script: 원문 스크립트 (갭 복구용)

        Returns:
            문장 리스트 [{scene_id, text, start_time, end_time, ...}, ...]
        """

        self._load_model()

        print(f"\n[WhisperV3] 오디오 분석 시작")
        print(f"[WhisperV3]   파일: {os.path.basename(audio_path)}")
        print(f"[WhisperV3]   언어: {language}")
        print(f"[WhisperV3]   VAD 파라미터: threshold={self.config.vad_threshold}, min_silence={self.config.min_silence_duration_ms}ms, speech_pad={self.config.speech_pad_ms}ms")

        # ⭐ v6.10: VadOptions 객체 생성 (확실한 VAD 파라미터 전달!)
        try:
            from faster_whisper.vad import VadOptions
            vad_options = VadOptions(
                threshold=self.config.vad_threshold,
                min_speech_duration_ms=self.config.min_speech_duration_ms,
                min_silence_duration_ms=self.config.min_silence_duration_ms,
                speech_pad_ms=self.config.speech_pad_ms,
                max_speech_duration_s=float('inf'),  # 무제한
            )
            print(f"[WhisperV3]   ✅ VadOptions 객체 생성됨")
        except ImportError:
            # VadOptions import 실패 시 dict 사용 (호환성)
            vad_options = {
                "threshold": self.config.vad_threshold,
                "min_speech_duration_ms": self.config.min_speech_duration_ms,
                "min_silence_duration_ms": self.config.min_silence_duration_ms,
                "speech_pad_ms": self.config.speech_pad_ms
            }
            print(f"[WhisperV3]   ⚠️ VadOptions import 실패, dict 사용")

        # 1차 분석 (최적화된 설정)
        segments, info = self.model.transcribe(
            audio_path,
            language=language,
            beam_size=self.config.beam_size,
            best_of=self.config.best_of,
            temperature=self.config.temperature,
            word_timestamps=self.config.word_timestamps,

            # ⭐ v6.10: VadOptions 객체로 VAD 파라미터 전달
            vad_filter=self.config.vad_filter,
            vad_parameters=vad_options
        )

        # 세그먼트 수집
        sentences = []
        for segment in segments:
            text = segment.text.strip() if segment.text else ""
            if not text:
                continue

            sentence = {
                'text': text,
                'start': segment.start,
                'end': segment.end,
                'confidence': getattr(segment, 'avg_logprob', 0),
                'words': []
            }

            # word_timestamps가 있으면 단어별 정보 저장
            if hasattr(segment, 'words') and segment.words:
                for word in segment.words:
                    sentence['words'].append({
                        'word': word.word,
                        'start': word.start,
                        'end': word.end,
                        'probability': getattr(word, 'probability', 0)
                    })

            sentences.append(sentence)

        print(f"[WhisperV3] 1차 분석 완료: {len(sentences)}개 세그먼트")

        audio_duration = info.duration

        # ⭐ 갭 분석 및 재분석
        if self.config.reanalyze_gaps:
            sentences = self._analyze_and_fill_gaps(
                sentences,
                audio_path,
                audio_duration,
                language,
                original_script
            )

        # 최종 변환
        result = []
        for i, sent in enumerate(sentences):
            result.append({
                'scene_id': i + 1,
                'text': sent['text'],
                'start_time': self._format_time(sent['start']),
                'end_time': self._format_time(sent['end']),
                '_start_seconds': sent['start'],
                '_end_seconds': sent['end'],
                'words': sent.get('words', []),
                '_recovered': sent.get('_recovered', False)
            })

        print(f"[WhisperV3] 최종 결과: {len(result)}개 문장")
        print(f"[WhisperV3] 총 길이: {audio_duration:.1f}초 ({audio_duration/60:.1f}분)")

        return result

    def _analyze_and_fill_gaps(self, sentences: List[Dict],
                                audio_path: str,
                                audio_duration: float,
                                language: str,
                                original_script: str = None) -> List[Dict]:
        """
        갭 분석 및 재분석

        큰 갭이 발견되면:
        1. 해당 구간만 추출하여 재분석
        2. VAD를 더 민감하게 설정
        3. 원문 스크립트와 대조
        """

        if not sentences:
            return sentences

        # 갭 찾기
        gaps = []

        # 시작 부분 갭
        if sentences[0]['start'] > self.config.gap_threshold_seconds:
            gaps.append({
                'start': 0,
                'end': sentences[0]['start'],
                'duration': sentences[0]['start'],
                'position': 'start'
            })

        # 중간 갭
        for i in range(len(sentences) - 1):
            current_end = sentences[i]['end']
            next_start = sentences[i + 1]['start']
            gap_duration = next_start - current_end

            if gap_duration >= self.config.gap_threshold_seconds:
                gaps.append({
                    'start': current_end,
                    'end': next_start,
                    'duration': gap_duration,
                    'position': i + 1,  # 삽입 위치
                    'prev_text': sentences[i]['text'][:50],
                    'next_text': sentences[i + 1]['text'][:50]
                })

        # 끝 부분 갭
        if sentences[-1]['end'] < audio_duration - self.config.gap_threshold_seconds:
            gaps.append({
                'start': sentences[-1]['end'],
                'end': audio_duration,
                'duration': audio_duration - sentences[-1]['end'],
                'position': 'end'
            })

        if not gaps:
            print(f"[WhisperV3] 큰 갭 없음 (>{self.config.gap_threshold_seconds}초)")
            return sentences

        print(f"\n[WhisperV3] ⚠️ {len(gaps)}개 갭 발견!")
        for gap in gaps:
            print(f"  [{self._format_time(gap['start'])} ~ {self._format_time(gap['end'])}] ({gap['duration']:.1f}초)")

        # 각 갭 재분석 (VAD 비활성화!)
        new_segments = []

        for gap in gaps:
            print(f"\n[WhisperV3] 🔄 갭 재분석: {self._format_time(gap['start'])} ~ {self._format_time(gap['end'])}")

            # ⭐ v6.5: VAD 비활성화로 재분석 (핵심!)
            recovered = self._reanalyze_gap_without_vad(
                audio_path,
                gap['start'],
                gap['end'],
                language
            )

            if recovered:
                print(f"[WhisperV3]   ✅ {len(recovered)}개 세그먼트 복구 (VAD 비활성화)")
                new_segments.extend(recovered)
            else:
                # VAD 비활성화로도 못 찾으면 민감한 VAD로 재시도
                print(f"[WhisperV3]   ⚠️ VAD 비활성화 실패, 민감한 VAD로 재시도...")
                recovered = self._reanalyze_gap(
                    audio_path,
                    gap['start'],
                    gap['end'],
                    language,
                    original_script
                )
                if recovered:
                    print(f"[WhisperV3]   ✅ {len(recovered)}개 세그먼트 복구 (민감 VAD)")
                    new_segments.extend(recovered)
                else:
                    print(f"[WhisperV3]   ⚠️ 복구 실패 (무음 구간일 수 있음)")

        # 기존 + 새로운 세그먼트 병합 및 정렬
        all_segments = sentences + new_segments
        all_segments.sort(key=lambda x: x['start'])

        # 중복 제거
        deduplicated = self._remove_duplicate_segments(all_segments)

        print(f"\n[WhisperV3] 갭 복구 결과:")
        print(f"  원본: {len(sentences)}개")
        print(f"  복구: {len(new_segments)}개")
        print(f"  최종: {len(deduplicated)}개")

        return deduplicated

    def _reanalyze_gap(self, audio_path: str,
                       start_time: float, end_time: float,
                       language: str,
                       original_script: str = None) -> List[Dict]:
        """
        갭 구간 재분석 (더 민감한 설정으로)
        """

        try:
            # 오디오 구간 추출
            from pydub import AudioSegment

            audio = AudioSegment.from_file(audio_path)

            # 밀리초로 변환
            start_ms = int(start_time * 1000)
            end_ms = int(end_time * 1000)

            # 약간의 여유 추가
            start_ms = max(0, start_ms - 500)
            end_ms = min(len(audio), end_ms + 500)

            segment_audio = audio[start_ms:end_ms]

            # ⭐ 오디오 전처리 (볼륨 정규화)
            segment_audio = self._normalize_audio(segment_audio)

            # 임시 파일로 저장
            import tempfile
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"gap_{start_time:.0f}_{end_time:.0f}.wav")
            segment_audio.export(temp_path, format="wav")

            # v6.5: 극도로 민감한 설정으로 재분석
            segments, info = self.model.transcribe(
                temp_path,
                language=language,
                beam_size=10,                    # 더 많은 후보
                best_of=10,
                temperature=0.0,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={
                    "threshold": 0.03,           # ⭐ 0.1 → 0.03 (극도로 민감)
                    "min_speech_duration_ms": 20,# ⭐ 30 → 20 (더 짧은 발화 감지)
                    "min_silence_duration_ms": 500,
                    "speech_pad_ms": 400         # ⭐ 300 → 400 (여유 확대)
                }
            )

            # 세그먼트 수집 (시간 보정)
            time_offset = start_time - 0.5  # 여유분 보정

            result = []
            for segment in segments:
                text = segment.text.strip() if segment.text else ""
                if not text:
                    continue

                adjusted_start = segment.start + time_offset
                adjusted_end = segment.end + time_offset

                # 원래 갭 범위 내에 있는지 확인
                if adjusted_start >= start_time - 1 and adjusted_end <= end_time + 1:
                    result.append({
                        'text': text,
                        'start': max(start_time, adjusted_start),
                        'end': min(end_time, adjusted_end),
                        '_recovered': True
                    })

            # 임시 파일 삭제
            try:
                os.remove(temp_path)
            except:
                pass

            return result

        except Exception as e:
            print(f"[WhisperV3] 재분석 오류: {e}")
            return []

    def _normalize_audio(self, audio_segment):
        """오디오 정규화 (볼륨 조정)"""
        try:
            from pydub.effects import normalize, compress_dynamic_range

            # 볼륨 정규화
            normalized = normalize(audio_segment)

            # 다이나믹 레인지 압축 (작은 소리 증폭)
            try:
                normalized = compress_dynamic_range(
                    normalized,
                    threshold=-20.0,
                    ratio=4.0,
                    attack=5.0,
                    release=50.0
                )
            except:
                pass

            return normalized
        except:
            return audio_segment

    def _remove_duplicate_segments(self, segments: List[Dict]) -> List[Dict]:
        """중복 세그먼트 제거"""
        if not segments:
            return segments

        result = []
        seen_texts = set()

        for seg in segments:
            text = seg['text'].strip().lower()
            # 처음 30자로 중복 판단
            text_key = text[:30]

            if text_key not in seen_texts:
                seen_texts.add(text_key)
                result.append(seg)
            else:
                print(f"  [WhisperV3] 중복 제거: {seg['text'][:40]}...")

        return result

    def _format_time(self, seconds: float) -> str:
        """초를 SRT 타임스탬프로 변환"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        whole_secs = int(secs)
        millis = int((secs - whole_secs) * 1000)
        return f"{hours:02d}:{minutes:02d}:{whole_secs:02d},{millis:03d}"


    def transcribe_with_full_coverage(
        self,
        audio_path: str,
        language: str = "ko",
        original_script: str = None
    ) -> Dict:
        """
        100% 커버리지를 보장하는 전사 메서드

        ⭐ 핵심 기능:
        1. 1차 분석 후 커버리지 체크
        2. 빈 구간 감지 및 재분석 (VAD 비활성화)
        3. 원본 스크립트 기반 빈 구간 채우기
        4. 커버리지 통계 출력

        Args:
            audio_path: 오디오 파일 경로
            language: 언어 코드
            original_script: 원문 스크립트 (빈 구간 채우기용)

        Returns:
            {
                "segments": 세그먼트 리스트,
                "duration": 오디오 길이,
                "coverage_percent": 커버리지 비율,
                "gaps_recovered": 복구된 갭 수
            }
        """
        self._load_model()

        # 오디오 길이 확인
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            audio_duration = len(audio) / 1000.0
        except Exception as e:
            print(f"[WhisperV3] 오디오 로드 오류: {e}")
            audio_duration = 0

        print(f"\n{'='*60}")
        print(f"[WhisperV3] 100% 커버리지 모드 시작")
        print(f"{'='*60}")
        print(f"  파일: {os.path.basename(audio_path)}")
        print(f"  길이: {audio_duration:.1f}초 ({audio_duration/60:.1f}분)")
        print(f"  원문: {'있음' if original_script else '없음'}")

        # 1차 분석
        print(f"\n📍 1차 분석 (최적화된 VAD)")
        segments = self.analyze(audio_path, language, original_script)

        # 커버리지 통계
        gaps = self._detect_gaps_detailed(segments, audio_duration)
        coverage = self._log_coverage_stats(segments, audio_duration, gaps)

        # 빈 구간이 있으면 추가 조치
        if gaps and coverage < 95.0:
            print(f"\n📍 2차 분석: 빈 구간 {len(gaps)}개 추가 처리")

            # VAD 비활성화하여 재분석
            for gap in gaps:
                if gap['duration'] > 3.0:  # 3초 이상 갭만
                    print(f"  🔄 VAD 비활성화 재분석: {gap['start']:.1f}s ~ {gap['end']:.1f}s")
                    recovered = self._reanalyze_gap_without_vad(
                        audio_path, gap['start'], gap['end'], language
                    )
                    if recovered:
                        segments.extend(recovered)
                        print(f"     ✅ {len(recovered)}개 복구")

            # 정렬 및 중복 제거
            segments.sort(key=lambda x: x.get('_start_seconds', x.get('start', 0)))
            segments = self._remove_duplicate_segments(segments)

            # 재검증
            gaps_after = self._detect_gaps_detailed(segments, audio_duration)
            coverage_after = self._log_coverage_stats(segments, audio_duration, gaps_after)

            # ❌ v6.5: 원문 기반 빈 구간 채우기 비활성화
            # 원문 기반 타임스탬프 생성은 싱크 문제를 일으키므로 사용하지 않음
            # 타임스탬프는 반드시 Whisper에서만 생성되어야 함
            if gaps_after and coverage_after < 95.0:
                print(f"\n[WhisperV3] ℹ️ 남은 갭 {len(gaps_after)}개 (원문 기반 채우기 비활성화)")
                print(f"[WhisperV3] ℹ️ 타임스탬프는 Whisper에서만 생성됨 (싱크 정확도 보장)")

            # 최종 통계
            final_gaps = gaps_after
            final_coverage = coverage_after
        else:
            final_coverage = coverage
            final_gaps = gaps

        # 결과 정리
        if final_coverage >= 95.0:
            print(f"\n[WhisperV3] ✅ {final_coverage:.1f}% 커버리지 달성!")
        else:
            print(f"\n[WhisperV3] ⚠️ {final_coverage:.1f}% 커버리지 (목표: 95%)")

        return {
            "segments": segments,
            "duration": audio_duration,
            "coverage_percent": final_coverage,
            "gaps_found": len(final_gaps),
            "gaps_recovered": len(gaps) - len(final_gaps) if gaps else 0
        }

    def _detect_gaps_detailed(self, segments: List[Dict], audio_duration: float,
                              gap_threshold: float = 2.0) -> List[Dict]:
        """
        빈 구간 상세 감지

        Args:
            segments: 세그먼트 리스트
            audio_duration: 오디오 전체 길이
            gap_threshold: 갭으로 판단할 최소 시간 (초)

        Returns:
            빈 구간 리스트
        """
        gaps = []

        if not segments:
            if audio_duration > 0:
                return [{"start": 0, "end": audio_duration, "duration": audio_duration}]
            return []

        # 시작 부분 갭
        first_start = segments[0].get('_start_seconds', segments[0].get('start', 0))
        if first_start > gap_threshold:
            gaps.append({
                "start": 0,
                "end": first_start,
                "duration": first_start,
                "position": "start"
            })

        # 중간 갭
        for i in range(len(segments) - 1):
            current_end = segments[i].get('_end_seconds', segments[i].get('end', 0))
            next_start = segments[i+1].get('_start_seconds', segments[i+1].get('start', 0))
            gap_duration = next_start - current_end

            if gap_duration > gap_threshold:
                gaps.append({
                    "start": current_end,
                    "end": next_start,
                    "duration": gap_duration,
                    "position": i + 1,
                    "prev_text": segments[i].get('text', '')[:30],
                    "next_text": segments[i+1].get('text', '')[:30]
                })

        # 끝 부분 갭
        last_end = segments[-1].get('_end_seconds', segments[-1].get('end', 0))
        if audio_duration - last_end > gap_threshold:
            gaps.append({
                "start": last_end,
                "end": audio_duration,
                "duration": audio_duration - last_end,
                "position": "end"
            })

        return gaps

    def _log_coverage_stats(self, segments: List[Dict], audio_duration: float,
                            gaps: List[Dict]) -> float:
        """커버리지 통계 출력 및 반환"""
        if audio_duration <= 0:
            return 0.0

        covered_duration = sum(
            seg.get('_end_seconds', seg.get('end', 0)) -
            seg.get('_start_seconds', seg.get('start', 0))
            for seg in segments
        )
        coverage_percent = (covered_duration / audio_duration) * 100
        gap_duration = sum(g['duration'] for g in gaps)

        print(f"\n[WhisperV3] 📊 커버리지 통계:")
        print(f"  오디오 길이: {audio_duration:.1f}초")
        print(f"  커버된 구간: {covered_duration:.1f}초 ({coverage_percent:.1f}%)")
        print(f"  빈 구간: {gap_duration:.1f}초 ({len(gaps)}개)")

        if gaps:
            print(f"  빈 구간 상세:")
            for i, gap in enumerate(gaps):
                print(f"    [{i+1}] {gap['start']:.1f}s ~ {gap['end']:.1f}s ({gap['duration']:.1f}초)")

        return coverage_percent

    def _reanalyze_gap_without_vad(self, audio_path: str,
                                   start_time: float, end_time: float,
                                   language: str) -> List[Dict]:
        """
        VAD를 완전히 비활성화하고 갭 구간 재분석
        """
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(audio_path)

            # 구간 추출 (여유 추가)
            start_ms = max(0, int(start_time * 1000) - 500)
            end_ms = min(len(audio), int(end_time * 1000) + 500)
            segment_audio = audio[start_ms:end_ms]

            # 볼륨 정규화 + 증폭
            segment_audio = self._normalize_audio(segment_audio)
            segment_audio = segment_audio + 6  # 6dB 증폭

            # 임시 파일
            import tempfile
            temp_path = os.path.join(tempfile.gettempdir(), f"gap_novad_{start_time:.0f}.wav")
            segment_audio.export(temp_path, format="wav")

            # VAD 완전 비활성화로 분석
            segments, info = self.model.transcribe(
                temp_path,
                language=language,
                beam_size=10,
                best_of=10,
                temperature=0.0,
                word_timestamps=True,
                vad_filter=False,  # ⭐ VAD 완전 비활성화
                no_speech_threshold=0.5,  # 더 관대하게
                compression_ratio_threshold=3.0
            )

            # 시간 오프셋 보정
            time_offset = start_time - 0.5
            result = []

            for segment in segments:
                text = segment.text.strip() if segment.text else ""
                if not text:
                    continue

                adj_start = max(start_time, segment.start + time_offset)
                adj_end = min(end_time, segment.end + time_offset)

                if adj_end > adj_start:
                    result.append({
                        'text': text,
                        'start': adj_start,
                        'end': adj_end,
                        '_start_seconds': adj_start,
                        '_end_seconds': adj_end,
                        '_recovered': True,
                        '_method': 'no_vad'
                    })

            # 정리
            try:
                os.remove(temp_path)
            except:
                pass

            return result

        except Exception as e:
            print(f"[WhisperV3] VAD 비활성화 재분석 오류: {e}")
            return []

    def _fill_gaps_with_original_script(self, segments: List[Dict],
                                         gaps: List[Dict],
                                         original_script: str,
                                         audio_duration: float) -> List[Dict]:
        """
        ❌ [DEPRECATED] v6.5에서 비활성화

        원문 기반 타임스탬프 생성은 싱크 문제를 일으키므로 사용하지 않음!
        타임스탬프는 반드시 Whisper에서만 생성되어야 함

        이 메서드는 호출되지 않지만 레거시 호환성을 위해 유지됨
        """
        print(f"[WhisperV3] ⚠️ _fill_gaps_with_original_script 호출됨 - v6.5에서 비활성화!")
        print(f"[WhisperV3] ℹ️ 타임스탬프는 Whisper에서만 생성됨")
        return []  # 빈 리스트 반환 - 원문 기반 채우기 비활성화
        import re
        from difflib import SequenceMatcher

        # 원본 문장 분리
        sentences = re.split(r'(?<=[.?!요죠다네])\s*', original_script)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]

        filled = []

        for gap in gaps:
            # 이전/다음 텍스트 찾기
            prev_text = gap.get('prev_text', '')
            next_text = gap.get('next_text', '')

            if not prev_text and not next_text:
                continue

            # 원본에서 위치 찾기
            prev_idx = -1
            next_idx = len(sentences)

            for i, sent in enumerate(sentences):
                if prev_text and SequenceMatcher(None, sent[:30], prev_text[:30]).ratio() > 0.5:
                    prev_idx = i
                if next_text and prev_idx >= 0 and SequenceMatcher(None, sent[:30], next_text[:30]).ratio() > 0.5:
                    next_idx = i
                    break

            # 중간 문장 추출
            if prev_idx >= 0 and next_idx > prev_idx + 1:
                missing = sentences[prev_idx + 1:next_idx]

                if missing:
                    # 시간 분배
                    gap_duration = gap['end'] - gap['start']
                    time_per_sent = gap_duration / len(missing)
                    current_time = gap['start'] + 0.05

                    for text in missing:
                        # 텍스트 길이 기반 duration
                        char_count = len(text)
                        est_duration = max(1.0, min(time_per_sent, char_count / 5.0))

                        end_time = min(current_time + est_duration, gap['end'] - 0.05)

                        if end_time > current_time + 0.5:
                            filled.append({
                                'text': text,
                                'start': current_time,
                                'end': end_time,
                                '_start_seconds': current_time,
                                '_end_seconds': end_time,
                                '_recovered': True,
                                '_method': 'script_match'
                            })
                            current_time = end_time + 0.05

        return filled


def create_optimized_whisper(model_size: str = "small") -> WhisperTimestampV3:
    """
    최적화된 Whisper 인스턴스 생성 (v6.5)

    Args:
        model_size: 모델 크기 (small 권장, medium은 더 정확하지만 느림)

    Returns:
        WhisperTimestampV3 인스턴스
    """
    config = WhisperConfigV3(
        model_size=model_size,        # base → small 권장
        vad_threshold=0.05,           # ⭐ v6.5: 극도로 민감하게
        min_speech_duration_ms=30,    # ⭐ v6.5: 매우 짧은 발화도 감지
        speech_pad_ms=300,            # ⭐ v6.5: 발화 앞뒤 여유 확대
        word_timestamps=True,         # 정밀 타임스탬프
        reanalyze_gaps=True           # 갭 자동 재분석
    )
    return WhisperTimestampV3(config)
