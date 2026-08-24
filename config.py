"""
Configuration du bot Telegram Ultra
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Token du bot (à récupérer sur @BotFather)
    BOT_TOKEN = os.getenv("BOT_TOKEN", "TON_TOKEN_ICI")

    # ID des administrateurs (liste de IDs Telegram)
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "123456789").split(",") if x]

    # Base de données
    DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_data.db")

    # Paramètres de modération
    MAX_WARNINGS = int(os.getenv("MAX_WARNINGS", "3"))
    MUTE_DURATION = int(os.getenv("MUTE_DURATION", "3600"))  # secondes

    # Assistant IA
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-flash")

    # Anti-flood
    FLOOD_MAX_MESSAGES = int(os.getenv("FLOOD_MAX_MESSAGES", "5"))
    FLOOD_WINDOW_SECONDS = int(os.getenv("FLOOD_WINDOW_SECONDS", "6"))

    # Captcha à l'entrée
    CAPTCHA_TIMEOUT = int(os.getenv("CAPTCHA_TIMEOUT", "180"))  # secondes avant exclusion

    # Paramètres de diffusion
    BROADCAST_DELAY = float(os.getenv("BROADCAST_DELAY", "0.5"))  # secondes entre chaque message

    # Paramètres de recherche web
    SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "15"))
    MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "5"))
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

    # Logs
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Fichiers de sauvegarde
    BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")

    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        return user_id in cls.ADMIN_IDS
