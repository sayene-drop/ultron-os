"""Native Task Database Manager for Ultron OS.
Adapted from AI OS Local Edition (Thomas Berton).
Provides SQLite CRUD operations and statistics for persistent task management.
"""
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent / "data" / "tasks.db"


def get_connection():
    """Get or create database connection with tasks table."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'medium',
            due_date TEXT,
            project TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        )
    """)
    conn.commit()
    return conn


def add_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    due_date: Optional[str] = None,
    project: str = "",
    tags: str = ""
) -> Dict[str, Any]:
    """Add a new task."""
    p = priority.lower().strip()
    if p not in ("high", "medium", "low", "urgent"):
        p = "medium"

    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO tasks (title, description, priority, due_date, project, tags)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (title.strip(), description.strip(), p, due_date.strip() if due_date else None,
         project.strip(), tags.strip())
    )
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return {
        "ok": True,
        "action": "added",
        "id": task_id,
        "title": title.strip(),
        "priority": p,
        "due_date": due_date,
        "message": f"Tâche #{task_id} créée : '{title.strip()}' (priorité: {p})"
    }


def list_tasks(
    status: Optional[str] = "pending",
    priority: Optional[str] = None,
    project: Optional[str] = None,
    overdue_only: bool = False,
    limit: int = 15
) -> List[Dict[str, Any]]:
    """List tasks with optional filters."""
    conn = get_connection()
    query = "SELECT * FROM tasks WHERE 1=1"
    params: List[Any] = []

    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
    else:
        query += " AND status != 'deleted'"

    if priority:
        query += " AND priority = ?"
        params.append(priority.lower())

    if project:
        query += " AND project LIKE ?"
        params.append(f"%{project}%")

    if overdue_only:
        today = datetime.now().strftime("%Y-%m-%d")
        query += " AND due_date < ? AND status = 'pending'"
        params.append(today)

    query += """
        ORDER BY
            CASE WHEN due_date < date('now') AND status = 'pending' THEN 0 ELSE 1 END,
            CASE WHEN due_date IS NULL THEN 1 ELSE 0 END,
            due_date,
            CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        LIMIT ?
    """
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def complete_task(task_id: int) -> Dict[str, Any]:
    """Mark a task as completed."""
    conn = get_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
        (now_str, task_id)
    )
    conn.commit()
    found = cur.rowcount > 0
    row = None
    if found:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()

    if not found:
        return {"ok": False, "error": f"Tâche #{task_id} introuvable."}
    return {
        "ok": True,
        "action": "completed",
        "id": task_id,
        "title": row["title"] if row else "",
        "message": f"Tâche #{task_id} ('{row['title'] if row else ''}') marquée comme terminée !"
    }


def delete_task(task_id: int) -> Dict[str, Any]:
    """Delete a task (soft delete)."""
    conn = get_connection()
    cur = conn.execute("UPDATE tasks SET status = 'deleted' WHERE id = ?", (task_id,))
    conn.commit()
    found = cur.rowcount > 0
    conn.close()
    return {
        "ok": found,
        "action": "deleted",
        "id": task_id,
        "message": f"Tâche #{task_id} supprimée." if found else f"Tâche #{task_id} introuvable."
    }


def get_task_stats() -> Dict[str, Any]:
    """Get overview statistics of tasks."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM tasks WHERE status != 'deleted'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'").fetchone()[0]
    done = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'done'").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    overdue = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE due_date < ? AND status = 'pending'", (today,)
    ).fetchone()[0]
    conn.close()
    return {
        "total": total,
        "pending": pending,
        "done": done,
        "overdue": overdue,
    }
