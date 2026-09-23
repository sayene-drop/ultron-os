"""Persistent Memory & Briefing Manager for Ultron OS.
Adapted from AI OS Local Edition (Thomas Berton).
Manages long-term curated facts (MEMORY.md), daily logs, and executive briefings.
"""
from datetime import datetime
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import tasks_db

MEMORY_DIR = Path(__file__).parent / "memory"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
LOGS_DIR = MEMORY_DIR / "logs"


def init_memory():
    """Ensure memory directory and today's log exist."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_log = LOGS_DIR / f"{today_str}.md"
    if not today_log.exists():
        today_log.write_text(
            f"# Journal de Bord du {today_str}\n\n## Actions & Événements\n- Session JARVIS initialisée.\n",
            encoding="utf-8"
        )


def read_memory() -> str:
    """Read the full content of MEMORY.md."""
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text(encoding="utf-8")
    return ""


def append_today_log(entry: str):
    """Append a notable action or memory event to today's daily log."""
    init_memory()
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")
    today_log = LOGS_DIR / f"{today_str}.md"
    try:
        with open(today_log, "a", encoding="utf-8") as f:
            f.write(f"- [{now_time}] {entry.strip()}\n")
    except Exception as e:
        print("append_today_log error:", e)


def remember_fact(fact: str, category: str = "Faits Durables") -> Dict[str, Any]:
    """Append a permanent fact into MEMORY.md and log it."""
    fact_clean = fact.strip()
    if not fact_clean:
        return {"ok": False, "error": "Le fait à mémoriser est vide."}

    content = read_memory()
    date_tag = datetime.now().strftime("%d/%m/%Y")
    new_entry = f"- {fact_clean} *(enregistré le {date_tag})*"

    # Look for section header
    header = f"## 5. Faits Durables & Notes Mémorisées"
    if header in content:
        parts = content.split(header, 1)
        updated = f"{parts[0]}{header}\n{new_entry}{parts[1]}"
    else:
        updated = f"{content}\n\n## Notes Mémorisées\n{new_entry}\n"

    MEMORY_FILE.write_text(updated, encoding="utf-8")
    append_today_log(f"Mémoire mise à jour : {fact_clean}")

    return {
        "ok": True,
        "action": "remembered",
        "fact": fact_clean,
        "message": f"C'est mémorisé, monsieur : « {fact_clean} »."
    }


def fetch_live_news(limit: int = 5) -> List[str]:
    """Fetch live news headlines via RSS."""
    try:
        req = urllib.request.Request(
            "https://news.google.com/rss?hl=fr&gl=FR&ceid=FR:fr",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            tree = ET.fromstring(resp.read())
            items = tree.findall(".//item")[:limit]
            return [it.find("title").text for it in items if it.find("title") is not None]
    except Exception:
        return []


def get_executive_briefing() -> Dict[str, Any]:
    """Compile a complete executive morning / daily briefing."""
    init_memory()
    stats = tasks_db.get_task_stats()
    pending = tasks_db.list_tasks(status="pending", limit=5)
    news = fetch_live_news(limit=4)

    tasks_summary = [
        f"#{t['id']} [{t['priority'].upper()}] {t['title']}" + (f" (pour le {t['due_date']})" if t['due_date'] else "")
        for t in pending
    ]

    now = datetime.now()
    date_display = now.strftime("%A %d %B %Y").capitalize()

    return {
        "date": date_display,
        "time": now.strftime("%H:%M"),
        "task_stats": stats,
        "urgent_tasks": tasks_summary,
        "top_news": news,
        "total_pending": stats["pending"],
        "overdue_count": stats["overdue"],
    }
