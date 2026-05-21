from dataclasses import dataclass, field


@dataclass
class SiteConfig:
    name: str
    key: str
    type: str  # "rss" or "scraper"
    url: str
    enabled: bool = True
    max_articles: int = 10
    selectors: dict[str, str] = field(default_factory=dict)


@dataclass
class RecipientConfig:
    chat_id: int | str
    name: str
    enabled: bool = True


@dataclass
class ScheduleConfig:
    name: str
    cron: str  # cron expression e.g. "0 8 * * *"
    timezone: str = "Asia/Seoul"
    sites: list[str] = field(default_factory=lambda: ["all"])
    recipients: list[str] = field(default_factory=lambda: ["all"])


@dataclass
class StorageConfig:
    db_path: str = "news_bot.db"
    retention_days: int = 90


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "news_bot.log"


@dataclass
class AppConfig:
    bot_token: str = ""
    parse_mode: str = "HTML"
    sites: list[SiteConfig] = field(default_factory=list)
    recipients: list[RecipientConfig] = field(default_factory=list)
    schedules: list[ScheduleConfig] = field(default_factory=list)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
