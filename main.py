#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
  🤖 SHADYBOT TELEGRAM - Version Render Stable
═══════════════════════════════════════════════════════════════
"""

import asyncio
import logging
import os
import sys
import signal
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
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
from ai_assistant import AIAssistant
from moderation import ModerationEngine

# ─── LOGS ─────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ─── MODULES ──────────────────────────────────────────────────
db = Database()
web_search = WebSearch()
ai_assistant = AIAssistant()
moderation = ModerationEngine()

# ─── ÉTAT EN MÉMOIRE (anti-flood & captcha) ─────────────────────
# Volontairement non persisté en base : ce sont des états très courts
# (quelques secondes à quelques minutes), pas besoin de survivre à un
# redémarrage, et ça évite une écriture DB à chaque message.
flood_tracker = {}    # {(chat_id, user_id): [timestamps des derniers messages]}
pending_captcha = {}  # {(chat_id, user_id): message_id du bouton de vérification}
message_history = {}  # {chat_id: deque des 200 derniers messages, pour /resume}

# ─── SERVEUR DE HEALTH CHECK (requis par Render en mode Web Service) ──
# Render sonde régulièrement le port de service pour vérifier qu'il est
# vivant. Sans réponse HTTP, Render pense le service mort et en relance
# un second en parallèle -> les deux instances font getUpdates() sur le
# même token -> telegram.error.Conflict. Ce petit serveur (dans un thread
# séparé, indépendant de la boucle asyncio du bot) répond juste "OK" pour
# que Render ne redémarre jamais une deuxième instance inutilement.
class _HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ShadyBot is running")

    def log_message(self, format, *args):
        pass  # Ne pas polluer les logs avec chaque requete de health check

def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthCheckHandler)
    server.serve_forever()

# États conversation
SCHEDULE_MSG = 0

# ─── UTILITAIRES ──────────────────────────────────────────────
def escape_md(text: str) -> str:
    if not text:
        return ""
    chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for c in chars:
        text = text.replace(c, f"\\{c}")
    return text

async def is_admin_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat or update.effective_chat.type == "private":
        return True
    try:
        member = await update.effective_chat.get_member(update.effective_user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False

async def log_action(update: Update, action: str, details: str = ""):
    uid = update.effective_user.id if update.effective_user else 0
    cid = update.effective_chat.id if update.effective_chat else 0
    try:
        await db.log_activity(uid, cid, action, details)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# COMMANDES DE BASE
# ═══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.add_user(user.id, user.username, user.first_name, user.last_name or "")
    text = (
        f"👋 *Bienvenue, {escape_md(user.first_name)}\!*\n\n"
        f"Je suis 🤖 *ShadyBot*, votre assistant intelligent\.\n\n"
        f"📋 *Commandes disponibles\:*\n"
        f"🔍 `/search <requête>` \- Recherche web\n"
        f"📰 `/news <sujet>` \- Actualités\n"
        f"🧠 `/ai <question>` \- Assistant IA\n"
        f"📢 `/broadcast <message>` \- Diffusion \(admin\)\n"
        f"⏰ `/schedule` \- Planifier une tâche\n"
        f"⚠️ `/warn` \- Avertir un membre\n"
        f"🔇 `/mute` \- Rendre muet\n"
        f"👢 `/ban` \- Bannir\n"
        f"📜 `/rules` \- Règles du groupe\n"
        f"📊 `/stats` \- Statistiques\n"
        f"⚙️ `/settings` \- Paramètres\n"
        f"❓ `/help` \- Aide complète\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "start")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *AIDE COMPLÈTE DE SHADYBOT*\n\n"
        "*🔍 RECHERCHE WEB*\n"
        "`/search <requête>` \- Recherche sur le web\n"
        "`/news <sujet>` \- Rechercher des actualités\n"
        "`/fetch <url>` \- Extraire le contenu d\'une page\n"
        "`/images <requête>` \- Lien recherche d\'images\n\n"
        "*🧠 ASSISTANT IA*\n"
        "`/ai <question>` \- Poser une question à l\'IA\n"
        "`/resume` \- Résumer les derniers messages du groupe\n\n"
        "*👥 MODÉRATION*\n"
        "`/warn` \- Donner un avertissement \(répondre à un msg\)\n"
        "`/unwarn` \- Retirer les avertissements\n"
        "`/mute <durée>` \- Muet \(ex\: 1h, 30m\)\n"
        "`/unmute` \- Démuet\n"
        "`/ban <raison>` \- Bannir\n"
        "`/unban <user_id>` \- Débannir\n"
        "`/kick` \- Expulser\n"
        "`/info` \- Informations sur un membre\n\n"
        "*📢 DIFFUSION \& TÂCHES*\n"
        "`/broadcast <message>` \- Diffuser à tous\n"
        "`/schedule` \- Planifier un message\n"
        "`/tasks` \- Voir les tâches planifiées\n"
        "`/cancel <id>` \- Annuler une tâche\n\n"
        "*⚙️ ADMINISTRATION*\n"
        "`/stats` \- Statistiques\n"
        "`/users` \- Liste des utilisateurs\n"
        "`/logs` \- Derniers logs\n"
        "`/settings` \- Paramètres du groupe\n"
        "`/setrules <règles>` \- Définir les règles\n"
        "`/filters` \- Voir les filtres\n"
        "`/addfilter <mot>` \- Ajouter un filtre\n"
        "`/delfilter <mot>` \- Retirer un filtre\n\n"
        "*🔒 CONFIDENTIALITÉ*\n"
        "`/privacy` \- Politique de confidentialité\n"
        "`/export_data` \- Exporter mes données\n"
        "`/delete_my_data` \- Supprimer mes données\n\n"
        "*ℹ️ AUTRES*\n"
        "`/id` \- Votre ID Telegram\n"
        "`/ping` \- Vérifier la latence\n"
        "`/about` \- À propos du bot"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "help")

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = datetime.now()
    msg = await update.message.reply_text("🏓 Pong\! Calcul\.")
    latency = (datetime.now() - start).total_seconds() * 1000
    await msg.edit_text(f"🏓 *Pong\!*\n\n⚡ Latence\: `{latency:.0f}ms`", parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    c = update.effective_chat
    text = (
        f"🆔 *Informations d\'identification*\n\n"
        f"👤 *Utilisateur\:*\n"
        f"• ID\: `{u.id}`\n"
        f"• Nom\: {escape_md(u.first_name)}\n"
        f"• Username\: @{escape_md(u.username or 'N/A')}\n\n"
        f"💬 *Chat\:*\n"
        f"• ID\: `{c.id}`\n"
        f"• Type\: {escape_md(c.type)}\n"
        f"• Titre\: {escape_md(c.title or 'N/A')}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await db.get_stats()
    text = (
        f"🤖 *ShadyBot v2\.0*\n\n"
        f"_Un bot Telegram intelligent et polyvalent_\n\n"
        f"📊 *Statistiques\:*\n"
        f"• 👥 Utilisateurs\: `{stats['total_users']}`\n"
        f"• 💬 Groupes\: `{stats['total_groups']}`\n"
        f"• ⚠️ Avertissements\: `{stats['total_warnings']}`\n"
        f"• ⏰ Tâches en attente\: `{stats['pending_tasks']}`\n\n"
        f"🔧 *Fonctionnalités\:*\n"
        f"✓ Recherche web\n"
        f"✓ Modération avancée\n"
        f"✓ Planification de tâches\n"
        f"✓ Administration complète\n"
        f"✓ Protection de la vie privée"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

# ═══════════════════════════════════════════════════════════════
# RECHERCHE WEB
# ═══════════════════════════════════════════════════════════════

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/search <votre requête>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    query = " ".join(context.args)
    msg = await update.message.reply_text("🔍 Recherche en cours\.", parse_mode=ParseMode.MARKDOWN_V2)
    results = await web_search.search(query)
    text = f"🔍 *Résultats pour\:* {escape_md(query)}\n\n"
    for i, r in enumerate(results[:5], 1):
        title = escape_md(r.get('title', 'Sans titre'))
        snippet = escape_md(r.get('snippet', '')[:200])
        url = r.get('url', '')
        text += f"{i}\. *{title}*\n📝 {snippet}\n🔗 [Voir plus]({url})\n\n"
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
    await log_action(update, "search", query)

async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/news <sujet>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    query = " ".join(context.args)
    msg = await update.message.reply_text("📰 Recherche d\'actualités\.", parse_mode=ParseMode.MARKDOWN_V2)
    results = await web_search.search_news(query)
    text = f"📰 *Actualités sur\:* {escape_md(query)}\n\n"
    for i, r in enumerate(results[:3], 1):
        title = escape_md(r.get('title', 'Sans titre'))
        snippet = escape_md(r.get('snippet', '')[:200])
        url = r.get('url', '')
        text += f"{i}\. *{title}*\n📝 {snippet}\n🔗 [Lire]({url})\n\n"
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
    await log_action(update, "news", query)

async def cmd_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/fetch <url>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    url = context.args[0]
    msg = await update.message.reply_text("📥 Extraction\.")
    content = await web_search.fetch_page_content(url)
    if len(content) > 3000:
        content = content[:3000] + "\n\n\."
    text = f"📄 *Contenu extrait\:*\n\n```\n{escape_md(content)}\n```"
    await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "fetch", url)

async def cmd_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/images <requête>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    query = " ".join(context.args)
    url = await web_search.search_images(query)
    await update.message.reply_text(f"🖼️ *Recherche d\'images\:* {escape_md(query)}\n\n🔗 [Cliquez ici]({url})", parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "images", query)

# ═══════════════════════════════════════════════════════════════
# ASSISTANT IA
# ═══════════════════════════════════════════════════════════════

async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /ai <votre question>")
        return
    question = " ".join(context.args)
    msg = await update.message.reply_text("🧠 Réflexion en cours...")
    answer = await ai_assistant.ask(question)
    await msg.edit_text(f"🧠 {answer[:3900]}")
    await log_action(update, "ai_ask", question[:100])

async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("❌ Uniquement dans les groupes.")
        return
    history = list(message_history.get(chat.id, []))
    if len(history) < 5:
        await update.message.reply_text("Pas encore assez de messages récents à résumer.")
        return
    msg = await update.message.reply_text("🧠 Résumé en cours...")
    summary = await ai_assistant.summarize_messages(history[-100:])
    await msg.edit_text(f"📋 Résumé des derniers messages\n\n{summary[:3900]}")
    await log_action(update, "ai_resume")

# ═══════════════════════════════════════════════════════════════
# MODÉRATION
# ═══════════════════════════════════════════════════════════════

async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Vous devez être administrateur.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message de l\'utilisateur à avertir.")
        return
    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Aucune raison"
    await db.add_warning(target.id, chat.id, reason, user.id)
    count = await db.get_warnings(target.id, chat.id)
    if count >= Config.MAX_WARNINGS:
        try:
            await chat.ban_member(target.id)
            await update.message.reply_text(f"⚠️ {target.mention_html()} a été *banni* après {count} avertissements.", parse_mode=ParseMode.HTML)
        except Exception as e:
            await update.message.reply_text(f"❌ Impossible de bannir\: {e}")
    else:
        await update.message.reply_text(f"⚠️ {target.mention_html()} averti\.", parse_mode=ParseMode.HTML)
    await log_action(update, "warn", f"target={target.id}")

async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message.")
        return
    target = update.message.reply_to_message.from_user
    await db.clear_warnings(target.id, update.effective_chat.id)
    await update.message.reply_text(f"✅ Avertissements de {target.mention_html()} réinitialisés.", parse_mode=ParseMode.HTML)
    await log_action(update, "unwarn", f"target={target.id}")

async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message.")
        return
    target = update.message.reply_to_message.from_user
    dur_str = context.args[0] if context.args else "1h"
    secs = Config.MUTE_DURATION
    try:
        if dur_str.endswith('h'): secs = int(dur_str[:-1]) * 3600
        elif dur_str.endswith('m'): secs = int(dur_str[:-1]) * 60
        elif dur_str.endswith('d'): secs = int(dur_str[:-1]) * 86400
        else: secs = int(dur_str)
    except ValueError:
        secs = Config.MUTE_DURATION
    until = datetime.now() + timedelta(seconds=secs)
    try:
        await chat.restrict_member(target.id, until_date=until, permissions=ChatPermissions(can_send_messages=False, can_send_polls=False, can_send_other_messages=False, can_add_web_page_previews=False))
        dtxt = f"{secs//3600}h" if secs >= 3600 else f"{secs//60}m"
        await update.message.reply_text(f"🔇 {target.mention_html()} muet pour *{dtxt}*.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur\: {e}")
    await log_action(update, "mute", f"target={target.id}, dur={secs}")

async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message.")
        return
    target = update.message.reply_to_message.from_user
    try:
        await chat.restrict_member(target.id, permissions=ChatPermissions(can_send_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
        await update.message.reply_text(f"🔊 {target.mention_html()} peut parler.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur\: {e}")
    await log_action(update, "unmute", f"target={target.id}")

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message.")
        return
    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Aucune raison"
    try:
        await chat.ban_member(target.id)
        await update.message.reply_text(f"👢 {target.mention_html()} banni\.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur\: {e}")
    await log_action(update, "ban", f"target={target.id}, reason={reason}")

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/unban <user_id>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    try:
        uid = int(context.args[0])
        await chat.unban_member(uid)
        await update.message.reply_text(f"✅ Utilisateur `{uid}` débanni.", parse_mode=ParseMode.MARKDOWN_V2)
    except ValueError:
        await update.message.reply_text("❌ ID invalide.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur\: {e}")
    await log_action(update, "unban", f"target={context.args[0] if context.args else 'none'}")

async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Répondez au message.")
        return
    target = update.message.reply_to_message.from_user
    try:
        await chat.ban_member(target.id)
        await chat.unban_member(target.id)
        await update.message.reply_text(f"👢 {target.mention_html()} expulsé.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur\: {e}")
    await log_action(update, "kick", f"target={target.id}")

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    else:
        target = update.effective_user
    user_data = await db.get_user(target.id)
    warnings = await db.get_warning_history(target.id)
    text = f"👤 *{escape_md(target.first_name)}*\n\n🆔 ID\: `{target.id}`\n📛 Nom\: {escape_md(target.first_name)} {escape_md(target.last_name or '')}\n👤 Username\: @{escape_md(target.username or 'N/A')}\n\n📊 *Activité\:*\n• Avertissements\: {len(warnings)}\n"
    if user_data:
        text += f"• Inscription\: {user_data['joined_at']}\n"
    text += "\n⚠️ *Historique\:*\n"
    if warnings:
        for w in warnings[:5]:
            text += f"• {w['warned_at']}\: {escape_md(w['reason'])}\n"
    else:
        text += "Aucun\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

# ═══════════════════════════════════════════════════════════════
# DIFFUSION
# ═══════════════════════════════════════════════════════════════

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not Config.is_admin(user.id):
        await update.message.reply_text("❌ Réservé aux super\-admins.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/broadcast <message>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    message = " ".join(context.args)
    users = await db.get_all_users()
    if not users:
        await update.message.reply_text("❌ Aucun utilisateur.")
        return
    msg = await update.message.reply_text(f"📢 Diffusion vers {len(users)} utilisateurs\.")
    sent = failed = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u['user_id'], text=f"📢 *Message admin*\n\n{escape_md(message)}", parse_mode=ParseMode.MARKDOWN_V2)
            sent += 1
            await asyncio.sleep(Config.BROADCAST_DELAY)
        except Exception:
            failed += 1
    await msg.edit_text(f"✅ Terminé\!\n📤 Envoyés\: {sent}\n❌ Échecs\: {failed}")
    await log_action(update, "broadcast", f"sent={sent}, failed={failed}")

# ═══════════════════════════════════════════════════════════════
# PLANIFICATION
# ═══════════════════════════════════════════════════════════════

async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux admins.")
        return
    await update.message.reply_text(
        "⏰ *Planification*\n\nEnvoyez\: `message | YYYY\-MM\-DD HH\:MM`\nExemple\: `Bonjour | 2026\-08\-25 10\:00`",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return SCHEDULE_MSG

async def schedule_msg_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "|" not in text:
        await update.message.reply_text("❌ Format invalide. Utilisez\: `message | YYYY\-MM\-DD HH\:MM`", parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END
    parts = text.rsplit("|", 1)
    message = parts[0].strip()
    time_str = parts[1].strip()
    try:
        schedule_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        if schedule_time <= datetime.now():
            await update.message.reply_text("❌ La date doit être dans le futur.")
            return ConversationHandler.END
        task_id = await db.add_task("broadcast", update.effective_chat.id, message, schedule_time)
        await update.message.reply_text(f"✅ Tâche `{task_id}` planifiée pour {schedule_time.strftime('%d/%m/%Y %H:%M')}\.", parse_mode=ParseMode.MARKDOWN_V2)
        await log_action(update, "schedule", f"task_id={task_id}")
    except ValueError:
        await update.message.reply_text("❌ Date invalide. Format\: `YYYY\-MM\-DD HH\:MM`", parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux admins.")
        return
    tasks = await db.get_all_tasks()
    if not tasks:
        await update.message.reply_text("📋 Aucune tâche.")
        return
    text = "📋 *Tâches\:*\n\n"
    for t in tasks[:10]:
        emoji = "⏳" if t['status'] == 'pending' else "✅" if t['status'] == 'executed' else "❌"
        text += f"{emoji} ID\: `{t['id']}` | {t['task_type']} | {t['status']}\n📅 {t['schedule_time']}\n💬 {escape_md(t['content'][:50])}...\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_cancel_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux admins.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/cancel <task_id>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    try:
        tid = int(context.args[0])
        await db.cancel_task(tid)
        await update.message.reply_text(f"✅ Tâche `{tid}` annulée.", parse_mode=ParseMode.MARKDOWN_V2)
        await log_action(update, "cancel_task", f"task_id={tid}")
    except ValueError:
        await update.message.reply_text("❌ ID invalide.")

# ═══════════════════════════════════════════════════════════════
# FILTRES
# ═══════════════════════════════════════════════════════════════

async def cmd_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    flist = moderation.get_filters()
    if not flist:
        await update.message.reply_text("📋 Aucun filtre.")
        return
    text = "📋 *Filtres actifs\:*\n\n"
    for i, f in enumerate(flist, 1):
        text += f"{i}\. `{escape_md(f)}`\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

async def cmd_addfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/addfilter <mot>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    word = " ".join(context.args).lower()
    moderation.add_custom_filter(word)
    await update.message.reply_text(f"✅ Filtre ajouté\: `{escape_md(word)}`", parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "addfilter", word)

async def cmd_delfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/delfilter <mot>`", parse_mode=ParseMode.MARKDOWN_V2)
        return
    word = " ".join(context.args).lower()
    moderation.remove_custom_filter(word)
    await update.message.reply_text(f"✅ Filtre retiré\: `{escape_md(word)}`", parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "delfilter", word)

# ═══════════════════════════════════════════════════════════════
# RÈGLES
# ═══════════════════════════════════════════════════════════════

async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("❌ Uniquement dans les groupes.")
        return
    rules = await db.get_group_rules(chat.id)
    if not rules:
        await update.message.reply_text("📜 Aucune règle définie. Admins\: `/setrules <règles>`")
        return
    await update.message.reply_text(f"📜 *Règles du groupe\:*\n\n{escape_md(rules)}", parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "rules")

async def cmd_setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage\: `/setrules <vos règles>`")
        return
    rules = " ".join(context.args)
    await db.set_group_rules(chat.id, rules)
    await update.message.reply_text("✅ Règles mises à jour.")
    await log_action(update, "setrules")

# ═══════════════════════════════════════════════════════════════
# ADMINISTRATION
# ═══════════════════════════════════════════════════════════════

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux super\-admins.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    stats = await db.get_stats()
    text = (
        f"📊 *STATISTIQUES*\n\n"
        f"👥 Utilisateurs\: `{stats['total_users']}`\n"
        f"💬 Groupes\: `{stats['total_groups']}`\n"
        f"⚠️ Avertissements\: `{stats['total_warnings']}`\n"
        f"⏰ Tâches en attente\: `{stats['pending_tasks']}`\n"
        f"📝 Logs\: `{stats['total_logs']}`\n\n"
        f"✅ Bot en ligne\n"
        f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "stats")

async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux super\-admins.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    users = await db.get_all_users()
    if not users:
        await update.message.reply_text("📋 Aucun utilisateur.")
        return
    text = f"📋 *Utilisateurs ({len(users)})\:*\n\n"
    for u in users[:20]:
        name = escape_md(u['first_name'] or 'Inconnu')
        uname = f"@{escape_md(u['username'])}" if u['username'] else "N/A"
        text += f"• `{u['user_id']}` | {name} | {uname}\n"
    if len(users) > 20:
        text += f"\n\."
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "users")

async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Réservé aux super\-admins.", parse_mode=ParseMode.MARKDOWN_V2)
        return
    logs = await db.get_recent_logs(20)
    if not logs:
        await update.message.reply_text("📋 Aucun log.")
        return
    text = "📋 *Derniers logs\:*\n\n"
    for log in logs:
        text += f"`{log['timestamp']}` | {escape_md(log['action'])} | {escape_md(log['details'][:50])}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "logs")

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("❌ Uniquement dans les groupes.")
        return
    if not await is_admin_check(update, context):
        await update.message.reply_text("❌ Admin requis.")
        return
    settings = await db.get_group_settings(chat.id)
    keyboard = [
        [InlineKeyboardButton("🤖 Auto\-mod\: " + ("ON ✅" if settings.get("auto_moderation") else "OFF ❌"), callback_data="toggle_auto_mod")],
        [InlineKeyboardButton("👋 Bienvenue\: " + ("ON ✅" if settings.get("welcome_msg") else "OFF ❌"), callback_data="toggle_welcome")],
        [InlineKeyboardButton("🔗 Anti\-liens\: " + ("ON ✅" if settings.get("anti_links") else "OFF ❌"), callback_data="toggle_anti_links")],
        [InlineKeyboardButton("🖼️ Anti\-spam\: " + ("ON ✅" if settings.get("anti_spam") else "OFF ❌"), callback_data="toggle_anti_spam")],
        [InlineKeyboardButton("🔐 Captcha\: " + ("ON ✅" if settings.get("captcha") else "OFF ❌"), callback_data="toggle_captcha")],
    ]
    await update.message.reply_text("⚙️ *Paramètres du groupe\:*", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup(keyboard))
    await log_action(update, "settings")

async def callback_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    settings = await db.get_group_settings(chat_id)
    if query.data == "toggle_auto_mod":
        settings["auto_moderation"] = not settings.get("auto_moderation", False)
        status = "activée ✅" if settings["auto_moderation"] else "désactivée ❌"
        await query.edit_message_text(f"🤖 Auto\-mod {status}")
    elif query.data == "toggle_welcome":
        settings["welcome_msg"] = not settings.get("welcome_msg", False)
        status = "activée ✅" if settings["welcome_msg"] else "désactivée ❌"
        await query.edit_message_text(f"👋 Bienvenue {status}")
    elif query.data == "toggle_anti_links":
        settings["anti_links"] = not settings.get("anti_links", False)
        status = "activée ✅" if settings["anti_links"] else "désactivée ❌"
        await query.edit_message_text(f"🔗 Anti\-liens {status}")
    elif query.data == "toggle_anti_spam":
        settings["anti_spam"] = not settings.get("anti_spam", False)
        status = "activée ✅" if settings["anti_spam"] else "désactivée ❌"
        await query.edit_message_text(f"🖼️ Anti\-spam {status}")
    elif query.data == "toggle_captcha":
        settings["captcha"] = not settings.get("captcha", False)
        status = "activé ✅" if settings["captcha"] else "désactivé ❌"
        await query.edit_message_text(f"🔐 Captcha {status}")
    await db.update_group_settings(chat_id, settings)

# ═══════════════════════════════════════════════════════════════
# CONFIDENTIALITÉ
# ═══════════════════════════════════════════════════════════════

async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔒 *POLITIQUE DE CONFIDENTIALITÉ*\n\n"
        "*Données collectées\:*\n"
        "• ID Telegram, nom d\'utilisateur\n"
        "• Messages dans les groupes \(modération, résumé IA \- 200 derniers messages en mémoire uniquement\)\n"
        "• Logs d\'activité\n\n"
        "*Utilisation\:*\n"
        "• Fonctionnement du bot\n"
        "• Modération des groupes\n"
        "• Assistant IA \(questions et résumés\)\n"
        "• Statistiques anonymisées\n\n"
        "*Vos droits\:*\n"
        "• `/export_data` \- Exporter vos données\n"
        "• `/delete_my_data` \- Supprimer vos données\n\n"
        "Contactez un admin pour toute question."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "privacy")

async def cmd_export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    import json
    json_data = json.dumps(data, indent=2, default=str)
    await update.message.reply_text(f"📤 *Vos données\:*\n\n```json\n{escape_md(json_data[:3000])}\n```", parse_mode=ParseMode.MARKDOWN_V2)
    await log_action(update, "export_data")

async def cmd_delete_my_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("✅ Oui, supprimer", callback_data=f"confirm_delete_{user.id}")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cancel_delete")]
    ]
    await update.message.reply_text(
        "⚠️ *Supprimer toutes vos données ?*\n\nCette action est irréversible.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await log_action(update, "delete_data_request")

async def callback_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_delete":
        await query.edit_message_text("✅ Suppression annulée.")
        return
    if query.data.startswith("confirm_delete_"):
        uid = int(query.data.split("_")[-1])
        if uid == update.effective_user.id:
            await db.block_user(uid)
            await query.edit_message_text("✅ Vos données ont été supprimées.")
            await log_action(update, "delete_data_confirmed")

# ═══════════════════════════════════════════════════════════════
# ÉVÉNEMENTS DE GROUPE
# ═══════════════════════════════════════════════════════════════

async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    settings = await db.get_group_settings(chat.id)
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        await db.add_user(member.id, member.username, member.first_name, member.last_name or "")
        await log_action(update, "new_member", f"user={member.id}")

        if settings.get("captcha"):
            try:
                await chat.restrict_member(member.id, permissions=ChatPermissions(can_send_messages=False))
            except Exception:
                pass
            keyboard = [[InlineKeyboardButton("✅ Je ne suis pas un robot", callback_data=f"captcha_{member.id}")]]
            msg = await update.message.reply_text(
                f"👋 {member.mention_html()}, clique ci-dessous dans les {Config.CAPTCHA_TIMEOUT // 60} minutes pour pouvoir écrire dans le groupe.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            pending_captcha[(chat.id, member.id)] = msg.message_id
            if context.job_queue:
                context.job_queue.run_once(
                    kick_unverified, Config.CAPTCHA_TIMEOUT,
                    data={"chat_id": chat.id, "user_id": member.id, "message_id": msg.message_id},
                    name=f"captcha_timeout_{chat.id}_{member.id}"
                )
        elif settings.get("welcome_msg"):
            welcome = settings.get("custom_welcome", f"👋 Bienvenue, {member.mention_html()}!\n📜 /rules")
            await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)

async def kick_unverified(context: ContextTypes.DEFAULT_TYPE):
    """Retire un membre qui n'a pas validé le captcha à temps."""
    data = context.job.data
    key = (data["chat_id"], data["user_id"])
    if key not in pending_captcha:
        return  # déjà vérifié entre-temps
    del pending_captcha[key]
    try:
        await context.bot.ban_chat_member(data["chat_id"], data["user_id"])
        await context.bot.unban_chat_member(data["chat_id"], data["user_id"])  # pas d'exclusion définitive, il pourra rejoindre plus tard
    except Exception:
        pass
    try:
        await context.bot.delete_message(data["chat_id"], data["message_id"])
    except Exception:
        pass

async def callback_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    target_id = int(query.data.split("_")[1])
    if query.from_user.id != target_id:
        await query.answer("Ce bouton ne t'est pas destiné.", show_alert=True)
        return
    await query.answer()
    chat = update.effective_chat
    key = (chat.id, target_id)
    if key not in pending_captcha:
        return  # déjà vérifié ou expiré
    del pending_captcha[key]
    try:
        await chat.restrict_member(target_id, permissions=ChatPermissions(
            can_send_messages=True, can_send_polls=True,
            can_send_other_messages=True, can_add_web_page_previews=True
        ))
    except Exception:
        pass
    settings = await db.get_group_settings(chat.id)
    if settings.get("welcome_msg"):
        welcome = settings.get("custom_welcome", f"👋 Bienvenue, {query.from_user.mention_html()}!\n📜 /rules")
    else:
        welcome = f"✅ {query.from_user.mention_html()} vérifié, bienvenue !"
    try:
        await query.edit_message_text(welcome, parse_mode=ParseMode.HTML)
    except Exception:
        pass
    await log_action(update, "captcha_verified", f"user={target_id}")

async def on_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = update.message.left_chat_member
    if member and not member.is_bot:
        await log_action(update, "left_member", f"user={member.id}")

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat = update.effective_chat
    user = update.effective_user
    text = update.message.text
    if chat.type == "private":
        return
    settings = await db.get_group_settings(chat.id)
    # Historique en mémoire (pour /resume)
    hist = message_history.setdefault(chat.id, deque(maxlen=200))
    hist.append({"author": user.first_name or user.username or str(user.id), "text": text[:300]})
    # Anti-flood
    if settings.get("anti_spam") and not Config.is_admin(user.id):
        key = (chat.id, user.id)
        now = datetime.now().timestamp()
        recent = [t for t in flood_tracker.get(key, []) if now - t < Config.FLOOD_WINDOW_SECONDS]
        recent.append(now)
        flood_tracker[key] = recent
        if len(recent) > Config.FLOOD_MAX_MESSAGES:
            flood_tracker[key] = []
            try:
                until = datetime.now() + timedelta(seconds=Config.MUTE_DURATION)
                await chat.restrict_member(user.id, until_date=until, permissions=ChatPermissions(can_send_messages=False))
                await update.message.reply_text(f"🚫 {user.mention_html()} mis en sourdine (flood détecté).", parse_mode=ParseMode.HTML)
                await log_action(update, "antiflood_mute", f"user={user.id}")
            except Exception:
                pass
            return
    # Anti-liens
    if settings.get("anti_links"):
        if "http://" in text or "https://" in text or "t.me/" in text:
            try:
                await update.message.delete()
                await db.log_filtered_message(user.id, chat.id, text, "link", "deleted")
                await update.message.reply_text(f"🔗 {user.mention_html()}, les liens ne sont pas autorisés.", parse_mode=ParseMode.HTML)
                return
            except Exception:
                pass
    # Auto-modération
    if settings.get("auto_moderation"):
        check = moderation.check_message(text, user.id)
        if not check["is_clean"]:
            wcount = await db.get_warnings(user.id, chat.id)
            action = moderation.get_recommended_action(check, wcount)
            if action == "delete":
                try:
                    await update.message.delete()
                    await db.log_filtered_message(user.id, chat.id, text, "auto_mod", "deleted")
                except Exception:
                    pass
            elif action == "warn":
                await db.add_warning(user.id, chat.id, "Auto-modération", 0)
                new_count = await db.get_warnings(user.id, chat.id)
                await update.message.reply_text(f"⚠️ {user.mention_html()} signalé. Avertissements: {new_count}/{Config.MAX_WARNINGS}", parse_mode=ParseMode.HTML)
            elif action == "mute":
                try:
                    until = datetime.now() + timedelta(seconds=Config.MUTE_DURATION)
                    await chat.restrict_member(user.id, until_date=until, permissions=ChatPermissions(can_send_messages=False, can_send_polls=False, can_send_other_messages=False))
                    await update.message.reply_text(f"🔇 {user.mention_html()} muet pour comportement inapproprié.", parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            elif action == "ban":
                try:
                    await chat.ban_member(user.id)
                    await update.message.reply_text(f"👢 {user.mention_html()} banni.", parse_mode=ParseMode.HTML)
                except Exception:
                    pass

# ═══════════════════════════════════════════════════════════════
# SCHEDULER DE TÂCHES
# ═══════════════════════════════════════════════════════════════

async def check_scheduled_tasks(context: ContextTypes.DEFAULT_TYPE):
    try:
        tasks = await db.get_pending_tasks()
        for task in tasks:
            try:
                if task['task_type'] == 'broadcast':
                    users = await db.get_all_users()
                    for u in users:
                        try:
                            await context.bot.send_message(chat_id=u['user_id'], text=f"⏰ *Message planifié*\n\n{escape_md(task['content'])}", parse_mode=ParseMode.MARKDOWN_V2)
                            await asyncio.sleep(Config.BROADCAST_DELAY)
                        except Exception:
                            pass
                elif task['task_type'] == 'group_message':
                    await context.bot.send_message(chat_id=task['target_id'], text=task['content'])
                await db.mark_task_executed(task['id'])
                logger.info(f"Tâche {task['id']} exécutée")
            except Exception as e:
                logger.error(f"Erreur tâche {task['id']}: {e}")
    except Exception as e:
        logger.error(f"Erreur scheduler: {e}")

# ═══════════════════════════════════════════════════════════════
# MAIN - DÉMARRAGE MANUEL (évite le bug run_polling)
# ═══════════════════════════════════════════════════════════════

async def main():
    """Point d'entrée principal - cycle de vie manuel"""

    if Config.BOT_TOKEN == "TON_TOKEN_ICI" or not Config.BOT_TOKEN:
        logger.error("❌ ERREUR: Définissez BOT_TOKEN dans .env")
        sys.exit(1)

    logger.info("🚀 Démarrage de ShadyBot v2.0...")
    logger.info("Initialisation de la base de données...")
    await db.init()
    logger.info("✅ Base de données prête!")

    # Création de l'application
    application = Application.builder().token(Config.BOT_TOKEN).build()

    # ─── Handlers de base ───
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("ping", cmd_ping))
    application.add_handler(CommandHandler("id", cmd_id))
    application.add_handler(CommandHandler("about", cmd_about))

    # ─── Recherche ───
    application.add_handler(CommandHandler("search", cmd_search))
    application.add_handler(CommandHandler("news", cmd_news))
    application.add_handler(CommandHandler("fetch", cmd_fetch))
    application.add_handler(CommandHandler("images", cmd_images))
    application.add_handler(CommandHandler("ai", cmd_ai))
    application.add_handler(CommandHandler("resume", cmd_resume))
    # ─── Modération ───
    application.add_handler(CommandHandler("warn", cmd_warn))
    application.add_handler(CommandHandler("unwarn", cmd_unwarn))
    application.add_handler(CommandHandler("mute", cmd_mute))
    application.add_handler(CommandHandler("unmute", cmd_unmute))
    application.add_handler(CommandHandler("ban", cmd_ban))
    application.add_handler(CommandHandler("unban", cmd_unban))
    application.add_handler(CommandHandler("kick", cmd_kick))
    application.add_handler(CommandHandler("info", cmd_info))

    # ─── Diffusion ───
    application.add_handler(CommandHandler("broadcast", cmd_broadcast))

    # ─── Planification (conversation) ───
    schedule_conv = ConversationHandler(
        entry_points=[CommandHandler("schedule", cmd_schedule)],
        states={SCHEDULE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_msg_received)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: u.message.reply_text("Annulé."))]
    )
    application.add_handler(schedule_conv)
    application.add_handler(CommandHandler("tasks", cmd_tasks))
    application.add_handler(CommandHandler("cancel", cmd_cancel_task))

    # ─── Filtres ───
    application.add_handler(CommandHandler("filters", cmd_filters))
    application.add_handler(CommandHandler("addfilter", cmd_addfilter))
    application.add_handler(CommandHandler("delfilter", cmd_delfilter))

    # ─── Règles ───
    application.add_handler(CommandHandler("rules", cmd_rules))
    application.add_handler(CommandHandler("setrules", cmd_setrules))

    # ─── Admin ───
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CommandHandler("users", cmd_users))
    application.add_handler(CommandHandler("logs", cmd_logs))
    application.add_handler(CommandHandler("settings", cmd_settings))

    # ─── Confidentialité ───
    application.add_handler(CommandHandler("privacy", cmd_privacy))
    application.add_handler(CommandHandler("export_data", cmd_export_data))
    application.add_handler(CommandHandler("delete_my_data", cmd_delete_my_data))

    # ─── Callbacks ───
    application.add_handler(CallbackQueryHandler(callback_settings, pattern="^toggle_"))
    application.add_handler(CallbackQueryHandler(callback_captcha, pattern="^captcha_"))
    application.add_handler(CallbackQueryHandler(callback_delete, pattern="^(confirm_delete_|cancel_delete)"))

    # ─── Événements de groupe ───
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_left_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    # ─── Scheduler ───
    application.job_queue.run_repeating(check_scheduled_tasks, interval=60, first=10)

    # ═══ DÉMARRAGE MANUEL (évite le bug run_polling) ═══
    logger.info("🔄 Initialisation de l'application...")
    await application.initialize()

    logger.info("🚀 Démarrage de l'application...")
    await application.start()

    logger.info("👂 Démarrage du polling...")
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    logger.info("✅ ShadyBot est en ligne et en écoute!")

    # Garder le programme en vie indéfiniment
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("🛑 Arrêt demandé...")
    finally:
        logger.info("🛑 Arrêt du bot...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("✅ Bot arrêté proprement.")

if __name__ == "__main__":
    # Démarré en premier, dans un thread séparé, pour que Render voie le
    # service comme "healthy" dès que possible (voir commentaire plus haut).
    threading.Thread(target=start_health_server, daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Interruption clavier.")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        sys.exit(1)
