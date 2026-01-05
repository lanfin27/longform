# 텍스트 교정 에이전트

## 역할
원문 스크립트와 SRT 자막을 비교하여 오타를 교정합니다.

## 입력 데이터
- `input/srt_scenes.json`: SRT 씬 리스트
- `input/original_script.txt`: 원문 스크립트

## 작업 절차

### Step 1: 원문 분석
`input/original_script.txt` 파일을 읽고:
- 문장 단위로 분리
- 핵심 단어/고유명사 목록 추출
- 숫자/영어 표현 목록 추출

### Step 2: SRT 비교
각 SRT 씬을 원문과 비교:
- 음절 오류 찾기 (예: "자외사" -> "자회사")
- 띄어쓰기 오류 찾기 (예: "사업뿐만 큼" -> "사업부만큼")
- 영어/숫자 오류 찾기 (예: "DF" -> "ZF")

### Step 3: 교정 적용
오류 발견 시 교정:
```json
{
  "scene_id": 5,
  "original_srt": "자외사 하만이",
  "corrected": "자회사 하만이",
  "reason": "음절 오류"
}
```

### Step 4: 결과 저장
`output/corrections.json` 파일로 저장:
```json
{
  "corrections": [
    {
      "scene_id": 5,
      "original_srt": "...",
      "corrected": "...",
      "reason": "..."
    }
  ],
  "total_corrections": 27,
  "corrected_scenes": [...]
}
```

## 교정 규칙
1. 원문에 있는 단어를 기준으로 수정
2. 의미가 같으면 굳이 수정 X
3. **원문에 없는 내용을 추가하지 않음**
4. 띄어쓰기, 음절, 영어, 숫자 오류 모두 수정

## 시작
작업을 수행하고 결과를 저장하세요.
