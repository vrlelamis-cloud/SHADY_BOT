"""
Module d'assistant IA
Utilise l'API Gemini (Google AI Studio, gratuite) pour répondre aux questions et résumer des discussions
"""
import aiohttp
import logging
from typing import List, Dict
from config import Config

logger = logging.getLogger(__name__)

class AIAssistant:
    """Assistant conversationnel asynchrone (API Gemini)"""

    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    async def ask(self, question: str, max_tokens: int = 1024) -> str:
        """Envoie une question à l'assistant IA et retourne la réponse en texte brut"""
        if not Config.GEMINI_API_KEY:
            return "⚠️ Assistant IA non configuré (GEMINI_API_KEY manquant sur Render)."

        url = self.API_URL.format(model=Config.AI_MODEL)
        headers = {
            "x-goog-api-key": Config.GEMINI_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "contents": [{"parts": [{"text": question}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    data = await response.json()

                    if response.status != 200:
                        error_msg = data.get("error", {}).get("message", f"Statut HTTP {response.status}")
                        logger.error(f"Erreur API Gemini: {error_msg}")
                        return f"❌ Erreur de l'assistant IA: {error_msg}"

                    try:
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError):
                        logger.error(f"Réponse Gemini inattendue: {data}")
                        return "❌ Réponse vide de l'assistant (contenu probablement filtré)."
                    return text.strip()
        except Exception as e:
            logger.exception("Erreur pendant l'appel à l'assistant IA")
            return f"❌ Erreur: {str(e) or type(e).__name__}"

    async def summarize_messages(self, messages: List[Dict]) -> str:
        """Résume une liste de messages récents. messages: [{'author': str, 'text': str}, ...]"""
        if not messages:
            return "Pas assez de messages récents à résumer."

        transcript = "\n".join(f"{m['author']}: {m['text']}" for m in messages)
        prompt = (
            "Voici les derniers messages d'un groupe Telegram. Fais un résumé court "
            "(5 à 8 points maximum) de ce qui s'est dit, en français, sans détails inutiles "
            "ni reformulation message par message:\n\n"
            f"{transcript}"
        )
        return await self.ask(prompt, max_tokens=500)
