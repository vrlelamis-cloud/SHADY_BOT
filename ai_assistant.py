"""
Module d'assistant IA
Utilise l'API OpenRouter (gratuite, format OpenAI-compatible) pour répondre
aux questions et résumer des discussions. Modèle par défaut: Qwen3-Coder
(gratuit sur OpenRouter, configurable via la variable AI_MODEL).
"""
import aiohttp
import asyncio
import logging
from typing import List, Dict
from config import Config

logger = logging.getLogger(__name__)

class AIAssistant:
    """Assistant conversationnel asynchrone (API OpenRouter)"""

    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    async def ask(self, question: str, max_tokens: int = 2048) -> str:
        """Envoie une question à l'assistant IA et retourne la réponse en texte brut"""
        if not Config.OPENROUTER_API_KEY:
            return "⚠️ Assistant IA non configuré (OPENROUTER_API_KEY manquant sur Render)."

        headers = {
            "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": Config.AI_MODEL,
            "messages": [{"role": "user", "content": question}],
            "max_tokens": max_tokens,
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as session:
                async with session.post(self.API_URL, json=payload, headers=headers) as response:
                    data = await response.json()

                    if response.status != 200:
                        error_msg = data.get("error", {}).get("message", f"Statut HTTP {response.status}")
                        logger.error(f"Erreur API OpenRouter: {error_msg}")
                        return f"❌ Erreur de l'assistant IA: {error_msg}"

                    try:
                        text = data["choices"][0]["message"]["content"]
                    except (KeyError, IndexError):
                        logger.error(f"Réponse OpenRouter inattendue: {data}")
                        return "❌ Réponse vide de l'assistant."
                    return (text or "").strip() or "❌ Réponse vide de l'assistant."
        except asyncio.TimeoutError:
            logger.error("Timeout pendant l'appel à l'assistant IA")
            return "⏱️ L'assistant IA met trop de temps à répondre. Réessaie dans quelques instants."
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
        return await self.ask(prompt, max_tokens=1200)

    async def answer_with_context(self, question: str, search_results: List[Dict], max_tokens: int = 1500) -> str:
        """Répond à une question en s'appuyant sur des résultats de recherche web récents"""
        usable = [r for r in search_results if r.get("url")]  # ignore les placeholders d'erreur/absence de résultat
        if not usable:
            return await self.ask(question, max_tokens)

        context_text = "\n\n".join(
            f"[{i+1}] {r.get('title', '')}\n{r.get('snippet', '')}\nSource: {r.get('url', '')}"
            for i, r in enumerate(usable)
        )
        prompt = (
            "Tu es un assistant qui répond en te basant sur des résultats de recherche web "
            "récents fournis ci-dessous. Réponds en français, de façon claire et directe. "
            "Si ces résultats ne contiennent pas l'information demandée, dis-le clairement "
            "plutôt que d'inventer une réponse à partir de tes connaissances générales.\n\n"
            f"Résultats de recherche:\n{context_text}\n\n"
            f"Question: {question}"
        )
        return await self.ask(prompt, max_tokens)
