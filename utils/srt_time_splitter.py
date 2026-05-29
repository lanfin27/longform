# -*- coding: utf-8 -*-
"""
srt_time_splitter.py - SRT 시간 단위 균등 분할기

Whisper의 word-level timestamps를 입력받아, 사용자가 지정한
고정 시간 간격(target_sec) 근처로 세그먼트를 균등 분할한다.

핵심 원칙 (우선순위 순):
1. 단어 경계 보존: 단어 중간을 절대 자르지 않는다.
2. 목표 시간 ± 허용 오차: [T*(1-tol), T*(1+tol)] 범위를 지향한다.
3. 자연 경계 우선순위 (목표의 70% 도달 이후):
   1순위 문장 종결 부호(. ? ! …)
   2순위 한국어 종결 어미 / 쉼표 / >=0.3초 무음 (목표 도달 이후)
   3순위 강제 컷 (오차 상한 도달)
4. 무음 구간 처리: 단어 간 pause가 target_sec * pause_break_ratio 이상이면
   그 지점에서 강제로 세그먼트를 끊는다.
5. 타임스탬프 정확성: 각 세그먼트의 start/end는 그 세그먼트에 포함된
   첫 단어의 start, 마지막 단어의 end를 그대로 사용한다 (인공 균등 분할 금지).

이 모듈은 SRT 생성 파이프라인 전용이며 TTS 코드와 완전히 격리되어 있다.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Word:
    """단어 단위 타임스탬프"""
    start: float
    end: float
    text: str


@dataclass
class Segment:
    """분할된 세그먼트 (start/end는 실제 단어 타임스탬프 사용)"""
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


# 문장 종결 부호 (강한 신호 - 구두점)
SENTENCE_END_CHARS = {'.', '?', '!', '…'}

# 한국어 종결 어미 (약한 신호 - 오탐 가능: '다'->'다음', '요'->'요리')
# 긴 어미를 먼저 검사하도록 길이 내림차순 정렬
KOREAN_END_SUFFIX = (
    '습니다', '입니다', '습니까', '됩니다',
    '요', '죠', '다', '까', '네', '군',
)

# 구두점 제거용 (어미 검사 전 후행 부호 제거)
_TRAILING_PUNCT = ''.join(SENTENCE_END_CHARS) + '"\'”’),.'


def is_sentence_end(text: str) -> bool:
    """문장 종결 부호로 끝나는가 (강한 신호)."""
    t = (text or '').rstrip()
    if not t:
        return False
    return t[-1] in SENTENCE_END_CHARS


def is_korean_ending(text: str) -> bool:
    """한국어 종결 어미로 끝나는가 (약한 신호 - 보수적으로만 사용)."""
    t = (text or '').rstrip().rstrip(_TRAILING_PUNCT)
    if not t:
        return False
    for suffix in KOREAN_END_SUFFIX:
        if t.endswith(suffix):
            return True
    return False


def _ends_with_comma(text: str) -> bool:
    t = (text or '').rstrip()
    return bool(t) and t[-1] in (',', '，')  # ASCII / fullwidth comma


def _join_words(words: List[Word]) -> str:
    """단어 리스트를 하나의 텍스트로 결합.

    faster-whisper의 word.text는 보통 선행 공백을 포함하므로 그대로 이어 붙인 뒤
    양끝 공백만 제거하면 자연스러운 문장이 복원된다. 폴백(합성 단어)의 경우
    선행 공백이 없으므로 단어 사이 공백을 보강한다.
    """
    if not words:
        return ''
    has_leading_space = any(w.text[:1].isspace() for w in words if w.text)
    if has_leading_space:
        return ''.join(w.text for w in words).strip()
    # 합성 단어/공백 없는 토큰: 공백으로 연결
    return ' '.join(w.text.strip() for w in words if w.text.strip()).strip()


def _flush(segments: List[Segment], buf: List[Word]) -> None:
    if not buf:
        return
    segments.append(Segment(
        start=buf[0].start,
        end=buf[-1].end,
        text=_join_words(buf),
        words=list(buf),
    ))


def split_by_target_duration(
    words: List[Word],
    target_sec: float,
    tolerance: float = 0.3,
    pause_break_ratio: float = 1.5,
    phrase_pause_sec: float = 0.3,
) -> List[Segment]:
    """
    word-level timestamps를 target_sec 근처로 균등 분할한다.

    Args:
        words: Whisper word_timestamps=True로 얻은 단어 리스트 (시간순 정렬 가정)
        target_sec: 목표 세그먼트 길이(초)
        tolerance: 허용 오차 비율 (기본 0.3 -> +-30%)
        pause_break_ratio: 이 비율 이상의 무음이면 강제 분할 (기본 1.5 * T)
        phrase_pause_sec: 어절 경계로 인정할 최소 무음 길이 (기본 0.3초)

    Returns:
        Segment 리스트 (각 세그먼트의 start/end는 실제 단어 타임스탬프 사용)
    """
    if not words:
        return []
    if not target_sec or target_sec <= 0:
        # 분할하지 않고 전체를 한 세그먼트로 (방어적)
        return [Segment(start=words[0].start, end=words[-1].end, text=_join_words(words), words=list(words))]

    lower = target_sec * (1.0 - tolerance)
    upper = target_sec * (1.0 + tolerance)
    pause_break = target_sec * pause_break_ratio

    segments: List[Segment] = []
    buf: List[Word] = []
    buf_start: Optional[float] = None

    n = len(words)

    def reset():
        return [], None

    for i, w in enumerate(words):
        # 1) 무음 강제 분할: 직전 단어와의 pause가 크면 먼저 끊는다
        if buf and (w.start - buf[-1].end) >= pause_break:
            _flush(segments, buf)
            buf, buf_start = reset()

        # 2) 사전 컷: 이 단어를 넣으면 상한을 넘고, 현재 버퍼가 이미 충분(>=lower)하면
        #    단어를 넣기 전에 끊는다 (상한을 넘는 오버슈트 방지, 단어 경계 보존).
        if buf and buf_start is not None:
            cur = buf[-1].end - buf_start
            prospective = w.end - buf_start
            if cur >= lower and prospective > upper:
                _flush(segments, buf)
                buf, buf_start = reset()

        if buf_start is None:
            buf_start = w.start

        buf.append(w)
        cur_len = w.end - buf_start

        # 3) 자연 경계 탐색 (목표 하한 도달 이후)
        if cur_len >= lower:
            # 1순위: 문장 종결 부호 (강한 신호)
            if is_sentence_end(w.text):
                _flush(segments, buf)
                buf, buf_start = reset()
                continue

            # 2순위: 목표 시간 도달 이후의 약한 경계 (어미/쉼표/무음)
            if cur_len >= target_sec:
                next_pause = (words[i + 1].start - w.end) if (i + 1 < n) else 0.0
                if is_korean_ending(w.text) or _ends_with_comma(w.text) or next_pause >= phrase_pause_sec:
                    _flush(segments, buf)
                    buf, buf_start = reset()
                    continue

            # 3순위: 강제 컷 - 단일 단어/누적이 이미 상한을 넘은 경우 (오버사이즈 단어 허용)
            if cur_len >= upper:
                _flush(segments, buf)
                buf, buf_start = reset()
                continue

    # 남은 버퍼 처리 (마지막 세그먼트는 target보다 짧아도 살린다)
    if buf:
        _flush(segments, buf)

    return segments


def summarize_segments(segments: List[Segment]) -> dict:
    """세그먼트 길이 분포 통계 (min/max/평균/표준편차)."""
    if not segments:
        return {'count': 0, 'avg': 0.0, 'min': 0.0, 'max': 0.0, 'std': 0.0}
    durations = [s.duration for s in segments]
    n = len(durations)
    avg = sum(durations) / n
    var = sum((d - avg) ** 2 for d in durations) / n
    std = var ** 0.5
    return {
        'count': n,
        'avg': avg,
        'min': min(durations),
        'max': max(durations),
        'std': std,
    }
