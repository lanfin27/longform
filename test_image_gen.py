"""
이미지 생성 프롬프트 전달 테스트

실행: python test_image_gen.py
"""
import os
import sys

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.image.image_generator import ImageGenerator, ImageConfig

def test_prompt_delivery():
    """프롬프트가 제대로 전달되는지 테스트"""

    # 테스트 프롬프트
    style_prompt = "flat vector illustration, Korean educational animation style, soft muted colors, clean lines, minimal detail, no text overlay"
    test_subject = "Middle-aged Korean male tax expert in his 40s, wearing a professional business suit"

    full_prompt = f"{style_prompt}, {test_subject}"

    print("=" * 60)
    print("테스트 프롬프트:")
    print("-" * 60)
    print(full_prompt)
    print("-" * 60)
    print(f"프롬프트 길이: {len(full_prompt)} 문자")
    print("=" * 60)

    # API 키 확인
    together_key = os.environ.get("TOGETHER_API_KEY")
    if not together_key:
        print("\n❌ TOGETHER_API_KEY가 설정되지 않았습니다.")
        print("다음 방법 중 하나로 설정하세요:")
        print("  1. .env 파일에 TOGETHER_API_KEY=your_key 추가")
        print("  2. 터미널에서 export TOGETHER_API_KEY=your_key")
        return

    print(f"\n✅ TOGETHER_API_KEY 발견: {together_key[:8]}...")

    # 이미지 생성
    print("\n이미지 생성 중...")

    generator = ImageGenerator()

    config = ImageConfig(
        provider="together",
        model="black-forest-labs/FLUX.1-schnell-Free",
        width=1024,
        height=1024
    )

    result = generator.generate(
        prompt=full_prompt,
        output_path="test_output.png",
        config=config
    )

    print("\n" + "=" * 60)
    print("결과:")
    print("-" * 60)
    print(f"성공: {result.success}")
    print(f"이미지 경로: {result.image_path}")
    print(f"생성 시간: {result.generation_time:.2f}초")

    if result.error:
        print(f"오류: {result.error}")

    if result.prompt:
        print(f"\n사용된 프롬프트 (앞 200자):")
        print(result.prompt[:200] if len(result.prompt) > 200 else result.prompt)

    print("=" * 60)

    if result.success:
        print(f"\n✅ 테스트 성공! 이미지가 저장되었습니다: {result.image_path}")
        print("이미지를 열어서 스타일이 제대로 적용되었는지 확인하세요.")
    else:
        print(f"\n❌ 테스트 실패: {result.error}")

if __name__ == "__main__":
    test_prompt_delivery()
