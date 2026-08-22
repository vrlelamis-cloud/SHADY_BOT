#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
  🤖 BOT TELEGRAM SHADYBOT - Version Complète

  Fonctionnalités:
  ✓ Recherche web intelligente
  ✓ Modération de groupe avancée
  ✓ Tâches planifiées (diffusion, rappels)
  ✓ Administration complète
  ✓ Gestion de confidentialité
  ✓ Traitement de données
  ✓ Commandes programmables

  Auteur: IA Assistant
  Version: 2.0
═══════════════════════════════════════════════════════════════
"""

import asyncio
import logging
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from config import Config
from database import Database
from web_search import WebSearch
from moderation import ModerationEngine

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION DES LOGS
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, Config.LOG_LEVEL),
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# INITIALISATION DES MODULES
# ═══════════════════════════════════════════════════════════════
db = Database()
web_search = WebSearch()
moderation = ModerationEngine()

# États pour les conversations
BROADCAST_MSG, BROADCAST_CONFIRM = range(2)
SCHEDULE_MSG, SCHEDULE_TIME = range(2, 4)
SET_RULES = 4
ADD_FILTER = 5

# ═══════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ═══════════════════════════════════════════════════════════════

def escape_md(text: str) -> str:
    """Échappe les caractères MarkdownV2"""
    if not text:
        return ""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in chars:
        text = text.replace(char, f"\\{char}")
    return text

async def is_admin_or_owner(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    """Vérifie si l'utilisateur est admin du groupe"""
    if not update.effective_chat or update.effective_chat.type == "private":
        return True

    uid = user_id or update.effective_user.id

    # Vérification super admin
    if Config.is_admin(uid):
        return True

    try:
        member = await update.effective_chat.get_member(uid)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False

async def log_action(update: Update, action: str, details: str = ""):
    """Enregistre une action dans les logs"""
    user_id = update.effective_user.id if update.effective_user else 0
    chat_id = update.effective_chat.id if update.effective_chat else 0
    await db.log_activity(user_id, chat_id, action, details)

# ═══════════════════════════════════════════════════════════════
# COMMANDES DE BASE
# ═══════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    user = update.effective_user

    # Enregistre l'utilisateur
    await db.add_user(user.id, user.username, user.first_name, user.last_name or "")

    welcome_text = f"""
👋 *Bienvenue, {escape_md(user.first_name)}\!*

Je suis 🤖 *UltraBot*, votre assistant intelligent sur Telegram\.

📋 *Commandes disponibles:*
🔍 `/search <requête>` \- Recherche web
📰 `/news <sujet>` \- Actualités
📢 `/broadcast <message>` \- Diffusion \(admin\)
⏰ `/schedule <message>` \- Planifier une tâche
⚠️ `/warn @user <raison>` \- Avertir un membre
🔇 `/mute @user <durée>` \- Rendre muet
👢 `/ban @user <raison>` \- Bannir
📜 `/rules` \- Règles du groupe
📊 `/stats` \- Statistiques
⚙️ `/settings` \- Paramètres
❓ `/help` \- Aide complète

_Tapez /help pour plus de détails\._
    """

    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "start")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help - Aide complète"""
    help_text = """
📖 *AIDE COMPLÈTE D'ULTRABOT*

*🔍 RECHERCHE WEB*
`/search <requête>` \- Recherche sur le web
`/news <sujet>` \- Rechercher des actualités
`/fetch <url>` \- Extraire le contenu d'une page
`/images <requête>` \- Lien recherche d'images

*👥 MODÉRATION DE GROUPE*
`/warn @user <raison>` \- Donner un avertissement
`/unwarn @user` \- Retirer les avertissements
`/mute @user <durée>` \- Muet \(ex: 1h, 30m\)
`/unmute @user` \- Démuet
`/ban @user <raison>` \- Bannir du groupe
`/unban @user` \- Débannir
`/kick @user` \- Expulser temporairement
`/filters` \- Voir les filtres actifs
`/addfilter <mot>` \- Ajouter un filtre
`/delfilter <mot>` \- Retirer un filtre

*📢 DIFFUSION & TÂCHES*
`/broadcast <message>` \- Diffuser à tous les utilisateurs
`/schedule <message>` \- Planifier un message
`/tasks` \- Voir les tâches planifiées
`/cancel <id>` \- Annuler une tâche

*⚙️ ADMINISTRATION*
`/stats` \- Statistiques du bot
`/users` \- Liste des utilisateurs
`/groups` \- Liste des groupes
`/logs` \- Derniers logs
`/backup` \- Sauvegarder les données
`/setrules` \- Définir les règles du groupe
`/settings` \- Paramètres du groupe

*🔒 CONFIDENTIALITÉ*
`/privacy` \- Politique de confidentialité
`/delete_my_data` \- Supprimer mes données
`/export_data` \- Exporter mes données

*ℹ️ AUTRES*
`/info @user` \- Informations sur un membre
`/id` \- Votre ID Telegram
`/ping` \- Vérifier la latence
`/about` \- À propos du bot
    """

    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "help")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vérifie la latence du bot"""
    start_time = datetime.now()
    msg = await update.message.reply_text("🏓 Pong\! Calcul...")
    end_time = datetime.now()
    latency = (end_time - start_time).total_seconds() * 1000

    await msg.edit_text(f"🏓 *Pong\!*\n\n⚡ Latence: `{latency:.0f}ms`", parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "ping", f"{latency:.0f}ms")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche l'ID de l'utilisateur et du chat"""
    user = update.effective_user
    chat = update.effective_chat

    text = f"""
🆔 *Informations d'identification*

👤 *Utilisateur:*
• ID: `{user.id}`
• Nom: {escape_md(user.first_name)}
• Username: @{escape_md(user.username or 'N/A')}

💬 *Chat:*
• ID: `{chat.id}`
• Type: {escape_md(chat.type)}
• Titre: {escape_md(chat.title or 'N/A')}
    """

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "id")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """À propos du bot"""
    stats = await db.get_stats()

    text = f"""
🤖 *UltraBot v2\.0*

_Un bot Telegram intelligent et polyvalent_

📊 *Statistiques:*
• 👥 Utilisateurs: `{stats['total_users']}`
• 💬 Groupes: `{stats['total_groups']}`
• ⚠️ Avertissements: `{stats['total_warnings']}`
• ⏰ Tâches en attente: `{stats['pending_tasks']}`

🔧 *Fonctionnalités:*
✓ Recherche web
✓ Modération avancée
✓ Planification de tâches
✓ Administration complète
✓ Protection de la vie privée

💻 *Développé avec:* Python \+ python\-telegram\-bot
    """

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


# ═══════════════════════════════════════════════════════════════
# COMMANDES DE RECHERCHE WEB
# ═══════════════════════════════════════════════════════════════

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recherche web: /search <requête>"""
    if not context.args:
        await update.message.reply_text(
            "❌ *Usage:* `/search <votre requête>`\n\nExemple: `/search python tutorial`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    query = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Recherche en cours: *{escape_md(query)}*...", parse_mode=ParseMode.MARKDOWN_V2)

    results = await web_search.search(query)

    if not results:
        await msg.edit_text("❌ Aucun résultat trouvé.")
        return

    text = f"🔍 *Résultats pour:* {escape_md(query)}\n\n"
    for i, result in enumerate(results[:5], 1):
        title = escape_md(result.get('title', 'Sans titre'))
        snippet = escape_md(result.get('snippet', '')[:200])
        url = result.get('url', '')
        text += f"{i}\. *{title}*\n📝 {snippet}\n🔗 [Voir plus]({url})\n\n"

    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
    await log_action(update, "search", query)

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recherche d'actualités: /news <sujet>"""
    if not context.args:
        await update.message.reply_text(
            "❌ *Usage:* `/news <sujet>`\n\nExemple: `/news technologie`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    query = " ".join(context.args)
    msg = await update.message.reply_text(f"📰 Recherche d'actualités: *{escape_md(query)}*...", parse_mode=ParseMode.MARKDOWN_V2)

    results = await web_search.search_news(query)

    text = f"📰 *Actualités sur:* {escape_md(query)}\n\n"
    for i, result in enumerate(results[:3], 1):
        title = escape_md(result.get('title', 'Sans titre'))
        snippet = escape_md(result.get('snippet', '')[:200])
        url = result.get('url', '')
        text += f"{i}\. *{title}*\n📝 {snippet}\n🔗 [Lire l'article]({url})\n\n"

    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
    await log_action(update, "news", query)

async def fetch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Extrait le contenu d'une page web: /fetch <url>"""
    if not context.args:
        await update.message.reply_text(
            "❌ *Usage:* `/fetch <url>`\n\nExemple: `/fetch https://example.com`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    url = context.args[0]
    msg = await update.message.reply_text("📥 Extraction du contenu...")

    content = await web_search.fetch_page_content(url)

    # Tronquer si trop long
    if len(content) > 3000:
        content = content[:3000] + "\n\n... _(tronqué)_"

    escaped_content = escape_md(content)
    text = f"📄 *Contenu extrait:*\n\n```{escaped_content}```"

    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "fetch", url)

async def images_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lien de recherche d'images: /images <requête>"""
    if not context.args:
        await update.message.reply_text(
            "❌ *Usage:* `/images <requête>`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    query = " ".join(context.args)
    url = await web_search.search_images(query)

    await update.message.reply_text(
        f"🖼️ *Recherche d'images:* {escape_md(query)}\n\n🔗 [Cliquez ici]({url})",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    await log_action(update, "images", query)



# ═══════════════════════════════════════════════════════════════
# COMMANDES DE MODÉRATION
# ═══════════════════════════════════════════════════════════════

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avertir un membre: /warn @user <raison>"""
    chat = update.effective_chat
    user = update.effective_user

    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur pour utiliser cette commande.")
        return

    if not update.message.reply_to_message and len(context.args) < 1:
        await update.message.reply_text("❌ Usage: `/warn @user <raison>` ou répondez à un message.")
        return

    # Récupérer l'utilisateur cible
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    else:
        username = context.args[0].replace("@", "")
        # Note: En pratique, il faudrait résoudre le username en user_id
        await update.message.reply_text("❌ Veuillez répondre au message de l'utilisateur à avertir.")
        return

    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Aucune raison spécifiée"

    # Ajouter l'avertissement
    await db.add_warning(target.id, chat.id, reason, user.id)
    warning_count = await db.get_warnings(target.id, chat.id)

    # Vérifier si le seuil est atteint
    if warning_count >= Config.MAX_WARNINGS:
        try:
            await chat.ban_member(target.id)
            await update.message.reply_text(
                f"⚠️ {target.mention_html()} a été *banni* après {warning_count} avertissements.\n"
                f"📝 Dernière raison: {reason}",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Impossible de bannir: {str(e)}")
    else:
        await update.message.reply_text(
            f"⚠️ {target.mention_html()} a été averti.\n"
            f"📝 Raison: {reason}\n"
            f"📊 Avertissements: {warning_count}/{Config.MAX_WARNINGS}",
            parse_mode=ParseMode.HTML
        )

    await log_action(update, "warn", f"target={target.id}, reason={reason}")

async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retirer les avertissements: /unwarn @user"""
    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message de l'utilisateur.")
        return

    target = update.message.reply_to_message.from_user
    await db.clear_warnings(target.id, update.effective_chat.id)

    await update.message.reply_text(
        f"✅ Les avertissements de {target.mention_html()} ont été réinitialisés.",
        parse_mode=ParseMode.HTML
    )
    await log_action(update, "unwarn", f"target={target.id}")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rendre muet un membre: /mute @user <durée>"""
    chat = update.effective_chat

    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message de l'utilisateur à rendre muet.")
        return

    target = update.message.reply_to_message.from_user

    # Parse la durée
    duration_str = context.args[0] if context.args else "1h"
    duration_seconds = Config.MUTE_DURATION

    try:
        if duration_str.endswith('h'):
            duration_seconds = int(duration_str[:-1]) * 3600
        elif duration_str.endswith('m'):
            duration_seconds = int(duration_str[:-1]) * 60
        elif duration_str.endswith('d'):
            duration_seconds = int(duration_str[:-1]) * 86400
        else:
            duration_seconds = int(duration_str)
    except ValueError:
        duration_seconds = Config.MUTE_DURATION

    until_date = datetime.now() + timedelta(seconds=duration_seconds)

    try:
        await chat.restrict_member(
            target.id,
            until_date=until_date,
            permissions={
                "can_send_messages": False,
                "can_send_media_messages": False,
                "can_send_other_messages": False,
                "can_add_web_page_previews": False
            }
        )

        duration_text = f"{duration_seconds // 3600}h" if duration_seconds >= 3600 else f"{duration_seconds // 60}m"
        await update.message.reply_text(
            f"🔇 {target.mention_html()} a été rendu muet pour *{duration_text}*.",
            parse_mode=ParseMode.HTML
        )
        await log_action(update, "mute", f"target={target.id}, duration={duration_seconds}s")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Démuet un membre: /unmute @user"""
    chat = update.effective_chat

    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message de l'utilisateur.")
        return

    target = update.message.reply_to_message.from_user

    try:
        await chat.restrict_member(
            target.id,
            permissions={
                "can_send_messages": True,
                "can_send_media_messages": True,
                "can_send_other_messages": True,
                "can_add_web_page_previews": True
            }
        )
        await update.message.reply_text(f"🔊 {target.mention_html()} peut à nouveau parler.", parse_mode=ParseMode.HTML)
        await log_action(update, "unmute", f"target={target.id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bannir un membre: /ban @user <raison>"""
    chat = update.effective_chat

    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message de l'utilisateur à bannir.")
        return

    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Aucune raison spécifiée"

    try:
        await chat.ban_member(target.id)
        await update.message.reply_text(
            f"👢 {target.mention_html()} a été banni.\n📝 Raison: {reason}",
            parse_mode=ParseMode.HTML
        )
        await log_action(update, "ban", f"target={target.id}, reason={reason}")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Débannir un membre: /unban <user_id>"""
    chat = update.effective_chat

    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/unban <user_id>`")
        return

    try:
        user_id = int(context.args[0])
        await chat.unban_member(user_id)
        await update.message.reply_text(f"✅ L'utilisateur `{user_id}` a été débanni.", parse_mode=ParseMode.MARKDOWN_V2)
        await log_action(update, "unban", f"target={user_id}")
    except ValueError:
        await update.message.reply_text("❌ ID invalide.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Expulser un membre: /kick @user"""
    chat = update.effective_chat

    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message de l'utilisateur à expulser.")
        return

    target = update.message.reply_to_message.from_user

    try:
        await chat.ban_member(target.id)
        await chat.unban_member(target.id)  # Unban immédiatement = kick
        await update.message.reply_text(f"👢 {target.mention_html()} a été expulsé.", parse_mode=ParseMode.HTML)
        await log_action(update, "kick", f"target={target.id}")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Informations sur un membre: /info @user"""
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    else:
        target = update.effective_user

    user_data = await db.get_user(target.id)
    warnings = await db.get_warning_history(target.id)

    text = f"""
👤 *Informations sur {escape_md(target.first_name)}*

🆔 ID: `{target.id}`
📛 Nom: {escape_md(target.first_name)} {escape_md(target.last_name or '')}
👤 Username: @{escape_md(target.username or 'N/A')}

📊 *Activité:*
• Avertissements: {len(warnings)}
• Inscription: {user_data['joined_at'] if user_data else 'Inconnu'}

⚠️ *Historique des avertissements:*
"""

    if warnings:
        for w in warnings[:5]:
            text += f"• {w['warned_at']}: {escape_md(w['reason'])}\n"
    else:
        text += "Aucun avertissement\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "info", f"target={target.id}")



# ═══════════════════════════════════════════════════════════════
# COMMANDES DE DIFFUSION (BROADCAST)
# ═══════════════════════════════════════════════════════════════

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Diffusion à tous les utilisateurs: /broadcast <message>"""
    user = update.effective_user

    if not Config.is_admin(user.id):
        await update.message.reply_text("❌ Cette commande est réservée aux super-administrateurs.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/broadcast <votre message>`")
        return

    message = " ".join(context.args)
    users = await db.get_all_users()

    if not users:
        await update.message.reply_text("❌ Aucun utilisateur enregistré.")
        return

    msg = await update.message.reply_text(f"📢 Diffusion en cours vers {len(users)} utilisateurs...")

    sent = 0
    failed = 0

    for user_data in users:
        try:
            await context.bot.send_message(
                chat_id=user_data['user_id'],
                text=f"📢 *Message de l'administrateur*\n\n{escape_md(message)}",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            sent += 1
            await asyncio.sleep(Config.BROADCAST_DELAY)
        except Exception:
            failed += 1

    await msg.edit_text(f"✅ Diffusion terminée!\n📤 Envoyés: {sent}\n❌ Échecs: {failed}")
    await log_action(update, "broadcast", f"sent={sent}, failed={failed}")

# ═══════════════════════════════════════════════════════════════
# COMMANDES DE PLANIFICATION (SCHEDULER)
# ═══════════════════════════════════════════════════════════════

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Planifier une tâche: /schedule"""
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux administrateurs.")
        return

    await update.message.reply_text(
        "⏰ *Planification de tâche*\n\n"
        "Envoyez le message que vous souhaitez planifier.\n"
        "Format: `message | YYYY-MM-DD HH:MM`\n\n"
        "Exemple: `Bonjour tout le monde | 2024-12-25 10:00`",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return SCHEDULE_MSG

async def schedule_msg_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reçoit le message à planifier"""
    text = update.message.text

    if "|" not in text:
        await update.message.reply_text("❌ Format invalide. Utilisez: `message | YYYY-MM-DD HH:MM`")
        return ConversationHandler.END

    parts = text.rsplit("|", 1)
    message = parts[0].strip()
    time_str = parts[1].strip()

    try:
        schedule_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")

        if schedule_time <= datetime.now():
            await update.message.reply_text("❌ La date doit être dans le futur.")
            return ConversationHandler.END

        task_id = await db.add_task(
            "broadcast",
            update.effective_chat.id,
            message,
            schedule_time
        )

        await update.message.reply_text(
            f"✅ Tâche planifiée!\n"
            f"🆔 ID: `{task_id}`\n"
            f"📅 Date: {schedule_time.strftime('%d/%m/%Y %H:%M')}\n"
            f"💬 Message: {escape_md(message[:100])}...",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        await log_action(update, "schedule", f"task_id={task_id}")

    except ValueError:
        await update.message.reply_text("❌ Format de date invalide. Utilisez: `YYYY-MM-DD HH:MM`")

    return ConversationHandler.END

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Voir les tâches planifiées: /tasks"""
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux administrateurs.")
        return

    tasks = await db.get_all_tasks()

    if not tasks:
        await update.message.reply_text("📋 Aucune tâche planifiée.")
        return

    text = "📋 *Tâches planifiées:*\n\n"
    for task in tasks[:10]:
        status_emoji = "⏳" if task['status'] == 'pending' else "✅" if task['status'] == 'executed' else "❌"
        text += f"{status_emoji} ID: `{task['id']}` | {task['task_type']}\n"
        text += f"   📅 {task['schedule_time']} | Status: {task['status']}\n"
        text += f"   💬 {escape_md(task['content'][:50])}...\n\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "tasks")

async def cancel_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annuler une tâche: /cancel <id>"""
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux administrateurs.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/cancel <task_id>`")
        return

    try:
        task_id = int(context.args[0])
        await db.cancel_task(task_id)
        await update.message.reply_text(f"✅ Tâche `{task_id}` annulée.", parse_mode=ParseMode.MARKDOWN_V2)
        await log_action(update, "cancel_task", f"task_id={task_id}")
    except ValueError:
        await update.message.reply_text("❌ ID invalide.")

# ═══════════════════════════════════════════════════════════════
# COMMANDES DE FILTRES
# ═══════════════════════════════════════════════════════════════

async def filters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Voir les filtres actifs: /filters"""
    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    filters_list = moderation.get_filters()

    if not filters_list:
        await update.message.reply_text("📋 Aucun filtre actif.")
        return

    text = "📋 *Filtres actifs:*\n\n"
    for i, f in enumerate(filters_list, 1):
        text += f"{i}\. `{escape_md(f)}`\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "filters")

async def addfilter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajouter un filtre: /addfilter <mot>"""
    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/addfilter <mot>`")
        return

    word = " ".join(context.args).lower()
    moderation.add_custom_filter(word)

    await update.message.reply_text(f"✅ Filtre ajouté: `{escape_md(word)}`", parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "addfilter", word)

async def delfilter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retirer un filtre: /delfilter <mot>"""
    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/delfilter <mot>`")
        return

    word = " ".join(context.args).lower()
    moderation.remove_custom_filter(word)

    await update.message.reply_text(f"✅ Filtre retiré: `{escape_md(word)}`", parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "delfilter", word)

# ═══════════════════════════════════════════════════════════════
# COMMANDES DE RÈGLES
# ═══════════════════════════════════════════════════════════════

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Afficher les règles du groupe: /rules"""
    chat = update.effective_chat

    if chat.type == "private":
        await update.message.reply_text("❌ Cette commande fonctionne uniquement dans les groupes.")
        return

    rules = await db.get_group_rules(chat.id)

    if not rules:
        await update.message.reply_text(
            "📜 Aucune règle définie pour ce groupe.\n"
            "Les administrateurs peuvent définir des règles avec `/setrules`."
        )
        return

    await update.message.reply_text(f"📜 *Règles du groupe:*\n\n{escape_md(rules)}", parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "rules")

async def setrules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Définir les règles: /setrules <règles>"""
    chat = update.effective_chat

    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: `/setrules <vos règles>`")
        return

    rules = " ".join(context.args)
    await db.set_group_rules(chat.id, rules)

    await update.message.reply_text("✅ Les règles du groupe ont été mises à jour.")
    await log_action(update, "setrules")



# ═══════════════════════════════════════════════════════════════
# COMMANDES D'ADMINISTRATION
# ═══════════════════════════════════════════════════════════════

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistiques du bot: /stats"""
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux super-administrateurs.")
        return

    stats = await db.get_stats()

    text = f"""
📊 *STATISTIQUES DU BOT*

👥 *Utilisateurs:* `{stats['total_users']}`
💬 *Groupes:* `{stats['total_groups']}`
⚠️ *Avertissements:* `{stats['total_warnings']}`
⏰ *Tâches en attente:* `{stats['pending_tasks']}`
📝 *Logs totaux:* `{stats['total_logs']}`

🔧 *État du bot:* ✅ En ligne
📅 *Date actuelle:* {datetime.now().strftime('%d/%m/%Y %H:%M')}
    """

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "stats")

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liste des utilisateurs: /users"""
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux super-administrateurs.")
        return

    users = await db.get_all_users()

    if not users:
        await update.message.reply_text("📋 Aucun utilisateur.")
        return

    text = f"📋 *Utilisateurs ({len(users)}):*\n\n"
    for u in users[:20]:
        name = escape_md(u['first_name'] or 'Inconnu')
        username = f"@{escape_md(u['username'])}" if u['username'] else "N/A"
        text += f"• `{u['user_id']}` | {name} | {username}\n"

    if len(users) > 20:
        text += f"\n... et {len(users) - 20} autres"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "users")

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Derniers logs: /logs"""
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux super-administrateurs.")
        return

    logs = await db.get_recent_logs(20)

    if not logs:
        await update.message.reply_text("📋 Aucun log.")
        return

    text = "📋 *Derniers logs:*\n\n"
    for log in logs:
        text += f"`{log['timestamp']}` | {escape_md(log['action'])} | {escape_md(log['details'][:50])}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "logs")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paramètres du groupe: /settings"""
    chat = update.effective_chat

    if chat.type == "private":
        await update.message.reply_text("❌ Cette commande fonctionne uniquement dans les groupes.")
        return

    if not await is_admin_or_owner(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return

    settings = await db.get_group_settings(chat.id)

    keyboard = [
        [InlineKeyboardButton("🤖 Modération auto: " + ("ON ✅" if settings.get("auto_moderation") else "OFF ❌"), callback_data="toggle_auto_mod")],
        [InlineKeyboardButton("👋 Message de bienvenue: " + ("ON ✅" if settings.get("welcome_msg") else "OFF ❌"), callback_data="toggle_welcome")],
        [InlineKeyboardButton("🔗 Anti-liens: " + ("ON ✅" if settings.get("anti_links") else "OFF ❌"), callback_data="toggle_anti_links")],
        [InlineKeyboardButton("🖼️ Anti-spam: " + ("ON ✅" if settings.get("anti_spam") else "OFF ❌"), callback_data="toggle_anti_spam")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ *Paramètres du groupe:*\n\n"
        "Cliquez sur les boutons pour activer/désactiver.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=reply_markup
    )
    await log_action(update, "settings")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les callbacks des boutons inline"""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    settings = await db.get_group_settings(chat_id)

    if query.data == "toggle_auto_mod":
        settings["auto_moderation"] = not settings.get("auto_moderation", False)
        status = "activée ✅" if settings["auto_moderation"] else "désactivée ❌"
        await query.edit_message_text(f"🤖 Modération auto {status}")

    elif query.data == "toggle_welcome":
        settings["welcome_msg"] = not settings.get("welcome_msg", False)
        status = "activée ✅" if settings["welcome_msg"] else "désactivée ❌"
        await query.edit_message_text(f"👋 Message de bienvenue {status}")

    elif query.data == "toggle_anti_links":
        settings["anti_links"] = not settings.get("anti_links", False)
        status = "activée ✅" if settings["anti_links"] else "désactivée ❌"
        await query.edit_message_text(f"🔗 Anti-liens {status}")

    elif query.data == "toggle_anti_spam":
        settings["anti_spam"] = not settings.get("anti_spam", False)
        status = "activée ✅" if settings["anti_spam"] else "désactivée ❌"
        await query.edit_message_text(f"🖼️ Anti-spam {status}")

    await db.update_group_settings(chat_id, settings)

# ═══════════════════════════════════════════════════════════════
# COMMANDES DE CONFIDENTIALITÉ
# ═══════════════════════════════════════════════════════════════

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Politique de confidentialité: /privacy"""
    text = """
🔒 *POLITIQUE DE CONFIDENTIALITÉ*

*Données collectées:*
• ID Telegram, nom d'utilisateur
• Messages dans les groupes (pour modération)
• Logs d'activité (commandes utilisées)

*Utilisation:*
• Fonctionnement du bot
• Modération des groupes
• Statistiques anonymisées

*Durée de conservation:*
• Données utilisateur: jusqu'à suppression manuelle
• Logs: 90 jours

*Vos droits:*
• `/export_data` \- Exporter vos données
• `/delete_my_data` \- Supprimer vos données

*Contact:* Contactez un administrateur pour toute question.
    """

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "privacy")

async def export_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exporter les données de l'utilisateur: /export_data"""
    user = update.effective_user
    user_data = await db.get_user(user.id)
    warnings = await db.get_warning_history(user.id)

    if not user_data:
        await update.message.reply_text("❌ Aucune donnée trouvée.")
        return

    data = {
        "user_id": user_data['user_id'],
        "username": user_data['username'],
        "first_name": user_data['first_name'],
        "last_name": user_data['last_name'],
        "joined_at": user_data['joined_at'],
        "last_activity": user_data['last_activity'],
        "warnings_count": len(warnings),
        "warnings_history": warnings[:10]
    }

    json_data = json.dumps(data, indent=2, default=str)

    await update.message.reply_text(
        f"📤 *Vos données:*\n\n```json\n{escape_md(json_data[:3000])}\n```",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    await log_action(update, "export_data")

async def delete_my_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Supprimer les données de l'utilisateur: /delete_my_data"""
    user = update.effective_user

    keyboard = [
        [InlineKeyboardButton("✅ Oui, supprimer", callback_data=f"confirm_delete_{user.id}")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cancel_delete")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚠️ *Êtes-vous sûr de vouloir supprimer toutes vos données ?*\n\n"
        "Cette action est irréversible.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=reply_markup
    )
    await log_action(update, "delete_data_request")

async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la confirmation de suppression"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_delete":
        await query.edit_message_text("✅ Suppression annulée.")
        return

    if query.data.startswith("confirm_delete_"):
        user_id = int(query.data.split("_")[-1])
        if user_id == update.effective_user.id:
            await db.block_user(user_id)
            await query.edit_message_text("✅ Vos données ont été supprimées. Vous ne recevrez plus de messages du bot.")
            await log_action(update, "delete_data_confirmed")



# ═══════════════════════════════════════════════════════════════
# HANDLERS DE MESSAGES (MODÉRATION AUTO, BIENVENUE, ETC.)
# ═══════════════════════════════════════════════════════════════

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère l'arrivée de nouveaux membres"""
    chat = update.effective_chat

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue

        # Enregistre l'utilisateur
        await db.add_user(member.id, member.username, member.first_name, member.last_name or "")

        # Message de bienvenue si activé
        settings = await db.get_group_settings(chat.id)
        if settings.get("welcome_msg"):
            welcome_text = settings.get("custom_welcome", 
                f"👋 Bienvenue, {member.mention_html()}!\n"
                f"📜 N'oubliez pas de consulter les règles avec /rules"
            )
            await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

        await log_action(update, "new_member", f"user={member.id}")

async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le départ d'un membre"""
    member = update.message.left_chat_member
    if member and not member.is_bot:
        await log_action(update, "left_member", f"user={member.id}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère tous les messages pour la modération automatique"""
    if not update.message or not update.message.text:
        return

    chat = update.effective_chat
    user = update.effective_user
    text = update.message.text

    # Ignore les messages privés pour la modération auto
    if chat.type == "private":
        return

    # Vérifie les paramètres du groupe
    settings = await db.get_group_settings(chat.id)

    # Anti-liens
    if settings.get("anti_links"):
        if "http://" in text or "https://" in text or "t.me/" in text:
            try:
                await update.message.delete()
                await db.log_filtered_message(user.id, chat.id, text, "link", "deleted")
                await update.message.reply_text(
                    f"🔗 {user.mention_html()}, les liens ne sont pas autorisés ici.",
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception:
                pass

    # Modération automatique
    if settings.get("auto_moderation"):
        check_result = moderation.check_message(text, user.id)

        if not check_result["is_clean"]:
            warning_count = await db.get_warnings(user.id, chat.id)
            action = moderation.get_recommended_action(check_result, warning_count)

            if action == "delete":
                try:
                    await update.message.delete()
                    await db.log_filtered_message(user.id, chat.id, text, "auto_mod", "deleted")
                except Exception:
                    pass

            elif action == "warn":
                await db.add_warning(user.id, chat.id, "Modération automatique", 0)
                new_count = await db.get_warnings(user.id, chat.id)
                await update.message.reply_text(
                    f"⚠️ {user.mention_html()}, votre message a été signalé.\n"
                    f"Avertissements: {new_count}/{Config.MAX_WARNINGS}",
                    parse_mode=ParseMode.HTML
                )

            elif action == "mute":
                try:
                    until = datetime.now() + timedelta(seconds=Config.MUTE_DURATION)
                    await chat.restrict_member(user.id, until_date=until, permissions={
                        "can_send_messages": False,
                        "can_send_media_messages": False,
                        "can_send_other_messages": False
                    })
                    await update.message.reply_text(
                        f"🔇 {user.mention_html()} a été rendu muet pour comportement inapproprié.",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

            elif action == "ban":
                try:
                    await chat.ban_member(user.id)
                    await update.message.reply_text(
                        f"👢 {user.mention_html()} a été banni pour comportement inapproprié.",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

# ═══════════════════════════════════════════════════════════════
# SCHEDULER DE TÂCHES (Exécution périodique)
# ═══════════════════════════════════════════════════════════════

async def check_scheduled_tasks(context: ContextTypes.DEFAULT_TYPE):
    """Vérifie et exécute les tâches planifiées"""
    try:
        tasks = await db.get_pending_tasks()

        for task in tasks:
            try:
                if task['task_type'] == 'broadcast':
                    users = await db.get_all_users()
                    for user_data in users:
                        try:
                            await context.bot.send_message(
                                chat_id=user_data['user_id'],
                                text=f"⏰ *Message planifié*\n\n{escape_md(task['content'])}",
                                parse_mode=ParseMode.MARKDOWN_V2
                            )
                            await asyncio.sleep(Config.BROADCAST_DELAY)
                        except Exception:
                            pass

                elif task['task_type'] == 'group_message':
                    await context.bot.send_message(
                        chat_id=task['target_id'],
                        text=task['content']
                    )

                await db.mark_task_executed(task['id'])
                logger.info(f"Tâche {task['id']} exécutée avec succès")

            except Exception as e:
                logger.error(f"Erreur exécution tâche {task['id']}: {e}")

    except Exception as e:
        logger.error(f"Erreur scheduler: {e}")

# ═══════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE
# ═══════════════════════════════════════════════════════════════

async def post_init(application: Application):
    """Initialisation après démarrage du bot"""
    logger.info("Initialisation de la base de données...")
    await db.init()
    logger.info("Base de données initialisée!")

    # Démarre le scheduler de tâches
    application.job_queue.run_repeating(check_scheduled_tasks, interval=60, first=10)
    logger.info("Scheduler de tâches démarré!")

def main():
    """Point d'entrée principal"""

    # Vérifie le token
    if Config.BOT_TOKEN == "TON_TOKEN_ICI" or not Config.BOT_TOKEN:
        logger.error("❌ ERREUR: Veuillez définir BOT_TOKEN dans le fichier .env")
        sys.exit(1)

    logger.info("🚀 Démarrage d'UltraBot v2.0...")

    # Crée l'application
    application = Application.builder().token(Config.BOT_TOKEN).post_init(post_init).build()

    # ═══════════════════════════════════════════════════════════
    # ENREGISTREMENT DES HANDLERS
    # ═══════════════════════════════════════════════════════════

    # Commandes de base
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("about", about_command))

    # Recherche web
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("news", news_command))
    application.add_handler(CommandHandler("fetch", fetch_command))
    application.add_handler(CommandHandler("images", images_command))

    # Modération
    application.add_handler(CommandHandler("warn", warn_command))
    application.add_handler(CommandHandler("unwarn", unwarn_command))
    application.add_handler(CommandHandler("mute", mute_command))
    application.add_handler(CommandHandler("unmute", unmute_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("kick", kick_command))
    application.add_handler(CommandHandler("info", info_command))

    # Diffusion
    application.add_handler(CommandHandler("broadcast", broadcast_command))

    # Planification (ConversationHandler)
    schedule_conv = ConversationHandler(
        entry_points=[CommandHandler("schedule", schedule_command)],
        states={
            SCHEDULE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_msg_received)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: u.message.reply_text("Annulé."))]
    )
    application.add_handler(schedule_conv)
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CommandHandler("cancel", cancel_task_command))

    # Filtres
    application.add_handler(CommandHandler("filters", filters_command))
    application.add_handler(CommandHandler("addfilter", addfilter_command))
    application.add_handler(CommandHandler("delfilter", delfilter_command))

    # Règles
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("setrules", setrules_command))

    # Administration
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("settings", settings_command))

    # Confidentialité
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(CommandHandler("export_data", export_data_command))
    application.add_handler(CommandHandler("delete_my_data", delete_my_data_command))

    # Callbacks (boutons inline)
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^toggle_"))
    application.add_handler(CallbackQueryHandler(delete_callback, pattern="^(confirm_delete_|cancel_delete)"))

    # Événements de groupe
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_left_member))

    # Messages (modération auto)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ═══════════════════════════════════════════════════════════
    # DÉMARRAGE DU BOT
    # ═══════════════════════════════════════════════════════════

    logger.info("✅ Bot démarré et en écoute!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
