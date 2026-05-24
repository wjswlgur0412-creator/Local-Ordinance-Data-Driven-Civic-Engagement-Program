import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import platform
import re
import time

# 한글 폰트 설정 (운영체제별 대응)
if platform.system() == 'Windows':
    plt.rc('font', family='Malgun Gothic')
else:
    plt.rc('font', family='AppleGothic')
plt.rc('axes', unicode_minus=False)


def load_csv_file(uploaded_file):
    """CSV 파일을 인코딩 예외 처리를 고려하여 읽어오는 함수"""
    try:
        df = pd.read_csv(uploaded_file, encoding='utf-8')
        return df
    except Exception:
        uploaded_file.seek(0)
        try:
            df = pd.read_csv(uploaded_file, encoding='cp949')
            return df
        except Exception as e:
            st.error(f"파일을 읽는 중 오류가 발생했습니다: {e}")
            return None


def display_wordcloud(series):
    """소관위원회 데이터의 빈도수를 기반으로 워드클라우드를 생성하고 표시하는 함수"""
    counts = series.value_counts().to_dict()
    font_path = "C:/Windows/Fonts/malgun.ttf" if platform.system() == 'Windows' else "/Library/Fonts/Arial Unicode.ttf"
    try:
        wc = WordCloud(width=800, height=400, background_color='white', font_path=font_path).generate_from_frequencies(
            counts)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.imshow(wc, interpolation='bilinear')
        ax.axis('off')
        st.pyplot(fig)
    except Exception as e:
        st.error(f"워드클라우드 생성 중 오류가 발생했습니다: {e}")


def crawl_nyjc_bills(target_committee):
    """화면 멈춤(검은 화면) 현상을 방지하기 위해 최적화된 누수 없는 정밀 크롤링 함수"""
    list_url_template = "https://www.nyjc.go.kr/content/minutes/bill.html?gtid=&page={}&f_bill_daesu=9&f_bill_th=&f_bill_committee=&f_bill_code=&f_bill_proposer=&f_bill_title=&f_proposer_code=&title_code="
    detail_url_template = "https://www.nyjc.go.kr/content/minutes/bill.html?pg=vv&number={}&f_bill_daesu=9&f_bill_title=&f_bill_proposer=&f_proposer_code=&f_bill_committee=&title_code=&page={}"

    all_bills = []

    # UI 먹통을 방지하기 위해 전용 상태 게이지 렌더러 확보
    progress_bar = st.progress(0)
    status_text = st.empty()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    clean_target = re.sub(r'\s+', '', target_committee)

    # 1~95페이지 정밀 스캔
    for page in range(1, 96):
        status_text.text(f"데이터 추출 중: {page} / 95 페이지 분석 중...")
        progress_bar.progress(page / 95)

        url = list_url_template.format(page)
        try:
            # 타임아웃을 5초로 최적화하여 무한 대기 현상을 방지합니다.
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            table_rows = soup.select("table tbody tr")
            if not table_rows:
                table_rows = soup.find_all("tr")

            for row in table_rows:
                cols = row.find_all(['td', 'th'])

                if len(cols) >= 3:
                    bill_title = cols[1].get_text(strip=True)
                    committee = cols[2].get_text(strip=True)
                    proposer = cols[3].get_text(strip=True) if len(cols) > 3 else "확인불가"

                    if not bill_title or "의안명" in bill_title:
                        continue

                    clean_committee = re.sub(r'\s+', '', committee)

                    if clean_target in clean_committee or clean_committee in clean_target:
                        bill_number = ""
                        link_tag = cols[1].find('a')

                        if link_tag:
                            onclick_str = link_tag.get('onclick', '')
                            href_str = link_tag.get('href', '')
                            combined_str = onclick_str + " " + href_str

                            number_match = re.search(r"view\('(\d+)'", combined_str) or re.search(r"number=(\d+)",
                                                                                                  combined_str)
                            if number_match:
                                bill_number = number_match.group(1)

                        if bill_number:
                            real_detail_url = detail_url_template.format(bill_number, page)
                        else:
                            real_detail_url = url

                        all_bills.append({
                            "의안명": bill_title,
                            "상세링크": real_detail_url,
                            "소관위원회": committee,
                            "제안자/제안일": proposer
                        })

            # 메인 스레드가 브라우저와의 연결을 놓치지 않도록 아주 미세한 텀(0.02초)만 인입
            time.sleep(0.02)

        except Exception:
            continue

    progress_bar.empty()
    status_text.empty()
    return pd.DataFrame(all_bills)


# --- 스트림릿 메인 화면 구성 ---
st.title("남양주시 조례안 분석 및 크롤링 시스템")

# 1-1. CSV 파일 업로드
uploaded_file = st.file_uploader("남양주시 조례안 CSV 파일을 업로드하세요.", type=["csv"])

if uploaded_file is not None:
    df = load_csv_file(uploaded_file)

    if df is not None:
        # 1-2. 원본 파일 내용 확인 (접었다 펼 수 있는 형태)
        with st.expander("원본 파일 내용 확인"):
            st.dataframe(df)

        # 1-3. 필요한 열 선택 : M열(13번째 열) 자동 분석 지정
        if len(df.columns) >= 13:
            m_col_name = df.columns[12]
        else:
            st.warning("파일에 M열(13번째 열)이 존재하지 않아 첫 번째 열을 분석용으로 지정합니다.")
            m_col_name = df.columns[0]

        st.subheader("M열(소관위원회) 최종 데이터")

        final_df = df[[m_col_name]].copy()
        final_df.columns = ["소관위원회"]

        st.write(f"총 데이터 건수: {len(final_df)} 건")
        st.write(f"분석 컬럼 목록: {list(final_df.columns)}")
        st.dataframe(final_df)

        # 1-4. 분석된 M열의 데이터를 워드클라우드로 제시
        st.subheader("소관위원회 분석 워드클라우드")
        clean_series = final_df["소관위원회"].dropna().astype(str)
        display_wordcloud(clean_series)

        # 2-1. 워드클라우드로 제시한 항목을 아래 표형태로 제시한 후 크롤링시작 버튼 생성
        st.subheader("소관위원회별 실시간 크롤링")
        unique_committees = clean_series.unique()

        for committee in unique_committees:
            if committee.strip() == "":
                continue

            if f"clicked_{committee}" not in st.session_state:
                st.session_state[f"clicked_{committee}"] = False
            if f"data_{committee}" not in st.session_state:
                st.session_state[f"data_{committee}"] = None

            col1, col2 = st.columns([3, 1])
            with col1:
                st.text(f"소관위원회명: {committee}")
            with col2:
                if st.button("크롤링 시작", key=committee):
                    st.session_state[f"clicked_{committee}"] = True
                    st.session_state[f"data_{committee}"] = None

            # 독립 레이아웃 구조 실행부
            if st.session_state[f"clicked_{committee}"]:
                if st.session_state[f"data_{committee}"] is None:
                    with st.spinner(f"[{committee}] 의안 목록 1~95페이지 전수 조사 중... 잠시만 기다려주세요."):
                        st.session_state[f"data_{committee}"] = crawl_nyjc_bills(committee)

                result_df = st.session_state[f"data_{committee}"]

                if not result_df.empty:
                    st.subheader(f"[{committee}] 전수 수집 결과 - 총 {len(result_df)}건")

                    st.data_editor(
                        result_df,
                        column_config={
                            "상세링크": st.column_config.LinkColumn(
                                "세부 조례안 진짜 URL",
                                help="클릭하면 해당 세부 조례안의 다이렉트 본문 페이지가 열립니다.",
                                display_text="👉 [해당 세부 조례안 직접 이동]"
                            )
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    st.write("---")
                else:
                    st.info("검색된 조례안 데이터가 없거나 서버 응답이 지연되었습니다.")