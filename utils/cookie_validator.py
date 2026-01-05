# -*- coding: utf-8 -*-
"""
쿠키 파일 검증 유틸리티

YouTube 자막 다운로드를 위한 쿠키 파일 유효성 검사
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


def validate_cookies_file(cookies_path: str = "data/cookies.txt") -> Dict:
    """
    쿠키 파일 유효성 검사

    Args:
        cookies_path: 쿠키 파일 경로

    Returns:
        {
            'valid': bool,
            'exists': bool,
            'format_ok': bool,
            'has_youtube': bool,
            'expired': bool,
            'errors': list,
            'warnings': list,
            'info': dict
        }
    """

    path = Path(cookies_path)
    result = {
        'valid': False,
        'exists': False,
        'format_ok': False,
        'has_youtube': False,
        'expired': False,
        'errors': [],
        'warnings': [],
        'info': {}
    }

    # 1. 파일 존재 확인
    if not path.exists():
        result['errors'].append(f'쿠키 파일이 존재하지 않습니다: {cookies_path}')
        return result

    result['exists'] = True
    result['info']['path'] = str(path.resolve())
    result['info']['size'] = path.stat().st_size

    # 파일 크기 확인
    if result['info']['size'] < 100:
        result['errors'].append('쿠키 파일이 너무 작습니다 (100바이트 미만)')
        return result

    # 2. 파일 읽기
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        result['errors'].append(f'파일 읽기 실패: {e}')
        return result

    lines = content.strip().split('\n')
    result['info']['lines'] = len(lines)

    # 3. Netscape 형식 확인
    is_netscape = False
    for line in lines[:10]:
        line_lower = line.lower()
        if '# netscape' in line_lower or '# http cookie' in line_lower:
            is_netscape = True
            break
        if line.startswith('#') and 'cookie' in line_lower:
            is_netscape = True
            break

    # 탭으로 구분된 쿠키 라인이 있는지 확인
    tab_lines = [l for l in lines if '\t' in l and not l.startswith('#')]
    if tab_lines:
        is_netscape = True

    if not is_netscape:
        result['errors'].append('Netscape 쿠키 형식이 아닙니다. "Get cookies.txt LOCALLY" 확장 프로그램으로 다시 내보내세요.')
    else:
        result['format_ok'] = True

    # 4. YouTube/Google 도메인 쿠키 확인
    youtube_cookies = []
    google_cookies = []
    expired_cookies = []
    current_time = datetime.now().timestamp()

    important_cookies = {
        'CONSENT': False,
        'LOGIN_INFO': False,
        'SID': False,
        'HSID': False,
        'SSID': False,
        'APISID': False,
        'SAPISID': False,
        'VISITOR_INFO1_LIVE': False,
        'YSC': False,
    }

    for line in lines:
        if line.startswith('#') or not line.strip():
            continue

        parts = line.split('\t')
        if len(parts) >= 7:
            domain = parts[0].strip()
            path = parts[2] if len(parts) > 2 else ''
            secure = parts[3] if len(parts) > 3 else ''
            expiry = parts[4] if len(parts) > 4 else '0'
            name = parts[5] if len(parts) > 5 else ''
            value = parts[6] if len(parts) > 6 else ''

            # YouTube 도메인 확인
            if 'youtube.com' in domain:
                youtube_cookies.append({
                    'domain': domain,
                    'name': name,
                    'expiry': expiry,
                    'has_value': bool(value)
                })

                # 중요 쿠키 체크
                if name in important_cookies:
                    important_cookies[name] = True

            # Google 도메인 확인 (YouTube 인증에 필요)
            if 'google.com' in domain:
                google_cookies.append({
                    'domain': domain,
                    'name': name,
                    'expiry': expiry
                })

                # 중요 쿠키 체크
                if name in important_cookies:
                    important_cookies[name] = True

            # 만료 확인
            try:
                exp_time = int(expiry)
                if exp_time > 0 and exp_time < current_time:
                    expired_cookies.append(name)
            except:
                pass

    result['info']['youtube_cookies'] = len(youtube_cookies)
    result['info']['google_cookies'] = len(google_cookies)
    result['info']['total_cookies'] = len(youtube_cookies) + len(google_cookies)

    # 중요 쿠키 체크
    found_important = [k for k, v in important_cookies.items() if v]
    missing_important = [k for k, v in important_cookies.items() if not v]

    result['info']['important_cookies_found'] = found_important
    result['info']['important_cookies_missing'] = missing_important

    if not youtube_cookies and not google_cookies:
        result['errors'].append('YouTube/Google 쿠키가 없습니다. YouTube.com에서 로그인 후 쿠키를 내보내세요.')
    else:
        result['has_youtube'] = True

    # 중요 쿠키 누락 경고
    if missing_important:
        # 최소한 SID나 LOGIN_INFO가 있어야 함
        if 'SID' in missing_important and 'LOGIN_INFO' in missing_important:
            result['warnings'].append(f'로그인 관련 쿠키가 없습니다. YouTube에 로그인한 상태에서 쿠키를 내보내세요.')

    if expired_cookies:
        # 만료된 쿠키가 많으면 경고
        if len(expired_cookies) > 5:
            result['expired'] = True
            result['warnings'].append(f'만료된 쿠키 {len(expired_cookies)}개 발견. 쿠키를 갱신하세요.')

    # 5. 최종 유효성
    result['valid'] = (
        result['exists'] and
        result['format_ok'] and
        result['has_youtube'] and
        not result['expired'] and
        len(result['errors']) == 0
    )

    return result


def print_cookie_status(cookies_path: str = "data/cookies.txt") -> Dict:
    """쿠키 상태 출력"""

    result = validate_cookies_file(cookies_path)

    print("\n" + "=" * 60)
    print("🍪 쿠키 파일 검증 결과")
    print("=" * 60)

    print(f"파일 존재: {'✅' if result['exists'] else '❌'}")
    print(f"형식 올바름: {'✅' if result['format_ok'] else '❌'}")
    print(f"YouTube 쿠키: {'✅' if result['has_youtube'] else '❌'}")
    print(f"만료됨: {'⚠️ 일부 만료' if result['expired'] else '✅ 정상'}")
    print(f"최종 유효: {'✅ 유효' if result['valid'] else '❌ 무효'}")

    if result['info']:
        print(f"\n📊 상세 정보:")
        print(f"  경로: {result['info'].get('path', 'N/A')}")
        print(f"  크기: {result['info'].get('size', 0):,} bytes")
        print(f"  줄 수: {result['info'].get('lines', 0)}")
        print(f"  YouTube 쿠키: {result['info'].get('youtube_cookies', 0)}개")
        print(f"  Google 쿠키: {result['info'].get('google_cookies', 0)}개")

        if result['info'].get('important_cookies_found'):
            print(f"  인증 쿠키: {', '.join(result['info']['important_cookies_found'][:5])}")

    if result['errors']:
        print(f"\n❌ 에러:")
        for err in result['errors']:
            print(f"  - {err}")

    if result['warnings']:
        print(f"\n⚠️ 경고:")
        for warn in result['warnings']:
            print(f"  - {warn}")

    if not result['valid']:
        print(f"\n💡 해결 방법:")
        print("  1. Chrome에서 YouTube.com에 로그인")
        print("  2. 확장프로그램 'Get cookies.txt LOCALLY' 클릭")
        print("  3. 'Export' 클릭하여 다운로드")
        print(f"  4. 파일을 '{cookies_path}'로 저장")

    print("=" * 60 + "\n")

    return result


def get_cookie_status_summary(cookies_path: str = "data/cookies.txt") -> Dict:
    """
    Streamlit UI용 쿠키 상태 요약

    Returns:
        {
            'status': 'ok' | 'warning' | 'error',
            'message': str,
            'details': dict
        }
    """

    result = validate_cookies_file(cookies_path)

    if result['valid']:
        return {
            'status': 'ok',
            'message': f"✅ 쿠키 파일 유효 ({result['info'].get('total_cookies', 0)}개 쿠키)",
            'details': result
        }

    if not result['exists']:
        return {
            'status': 'error',
            'message': '❌ 쿠키 파일 없음 - Rate Limit 위험 높음',
            'details': result
        }

    if not result['format_ok']:
        return {
            'status': 'error',
            'message': '❌ 쿠키 파일 형식 오류',
            'details': result
        }

    if not result['has_youtube']:
        return {
            'status': 'error',
            'message': '❌ YouTube 쿠키 없음 - 다시 내보내기 필요',
            'details': result
        }

    if result['expired']:
        return {
            'status': 'warning',
            'message': '⚠️ 일부 쿠키 만료됨 - 갱신 권장',
            'details': result
        }

    if result['warnings']:
        return {
            'status': 'warning',
            'message': f"⚠️ {result['warnings'][0]}",
            'details': result
        }

    return {
        'status': 'error',
        'message': '❌ 쿠키 파일 문제 발견',
        'details': result
    }


if __name__ == "__main__":
    import sys

    # 경로가 주어지면 사용, 아니면 기본값
    cookies_path = sys.argv[1] if len(sys.argv) > 1 else "data/cookies.txt"
    print_cookie_status(cookies_path)
