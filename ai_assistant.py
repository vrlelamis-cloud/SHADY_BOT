import aiohttp, asyncio, logging
from typing import List, Dict
from config import Config

logger = logging.getLogger(__name__)

class AIAssistant:
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    SYSTEM_PROMPT = """
Tu es SHADYBOT, un assistant IA intégré à Telegram.
Réponds principalement en français. Sois naturel, utile, direct et précis.
Utilise l'historique fourni pour conserver le contexte. N'invente pas les faits.
Les commandes Telegram sont exécutées par le programme : ne prétends jamais
avoir exécuté une commande si le programme ne l'a pas réellement fait.
"""

    async def _request(self, messages: List[Dict], max_tokens: int = 2048) -> str:
        if not Config.OPENROUTER_API_KEY:
            return "⚠️ Assistant IA non configuré. Ajoute OPENROUTER_API_KEY dans Railway."
        headers = {
            "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/vrlelamis-cloud/SHADY_BOT",
            "X-Title": "SHADYBOT",
        }
        payload = {"model": Config.AI_MODEL, "messages": messages,
                   "max_tokens": max_tokens, "temperature": Config.AI_TEMPERATURE}
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.API_URL, json=payload, headers=headers) as response:
                    data = await response.json()
                    if response.status != 200:
                        error = data.get("error", {}).get("message", f"HTTP {response.status}")
                        return f"❌ Erreur IA : {error}"
                    choices = data.get("choices", [])
                    if not choices:
                        return "❌ L'IA n'a pas retourné de réponse."
                    answer = choices[0].get("message", {}).get("content", "")
                    return answer.strip() or "❌ Réponse IA vide."
        except asyncio.TimeoutError:
            return "⏱️ L'IA met trop de temps à répondre. Réessaie dans quelques secondes."
        except Exception as exc:
            logger.exception("Erreur OpenRouter")
            return f"❌ Erreur de connexion à l'IA : {str(exc) or type(exc).__name__}"

    async def ask(self, question: str, max_tokens: int = 2048) -> str:
        return await self._request([
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ], max_tokens)

    async def ask_with_history(self, question: str, history: List[Dict], max_tokens: int = 2048) -> str:
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        for item in history:
            role, content = item.get("role"), str(item.get("content", "")).strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": question})
        max_messages = max(2, Config.AI_MAX_HISTORY_MESSAGES + 2)
        messages = [messages[0]] + messages[-(max_messages - 1):]
        return await self._request(messages, max_tokens)

    async def summarize_messages(self, messages: List[Dict]) -> str:
        if not messages:
            return "Pas assez de messages récents à résumer."
        transcript = "\n".join(f"{m.get('author', 'Utilisateur')}: {m.get('text', '')}" for m in messages)
        return await self.ask("Résume brièvement ces messages en français sous forme de points :\n\n" + transcript, 1200)

    async def answer_with_context(self, question: str, search_results: List[Dict], max_tokens: int = 1500) -> str:
        usable = [r for r in search_results if r.get("url")]
        if not usable:
            return await self.ask(question, max_tokens)
        context = "\n\n".join(
            f"[{i+1}] {r.get('title', '')}\n{r.get('snippet', '')}\nSource: {r.get('url', '')}"
            for i, r in enumerate(usable)
        )
        return await self._request([
            {"role": "system", "content": self.SYSTEM_PROMPT + "\nUtilise les résultats Web fournis comme source principale."},
            {"role": "user", "content": f"Résultats Web :\n\n{context}\n\nQuestion : {question}"},
        ], max_tokens)
