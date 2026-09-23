#!/usr/bin/env python3
"""JARVIS Local (Ultron OS): Realtime voice assistant with Gemini Live & Native PC Control.

Endpoints:
  GET  /              Futuristic UI (Arc reactor orb + system panels)
  GET  /api/config    Voice backend config & capabilities
  WS   /ws/live       Gemini Multimodal Live bidirectional streaming WebSocket
  POST /api/task      Spawns an autonomous background task (Gemini engine)
  GET  /api/task/{id} Polls task status and output
  POST /api/open      Launches desktop applications or websites
  POST /api/open_tab  Opens a new tab in Comet browser (optionally with URL)
  POST /api/close_tab Closes the active tab in browser/app
  POST /api/close_app Closes an app or window by name
  POST /api/hotkey    Sends keyboard shortcuts / media keys to Windows
  POST /api/run_cmd   Executes a PowerShell command
"""
import asyncio
import base64
import copy
import ctypes
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
try:
    from ctypes import wintypes
except Exception:
    wintypes = None
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

import tasks_db
import memory_manager

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

ROOT = Path(__file__).parent
app = FastAPI(title="JARVIS Local - Ultron OS")

# ---------------------------------------------------------------- config

def load_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

load_env()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-native-audio-latest")
GEMINI_VOICE = os.environ.get("GEMINI_VOICE", "Charon")
GEMINI_TASK_MODEL = os.environ.get("GEMINI_TASK_MODEL", "gemini-3.6-flash")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
REALTIME_MODEL = os.environ.get("REALTIME_MODEL", "gpt-realtime")
VOICE = os.environ.get("JARVIS_VOICE", "ballad")
LANGUAGE = os.environ.get("JARVIS_LANGUAGE", "français")

WORKDIR = os.path.expanduser(os.environ.get("JARVIS_WORKDIR", "~"))
PERMISSION_MODE = os.environ.get("JARVIS_PERMISSION_MODE", "bypassPermissions")

# Comet Browser detection
def find_comet_path():
    candidates = [
        r"C:\Program Files\Perplexity\Comet\Application\comet.exe",
        r"C:\Program Files (x86)\Perplexity\Comet\Application\comet.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Perplexity\Comet\Application\comet.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Perplexity\Comet\Application\comet.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

COMET_PATH = find_comet_path()

INSTRUCTIONS = f"""Tu es JARVIS, l'assistant vocal personnel de monsieur, dans
l'esprit du majordome d'Iron Man (système Ultron OS). Tu parles en {LANGUAGE} avec
un LÉGER ACCENT BRITANNIQUE distingué et un flegme impeccable: voix posée, articulation
soignée, débit calme, jamais d'exubérance. Tu t'adresses à l'utilisateur par
"monsieur", avec une courtoisie raffinée et une pointe d'esprit pince-sans-rire
("Très bien, monsieur.", "À vos ordres, monsieur.", "C'est fait, monsieur.").
Réponses COURTES (une ou deux phrases), naturelles, directes et percutantes.
RÉPONSE INSTANTANÉE : Réponds dès la première fraction de seconde où monsieur s'arrête de parler. Ne fais aucune pause ni hésitation inutile.

RÈGLES DU NAVIGATEUR PRINCIPAL (COMET) & ONGLETS :
- Le navigateur principal de monsieur est **Comet** (de Perplexity).
- Pour ouvrir un onglet ou un site ("ouvre un onglet", "ouvre YouTube", "cherche sur Comet"), appelle IMMÉDIATEMENT open_tab (avec l'URL si demandée, ou sans URL pour un onglet vierge).
- Pour fermer un onglet ("ferme cet onglet", "ferme l'onglet"), appelle IMMÉDIATEMENT close_tab.

RÈGLES D'ACTION ET DE CONTRÔLE SUR CE PC :
- Pour fermer une application ("ferme Discord", "quitte Chrome", "ferme Spotify", "ferme le bloc-notes"), appelle close_app.
- Pour lancer une application ("lance Discord", "ouvre Spotify", "ouvre Comet"), appelle open_app.
- Pour manipuler le son ou les fenêtres ("monte le son", "baisse le son", "coupe le son", "pause", "plein écran"), appelle press_hotkey.
- Pour exécuter une commande système sur la machine, appelle run_command.
- Pour des tâches complexes (analyser des fichiers, coder, chercher, créer un document), appelle execute_task.
- Pour afficher des notes ou résultats ponctuels, utilise display_card. Pour des rapports et graphiques interactifs, utilise display_report.

RÈGLES DE GESTION DE TÂCHES, AGENDA & MÉMOIRE :
- Pour ajouter une tâche ("rappelle-moi de...", "ajoute une tâche...", "note qu'il faut faire..."), appelle manage_tasks avec action="add".
- Pour voir les tâches en cours ("quelles sont mes tâches ?", "qu'est-ce que j'ai à faire ?"), appelle manage_tasks avec action="list".
- Pour valider/terminer une tâche ("coche la tâche 1", "tâche terminée"), appelle manage_tasks avec action="complete".
- Pour mémoriser une information durable sur monsieur ou ses préférences ("retiens que...", "mémorise..."), appelle manage_memory avec action="remember".
- Pour le briefing du matin ou de la journée ("briefing du jour", "fais-moi le point", "rapport du matin"), appelle daily_briefing.

Ne prétexte jamais qu'un outil manque: tu as le contrôle direct du PC, de la mémoire, des tâches et de Comet."""

TOOLS = [{
    "type": "function",
    "name": "open_tab",
    "description": "Ouvre un nouvel onglet ou un site dans le navigateur principal de monsieur (Comet). Ouvre directement l'URL demandée si précisée, sinon un nouvel onglet vierge.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL optionnelle à ouvrir dans Comet (ex: 'https://youtube.com', 'https://mail.google.com')"},
        },
    },
}, {
    "type": "function",
    "name": "close_tab",
    "description": "Ferme l'onglet actif du navigateur web ou de l'application active au premier plan (envoie Ctrl+W).",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}, {
    "type": "function",
    "name": "close_app",
    "description": "Ferme une application ou une fenêtre ouverte par son nom (ex: 'chrome', 'discord', 'spotify', 'notepad', 'comet').",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nom de l'application à fermer"},
        },
        "required": ["name"],
    },
}, {
    "type": "function",
    "name": "open_app",
    "description": "Lance une application installée sur ce PC (ex: 'comet', 'discord', 'spotify', 'chrome', 'notepad').",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nom de l'application"},
            "monitor": {"type": "string", "description": "Écran cible ('left', 'right', 'top', 'bottom', 'primary' ou un numéro). Optionnel."},
        },
        "required": ["name"],
    },
}, {
    "type": "function",
    "name": "press_hotkey",
    "description": "Envoie un raccourci clavier ou une commande média au système Windows ('ctrl+w', 'ctrl+t', 'alt+f4', 'volume_up', 'volume_down', 'volume_mute', 'play_pause').",
    "parameters": {
        "type": "object",
        "properties": {
            "hotkey": {"type": "string", "description": "Nom du raccourci à exécuter"},
        },
        "required": ["hotkey"],
    },
}, {
    "type": "function",
    "name": "run_command",
    "description": "Exécute une commande PowerShell sur le système Windows et retourne le résultat textuel.",
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Commande PowerShell à exécuter"},
        },
        "required": ["command"],
    },
}, {
    "type": "function",
    "name": "execute_task",
    "description": "Exécute une tâche complexe de fond sur la machine (analyse de fichiers, écriture de code, recherche, création de documents, automatisation). Tourne en tâche de fond et prévient dès que c'est terminé.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Titre court de la tâche (3-5 mots)"},
            "prompt": {"type": "string", "description": "Instructions complètes et détaillées pour exécuter la tâche"},
        },
        "required": ["title", "prompt"],
    },
}, {
    "type": "function",
    "name": "cancel_task",
    "description": "Annule une tâche de fond en cours.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "ID de la tâche à annuler (optionnel, dernière par défaut)"},
        },
    },
}, {
    "type": "function",
    "name": "display_card",
    "description": "Affiche une carte holographique sur l'écran de JARVIS (résultat, synthèse, extrait de code, mémo).",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Titre de la carte"},
            "content": {"type": "string", "description": "Corps de la carte en markdown léger"},
            "kind": {"type": "string", "enum": ["info", "result", "code", "warning"], "description": "Style visuel"},
        },
        "required": ["title", "content"],
    },
}, {
    "type": "function",
    "name": "display_report",
    "description": "Affiche un tableau de bord complet de données chiffrées (indicateurs clés KPIs, graphique interactif, tableau de données et notes).",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Titre du rapport"},
            "kpis": {"type": "array", "description": "Chiffres clés (max 4)",
                     "items": {"type": "object", "properties": {
                         "label": {"type": "string"},
                         "value": {"type": "string"},
                         "delta": {"type": "string"},
                     }, "required": ["label", "value"]}},
            "chart": {"type": "object", "description": "Graphique", "properties": {
                "type": {"type": "string", "enum": ["line", "bar", "area", "donut"]},
                "categories": {"type": "array", "items": {"type": "string"}},
                "series": {"type": "array", "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "data": {"type": "array", "items": {"type": "number"}},
                }, "required": ["name", "data"]}},
            }},
            "table": {"type": "object", "properties": {
                "columns": {"type": "array", "items": {"type": "string"}},
                "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
            }},
            "markdown": {"type": "string", "description": "Notes d'analyse"},
        },
        "required": ["title"],
    },
}, {
    "type": "function",
    "name": "manage_tasks",
    "description": "Gère les tâches, rappels et to-do list persistante de monsieur dans la base SQLite locale (ajouter, lister, cocher terminée, supprimer, voir statistiques).",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "list", "complete", "delete", "stats"], "description": "Action à effectuer"},
            "title": {"type": "string", "description": "Titre ou libellé de la tâche"},
            "priority": {"type": "string", "enum": ["urgent", "high", "medium", "low"], "description": "Niveau de priorité"},
            "due_date": {"type": "string", "description": "Date d'échéance optionnelle (ex: '2026-09-25')"},
            "task_id": {"type": "integer", "description": "ID de la tâche (pour complete ou delete)"},
            "project": {"type": "string", "description": "Nom du projet ou tag"},
        },
        "required": ["action"],
    },
}, {
    "type": "function",
    "name": "manage_memory",
    "description": "Mémorise ou consulte des faits durables, préférences ou informations importantes sur monsieur dans sa mémoire centrale permanente (MEMORY.md).",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["remember", "recall"], "description": "Action sur la mémoire"},
            "fact": {"type": "string", "description": "Fait, préférence ou consigne à enregistrer"},
        },
        "required": ["action"],
    },
}, {
    "type": "function",
    "name": "daily_briefing",
    "description": "Génère le briefing exécutif complet de monsieur : date, tâches urgentes en cours dans la base de données, faits clés mémorisés et synthèse des dernières actualités en direct.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}]


def get_gemini_tools():
    fn_decls = []
    for t in TOOLS:
        c = copy.deepcopy(t)
        if c["name"] == "display_report":
            c["parameters"]["properties"]["table"]["properties"]["rows"]["items"]["items"] = {"type": "string"}
        fn_decls.append({
            "name": c["name"],
            "description": c["description"],
            "parameters": c["parameters"],
        })
    return [{"function_declarations": fn_decls}]


def get_system_instructions():
    mem = memory_manager.read_memory()
    briefing_context = f"\n\n[MÉMOIRE PERMANENTE & CONTEXTE DE MONSIEUR (MEMORY.md)] :\n{mem}" if mem else ""
    return INSTRUCTIONS + briefing_context


# ---------------------------------------------------------------- Native Task Engine

TASKS: dict = {}
PROCS: dict = {}


def fetch_live_news_context():
    try:
        import urllib.request
        import xml.etree.ElementTree as ET
        req = urllib.request.Request(
            "https://news.google.com/rss?hl=fr&gl=FR&ceid=FR:fr",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            tree = ET.fromstring(resp.read())
            items = tree.findall(".//item")[:10]
            news = [f"- {it.find('title').text}" for it in items if it.find('title') is not None]
            if news:
                return "\n[DÉPÊCHES ET ACTUALITÉS EN DIRECT EN FRANCE ET DANS LE MONDE] :\n" + "\n".join(news) + "\n"
    except Exception:
        pass
    return ""


def _run_task(task_id: str, prompt: str):
    task = TASKS[task_id]
    try:
        claude = shutil.which("claude")
        if claude:
            cmd = [claude, "-p", prompt]
            if PERMISSION_MODE and PERMISSION_MODE.lower() != "off":
                cmd += ["--permission-mode", PERMISSION_MODE]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", cwd=WORKDIR,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            PROCS[task_id] = proc
            try:
                stdout, stderr = proc.communicate(timeout=int(os.environ.get("JARVIS_TASK_TIMEOUT", "600")))
                out = (stdout or "").strip()
                err = (stderr or "").strip()
                task["status"] = "done" if proc.returncode == 0 else "error"
                task["output"] = out if out else err[:2000]
            except subprocess.TimeoutExpired:
                proc.kill()
                task["status"] = "error"
                task["output"] = "Timeout: La session a dépassé la limite de temps."
            return

        if not GEMINI_API_KEY:
            task["status"] = "error"
            task["output"] = "Clé GEMINI_API_KEY absente pour exécuter la tâche."
            return

        gclient = genai.Client(api_key=GEMINI_API_KEY)
        
        # Inject live news if requested
        prompt_lower = prompt.lower()
        effective_prompt = prompt
        if any(w in prompt_lower for w in ("actualit", "actu", "nouvelle", "news", "journal", "titre")):
            live_news = fetch_live_news_context()
            if live_news:
                effective_prompt = f"{live_news}\nDemande de l'utilisateur : {prompt}"

        system_instruction = (
            f"Tu es le moteur d'exécution autonome de JARVIS pour le système Ultron OS sur Windows. "
            f"Répertoire de travail actuel: {WORKDIR}. "
            f"Exécute fidèlement la tâche demandée et fournis un compte-rendu clair, "
            f"synthétique et précis en français. Termine avec les données chiffrées si pertinent."
        )

        candidate_models = [GEMINI_TASK_MODEL, "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
        candidate_models = list(dict.fromkeys(candidate_models))

        last_error = None
        for model_name in candidate_models:
            try:
                response = gclient.models.generate_content(
                    model=model_name,
                    contents=effective_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                    )
                )
                if response and response.text:
                    task["status"] = "done"
                    task["output"] = response.text
                    return
            except Exception as exc:
                last_error = exc
                print(f"Modèle {model_name} indisponible: {exc}, bascule vers le modèle suivant...")
                time.sleep(0.2)
                continue

        task["status"] = "error"
        task["output"] = f"Erreur lors de l'exécution: {str(last_error)}"

    except Exception as exc:
        task["status"] = "error"
        task["output"] = f"Erreur lors de l'exécution: {str(exc)}"
    finally:
        PROCS.pop(task_id, None)
        task["ended"] = time.time()


class TaskIn(BaseModel):
    title: str
    prompt: str


@app.post("/api/task")
def create_task(body: TaskIn):
    task_id = uuid.uuid4().hex[:8]
    TASKS[task_id] = {
        "id": task_id, "title": body.title, "prompt": body.prompt,
        "status": "running", "output": "", "started": time.time(), "ended": None,
    }
    threading.Thread(target=_run_task, args=(task_id, body.prompt), daemon=True).start()
    return {"id": task_id, "status": "running"}


@app.post("/api/task/{task_id}/cancel")
def cancel_task(task_id: str):
    if task_id in ("latest", "last", "-"):
        running = [t for t in TASKS.values() if t["status"] == "running"]
        if not running:
            return {"ok": False, "error": "Aucune tâche en cours."}
        task = max(running, key=lambda t: t["started"])
    else:
        task = TASKS.get(task_id)
        if not task:
            raise HTTPException(404, "Tâche inconnue")
        if task["status"] != "running":
            return {"ok": False, "error": f"La tâche est déjà {task['status']}."}

    task["status"] = "cancelled"
    task["output"] = "Annulée par l'utilisateur."
    proc = PROCS.get(task["id"])
    if proc and proc.poll() is None:
        proc.kill()
    return {"ok": True, "cancelled": task["id"], "title": task["title"]}


@app.get("/api/task/{task_id}")
def get_task(task_id: str):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "Tâche inconnue")
    return task


# ---------------------------------------------------------------- Windows Control & Hotkeys

IS_WINDOWS = os.name == "nt"
user32 = None
kernel32 = None
_MonitorEnumProc = None

if IS_WINDOWS:
    try:
        user32 = getattr(ctypes, "windll", None).user32 if hasattr(ctypes, "windll") else None
        kernel32 = getattr(ctypes, "windll", None).kernel32 if hasattr(ctypes, "windll") else None
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        if wintypes:
            _MonitorEnumProc = ctypes.WINFUNCTYPE(
                ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    except Exception:
        user32 = None
        kernel32 = None
        _MonitorEnumProc = None


def _monitors():
    if not user32 or not _MonitorEnumProc:
        return []
    mons = []
    def cb(hmon, hdc, lprc, lparam):
        r = lprc.contents
        mons.append((r.left, r.top, r.right, r.bottom))
        return 1
    try:
        user32.EnumDisplayMonitors(0, 0, _MonitorEnumProc(cb), 0)
    except Exception:
        pass
    return mons


def _pick_monitor(target: str):
    mons = _monitors()
    if not mons:
        return None
    t = (target or "").strip().lower()
    if t.isdigit():
        i = int(t) - 1
        return mons[i] if 0 <= i < len(mons) else None
    key = {
        "left": lambda m: m[0], "gauche": lambda m: m[0],
        "top": lambda m: m[1], "haut": lambda m: m[1],
    }
    if t in key:
        return min(mons, key=key[t])
    key = {
        "right": lambda m: m[2], "droite": lambda m: m[2], "droit": lambda m: m[2],
        "bottom": lambda m: m[3], "bas": lambda m: m[3],
    }
    if t in key:
        return max(mons, key=key[t])
    for m in mons:
        if m[0] <= 0 < m[2] and m[1] <= 0 < m[3]:
            return m
    return mons[0]


def ensure_default_desktop():
    if not user32:
        return None
    try:
        hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
            return hdesk
    except Exception:
        pass
    return None


def focus_comet_window():
    if not user32 or not wintypes:
        return None
    SW_RESTORE = 9
    hdesk = ensure_default_desktop()

    comet_pids = set()
    try:
        raw_pids = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "(Get-Process comet -ErrorAction SilentlyContinue).Id"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        ).decode().split()
        for p in raw_pids:
            if p.strip().isdigit():
                comet_pids.add(int(p.strip()))
    except Exception:
        pass

    found = []
    _EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in comet_pids or "comet" in title.lower():
                if length > 0:
                    found.append(hwnd)
        return True

    if hdesk:
        user32.EnumDesktopWindows(hdesk, _EnumWindowsProc(cb), 0)
    else:
        user32.EnumWindows(_EnumWindowsProc(cb), 0)

    if found:
        target_hwnd = found[0]
        try:
            fore_hwnd = user32.GetForegroundWindow()
            cur_tid = kernel32.GetCurrentThreadId()
            fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None)
            if cur_tid != fore_tid:
                user32.AttachThreadInput(cur_tid, fore_tid, True)

            VK_MENU = 0x12
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            user32.ShowWindow(target_hwnd, SW_RESTORE)
            user32.SetForegroundWindow(target_hwnd)
            user32.BringWindowToTop(target_hwnd)

            if cur_tid != fore_tid:
                user32.AttachThreadInput(cur_tid, fore_tid, False)
        except Exception:
            pass
        return True
    return False


def do_open_tab(url: str = ""):
    """Open a new tab in Comet browser (or default browser if Comet missing)."""
    target = url.strip()
    if target and not target.startswith(("http://", "https://", "chrome://", "about:")):
        target = "https://" + target

    if COMET_PATH and os.path.exists(COMET_PATH):
        if target:
            subprocess.Popen([COMET_PATH, target])
            time.sleep(0.15)
            focus_comet_window()
            return {"ok": True, "browser": "Comet", "url": target, "message": f"Nouvel onglet ouvert dans Comet : {target}"}
        else:
            # Blank tab: focus Comet window and send native Ctrl+T
            focused = focus_comet_window()
            if focused:
                time.sleep(0.12)
                VK_CONTROL = 0x11
                VK_T = 0x54
                KEYEVENTF_KEYUP = 0x0002
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_T, 0, 0, 0)
                time.sleep(0.04)
                user32.keybd_event(VK_T, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                return {"ok": True, "browser": "Comet", "message": "Nouvel onglet vierge ouvert dans Comet (Ctrl+T)."}
            else:
                subprocess.Popen([COMET_PATH])
                return {"ok": True, "browser": "Comet", "message": "Comet lancé avec un nouvel onglet."}
    else:
        import webbrowser
        webbrowser.open(target or "about:blank")
        return {"ok": True, "browser": "default", "url": target, "message": f"Nouvel onglet ouvert : {target}"}


def do_close_tab():
    """Simulate Ctrl+W to close active tab in Comet or active window."""
    if not user32:
        return {"ok": False, "message": "Contrôle d'onglets non disponible sur serveur distant (nécessite le mode local Windows)."}
    ensure_default_desktop()
    focus_comet_window()
    time.sleep(0.08)
    VK_CONTROL = 0x11
    VK_W = 0x57
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(VK_W, 0, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    return {"ok": True, "message": "Onglet fermé dans Comet (Ctrl+W envoyé)."}


def do_close_app(name: str):
    """Close application or window by name."""
    if not user32:
        return {"ok": False, "message": "Fermeture d'application non disponible sur serveur distant."}
    q = name.strip().lower()
    WM_CLOSE = 0x0010
    closed_titles = []
    hdesk = ensure_default_desktop()

    _EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                t = buf.value
                if q in t.lower():
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    closed_titles.append(t)
        return True

    if hdesk:
        user32.EnumDesktopWindows(hdesk, _EnumWindowsProc(cb), 0)
    else:
        user32.EnumWindows(_EnumWindowsProc(cb), 0)

    if closed_titles:
        return {"ok": True, "message": f"Fermeture de {len(closed_titles)} fenêtre(s) : {', '.join(closed_titles)}"}

    # Fallback: stop process with PowerShell
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Get-Process -ErrorAction SilentlyContinue | Where-Object {{ $_.ProcessName -like '*{q}*' }} | Stop-Process -Force"],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    return {"ok": True, "message": f"Fermeture du processus '{name}' effectuée."}


def do_press_hotkey(hotkey: str):
    """Send Windows hotkeys and media keys."""
    if not user32:
        return {"ok": False, "message": "Raccourcis Windows non disponibles sur serveur distant."}
    ensure_default_desktop()
    h = hotkey.lower().strip()
    KEYEVENTF_KEYUP = 0x0002

    if h in ("ctrl+w", "close_tab", "fermer_onglet"):
        return do_close_tab()
    elif h in ("ctrl+t", "new_tab", "nouvel_onglet"):
        return do_open_tab("")
    elif h in ("alt+f4", "close_window"):
        VK_MENU = 0x12
        VK_F4 = 0x73
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_F4, 0, 0, 0)
        time.sleep(0.04)
        user32.keybd_event(VK_F4, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        return {"ok": True, "message": "Fenêtre fermée (Alt+F4)"}
    elif h in ("volume_mute", "mute"):
        VK_VOLUME_MUTE = 0xAD
        user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
        user32.keybd_event(VK_VOLUME_MUTE, 0, KEYEVENTF_KEYUP, 0)
        return {"ok": True, "message": "Volume coupé / rétabli"}
    elif h in ("volume_up", "plus_fort"):
        VK_VOLUME_UP = 0xAF
        for _ in range(4):
            user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
            user32.keybd_event(VK_VOLUME_UP, 0, KEYEVENTF_KEYUP, 0)
        return {"ok": True, "message": "Volume augmenté"}
    elif h in ("volume_down", "moins_fort"):
        VK_VOLUME_DOWN = 0xAE
        for _ in range(4):
            user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
            user32.keybd_event(VK_VOLUME_DOWN, 0, KEYEVENTF_KEYUP, 0)
        return {"ok": True, "message": "Volume diminué"}
    elif h in ("play_pause", "media_play_pause", "pause"):
        VK_MEDIA_PLAY_PAUSE = 0xB3
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
        user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_KEYUP, 0)
        return {"ok": True, "message": "Lecture / Pause média"}
    else:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{h}')"],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return {"ok": True, "message": f"Raccourci '{h}' envoyé."}


def do_run_command(command: str):
    """Execute a command on the host (PowerShell on Windows, sh on Linux)."""
    try:
        if shutil.which("powershell"):
            cmd = ["powershell", "-NoProfile", "-Command", command]
        else:
            cmd = ["/bin/sh", "-c", command]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip()
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------- App & URL launch

START_MENU_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]


def _find_shortcut(name: str):
    q = name.lower().strip()
    best, best_score = None, 0.0
    for root in START_MENU_DIRS:
        if not root.is_dir():
            continue
        for lnk in root.rglob("*.lnk"):
            stem = lnk.stem.lower()
            if q == stem:
                return lnk
            score = 0.0
            if q in stem:
                score = 2 + len(q) / len(stem)
            elif all(w in stem for w in q.split()):
                score = 1
            if any(bad in stem for bad in ("uninstall", "désinstaller", "readme", "website")):
                score -= 2
            if score > best_score:
                best, best_score = lnk, score
    return best


class OpenIn(BaseModel):
    name: str = ""
    url: str | None = None
    monitor: str | None = None


class TabIn(BaseModel):
    url: str = ""


class CloseIn(BaseModel):
    name: str = ""


class HotkeyIn(BaseModel):
    hotkey: str


class CmdIn(BaseModel):
    command: str


@app.post("/api/open_tab")
def api_open_tab(body: TabIn):
    return do_open_tab(body.url)


@app.post("/api/close_tab")
def api_close_tab():
    return do_close_tab()


@app.post("/api/close_app")
def api_close_app(body: CloseIn):
    return do_close_app(body.name)


@app.post("/api/hotkey")
def api_hotkey(body: HotkeyIn):
    return do_press_hotkey(body.hotkey)


@app.post("/api/run_cmd")
def api_run_cmd(body: CmdIn):
    return do_run_command(body.command)


class TaskManageIn(BaseModel):
    action: str
    title: str = ""
    priority: str = "medium"
    due_date: str | None = None
    project: str = ""
    task_id: int | None = None


class MemoryIn(BaseModel):
    action: str
    fact: str = ""


@app.post("/api/tasks/manage")
def api_manage_tasks(body: TaskManageIn):
    act = body.action.lower().strip()
    if act == "add":
        if not body.title:
            raise HTTPException(400, "Titre manquant pour ajouter une tâche.")
        res = tasks_db.add_task(body.title, priority=body.priority, due_date=body.due_date, project=body.project)
        memory_manager.append_today_log(f"Nouvelle tâche ajoutée : {body.title}")
        return res
    elif act == "list":
        tasks = tasks_db.list_tasks(status="pending")
        stats = tasks_db.get_task_stats()
        return {"ok": True, "tasks": tasks, "stats": stats}
    elif act == "complete":
        if not body.task_id:
            raise HTTPException(400, "task_id manquant.")
        res = tasks_db.complete_task(body.task_id)
        memory_manager.append_today_log(f"Tâche #{body.task_id} terminée.")
        return res
    elif act == "delete":
        if not body.task_id:
            raise HTTPException(400, "task_id manquant.")
        return tasks_db.delete_task(body.task_id)
    elif act == "stats":
        return {"ok": True, "stats": tasks_db.get_task_stats()}
    else:
        raise HTTPException(400, f"Action '{act}' inconnue.")


@app.post("/api/memory/manage")
def api_manage_memory(body: MemoryIn):
    act = body.action.lower().strip()
    if act == "remember":
        return memory_manager.remember_fact(body.fact)
    elif act == "recall":
        return {"ok": True, "memory": memory_manager.read_memory()}
    else:
        raise HTTPException(400, f"Action '{act}' inconnue.")


@app.get("/api/briefing")
def api_daily_briefing():
    return memory_manager.get_executive_briefing()


@app.post("/api/open")
def open_app(body: OpenIn):
    name = body.name.strip()
    if body.url:
        return do_open_tab(body.url)

    if not name:
        raise HTTPException(400, "Nom d'application ou URL manquant.")

    # Check Comet specifically
    if name.lower() in ("comet", "navigateur", "browser"):
        return do_open_tab("")

    lnk = _find_shortcut(name)
    if lnk:
        os.startfile(lnk)  # noqa: S606
        return {"ok": True, "launched": lnk.stem}
    exe = shutil.which(name) or shutil.which(name + ".exe")
    if not exe:
        try:
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    key = winreg.OpenKey(hive, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{name}.exe")
                    exe = winreg.QueryValueEx(key, None)[0].strip('"')
                    break
                except OSError:
                    continue
        except ImportError:
            pass
    if not exe:
        return {"ok": False, "error": f"Application '{name}' introuvable sur ce PC."}
    try:
        subprocess.Popen([exe], cwd=str(Path(exe).parent))
        return {"ok": True, "launched": Path(exe).stem}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------- config endpoint

@app.get("/api/config")
def get_config():
    backend = "gemini" if GEMINI_API_KEY else ("openai" if OPENAI_API_KEY else "none")
    return {
        "backend": backend,
        "browser": "Comet" if COMET_PATH else "Défaut",
        "gemini_model": GEMINI_MODEL,
        "gemini_voice": GEMINI_VOICE,
        "openai_model": REALTIME_MODEL,
        "openai_voice": VOICE,
        "has_gemini": bool(GEMINI_API_KEY),
        "has_openai": bool(OPENAI_API_KEY),
    }


# ---------------------------------------------------------------- Gemini Live WebSocket

@app.websocket("/ws/live")
async def websocket_gemini_live(ws: WebSocket):
    await ws.accept()

    if not GEMINI_API_KEY:
        await ws.send_json({
            "type": "error",
            "message": "GEMINI_API_KEY manquant: ajoute ta clé dans le fichier .env."
        })
        await ws.close()
        return

    if not genai:
        await ws.send_json({
            "type": "error",
            "message": "Le package google-genai n'est pas installé."
        })
        await ws.close()
        return

    client = genai.Client(api_key=GEMINI_API_KEY, http_options={"api_version": "v1alpha"})

    config = {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {"voice_name": GEMINI_VOICE}
            }
        },
        "system_instruction": {"parts": [{"text": get_system_instructions()}]},
        "tools": get_gemini_tools(),
    }

    try:
        async with client.aio.live.connect(model=GEMINI_MODEL, config=config) as gemini_session:
            await ws.send_json({
                "type": "ready",
                "model": GEMINI_MODEL,
                "voice": GEMINI_VOICE,
                "browser": "Comet",
            })

            async def browser_to_gemini():
                try:
                    while True:
                        msg = await ws.receive()
                        if "bytes" in msg and msg["bytes"]:
                            await gemini_session.send_realtime_input(
                                audio=types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000")
                            )
                        elif "text" in msg and msg["text"]:
                            data = json.loads(msg["text"])
                            mtype = data.get("type")
                            if mtype == "tool_response":
                                call_id = data.get("id")
                                call_name = data.get("name")
                                output = data.get("output", {})
                                await gemini_session.send_tool_response(
                                    function_responses=[{
                                        "name": call_name,
                                        "id": call_id,
                                        "response": {"output": output}
                                    }]
                                )
                            elif mtype == "client_message":
                                text = data.get("text", "")
                                await gemini_session.send_client_content(
                                    turns=[{"role": "user", "parts": [{"text": text}]}],
                                    turn_complete=True
                                )
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    print("browser_to_gemini exception:", e)

            async def gemini_to_browser():
                try:
                    while True:
                        async for response in gemini_session.receive():
                            if response.server_content:
                                sc = response.server_content
                                if sc.interrupted:
                                    await ws.send_json({"type": "interrupted"})
                                if sc.model_turn:
                                    for part in sc.model_turn.parts:
                                        if part.text:
                                            await ws.send_json({"type": "text", "text": part.text})
                                        if part.inline_data:
                                            b64 = base64.b64encode(part.inline_data.data).decode("utf-8")
                                            await ws.send_json({
                                                "type": "audio",
                                                "data": b64,
                                                "mime_type": part.inline_data.mime_type or "audio/pcm;rate=24000"
                                            })
                                if sc.turn_complete:
                                    await ws.send_json({"type": "turn_complete"})

                            if response.tool_call:
                                for call in response.tool_call.function_calls:
                                    await ws.send_json({
                                        "type": "tool_call",
                                        "id": call.id,
                                        "name": call.name,
                                        "args": call.args or {}
                                    })
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print("gemini_to_browser exception:", e)
                    try:
                        await ws.send_json({"type": "error", "message": str(e)})
                    except Exception:
                        pass

            c_task = asyncio.create_task(browser_to_gemini())
            p_task = asyncio.create_task(gemini_to_browser())
            done, pending = await asyncio.wait([c_task, p_task], return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()

    except Exception as e:
        print("Gemini live connection error:", e)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
            await ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------- OpenAI realtime session (fallback)

@app.post("/api/session")
def create_session():
    if not OPENAI_API_KEY:
        raise HTTPException(500, "OPENAI_API_KEY manquant dans .env")
    payload = {
        "session": {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "instructions": INSTRUCTIONS,
            "tools": TOOLS,
            "audio": {
                "input": {"transcription": {"model": "whisper-1"}},
                "output": {"voice": VOICE},
            },
        }
    }
    r = httpx.post(
        "https://api.openai.com/v1/realtime/client_secrets",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                 "Content-Type": "application/json"},
        json=payload, timeout=30,
    )
    if r.status_code >= 400:
        raise HTTPException(r.status_code, f"OpenAI: {r.text[:300]}")
    data = r.json()
    return {"client_secret": data["value"], "model": REALTIME_MODEL}


# ---------------------------------------------------------------- static & health

@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "service": "JARVIS Ultron OS", "version": "2.0"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", os.environ.get("JARVIS_PORT", "8788")))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"\n  JARVIS (Ultron OS) running on http://{host}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")
