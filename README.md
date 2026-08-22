# 🤖 UltraBot - Bot Telegram Intelligent

Un bot Telegram complet avec recherche web, modération de groupe, planification de tâches, administration et protection de la vie privée.

---

## ✨ Fonctionnalités

### 🔍 Recherche Web
- `/search <requête>` - Recherche sur le web via DuckDuckGo
- `/news <sujet>` - Recherche d'actualités
- `/fetch <url>` - Extraction de contenu de page web
- `/images <requête>` - Lien de recherche d'images

### 👥 Modération de Groupe
- `/warn @user <raison>` - Avertir un membre
- `/unwarn @user` - Retirer les avertissements
- `/mute @user <durée>` - Rendre muet (ex: 1h, 30m)
- `/unmute @user` - Démuet
- `/ban @user <raison>` - Bannir
- `/unban <user_id>` - Débannir
- `/kick @user` - Expulser
- `/info @user` - Informations sur un membre
- **Modération automatique** configurable

### 📢 Diffusion & Planification
- `/broadcast <message>` - Diffuser à tous les utilisateurs
- `/schedule` - Planifier un message (conversation interactive)
- `/tasks` - Voir les tâches planifiées
- `/cancel <id>` - Annuler une tâche

### ⚙️ Administration
- `/stats` - Statistiques du bot
- `/users` - Liste des utilisateurs
- `/logs` - Derniers logs d'activité
- `/settings` - Paramètres du groupe (boutons interactifs)
- `/rules` & `/setrules` - Gestion des règles

### 🔒 Confidentialité
- `/privacy` - Politique de confidentialité
- `/export_data` - Exporter ses données personnelles
- `/delete_my_data` - Supprimer ses données

### Autres
- `/start`, `/help`, `/ping`, `/id`, `/about`
- Message de bienvenue automatique
- Filtres de mots personnalisables
- Logs d'activité complets
- Base de données SQLite

---

## 🚀 Installation

### 1. Prérequis
- Python 3.9+
- pip

### 2. Cloner / Télécharger le projet
```bash
cd telegram_bot
```

### 3. Créer un environnement virtuel (recommandé)
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 4. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 5. Configurer le bot
```bash
cp .env.example .env
```

Éditez le fichier `.env` avec vos informations :
```
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxyz
ADMIN_IDS=123456789
```

**Obtenir le token :**
1. Allez sur Telegram, cherchez `@BotFather`
2. Envoyez `/newbot`
3. Suivez les instructions
4. Copiez le token dans `.env`

**Obtenir votre ID :**
1. Allez sur Telegram, cherchez `@userinfobot`
2. Envoyez `/start`
3. Copiez votre ID dans `ADMIN_IDS`

### 6. Lancer le bot
```bash
python main.py
```

---

## 📁 Structure du projet

```
telegram_bot/
├── main.py           # Point d'entrée principal
├── config.py         # Configuration
├── database.py       # Gestion SQLite
├── web_search.py     # Moteur de recherche
├── moderation.py     # Système de modération
├── requirements.txt  # Dépendances
├── .env.example      # Exemple de configuration
├── .env              # Configuration (à créer)
├── bot_data.db       # Base de données (créée auto)
└── bot.log           # Fichier de logs
```

---

## 🛠️ Déploiement

### Hébergement gratuit (Recommandé)

#### Option 1: Render.com
1. Créez un compte sur [render.com](https://render.com)
2. Créez un nouveau Web Service
3. Connectez votre repo GitHub ou uploadez les fichiers
4. Définissez la commande de démarrage : `python main.py`
5. Ajoutez les variables d'environnement (BOT_TOKEN, ADMIN_IDS)

#### Option 2: Railway.app
1. Créez un compte sur [railway.app](https://railway.app)
2. Déployez depuis GitHub
3. Configurez les variables d'environnement

#### Option 3: PythonAnywhere
1. Créez un compte sur [pythonanywhere.com](https://pythonanywhere.com)
2. Uploadez les fichiers
3. Créez un console et lancez `python main.py`

---

## ⚙️ Configuration avancée

### Modération automatique
Activez/désactivez via `/settings` dans votre groupe :
- 🤖 Modération automatique
- 👋 Message de bienvenue
- 🔗 Anti-liens
- 🖼️ Anti-spam

### Filtres personnalisés
```
/addfilter mot_interdit
/delfilter mot_interdit
/filters
```

### Planification de messages
```
/schedule
→ Envoyez: Bonjour | 2024-12-25 10:00
```

---

## 🔒 Sécurité

- Les commandes admin sont protégées par ID
- Les commandes de groupe nécessitent le statut admin
- Les données utilisateur sont stockées localement
- Conformité RGPD avec export/suppression de données

---

## 📝 Licence

Projet open-source. Libre d'utilisation et de modification.

---

## 🆘 Support

En cas de problème :
1. Vérifiez les logs dans `bot.log`
2. Vérifiez que le token est correct
3. Assurez-vous que le bot a les droits d'admin dans les groupes
