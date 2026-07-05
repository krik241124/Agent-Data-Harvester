import os
import json
import configparser
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build

# ================= 配置区域 =================
API_KEY = "YOUR_API_KEY_HERE"

# 动态定位项目根目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

BENCH_FILE = os.path.join(PROJECT_ROOT, "config", "bench.txt")
# 获取今天和7天前的时间边界 (RFC 3339 格式)
NOW = datetime.now(timezone.utc)
SEVEN_DAYS_AGO = (NOW - timedelta(days=7)).isoformat()
# ============================================

def get_channel_id_from_url(url):
    """
    (极简处理) 实际应用中：
    如果是 @handle，需调用 search 接口获取 Channel ID
    如果是 /channel/UCxxx，直接提取 UCxxx
    这里为了演示，假设直接传入了 channel ID 或者你需要用正则处理它
    """
    # 真实场景中，如果全是 @handle，可以用 youtube.search().list(part="snippet", q="@handle", type="channel")
    pass 

def main():
    # 1. 解析 bench.txt
    config = configparser.ConfigParser()
    config.read(BENCH_FILE, encoding='utf-8')
    
    youtube_channels = []
    if 'YouTube' in config:
        for name, url in config.items('YouTube'):
            youtube_channels.append({"name": name, "url": url})
            
    if not youtube_channels:
        print("bench.txt 里没有找到 YouTube 频道哦！")
        return

    # 2. 初始化 YouTube API 客户端
    youtube = build("youtube", "v3", developerKey=API_KEY)
    
    all_videos_data = []

    for item in youtube_channels:
        # 智能提取: 判断是直接给的 Channel ID 还是 @Handle
        raw_id_or_handle = item["url"].split("/")[-1]
        
        try:
            # Step A: 获取频道的 "uploads" 播放列表 ID
            if raw_id_or_handle.startswith("@"):
                # 如果是 @handle 格式
                channel_res = youtube.channels().list(
                    part="contentDetails",
                    forHandle=raw_id_or_handle # 官方新支持的参数！
                ).execute()
            else:
                # 假设是直接的 UC... 格式
                channel_res = youtube.channels().list(
                    part="contentDetails",
                    id=raw_id_or_handle
                ).execute()
            
            # 如果没找到这个频道，直接跳过
            if not channel_res.get("items"):
                print(f"没有找到频道：{item['name']}")
                continue
                
            uploads_playlist_id = channel_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            
            # Step B: 从 uploads 播放列表提取近 7 天视频
            playlist_res = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=50 # 假设频道7天内发视频不超过50个
            ).execute()
            
            video_ids = []
            for pl_item in playlist_res.get("items", []):
                pub_at = pl_item["snippet"]["publishedAt"]
                # 过滤近7天的视频
                if pub_at >= SEVEN_DAYS_AGO:
                    video_ids.append(pl_item["snippet"]["resourceId"]["videoId"])
            
            if not video_ids:
                continue
                
            # Step C: 批量获取视频详情与三维统计数据
            videos_res = youtube.videos().list(
                part="snippet,statistics",
                id=",".join(video_ids)
            ).execute()
            
            for v_item in videos_res.get("items", []):
                stats = v_item.get("statistics", {})
                all_videos_data.append({
                    "channel": item["name"],
                    "video_id": v_item["id"],
                    "title": v_item["snippet"]["title"],
                    "published_at": v_item["snippet"]["publishedAt"],
                    "description": v_item["snippet"]["description"][:200], # 取前200字截断，保持极简
                    "view_count": int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "url": f"https://www.youtube.com/watch?v={v_item['id']}"
                })
                
        except Exception as e:
            print(f"抓取频道 {item['name']} 时出错: {e}")

    # 3. 按播放量降序排序
    all_videos_data.sort(key=lambda x: x["view_count"], reverse=True)

    # 4. 导出 JSON
    date_str = NOW.strftime("%Y%m%d")
    output_filename = os.path.join(PROJECT_ROOT, f"youtube_social_read_{date_str}.json")
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(all_videos_data, f, ensure_ascii=False, indent=2)

    print(json.dumps(all_videos_data, ensure_ascii=False, indent=2))       
    print(f"成功抓取并生成了 {output_filename}，一共提取了 {len(all_videos_data)} 个爆款视频哦！♡")

if __name__ == "__main__":
    main()
