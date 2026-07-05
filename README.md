🕸️ Agent-Data-Harvester (垂域 Agent 数据感知与清洗引擎)


📖 项目简介 (Introduction)
本项目是我在构建 Multi-Agent 系统（基于 OpenClaw）时，为其量身打造的高并发外部数据感知与清洗模块。
它作为一个独立的数据管道（Data Pipeline），负责从海量互联网非结构化数据中（如独立站 Sitemap、海外社媒 API），爬取、清洗并提取出结构化的 JSON 数据，最终作为外挂知识库（RAG）或工具调用（Tools）喂给大模型 Agent。

✨ 核心特性 (Key Features)
🚀 0 依赖轻量级高并发 (Standard Lib Mastery)

在 site-read.py 中，弃用臃肿的 requests，采用纯 Python 内置 urllib 实现。

引入 concurrent.futures.ThreadPoolExecutor 开启 20 线程并发抓取，完美解决海量请求的 Timeout 问题，将原本 5 分钟的扫描压缩至 10 秒内。

🧹 精准的正则清洗与文本处理 (Regex & Text Processing)

内置 URL 语义提取引擎，使用多重正则表达式 (re.sub) 将脏路径、无意义后缀过滤，精准提取出高质量的自然语言 Keyword，转化为大模型易于理解的语料。

💾 SQLite 增量状态机 (Incremental Database)

爬虫不再是简单的“抓取-覆盖”，而是引入了本地 SQLite 数据库。实现了页面级的新增、下架增量追踪，让 Agent 能够动态感知外界信息的“变化”（例如：监控竞争对手今日上新的内容）。

🔌 标准化的 Agent 接口输出 (JSON Format for LLMs)

所有抓取结果（如 YouTube API 获取的三维统计数据、Sitemap 的关键词风向标）最终均被清洗并打包为规范的 JSON 格式。完美契合大模型 Function Calling 的参数要求。

📂 核心模块架构 (Architecture)
core/site-read.py: 基于多线程和 SQLite 的高可用 Sitemap 监控爬虫，支持 XML/GZIP 自动解析及异常重试。

core/youtube-read.py: 基于 Google API Client 的精准频道数据提取器，支持 RFC 3339 时间窗过滤（自动拉取近 7 天爆款内容）。

config/: 包含 targets.txt 和 bench.txt，将代码逻辑与配置解耦，易于维护。

🛠️ 快速开始 (Quick Start)
code
Bash
# 1. 克隆项目
git clone https://github.com/krik241124/Agent-Data-Harvester.git
cd Agent-Data-Harvester

# 2. 安装依赖 (主要用于 YouTube API)
pip install -r requirements.txt

# 3. 运行多线程 Sitemap 爬虫 (纯标准库，无需额外依赖)
python core/site-read.py

# 4. 运行 YouTube 监控源 (需在源码中配置 YOUR_API_KEY)
python core/youtube-read.py
