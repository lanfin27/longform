"""
시니어 타겟 톤앤매너 가이드

⚠️ Critical: 모든 스크립트 생성에 이 가이드가 적용되어야 합니다.
타겟 오디언스: 55세 이상 한국인, 60세 이상 일본인
"""

SENIOR_STYLE_GUIDE = {
    "korean": {
        "persona": "청자는 55세 이상 한국인입니다.",
        "tone_rules": [
            "존댓말(합쇼체)을 기본으로 사용하세요.",
            "'~하시죠?', '~해보시는 건 어떨까요?' 같은 공손한 권유형을 사용하세요.",
            "딱딱한 명령형 대신 부드러운 청유형을 사용하세요.",
            "전문용어는 쉬운 말로 풀어서 설명하세요.",
            "문장은 짧고 명확하게 끊어 주세요.",
            "중요한 내용은 반복해서 강조해주세요."
        ],
        "vocabulary_rules": [
            "어려운 한자어 대신 순우리말을 우선 사용하세요.",
            "영어 약어(AI, API 등)는 반드시 한글로 풀어 설명하세요.",
            "신조어나 인터넷 용어는 피하세요.",
            "숫자는 '삼백만 원' 대신 '300만 원'처럼 읽기 쉽게 표기하세요."
        ],
        "structure_rules": [
            "한 문장은 40자 이내로 작성하세요.",
            "한 문단은 3~4문장으로 구성하세요.",
            "문단 사이에는 자연스러운 전환 문구를 넣으세요.",
            "핵심 메시지는 문단 시작에 배치하세요."
        ],
        "examples": {
            "bad": "AI 기반 콘텐츠 제작 프로세스를 자동화하면 생산성이 향상됩니다.",
            "good": "인공지능을 활용하면 영상 만드는 일이 훨씬 쉬워집니다. 어렵지 않으시죠?"
        }
    },

    "japanese": {
        "persona": "청자는 60세 이상 일본인입니다.",
        "tone_rules": [
            "정중한 'です/ます체'를 기본으로 사용하세요.",
            "'~ですよね?(~이시죠?)', '~しましょう(~합시다)' 같은 공감/권유형 어미를 사용하세요.",
            "딱딱한 'である체'는 피하세요.",
            "상대를 높이는 표현을 적절히 섞어주세요."
        ],
        "vocabulary_rules": [
            "어려운 한자어(漢語) 대신 쉬운 고유어(和語, Yamato-kotoba)를 우선 사용하세요.",
            "예: '困難(곤난)' → '難しい(어렵다)', '開始(개시)' → '始める(시작하다)'",
            "카타카나 외래어가 필요할 때는 히라가나로 읽는 법을 병기하세요.",
            "숫자는 '三百万円' 대신 '300万円(さんびゃくまんえん)'처럼 표기하세요."
        ],
        "structure_rules": [
            "한 문장은 40자(일본어 기준) 이내로 작성하세요.",
            "문장 끝에 '。'를 확실히 찍고 끊어주세요.",
            "접속사('それでは', 'そして', 'ところで')로 문단을 자연스럽게 연결하세요."
        ],
        "examples": {
            "bad": "AIを活用したコンテンツ制作プロセスの自動化により、生産性が向上する。",
            "good": "人工知能を使うと、動画を作る作業がずっと楽になりますよ。難しくないですよね？"
        },
        "transcreation_note": """
⚠️ Trans-creation(초월 번역) 원칙:

단순 번역이 아닌 문화 적응형 재창작을 수행하세요.

1. 한국어 원문의 '의도'와 '감정'을 전달하는 것이 목표입니다.
2. 직역하면 어색한 표현은 일본 문화에 맞게 재창작하세요.
3. 한국 고유의 예시(한국 기업, 한국 문화)는 일본 청자가 공감할 수 있는 것으로 대체하세요.
4. 유머나 비유는 일본 시니어가 이해할 수 있는 것으로 바꾸세요.
5. 일본의 계절, 명절, 관습 등을 적절히 활용하세요.
"""
    }
}


def get_style_prompt(language: str) -> str:
    """
    프롬프트에 삽입할 스타일 가이드 텍스트 생성

    Args:
        language: "ko" 또는 "ja"

    Returns:
        스타일 가이드 프롬프트 문자열
    """
    lang_key = "korean" if language in ["ko", "korean", "한국어"] else "japanese"
    guide = SENIOR_STYLE_GUIDE[lang_key]

    prompt = f"""
## 시니어 타겟 톤앤매너 가이드 (필수 적용)

### 페르소나
{guide['persona']}

### 말투 규칙
{chr(10).join(f"- {rule}" for rule in guide['tone_rules'])}

### 어휘 규칙
{chr(10).join(f"- {rule}" for rule in guide['vocabulary_rules'])}

### 구조 규칙
{chr(10).join(f"- {rule}" for rule in guide['structure_rules'])}

### 예시
❌ 나쁜 예: {guide['examples']['bad']}
✅ 좋은 예: {guide['examples']['good']}
"""

    if lang_key == "japanese" and "transcreation_note" in guide:
        prompt += f"\n{guide['transcreation_note']}"

    return prompt


def get_style_checklist(language: str) -> list:
    """
    스타일 체크리스트 반환 (UI 표시용)

    Args:
        language: "ko" 또는 "ja"

    Returns:
        체크리스트 항목 리스트
    """
    lang_key = "korean" if language in ["ko", "korean", "한국어"] else "japanese"
    guide = SENIOR_STYLE_GUIDE[lang_key]

    checklist = []
    checklist.extend(guide['tone_rules'])
    checklist.extend(guide['vocabulary_rules'])
    checklist.extend(guide['structure_rules'])

    return checklist


def get_example(language: str) -> dict:
    """
    좋은 예/나쁜 예 반환

    Args:
        language: "ko" 또는 "ja"

    Returns:
        {"bad": str, "good": str}
    """
    lang_key = "korean" if language in ["ko", "korean", "한국어"] else "japanese"
    return SENIOR_STYLE_GUIDE[lang_key]['examples']
