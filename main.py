#!/usr/bin/env python3
"""SHADYBOT MAX — bot Telegram asynchrone."""
from __future__ import annotations

import asyncio
import html
import logging
import os
import sys
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import (
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ai_assistant import AIAssistant
from config import Config
from database import Database
from moderation import ModerationEngine
from web_search import WebSearch

logging.basicConfig(
    level=getattr(logging, Config.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("shadybot")

db = Database()
web = WebSearch()
ai = AIAssistant()
moderation = ModerationEngine()

message_history: dict[int, deque] = defaultdict(
    lambda: deque(maxlen=Config.max_message_history)
)
flood_tracker: dict[tuple[int, int], deque[float]] = defaultdict(deque)
pending_captcha: dict[tuple[int, int], int] = {}
# IDs des messages vus par le bot, utilisés notamment par /clear.
# Conservés uniquement en RAM pour éviter une écriture DB à chaque message.
clear_message_ids: dict[int, deque] = defaultdict(lambda: deque(maxlen=5000))

SCHEDULE_MESSAGE = 1

DEFAULT_SETTINGS = {
    "auto_moderation": False,
    "welcome_msg": True,
    "anti_links": False,
    "anti_spam": True,
    "captcha": False,
}


def esc(value: object) -> str:
    return html.escape(str(value or ""))


async def log_action(update: Update, action: str, details: str = "") -> None:
    try:
        user_id = update.effective_user.id if update.effective_user else 0
        chat_id = update.effective_chat.id if update.effective_chat else 0
        await db.log_activity(user_id, chat_id, action, details)
    except Exception:
        logger.exception("Impossible d'enregistrer l'action %s", action)


async def require_admin(update: Update) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if Config.is_admin(user.id):
        return True
    if chat.type == "private":
        return False
    try:
        member = await chat.get_member(user.id)
        return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
    except TelegramError:
        return False


async def reply(update: Update, text: str, **kwargs):
    if update.message:
        return await update.message.reply_text(text, **kwargs)
    return None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    await db.add_user(user.id, user.username, user.first_name, user.last_name)
    text = (
        f"👋 <b>Bienvenue, {esc(user.first_name)} !</b>\n\n"
        "🤖 Je suis <b>SHADYBOT</b>, assistant Telegram polyvalent.\n\n"
        "🔍 /search — recherche web\n"
        "📰 /news — actualités\n"
        "🧠 /ai — assistant IA\n"
        "📋 /resume — résumé du groupe\n"
        "🛡️ /rules — règles du groupe\n"
        "❓ /help — toutes les commandes"
    )
    await reply(update, text, parse_mode=ParseMode.HTML)
    await log_action(update, "start")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>📖 AIDE SHADYBOT</b>\n\n"
        "<b>🔍 Web</b>\n"
        "/search requête\n/news sujet\n/fetch URL\n/images requête\n\n"
        "<b>🧠 IA</b>\n"
        "/ai question\n/resume\n\n"
        "<b>👥 Modération</b>\n"
        "/clear /warn /unwarn /mute /unmute /ban /unban /kick /info\n\n"
        "<b>📢 Admin</b>\n"
        "/broadcast message\n/schedule\n/tasks\n/cancel ID\n"
        "/stats /users /logs /settings\n"
        "/filters /addfilter /delfilter\n"
        "/rules /setrules\n\n"
        "<b>🔒 Données</b>\n"
        "/privacy /export_data /delete_my_data\n\n"
        "/ping /id /about"
    )
    await reply(update, text, parse_mode=ParseMode.HTML)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start = asyncio.get_running_loop().time()
    msg = await reply(update, "🏓 Calcul de la latence…")
    ms = (asyncio.get_running_loop().time() - start) * 1000
    if msg:
        await msg.edit_text(f"🏓 <b>Pong</b> — {ms:.0f} ms", parse_mode=ParseMode.HTML)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u, c = update.effective_user, update.effective_chat
    await reply(
        update,
        f"<b>🆔 Identifiants</b>\n\n"
        f"Utilisateur: <code>{u.id}</code>\n"
        f"Nom: {esc(u.full_name)}\n"
        f"Username: @{esc(u.username or 'N/A')}\n\n"
        f"Chat: <code>{c.id}</code>\nType: {esc(c.type)}\nTitre: {esc(c.title or 'N/A')}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = await db.get_stats()
    await reply(
        update,
        f"<b>🤖 SHADYBOT MAX</b>\n\n"
        f"👥 Utilisateurs: <code>{s['total_users']}</code>\n"
        f"💬 Groupes: <code>{s['total_groups']}</code>\n"
        f"⚠️ Avertissements: <code>{s['total_warnings']}</code>\n"
        f"⏰ Tâches: <code>{s['pending_tasks']}</code>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply(update, "Usage: /search <requête>")
    query = " ".join(context.args)
    msg = await reply(update, "🔍 Recherche…")
    results = await web.search(query)
    lines = [f"<b>🔍 Résultats: {esc(query)}</b>"]
    for i, r in enumerate(results[:5], 1):
        title, snippet, url = esc(r.get("title")), esc(r.get("snippet", "")[:350]), r.get("url", "")
        if url:
            lines.append(f"\n<b>{i}. {title}</b>\n{snippet}\n<a href=\"{esc(url)}\">🔗 Ouvrir</a>")
        else:
            lines.append(f"\n<b>{i}. {title}</b>\n{snippet}")
    if msg:
        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    await log_action(update, "search", query)


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply(update, "Usage: /news <sujet>")
    query = " ".join(context.args)
    msg = await reply(update, "📰 Recherche d’actualités…")
    results = await web.search_news(query)
    lines = [f"<b>📰 Actualités: {esc(query)}</b>"]
    for i, r in enumerate(results[:5], 1):
        url = r.get("url", "")
        lines.append(
            f"\n<b>{i}. {esc(r.get('title','Sans titre'))}</b>\n"
            f"{esc(r.get('snippet','')[:350])}\n"
            + (f"<a href=\"{esc(url)}\">🔗 Lire</a>" if url else "")
        )
    if msg:
        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    await log_action(update, "news", query)


async def cmd_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply(update, "Usage: /fetch <URL>")
    msg = await reply(update, "📥 Extraction…")
    content = await web.fetch_page_content(context.args[0])
    if msg:
        await msg.edit_text(f"<b>📄 Contenu</b>\n\n<pre>{esc(content[:6000])}</pre>",
                            parse_mode=ParseMode.HTML)
    await log_action(update, "fetch", context.args[0])


async def cmd_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply(update, "Usage: /images <requête>")
    query = " ".join(context.args)
    from urllib.parse import quote_plus
    url = "https://www.google.com/search?tbm=isch&q=" + quote_plus(query)
    await reply(update, f"🖼️ <a href=\"{esc(url)}\">Recherche d’images pour {esc(query)}</a>",
                parse_mode=ParseMode.HTML)
    await log_action(update, "images", query)


async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await reply(update, "Usage: /ai <question>")
    msg = await reply(update, "🧠 Réflexion…")
    answer = await ai.ask(" ".join(context.args))
    if msg:
        await msg.edit_text(f"🧠 {esc(answer[:3900])}", parse_mode=ParseMode.HTML)
    await log_action(update, "ai", "question")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type == "private":
        return await reply(update, "❌ Cette commande fonctionne dans un groupe.")
    history = list(message_history.get(chat.id, []))
    if len(history) < 5:
        return await reply(update, "Pas encore assez de messages récents.")
    msg = await reply(update, "🧠 Résumé en cours…")
    summary = await ai.summarize_messages(history)
    if msg:
        await msg.edit_text(f"📋 <b>Résumé</b>\n\n{esc(summary[:3900])}",
                            parse_mode=ParseMode.HTML)
    await log_action(update, "resume")


async def target_from_reply(update: Update):
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Supprime les messages récents du chat.

    En privé : l'utilisateur peut nettoyer les messages récents du chat.
    En groupe : seuls les administrateurs peuvent lancer /clear et le bot
    doit disposer du droit « Supprimer les messages ».

    Telegram limite la suppression des messages à ceux qui peuvent encore
    être supprimés (notamment la fenêtre de 48 h). Le bot ne peut pas
    récupérer arbitrairement tout l'historique d'un chat via l'API Bot.
    """
    chat = update.effective_chat
    command = update.effective_message
    if not chat or not command:
        return

    # En privé, /clear est disponible pour l'utilisateur du chat.
    # Dans un groupe, la commande est réservée aux administrateurs.
    if chat.type != "private":
        if not await require_admin(update):
            try:
                await command.delete()
            except TelegramError:
                pass
            return await reply(update, "❌ Administrateur requis pour utiliser /clear.")

        # Vérifie que SHADYBOT peut effectivement supprimer les messages.
        try:
            me = await chat.get_member(context.bot.id)
            if not getattr(me, "can_delete_messages", False):
                return await reply(
                    update,
                    "❌ Je n'ai pas le droit « Supprimer les messages ». "
                    "Donne-moi ce droit puis réessaie /clear."
                )
        except TelegramError as exc:
            logger.warning("Impossible de vérifier les droits de /clear: %s", exc)
            return await reply(update, "❌ Impossible de vérifier mes permissions dans ce groupe.")

    status = None
    try:
        status = await chat.send_message("🧹 Nettoyage en cours…")
    except TelegramError:
        pass

    # Priorité aux IDs que le bot a vus depuis son démarrage.
    known_ids = set(clear_message_ids.get(chat.id, ()))
    known_ids.update({command.message_id})
    if status:
        known_ids.add(status.message_id)

    # Complément : tentative sur les IDs récents. Telegram ignore/refuse
    # simplement ceux qui n'existent pas ou ne sont plus supprimables.
    last_id = max(known_ids) if known_ids else command.message_id
    first_id = max(1, last_id - 4999)
    candidate_ids = set(range(first_id, last_id + 1))
    candidate_ids.update(known_ids)
    candidate_ids.discard(status.message_id if status else -1)
    candidate_ids.discard(command.message_id)

    deleted = 0
    candidates = sorted(candidate_ids)

    # delete_messages accepte au maximum 100 IDs par appel.
    for start in range(0, len(candidates), 100):
        batch = candidates[start:start + 100]
        if not batch:
            continue
        try:
            await context.bot.delete_messages(
                chat_id=chat.id,
                message_ids=batch,
            )
            deleted += len(batch)
        except TelegramError:
            # Un bloc peut contenir des messages non supprimables. On retente
            # individuellement pour supprimer ceux qui restent accessibles.
            for message_id in batch:
                try:
                    await context.bot.delete_message(
                        chat_id=chat.id,
                        message_id=message_id,
                    )
                    deleted += 1
                except TelegramError:
                    continue
        await asyncio.sleep(0.05)

    clear_message_ids.pop(chat.id, None)
    message_history.pop(chat.id, None)

    # Le message de statut est supprimé après le nettoyage.
    if status:
        try:
            await status.delete()
        except TelegramError:
            pass

    await log_action(
        update,
        "clear",
        f"candidates={len(candidates)} deleted={deleted}",
    )

    # Dans un groupe, on laisse une confirmation très courte. En privé,
    # on la laisse également pour confirmer l'action à l'utilisateur.
    try:
        confirmation = await chat.send_message(
            f"🧹 Nettoyage terminé. {deleted} message(s) supprimé(s)."
        )
        # La confirmation est aussi suivie afin qu'un prochain /clear puisse
        # la supprimer.
        clear_message_ids[chat.id].append(confirmation.message_id)
    except TelegramError:
        pass


async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    target = await target_from_reply(update)
    if not target:
        return await reply(update, "Réponds au message de la personne à avertir.")
    chat = update.effective_chat
    reason = " ".join(context.args) or "Aucune raison"
    await db.add_warning(target.id, chat.id, reason, update.effective_user.id)
    count = await db.get_warnings(target.id, chat.id)
    if count >= Config.max_warnings:
        try:
            await chat.ban_member(target.id)
            text = f"🚫 {target.mention_html()} banni après {count} avertissements."
        except TelegramError as exc:
            text = f"⚠️ {target.mention_html()} — {count} avertissements. Bannissement impossible: {esc(exc)}"
    else:
        text = f"⚠️ {target.mention_html()} averti ({count}/{Config.max_warnings})."
    await reply(update, text, parse_mode=ParseMode.HTML)
    await log_action(update, "warn", f"target={target.id}")


async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    target = await target_from_reply(update)
    if not target:
        return await reply(update, "Réponds au message de la personne.")
    n = await db.clear_warnings(target.id, update.effective_chat.id)
    await reply(update, f"✅ {target.mention_html()}: {n} avertissement(s) retiré(s).",
                parse_mode=ParseMode.HTML)


def parse_duration(value: str) -> int | None:
    try:
        if value[-1:] in {"s", "m", "h", "d"}:
            unit = value[-1]
            number = int(value[:-1])
            factor = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
            seconds = number * factor
        else:
            seconds = int(value)
        if seconds <= 0 or seconds > 28 * 86400:
            return None
        return seconds
    except (ValueError, IndexError):
        return None


async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    target = await target_from_reply(update)
    if not target:
        return await reply(update, "Réponds au message de la personne.")
    seconds = parse_duration(context.args[0]) if context.args else Config.mute_duration
    if seconds is None:
        return await reply(update, "Durée invalide. Exemples: 30m, 2h, 1d.")
    until = datetime.now() + timedelta(seconds=seconds)
    perms = ChatPermissions(can_send_messages=False)
    try:
        await update.effective_chat.restrict_member(target.id, permissions=perms, until_date=until)
        await reply(update, f"🔇 {target.mention_html()} muet pour {seconds}s.", parse_mode=ParseMode.HTML)
    except TelegramError as exc:
        await reply(update, f"❌ {esc(exc)}")


async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    target = await target_from_reply(update)
    if not target:
        return await reply(update, "Réponds au message de la personne.")
    perms = ChatPermissions(
        can_send_messages=True, can_send_polls=True,
        can_send_other_messages=True, can_add_web_page_previews=True
    )
    try:
        await update.effective_chat.restrict_member(target.id, permissions=perms)
        await reply(update, f"🔊 {target.mention_html()} peut parler.",
                    parse_mode=ParseMode.HTML)
    except TelegramError as exc:
        await reply(update, f"❌ {esc(exc)}")


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    target = await target_from_reply(update)
    if not target:
        return await reply(update, "Réponds au message de la personne.")
    try:
        await update.effective_chat.ban_member(target.id)
        await reply(update, f"🚫 {target.mention_html()} banni.", parse_mode=ParseMode.HTML)
    except TelegramError as exc:
        await reply(update, f"❌ {esc(exc)}")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    if not context.args:
        return await reply(update, "Usage: /unban <user_id>")
    try:
        user_id = int(context.args[0])
        await update.effective_chat.unban_member(user_id)
        await reply(update, f"✅ <code>{user_id}</code> débanni.", parse_mode=ParseMode.HTML)
    except (ValueError, TelegramError) as exc:
        await reply(update, f"❌ {esc(exc)}")


async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    target = await target_from_reply(update)
    if not target:
        return await reply(update, "Réponds au message de la personne.")
    try:
        await update.effective_chat.ban_member(target.id)
        await update.effective_chat.unban_member(target.id)
        await reply(update, f"👢 {target.mention_html()} expulsé.", parse_mode=ParseMode.HTML)
    except TelegramError as exc:
        await reply(update, f"❌ {esc(exc)}")


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = await target_from_reply(update) or update.effective_user
    history = await db.get_warning_history(target.id, update.effective_chat.id)
    data = await db.get_user(target.id)
    lines = [
        f"<b>👤 {esc(target.full_name)}</b>",
        f"ID: <code>{target.id}</code>",
        f"Username: @{esc(target.username or 'N/A')}",
        f"Avertissements: {len(history)}",
    ]
    if data:
        lines.append(f"Inscription: {esc(data['joined_at'])}")
    await reply(update, "\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        return await reply(update, "❌ Super-admin requis.")
    message = " ".join(context.args).strip()
    if not message:
        return await reply(update, "Usage: /broadcast <message>")
    users = await db.get_all_users()
    if not users:
        return await reply(update, "Aucun utilisateur.")
    status = await reply(update, f"📢 Diffusion vers {len(users)} utilisateurs…")
    semaphore = asyncio.Semaphore(Config.broadcast_concurrency)
    sent = failed = 0

    async def send_one(user):
        nonlocal sent, failed
        async with semaphore:
            try:
                await context.bot.send_message(user["user_id"], f"📢 Message admin\n\n{message}")
                sent += 1
            except (Forbidden, BadRequest, TelegramError):
                failed += 1
            await asyncio.sleep(Config.broadcast_delay)

    await asyncio.gather(*(send_one(u) for u in users))
    if status:
        await status.edit_text(f"✅ Terminé\n📤 Envoyés: {sent}\n❌ Échecs: {failed}")
    await log_action(update, "broadcast", f"sent={sent};failed={failed}")


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        return await reply(update, "❌ Super-admin requis.")
    await reply(update, "⏰ Envoie: message | YYYY-MM-DD HH:MM")
    return SCHEDULE_MESSAGE


async def receive_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip()
    if "|" not in raw:
        await reply(update, "❌ Format: message | YYYY-MM-DD HH:MM")
        return ConversationHandler.END
    message, date_text = (p.strip() for p in raw.rsplit("|", 1))
    try:
        when = datetime.strptime(date_text, "%Y-%m-%d %H:%M")
    except ValueError:
        await reply(update, "❌ Date invalide.")
        return ConversationHandler.END
    if not message or when <= datetime.now():
        await reply(update, "❌ Message vide ou date déjà passée.")
        return ConversationHandler.END
    task_id = await db.add_task("broadcast", update.effective_chat.id, message, when)
    await reply(update, f"✅ Tâche <code>#{task_id}</code> planifiée pour {when:%d/%m/%Y %H:%M}.",
                parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        return await reply(update, "❌ Super-admin requis.")
    tasks = await db.get_all_tasks()
    if not tasks:
        return await reply(update, "📋 Aucune tâche.")
    lines = ["<b>📋 Tâches</b>"]
    for t in tasks[:15]:
        emoji = {"pending": "⏳", "executed": "✅", "cancelled": "❌"}.get(t["status"], "•")
        lines.append(f"{emoji} <code>#{t['id']}</code> — {esc(t['schedule_time'])} — {esc(t['content'][:80])}")
    await reply(update, "\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        return await reply(update, "❌ Super-admin requis.")
    if not context.args:
        return await reply(update, "Usage: /cancel <id>")
    try:
        task_id = int(context.args[0])
    except ValueError:
        return await reply(update, "ID invalide.")
    ok = await db.cancel_task(task_id)
    await reply(update, "✅ Tâche annulée." if ok else "❌ Tâche introuvable ou déjà terminée.")


async def cmd_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    words = moderation.get_filters()
    await reply(update, "🛡️ Filtres:\n" + ", ".join(words[:100]))


async def cmd_addfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    word = " ".join(context.args).strip()
    if not word:
        return await reply(update, "Usage: /addfilter <mot>")
    moderation.add_custom_filter(word)
    await reply(update, f"✅ Filtre ajouté: {esc(word)}", parse_mode=ParseMode.HTML)


async def cmd_delfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    word = " ".join(context.args).strip()
    if not word:
        return await reply(update, "Usage: /delfilter <mot>")
    moderation.remove_custom_filter(word)
    await reply(update, f"✅ Filtre retiré: {esc(word)}", parse_mode=ParseMode.HTML)


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        return await reply(update, "❌ Uniquement dans les groupes.")
    rules = await db.get_group_rules(update.effective_chat.id)
    await reply(update, f"📜 <b>Règles</b>\n\n{esc(rules)}" if rules else "📜 Aucune règle.",
                parse_mode=ParseMode.HTML)


async def cmd_setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    rules = " ".join(context.args).strip()
    if not rules:
        return await reply(update, "Usage: /setrules <règles>")
    await db.set_group_rules(update.effective_chat.id, rules)
    await reply(update, "✅ Règles mises à jour.")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        return await reply(update, "❌ Super-admin requis.")
    s = await db.get_stats()
    await reply(update, "\n".join([
        "<b>📊 Statistiques</b>",
        f"Utilisateurs: {s['total_users']}",
        f"Groupes: {s['total_groups']}",
        f"Avertissements: {s['total_warnings']}",
        f"Tâches en attente: {s['pending_tasks']}",
        f"Logs: {s['total_logs']}",
    ]), parse_mode=ParseMode.HTML)


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        return await reply(update, "❌ Super-admin requis.")
    users = await db.get_all_users()
    lines = [f"<b>👥 {len(users)} utilisateurs</b>"]
    for u in users[:50]:
        lines.append(f"• <code>{u['user_id']}</code> @{esc(u['username'] or 'N/A')}")
    await reply(update, "\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not Config.is_admin(update.effective_user.id):
        return await reply(update, "❌ Super-admin requis.")
    logs = await db.get_recent_logs(30)
    if not logs:
        return await reply(update, "Aucun log.")
    text = "\n".join(
        f"{esc(x['timestamp'])} | {esc(x['action'])} | {esc(x['details'][:120])}"
        for x in logs
    )
    await reply(update, f"<pre>{text[:3800]}</pre>", parse_mode=ParseMode.HTML)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        return await reply(update, "❌ Uniquement dans les groupes.")
    if not await require_admin(update):
        return await reply(update, "❌ Administrateur requis.")
    settings = {**DEFAULT_SETTINGS, **await db.get_group_settings(update.effective_chat.id)}
    keyboard = [
        [InlineKeyboardButton(f"🤖 Auto-mod: {'ON' if settings['auto_moderation'] else 'OFF'}",
                              callback_data="set:auto_moderation")],
        [InlineKeyboardButton(f"👋 Bienvenue: {'ON' if settings['welcome_msg'] else 'OFF'}",
                              callback_data="set:welcome_msg")],
        [InlineKeyboardButton(f"🔗 Anti-liens: {'ON' if settings['anti_links'] else 'OFF'}",
                              callback_data="set:anti_links")],
        [InlineKeyboardButton(f"🖼️ Anti-spam: {'ON' if settings['anti_spam'] else 'OFF'}",
                              callback_data="set:anti_spam")],
        [InlineKeyboardButton(f"🔐 Captcha: {'ON' if settings['captcha'] else 'OFF'}",
                              callback_data="set:captcha")],
    ]
    await reply(update, "⚙️ <b>Paramètres du groupe</b>",
                parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def callback_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await require_admin(update):
        return await q.answer("Administrateur requis.", show_alert=True)
    _, key = q.data.split(":", 1)
    if key not in DEFAULT_SETTINGS:
        return
    settings = {**DEFAULT_SETTINGS, **await db.get_group_settings(update.effective_chat.id)}
    settings[key] = not bool(settings[key])
    await db.update_group_settings(update.effective_chat.id, settings)
    await q.edit_message_text(f"✅ {key}: {'ON' if settings[key] else 'OFF'}")


async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply(update,
        "<b>🔒 Confidentialité</b>\n\n"
        "Le bot stocke les informations nécessaires à son fonctionnement "
        "(identifiant Telegram, profil minimal, avertissements et logs). "
        "L'historique utilisé par /resume reste en mémoire du processus.\n\n"
        "/export_data — exporter\n/delete_my_data — supprimer",
        parse_mode=ParseMode.HTML)


async def cmd_export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.get_user(update.effective_user.id)
    if not user:
        return await reply(update, "Aucune donnée trouvée.")
    warnings = await db.get_warning_history(update.effective_user.id)
    import json
    payload = {
        "user": user,
        "warnings": warnings,
    }
    await reply(update, f"<pre>{esc(json.dumps(payload, ensure_ascii=False, indent=2, default=str)[:3900])}</pre>",
                parse_mode=ParseMode.HTML)


async def cmd_delete_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    keyboard = [[
        InlineKeyboardButton("✅ Supprimer", callback_data=f"delete:{uid}"),
        InlineKeyboardButton("❌ Annuler", callback_data="delete:cancel"),
    ]]
    await reply(update, "⚠️ Confirmer la suppression de vos données ?",
                reply_markup=InlineKeyboardMarkup(keyboard))


async def callback_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "delete:cancel":
        return await q.edit_message_text("Annulé.")
    uid = int(q.data.split(":")[1])
    if q.from_user.id != uid:
        return await q.answer("Ce bouton ne t'appartient pas.", show_alert=True)
    await db.delete_user_data(uid)
    await q.edit_message_text("✅ Vos données ont été supprimées.")


async def on_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        await db.add_user(member.id, member.username, member.first_name, member.last_name)
        await db.add_group(chat.id, chat.title or "", chat.type)
        settings = {**DEFAULT_SETTINGS, **await db.get_group_settings(chat.id)}
        if settings["captcha"]:
            try:
                await chat.restrict_member(member.id, permissions=ChatPermissions(can_send_messages=False))
                keyboard = [[InlineKeyboardButton(
                    "✅ Je suis humain", callback_data=f"captcha:{member.id}"
                )]]
                sent = await message.reply_text(
                    f"🔐 {member.mention_html()}, confirme ton arrivée.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                pending_captcha[(chat.id, member.id)] = sent.message_id
                context.job_queue.run_once(expire_captcha, Config.captcha_timeout,
                                           data=(chat.id, member.id, sent.message_id))
            except TelegramError:
                logger.exception("Captcha impossible")


async def expire_captcha(context: ContextTypes.DEFAULT_TYPE):
    chat_id, user_id, message_id = context.job.data
    key = (chat_id, user_id)
    if key not in pending_captcha:
        return
    pending_captcha.pop(key, None)
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.delete_message(chat_id, message_id)
    except TelegramError:
        logger.warning("Expiration captcha impossible: %s/%s", chat_id, user_id)


async def callback_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat = update.effective_chat
    target_id = int(q.data.split(":")[1])
    if q.from_user.id != target_id:
        return await q.answer("Ce bouton n'est pas pour toi.", show_alert=True)
    key = (chat.id, target_id)
    if key not in pending_captcha:
        return await q.answer("Captcha expiré ou déjà validé.", show_alert=True)
    pending_captcha.pop(key, None)
    await q.answer("Vérification réussie.")
    perms = ChatPermissions(
        can_send_messages=True, can_send_polls=True,
        can_send_other_messages=True, can_add_web_page_previews=True
    )
    try:
        await chat.restrict_member(target_id, permissions=perms)
    except TelegramError:
        logger.exception("Déblocage captcha impossible")
    try:
        await q.edit_message_text(f"✅ {q.from_user.mention_html()} vérifié.",
                                   parse_mode=ParseMode.HTML)
    except TelegramError:
        pass


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not user or not chat or chat.type == "private":
        return
    text = msg.text or ""
    clear_message_ids[chat.id].append(msg.message_id)
    await db.add_user(user.id, user.username, user.first_name, user.last_name)
    await db.add_group(chat.id, chat.title or "", chat.type)
    await db.touch_user(user.id)

    message_history[chat.id].append({
        "author": user.first_name or user.username or str(user.id),
        "text": text[:1000],
    })

    settings = {**DEFAULT_SETTINGS, **await db.get_group_settings(chat.id)}

    if settings["anti_spam"] and not Config.is_admin(user.id):
        now = asyncio.get_running_loop().time()
        q = flood_tracker[(chat.id, user.id)]
        while q and now - q[0] > Config.flood_window_seconds:
            q.popleft()
        q.append(now)
        if len(q) > Config.flood_max_messages:
            q.clear()
            try:
                await chat.restrict_member(
                    user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=datetime.now() + timedelta(seconds=Config.mute_duration),
                )
                await msg.reply_text(f"🚫 {user.mention_html()} flood détecté.",
                                     parse_mode=ParseMode.HTML)
                await db.log_filtered_message(user.id, chat.id, text, "flood", "mute")
            except TelegramError:
                pass
            return

    if settings["anti_links"] and web.URL_RE.search(text) and not Config.is_admin(user.id):
        try:
            await msg.delete()
            await db.log_filtered_message(user.id, chat.id, text, "link", "delete")
        except TelegramError:
            pass
        return

    if settings["auto_moderation"] and not Config.is_admin(user.id):
        result = moderation.check_message(text, user.id)
        if not result["is_clean"]:
            warnings = await db.get_warnings(user.id, chat.id)
            action = moderation.get_recommended_action(result, warnings)
            try:
                if action == "delete":
                    await msg.delete()
                elif action == "warn":
                    await db.add_warning(user.id, chat.id, "Auto-modération", 0)
                    await msg.reply_text(
                        f"⚠️ {user.mention_html()} averti ({warnings+1}/{Config.max_warnings}).",
                        parse_mode=ParseMode.HTML,
                    )
                elif action == "mute":
                    await chat.restrict_member(
                        user.id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=datetime.now() + timedelta(seconds=Config.mute_duration),
                    )
                elif action == "ban":
                    await chat.ban_member(user.id)
                await db.log_filtered_message(user.id, chat.id, text, "auto_mod", action)
            except TelegramError:
                logger.exception("Action de modération échouée")


async def check_tasks(context: ContextTypes.DEFAULT_TYPE):
    tasks = await db.get_pending_tasks()
    for task in tasks:
        try:
            if task["task_type"] == "broadcast":
                users = await db.get_all_users()
                for user in users:
                    try:
                        await context.bot.send_message(
                            user["user_id"], f"⏰ Message planifié\n\n{task['content']}"
                        )
                        await asyncio.sleep(Config.broadcast_delay)
                    except TelegramError:
                        continue
            elif task["task_type"] == "group_message":
                await context.bot.send_message(task["target_id"], task["content"])
            await db.mark_task_executed(task["id"])
        except Exception:
            logger.exception("Erreur tâche #%s", task["id"])


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"SHADYBOT OK")

    def log_message(self, format, *args):
        return


def start_health_server() -> None:
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info("Health server: port %s", port)
    server.serve_forever()


async def post_init(application: Application):
    await db.init()
    logger.info("Database initialized.")


async def post_shutdown(application: Application):
    await ai.close()


def build_application() -> Application:
    app = (
        Application.builder()
        .token(Config.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    base = [
        ("start", cmd_start), ("help", cmd_help), ("ping", cmd_ping),
        ("id", cmd_id), ("about", cmd_about),
        ("search", cmd_search), ("news", cmd_news), ("fetch", cmd_fetch),
        ("images", cmd_images), ("ai", cmd_ai), ("resume", cmd_resume), ("clear", cmd_clear),
        ("warn", cmd_warn), ("unwarn", cmd_unwarn), ("mute", cmd_mute),
        ("unmute", cmd_unmute), ("ban", cmd_ban), ("unban", cmd_unban),
        ("kick", cmd_kick), ("info", cmd_info),
        ("broadcast", cmd_broadcast), ("tasks", cmd_tasks), ("cancel", cmd_cancel),
        ("filters", cmd_filters), ("addfilter", cmd_addfilter), ("delfilter", cmd_delfilter),
        ("rules", cmd_rules), ("setrules", cmd_setrules),
        ("stats", cmd_stats), ("users", cmd_users), ("logs", cmd_logs),
        ("settings", cmd_settings), ("privacy", cmd_privacy),
        ("export_data", cmd_export_data), ("delete_my_data", cmd_delete_data),
    ]
    for command, handler in base:
        app.add_handler(CommandHandler(command, handler))

    schedule = ConversationHandler(
        entry_points=[CommandHandler("schedule", cmd_schedule)],
        states={
            SCHEDULE_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_schedule)
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_user=True,
        per_chat=True,
    )
    app.add_handler(schedule)

    app.add_handler(CallbackQueryHandler(callback_settings, pattern=r"^set:"))
    app.add_handler(CallbackQueryHandler(callback_delete, pattern=r"^delete:"))
    app.add_handler(CallbackQueryHandler(callback_captcha, pattern=r"^captcha:"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))
    app.job_queue.run_repeating(check_tasks, interval=30, first=10)
    return app


def main() -> None:
    try:
        Config.validate()
    except Exception as exc:
        logger.error("Configuration invalide: %s", exc)
        raise SystemExit(1) from exc

    if os.getenv("PORT"):
        threading.Thread(target=start_health_server, daemon=True).start()

    application = build_application()
    logger.info("SHADYBOT MAX starting…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
