import logging

from telegram import Bot

from fetchers.base import Article

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, parse_mode: str = "HTML"):
        self.bot = Bot(token=bot_token)
        self.parse_mode = parse_mode

    async def send_articles(
        self, chat_id: int | str, articles: list[Article], source_label: str
    ) -> int:
        """Send articles grouped by source to a chat. Returns count of sent messages."""
        if not articles:
            return 0

        messages = self._format_messages(articles, source_label)
        sent = 0
        for msg in messages:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode=self.parse_mode,
                    disable_web_page_preview=True,
                )
                sent += 1
            except Exception as e:
                logger.error(f"Failed to send to {chat_id}: {e}")
        return sent

    async def send_test(self, chat_id: int | str) -> bool:
        """Send test message. Returns True if successful."""
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text="News Telegram Bot 연결 테스트 성공!",
            )
            return True
        except Exception as e:
            logger.error(f"Test message failed for {chat_id}: {e}")
            return False

    def _format_messages(
        self, articles: list[Article], source_label: str
    ) -> list[str]:
        """Format articles into Telegram messages. Split if >4096 chars."""
        from datetime import datetime

        header = (
            f"<b>{source_label}</b> - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        )

        messages: list[str] = []
        current = header

        for i, article in enumerate(articles, 1):
            entry = f'{i}. <a href="{article.url}">{self._escape_html(article.title)}</a>\n'
            if article.summary:
                entry += f"   {self._escape_html(article.summary[:100])}\n"
            entry += "\n"

            if len(current) + len(entry) > 4000:  # Leave margin for Telegram's 4096 limit
                messages.append(current.strip())
                current = header + entry
            else:
                current += entry

        if current.strip() and current.strip() != header.strip():
            messages.append(current.strip())

        return messages if messages else [header + "새로운 기사가 없습니다."]

    @staticmethod
    def _escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
