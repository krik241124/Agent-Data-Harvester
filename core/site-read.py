# bench_read.py
import os
import sqlite3
import gzip
import datetime
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urlunparse
import re
import json
import glob
# 替换 requests 为内置的 urllib，实现 0 依赖！
import urllib.request
import urllib.error
# 引入多线程并发，解决 Timeout 问题！
import concurrent.futures

# 获取当前脚本所在目录 (core/)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录 (向上推一级)
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
# 动态拼接配置与输出路径
DB_FILE = os.path.join(PROJECT_ROOT, "sitemap_monitor.db")
TARGETS_FILE = os.path.join(PROJECT_ROOT, "config", "targets.txt")

REQUEST_TIMEOUT = 15 # 每个请求的超时缩短，防止个别死链拖慢全局
USER_AGENT = "Mozilla/5.0 (compatible; bench-read-agent/1.0; +https://openclaw.ai/)"
MAX_JSON_ITEMS = 50 
MAX_WORKERS = 20 # 开启 20 个并发线程，把 5 分钟压缩到 10 秒！

def get_current_time_str():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS sites (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE)")
    cur.execute("CREATE TABLE IF NOT EXISTS pages (site_id INTEGER, page_url TEXT, first_seen TEXT, last_seen TEXT, PRIMARY KEY (site_id, page_url))")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(page_url)")
    conn.commit()
    return conn

def normalize_to_sitemap(raw_url):
    u = raw_url.strip()
    if not u.startswith('http'): u = 'https://' + u
    parsed = urlparse(u)
    if parsed.path.endswith('.xml'): return u
    return urlunparse((parsed.scheme, parsed.netloc, '/sitemap.xml', '', '', ''))

def sync_targets(conn):
    if not os.path.exists(TARGETS_FILE): return
    with open(TARGETS_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    cur = conn.cursor()
    for line in lines:
        if not line.strip(): continue
        try: cur.execute("INSERT INTO sites (url) VALUES (?)", (normalize_to_sitemap(line),))
        except sqlite3.IntegrityError: pass 
    conn.commit()

# --- 使用标准库 urllib 替代 requests ---
def fetch_url_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            return response.read()
    except Exception:
        return None 

def parse_sitemap_bytes(content):
    try: root = ET.fromstring(content)
    except Exception:
        try: root = ET.fromstring(content.decode('utf-8', errors='ignore'))
        except Exception: return [], False
    locs = []
    for elem in root.iter():
        if elem.tag.lower().endswith('loc') and elem.text:
            locs.append(elem.text.strip())
    return locs, root.tag.lower().endswith('sitemapindex')

def fetch_sitemap(url, depth=0, visited=None):
    if visited is None: visited = set()
    if depth > 3 or url in visited: return []
    visited.add(url)
    content = fetch_url_bytes(url)
    if not content: return []
    if url.endswith('.gz'):
        try: content = gzip.decompress(content)
        except Exception: pass
    locs, is_index = parse_sitemap_bytes(content)
    if is_index:
        urls = []
        for s in locs: urls += fetch_sitemap(s, depth + 1, visited)
        return urls
    return locs

def normalize_url(u):
    try:
        p = urlparse(u)
        path = p.path or '/'
        while '//' in path: path = path.replace('//', '/')
        if path != '/' and path.endswith('/'): path = path[:-1]
        return urlunparse((p.scheme, p.netloc, path, '', '', ''))
    except Exception: return u

def extract_keywords_from_url(u):
    try:
        p = urlparse(u)
        path = p.path
        if path != '/' and path.endswith('/'): path = path[:-1]
        if not path or path == '/': return []
        slug = path.split('/')[-1]
        slug_without_ext = re.sub(r'\.(html|htm|php|aspx|asp)$', '', slug, flags=re.IGNORECASE)
        if not slug_without_ext: return []
        keyword_phrase = re.sub(r'[-_]+', ' ', slug_without_ext)
        keyword_phrase = re.sub(r'\s+', ' ', keyword_phrase).strip()
        if len(keyword_phrase) > 2 and not keyword_phrase.isdigit():
            return [keyword_phrase.lower()]
        return []
    except Exception: return []

# --- 新增：为多线程剥离出的独立抓取函数 ---
def process_single_site(site_data):
    site_id, site_url = site_data
    urls = fetch_sitemap(site_url)
    current_urls = {normalize_url(u) for u in urls if u}
    return site_id, site_url, current_urls

def generate_reports(conn, new_pages_today, removed_pages_today, current_time_str):
    cur = conn.cursor()
    added_kw_map, removed_kw_map, global_kw_map = {}, {}, {}
    
    for page, sources in new_pages_today.items():
        for kw in extract_keywords_from_url(page):
            added_kw_map[kw] = added_kw_map.get(kw, 0) + len(sources)
            
    for page, sources in removed_pages_today.items():
        for kw in extract_keywords_from_url(page):
            removed_kw_map[kw] = removed_kw_map.get(kw, 0) + len(sources)
            
    cur.execute("SELECT page_url, site_id FROM pages")
    for page_url, site_id in cur.fetchall():
        for kw in extract_keywords_from_url(page_url):
            global_kw_map.setdefault(kw, set()).add(site_id)
            
    global_kw_counts = {kw: len(sites) for kw, sites in global_kw_map.items()}

    sorted_added = sorted(added_kw_map.items(), key=lambda x: x[1], reverse=True)
    sorted_removed = sorted(removed_kw_map.items(), key=lambda x: x[1], reverse=True)
    sorted_global = sorted(global_kw_counts.items(), key=lambda x: x[1], reverse=True)

    txt_pattern = os.path.join(PROJECT_ROOT, "????-??-??.txt")
    existing_txts = sorted(glob.glob(txt_pattern))
    last_scan_time = "First Scan"
    if existing_txts:
        mtime = os.path.getmtime(existing_txts[-1])
        last_scan_time = datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    txt_filename = os.path.join(PROJECT_ROOT, f"{date_str}.txt")
    
    with open(txt_filename, 'w', encoding='utf-8') as f:
        f.write(f"=== Bench Read Report: {current_time_str} ===\n\n")
        f.write(f"--- 1. 新增内页 (总计 {len(new_pages_today)}) ---\n")
        for page, sources in new_pages_today.items(): f.write(f" + {page} (From {len(sources)} sites)\n")
        f.write(f"\n--- 2. 下架内页 (总计 {len(removed_pages_today)}) ---\n")
        for page, sources in removed_pages_today.items(): f.write(f" - {page} (From {len(sources)} sites)\n")
        f.write("\n--- 3. 关键词风向标 (Top 新增) ---\n")
        for kw, cnt in sorted_added: f.write(f" {kw}: {cnt}\n")
        f.write("\n--- 4. 关键词避坑指南 (Top 移除) ---\n")
        for kw, cnt in sorted_removed: f.write(f" {kw}: {cnt}\n")
        f.write("\n--- 5. 关键词概览 (Top 全量) ---\n")
        for kw, cnt in sorted_global: f.write(f" {kw}: {cnt}\n")

    current_txts = sorted(glob.glob(txt_pattern))
    while len(current_txts) > 10:
        oldest_file = current_txts.pop(0)
        try: os.remove(oldest_file)
        except OSError: pass

    cur.execute("SELECT COUNT(*) FROM sites")
    sites_count = cur.fetchone()[0] or 0

    added_json_dict = {k: str(v) for k, v in sorted_added[:MAX_JSON_ITEMS]}
    removed_json_dict = {k: str(v) for k, v in sorted_removed[:MAX_JSON_ITEMS]}
    global_json_dict = {k: str(v) for k, v in sorted_global[:MAX_JSON_ITEMS]}

    output_json = {
        "event_type": "bench_read_complete",
        "last_scan": last_scan_time,
        "timestamp": current_time_str,
        "data": {
            "summary": {
                "sites_count": sites_count,
                "added_keywords_count": len(added_kw_map),
                "removed_keywords_count": len(removed_kw_map)
            },
            "added_keywords": [added_json_dict] if added_json_dict else [],
            "removed_keywords": [removed_json_dict] if removed_json_dict else [],
            "keywords_status": [global_json_dict] if global_json_dict else []
        }
    }
    
    print(json.dumps(output_json, ensure_ascii=False, indent=4))

def run_monitor():
    conn = init_db()
    sync_targets(conn)
    current_time_str = get_current_time_str()
    cur = conn.cursor()
    cur.execute("SELECT id, url FROM sites")
    sites = cur.fetchall()

    new_pages_today = {}
    removed_pages_today = {}

    # --- 多线程兵分 20 路狂飙 ---
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(process_single_site, sites))

    # 收拢多线程结果，统一操作 SQLite 避免锁冲突
    for site_id, site_url, current_urls in results:
        cur.execute("SELECT page_url FROM pages WHERE site_id=?", (site_id,))
        history_urls = {row[0] for row in cur.fetchall()}
        
        added = current_urls - history_urls
        removed = history_urls - current_urls
        
        if added:
            insert_list = [(site_id, u, current_time_str, current_time_str) for u in added]
            for u in added: new_pages_today.setdefault(u, []).append(site_url)
            cur.executemany("INSERT OR REPLACE INTO pages (site_id, page_url, first_seen, last_seen) VALUES (?, ?, ?, ?)", insert_list)

        if removed:
            delete_list = [(site_id, u) for u in removed]
            for u in removed: removed_pages_today.setdefault(u, []).append(site_url)
            cur.executemany("DELETE FROM pages WHERE site_id=? AND page_url=?", delete_list)

    conn.commit()
    generate_reports(conn, new_pages_today, removed_pages_today, current_time_str)

if __name__ == "__main__":
    run_monitor()
