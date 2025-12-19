"""
엑셀 추출 유틸리티

영상 리서치 결과를 Excel/CSV로 내보내기
"""
import pandas as pd
from typing import List, Union
from io import BytesIO
from datetime import datetime


def export_videos_to_excel(
    videos: List[dict],
    filename_prefix: str = "영상_리서치"
) -> BytesIO:
    """
    영상 목록을 엑셀 파일로 변환

    Args:
        videos: VideoInfo.to_excel_row() 형식의 딕셔너리 리스트
        filename_prefix: 파일명 접두어

    Returns:
        BytesIO: 엑셀 파일 바이트 스트림
    """
    if not videos:
        # 빈 파일 반환
        output = BytesIO()
        df = pd.DataFrame()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='영상 목록', index=False)
        output.seek(0)
        return output

    # DataFrame 생성
    df = pd.DataFrame(videos)

    # 컬럼 순서 정렬
    column_order = [
        "영상 제목",
        "영상 URL",
        "영상 유형",
        "영상 길이",
        "업로드일",
        "조회수",
        "좋아요",
        "댓글수",
        "채널명",
        "채널 URL",
        "구독자수",
        "채널 개설일",
        "채널 총 영상수",
        "구독자 대비 조회수",
        "참여율(%)",
        "업로드 후 일수",
        "일일 평균 조회수",
        "급등 점수",
    ]

    # 존재하는 컬럼만 선택
    available_columns = [col for col in column_order if col in df.columns]
    # 나머지 컬럼도 추가
    remaining = [col for col in df.columns if col not in available_columns]
    df = df[available_columns + remaining]

    # 엑셀 파일 생성
    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='영상 목록', index=False)

        # 워크시트 스타일링
        worksheet = writer.sheets['영상 목록']

        # 열 너비 자동 조정
        for idx, col in enumerate(df.columns, 1):
            max_length = max(
                df[col].astype(str).apply(len).max(),
                len(str(col))
            )
            # openpyxl은 1-indexed, 열 문자로 변환
            col_letter = get_column_letter(idx)
            worksheet.column_dimensions[col_letter].width = min(max_length + 2, 50)

    output.seek(0)
    return output


def get_column_letter(idx: int) -> str:
    """열 인덱스를 엑셀 열 문자로 변환 (1=A, 27=AA)"""
    result = ""
    while idx > 0:
        idx, remainder = divmod(idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def export_to_csv(videos: List[dict]) -> str:
    """CSV 형식으로 변환"""
    if not videos:
        return ""

    df = pd.DataFrame(videos)
    return df.to_csv(index=False, encoding='utf-8-sig')


def export_videos_simple(
    videos: List[dict],
    include_columns: List[str] = None
) -> BytesIO:
    """
    간단한 형식으로 엑셀 내보내기

    Args:
        videos: 영상 데이터 리스트
        include_columns: 포함할 컬럼 목록 (None이면 전체)

    Returns:
        BytesIO: 엑셀 파일 바이트 스트림
    """
    df = pd.DataFrame(videos)

    if include_columns:
        available = [c for c in include_columns if c in df.columns]
        df = df[available]

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='영상 목록', index=False)
    output.seek(0)

    return output


def create_summary_sheet(videos: List[dict]) -> pd.DataFrame:
    """요약 통계 시트 생성"""
    if not videos:
        return pd.DataFrame()

    df = pd.DataFrame(videos)

    summary = {
        "항목": [],
        "값": []
    }

    # 전체 통계
    summary["항목"].append("총 영상 수")
    summary["값"].append(len(videos))

    if "조회수" in df.columns:
        summary["항목"].append("총 조회수")
        summary["값"].append(f"{df['조회수'].sum():,}")
        summary["항목"].append("평균 조회수")
        summary["값"].append(f"{df['조회수'].mean():,.0f}")
        summary["항목"].append("최대 조회수")
        summary["값"].append(f"{df['조회수'].max():,}")

    if "구독자수" in df.columns:
        summary["항목"].append("평균 구독자")
        summary["값"].append(f"{df['구독자수'].mean():,.0f}")

    if "영상 유형" in df.columns:
        shorts_count = len(df[df["영상 유형"] == "쇼츠"])
        longform_count = len(df[df["영상 유형"] == "롱폼"])
        summary["항목"].append("롱폼 영상 수")
        summary["값"].append(longform_count)
        summary["항목"].append("쇼츠 영상 수")
        summary["값"].append(shorts_count)

    return pd.DataFrame(summary)


def export_with_summary(
    videos: List[dict],
    filename_prefix: str = "영상_리서치"
) -> BytesIO:
    """
    요약 시트를 포함한 엑셀 파일 생성

    Args:
        videos: 영상 데이터 리스트
        filename_prefix: 파일명 접두어

    Returns:
        BytesIO: 엑셀 파일 바이트 스트림
    """
    if not videos:
        output = BytesIO()
        df = pd.DataFrame()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='영상 목록', index=False)
        output.seek(0)
        return output

    df = pd.DataFrame(videos)
    summary_df = create_summary_sheet(videos)

    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # 요약 시트
        summary_df.to_excel(writer, sheet_name='요약', index=False)

        # 영상 목록 시트
        df.to_excel(writer, sheet_name='영상 목록', index=False)

        # 열 너비 조정
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for idx, col in enumerate(worksheet.iter_cols(min_row=1, max_row=1), 1):
                col_letter = get_column_letter(idx)
                worksheet.column_dimensions[col_letter].width = 15

    output.seek(0)
    return output
