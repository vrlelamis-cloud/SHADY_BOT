"""
Module de recherche web intelligent
Utilise DuckDuckGo et scraping pour obtenir des résultats
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
    """Moteur de recherche web asynchrone"""

    DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"

    async def search(self, query: str, max_results: int = None) -> List[Dict]:
        """
        Effectue une recherche web et retourne les résultats
        """
        max_results = max_results or Config.MAX_SEARCH_RESULTS

        params = {
            'q': query,
            'kl': 'fr-fr'
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=Config.SEARCH_TIMEOUT)) as session:
                async with session.get(self.DUCKDUCKGO_URL, params=params, headers=headers) as response:
                    if response.status != 200:
                        return [{"title": "Erreur", "url": "", "snippet": f"Status: {response.status}"}]

                    html = await response.text()
                    return self._parse_results(html, max_results)
        except Exception as e:
            logger.exception(f"Erreur pendant la recherche web pour la requête '{query}'")
            return [{"title": "Erreur de recherche", "url": "", "snippet": str(e) or type(e).__name__}]

    def _parse_results(self, html: str, max_results: int) -> List[Dict]:
        """Parse les résultats HTML de DuckDuckGo"""
        soup = BeautifulSoup(html, 'html.parser')
        results = []

        for result in soup.find_all('div', class_='result')[:max_results]:
            title_tag = result.find('a', class_='result__a')
            snippet_tag = result.find('a', class_='result__snippet')

            if title_tag and snippet_tag:
                results.append({
                    'title': title_tag.get_text(strip=True),
                    'url': title_tag.get('href', ''),
                    'snippet': snippet_tag.get_text(strip=True)
                })

        return results if results else [{"title": "Aucun résultat", "url": "", "snippet": "La recherche n'a retourné aucun résultat."}]

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
