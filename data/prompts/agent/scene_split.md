# 씬 분할 에이전트

## 역할
Whisper로 추출된 문장들을 자연스러운 씬 단위로 병합합니다.

## 입력 데이터
- `input/sentences.json`: Whisper 추출 문장 리스트
- `input/config.json`: 분할 설정 (스타일, 최대 글자수 등)

## 작업 절차

### Step 1: 설정 확인
`input/config.json`에서 분할 스타일 확인:
- "잘게": 1-2문장/씬, 최대 50자, 최대 3초
- "기본": 2-4문장/씬, 최대 80자, 최대 5초
- "크게": 4-8문장/씬, 최대 150자, 최대 10초

### Step 2: 문장 분석
`input/sentences.json` 파일 읽기:
```json
[
  {"id": 0, "text": "여러분 삼성전자 하면은 뭐가 떠오르세요?", "start": 0.1, "end": 2.5},
  {"id": 1, "text": "스마트폰,", "start": 3.2, "end": 3.6},
  ...
]
```

### Step 3: 씬 병합
의미 단위로 문장들을 묶으세요:
- 문장 중간에서 끊지 않기
- sentence_ids는 연속된 번호
- 모든 문장이 정확히 하나의 씬에 포함

### Step 4: 결과 저장
`output/scenes.json` 파일로 저장:
```json
{
  "scenes": [
    {
      "scene_id": 1,
      "sentence_ids": [0, 1, 2, 3],
      "text": "여러분 삼성전자 하면은 뭐가 떠오르세요? 스마트폰, 반도체, TV",
      "start_time": 0.1,
      "end_time": 5.3
    }
  ],
  "total_scenes": 45,
  "style_used": "기본"
}
```

## 규칙
1. 의미 단위로 끊기 (문장 중간 X)
2. 설정된 최대 글자수/시간 준수
3. 모든 문장이 하나의 씬에 포함
4. sentence_ids는 연속

## 시작
작업을 수행하고 결과를 저장하세요.
