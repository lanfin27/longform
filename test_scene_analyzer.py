"""
씬 분석기 디버그 테스트

실행: python test_scene_analyzer.py
"""
import os
import sys

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_template_manager():
    """템플릿 매니저 테스트"""
    print("\n" + "=" * 60)
    print("1. 템플릿 매니저 테스트")
    print("=" * 60)

    try:
        from core.prompt.prompt_template_manager import get_template_manager

        manager = get_template_manager()
        print(f"   템플릿 매니저 로드됨: {manager}")

        # 모든 템플릿 확인
        templates = manager.get_all_templates()
        print(f"   등록된 템플릿: {list(templates.keys())}")

        # scene_analysis 템플릿 확인
        scene_prompt = manager.get_prompt("scene_analysis")
        print(f"\n   scene_analysis 프롬프트:")
        print(f"   - 길이: {len(scene_prompt)} 문자")
        print(f"   - 미리보기: {scene_prompt[:200] if scene_prompt else '비어있음'}...")

        # character_extraction 템플릿 확인
        char_prompt = manager.get_prompt("character_extraction")
        print(f"\n   character_extraction 프롬프트:")
        print(f"   - 길이: {len(char_prompt)} 문자")
        print(f"   - 미리보기: {char_prompt[:200] if char_prompt else '비어있음'}...")

        if not scene_prompt:
            print("\n   경고: scene_analysis 프롬프트가 비어있습니다!")
            return False

        if not char_prompt:
            print("\n   경고: character_extraction 프롬프트가 비어있습니다!")
            return False

        print("\n   템플릿 매니저 테스트 통과")
        return True

    except Exception as e:
        print(f"   템플릿 매니저 로드 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_key():
    """API 키 테스트"""
    print("\n" + "=" * 60)
    print("2. API 키 테스트")
    print("=" * 60)

    try:
        from config.settings import ANTHROPIC_API_KEY

        if ANTHROPIC_API_KEY:
            print(f"   ANTHROPIC_API_KEY: {ANTHROPIC_API_KEY[:15]}...")
            return True
        else:
            print("   경고: ANTHROPIC_API_KEY가 설정되지 않았습니다!")
            return False

    except Exception as e:
        print(f"   API 키 로드 실패: {e}")
        return False


def test_scene_analyzer_init():
    """SceneAnalyzer 초기화 테스트"""
    print("\n" + "=" * 60)
    print("3. SceneAnalyzer 초기화 테스트")
    print("=" * 60)

    try:
        from core.script.scene_analyzer import SceneAnalyzer

        analyzer = SceneAnalyzer()
        print(f"   SceneAnalyzer 생성됨: {analyzer}")
        print(f"   - client: {analyzer.client}")
        print(f"   - template_manager: {analyzer.template_manager}")

        # 프롬프트 가져오기 테스트
        base_prompt = analyzer.template_manager.get_prompt("scene_analysis")
        print(f"   - scene_analysis 프롬프트 길이: {len(base_prompt)} 문자")

        return True

    except Exception as e:
        print(f"   SceneAnalyzer 초기화 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_analyze_script():
    """실제 스크립트 분석 테스트 (짧은 테스트 스크립트)"""
    print("\n" + "=" * 60)
    print("4. 스크립트 분석 테스트")
    print("=" * 60)

    # 짧은 테스트 스크립트
    test_script = """
안녕하세요, 오늘은 애플의 역사에 대해 알아보겠습니다.

1976년, 스티브 잡스와 스티브 워즈니악은 차고에서 애플을 창업했습니다.
두 청년은 세상을 바꾸겠다는 꿈을 가지고 있었습니다.

초기 애플 컴퓨터는 취미용 제품이었지만,
애플 II가 출시되면서 큰 성공을 거두게 됩니다.

1984년, 매킨토시가 출시됩니다.
혁신적인 그래픽 사용자 인터페이스는 컴퓨터 역사를 바꿨습니다.

하지만 잡스는 1985년 자신이 세운 회사에서 쫓겨나게 됩니다.
이후 넥스트와 픽사를 설립하며 새로운 도전을 시작합니다.
""".strip()

    print(f"   테스트 스크립트 길이: {len(test_script)} 문자")
    print(f"   내용 미리보기: {test_script[:100]}...")

    try:
        from core.script.scene_analyzer import SceneAnalyzer

        analyzer = SceneAnalyzer()

        print("\n   분석 시작...")
        print("   (Claude API 호출 중... 약 10-30초 소요)")

        import time
        start = time.time()

        result = analyzer.analyze_script(test_script, "ko", "브랜드 역사")

        elapsed = time.time() - start
        print(f"   분석 완료! ({elapsed:.1f}초)")

        # 결과 확인
        print("\n   결과:")
        print(f"   - 씬 수: {len(result.get('scenes', []))}")
        print(f"   - 캐릭터 수: {len(result.get('characters', []))}")
        print(f"   - total_scenes: {result.get('total_scenes', 'N/A')}")
        print(f"   - estimated_duration: {result.get('estimated_duration', 'N/A')}")

        if result.get('error'):
            print(f"\n   오류: {result.get('error')}")
            print(f"   Raw: {result.get('raw_response', '')[:300]}...")

        # 씬 상세
        scenes = result.get('scenes', [])
        if scenes:
            print(f"\n   첫 번째 씬:")
            first = scenes[0]
            for key, value in first.items():
                if isinstance(value, str) and len(value) > 80:
                    print(f"      {key}: {value[:80]}...")
                else:
                    print(f"      {key}: {value}")

        # 캐릭터 상세
        chars = result.get('characters', [])
        if chars:
            print(f"\n   첫 번째 캐릭터:")
            first_char = chars[0]
            for key, value in first_char.items():
                if isinstance(value, str) and len(value) > 80:
                    print(f"      {key}: {value[:80]}...")
                else:
                    print(f"      {key}: {value}")

        return len(scenes) > 0

    except Exception as e:
        print(f"   스크립트 분석 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_load_existing_script():
    """기존 프로젝트의 스크립트 로드 테스트"""
    print("\n" + "=" * 60)
    print("5. 기존 프로젝트 스크립트 로드 테스트")
    print("=" * 60)

    from pathlib import Path

    projects_dir = Path("projects")
    if not projects_dir.exists():
        print("   projects 폴더가 없습니다.")
        return True  # 이건 필수가 아니므로 pass

    # 프로젝트 목록 확인
    projects = [p for p in projects_dir.iterdir() if p.is_dir()]
    print(f"   발견된 프로젝트: {len(projects)}개")

    for project in projects[:3]:  # 최대 3개만 테스트
        print(f"\n   프로젝트: {project.name}")

        # 스크립트 찾기
        scripts_dir = project / "scripts"
        if scripts_dir.exists():
            scripts = list(scripts_dir.glob("*.txt"))
            print(f"      스크립트 파일: {[s.name for s in scripts]}")

            # 첫 번째 스크립트 로드 테스트
            if scripts:
                with open(scripts[0], "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"      스크립트 길이: {len(content)} 문자")
                print(f"      내용 미리보기: {content[:100]}...")
        else:
            print("      scripts 폴더 없음")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("씬 분석기 디버그 테스트")
    print("=" * 60)

    results = {}

    # 1. 템플릿 매니저 테스트
    results["template_manager"] = test_template_manager()

    # 2. API 키 테스트
    results["api_key"] = test_api_key()

    # 3. SceneAnalyzer 초기화 테스트
    results["analyzer_init"] = test_scene_analyzer_init()

    # 4. 기존 스크립트 로드 테스트
    results["load_script"] = test_load_existing_script()

    # 5. 실제 분석 테스트 (API 키가 있을 때만)
    if results["api_key"] and results["template_manager"]:
        user_input = input("\n실제 API 호출 테스트를 실행하시겠습니까? (y/n): ").strip().lower()
        if user_input == 'y':
            results["analyze"] = test_analyze_script()
        else:
            print("\n   API 호출 테스트 건너뜀")
            results["analyze"] = None
    else:
        print("\n   API 키 또는 템플릿 매니저 문제로 분석 테스트 건너뜀")
        results["analyze"] = None

    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)

    for name, result in results.items():
        if result is None:
            status = "건너뜀"
        elif result:
            status = "통과"
        else:
            status = "실패"
        print(f"   {name}: {status}")

    # 전체 결과
    failures = [k for k, v in results.items() if v is False]
    if failures:
        print(f"\n실패한 테스트: {failures}")
        print("위 문제를 해결한 후 다시 테스트하세요.")
    else:
        print("\n모든 테스트 통과!")
