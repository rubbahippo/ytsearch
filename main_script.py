import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta, timezone
import isodate
import pytz

# API 키 설정 (코랩에서는 userdata.get('YTDATA_API_KEY')를 사용할 수 있습니다)
# 직접 실행하는 경우 아래 줄의 주석을 해제하고 API 키를 입력하세요
# API_KEY = "YOUR_API_KEY_HERE"

# 코랩에서 실행하는 경우 아래 코드 사용
from google.colab import userdata
API_KEY = userdata.get('YTDATA_API_KEY')

# 검색 설정
HOURS_AGO = 24 * 7  # 최근 7일(7*24시간) 내 업로드된 영상
MAX_DURATION_SECONDS = 60  # 1분(60초) 미만 영상
SEARCH_QUERY = ""  # 검색어 (빈 문자열로 두면 모든 영상 검색)
REGION_CODE = "KR"  # 한국 지역 (다른 지역은 US, JP 등으로 변경)
MAX_RESULTS = 50  # 한 번에 가져올 결과 수
MAX_TOTAL_RESULTS = 200  # 총 결과 수 제한 (API 할당량 고려)
MIN_VIEW_COUNT = 1000  # 최소 조회수

# YouTube API 클라이언트 생성
def get_youtube_client(api_key):
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        return youtube
    except Exception as e:
        print(f"API 클라이언트 생성 중 오류: {e}")
        return None

# 특정 시간 전부터 현재까지의 시간 범위 생성
def get_time_range(hours_ago):
    now = datetime.now(timezone.utc)
    past_time = now - timedelta(hours=hours_ago)
    # RFC 3339 형식으로 변환 (YouTube API 요구 형식)
    return past_time.strftime('%Y-%m-%dT%H:%M:%SZ')

# UTC 시간을 한국 시간(KST)으로 변환
def convert_to_kst(utc_time_str):
    try:
        utc_time = datetime.strptime(utc_time_str, '%Y-%m-%dT%H:%M:%SZ')
        utc_time = utc_time.replace(tzinfo=timezone.utc)
        kst = pytz.timezone('Asia/Seoul')
        kst_time = utc_time.astimezone(kst)
        return kst_time.strftime('%Y-%m-%d %H:%M:%S KST')
    except Exception as e:
        print(f"시간 변환 오류: {e}")
        return utc_time_str

# 영상 길이(ISO 8601 형식)를 초 단위로 변환
def duration_to_seconds(duration_str):
    if not duration_str:
        return 0
    try:
        return isodate.parse_duration(duration_str).total_seconds()
    except Exception as e:
        print(f"영상 길이 변환 오류: {e}")
        return 0

# 최근 짧은 영상 검색
def search_recent_short_videos(youtube, hours_ago, max_duration, query, region, max_results, max_total, min_views):
    published_after = get_time_range(hours_ago)
    print(f"검색 시작: {hours_ago}시간 이내, {max_duration}초 이하 영상")
    print(f"검색 시작 시간: {published_after} (UTC)")
    
    # 검색 파라미터 설정
    search_params = {
        'part': 'snippet',
        'maxResults': max_results,
        'type': 'video',
        'videoDuration': 'short',  # 4분 미만 영상 (API 기본 필터)
        'order': 'date',  # 최신 영상 우선
        'publishedAfter': published_after,
        'regionCode': region
    }
    
    # 검색어가 있는 경우 추가
    if query:
        search_params['q'] = query
    
    videos_found = []
    next_page_token = None
    total_results = 0
    
    # 페이지 단위로 검색 결과 가져오기
    while total_results < max_total:
        if next_page_token:
            search_params['pageToken'] = next_page_token
            
        try:
            search_response = youtube.search().list(**search_params).execute()
            
            if not search_response.get('items'):
                print("더 이상 결과가 없습니다.")
                break
                
            # 검색된 비디오 ID 수집
            video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
            
            # 비디오 상세 정보 가져오기
            if video_ids:
                video_response = youtube.videos().list(
                    part='snippet,contentDetails,statistics',
                    id=','.join(video_ids)
                ).execute()
                
                # 1분 미만 영상만 필터링
                for item in video_response.get('items', []):
                    duration = item['contentDetails']['duration']
                    duration_seconds = duration_to_seconds(duration)
                    view_count = int(item['statistics'].get('viewCount', 0))
                    
                    # 1분 미만 + 최소 조회수 이상만 필터링
                    if duration_seconds <= max_duration and view_count >= min_views:
                        published_at = item['snippet']['publishedAt']
                        
                        video_info = {
                            'title': item['snippet']['title'],
                            'channelTitle': item['snippet']['channelTitle'],
                            'publishedAt': published_at,
                            'publishedAt_kst': convert_to_kst(published_at),
                            'viewCount': view_count,
                            'likeCount': int(item['statistics'].get('likeCount', 0)),
                            'duration': duration,
                            'duration_seconds': duration_seconds,
                            'videoId': item['id'],
                            'url': f"https://www.youtube.com/watch?v={item['id']}"
                        }
                        videos_found.append(video_info)
                        total_results += 1
                
                # 다음 페이지 토큰 가져오기
                next_page_token = search_response.get('nextPageToken')
                if not next_page_token:
                    print("다음 페이지가 없습니다.")
                    break
            
            print(f"현재까지 {len(videos_found)}개의 영상을 찾았습니다.")
            
        except HttpError as e:
            print(f"API 오류: {e}")
            break
        except Exception as e:
            print(f"오류 발생: {e}")
            break
    
    # 조회수 기준으로 정렬
    videos_found.sort(key=lambda x: x['viewCount'], reverse=True)
    return videos_found

# 메인 실행 코드
if __name__ == "__main__":
    youtube = get_youtube_client(API_KEY)
    if not youtube:
        print("YouTube API 클라이언트를 생성할 수 없습니다.")
    else:
        # 최근 짧은 영상 검색
        short_videos = search_recent_short_videos(
            youtube, 
            HOURS_AGO, 
            MAX_DURATION_SECONDS, 
            SEARCH_QUERY, 
            REGION_CODE, 
            MAX_RESULTS, 
            MAX_TOTAL_RESULTS, 
            MIN_VIEW_COUNT
        )
        
        # 결과 출력
        print("\n=== 검색 결과 ===")
        print(f"총 {len(short_videos)}개의 영상을 찾았습니다.")
        
        for i, video in enumerate(short_videos):
            print(f"\n--- 영상 {i+1} ---")
            print(f"제목: {video['title']}")
            print(f"채널: {video['channelTitle']}")
            print(f"게시일: {video['publishedAt_kst']}")
            print(f"조회수: {video['viewCount']:,}")
            print(f"좋아요: {video['likeCount']:,}")
            print(f"영상 길이: {video['duration_seconds']:.1f}초")
            print(f"URL: {video['url']}")
        
        # 통계 정보
        if short_videos:
            avg_views = sum(v['viewCount'] for v in short_videos) / len(short_videos)
            avg_likes = sum(v['likeCount'] for v in short_videos) / len(short_videos)
            avg_duration = sum(v['duration_seconds'] for v in short_videos) / len(short_videos)
            
            print("\n=== 통계 정보 ===")
            print(f"평균 조회수: {avg_views:,.1f}")
            print(f"평균 좋아요: {avg_likes:,.1f}")
            print(f"평균 영상 길이: {avg_duration:.1f}초")
            
            # 시간대별 분포
            hour_distribution = {}
            for video in short_videos:
                utc_time = datetime.strptime(video['publishedAt'], '%Y-%m-%dT%H:%M:%SZ')
                utc_time = utc_time.replace(tzinfo=timezone.utc)
                kst = pytz.timezone('Asia/Seoul')
                kst_time = utc_time.astimezone(kst)
                hour = kst_time.hour
                
                if hour not in hour_distribution:
                    hour_distribution[hour] = 0
                hour_distribution[hour] += 1
            
            print("\n=== 시간대별 업로드 분포 (KST) ===")
            for hour in sorted(hour_distribution.keys()):
                count = hour_distribution[hour]
                percentage = (count / len(short_videos)) * 100
                bar = "■" * int(percentage / 5)
                print(f"{hour:02}시: {count}개 ({percentage:.1f}%) {bar}")
