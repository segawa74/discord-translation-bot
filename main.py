from src.bot import TranslationBot
from src.config import get_discord_token


def main():
    token = get_discord_token()
    bot = TranslationBot(token)
    bot.run()


if __name__ == "__main__":
    main()
