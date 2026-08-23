"""
Module de recherche web intelligent
Utilise l'API Tavily (recherche web pensée pour les applications IA)
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
    """Moteur de recherche web asynchrone (Tavily API)"""

    TAVILY_SEARCH_URL = "https://api.tavily.com/search"

    async def search(self, query: str, max_results: int = None) -> List[Dict]:
        """
        Effectue une recherche web via l'API Tavily et retourne les résultats
        """
        max_results = max_results or Config.MAX_SEARCH_RESULTS

        if not Config.TAVILY_API_KEY:
            logger.error("TAVILY_API_KEY manquant dans les variables d'environnement")
            return [{
                "title": "Recherche non configurée",
                "url": "",
                "snippet": "TAVILY_API_KEY doit être défini sur Render."
            }]

        headers = {
            "Authorization": f"Bearer {Config.TAVILY_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=Config.SEARCH_TIMEOUT)) as session:
                async with session.post(self.TAVILY_SEARCH_URL, json=payload, headers=headers) as response:
                    data = await response.json()

                    if response.status != 200:
                        error_msg = data.get('detail', data.get('error', f"Statut HTTP {response.status}"))
                        logger.error(f"Erreur API Tavily pour '{query}': {error_msg}")
                        return [{"title": "Erreur de recherche", "url": "", "snippet": str(error_msg)}]

                    items = data.get('results', [])
                    if not items:
                        return [{"title": "Aucun résultat", "url": "", "snippet": "La recherche n'a retourné aucun résultat."}]

                    return [
                        {
                            'title': item.get('title', ''),
                            'url': item.get('url', ''),
                            'snippet': item.get('content', ''),
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
