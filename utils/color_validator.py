# -*- coding: utf-8 -*-
"""
색상 정확도 검증 유틸리티

v1.0 - 원본 이미지와 동영상 프레임의 색상 비교
- 색상 시프트 감지 (빨간색→주황색 등)
- 채도 손실 측정
- 보정 필터 제안

사용법:
    python utils/color_validator.py <original.png> <output_frame.png>
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
    print("OpenCV가 설치되지 않았습니다. pip install opencv-python")


def extract_dominant_color(image_path: str, region: tuple = None) -> tuple:
    """
    이미지에서 주요 색상 추출 (BGR)

    Args:
        image_path: 이미지 파일 경로
        region: (x, y, w, h) 특정 영역만 분석

    Returns:
        (B, G, R) 평균 색상 튜플
    """
    if not CV2_AVAILABLE:
        return (0, 0, 0)

    image = cv2.imread(image_path)
    if image is None:
        print(f"이미지 로드 실패: {image_path}")
        return (0, 0, 0)

    if region:
        x, y, w, h = region
        image = image[y:y+h, x:x+w]

    # 평균 색상
    avg_color = np.mean(image, axis=(0, 1))
    return tuple(map(int, avg_color))


def extract_video_frame(video_path: str, frame_number: int = 0) -> Optional[str]:
    """
    동영상에서 프레임 추출하여 임시 파일로 저장

    Args:
        video_path: 동영상 경로
        frame_number: 추출할 프레임 번호

    Returns:
        추출된 프레임 파일 경로
    """
    if not CV2_AVAILABLE:
        return None

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return None

        # 임시 파일로 저장
        output_path = f"{Path(video_path).stem}_frame_{frame_number}.png"
        cv2.imwrite(output_path, frame)
        return output_path

    except Exception as e:
        print(f"프레임 추출 오류: {e}")
        return None


def compare_colors(original_path: str, output_path: str, verbose: bool = True) -> Dict:
    """
    원본과 출력의 색상 비교

    Args:
        original_path: 원본 이미지 경로
        output_path: 출력 이미지/프레임 경로
        verbose: 상세 출력 여부

    Returns:
        분석 결과 딕셔너리
    """
    if not CV2_AVAILABLE:
        return {'error': 'OpenCV가 설치되지 않았습니다.'}

    # 이미지 로드
    orig_img = cv2.imread(original_path)
    out_img = cv2.imread(output_path)

    if orig_img is None:
        return {'error': f'원본 이미지 로드 실패: {original_path}'}
    if out_img is None:
        return {'error': f'출력 이미지 로드 실패: {output_path}'}

    # 크기 맞추기
    if orig_img.shape[:2] != out_img.shape[:2]:
        out_img = cv2.resize(out_img, (orig_img.shape[1], orig_img.shape[0]),
                            interpolation=cv2.INTER_LANCZOS4)

    if verbose:
        print()
        print("=" * 60)
        print("색상 정확도 검증")
        print("=" * 60)

    # 전체 이미지 평균 색상
    orig_color = np.mean(orig_img, axis=(0, 1))
    out_color = np.mean(out_img, axis=(0, 1))

    if verbose:
        print(f"\n[전체 이미지 평균 색상 (BGR)]")
        print(f"  원본:   B={orig_color[0]:.1f}, G={orig_color[1]:.1f}, R={orig_color[2]:.1f}")
        print(f"  출력:   B={out_color[0]:.1f}, G={out_color[1]:.1f}, R={out_color[2]:.1f}")

    # 색상 차이
    diff = orig_color - out_color

    if verbose:
        print(f"  차이:   B={diff[0]:+.1f}, G={diff[1]:+.1f}, R={diff[2]:+.1f}")

        # 색상 시프트 진단
        print(f"\n[진단]")
        if diff[2] > 10:  # R 채널 손실
            print(f"  빨간색 손실 감지: R 채널이 {diff[2]:.1f} 낮음")
            print(f"     -> 빨간색이 주황색으로 보이는 원인")
        if diff[1] < -10:  # G 채널 증가
            print(f"  녹색 증가 감지: G 채널이 {-diff[1]:.1f} 높음")
        if abs(diff[0]) > 10:
            print(f"  파란색 변화 감지: B 채널 차이 {diff[0]:.1f}")

    # HSV로 변환하여 채도/색조 비교
    orig_hsv = cv2.cvtColor(orig_img, cv2.COLOR_BGR2HSV)
    out_hsv = cv2.cvtColor(out_img, cv2.COLOR_BGR2HSV)

    orig_hue = np.mean(orig_hsv[:,:,0])
    out_hue = np.mean(out_hsv[:,:,0])
    hue_shift = out_hue - orig_hue

    orig_sat = np.mean(orig_hsv[:,:,1])
    out_sat = np.mean(out_hsv[:,:,1])
    sat_loss = orig_sat - out_sat
    sat_loss_pct = (sat_loss / orig_sat * 100) if orig_sat > 0 else 0

    orig_val = np.mean(orig_hsv[:,:,2])
    out_val = np.mean(out_hsv[:,:,2])
    val_diff = out_val - orig_val

    if verbose:
        print(f"\n[색조(Hue) 비교]")
        print(f"  원본 색조: {orig_hue:.1f}")
        print(f"  출력 색조: {out_hue:.1f}")
        print(f"  색조 시프트: {hue_shift:+.1f}")

        if abs(hue_shift) > 3:
            print(f"  ** 색조 시프트 감지! hue=h={-hue_shift:.0f} 필터로 보정 필요")

        print(f"\n[채도(Saturation) 비교]")
        print(f"  원본 채도: {orig_sat:.1f}")
        print(f"  출력 채도: {out_sat:.1f}")
        print(f"  채도 손실: {sat_loss:.1f} ({sat_loss_pct:.1f}%)")

        if sat_loss > 5:
            print(f"  ** 채도 손실 감지! eq=saturation 필터로 보정 필요")

        print(f"\n[밝기(Value) 비교]")
        print(f"  원본 밝기: {orig_val:.1f}")
        print(f"  출력 밝기: {out_val:.1f}")
        print(f"  밝기 차이: {val_diff:+.1f}")

    # 품질 판정
    if abs(hue_shift) < 2 and sat_loss < 3:
        quality = 'excellent'
        quality_ko = '우수'
    elif abs(hue_shift) < 4 and sat_loss < 6:
        quality = 'good'
        quality_ko = '양호'
    elif abs(hue_shift) < 6 and sat_loss < 10:
        quality = 'acceptable'
        quality_ko = '보통'
    else:
        quality = 'poor'
        quality_ko = '불량'

    if verbose:
        print()
        print("-" * 60)
        quality_emoji = {
            'excellent': '[우수]',
            'good': '[양호]',
            'acceptable': '[보통]',
            'poor': '[불량]'
        }
        print(f"색감 품질 판정: {quality_emoji.get(quality, '?')} {quality_ko}")
        print("=" * 60)

    return {
        'color_diff_bgr': diff.tolist(),
        'hue_shift': float(hue_shift),
        'saturation_loss': float(sat_loss),
        'saturation_loss_pct': float(sat_loss_pct),
        'brightness_diff': float(val_diff),
        'quality': quality,
        'quality_ko': quality_ko,
        'original_avg_bgr': orig_color.tolist(),
        'output_avg_bgr': out_color.tolist(),
    }


def suggest_correction_filter(analysis_result: Dict) -> Optional[str]:
    """
    분석 결과를 바탕으로 FFmpeg 보정 필터 제안

    Args:
        analysis_result: compare_colors()의 결과

    Returns:
        FFmpeg -vf 필터 문자열 또는 None
    """
    if 'error' in analysis_result:
        return None

    filters = []

    sat_loss = analysis_result.get('saturation_loss', 0)
    hue_shift = analysis_result.get('hue_shift', 0)

    # 채도 보정 (손실이 3% 이상이면)
    if sat_loss > 3:
        sat_boost = 1 + (sat_loss / 100)
        filters.append(f"eq=saturation={sat_boost:.2f}")

    # 색조 보정 (시프트가 2도 이상이면)
    if abs(hue_shift) > 2:
        filters.append(f"hue=h={-hue_shift:.0f}")

    if filters:
        return ','.join(filters)
    else:
        return None


def analyze_specific_color(image_path: str, target_color_bgr: Tuple[int, int, int],
                           tolerance: int = 30) -> Dict:
    """
    특정 색상이 이미지에서 어떻게 변했는지 분석

    Args:
        image_path: 이미지 경로
        target_color_bgr: 찾을 색상 (B, G, R)
        tolerance: 허용 오차

    Returns:
        분석 결과
    """
    if not CV2_AVAILABLE:
        return {'error': 'OpenCV가 설치되지 않았습니다.'}

    image = cv2.imread(image_path)
    if image is None:
        return {'error': f'이미지 로드 실패: {image_path}'}

    # 타겟 색상 범위
    lower = np.array([max(0, c - tolerance) for c in target_color_bgr])
    upper = np.array([min(255, c + tolerance) for c in target_color_bgr])

    # 마스크 생성
    mask = cv2.inRange(image, lower, upper)

    # 해당 색상 픽셀의 평균
    if np.sum(mask) > 0:
        masked_pixels = image[mask > 0]
        avg_color = np.mean(masked_pixels, axis=0)
        pixel_count = np.sum(mask > 0)
    else:
        avg_color = np.array([0, 0, 0])
        pixel_count = 0

    return {
        'target_color_bgr': target_color_bgr,
        'found_avg_color_bgr': avg_color.tolist(),
        'pixel_count': int(pixel_count),
        'coverage_pct': float(pixel_count / (image.shape[0] * image.shape[1]) * 100)
    }


def compare_specific_color(original_path: str, output_path: str,
                           target_color_bgr: Tuple[int, int, int],
                           color_name: str = "Target",
                           verbose: bool = True) -> Dict:
    """
    특정 색상이 원본과 출력에서 어떻게 다른지 비교

    예: 빨간색 #FF6B6B (BGR: 107, 107, 255) 비교

    Args:
        original_path: 원본 이미지
        output_path: 출력 이미지
        target_color_bgr: 비교할 색상 (B, G, R)
        color_name: 색상 이름 (출력용)
        verbose: 상세 출력

    Returns:
        비교 결과
    """
    orig_result = analyze_specific_color(original_path, target_color_bgr)
    out_result = analyze_specific_color(output_path, target_color_bgr)

    if 'error' in orig_result or 'error' in out_result:
        return {'error': orig_result.get('error') or out_result.get('error')}

    orig_avg = np.array(orig_result['found_avg_color_bgr'])
    out_avg = np.array(out_result['found_avg_color_bgr'])
    color_shift = out_avg - orig_avg

    if verbose:
        print()
        print(f"[{color_name} 색상 비교 (BGR: {target_color_bgr})]")
        print(f"  원본 평균: B={orig_avg[0]:.1f}, G={orig_avg[1]:.1f}, R={orig_avg[2]:.1f}")
        print(f"  출력 평균: B={out_avg[0]:.1f}, G={out_avg[1]:.1f}, R={out_avg[2]:.1f}")
        print(f"  색상 변화: B={color_shift[0]:+.1f}, G={color_shift[1]:+.1f}, R={color_shift[2]:+.1f}")

        if color_shift[2] < -10:  # R 감소
            print(f"  ** {color_name} 색이 탁해졌습니다 (빨간색 손실)")
        if color_shift[1] > 10:  # G 증가
            print(f"  ** {color_name} 색이 주황색으로 시프트됨 (녹색 증가)")

    return {
        'color_name': color_name,
        'target_bgr': target_color_bgr,
        'original_avg_bgr': orig_avg.tolist(),
        'output_avg_bgr': out_avg.tolist(),
        'color_shift_bgr': color_shift.tolist(),
        'original_pixel_count': orig_result['pixel_count'],
        'output_pixel_count': out_result['pixel_count'],
    }


# CLI 인터페이스
if __name__ == '__main__':
    if len(sys.argv) >= 3:
        original = sys.argv[1]
        output = sys.argv[2]

        result = compare_colors(original, output)

        if 'error' not in result:
            suggested = suggest_correction_filter(result)
            if suggested:
                print()
                print(f"[권장 보정 필터]")
                print(f"  -vf \"{suggested}\"")
            else:
                print()
                print("[보정 필터 필요 없음] - 색감이 잘 보존되었습니다.")

            # 빨간색 (#FF6B6B) 구체 검사
            print()
            compare_specific_color(
                original, output,
                (107, 107, 255),  # #FF6B6B in BGR
                "PINKFONG 빨간색"
            )

    elif len(sys.argv) == 2:
        # 동영상에서 프레임 추출
        video = sys.argv[1]
        frame_path = extract_video_frame(video, 0)
        if frame_path:
            print(f"첫 프레임 추출: {frame_path}")
        else:
            print("프레임 추출 실패")

    else:
        print("사용법:")
        print("  색상 비교: python color_validator.py <original.png> <output.png>")
        print("  프레임 추출: python color_validator.py <video.mp4>")
