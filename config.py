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

    # Paramètres de diffusion
    BROADCAST_DELAY = float(os.getenv("BROADCAST_DELAY", "0.5"))  # secondes entre chaque message

    # Paramètres de recherche web
    SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "15"))
    MAX_SEARCH_RESULTS = int(os.getenv("MAX_SEARCH_RESULTS", "5"))
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")

    # Logs
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Fichiers de sauvegarde
    BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")

    @classmethod
    def is_admin(cls, user_id: int) -> bool:
        return user_id in cls.ADMIN_IDS
