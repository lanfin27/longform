# -*- coding: utf-8 -*-
"""
utils/srt_time_splitter.py 단위 테스트

실행:
    python tests/test_srt_time_splitter.py
또는:
    python -m pytest tests/test_srt_time_splitter.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows 콘솔(cp949)에서도 한글/기호 출력이 깨지지 않도록 UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from utils.srt_time_splitter import (
    Word,
    Segment,
    split_by_target_duration,
    is_sentence_end,
    is_korean_ending,
    summarize_segments,
)


def _make_uniform_words(count, word_dur=0.4, gap=0.0, start=0.0, text="단어"):
    """일정한 길이의 단어들을 생성."""
    words = []
    t = start
    for i in range(count):
        words.append(Word(start=t, end=t + word_dur, text=f" {text}{i}"))
        t += word_dur + gap
    return words


def _all_within_some_word_boundary(segments, words):
    """모든 세그먼트의 start/end가 실제 단어 타임스탬프와 일치하는지 확인."""
    word_starts = {round(w.start, 6) for w in words}
    word_ends = {round(w.end, 6) for w in words}
    for seg in segments:
        assert round(seg.start, 6) in word_starts, f"seg.start {seg.start} not a word start"
        assert round(seg.end, 6) in word_ends, f"seg.end {seg.end} not a word end"


def test_uniform_distribution():
    """30초 단조 음성 -> target 1초 시 세그먼트 ~30개, 평균 ~1초, 표준편차 작음."""
    # 0.4초 단어가 연속 (gap 0) -> 30초 = 75개 단어
    words = _make_uniform_words(count=75, word_dur=0.4, gap=0.0)
    segs = split_by_target_duration(words, target_sec=1.0)
    stats = summarize_segments(segs)

    # 30초 / 1초 -> 약 30개 (단어 입도 0.4초이므로 1.0~1.2초 단위)
    assert 24 <= stats['count'] <= 34, f"count={stats['count']}"
    assert 0.85 <= stats['avg'] <= 1.35, f"avg={stats['avg']}"
    assert stats['std'] < 0.35, f"std={stats['std']}"
    _all_within_some_word_boundary(segs, words)
    print(f"  [uniform] count={stats['count']} avg={stats['avg']:.2f} std={stats['std']:.2f}")


def test_long_silence_forces_break():
    """중간에 큰 무음이 있으면 그 지점에서 강제 분할된다."""
    # 앞쪽 5개 단어(약 2초), 그 다음 5초 무음, 뒤쪽 5개 단어
    front = _make_uniform_words(count=5, word_dur=0.4, gap=0.0, start=0.0)
    # front 마지막 end = 2.0, 5초 무음 후 7.0부터 시작
    back = _make_uniform_words(count=5, word_dur=0.4, gap=0.0, start=7.0)
    words = front + back

    segs = split_by_target_duration(words, target_sec=2.0)  # pause_break = 3.0초
    # 무음(5초) >= 3.0 이므로 반드시 7.0 경계에서 끊겨야 함
    boundary_ends = [round(s.end, 3) for s in segs]
    boundary_starts = [round(s.start, 3) for s in segs]
    assert 2.0 in boundary_ends, f"무음 직전(2.0)에서 끊기지 않음: {boundary_ends}"
    assert 7.0 in boundary_starts, f"무음 직후(7.0)에서 시작하지 않음: {boundary_starts}"
    _all_within_some_word_boundary(segs, words)
    print(f"  [silence] segments={len(segs)} starts={boundary_starts}")


def test_word_boundary_preserved():
    """어떤 세그먼트도 단어 중간을 자르지 않는다."""
    words = _make_uniform_words(count=50, word_dur=0.37, gap=0.05)
    segs = split_by_target_duration(words, target_sec=1.5)
    _all_within_some_word_boundary(segs, words)
    # 전체 단어 수 보존
    total = sum(len(s.words) for s in segs)
    assert total == len(words), f"단어 누락/중복: {total} != {len(words)}"
    print(f"  [boundary] segments={len(segs)} words_preserved={total}")


def test_last_segment_short_survives():
    """음성 끝부분이 target보다 짧아도 마지막 세그먼트로 살아남는다."""
    # 11개 단어, 0.4초 -> 약 4.4초. target 2초면 2개 + 짧은 꼬리 가능
    words = _make_uniform_words(count=11, word_dur=0.4, gap=0.0)
    segs = split_by_target_duration(words, target_sec=2.0)
    # 마지막 단어가 마지막 세그먼트에 포함
    assert segs, "세그먼트가 비어있음"
    assert round(segs[-1].end, 6) == round(words[-1].end, 6)
    # 전체 커버
    assert round(segs[0].start, 6) == round(words[0].start, 6)
    print(f"  [last] segments={len(segs)} last_dur={segs[-1].duration:.2f}")


def test_empty_input():
    """빈 입력 -> 빈 결과, 예외 없음."""
    assert split_by_target_duration([], target_sec=2.0) == []
    print("  [empty] ok")


def test_single_word():
    """단어 1개 -> 세그먼트 1개, start/end 정확."""
    w = Word(start=1.23, end=2.34, text="안녕하세요")
    segs = split_by_target_duration([w], target_sec=2.0)
    assert len(segs) == 1
    assert segs[0].start == 1.23
    assert segs[0].end == 2.34
    assert segs[0].text == "안녕하세요"
    print("  [single] ok")


def test_oversize_single_word_allowed():
    """target보다 긴 단일 단어는 분할하지 않고 오버사이즈 허용."""
    w = Word(start=0.0, end=5.0, text="아주긴단어")
    segs = split_by_target_duration([w], target_sec=1.0)
    assert len(segs) == 1
    assert segs[0].duration == 5.0
    print("  [oversize] ok")


def test_sentence_end_priority():
    """문장 종결 부호에서 우선 분할된다."""
    words = [
        Word(0.0, 0.4, " 안녕"),
        Word(0.4, 0.8, " 하세요."),   # 종결 부호 -> 0.8초이지만 lower(2*0.7=1.4) 미만이라 아직 안 끊김
        Word(0.8, 1.2, " 오늘은"),
        Word(1.2, 1.6, " 좋은"),
        Word(1.6, 2.0, " 날입니다."),  # 2.0초, lower 도달 + 종결 부호 -> 분할
        Word(2.0, 2.4, " 그리고"),
    ]
    segs = split_by_target_duration(words, target_sec=2.0)
    # 첫 세그먼트는 "날입니다." 에서 끝나야 함
    assert any(s.text.endswith("날입니다.") for s in segs), [s.text for s in segs]
    print(f"  [sentence] segments={[s.text for s in segs]}")


def test_helpers():
    assert is_sentence_end("좋아요.") is True
    assert is_sentence_end("좋아요?") is True
    assert is_sentence_end("좋아요") is False
    assert is_korean_ending("합니다") is True
    assert is_korean_ending("입니다.") is True
    assert is_korean_ending("사과") is False
    print("  [helpers] ok")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        print(f"RUN {t.__name__}")
        t()
        passed += 1
    print(f"\n[OK] {passed}/{len(tests)} tests passed")


if __name__ == "__main__":
    _run_all()
