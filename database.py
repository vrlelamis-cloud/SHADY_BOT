"""
Gestion de la base de données SQLite
Stockage des utilisateurs, groupes, avertissements, tâches, logs
"""
import aiosqlite
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import Config

class Database:
    def __init__(self, db_path: str = Config.DATABASE_PATH):
        self.db_path = db_path

    async def init(self):
        """Initialise la base de données avec toutes les tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Table des utilisateurs
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language TEXT DEFAULT 'fr',
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_blocked INTEGER DEFAULT 0,
                    metadata TEXT DEFAULT '{}'
                )
            """)

            # Table des groupes
            await db.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    group_id INTEGER PRIMARY KEY,
                    group_name TEXT,
                    group_type TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    settings TEXT DEFAULT '{}',
                    rules TEXT DEFAULT '',
                    welcome_message TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 1
                )
            """)

            # Table des avertissements (warnings)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    group_id INTEGER,
                    reason TEXT,
                    warned_by INTEGER,
                    warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

            # Table des tâches planifiées
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT,
                    target_id INTEGER,
                    content TEXT,
                    schedule_time TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    executed_at TIMESTAMP
                )
            """)

            # Table des logs d'activité
            await db.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    chat_id INTEGER,
                    action TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table des messages filtrés/bloqués
            await db.execute("""
                CREATE TABLE IF NOT EXISTS filtered_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    group_id INTEGER,
                    message_text TEXT,
                    filter_type TEXT,
                    action_taken TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.commit()

    # --- UTILISATEURS ---
    async def add_user(self, user_id: int, username: str, first_name: str, last_name: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, last_activity)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, datetime.now()))
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_all_users(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE is_blocked = 0") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def block_user(self, user_id: int, block: bool = True):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_blocked = ? WHERE user_id = ?", (1 if block else 0, user_id))
            await db.commit()

    # --- GROUPES ---
    async def add_group(self, group_id: int, group_name: str, group_type: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO groups (group_id, group_name, group_type)
                VALUES (?, ?, ?)
            """, (group_id, group_name, group_type))
            await db.commit()

    async def get_group_settings(self, group_id: int) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT settings FROM groups WHERE group_id = ?", (group_id,)) as cursor:
                row = await cursor.fetchone()
                return json.loads(row[0]) if row and row[0] else {}

    async def update_group_settings(self, group_id: int, settings: Dict):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE groups SET settings = ? WHERE group_id = ?
            """, (json.dumps(settings), group_id))
            await db.commit()

    async def set_group_rules(self, group_id: int, rules: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE groups SET rules = ? WHERE group_id = ?", (rules, group_id))
            await db.commit()

    async def get_group_rules(self, group_id: int) -> str:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT rules FROM groups WHERE group_id = ?", (group_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else ""

    # --- WARNINGS ---
    async def add_warning(self, user_id: int, group_id: int, reason: str, warned_by: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO warnings (user_id, group_id, reason, warned_by)
                VALUES (?, ?, ?, ?)
            """, (user_id, group_id, reason, warned_by))
            await db.commit()

    async def get_warnings(self, user_id: int, group_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT COUNT(*) FROM warnings WHERE user_id = ? AND group_id = ?
            """, (user_id, group_id)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def clear_warnings(self, user_id: int, group_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM warnings WHERE user_id = ? AND group_id = ?", (user_id, group_id))
            await db.commit()

    async def get_warning_history(self, user_id: int) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM warnings WHERE user_id = ? ORDER BY warned_at DESC
            """, (user_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # --- TÂCHES PLANIFIÉES ---
    async def add_task(self, task_type: str, target_id: int, content: str, schedule_time: datetime) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO scheduled_tasks (task_type, target_id, content, schedule_time)
                VALUES (?, ?, ?, ?)
            """, (task_type, target_id, content, schedule_time))
            await db.commit()
            return cursor.lastrowid

    async def get_pending_tasks(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM scheduled_tasks 
                WHERE status = 'pending' AND schedule_time <= ?
                ORDER BY schedule_time ASC
            """, (datetime.now(),)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def mark_task_executed(self, task_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE scheduled_tasks SET status = 'executed', executed_at = ? WHERE id = ?
            """, (datetime.now(), task_id))
            await db.commit()

    async def cancel_task(self, task_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE scheduled_tasks SET status = 'cancelled' WHERE id = ?", (task_id,))
            await db.commit()

    async def get_all_tasks(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM scheduled_tasks ORDER BY created_at DESC") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # --- LOGS ---
    async def log_activity(self, user_id: int, chat_id: int, action: str, details: str = ""):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO activity_logs (user_id, chat_id, action, details)
                VALUES (?, ?, ?, ?)
            """, (user_id, chat_id, action, details))
            await db.commit()

    async def get_recent_logs(self, limit: int = 50) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM activity_logs ORDER BY timestamp DESC LIMIT ?
            """, (limit,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # --- MESSAGES FILTRÉS ---
    async def log_filtered_message(self, user_id: int, group_id: int, message_text: str, filter_type: str, action_taken: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO filtered_messages (user_id, group_id, message_text, filter_type, action_taken)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, group_id, message_text, filter_type, action_taken))
            await db.commit()

    # --- STATISTIQUES ---
    async def get_stats(self) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            stats = {}

            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                stats['total_users'] = (await cursor.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM groups") as cursor:
                stats['total_groups'] = (await cursor.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM warnings") as cursor:
                stats['total_warnings'] = (await cursor.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM scheduled_tasks WHERE status = 'pending'") as cursor:
                stats['pending_tasks'] = (await cursor.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM activity_logs") as cursor:
                stats['total_logs'] = (await cursor.fetchone())[0]

            return stats
