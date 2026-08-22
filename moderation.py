"""
Système de modération avancé pour groupes Telegram
Filtres, avertissements, mutes, bannissements
"""
import re
from typing import List, Dict, Optional
from config import Config

class ModerationEngine:
    """Moteur de modération avec filtres configurables"""

    # Mots interdits par défaut (personnalisable)
    DEFAULT_BAD_WORDS = [
        'spam', 'arnaque', 'escroquerie', 'arnaqueur',
        'pute', 'salope', 'connard', 'enculé', 'fdp',
        'nique', 'bite', 'couille', 'merde', 'putain'
    ]

    # Patterns de spam
    SPAM_PATTERNS = [
        r'(.)\1{10,}',  # Répétitions de caractères
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Emails
        r'\+?\d{1,3}?[-.\s]?\(?(?:\d{1,4}?)\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',  # Téléphones
    ]

    def __init__(self, custom_bad_words: List[str] = None):
        self.bad_words = set(custom_bad_words or self.DEFAULT_BAD_WORDS)
        self.spam_patterns = [re.compile(p, re.IGNORECASE) for p in self.SPAM_PATTERNS]

    def check_message(self, text: str, user_id: int = None) -> Dict:
        """
        Analyse un message et retourne les infractions détectées
        """
        if not text:
            return {"is_clean": True, "violations": []}

        violations = []
        text_lower = text.lower()

        # Vérification des mots interdits
        for word in self.bad_words:
            if word in text_lower:
                violations.append({
                    "type": "bad_word",
                    "severity": "medium",
                    "details": f"Mot interdits détectés: {word}"
                })

        # Vérification des patterns de spam
        for pattern in self.spam_patterns:
            matches = pattern.findall(text)
            if matches:
                violations.append({
                    "type": "spam",
                    "severity": "high" if len(matches) > 2 else "medium",
                    "details": f"Pattern spam détectés ({len(matches)} occurrences)"
                })

        # Vérification des majuscules excessives (crier)
        if len(text) > 20:
            upper_ratio = sum(1 for c in text if c.isupper()) / len(text)
            if upper_ratio > 0.7:
                violations.append({
                    "type": "caps",
                    "severity": "low",
                    "details": "Utilisation excessive de majuscules"
                })

        # Vérification de la longueur excessive
        if len(text) > 2000:
            violations.append({
                "type": "flood",
                "severity": "medium",
                "details": "Message excessivement long"
            })

        return {
            "is_clean": len(violations) == 0,
            "violations": violations,
            "severity_score": self._calculate_severity(violations)
        }

    def _calculate_severity(self, violations: List[Dict]) -> int:
        """Calcule un score de sévérité (0-100)"""
        severity_map = {"low": 10, "medium": 30, "high": 50}
        return min(100, sum(severity_map.get(v["severity"], 10) for v in violations))

    def get_recommended_action(self, check_result: Dict, warning_count: int = 0) -> str:
        """
        Détermine l'action recommandée basée sur les violations
        """
        score = check_result["severity_score"]

        if score >= 80 or warning_count >= Config.MAX_WARNINGS:
            return "ban"
        elif score >= 50 or warning_count >= Config.MAX_WARNINGS - 1:
            return "mute"
        elif score >= 20:
            return "warn"
        else:
            return "delete"

    def add_custom_filter(self, word: str):
        """Ajoute un mot aux filtres"""
        self.bad_words.add(word.lower())

    def remove_custom_filter(self, word: str):
        """Retire un mot des filtres"""
        self.bad_words.discard(word.lower())

    def get_filters(self) -> List[str]:
        """Retourne la liste des filtres actifs"""
        return sorted(list(self.bad_words))
