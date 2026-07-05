# Agent Data Harvester

## Introduction
本项目是一个为 Multi-Agent 系统设计的外部数据感知与预处理模块。核心目标是从非结构化的 Web 节点（Sitemap）和第三方 API（YouTube）中提取、清洗数据，并转化为标准化 JSON 格式，作为大语言模型（LLM）的外挂知识库或 Function Calling 的入参。

## Architecture & Directory Structure
项目将逻辑代码与配置文件进行了解耦，目录结构如下：

```text
Agent-Data-Harvester/
├── README.md
├── requirements.txt
├── core/
│   ├── site-read.py          # 网站 Sitemap 监控与解析脚本
│   └── youtube-read.py       # YouTube 频道 API 数据抓取脚本
└── config/
    ├── targets.txt           # 待监控的 Sitemap URL 列表
    └── bench.txt             # 待监控的 YouTube 频道/社媒列表
```

## Key Engineering Features

**1. Sitemap Monitor (`core/site-read.py`)**
*   **0第三方依赖：** 弃用 `requests`，采用 Python 标准库 `urllib`，降低系统部署复杂度和环境依赖。
*   **并发控制：** 使用 `concurrent.futures.ThreadPoolExecutor` 实现多线程 I/O 并发，优化因个别死链导致的全局 Timeout 阻塞问题。
*   **状态机与增量持久化：** 引入 SQLite 数据库。采用 `(site_id, page_url)` 联合主键与 `UPSERT` 逻辑，记录页面生命周期（first_seen / last_seen），精准计算每日新增与下架的增量数据。
*   **文本清洗策略：** 内置正则清洗函数，过滤 URL 路径中的技术后缀（如 `.html`, `.php`），将连接符转化为空格，输出纯净的自然语言 Keyword 供 LLM 分析。

**2. YouTube Data Fetcher (`core/youtube-read.py`)**
*   **标准化 API 集成：** 基于 `google-api-python-client`，通过频道 `uploads` 列表进行数据获取。
*   **时间窗过滤：** 采用 RFC 3339 标准时间戳过滤近 7 天内的视频更新。
*   **数据结构化：** 对接 API 获取 `viewCount` 等统计数据，对冗长 Description 进行截断处理，最终输出 LLM 友好的 JSON 结构。

## Usage

**环境准备**
```bash
git clone https://github.com/krik241124/Agent-Data-Harvester.git
cd Agent-Data-Harvester
pip install -r requirements.txt  # 仅针对 YouTube API 依赖
```

**运行模块**
```bash
# 1. 运行 Sitemap 监控 (执行后会在根目录生成 .db 与 .txt 分析报告)
python core/site-read.py

# 2. 运行 YouTube 监控 (需提前在源码中配置 Google API Key)
python core/youtube-read.py
```

## Technical Constraints & Error Handling
*   **API 边界：** 为防止上下文超载（Fat Payload），长文本字段在解析阶段被强制截断。
*   **容错机制：** 针对 Sitemap XML 格式不规范及 GZIP 压缩乱码问题，内置了 `ET.fromstring` 的多重异常捕获与转码处理逻辑，确保主线程不崩溃。

***
