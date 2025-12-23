# -*- coding: utf-8 -*-
"""
동영상 품질 검증 유틸리티

v1.0 - 원본 이미지와 동영상 프레임 비교
- 색상 차이 측정
- 채도 손실 감지
- 품질 진단 리포트 출력

사용법:
    python utils/quality_checker.py <original.png> <video.mp4>
"""

import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

# OpenCV import
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("⚠️ OpenCV가 설치되지 않았습니다. pip install opencv-python")


def extract_frame(video_path: str, frame_number: int = 0) -> Optional[np.ndarray]:
    """
    동영상에서 특정 프레임 추출

    Args:
        video_path: 동영상 파일 경로
        frame_number: 추출할 프레임 번호 (0부터 시작)

    Returns:
        BGR 형식의 numpy 배열 (실패 시 None)
    """
    if not CV2_AVAILABLE:
        return None

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"❌ 동영상 열기 실패: {video_path}")
            return None

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        cap.release()

        return frame if ret else None
    except Exception as e:
        print(f"❌ 프레임 추출 오류: {e}")
        return None


def compare_images(original_path: str, video_path: str, frame_number: int = 0) -> Dict:
    """
    원본 이미지와 동영상 프레임 비교

    Args:
        original_path: 원본 이미지 경로 (PNG)
        video_path: 동영상 파일 경로 (MP4)
        frame_number: 비교할 프레임 번호

    Returns:
        비교 결과 딕셔너리
    """
    if not CV2_AVAILABLE:
        return {'error': 'OpenCV가 설치되지 않았습니다.'}

    # 원본 이미지 로드
    original = cv2.imread(original_path)
    if original is None:
        return {'error': f'원본 이미지 로드 실패: {original_path}'}

    # 동영상 프레임 추출
    frame = extract_frame(video_path, frame_number)
    if frame is None:
        return {'error': f'동영상 프레임 추출 실패: {video_path}'}

    # 크기 맞추기 (필요시)
    if original.shape != frame.shape:
        print(f"⚠️ 크기 불일치: 원본 {original.shape[:2]} vs 프레임 {frame.shape[:2]}")
        frame = cv2.resize(frame, (original.shape[1], original.shape[0]),
                          interpolation=cv2.INTER_LANCZOS4)

    # 1. 절대 차이 계산
    diff = cv2.absdiff(original, frame)
    mean_diff = np.mean(diff)
    max_diff = np.max(diff)

    # 2. 채널별 차이
    b_diff = np.mean(diff[:, :, 0])
    g_diff = np.mean(diff[:, :, 1])
    r_diff = np.mean(diff[:, :, 2])

    # 3. HSV 변환 후 채도 비교
    orig_hsv = cv2.cvtColor(original, cv2.COLOR_BGR2HSV)
    frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # 채도 (Saturation) 채널
    orig_saturation = np.mean(orig_hsv[:, :, 1])
    frame_saturation = np.mean(frame_hsv[:, :, 1])
    saturation_loss = orig_saturation - frame_saturation
    saturation_loss_pct = (saturation_loss / orig_saturation * 100) if orig_saturation > 0 else 0

    # 밝기 (Value) 채널
    orig_value = np.mean(orig_hsv[:, :, 2])
    frame_value = np.mean(frame_hsv[:, :, 2])
    brightness_diff = frame_value - orig_value

    # 4. SSIM (구조적 유사성 - 선택적)
    ssim = None
    try:
        from skimage.metrics import structural_similarity
        gray_orig = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        ssim = structural_similarity(gray_orig, gray_frame)
    except ImportError:
        pass

    # 5. 품질 판정
    if mean_diff < 3 and abs(saturation_loss) < 2:
        quality = 'excellent'
        quality_ko = '우수'
    elif mean_diff < 5 and abs(saturation_loss) < 5:
        quality = 'good'
        quality_ko = '양호'
    elif mean_diff < 10:
        quality = 'acceptable'
        quality_ko = '보통'
    else:
        quality = 'poor'
        quality_ko = '불량'

    return {
        'mean_diff': float(mean_diff),
        'max_diff': float(max_diff),
        'channel_diff': {
            'blue': float(b_diff),
            'green': float(g_diff),
            'red': float(r_diff),
        },
        'saturation': {
            'original': float(orig_saturation),
            'frame': float(frame_saturation),
            'loss': float(saturation_loss),
            'loss_pct': float(saturation_loss_pct),
        },
        'brightness': {
            'original': float(orig_value),
            'frame': float(frame_value),
            'diff': float(brightness_diff),
        },
        'ssim': ssim,
        'quality': quality,
        'quality_ko': quality_ko,
        'sizes': {
            'original': f"{original.shape[1]}x{original.shape[0]}",
            'frame': f"{frame.shape[1]}x{frame.shape[0]}",
        }
    }


def save_diff_image(original_path: str, video_path: str, output_path: str,
                    frame_number: int = 0, amplify: int = 10) -> bool:
    """
    원본과 프레임의 차이를 시각화한 이미지 저장

    Args:
        original_path: 원본 이미지 경로
        video_path: 동영상 경로
        output_path: 차이 이미지 저장 경로
        frame_number: 비교할 프레임 번호
        amplify: 차이 증폭 배율 (더 선명하게 보이도록)
    """
    if not CV2_AVAILABLE:
        return False

    original = cv2.imread(original_path)
    frame = extract_frame(video_path, frame_number)

    if original is None or frame is None:
        return False

    if original.shape != frame.shape:
        frame = cv2.resize(frame, (original.shape[1], original.shape[0]),
                          interpolation=cv2.INTER_LANCZOS4)

    # 차이 계산 및 증폭
    diff = cv2.absdiff(original, frame)
    diff_amplified = np.clip(diff * amplify, 0, 255).astype(np.uint8)

    # 결과 저장
    cv2.imwrite(output_path, diff_amplified)
    print(f"✅ 차이 이미지 저장: {output_path}")

    return True


def diagnose_quality(original_path: str, video_path: str, verbose: bool = True) -> Dict:
    """
    품질 진단 리포트 출력

    Args:
        original_path: 원본 이미지 경로
        video_path: 동영상 경로
        verbose: 상세 출력 여부

    Returns:
        비교 결과 딕셔너리
    """
    result = compare_images(original_path, video_path)

    if 'error' in result:
        print(f"❌ 오류: {result['error']}")
        return result

    if verbose:
        print()
        print("=" * 60)
        print("📊 동영상 품질 진단 결과 (v3.11)")
        print("=" * 60)
        print()
        print(f"📁 원본 이미지: {original_path}")
        print(f"🎬 비교 동영상: {video_path}")
        print(f"📐 크기: 원본 {result['sizes']['original']} / 프레임 {result['sizes']['frame']}")
        print()
        print("-" * 60)
        print("🎨 색상 차이 분석")
        print("-" * 60)
        print(f"  평균 색상 차이: {result['mean_diff']:.2f} (0=동일, 낮을수록 좋음)")
        print(f"  최대 색상 차이: {result['max_diff']:.2f}")
        print(f"  채널별 차이: R={result['channel_diff']['red']:.2f}, "
              f"G={result['channel_diff']['green']:.2f}, "
              f"B={result['channel_diff']['blue']:.2f}")
        print()
        print("-" * 60)
        print("💎 채도/밝기 분석")
        print("-" * 60)
        sat = result['saturation']
        print(f"  원본 채도: {sat['original']:.2f}")
        print(f"  프레임 채도: {sat['frame']:.2f}")
        print(f"  채도 손실: {sat['loss']:.2f} ({sat['loss_pct']:.1f}%)")

        brt = result['brightness']
        print(f"  밝기 차이: {brt['diff']:+.2f}")

        if result['ssim'] is not None:
            print(f"  SSIM (구조 유사도): {result['ssim']:.4f} (1.0=완벽)")

        print()
        print("-" * 60)
        print("🏆 품질 판정")
        print("-" * 60)

        quality_emoji = {
            'excellent': '🌟',
            'good': '✅',
            'acceptable': '⚠️',
            'poor': '❌'
        }

        emoji = quality_emoji.get(result['quality'], '❓')
        print(f"  {emoji} 판정: {result['quality_ko']} ({result['quality']})")

        # 권장 사항
        print()
        print("-" * 60)
        print("💡 권장 사항")
        print("-" * 60)

        if result['mean_diff'] > 10:
            print("  ⚠️ 색상 차이가 큽니다.")
            print("     → FFmpeg CRF 값을 낮추세요 (예: 10 → 8)")
            print("     → device-scale-factor=2 확인")

        if sat['loss'] > 5:
            print("  ⚠️ 채도 손실이 있습니다.")
            print("     → yuv420p 대신 yuv444p 고려 (VLC 전용)")
            print("     → color_preserve: true 확인")

        if result['quality'] in ['excellent', 'good']:
            print("  ✅ 현재 품질 설정이 양호합니다.")

        print()
        print("=" * 60)

    return result


def extract_first_frame(video_path: str, output_path: str = None) -> Optional[str]:
    """
    동영상의 첫 프레임을 PNG로 추출

    Args:
        video_path: 동영상 경로
        output_path: 저장 경로 (None이면 자동 생성)

    Returns:
        저장된 파일 경로
    """
    if not CV2_AVAILABLE:
        return None

    frame = extract_frame(video_path, 0)
    if frame is None:
        return None

    if output_path is None:
        video_name = Path(video_path).stem
        output_path = f"{video_name}_frame_0.png"

    cv2.imwrite(output_path, frame)
    print(f"✅ 첫 프레임 추출: {output_path}")

    return output_path


# CLI 인터페이스
if __name__ == '__main__':
    if len(sys.argv) >= 3:
        original = sys.argv[1]
        video = sys.argv[2]

        result = diagnose_quality(original, video)

        # 차이 이미지 저장 (선택적)
        if len(sys.argv) >= 4 and sys.argv[3] == '--save-diff':
            diff_path = Path(original).stem + "_diff.png"
            save_diff_image(original, video, diff_path)

    elif len(sys.argv) == 2:
        # 단일 인자: 동영상에서 첫 프레임 추출
        video = sys.argv[1]
        extract_first_frame(video)

    else:
        print("사용법:")
        print("  품질 비교: python quality_checker.py <original.png> <video.mp4>")
        print("  차이 저장: python quality_checker.py <original.png> <video.mp4> --save-diff")
        print("  프레임 추출: python quality_checker.py <video.mp4>")
