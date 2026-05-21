import os
from pathlib import Path

import yaml

from config.schema import (
    AppConfig,
    LoggingConfig,
    RecipientConfig,
    ScheduleConfig,
    SiteConfig,
    StorageConfig,
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class ConfigManager:
    """Loads, modifies, and persists config.yaml as an AppConfig."""

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.config: AppConfig = self._load()

    # ── load / save ──────────────────────────────────────────────

    def _load(self) -> AppConfig:
        if not self.config_path.exists():
            return AppConfig()

        raw = self.config_path.read_text(encoding="utf-8")
        # Substitute env vars like ${TELEGRAM_BOT_TOKEN}
        raw = os.path.expandvars(raw)
        data: dict = yaml.safe_load(raw) or {}

        bot = data.get("bot", {})
        sites = [SiteConfig(**s) for s in data.get("sites", [])]
        recipients = [RecipientConfig(**r) for r in data.get("recipients", [])]
        schedules = [ScheduleConfig(**sc) for sc in data.get("schedules", [])]
        storage = StorageConfig(**data.get("storage", {}))
        logging_cfg = LoggingConfig(**data.get("logging", {}))

        return AppConfig(
            bot_token=bot.get("token", ""),
            parse_mode=bot.get("parse_mode", "HTML"),
            sites=sites,
            recipients=recipients,
            schedules=schedules,
            storage=storage,
            logging=logging_cfg,
        )

    def reload(self) -> None:
        self.config = self._load()

    def save(self) -> None:
        data = self._to_dict()
        self.config_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def _to_dict(self) -> dict:
        cfg = self.config
        return {
            "bot": {
                "token": cfg.bot_token,
                "parse_mode": cfg.parse_mode,
            },
            "sites": [
                {
                    "name": s.name,
                    "key": s.key,
                    "type": s.type,
                    "url": s.url,
                    "enabled": s.enabled,
                    "max_articles": s.max_articles,
                    **({"selectors": s.selectors} if s.selectors else {}),
                }
                for s in cfg.sites
            ],
            "recipients": [
                {"chat_id": r.chat_id, "name": r.name, "enabled": r.enabled}
                for r in cfg.recipients
            ],
            "schedules": [
                {
                    "name": sc.name,
                    "cron": sc.cron,
                    "timezone": sc.timezone,
                    "sites": sc.sites,
                    "recipients": sc.recipients,
                }
                for sc in cfg.schedules
            ],
            "storage": {
                "db_path": cfg.storage.db_path,
                "retention_days": cfg.storage.retention_days,
            },
            "logging": {
                "level": cfg.logging.level,
                "file": cfg.logging.file,
            },
        }

    # ── sites ────────────────────────────────────────────────────

    def add_site(self, site: SiteConfig) -> None:
        if any(s.key == site.key for s in self.config.sites):
            raise ValueError(f"Site with key '{site.key}' already exists")
        self.config.sites.append(site)
        self.save()

    def remove_site(self, key: str) -> None:
        before = len(self.config.sites)
        self.config.sites = [s for s in self.config.sites if s.key != key]
        if len(self.config.sites) == before:
            raise KeyError(f"Site '{key}' not found")
        self.save()

    def list_sites(self) -> list[SiteConfig]:
        return list(self.config.sites)

    # ── recipients ───────────────────────────────────────────────

    def add_recipient(self, recipient: RecipientConfig) -> None:
        if any(r.name == recipient.name for r in self.config.recipients):
            raise ValueError(f"Recipient '{recipient.name}' already exists")
        self.config.recipients.append(recipient)
        self.save()

    def remove_recipient(self, name: str) -> None:
        before = len(self.config.recipients)
        self.config.recipients = [r for r in self.config.recipients if r.name != name]
        if len(self.config.recipients) == before:
            raise KeyError(f"Recipient '{name}' not found")
        self.save()

    def list_recipients(self) -> list[RecipientConfig]:
        return list(self.config.recipients)

    # ── schedules ────────────────────────────────────────────────

    def add_schedule(self, schedule: ScheduleConfig) -> None:
        if any(sc.name == schedule.name for sc in self.config.schedules):
            raise ValueError(f"Schedule '{schedule.name}' already exists")
        self.config.schedules.append(schedule)
        self.save()

    def remove_schedule(self, name: str) -> None:
        before = len(self.config.schedules)
        self.config.schedules = [sc for sc in self.config.schedules if sc.name != name]
        if len(self.config.schedules) == before:
            raise KeyError(f"Schedule '{name}' not found")
        self.save()
