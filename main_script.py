import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta, timezone
import isodate
import pytz
import pandas as pd
import time

st.set_page_config(page_title="YouTube Shorts Finder", page_icon="🎬", layout="wide")

st.title("YouTube Shorts Finder")
st.markdown("👇 YouTube에서 짧은 영상(Shorts)를 찾고 분석하는 도구입니다.")

# 사이드바 설정
with st.sidebar:
    st.header("설정")
    
    # API 키 설정 (Streamlit Cloud에서는 st.secrets 사용, 로컬에서는 입력)
    try:
        API_KEY = st.secrets["YOUTUBE_API_KEY"]
        st.success("API 키가 시크릿에서 로드되었습니다.")
    except:
        API_KEY = st.text_input("YouTube API 키를 입력하세요", type="password")
        if not API_KEY:
            st.warning("API 키를 입력해주세요. YouTube Data API v3 키가 필요합니다.")
    
    # 검색 설정
    st.subheader("검색 설정")
    HOURS_AGO = st.slider("검색 기간 (시간)", min_value=1, max_value=24*30, value=24*7, step=1, 
                           help="몇 시간 이내에 업로드된 영상을 검색할지 설정합니다. 최대 30일(720시간)까지 가능합니다.")
    
    MAX_DURATION_SECONDS = st.slider("최대 영상 길이 (초)", min_value=10, max_value=180, value=60, step=5,
                                     help="이 길이 이하의 영상만 결과에 포함됩니다. Shorts는 보통 60초 이하입니다.")
    
    MIN_VIEW_COUNT = st.number_input("최소 조회수", min_value=0, max_value=1000000, value=1000, step=1000,
                                     help="이 조회수 이상의 영상만 결과에 포함됩니다.")
    
    REGION_CODE = st.selectbox("국가/지역", options=["KR", "US", "JP", "GB", "CA", "AU", "FR", "DE", "IN", "BR", "RU"], 
                              index=0, help="특정 국가/지역의 인기 영상을 검색합니다.")
    
    MAX_RESULTS = st.slider("검색 결과 수", min_value=10, max_value=200, value=50, step=10,
                            help="가져올 검색 결과의 최대 개수입니다. 값이 클수록 시간이 오래 걸릴 수 있습니다.")
    
    # 카테고리 설정
    st.subheader("카테고리 (선택사항)")
    CATEGORY_ENABLED = st.checkbox("특정 카테고리만 검색", value=False, 
                                  help="체크하면 특정 카테고리의 영상만 검색합니다.")
    
    # 주요 카테고리 ID (국가마다 다를 수 있음)
    CATEGORIES = {
        "영화 & 애니메이션": "1", 
        "자동차 & 차량": "2", 
        "음악": "10", 
        "애완동물 & 동물": "15", 
        "스포츠": "17", 
        "여행 & 이벤트": "19", 
        "게임": "20", 
        "블로그": "22", 
        "코미디": "23", 
        "엔터테인먼트": "24", 
        "뉴스 & 정치": "25", 
        "하우투 & 스타일": "26", 
        "교육": "27", 
        "과학 & 기술": "28"
    }
    
    if CATEGORY_ENABLED:
        CATEGORY_ID = st.selectbox("카테고리", options=list(CATEGORIES.keys()), index=6)
        CATEGORY_ID = CATEGORIES[CATEGORY_ID]  # ID로 변환
    else:
        CATEGORY_ID = None
    
    # 부가 설정
    st.subheader("부가 설정")
    SEARCH_METHOD = st.radio("검색 방식", options=["최신순", "인기순"], index=0,
                           help="'최신순'은 최근 업로드 순으로, '인기순'은 조회수 순으로 검색합니다.")
    
    INCLUDE_DETAILS = st.checkbox("상세 정보 포함", value=True,
                                help="영상의 설명, 태그 등 추가 정보를 가져옵니다.")

# 유틸리티 함수
def get_youtube_client(api_key):
    """YouTube API 클라이언트 생성"""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        return youtube
    except Exception as e:
        st.error(f"API 클라이언트 생성 중 오류: {str(e)}")
        return None

def get_time_range(hours_ago):
    """특정 시간 전부터 현재까지의 시간 범위 생성"""
    now = datetime.now(timezone.utc)
    past_time = now - timedelta(hours=hours_ago)
    return past_time.strftime('%Y-%m-%dT%H:%M:%SZ')

def convert_to_kst(utc_time_str):
    """UTC 시간을 한국 시간(KST)으로 변환"""
    try:
        utc_time = datetime.strptime(utc_time_str, '%Y-%m-%dT%H:%M:%SZ')
        utc_time = utc_time.replace(tzinfo=timezone.utc)
        kst = pytz.timezone('Asia/Seoul')
        kst_time = utc_time.astimezone(kst)
        return kst_time.strftime('%Y-%m-%d %H:%M:%S KST')
    except Exception as e:
        return utc_time_str

def duration_to_seconds(duration_str):
    """영상 길이(ISO 8601 형식)를 초 단위로 변환"""
    if not duration_str:
        return 0
    try:
        return isodate.parse_duration(duration_str).total_seconds()
    except Exception as e:
        return 0

def format_number(number):
    """숫자를 천 단위 구분자로 포맷팅"""
    return f"{number:,}"

def search_recent_short_videos(youtube, hours_ago, max_duration, min_views, region, max_results, category_id=None, search_method="최신순", include_details=True):
    """최근 짧은 영상 검색"""
    if not youtube:
        return []
    
    published_after = get_time_range(hours_ago)
    
    # 진행 상태 표시
    progress_text = st.empty()
    progress_bar = st.progress(0)
    progress_text.text("검색 준비 중...")
    
    # 검색 파라미터 설정
    if search_method == "최신순":
        # search API 사용 (최신 영상 검색)
        search_params = {
            'part': 'snippet',
            'maxResults': min(max_results, 50),  # API 한도
            'type': 'video',
            'videoDuration': 'short',  # 4분 미만 영상 (API 기본 필터)
            'order': 'date',  # 최신 영상 우선
            'publishedAfter': published_after,
            'regionCode': region
        }
        
        if category_id:
            search_params['videoCategoryId'] = category_id
        
        progress_text.text(f"최근 {hours_ago}시간 이내 업로드된 영상 검색 중...")
        progress_bar.progress(10)
        
        try:
            # 검색 실행
            search_response = youtube.search().list(**search_params).execute()
            
            if not search_response.get('items'):
                progress_text.text("검색 결과가 없습니다.")
                progress_bar.progress(100)
                return []
            
            # 비디오 ID 수집
            video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
            
        except HttpError as e:
            progress_text.text(f"API 오류: {str(e)}")
            progress_bar.progress(100)
            return []
            
    else:  # 인기순
        # videos.list API에서 인기 영상 직접 가져오기
        videos_params = {
            'part': 'snippet,contentDetails,statistics',
            'chart': 'mostPopular',
            'regionCode': region,
            'maxResults': min(max_results, 50)  # API 한도
        }
        
        if category_id:
            videos_params['videoCategoryId'] = category_id
        
        progress_text.text(f"인기 영상 검색 중...")
        progress_bar.progress(10)
        
        try:
            popular_response = youtube.videos().list(**videos_params).execute()
            
            if not popular_response.get('items'):
                progress_text.text("검색 결과가 없습니다.")
                progress_bar.progress(100)
                return []
                
            # 가져온 영상을 60초 이하 & 설정된 시간 이내 필터링
            video_ids = []
            for item in popular_response.get('items', []):
                duration = item['contentDetails']['duration']
                duration_seconds = duration_to_seconds(duration)
                published_at = item['snippet']['publishedAt']
                
                # 영상 길이가 max_duration 이하이고, 설정된 시간 이내에 업로드된 경우만 포함
                if duration_seconds <= max_duration and published_at >= published_after:
                    video_ids.append(item['id'])
        
        except HttpError as e:
            progress_text.text(f"API 오류: {str(e)}")
            progress_bar.progress(100)
            return []
    
    # 비디오 상세 정보 가져오기
    progress_text.text("영상 상세 정보 가져오는 중...")
    progress_bar.progress(30)
    
    # 비디오 상세 정보 요청에 포함할 부분 설정
    video_parts = ['snippet', 'contentDetails', 'statistics']
    if include_details:
        video_parts.extend(['topicDetails', 'recordingDetails'])
    
    videos_found = []
    
    try:
        if video_ids:
            video_response = youtube.videos().list(
                part=','.join(video_parts),
                id=','.join(video_ids)
            ).execute()
            
            progress_text.text("데이터 처리 중...")
            progress_bar.progress(60)
            
            # 처리 및 필터링
            for item in video_response.get('items', []):
                duration = item['contentDetails']['duration']
                duration_seconds = duration_to_seconds(duration)
                view_count = int(item['statistics'].get('viewCount', 0))
                
                # 길이 및 조회수 기준 필터링
                if duration_seconds <= max_duration and view_count >= min_views:
                    published_at = item['snippet']['publishedAt']
                    
                    # 기본 정보 수집
                    video_info = {
                        '제목': item['snippet']['title'],
                        '채널명': item['snippet']['channelTitle'],
                        '게시일': published_at,
                        '게시일(KST)': convert_to_kst(published_at),
                        '조회수': view_count,
                        '좋아요': int(item['statistics'].get('likeCount', 0)),
                        '댓글수': int(item['statistics'].get('commentCount', 0)),
                        '영상 길이(초)': round(duration_seconds, 1),
                        '영상 ID': item['id'],
                        'URL': f"https://www.youtube.com/watch?v={item['id']}"
                    }
                    
                    # 상세 정보 추가 (선택적)
                    if include_details:
                        video_info['설명'] = item['snippet'].get('description', '')
                        video_info['태그'] = ', '.join(item['snippet'].get('tags', []))
                        video_info['기본 언어'] = item['snippet'].get('defaultLanguage', '')
                        video_info['카테고리 ID'] = item['snippet'].get('categoryId', '')
                        
                        if 'topicDetails' in item:
                            video_info['토픽 카테고리'] = ', '.join(item['topicDetails'].get('topicCategories', []))
                    
                    videos_found.append(video_info)
            
            # 조회수 기준 정렬
            videos_found.sort(key=lambda x: x['조회수'], reverse=True)
            
    except HttpError as e:
        progress_text.text(f"API 오류: {str(e)}")
    except Exception as e:
        progress_text.text(f"처리 중 오류 발생: {str(e)}")
    
    progress_text.text(f"검색 완료! {len(videos_found)}개의 영상을 찾았습니다.")
    progress_bar.progress(100)
    
    return videos_found


# 실행 버튼
if st.button("검색 시작", type="primary"):
    if not API_KEY:
        st.error("YouTube API 키를 입력해주세요.")
    else:
        # YouTube API 클라이언트 생성
        youtube = get_youtube_client(API_KEY)
        
        if youtube:
            with st.spinner("검색 중입니다..."):
                # 검색 실행
                start_time = time.time()
                
                videos = search_recent_short_videos(
                    youtube=youtube,
                    hours_ago=HOURS_AGO,
                    max_duration=MAX_DURATION_SECONDS,
                    min_views=MIN_VIEW_COUNT,
                    region=REGION_CODE,
                    max_results=MAX_RESULTS,
                    category_id=CATEGORY_ID,
                    search_method=SEARCH_METHOD,
                    include_details=INCLUDE_DETAILS
                )
                
                search_time = time.time() - start_time
                
                # 결과 표시
                if videos:
                    st.success(f"{len(videos)}개의 영상을 찾았습니다! (검색 시간: {search_time:.2f}초)")
                    
                    # 데이터프레임으로 변환
                    df = pd.DataFrame(videos)
                    
                    # 통계 정보
                    st.header("통계 정보")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("총 영상 수", f"{len(videos)}개")
                    with col2:
                        st.metric("평균 조회수", f"{int(df['조회수'].mean()):,}")
                    with col3:
                        st.metric("평균 좋아요", f"{int(df['좋아요'].mean()):,}")
                    with col4:
                        st.metric("평균 영상 길이", f"{df['영상 길이(초)'].mean():.1f}초")
                    
                    # 영상 목록
                    st.header("영상 목록")
                    
                    # 표시할 컬럼
                    display_columns = ['제목', '채널명', '게시일(KST)', '조회수', '좋아요', '영상 길이(초)', 'URL']
                    
                    # 조회수, 좋아요수 포맷팅
                    df_display = df.copy()
                    df_display['조회수'] = df_display['조회수'].apply(format_number)
                    df_display['좋아요'] = df_display['좋아요'].apply(format_number)
                    
                    # 테이블로 표시
                    st.dataframe(df_display[display_columns], use_container_width=True, 
                                height=400, column_config={
                                    'URL': st.column_config.LinkColumn(),
                                    '제목': st.column_config.Column(width="large")
                                })
                    
                    # CSV 다운로드 버튼
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="CSV로 다운로드",
                        data=csv,
                        file_name=f"youtube_shorts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                    
                    # 시각화
                    st.header("시각화")
                    chart_tab1, chart_tab2, chart_tab3 = st.tabs(["조회수 분포", "길이 분포", "시간대별 업로드"])
                    
                    with chart_tab1:
                        # 조회수 구간별 분류
                        view_bins = [0, 10000, 50000, 100000, 500000, 1000000, float('inf')]
                        view_labels = ['1만 미만', '1만-5만', '5만-10만', '10만-50만', '50만-100만', '100만 이상']
                        df['조회수 구간'] = pd.cut(df['조회수'], bins=view_bins, labels=view_labels)
                        view_counts = df['조회수 구간'].value_counts().sort_index()
                        
                        st.bar_chart(view_counts)
                    
                    with chart_tab2:
                        # 영상 길이 분포
                        length_bins = [0, 15, 30, 45, 60, float('inf')]
                        length_labels = ['0-15초', '15-30초', '30-45초', '45-60초', '60초 이상']
                        df['길이 구간'] = pd.cut(df['영상 길이(초)'], bins=length_bins, labels=length_labels)
                        length_counts = df['길이 구간'].value_counts().sort_index()
                        
                        st.bar_chart(length_counts)
                    
                    with chart_tab3:
                        # 시간대별 업로드 분포
                        df['시간대'] = pd.to_datetime(df['게시일']).dt.hour
                        hour_counts = df['시간대'].value_counts().sort_index()
                        hour_df = pd.DataFrame({'시간': hour_counts.index, '영상 수': hour_counts.values})
                        
                        st.bar_chart(hour_df.set_index('시간'))

                    # 영상 미리보기 (선택적)
                    if st.checkbox("영상 미리보기 보기"):
                        st.header("영상 미리보기")
                        # 상위 3개 영상만 미리보기 표시
                        for i, video in enumerate(videos[:3]):
                            col1, col2 = st.columns([2, 3])
                            with col1:
                                st.video(video['URL'])
                            with col2:
                                st.subheader(video['제목'])
                                st.write(f"채널: {video['채널명']}")
                                st.write(f"조회수: {format_number(video['조회수'])}")
                                st.write(f"좋아요: {format_number(video['좋아요'])}")
                                st.write(f"길이: {video['영상 길이(초)']}초")
                                st.write(f"게시일: {video['게시일(KST)']}")
                            st.divider()
                
                else:
                    st.warning("검색 조건을 만족하는 영상을 찾지 못했습니다. 검색 조건을 변경해보세요.")

# 하단 정보
st.markdown("---")
st.markdown("Made with ❤️ using Streamlit and YouTube Data API")
st.markdown("이 앱은 YouTube Data API를 사용하며, API 할당량 제한이 있을 수 있습니다.")
