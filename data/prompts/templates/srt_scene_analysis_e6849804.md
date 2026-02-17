---
template_id: srt_scene_analysis_e6849804
template_name: # SRT 배치 씬 분석 프롬프트 (v3.1 - 브랜드 로고 허용, 씬별 고유 이미지 생성 강화)
category: srt_scene_analysis
description: 사용자 정의 SRT 분석 프롬프트
updated_at: 2026-01-29T22:31:28.627150
---

## 🔴🔴🔴 [ABSOLUTE CRITICAL] scene_id 정확성 절대 규칙 🔴🔴🔴

### ⚠️ 최우선 규칙: 입력받은 scene_id를 절대 변경하지 마세요!

**절대 금지 행위:**
| 금지 행위 | 설명 |
|-----------|------|
| scene_id 변경 | 입력된 scene_id와 다른 값 반환 ❌ |
| scene_id 순서 변경 | 입력 순서와 다른 순서로 반환 ❌ |
| scene_id 누락 | 입력된 scene_id 중 일부 누락 ❌ |
| scene_id 추가 | 입력에 없는 scene_id 추가 ❌ |
| 다른 씬의 스크립트 사용 | 씬 16의 스크립트를 씬 19에 사용 ❌ |

**✅ 반드시 지킬 규칙:**
1. **입력된 scene_id를 그대로 반환** - 한 자리도 바꾸지 않음
2. **입력 순서 유지** - 씬 1, 4, 7 순서로 받았으면 1, 4, 7 순서로 반환
3. **모든 씬 포함** - 입력된 모든 scene_id에 대해 결과 반환
4. **각 씬의 스크립트와 scene_id 매칭 확인** - 씬 16의 스크립트가 씬 19에 들어가면 안됨

### 🔴 scene_id와 스크립트 매칭 검증 예시

**입력:**
```
씬 16: "삼성이 진짜 무서운 회사구나,"
씬 19: "자, 일단 기본부터 깔고 가야 해요."
```

**✅ 올바른 출력:**
```json
[
  {"scene_id": 16, "image_prompt": "삼성 본사 관련 이미지...", ...},
  {"scene_id": 19, "image_prompt": "하만 브랜드 소개 이미지...", ...}
]
```

**❌ 잘못된 출력 (절대 금지!):**
```json
[
  {"scene_id": 16, "image_prompt": "삼성 본사...", ...},
  {"scene_id": 19, "image_prompt": "삼성 본사...", ...}  ← 씬 16과 동일한 내용!
]
```

### 🔴 분석 전 필수 확인 사항

JSON 응답 생성 전 반드시 확인:
- [ ] 입력된 각 scene_id와 해당 스크립트를 정확히 파악했는가?
- [ ] 각 scene_id에 대해 **해당 씬의 스크립트 내용**을 기반으로 이미지 프롬프트를 생성했는가?
- [ ] 반환할 JSON의 scene_id가 입력과 100% 일치하는가?
- [ ] 서로 다른 씬에 동일한 이미지 프롬프트를 사용하지 않았는가?

---

## 🔴🔴🔴 [CRITICAL] 스크립트 원본 보존 절대 규칙 🔴🔴🔴
### ⚠️ 가장 중요한 규칙: 스크립트 텍스트를 절대 수정하지 마세요!
**절대 금지 행위:**
| 금지 행위 | 설명 |
|-----------|------|
| 문장 바꾸기 | 원본 문장을 다른 표현으로 변경 ❌ |
| 문장 추가 | 스크립트에 없는 문장 생성 ❌ |
| 문장 요약 | 여러 문장을 하나로 합치기 ❌ |
| 아웃트로 대체 | 마지막을 "구독과 좋아요" 등으로 바꾸기 ❌ |
**✅ 반드시 지킬 규칙:**
- script_text는 원본 스크립트에서 **한 글자도 바꾸지 않고** 그대로 복사
- 스크립트에 없는 문장은 절대 생성하지 않음
- 마지막 씬도 원본 스크립트의 마지막 문장 그대로 사용
---
# SRT 배치 씬 분석 프롬프트 (v3.0.1 - background_prompt_en 규칙 강화)
다음 씬들을 분석하고 JSON 배열로 응답해주세요.
## 각 씬에 대해 포함할 필드
- scene_id: 씬 번호 **(⚠️ 입력된 값 그대로 반환!)**
- image_prompt: 한국어 이미지 생성 프롬프트 (텍스트/문자 제외, 브랜드 로고는 허용)
- image_prompt_en: 영문 이미지 프롬프트 (FLUX용, 상세하게, 끝에 "no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable" 필수 포함)
- image_prompt_korean_text: 한글 텍스트 포함 영문 이미지 프롬프트 (🟢 아래 규칙 참조)
- background_prompt: 한국어 배경 프롬프트 (캐릭터/인물 설명 제외, 배경과 환경만 묘사)
- background_prompt_en: 영문 배경 프롬프트 (🔴🔴🔴🔴🔴 아래 필수 규칙 반드시 참조!)
- character_prompt: 한국어 캐릭터 프롬프트 (사람/인물이 있는 경우만, 없으면 빈 문자열)
- character_prompt_en: 영문 캐릭터 프롬프트 (사람/인물이 있는 경우만, 없으면 빈 문자열, 끝에 "no text, no logos on clothing, no name tags" 포함)
- visual_elements: 시각 요소 리스트
- direction_guide: 연출 가이드
- video_prompt_character: Character animation description (ENGLISH, 인물 없으면 빈 문자열)
- video_prompt_full: Full scene video description (ENGLISH)
- characters: 등장 캐릭터 리스트 (🔴 반드시 사람/인물만! 각 캐릭터에 name, visual_prompt 포함, 인물 없으면 빈 배열 [])
- location: 배경 장소
- mood: 분위기

## 🟢🟢🟢 [NEW] 브랜드 로고 허용 규칙 🟢🟢🟢

### ⚠️ 핵심 원칙
**텍스트(글자/문자)는 금지하되, 브랜드 로고는 허용합니다!**

### 🟢 허용되는 것 (Brand Logos OK)
| 허용 항목 | 예시 | 프롬프트 표현 |
|-----------|------|--------------|
| 기업 로고 | 삼성, 애플, 하만, 테슬라 로고 | "Samsung logo visible on device", "with Apple logo" |
| 제품 로고 | 갤럭시, 아이폰, 하만카돈 로고 | "Harman Kardon logo on speaker grille" |
| 브랜드 심볼 | 삼성 타원형, 애플 사과, 테슬라 T | "Tesla T symbol on steering wheel" |
| 제품에 새겨진 로고 | TV, 스마트폰, 스피커의 브랜드 마크 | "brand logo subtly visible on the device" |

### 🔴 금지되는 것 (Text NOT OK)
| 금지 항목 | 예시 | 이유 |
|-----------|------|------|
| 읽을 수 있는 텍스트 | "Samsung Electronics", "Galaxy S24" | 글자/문자임 |
| 슬로건/문구 | "Do What You Can't", "Think Different" | 읽을 수 있는 텍스트 |
| 숫자/가격 | "$999", "2024", "80억 달러" | 읽을 수 있는 숫자 |
| 간판/표지판 | "Welcome", "Exit", "Samsung Store" | 읽을 수 있는 텍스트 |
| 말풍선/자막 | 대화 내용, 설명 텍스트 | 읽을 수 있는 텍스트 |

### 🟢 image_prompt_en 끝부분 필수 문구 (변경됨!)
```
기존: "absolutely no text, no letters, no words, no signs, no writing, no numbers, no speech bubbles, no readable content"

변경: "no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"
```

### 🟢 로고 활용 가이드
기업/브랜드가 언급된 씬에서는 적극적으로 로고를 활용하세요:

| 씬 주제 | 로고 활용 예시 |
|--------|---------------|
| 삼성전자 제품 | "Samsung logo visible on the smartphone back", "TV with Samsung logo in corner" |
| 하만카돈 오디오 | "Harman Kardon logo elegantly displayed on speaker", "JBL logo on soundbar" |
| 애플 제품 | "Apple logo glowing on laptop lid", "iPhone with Apple logo" |
| 테슬라 차량 | "Tesla T logo on steering wheel center", "Tesla emblem on front grille" |
| 자동차 인포테인먼트 | "Harman logo integrated into dashboard display" |

## 🔴🔴🔴 [CRITICAL - 최최우선] 씬별 고유 이미지 생성 규칙 🔴🔴🔴

### ⚠️ 가장 중요한 원칙
**각 씬은 반드시 해당 씬의 스크립트 내용에 맞는 고유한 이미지 프롬프트를 가져야 합니다!**
**연속된 씬이라도 동일하거나 유사한 이미지 프롬프트 사용 절대 금지!**

### 🔴🔴 씬별 이미지 차별화 필수 규칙

**절대 금지 - 동일 이미지 반복:**
```
❌ 씬 13, 14, 15 모두 "Advanced semiconductor fabrication facility cleanroom..." 사용
❌ 씬 16, 17, 18 모두 "Premium consumer electronics display..." 사용
❌ 영상 주제만 보고 모든 씬에 동일한 "템플릿 이미지" 적용
```

**필수 - 각 씬마다 고유한 이미지:**
```
✅ 각 씬의 스크립트 텍스트를 개별 분석
✅ 스크립트의 감정/톤/키워드에 맞는 고유한 시각 요소 선택
✅ 같은 주제라도 다른 앵글, 다른 구도, 다른 시각 요소 사용
✅ 연속된 씬은 시각적 "흐름"을 만들되 각각 구별되어야 함
```

### 🔴 1단계: 각 씬의 스크립트 개별 분석 (필수!)

모든 씬에 대해 다음을 **개별적으로** 분석하세요:

| 분석 항목 | 질문 | 이미지 반영 방법 |
|-----------|------|-----------------|
| **핵심 메시지** | 이 씬에서 전달하려는 핵심 내용은? | 해당 메시지를 시각화 |
| **감정/톤** | 놀람? 강조? 전환? 설명? 결론? | 감정에 맞는 색감/구도 |
| **키워드** | 스크립트에서 가장 중요한 단어는? | 해당 키워드의 시각적 표현 |
| **맥락적 위치** | 이 씬은 영상에서 어떤 역할? (도입/전개/클라이맥스/마무리) | 역할에 맞는 연출 |

### 🔴 2단계: 스크립트 유형별 이미지 차별화

#### A. 감정/반응 표현 스크립트
| 스크립트 예시 | 감정 | 이미지 표현 방법 |
|--------------|------|-----------------|
| "삼성이 진짜 무서운 회사구나" | 놀람, 경외 | 거대한 규모감 강조 - 거대한 건물 실루엣, 글로벌 지도 위 확장, 하늘을 찌르는 본사 빌딩, 드라마틱한 조명, Samsung 로고 강조 |
| "정말 놀랍지 않나요?" | 놀람, 흥미 | 인상적인 시각 요소 클로즈업, 극적인 조명, 경이로운 분위기 |
| "저도 소름 돋았어요" | 강렬한 인상 | 강렬한 대비, 임팩트 있는 구도, 드라마틱한 앵글 |
| "대단하죠?" | 감탄 | 성과/결과물 강조, 성공적인 이미지, 밝고 긍정적인 톤 |

#### B. 전환/연결 스크립트
| 스크립트 예시 | 역할 | 이미지 표현 방법 |
|--------------|------|-----------------|
| "자, 시작해볼게요" | 도입 | 오프닝 느낌 - 넓은 전경, 시작점 느낌, 문이 열리는 듯한 구도 |
| "이런 생각이 들더라고요" | 관점 전환 | 새로운 시각 - 다른 앵글, 클로즈업에서 와이드로, 또는 그 반대 |
| "아, 그리고 솔직히 말씀드리면요" | 추가 정보 | 디테일 강조 - 특정 부분 클로즈업, 세부 사항 부각 |
| "정리하자면요" | 요약 | 전체 조망 - 와이드 샷, 여러 요소를 한 프레임에 |

#### C. 설명/정보 스크립트
| 스크립트 예시 | 정보 유형 | 이미지 표현 방법 |
|--------------|----------|-----------------|
| "완전히 이해하시게 될 거예요" | 이해 촉진 | 명확하고 깔끔한 구도, 핵심 요소 중심 배치, 교육적 느낌 |
| "이게 왜 중요하냐면요" | 중요성 강조 | 해당 요소를 중심에 배치, 스포트라이트 효과 |
| "구체적으로 말씀드리면" | 상세 설명 | 세부 디테일 클로즈업, 매크로 샷 |

### 🔴 3단계: 동일 주제 내 씬별 시각적 변화 전략

같은 영상 주제(예: 삼성전자/하만)라도 각 씬마다 **다른 시각적 접근**을 사용:

| 씬 순서 | 시각적 변화 전략 | 예시 (삼성전자 주제) |
|--------|-----------------|---------------------|
| 도입부 씬 | 전체 조망, 와이드 샷 | 삼성 본사 건물 전경 with Samsung logo, 스카이라인 |
| 전개 씬 1 | 제품 포커스 | 스마트폰 클로즈업 with Samsung logo on back |
| 전개 씬 2 | 다른 제품/영역 | TV/디스플레이 쇼케이스 with Samsung logo |
| 전개 씬 3 | 기술/혁신 | 반도체 웨이퍼, R&D 시설 |
| 강조 씬 | 임팩트 있는 구도 | 드라마틱한 조명의 제품 히어로샷 with brand logo |
| 전환 씬 | 새로운 관점 | 다른 앵글, 다른 환경 |
| 마무리 씬 | 종합/정리 | 여러 제품이 함께 있는 라이프스타일 씬 |

### 🔴 4단계: 구체적 예시 - 연속 씬의 차별화

**예시: 반도체 관련 영상의 연속 3개 씬**

```
씬 13 스크립트: "완전히 이해하시게 될 거예요."
→ 분석: 이해/교육 촉진, 명확한 설명 시작
→ 이미지: 반도체 웨이퍼의 클린하고 명확한 클로즈업, 교육적 다이어그램 느낌, 밝고 깔끔한 조명
✅ "Crystal clear macro shot of silicon wafer showing intricate circuit patterns, educational documentary style, bright clean lighting, sharp focus on chip details, pristine laboratory environment, informative and accessible aesthetic, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"

씬 14 스크립트: "아, 그리고 솔직히 말씀드리면요."
→ 분석: 추가 정보/솔직한 관점, 디테일 추가
→ 이미지: 반도체 제조 과정의 다른 측면, 로봇 팔이 웨이퍼를 다루는 장면, 제조 공정 디테일
✅ "Robotic arms precisely handling silicon wafers in semiconductor fab, detailed view of manufacturing process, blue UV lighting casting dramatic shadows, industrial precision and accuracy, behind-the-scenes perspective, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"

씬 15 스크립트: "저도 이거 조사하면서 좀 소름 돋았어요."
→ 분석: 강렬한 인상, 놀라움, 임팩트
→ 이미지: 반도체의 놀라운 미세 구조, 드라마틱한 매크로 샷, 경이로운 스케일 강조
✅ "Dramatic extreme macro shot revealing impossibly tiny transistor structures on microchip, mind-bending scale comparison, awe-inspiring nanotechnology, moody dramatic lighting emphasizing the incredible engineering feat, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"
```

**예시: 삼성전자 관련 영상의 연속 3개 씬 (로고 활용)**

```
씬 16 스크립트: "삼성이 진짜 무서운 회사구나."
→ 분석: 경외감, 거대한 규모, 압도적 존재감
→ 이미지: 삼성의 거대한 규모와 영향력 - 거대한 본사 건물 with Samsung logo prominently displayed, 글로벌 확장, 드라마틱한 스케일
✅ "Imposing Samsung headquarters tower with Samsung logo prominently displayed reaching into dramatic cloudy sky, massive corporate campus spreading across landscape, powerful architectural presence, awe-inspiring scale and grandeur, cinematic wide angle shot, dramatic golden hour lighting, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"

씬 17 스크립트: "이런 생각이 들더라고요."
→ 분석: 관점 전환, 새로운 시각, 개인적 인사이트
→ 이미지: 더 개인적/인간적 관점 - 제품을 사용하는 환경, 일상 속 삼성 기술 with subtle brand logos
✅ "Cozy modern living room bathed in warm evening light, large Samsung TV with subtle Samsung logo softly glowing displaying beautiful imagery, smartphone with Samsung logo on coffee table, seamless technology integration into daily life, intimate and relatable perspective, warm ambient lighting, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"

씬 18 스크립트: "자, 시작해볼게요."
→ 분석: 새로운 시작, 도입, 전환점
→ 이미지: 시작/출발 느낌 - 문이 열리는 듯한 구도, 새로운 장의 시작, 밝은 미래 느낌
✅ "Bright modern Samsung innovation lab with glass doors opening to reveal cutting-edge prototypes, Samsung logo visible on lab entrance, sense of new beginnings and possibilities, morning sunlight streaming through windows, fresh and optimistic atmosphere, welcoming perspective, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"
```

### 🔴 5단계: 씬별 고유성 검증 체크리스트

이미지 프롬프트 생성 후 **반드시** 다음을 확인:

| 검증 항목 | 확인 질문 |
|----------|----------|
| **고유성** | 이전/이후 씬과 이미지 프롬프트가 다른가? |
| **스크립트 반영** | 해당 씬의 스크립트 감정/메시지가 이미지에 반영되었는가? |
| **시각적 차별화** | 앵글, 구도, 조명, 색감 중 최소 2개 이상이 다른 씬과 다른가? |
| **맥락적 적합성** | 영상 흐름에서 이 씬의 역할에 맞는 이미지인가? |
| **로고 활용** | 기업/브랜드 관련 씬에서 로고를 적절히 활용했는가? |

### 🔴🔴 금지: 템플릿 이미지 반복 사용

다음과 같은 "템플릿화"는 **절대 금지**:

```
❌ 모든 "삼성전자" 씬에 동일한 "전자제품 쇼룸" 이미지 사용
❌ 모든 "반도체" 씬에 동일한 "클린룸" 이미지 사용  
❌ 모든 "추상적 스크립트" 씬에 동일한 "영상 주제 기본 이미지" 사용
❌ 스크립트 내용을 무시하고 영상 주제만으로 이미지 결정
```

## 🔴🔴🔴 [CRITICAL] 스크립트 주제/키워드 기반 이미지 프롬프트 생성 규칙 🔴🔴🔴

### ⚠️ 핵심 원칙
**이미지 프롬프트는 반드시 스크립트에서 언급된 주제, 기업, 제품, 개념을 시각적으로 표현해야 합니다!**
**일반적인 사무실/회의실 배경을 기본값으로 사용하지 마세요!**

### 🔴 1단계: 스크립트에서 핵심 키워드/주제 추출 (필수!)

모든 씬 분석 시 **가장 먼저** 스크립트에서 다음을 식별하세요:

| 추출 대상 | 예시 | 이미지에 반영할 요소 |
|-----------|------|---------------------|
| **기업명** | 삼성전자, 애플, 테슬라, 하만 | 해당 기업의 대표 제품, 기술, 시설 + **브랜드 로고** |
| **제품/기술** | 스마트폰, 반도체, AI, 전기차 | 해당 제품/기술의 실물 또는 관련 이미지 |
| **산업/분야** | 자동차, IT, 금융, 헬스케어 | 해당 산업의 대표적 시각 요소 |
| **인물/직함** | CEO, 창업자, 엔지니어 | 해당 인물 유형의 활동 장면 |
| **개념/트렌드** | M&A, IPO, 투자, 성장 | 해당 개념을 시각화한 장면 |
| **숫자/데이터** | 2조원, 80억 달러, 64% | 성장, 규모를 나타내는 시각 요소 |
| **감정/반응 표현** | 무섭다, 놀랍다, 소름, 대단하다 | 해당 감정을 시각적으로 전달하는 구도/조명 |

### 🔴 2단계: 추출된 키워드를 이미지로 변환 (필수!)

**기업명이 언급된 경우 - 해당 기업의 대표 시각 요소 + 로고 사용:**

| 기업명 | 이미지에 포함할 시각 요소 |
|--------|---------------------------------------------|
| 삼성전자 | 스마트폰 with Samsung logo, 대형 TV with Samsung logo, 반도체 웨이퍼, 가전제품 쇼룸, 첨단 공장, OLED 디스플레이, 본사 건물 with Samsung logo |
| 애플 | 스마트폰 with Apple logo, 노트북 with glowing Apple logo, 태블릿, 미니멀한 제품 전시대, 현대적인 리테일 스토어 |
| 테슬라 | 전기차 with Tesla emblem, 충전소 with Tesla logo, 배터리 팩, 기가팩토리, 자율주행 기술 |
| 엔비디아 | GPU 카드 with NVIDIA logo, 데이터센터, AI 서버, 고성능 컴퓨팅 |
| 하만 | 프리미엄 오디오 스피커 with Harman Kardon logo, 자동차 인포테인먼트 시스템 with Harman logo, 사운드 시스템 with JBL logo |
| 현대차/기아 | 자동차 생산라인, 전기차 with Hyundai/Kia emblem, 자동차 전시장 |

**감정/반응 표현이 있는 경우 - 해당 감정을 시각적으로 전달:**

| 감정 표현 | 시각적 표현 방법 |
|-----------|-----------------|
| "무섭다/무서운" | 거대한 스케일, 압도적 구도, 드라마틱한 앵글, 경외감 조성, 브랜드 로고로 기업 정체성 강조 |
| "놀랍다/놀라운" | 임팩트 있는 클로즈업, 극적인 조명, 경이로운 디테일 |
| "소름 돋는다" | 강렬한 대비, 드라마틱한 매크로 샷, 숨겨진 디테일 노출 |
| "대단하다" | 성과 강조, 성공적인 이미지, 승리감 있는 구도 |
| "기대된다" | 밝은 미래 이미지, 희망적 조명, 가능성 암시 |

**제품/기술이 언급된 경우:**

| 제품/기술 | 이미지에 포함할 시각 요소 |
|-----------|--------------------------|
| 반도체 | 반도체 웨이퍼, 클린룸, 현미경, 칩 클로즈업, 반도체 공장 |
| 스마트폰 | 스마트폰 디바이스 with brand logo, 앱 화면(텍스트 없이), 손에 든 폰 |
| AI/인공지능 | 데이터센터, 서버랙, 뉴럴네트워크 시각화, 로봇 |
| 전기차 | 전기차 with brand emblem, 충전 포트, 배터리, 친환경 이미지 |
| 디스플레이 | 대형 스크린 with brand logo, OLED 패널, 곡면 디스플레이, TV |

**비즈니스 개념이 언급된 경우:**

| 개념 | 이미지에 포함할 시각 요소 |
|------|--------------------------|
| M&A/인수합병 | 악수하는 손, 계약서 서명, 두 건물이 합쳐지는 이미지, 양사 로고 |
| 투자/펀딩 | 성장 그래프(숫자 없이), 금화/동전 스택, 투자 미팅 |
| 성장/확장 | 상승하는 화살표, 확장되는 건물, 글로벌 지도 |
| 혁신/기술 | 연구소, 프로토타입, 첨단 장비, 실험실 |

### 🔴 3단계: 구체적 예시 - 올바른 vs 잘못된 이미지 프롬프트

**예시 1: 감정 표현이 있는 스크립트 (로고 활용)**
```
스크립트: "삼성이 진짜 무서운 회사구나."

❌ 잘못된 프롬프트 (감정 무시, 로고 미활용):
"Premium consumer electronics display featuring smartphones and tablets on white pedestals, modern retail environment with soft spotlighting..."

✅ 올바른 프롬프트 (경외감/압도감 표현 + 로고 활용):
"Imposing Samsung Electronics headquarters tower with Samsung logo prominently displayed dramatically silhouetted against moody sky, massive scale of corporate campus visible from aerial perspective, powerful architectural presence conveying corporate might, dramatic cinematic lighting with long shadows, awe-inspiring grandeur and overwhelming scale, low angle shot emphasizing dominance, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"
```

**예시 2: 관점 전환 스크립트**
```
스크립트: "이런 생각이 들더라고요."

❌ 잘못된 프롬프트 (이전 씬과 동일):
"Premium consumer electronics display featuring Samsung smartphones..."

✅ 올바른 프롬프트 (개인적 관점, 일상 속 기술 + 로고):
"Intimate home setting with warm evening ambiance, Samsung TV with subtle Samsung logo softly glowing in cozy living room, smartphone with Samsung logo resting on wooden coffee table beside steaming cup, personal and relatable technology integration, thoughtful contemplative mood, warm golden hour lighting through curtains, human-scale perspective on technology, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"
```

**예시 3: 새로운 시작 스크립트**
```
스크립트: "자, 시작해볼게요."

❌ 잘못된 프롬프트 (이전 씬과 동일):
"Premium consumer electronics display featuring Samsung smartphones..."

✅ 올바른 프롬프트 (시작/출발 느낌):
"Bright modern technology innovation lab with sleek glass doors swinging open, Samsung logo visible on entrance, fresh morning sunlight flooding into pristine workspace, sense of new beginnings and exciting possibilities, cutting-edge prototypes visible on clean workbenches, optimistic and energetic atmosphere, welcoming wide angle perspective inviting viewer in, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"
```

### 🔴 4단계: 질문형/대화형 스크립트 처리 규칙

질문형 스크립트라도 **질문의 대상/주제**를 이미지로 표현해야 합니다:

| 스크립트 유형 | 처리 방법 |
|--------------|----------|
| "삼성전자 하면 뭐가 떠오르세요?" | → 삼성전자 제품/기술 이미지 with Samsung logos |
| "반도체가 왜 중요할까요?" | → 반도체/첨단 기술 이미지 |
| "전기차 시장은 어떨까요?" | → 전기차/친환경 모빌리티 이미지 with brand emblems |
| "이 회사 아세요?" | → 해당 회사의 대표 제품/서비스 이미지 with brand logo |

**절대 금지**: 질문형이라는 이유로 물음표, 생각하는 사람, 추상적 배경 등 사용 ❌

### 🔴 5단계: 복합 주제 처리

스크립트에 여러 주제가 언급된 경우, **가장 핵심적인 주제**를 선택하여 이미지화:

```
스크립트: "삼성전자가 하만을 인수해서 자동차 오디오 시장에 진출했습니다"

핵심 주제 분석:
1. 삼성전자 (기업)
2. 하만 (기업/오디오)
3. 자동차 오디오 (제품)
4. 인수 (비즈니스 행위)

→ 가장 시각적으로 표현하기 좋은 주제 선택: "자동차 오디오 시스템" + 양사 로고

✅ 올바른 프롬프트:
"Premium automotive interior featuring high-end car audio speaker system with Harman Kardon logo on speaker grilles, detailed view of door-mounted speakers and dashboard audio controls, luxury vehicle cabin with leather trim, Samsung logo subtly visible on infotainment display, ambient lighting highlighting speaker components, sophisticated in-car entertainment setup, warm interior lighting, close-up to medium shot, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"
```

## 🔴🔴🔴 [CRITICAL] 추상적 스크립트 씬의 구체적 이미지 프롬프트 생성 규칙 🔴🔴🔴

### ⚠️ 핵심 원칙
**스크립트가 추상적이더라도 이미지 프롬프트는 반드시 구체적이고 상세해야 합니다!**
**단, 추상적 스크립트라도 영상 전체의 주제/맥락 + 해당 씬의 역할/감정을 모두 반영해야 합니다!**

### 🔴 추상적 스크립트 식별
다음과 같은 스크립트는 "추상적 스크립트"로 간주합니다:
| 유형 | 예시 |
|------|------|
| 전환/연결 문구 | "아, 그리고 솔직히 말씀드리면요", "자, 시작해볼게요", "이런 생각이 들더라고요" |
| 감정 표현 | "완전히 이해하시게 될 거예요", "정말 놀랍지 않나요?", "기대되시죠?" |
| 질문/수사 | "어떻게 생각하세요?", "왜 그럴까요?", "궁금하시죠?" |
| 요약/마무리 | "정리하자면요", "결론적으로", "한마디로" |
| 인사/시작 | "안녕하세요", "반갑습니다", "오늘은" |

### 🔴 추상적 스크립트 처리 방법 (필수!)

**1단계: 영상 전체 맥락 + 씬별 역할 파악** (가장 중요!)
- 이 영상의 **주제 기업/제품/기술**은 무엇인가?
- 이 씬은 영상에서 **어떤 역할**인가? (도입/전환/강조/마무리)
- 이 씬의 스크립트가 전달하는 **감정/톤**은 무엇인가?

**2단계: 맥락 + 역할 + 감정을 모두 반영한 이미지 생성**

| 영상 주제 | 씬 역할 | 추상적 스크립트 | 고유한 이미지 프롬프트 |
|-----------|--------|----------------|---------------------|
| 삼성전자 | 도입 | "자, 시작해볼게요" | 삼성 혁신 센터 입구가 열리는 장면 with Samsung logo, 가능성의 시작 |
| 삼성전자 | 감탄 | "무서운 회사구나" | 압도적인 삼성 본사 건물 with prominent Samsung logo, 경외감 조성 |
| 삼성전자 | 관점전환 | "이런 생각이 들더라고요" | 일상 속 삼성 제품 with subtle brand logos, 개인적 관점 |
| 반도체 | 설명 | "완전히 이해하시게 될 거예요" | 교육적 느낌의 웨이퍼 클로즈업, 명확한 구도 |
| 반도체 | 추가정보 | "솔직히 말씀드리면요" | 제조 과정 디테일, 비하인드 씬 느낌 |
| 반도체 | 놀라움 | "소름 돋았어요" | 드라마틱한 나노 구조 매크로, 경이로운 스케일 |

**절대 금지 - 이런 프롬프트 생성 금지:**
```
❌ "Abstract pattern with a bright background, no text or letters, soft gradient effect..."
❌ "Colorful abstract shapes, modern design, clean background..."
❌ "Modern office conference room with glass walls..." (주제와 무관한 일반 사무실)
❌ 여러 씬에 동일한 이미지 프롬프트 반복 사용
```

### 🔴 추상적 프롬프트 금지 키워드
다음 키워드로 시작하거나 주로 구성된 프롬프트는 **절대 금지**:
| 금지 키워드 | 이유 |
|------------|------|
| Abstract pattern | 너무 모호함 |
| Abstract shapes | 구체성 없음 |
| Colorful background | 장면 묘사 없음 |
| Simple design | 시각적 정보 부족 |
| Gradient effect | 배경만 있고 내용 없음 |
| Geometric patterns | 스타일에만 의존하게 됨 |
| Minimalist shapes | 구체적 사물 없음 |
| 'start' button | UI 요소는 이미지로 부적합 |
| Question marks | 기호는 이미지로 부적합 |

### 🔴 일반적 배경 사용 금지 (주제 무관 시)
다음과 같은 **일반적인 배경**은 영상 주제와 직접 관련이 없으면 사용 금지:
| 금지 패턴 | 대신 사용할 것 |
|-----------|---------------|
| Generic office conference room | 영상 주제 관련 장소/제품 with brand logos |
| Modern home office with laptop | 영상에서 다루는 기술/제품 |
| Cozy cafe with coffee | 영상 주제의 핵심 시각 요소 |
| Classroom with whiteboard | 영상에서 설명하는 기술/개념 |

### 🔴 최소 프롬프트 요구사항
모든 image_prompt_en은 다음을 **반드시** 충족해야 합니다:
1. **최소 40단어 이상** (no text... 부분 제외)
2. **영상 주제와 직접 관련된 시각 요소** 포함
3. **해당 씬의 감정/역할**이 반영된 구도/조명/분위기
4. **이전/이후 씬과 다른 고유한 시각적 접근**
5. **구체적인 제품/기술/장소** 1개 이상 명시
6. **기업 관련 씬에서는 브랜드 로고 활용** 권장

## 🔴🔴🔴🔴🔴 [ABSOLUTE CRITICAL] 배경 프롬프트 (background_prompt_en) 작성 절대 규칙 🔴🔴🔴🔴🔴

### ⚠️⚠️⚠️ 이 규칙을 반드시 지켜야 합니다! 위반 시 심각한 오류 발생! ⚠️⚠️⚠️

**핵심 원칙: background_prompt_en은 image_prompt_en을 기반으로 작성**

---

### 🔴🔴🔴 CASE 1: 인물이 없는 씬 (characters = [], character_prompt_en = "")

## ⚠️⚠️⚠️ 절대 규칙: 인물이 없으면 background_prompt_en은 image_prompt_en을 100% 그대로 복사! ⚠️⚠️⚠️

**반드시 지켜야 할 것:**
| 규칙 | 설명 |
|------|------|
| 100% 동일 복사 | `background_prompt_en` = `image_prompt_en` (완전히 동일, 한 글자도 다르면 안됨!) |
| 축약 금지 | 긴 프롬프트를 짧게 줄이기 ❌ |
| 요약 금지 | 핵심만 추려서 다시 쓰기 ❌ |
| 일부만 복사 금지 | 문장 중간이나 끝부분만 가져오기 ❌ |
| 새로 작성 금지 | 완전히 새로운 문장으로 다시 쓰기 ❌ |
| 수정 금지 | 단어나 표현을 다른 것으로 대체 ❌ |

**✅ 올바른 예시 (인물 없는 씬 - 100% 동일!):**
```json
{
  "characters": [],
  "character_prompt_en": "",
  "image_prompt_en": "Concept image of a car as a computer on wheels, symbolizing the future of automotive technology, sleek futuristic vehicle design with advanced digital interfaces, holographic displays and AI integration, vibrant and dynamic composition showcasing technological innovation, modern urban environment in background, evoking a sense of progress and transformation, subtle brand logos integrated into design, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
  "background_prompt_en": "Concept image of a car as a computer on wheels, symbolizing the future of automotive technology, sleek futuristic vehicle design with advanced digital interfaces, holographic displays and AI integration, vibrant and dynamic composition showcasing technological innovation, modern urban environment in background, evoking a sense of progress and transformation, subtle brand logos integrated into design, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"
}
```
→ **완전히 동일!** 한 글자도 다르지 않음 ✅

**❌ 잘못된 예시 1 (일부만 복사 - 절대 금지!):**
```json
{
  "characters": [],
  "image_prompt_en": "Concept image of a car as a computer on wheels, symbolizing the future of automotive technology, sleek futuristic vehicle design with advanced digital interfaces, holographic displays and AI integration, vibrant and dynamic composition showcasing technological innovation, modern urban environment in background...",
  "background_prompt_en": "Modern urban environment in background, evoking a sense of progress and transformation..."
}
```
→ **❌ 틀림!** image_prompt_en의 일부(끝부분)만 복사됨

**❌ 잘못된 예시 2 (새로 작성 - 절대 금지!):**
```json
{
  "characters": [],
  "image_prompt_en": "High-tech motherboard with glowing components and digital connections, vibrant and dynamic composition highlighting technological complexity...",
  "background_prompt_en": "Digital technology background with circuit patterns and glowing elements..."
}
```
→ **❌ 틀림!** background_prompt_en이 완전히 새로 작성됨

**❌ 잘못된 예시 3 (축약 - 절대 금지!):**
```json
{
  "characters": [],
  "image_prompt_en": "Imposing Samsung Electronics headquarters tower with Samsung logo prominently displayed dramatically silhouetted against moody clouded sky, massive corporate campus spreading impressively across landscape, powerful architectural presence...",
  "background_prompt_en": "Samsung headquarters tower against moody sky, corporate campus..."
}
```
→ **❌ 틀림!** 프롬프트가 축약됨

---

### 🟡 CASE 2: 인물이 있는 씬 (characters ≠ [] 또는 character_prompt_en ≠ "")

**규칙: image_prompt_en에서 인물 관련 표현만 제거하고 나머지는 100% 그대로 유지**

**제거할 인물 관련 표현:**
| 제거 대상 | 예시 |
|-----------|------|
| 직함/역할 | CEO, engineer, worker, employee, businessman, manager, presenter |
| 일반 인물 | man, woman, person, people, figure, character, human |
| 인물 동작 | presenting, standing, walking, sitting, monitoring, working |
| 인물 묘사 | confident expression, wearing suit, middle-aged |
| 그룹 표현 | executives, team, audience, crowd, employees |

**유지할 요소 (절대 삭제/수정 금지!):**
| 유지 대상 | 설명 |
|-----------|------|
| 모든 장소/공간 | boardroom, factory, office, cafe, studio 등 |
| 모든 사물/제품 | desk, laptop, coffee cup, bookshelf, chair 등 |
| 모든 환경/분위기 | warm lighting, cozy atmosphere, professional mood 등 |
| 모든 기술/컨셉 | modern design, minimalist style 등 |
| 브랜드 로고 | Samsung logo, Apple logo, Harman logo 등 (유지!) |
| 끝부분 no text... | 그대로 유지 |

**✅ 올바른 예시 (인물 있는 씬 - 인물 표현만 삭제):**
```json
{
  "characters": [{"name": "비즈니스맨", "visual_prompt": "..."}],
  "image_prompt_en": "Modern corporate boardroom with CEO presenting to executives, sleek glass table, city skyline view through floor-to-ceiling windows, warm ambient lighting, minimalist decor, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
  "background_prompt_en": "Modern corporate boardroom, sleek glass table, city skyline view through floor-to-ceiling windows, warm ambient lighting, minimalist decor, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable"
}
```
→ "with CEO presenting to executives" 부분만 삭제됨, 나머지 100% 동일 ✅

---

### 🔴🔴🔴 절대 금지 행위 (background_prompt_en 작성 시)

| 금지 행위 | 설명 | 예시 |
|-----------|------|------|
| **축약** | image_prompt_en을 짧게 줄이기 | ❌ 긴 프롬프트 → 짧은 프롬프트 |
| **요약** | 핵심만 추려서 다시 쓰기 | ❌ |
| **새로 작성** | image_prompt_en과 완전히 다른 내용 | ❌ "Digital background...", "Abstract pattern..." |
| **일부만 복사** | 문장 중간이나 끝부분만 가져오기 | ❌ "Modern urban environment..." (끝부분만) |
| **네거티브 추가** | "no people", "no human figures" 추가 | ❌ |
| **내용 변경** | 단어나 표현을 다른 것으로 대체 | ❌ |

---

### 🔴 background_prompt_en 작성 체크리스트 (각 씬마다 반드시 확인!)

**인물이 없는 씬 (characters = []):**
- [ ] background_prompt_en이 image_prompt_en과 **글자 하나까지 완전히 동일**한가?
- [ ] 축약하거나 요약하지 않았는가?
- [ ] 일부만 복사하지 않았는가?
- [ ] 새로 작성하지 않았는가?

**인물이 있는 씬 (characters ≠ []):**
- [ ] 인물 관련 표현만 제거했는가?
- [ ] 나머지 내용은 image_prompt_en과 동일한가?
- [ ] "no people" 등 네거티브를 추가하지 않았는가?

## 🔴🔴🔴 [CRITICAL] 캐릭터 추출 규칙 - 반드시 사람/인물만 🔴🔴🔴

**캐릭터(characters)의 정의**: 
- ✅ **오직 사람(human)만** 캐릭터로 인정
- ✅ 실제 인물, 가상의 인물, 애니메이션 인물 등 **인간 형태의 존재만** 포함

**❌ 캐릭터로 추출 금지 (절대 포함하지 않음):**
| 금지 대상 | 예시 |
|-----------|------|
| 기업/브랜드 로고 | Samsung logo, Apple logo, Harman logo, ZF logo ❌ |
| 제품/사물 | 자동차, 스마트폰, 건물, 기계 ❌ |
| 동물 | 개, 고양이, 새 ❌ |
| 추상적 개념 | 아이디어, 미래, 혁신 ❌ |
| 로봇/AI (비인간형) | 로봇 팔, 드론, 센서 ❌ |
| 아이콘/심볼 | 화살표, 차트, 그래프 ❌ |

**✅ 캐릭터로 추출 허용:**
| 허용 대상 | 예시 |
|-----------|------|
| 실명 인물 | CEO 김영한, 발표자, 인터뷰이 ✅ |
| 익명 인물 | 비즈니스맨, 엔지니어, 직원들 ✅ |
| 역할 기반 인물 | 나레이터, 전문가, 고객 ✅ |
| 군중/그룹 | 회의 참석자들, 관객들 ✅ |

**인물이 없는 경우 처리:**
- `characters`: 빈 배열 `[]` 반환
- `character_prompt`: 빈 문자열 `""` 반환
- `character_prompt_en`: 빈 문자열 `""` 반환
- `video_prompt_character`: 빈 문자열 `""` 반환

## ⚠️ 중요 규칙
1. **🔴🔴🔴 scene_id는 입력된 값 그대로 반환** - 절대 변경/누락/추가 금지
2. **🔴🔴🔴 각 씬의 스크립트에 맞는 고유한 이미지 프롬프트** - 다른 씬의 내용 사용 금지
3. **🔴🔴🔴 각 씬마다 고유한 이미지 프롬프트 생성** - 동일/유사한 프롬프트 연속 사용 절대 금지
4. **🔴🔴 스크립트의 감정/톤/역할을 이미지에 반영** - 단순 영상 주제 템플릿 금지
5. **🔴🔴 스크립트에 언급된 기업/제품/기술을 이미지에 직접 반영** - 일반적인 사무실/회의실 배경 기본값 사용 금지
6. **🟢🟢 기업/브랜드 관련 씬에서는 브랜드 로고 적극 활용** - 텍스트는 금지, 로고는 허용
7. **🔴 추상적 스크립트라도 영상 주제 + 씬 역할 + 감정을 모두 반영** - Abstract pattern, colorful background 등 모호한 프롬프트 금지
8. **🔴 characters 배열에는 반드시 사람/인물만 포함** - 로고, 제품, 사물, 동물 등은 절대 포함 금지
9. **🔴 씬에 사람/인물이 없으면 characters는 빈 배열 `[]`로 반환**
10. **🔴🔴🔴 background_prompt_en 절대 규칙:**
    - **인물 없으면**: background_prompt_en = image_prompt_en (**100% 동일 복사, 한 글자도 바꾸지 않음!**)
    - **인물 있으면**: image_prompt_en에서 인물 표현만 삭제, 나머지 100% 유지
    - 축약 금지, 요약 금지, 새로 작성 금지, 일부만 복사 금지!
11. characters 배열의 각 캐릭터에는 반드시 visual_prompt를 영문으로 포함
12. video_prompt_character와 video_prompt_full은 반드시 영어로 작성
13. 카메라 움직임 포함 (zoom, pan, dolly 등)
14. **🔴 image_prompt_en 텍스트 규칙:**
    - ❌ 금지: 읽을 수 있는 텍스트, 문자, 숫자, 슬로건, 말풍선
    - ✅ 허용: 브랜드 로고 (Samsung logo, Apple logo, Harman Kardon logo 등)

## 🟢 image_prompt_korean_text 작성 규칙

**목적**: 외부 AI 이미지 생성기에서 한글 텍스트가 포함된 이미지를 생성하기 위한 프롬프트

**작성 방법**:
1. image_prompt_en의 시각적 묘사를 기반으로 작성 (영어로 작성)
2. "no text, no letters..." 부분을 **제거**
3. 해당 씬의 나레이션에서 핵심 메시지를 추출하여 한글 텍스트로 포함
4. 아래 글씨체 스타일을 **반드시** 적용
5. 🔴 **[필수] 숫자/날짜 변환 규칙을 반드시 적용** (아래 참조)
6. 🔴 **[필수] 텍스트 배치 규칙을 반드시 적용** (아래 참조)

**한글 텍스트 추출 규칙**:
- **헤드라인**: 나레이션의 핵심 키워드/메시지 (5-15자)
- **서브타이틀**: 부가 설명 또는 맥락 (10-25자)

**글씨체 스타일 (고정 - 반드시 포함)**:
- headline: `in handwritten pen script style with casual brush strokes`
- subtitle: `in informal handwritten font style`
- all text: `all Korean text in natural hand-drawn pen calligraphy style with slight irregularity`

## 🔴🔴🔴 [중요] 텍스트 배치 규칙 - 상단~중단 유연 배치, 하단만 금지 🔴🔴🔴

**⚠️ 핵심 원칙**: 
- **텍스트(글자)는 이미지 상단~중단에 자연스럽게 배치** (이미지와 어울리게)
- **이미지/비주얼 요소는 전체 영역**에 자연스럽게 채워짐 (하단 포함)
- **하단 25~30%에만 텍스트 금지** (자막 영역이므로)

**✅ 텍스트 배치 허용 위치**:
- `at the top` - 이미지 상단
- `in the upper area` - 상단 영역
- `in the middle section` - 중단 영역
- `integrated naturally with the main visual` - 메인 비주얼과 자연스럽게 통합
- `overlaid harmoniously on the scene` - 장면 위에 조화롭게 오버레이
- `positioned to complement the composition` - 구도를 보완하는 위치에 배치
- `floating alongside the main subject` - 주요 피사체 옆에 자연스럽게 배치

**❌ 텍스트 배치 금지 위치 (하단만)**:
- ~~text at the bottom~~ ❌
- ~~text in the lower 25%~~ ❌
- ~~text below the main visual~~ ❌

**텍스트 배치 원칙**:
1. **헤드라인**: 상단 또는 이미지와 어울리는 중단 위치에 배치
2. **서브타이틀**: 헤드라인 근처 또는 메인 비주얼과 조화로운 위치에 배치
3. 텍스트는 **이미지 상단 70% 영역 내**에서 자유롭게 배치 가능
4. **이미지/비주얼 요소**는 전체 프레임을 자연스럽게 채움 (하단 포함 OK)
5. 텍스트 위치는 장면의 구도와 시각적 밸런스를 고려하여 결정

## 🔴 숫자/날짜 한국어 변환 규칙 (image_prompt_korean_text 필수 적용)

나레이션에 영어 숫자/날짜가 포함된 경우 **반드시 한국어로 변환**하여 헤드라인/서브타이틀에 사용:

### 📊 금액 변환
| 영어 | 한국어 | 예시 |
|------|--------|------|
| trillion | 조 | "$2 trillion" → "2조 달러" |
| billion | 억 | "$8 billion" → "80억 달러" |
| million | 만/백만 | "$50 million" → "5천만 달러" |
| $ / dollar | 달러 | "$100" → "100달러" |
| won / KRW | 원 | "2 trillion won" → "2조원" |

### 📅 날짜/연도 변환
| 영어 | 한국어 | 예시 |
|------|--------|------|
| January~December | 1월~12월 | "December 2025" → "2025년 12월" |
| Q1~Q4 | 1분기~4분기 | "Q3 2024" → "2024년 3분기" |
| first half | 상반기 | "first half of 2025" → "2025년 상반기" |
| second half | 하반기 | "second half of 2025" → "2025년 하반기" |

### 📈 퍼센트/비율 변환
| 영어 | 한국어 | 예시 |
|------|--------|------|
| percent / % | % | "64 percent" → "64%" |
| growth rate | 성장률 | "50% growth rate" → "50% 성장률" |
| market share | 점유율 | "30% market share" → "30% 점유율" |

### 🏆 순위/수량 변환
| 영어 | 한국어 | 예시 |
|------|--------|------|
| 1st / first | 1위 | "ranked 1st" → "1위" |
| 2nd / second | 2위 | "ranked 2nd" → "2위" |
| million units | 만 대 | "10 million units" → "1천만 대" |
| people/employees | 명 | "5,000 employees" → "5천 명" |

**image_prompt_korean_text 형식 (유연 배치 버전)**:
[시각적 묘사 - 전체 프레임을 채우는 비주얼], headline text in Korean reading "[헤드라인 한글 - 숫자는 한국어로 변환]" [배치 위치: at the top / in the upper-middle area / integrated with the main visual 등 장면에 맞게 선택] in handwritten pen script style with casual brush strokes, subtitle text in Korean reading "[서브타이틀 한글 - 숫자는 한국어로 변환]" [배치 위치: 헤드라인과 조화롭게] in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity, text positioned harmoniously within the upper 70% of the image avoiding the bottom subtitle area, visual elements fill the entire frame naturally, [나머지 시각 요소]

=== 분석할 씬들 ===
{scenes_content}

=== 응답 형식 ===
JSON 배열만 반환하세요. 다른 텍스트 없이 순수 JSON만 출력하세요.
```json
[
  {
    "scene_id": 13,
    "image_prompt": "반도체 웨이퍼의 선명한 클로즈업, 정교한 회로 패턴, 교육적 다큐멘터리 스타일, 밝고 깔끔한 조명, 핵심 디테일에 선명한 포커스",
    "image_prompt_en": "Crystal clear macro shot of silicon wafer showing intricate circuit patterns in stunning detail, educational documentary style presentation, bright clean laboratory lighting, sharp focus on microscopic chip structures, pristine research environment aesthetic, informative and accessible visual approach, professional technology photography, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "image_prompt_korean_text": "Crystal clear macro shot of silicon wafer showing intricate circuit patterns, educational documentary style, bright clean lighting, headline text in Korean reading \"반도체의 세계\" at the top in handwritten pen script style with casual brush strokes, subtitle text in Korean reading \"완전히 이해하시게 될 거예요\" in the upper area in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity, text positioned harmoniously within the upper 70% of the image avoiding the bottom subtitle area",
    "background_prompt": "반도체 웨이퍼의 선명한 클로즈업, 정교한 회로 패턴, 교육적 다큐멘터리 스타일, 밝고 깔끔한 조명",
    "background_prompt_en": "Crystal clear macro shot of silicon wafer showing intricate circuit patterns in stunning detail, educational documentary style presentation, bright clean laboratory lighting, sharp focus on microscopic chip structures, pristine research environment aesthetic, informative and accessible visual approach, professional technology photography, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "character_prompt": "",
    "character_prompt_en": "",
    "characters": [],
    "video_prompt_character": "",
    "video_prompt_full": "Smooth macro camera movement revealing intricate silicon wafer patterns, educational documentary feel, bright clean lighting illuminating microscopic details",
    "visual_elements": ["반도체 웨이퍼", "회로 패턴", "매크로 샷", "연구 환경"],
    "direction_guide": "교육적이고 명확한 느낌의 매크로 클로즈업, 시청자가 이해하기 쉽도록 밝고 선명하게",
    "location": "반도체 연구소",
    "mood": "교육적이고 명확한"
  },
  {
    "scene_id": 14,
    "image_prompt": "로봇 팔이 실리콘 웨이퍼를 정밀하게 다루는 장면, 반도체 팹 제조 공정 디테일, 푸른 UV 조명의 드라마틱한 그림자",
    "image_prompt_en": "Robotic arms precisely handling silicon wafers in semiconductor fabrication facility, detailed behind-the-scenes view of manufacturing process, blue ultraviolet lighting casting dramatic shadows across machinery, industrial precision and mechanical accuracy on display, authentic factory floor perspective, cool blue and metallic color palette, medium shot showing process detail, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "image_prompt_korean_text": "Robotic arms handling silicon wafers in semiconductor fab, blue UV lighting with dramatic shadows, industrial precision, headline text in Korean reading \"솔직히 말씀드리면\" at the top in handwritten pen script style with casual brush strokes, subtitle text in Korean reading \"제조 공정의 비밀\" in the upper area in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity, text positioned harmoniously within the upper 70% of the image avoiding the bottom subtitle area",
    "background_prompt": "로봇 팔이 실리콘 웨이퍼를 다루는 반도체 팹, 제조 공정 디테일, 푸른 UV 조명의 드라마틱한 그림자",
    "background_prompt_en": "Robotic arms precisely handling silicon wafers in semiconductor fabrication facility, detailed behind-the-scenes view of manufacturing process, blue ultraviolet lighting casting dramatic shadows across machinery, industrial precision and mechanical accuracy on display, authentic factory floor perspective, cool blue and metallic color palette, medium shot showing process detail, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "character_prompt": "",
    "character_prompt_en": "",
    "characters": [],
    "video_prompt_character": "",
    "video_prompt_full": "Camera follows robotic arm movement handling wafers, blue UV lighting creates atmospheric shadows, industrial manufacturing process in motion",
    "visual_elements": ["로봇 팔", "웨이퍼 핸들링", "UV 조명", "제조 공정"],
    "direction_guide": "비하인드 씬 느낌으로 제조 공정의 디테일을 보여주는 미디엄 샷",
    "location": "반도체 제조 시설",
    "mood": "산업적이고 정밀한"
  },
  {
    "scene_id": 15,
    "image_prompt": "극도로 미세한 트랜지스터 구조를 보여주는 드라마틱한 매크로 샷, 경이로운 나노 스케일, 숨막히는 엔지니어링",
    "image_prompt_en": "Dramatic extreme macro shot revealing impossibly tiny transistor structures on microchip surface, mind-bending nanotechnology scale comparison, awe-inspiring engineering achievement visible in microscopic detail, moody dramatic lighting emphasizing the incredible technological feat, sense of wonder and amazement, deep contrast and rich colors, cinematic close-up perspective, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "image_prompt_korean_text": "Extreme macro shot of tiny transistor structures on microchip, mind-bending nano scale, dramatic moody lighting, headline text in Korean reading \"소름 돋는 기술\" at the top in handwritten pen script style with casual brush strokes, subtitle text in Korean reading \"나노의 경이로움\" in the upper area in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity, text positioned harmoniously within the upper 70% of the image avoiding the bottom subtitle area",
    "background_prompt": "극도로 미세한 트랜지스터 구조, 경이로운 나노 스케일, 드라마틱한 조명",
    "background_prompt_en": "Dramatic extreme macro shot revealing impossibly tiny transistor structures on microchip surface, mind-bending nanotechnology scale comparison, awe-inspiring engineering achievement visible in microscopic detail, moody dramatic lighting emphasizing the incredible technological feat, sense of wonder and amazement, deep contrast and rich colors, cinematic close-up perspective, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "character_prompt": "",
    "character_prompt_en": "",
    "characters": [],
    "video_prompt_character": "",
    "video_prompt_full": "Slow dramatic zoom into microchip surface revealing impossibly small transistor structures, moody lighting creates sense of awe, cinematic reveal of nanotechnology",
    "visual_elements": ["트랜지스터 구조", "나노 스케일", "마이크로칩", "드라마틱 조명"],
    "direction_guide": "경이로움과 놀라움을 전달하는 극적인 매크로 샷, 드라마틱한 조명으로 임팩트 강조",
    "location": "마이크로칩 표면",
    "mood": "경이롭고 드라마틱한"
  },
  {
    "scene_id": 16,
    "image_prompt": "거대한 삼성전자 본사 타워 with Samsung 로고가 드라마틱한 하늘을 배경으로 우뚝 솟은 모습, 압도적인 기업 규모, 경외감을 주는 건축",
    "image_prompt_en": "Imposing Samsung Electronics headquarters tower with Samsung logo prominently displayed dramatically silhouetted against moody clouded sky, massive corporate campus spreading impressively across landscape, powerful architectural presence conveying overwhelming corporate might, dramatic cinematic lighting with long shadows at golden hour, awe-inspiring scale and grandeur, low angle shot emphasizing dominance and power, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "image_prompt_korean_text": "Imposing Samsung headquarters tower with Samsung logo against dramatic sky, massive corporate campus, powerful architectural presence, headline text in Korean reading \"무서운 회사\" at the top in handwritten pen script style with casual brush strokes, subtitle text in Korean reading \"삼성의 압도적 규모\" in the upper area in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity, text positioned harmoniously within the upper 70% of the image avoiding the bottom subtitle area",
    "background_prompt": "거대한 삼성전자 본사 타워 with Samsung 로고, 드라마틱한 하늘, 압도적인 기업 규모, 경외감을 주는 건축",
    "background_prompt_en": "Imposing Samsung Electronics headquarters tower with Samsung logo prominently displayed dramatically silhouetted against moody clouded sky, massive corporate campus spreading impressively across landscape, powerful architectural presence conveying overwhelming corporate might, dramatic cinematic lighting with long shadows at golden hour, awe-inspiring scale and grandeur, low angle shot emphasizing dominance and power, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "character_prompt": "",
    "character_prompt_en": "",
    "characters": [],
    "video_prompt_character": "",
    "video_prompt_full": "Dramatic low angle shot of towering Samsung headquarters with Samsung logo visible, camera slowly tilts up revealing massive scale, dramatic clouds moving behind building, golden hour lighting",
    "visual_elements": ["본사 타워", "Samsung 로고", "기업 캠퍼스", "드라마틱 하늘", "건축적 위용"],
    "direction_guide": "로우 앵글로 삼성의 압도적 규모와 힘을 강조, Samsung 로고로 브랜드 정체성 표현, 경외감을 불러일으키는 드라마틱한 연출",
    "location": "삼성전자 본사",
    "mood": "경외감과 압도감"
  },
  {
    "scene_id": 17,
    "image_prompt": "따뜻한 저녁 분위기의 아늑한 거실, Samsung 로고가 보이는 삼성 TV가 부드럽게 빛나고 Samsung 로고가 있는 스마트폰이 커피 테이블 위에, 일상 속 기술 통합",
    "image_prompt_en": "Cozy modern living room bathed in warm evening golden light, large Samsung TV with subtle Samsung logo softly glowing displaying beautiful imagery, sleek smartphone with Samsung logo resting on wooden coffee table beside steaming cup, seamless technology integration into comfortable daily life, intimate and personally relatable perspective, warm amber and earth tone color palette, inviting medium shot of lifestyle scene, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "image_prompt_korean_text": "Cozy living room with warm evening light, Samsung TV with Samsung logo softly glowing, smartphone with Samsung logo on coffee table, comfortable daily life, headline text in Korean reading \"이런 생각이\" at the top in handwritten pen script style with casual brush strokes, subtitle text in Korean reading \"일상 속의 기술\" in the upper area in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity, text positioned harmoniously within the upper 70% of the image avoiding the bottom subtitle area",
    "background_prompt": "따뜻한 저녁 분위기의 아늑한 거실, Samsung 로고가 보이는 삼성 TV, Samsung 로고가 있는 스마트폰, 커피 테이블, 일상 속 기술",
    "background_prompt_en": "Cozy modern living room bathed in warm evening golden light, large Samsung TV with subtle Samsung logo softly glowing displaying beautiful imagery, sleek smartphone with Samsung logo resting on wooden coffee table beside steaming cup, seamless technology integration into comfortable daily life, intimate and personally relatable perspective, warm amber and earth tone color palette, inviting medium shot of lifestyle scene, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "character_prompt": "",
    "character_prompt_en": "",
    "characters": [],
    "video_prompt_character": "",
    "video_prompt_full": "Gentle camera movement through cozy living room, warm evening light creating intimate atmosphere, Samsung TV and devices with Samsung logos naturally integrated into home life",
    "visual_elements": ["거실", "Samsung TV", "Samsung 로고", "스마트폰", "저녁 조명", "일상 풍경"],
    "direction_guide": "따뜻하고 개인적인 관점에서 일상 속 삼성 기술을 보여주는 라이프스타일 씬, 제품에 Samsung 로고가 자연스럽게 보이도록",
    "location": "현대적인 거실",
    "mood": "따뜻하고 개인적인"
  },
  {
    "scene_id": 18,
    "image_prompt": "밝은 삼성 혁신 연구소 입구에 Samsung 로고, 유리문이 열리며 최첨단 프로토타입이 보이는 장면, 새로운 시작의 느낌",
    "image_prompt_en": "Bright modern Samsung innovation lab with Samsung logo visible on entrance, sleek glass doors swinging open to reveal cutting-edge prototypes, fresh morning sunlight flooding into pristine high-tech workspace, sense of new beginnings and exciting possibilities ahead, welcoming wide angle perspective inviting viewer into the space, optimistic and energetic atmosphere, clean white and blue color palette, establishing shot of new chapter beginning, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "image_prompt_korean_text": "Bright Samsung innovation lab with Samsung logo on entrance, glass doors opening, cutting-edge prototypes visible, morning sunlight, sense of new beginnings, headline text in Korean reading \"시작해볼게요\" at the top in handwritten pen script style with casual brush strokes, subtitle text in Korean reading \"새로운 장의 시작\" in the upper area in informal handwritten font style, all Korean text in natural hand-drawn pen calligraphy style with slight irregularity, text positioned harmoniously within the upper 70% of the image avoiding the bottom subtitle area",
    "background_prompt": "밝은 삼성 혁신 연구소 with Samsung 로고, 유리문이 열리는 장면, 최첨단 프로토타입, 아침 햇살",
    "background_prompt_en": "Bright modern Samsung innovation lab with Samsung logo visible on entrance, sleek glass doors swinging open to reveal cutting-edge prototypes, fresh morning sunlight flooding into pristine high-tech workspace, sense of new beginnings and exciting possibilities ahead, welcoming wide angle perspective inviting viewer into the space, optimistic and energetic atmosphere, clean white and blue color palette, establishing shot of new chapter beginning, no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable",
    "character_prompt": "",
    "character_prompt_en": "",
    "characters": [],
    "video_prompt_character": "",
    "video_prompt_full": "Camera moves forward through opening glass doors into bright Samsung innovation lab with Samsung logo visible, morning sunlight creates welcoming atmosphere, sense of embarking on new journey",
    "visual_elements": ["혁신 연구소", "Samsung 로고", "유리문", "프로토타입", "아침 햇살"],
    "direction_guide": "문이 열리며 새로운 시작을 암시하는 와이드 샷, Samsung 로고가 입구에 보이며 브랜드 정체성 표현, 밝고 희망적인 분위기",
    "location": "삼성 혁신 연구소",
    "mood": "희망적이고 새로운 시작"
  }
]
```

→ **주목**: 모든 예시에서 characters=[]이므로 background_prompt_en이 image_prompt_en과 **100% 동일**합니다!

### 🔴🔴🔴 최종 확인 체크리스트 (응답 전 반드시 확인!) 🔴🔴🔴

**[필수 검증 1] scene_id 확인:**
- [ ] **🔴🔴🔴 scene_id가 입력된 값과 100% 일치하는가?** → 절대 변경 금지
- [ ] **🔴🔴🔴 각 씬의 이미지가 해당 씬의 스크립트 내용을 반영하는가?** → 다른 씬 내용 사용 금지

**[필수 검증 2] 이미지 고유성 확인:**
- [ ] **🔴🔴 각 씬의 이미지 프롬프트가 고유한가?** → 연속된 씬이라도 동일/유사한 프롬프트 사용 금지
- [ ] **🔴🔴 스크립트의 감정/톤이 이미지에 반영되었는가?** → "무섭다"는 경외감, "소름"은 드라마틱하게

**[필수 검증 3] 브랜드 로고 활용:**
- [ ] **🟢🟢 기업/브랜드 관련 씬에서 로고를 활용했는가?** → Samsung logo, Harman logo 등 적극 활용
- [ ] **스크립트에 기업/제품/기술명이 있는가?** → 해당 기업/제품/기술의 시각 요소 + 로고를 이미지에 반영했는가?

**[필수 검증 4] 기타 확인:**
- [ ] **질문형 스크립트인가?** → 질문의 대상/주제를 이미지로 표현했는가? (물음표, 추상적 배경 사용 금지)
- [ ] **추상적 스크립트 씬**: 영상 전체 주제 + 해당 씬의 역할/감정을 모두 반영한 고유 이미지인가?
- [ ] **일반적인 사무실/회의실 배경**을 기본값으로 사용하지 않았는가?
- [ ] **모든 image_prompt_en**: 최소 40단어 이상이며, 영상 주제와 직접 관련된 시각 요소가 충분한가?
- [ ] **모든 image_prompt_en 끝부분**: "no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable" 포함 확인

**[필수 검증 5] background_prompt_en 확인 (⚠️⚠️⚠️ 가장 중요! ⚠️⚠️⚠️):**
- [ ] **🔴🔴🔴 인물 없는 씬 (characters=[])**: background_prompt_en이 image_prompt_en과 **글자 하나까지 완전히 동일**한가?
- [ ] **🔴🔴 인물 있는 씬**: background_prompt_en에서 인물 표현만 삭제되고 나머지는 동일한가?
- [ ] **축약/요약/새로 작성/일부만 복사**하지 않았는가?
- [ ] **"no people", "no human figures" 등 네거티브**가 추가되지 않았는가?

**⚠️⚠️⚠️ 특히 background_prompt_en을 반드시 다시 확인하세요! ⚠️⚠️⚠️**
**인물 없는 씬에서 background_prompt_en ≠ image_prompt_en이면 심각한 오류입니다!**