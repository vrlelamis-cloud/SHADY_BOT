"""
Module de recherche web intelligent
Utilise l'API Google Custom Search (officielle) pour obtenir des résultats
"""
import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup
from typing import List, Dict
from config import Config
import urllib.parse

logger = logging.getLogger(__name__)

class WebSearch:
    """Moteur de recherche web asynchrone (Google Custom Search API)"""

    GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

    async def search(self, query: str, max_results: int = None) -> List[Dict]:
        """
        Effectue une recherche web via l'API Google Custom Search et retourne les résultats
        """
        max_results = max_results or Config.MAX_SEARCH_RESULTS

        if not Config.GOOGLE_API_KEY or not Config.GOOGLE_CSE_ID:
            logger.error("GOOGLE_API_KEY ou GOOGLE_CSE_ID manquant dans les variables d'environnement")
            return [{
                "title": "Recherche non configurée",
                "url": "",
                "snippet": "GOOGLE_API_KEY et GOOGLE_CSE_ID doivent être définis sur Render."
            }]

        params = {
            'key': Config.GOOGLE_API_KEY,
            'cx': Config.GOOGLE_CSE_ID,
            'q': query,
            'num': min(max_results, 10),  # l'API limite à 10 résultats par requête
            'hl': 'fr',
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=Config.SEARCH_TIMEOUT)) as session:
                async with session.get(self.GOOGLE_SEARCH_URL, params=params) as response:
                    data = await response.json()

                    if response.status != 200:
                        error_msg = data.get('error', {}).get('message', f"Statut HTTP {response.status}")
                        logger.error(f"Erreur API Google Search pour '{query}': {error_msg}")
                        return [{"title": "Erreur de recherche", "url": "", "snippet": error_msg}]

                    items = data.get('items', [])
                    if not items:
                        return [{"title": "Aucun résultat", "url": "", "snippet": "La recherche n'a retourné aucun résultat."}]

                    return [
                        {
                            'title': item.get('title', ''),
                            'url': item.get('link', ''),
                            'snippet': item.get('snippet', ''),
                        }
                        for item in items[:max_results]
                    ]
        except Exception as e:
            logger.exception(f"Erreur pendant la recherche web pour la requête '{query}'")
            return [{"title": "Erreur de recherche", "url": "", "snippet": str(e) or type(e).__name__}]

    async def fetch_page_content(self, url: str) -> str:
        """
        Récupère le contenu textuel d'une page web
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        # Supprime les scripts et styles
                        for script in soup(["script", "style"]):
                            script.decompose()
                        text = soup.get_text(separator='\n', strip=True)
                        # Limite à 3000 caractères
                        return text[:3000] + "..." if len(text) > 3000 else text
                    else:
                        return f"Erreur HTTP {response.status}"
        except Exception as e:
            logger.exception(f"Erreur pendant l'extraction de la page '{url}'")
            return f"Erreur: {str(e)}"

    async def search_news(self, query: str, max_results: int = 3) -> List[Dict]:
        """Recherche spécifique d'actualités"""
        return await self.search(f"{query} actualités news", max_results)

    async def search_images(self, query: str) -> str:
        """Retourne une URL de recherche d'images"""
        encoded = urllib.parse.quote(query)
        return f"https://duckduckgo.com/?q={encoded}&iax=images&ia=images"
