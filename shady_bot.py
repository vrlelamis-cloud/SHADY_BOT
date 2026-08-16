import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Salut !\n\n"
        "Je suis ton bot Telegram personnel.\n"
        "Le bot fonctionne correctement 🤖"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Commandes disponibles :\n\n"
        "/start - Démarrer le bot\n"
        "/help - Afficher l'aide"
    )

def main():
    if not TOKEN:
        raise ValueError("La variable BOT_TOKEN n'est pas configurée.")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    print("🤖 Bot démarré...")
    app.run_polling()

if __name__ == "__main__":
    main()
