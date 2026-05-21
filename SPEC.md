# Technical Specification: News Aggregator with Telegram Notifications

## 1. Overview

A Python CLI application that collects news articles from Korean tech sites via RSS feeds, APIs, and web scraping, then delivers them to configured Telegram recipients on a schedule. Designed as a simple, single-process personal tool with YAML-driven configuration and SQLite-based deduplication.

---

## 2. Tech Stack

| Component | Choice | Rationale |
|---|---|---|
| Language | Python 3.10+ | Pattern matching, modern typing, broad library ecosystem |
| RSS Parsing | `feedparser` | De facto standard for RSS/Atom parsing; handles malformed feeds gracefully |
| HTTP Client | `httpx` | Async-capable, timeout handling, HTTP/2 support; replaces requests for modern usage |
| HTML Parsing | `beautifulsoup4` + `lxml` | Robust scraping fallback when RSS is unavailable; lxml for speed |
| Telegram | `python-telegram-bot` (v20+) | Official-quality wrapper, async-native in v20+, well-documented |
| Scheduler | `APScheduler` (v3.x) | Cron-style scheduling without external dependencies (no crontab needed) |
| Config | `pyyaml` | Human-readable config format; native Python dict mapping |
| Storage | `sqlite3` (stdlib) | Zero-dependency persistent storage; perfect for dedup tracking at this scale |
| CLI | `click` | Cleaner than argparse for subcommand-based CLIs; automatic help generation |
| Logging | `logging` (stdlib) | Standard, configurable, zero-dependency |

---

## 3. Architecture

### 3.1 Module Diagram

```
┌─────────────────────────────────────────────────────┐
│                    CLI (click)                       │
│  news-bot run | add-site | remove-site | list-sites │
│  send-now | add-recipient | test | status           │
└──────────────┬──────────────────────────────────────┘
               │
       ┌───────▼───────┐
       │  App Core      │
       │  (main.py)     │
       └───┬───┬───┬────┘
           │   │   │
    ┌──────┘   │   └──────┐
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌──────────┐
│Fetcher │ │Notifier│ │Scheduler │
│Module  │ │Module  │ │Module    │
└───┬────┘ └───┬────┘ └──────────┘
    │          │
    ▼          ▼
┌────────┐ ┌────────┐
│Storage │ │Telegram│
│(SQLite)│ │Bot API │
└────────┘ └────────┘
    ▲
    │
┌───┴─────┐
│ Config  │
│ Manager │
│ (YAML)  │
└─────────┘
```

### 3.2 Module Responsibilities

**Fetcher Module** (`fetchers/`)
- Parses RSS feeds using feedparser
- Falls back to HTTP + BeautifulSoup scraping when RSS is unavailable
- Returns a unified `Article` dataclass regardless of source type
- Each site has its own fetcher class implementing a common interface
- Handles timeouts, retries (1 retry), and error logging per source

**Notifier Module** (`notifiers/`)
- Formats articles into Telegram-friendly messages (HTML parse mode)
- Sends messages to configured chat IDs via python-telegram-bot
- Batches articles per source to avoid Telegram rate limits (max 20 msgs/min per chat)
- Supports both individual users and group chats

**Scheduler Module** (`scheduler/`)
- Wraps APScheduler with cron triggers loaded from config
- Runs the fetch-deduplicate-notify pipeline on each trigger
- Supports multiple independent schedules (e.g., morning digest, evening digest)

**Config Manager** (`config/`)
- Loads and validates `config.yaml`
- Provides typed access to sites, schedules, recipients, and bot settings
- Supports runtime modification via CLI commands (add/remove sites, recipients)

**Storage** (`db/`)
- SQLite database for tracking sent articles (deduplication)
- Stores article fingerprints (URL hash) with timestamps
- Provides cleanup of old records (configurable retention, default 90 days)

**CLI Interface** (`cli.py`)
- `run` - Start the scheduler daemon
- `fetch` - One-shot fetch from all or specific sources (dry run)
- `send-now` - Immediately fetch and send to all recipients
- `add-site` / `remove-site` / `list-sites` - Manage news sources
- `add-recipient` / `remove-recipient` / `list-recipients` - Manage Telegram recipients
- `test` - Send a test message to verify Telegram connectivity
- `status` - Show last fetch times, article counts, next scheduled run

---

## 4. File Structure

```
news-telegram-bot/
├── config/
│   ├── __init__.py
│   ├── manager.py          # YAML config load/save/validate
│   └── schema.py           # Config dataclasses and validation
├── fetchers/
│   ├── __init__.py
│   ├── base.py             # Abstract base fetcher + Article dataclass
│   ├── rss.py              # Generic RSS fetcher (feedparser)
│   ├── hada.py             # news.hada.io fetcher (RSS)
│   ├── aitimes.py          # aitimes.com fetcher (scraper)
│   └── yozm.py             # yozm.wishket.com fetcher (scraper)
├── notifiers/
│   ├── __init__.py
│   └── telegram.py         # Telegram message formatting + sending
├── scheduler/
│   ├── __init__.py
│   └── cron.py             # APScheduler wrapper
├── db/
│   ├── __init__.py
│   └── storage.py          # SQLite operations (dedup, cleanup)
├── tests/
│   ├── __init__.py
│   ├── test_fetchers.py
│   ├── test_notifier.py
│   ├── test_storage.py
│   └── test_config.py
├── cli.py                  # Click CLI entry point
├── main.py                 # App core: pipeline orchestration
├── config.yaml             # User configuration (gitignored in template)
├── config.example.yaml     # Template configuration
├── requirements.txt
├── pyproject.toml
├── SPEC.md                 # This document
└── README.md
```

---

## 5. Dependencies

### requirements.txt

```
feedparser>=6.0
httpx>=0.27
beautifulsoup4>=4.12
lxml>=5.0
python-telegram-bot>=20.0
APScheduler>=3.10,<4.0
pyyaml>=6.0
click>=8.1
```

### Dev Dependencies

```
pytest>=8.0
pytest-asyncio>=0.23
ruff>=0.4
```

---

## 6. Key Interfaces and Data Structures

### 6.1 Article Dataclass

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Article:
    title: str
    url: str
    source: str                          # e.g., "hada", "aitimes", "yozm"
    summary: str = ""
    published_at: datetime | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def fingerprint(self) -> str:
        """SHA-256 hash of the URL for deduplication."""
        import hashlib
        return hashlib.sha256(self.url.encode()).hexdigest()
```

### 6.2 Base Fetcher Interface

```python
from abc import ABC, abstractmethod

class BaseFetcher(ABC):
    def __init__(self, site_config: SiteConfig):
        self.config = site_config

    @abstractmethod
    async def fetch(self) -> list[Article]:
        """Fetch articles from the source. Returns list of Article."""
        ...
```

### 6.3 Notifier Interface

```python
class TelegramNotifier:
    def __init__(self, bot_token: str):
        self.bot = Bot(token=bot_token)

    async def send_articles(
        self,
        chat_id: int | str,
        articles: list[Article],
        source_label: str,
    ) -> int:
        """
        Send formatted articles to a Telegram chat.
        Returns number of successfully sent articles.
        """
        ...
```

### 6.4 Storage Interface

```python
class ArticleStorage:
    def __init__(self, db_path: str = "news_bot.db"):
        ...

    def is_sent(self, fingerprint: str) -> bool:
        """Check if article was already sent."""
        ...

    def mark_sent(self, fingerprint: str, source: str) -> None:
        """Record article as sent with current timestamp."""
        ...

    def cleanup(self, retention_days: int = 90) -> int:
        """Delete records older than retention period. Returns count deleted."""
        ...
```

---

## 7. Configuration Schema

### config.yaml

```yaml
bot:
  token: "${TELEGRAM_BOT_TOKEN}"    # Env var substitution supported
  parse_mode: "HTML"

sites:
  - name: "GeekNews (Hada)"
    key: "hada"
    type: "rss"
    url: "https://news.hada.io/rss"
    enabled: true
    max_articles: 10                 # Per fetch cycle

  - name: "AI Times"
    key: "aitimes"
    type: "scraper"
    url: "https://www.aitimes.com/"
    enabled: true
    max_articles: 10
    selectors:                       # CSS selectors for scraper
      article_list: "div.article-list-content"
      title: "h2.article-title a"
      link: "h2.article-title a"
      summary: "p.article-summary"

  - name: "Yozm Wishket AI"
    key: "yozm"
    type: "scraper"
    url: "https://yozm.wishket.com/magazine/list/ai/"
    enabled: true
    max_articles: 10
    selectors:
      article_list: "ul.list-group"
      title: "a.item-title"
      link: "a.item-title"
      summary: "p.item-description"

recipients:
  - chat_id: 123456789
    name: "sejin"
    enabled: true

schedules:
  - name: "morning"
    cron: "0 8 * * *"               # 08:00 daily
    timezone: "Asia/Seoul"
    sites: ["hada", "aitimes", "yozm"]  # Which sites to include
    recipients: ["all"]              # "all" or list of chat_ids

  - name: "evening"
    cron: "0 18 * * 1-5"            # 18:00 weekdays only
    timezone: "Asia/Seoul"
    sites: ["hada"]
    recipients: ["all"]

storage:
  db_path: "news_bot.db"
  retention_days: 90

logging:
  level: "INFO"
  file: "news_bot.log"
```

---

## 8. Data Flow

### 8.1 Scheduled Fetch-and-Notify Pipeline

```
1. APScheduler triggers a schedule (e.g., "morning" at 08:00 KST)
2. Pipeline reads schedule config -> determines which sites to fetch
3. For each enabled site:
   a. Instantiate the appropriate fetcher (RSS or Scraper)
   b. Fetch articles -> list[Article]
   c. Filter through storage.is_sent() -> only new articles
   d. If new articles exist:
      - For each recipient in the schedule:
        - Format message (grouped by source)
        - Send via TelegramNotifier
      - Mark all sent articles via storage.mark_sent()
4. Log summary: "Sent 5 new articles (hada: 3, aitimes: 2) to 1 recipient"
```

### 8.2 Message Format (Telegram HTML)

```
📰 GeekNews (Hada) - 2026-05-21

1. <a href="https://...">Article Title One</a>
   Summary text truncated to 100 chars...

2. <a href="https://...">Article Title Two</a>
   Summary text truncated to 100 chars...

3. <a href="https://...">Article Title Three</a>
   Summary text truncated to 100 chars...
```

---

## 9. SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS sent_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fingerprint ON sent_articles(fingerprint);
CREATE INDEX IF NOT EXISTS idx_sent_at ON sent_articles(sent_at);

CREATE TABLE IF NOT EXISTS fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    fetched_count INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    error TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 10. Error Handling Strategy

| Scenario | Handling |
|---|---|
| RSS feed timeout / unreachable | Log warning, skip source, continue with other sources |
| Scraper CSS selector mismatch | Log error with page snippet for debugging, skip source |
| Telegram API rate limit (429) | Exponential backoff with max 3 retries, then log and skip |
| Telegram bot token invalid | Fatal error on startup with clear message |
| Config file missing/invalid | Exit with validation error message and example config path |
| SQLite DB locked | Retry once after 1s; single-process design minimizes this risk |
| Duplicate article detected | Skip silently (this is normal operation) |

---

## 11. CLI Usage Examples

```bash
# Start the scheduler (foreground)
python cli.py run

# One-shot: fetch and display without sending
python cli.py fetch
python cli.py fetch --source hada

# One-shot: fetch and send immediately
python cli.py send-now
python cli.py send-now --source hada

# Site management
python cli.py add-site --name "TechCrunch Korea" --key techcrunch \
    --type rss --url "https://example.com/rss"
python cli.py remove-site techcrunch
python cli.py list-sites

# Recipient management
python cli.py add-recipient --chat-id 123456789 --name "sejin"
python cli.py remove-recipient 123456789
python cli.py list-recipients

# Test connectivity
python cli.py test                    # Send test message to all recipients
python cli.py test --chat-id 123456  # Send to specific recipient

# Status check
python cli.py status                  # Last fetch times, next scheduled run
```

---

## 12. Implementation Priority

| Phase | Scope | Deliverable |
|---|---|---|
| Phase 1 | Core pipeline | Config loader, RSS fetcher (hada), SQLite storage, Telegram notifier, CLI `send-now` command |
| Phase 2 | Scraping + scheduling | Scraper fetchers (aitimes, yozm), APScheduler integration, CLI `run` command |
| Phase 3 | Management CLI | All site/recipient/schedule management commands, `status` command |
| Phase 4 | Polish | Error recovery improvements, logging, `config.example.yaml`, tests |

---

## 13. Constraints and Non-Goals

**Constraints:**
- Single-process, single-machine deployment
- All state in one SQLite file + one YAML config
- Korean-language content (UTF-8 throughout)
- Telegram message size limit: 4096 characters per message (split if needed)

**Non-Goals:**
- Web UI or dashboard
- Multi-user authentication
- Real-time push (polling-based is sufficient)
- Full-text article storage (only metadata for dedup)
- Containerization (can be added later but not in initial scope)
