import asyncio
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv(Path(__file__).parent / ".env")

from config.manager import ConfigManager
from config.schema import RecipientConfig, ScheduleConfig, SiteConfig
from db.storage import ArticleStorage
from main import run_pipeline, setup_logging
from notifiers.telegram import TelegramNotifier
from scheduler.cron import NewsScheduler

DEFAULT_CONFIG = "config.yaml"


@click.group()
@click.option("--config", "-c", default=DEFAULT_CONFIG, help="Config file path")
@click.pass_context
def cli(ctx, config):
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


# ── run command ──────────────────────────────────────────────────


@cli.command()
@click.pass_context
def run(ctx):
    """Start the scheduler daemon."""
    cm = ConfigManager(ctx.obj["config_path"])
    setup_logging(cm.config.logging.level, cm.config.logging.file)

    storage = ArticleStorage(cm.config.storage.db_path)
    notifier = TelegramNotifier(cm.config.bot_token, cm.config.parse_mode)
    scheduler = NewsScheduler()

    async def pipeline_callback(**kwargs):
        await run_pipeline(cm, storage, notifier, **kwargs)

    scheduler.set_pipeline(pipeline_callback)
    scheduler.load_schedules(cm.config.schedules)

    click.echo("News Bot started. Press Ctrl+C to stop.")
    for job in scheduler.get_next_runs():
        click.echo(f"  {job['name']} -> next: {job['next_run']}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    scheduler.start()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
        scheduler.stop()
        loop.close()


# ── fetch command (dry run) ──────────────────────────────────────


@cli.command()
@click.option("--source", "-s", default=None, help="Fetch from specific source key")
@click.pass_context
def fetch(ctx, source):
    """Fetch articles without sending (dry run)."""
    cm = ConfigManager(ctx.obj["config_path"])
    setup_logging(cm.config.logging.level)
    storage = ArticleStorage(cm.config.storage.db_path)
    notifier = TelegramNotifier(cm.config.bot_token)

    sites = [source] if source else None
    result = asyncio.run(
        run_pipeline(cm, storage, notifier, dry_run=True, sites=sites)
    )

    click.echo(f"\nResults: fetched={result['fetched']}, new={result['new']}")
    if result["errors"]:
        for err in result["errors"]:
            click.echo(f"  ERROR: {err}")


# ── send-now command ─────────────────────────────────────────────


@cli.command("send-now")
@click.option("--source", "-s", default=None, help="Send from specific source")
@click.pass_context
def send_now(ctx, source):
    """Fetch and send immediately."""
    cm = ConfigManager(ctx.obj["config_path"])
    setup_logging(cm.config.logging.level)
    storage = ArticleStorage(cm.config.storage.db_path)
    notifier = TelegramNotifier(cm.config.bot_token)

    sites = [source] if source else None
    result = asyncio.run(
        run_pipeline(cm, storage, notifier, schedule_name="manual", sites=sites)
    )

    click.echo(f"\nSent: {result['sent']} messages ({result['new']} new articles)")
    if result["errors"]:
        for err in result["errors"]:
            click.echo(f"  ERROR: {err}")


# ── Site management ──────────────────────────────────────────────


@cli.command("add-site")
@click.option("--name", required=True, help="Display name")
@click.option("--key", required=True, help="Unique key")
@click.option(
    "--type", "site_type", type=click.Choice(["rss", "scraper"]), required=True
)
@click.option("--url", required=True, help="Feed or page URL")
@click.option("--max-articles", default=10, help="Max articles per fetch")
@click.pass_context
def add_site(ctx, name, key, site_type, url, max_articles):
    """Add a news source."""
    cm = ConfigManager(ctx.obj["config_path"])
    site = SiteConfig(
        name=name, key=key, type=site_type, url=url, max_articles=max_articles
    )
    cm.add_site(site)
    click.echo(f"Site added: {name} ({key})")


@cli.command("remove-site")
@click.argument("key")
@click.pass_context
def remove_site(ctx, key):
    """Remove a news source by key."""
    cm = ConfigManager(ctx.obj["config_path"])
    cm.remove_site(key)
    click.echo(f"Site removed: {key}")


@cli.command("list-sites")
@click.pass_context
def list_sites(ctx):
    """List all configured sites."""
    cm = ConfigManager(ctx.obj["config_path"])
    for s in cm.config.sites:
        status = "ON" if s.enabled else "OFF"
        click.echo(f"  [{status}] [{s.key}] {s.name} ({s.type}) - {s.url}")


# ── Recipient management ─────────────────────────────────────────


@cli.command("add-recipient")
@click.option("--chat-id", required=True, help="Telegram chat ID")
@click.option("--name", required=True, help="Recipient name")
@click.pass_context
def add_recipient(ctx, chat_id, name):
    """Add a Telegram recipient."""
    cm = ConfigManager(ctx.obj["config_path"])
    recipient = RecipientConfig(chat_id=int(chat_id), name=name)
    cm.add_recipient(recipient)
    click.echo(f"Recipient added: {name} ({chat_id})")


@cli.command("remove-recipient")
@click.argument("name")
@click.pass_context
def remove_recipient(ctx, name):
    """Remove a recipient by name."""
    cm = ConfigManager(ctx.obj["config_path"])
    cm.remove_recipient(name)
    click.echo(f"Recipient removed: {name}")


@cli.command("list-recipients")
@click.pass_context
def list_recipients(ctx):
    """List all recipients."""
    cm = ConfigManager(ctx.obj["config_path"])
    for r in cm.config.recipients:
        status = "ON" if r.enabled else "OFF"
        click.echo(f"  [{status}] {r.name} (chat_id: {r.chat_id})")


# ── Schedule management ──────────────────────────────────────────


@cli.command("add-schedule")
@click.option("--name", required=True, help="Schedule name")
@click.option("--cron", required=True, help="Cron expression (e.g. '0 8 * * *')")
@click.option("--timezone", default="Asia/Seoul", help="Timezone")
@click.pass_context
def add_schedule(ctx, name, cron, timezone):
    """Add a notification schedule."""
    cm = ConfigManager(ctx.obj["config_path"])
    schedule = ScheduleConfig(name=name, cron=cron, timezone=timezone)
    cm.add_schedule(schedule)
    click.echo(f"Schedule added: {name} ({cron}, {timezone})")


@cli.command("remove-schedule")
@click.argument("name")
@click.pass_context
def remove_schedule(ctx, name):
    """Remove a schedule by name."""
    cm = ConfigManager(ctx.obj["config_path"])
    cm.remove_schedule(name)
    click.echo(f"Schedule removed: {name}")


@cli.command("list-schedules")
@click.pass_context
def list_schedules(ctx):
    """List all schedules."""
    cm = ConfigManager(ctx.obj["config_path"])
    for s in cm.config.schedules:
        sites_str = ", ".join(s.sites)
        click.echo(f"  {s.name}: {s.cron} ({s.timezone}) -> sites: [{sites_str}]")


# ── test command ─────────────────────────────────────────────────


@cli.command()
@click.option("--chat-id", default=None, help="Send to specific chat ID")
@click.pass_context
def test(ctx, chat_id):
    """Send a test message to verify Telegram connectivity."""
    cm = ConfigManager(ctx.obj["config_path"])
    notifier = TelegramNotifier(cm.config.bot_token)

    async def _test():
        targets = (
            [chat_id]
            if chat_id
            else [str(r.chat_id) for r in cm.config.recipients if r.enabled]
        )
        for cid in targets:
            ok = await notifier.send_test(cid)
            status = "Success" if ok else "Failed"
            click.echo(f"  {status}: {cid}")

    asyncio.run(_test())


# ── status command ───────────────────────────────────────────────


@cli.command()
@click.pass_context
def status(ctx):
    """Show bot status and statistics."""
    cm = ConfigManager(ctx.obj["config_path"])
    storage = ArticleStorage(cm.config.storage.db_path)
    stats = storage.get_stats()

    click.echo("News Bot Status")
    click.echo(f"  Sites: {len(cm.config.sites)}")
    click.echo(f"  Recipients: {len(cm.config.recipients)}")
    click.echo(f"  Schedules: {len(cm.config.schedules)}")
    click.echo(f"  Total articles sent: {stats.get('total', 0)}")
    if stats.get("sources"):
        click.echo("  By source:")
        for source, count in stats["sources"].items():
            click.echo(f"    {source}: {count}")
    if stats.get("last_fetch"):
        click.echo(f"  Last fetch: {stats['last_fetch']}")


if __name__ == "__main__":
    cli()
