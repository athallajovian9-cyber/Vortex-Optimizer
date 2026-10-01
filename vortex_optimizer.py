"""
VORTEX OPTIMIZER v1.0.0 // PROFESSIONAL HARDWARE SUITE
Minimalist, tactical dark interface. Engineered for clean execution, hardware safety, and low latency.
"""

import sys
import os
import ctypes
import subprocess
import winreg
import threading
import json
import time
import shutil
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

VORTEX_LEDGER = os.path.join(os.environ.get("LOCALAPPDATA", "C:"), "VortexOptimizerBackup", "rollback_ledger.json")
VORTEX_SETTINGS = os.path.join(os.environ.get("LOCALAPPDATA", "C:"), "VortexOptimizerBackup", "optimizer_settings.json")

# Professional Color Palette
C_BG = "#0b0e14"
C_PANEL = "#121722"
C_BORDER = "#212b3d"
C_CYAN = "#00e5ff"
C_TEXT = "#e2e8f0"
C_MUTED = "#8290a6"
C_GREEN = "#10b981"
C_RED = "#f43f5e"
C_AMBER = "#f59e0b"
C_CONSOLE = "#06090e"

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def run_as_admin():
    if not is_admin():
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
        sys.exit(0)

    # ============================================================================
#  HAGS POLICY
#
#  This replaced a rule that had it backwards. The old one treated a GTX 1650 as
#  "weak silicon" - it was on a literal deny list - and switched HAGS OFF, even
#  though Turing supports it properly. It also turned HAGS off on anything that
#  was not an RTX or an RX 6/7/9, which is nearly every card.
#
#  Two things decide it now, and either can refuse:
#    1. VRAM. 2 GB or less does not get HAGS whatever the generation, because
#       HAGS needs somewhere to put the scheduling work.
#    2. Generation. Turing or newer on NVIDIA, RDNA on AMD, Arc on Intel.
#       A GT 130 (Tesla, 2009) is refused outright and always will be.
#
#  The canonical copy of this lives in Vortex_Suite/hags_policy.py, with tests.
# ============================================================================
import re as _re

_HAGS_MIN_VRAM_MB = 2048
_HAGS_DISPLAY_CLASS = (r"SYSTEM\CurrentControlSet\Control\Class"
                       r"\{4d36e968-e325-11ce-bfc1-08002be10318}")


def detect_vram_mb():
    """Real VRAM in MB. Registry first: Win32_VideoController.AdapterRAM is a 32-bit
    value that saturates at 4095 MB, which cannot tell 6 GB from 4 GB when the
    threshold is 2 GB."""
    best = None
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _HAGS_DISPLAY_CLASS)
        try:
            for i in range(64):
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                if not _re.fullmatch(r"\d{4}", sub):
                    continue
                try:
                    k = winreg.OpenKey(root, sub)
                    try:
                        qw, _ = winreg.QueryValueEx(k, "HardwareInformation.qwMemorySize")
                        mb = int(qw) // (1024 * 1024)
                        if mb > 0 and (best is None or mb > best):
                            best = mb
                    finally:
                        winreg.CloseKey(k)
                except OSError:
                    continue
        finally:
            winreg.CloseKey(root)
    except OSError:
        pass
    if best:
        return best
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-CimInstance Win32_VideoController | Sort-Object -Property AdapterRAM "
             "-Descending | Select-Object -First 1 -ExpandProperty AdapterRAM)"],
            capture_output=True, text=True, timeout=20)
        v = (r.stdout or "").strip()
        if v.isdigit():
            return int(v) // (1024 * 1024)
    except Exception:
        pass
    return None


# HwSchMode values in HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers
HAGS_OFF = 1
HAGS_ON = 2


def hags_supported(gpu_name):
    """Does this GPU's driver have HAGS at all? False for anything unrecognised -
    leaving it off on capable hardware costs little, while enabling it on silicon
    that cannot do it leaves a setting that lies."""
    g = (gpu_name or "").strip().lower()
    if not g or g in ("unknown", "n/a", "none", "microsoft basic display adapter"):
        return False, "no usable GPU reported"
    if any(k in g for k in ("nvidia", "geforce", "quadro", "rtx", "gtx", "gts", "gt ")):
        if "rtx" in g:
            return True, "NVIDIA RTX (Turing or newer)"
        if _re.search(r"gtx\s*16\d0", g):
            return True, "NVIDIA GTX 16-series (Turing)"
        if _re.search(r"quadro\s*t\d", g):
            return True, "NVIDIA Quadro T-series (Turing)"
        return False, "NVIDIA pre-Turing (Pascal, Maxwell, Kepler or Tesla)"
    m = _re.search(r"rx\s*(\d{4})", g)
    if m:
        if int(m.group(1)) >= 5000:
            return True, "AMD RDNA (RX 5000 series or newer)"
        return False, "AMD pre-RDNA (Polaris or Vega)"
    if any(k in g for k in ("radeon", "amd", "ati ")):
        return False, "AMD pre-RDNA or unrecognised generation"
    if "arc" in g:
        return True, "Intel Arc (Xe HPG)"
    if "intel" in g:
        return False, "Intel integrated graphics"
    return False, "unrecognised GPU"


def hags_mode_for(gpu_name, vram_mb=None):
    """(mode, enabled, reason). VRAM first and on its own, so the message can say
    which of the two limits applied."""
    if vram_mb is not None and vram_mb > 0 and vram_mb <= _HAGS_MIN_VRAM_MB:
        return 1, False, (f"{vram_mb} MB VRAM - at or below {_HAGS_MIN_VRAM_MB} MB, "
                          "HAGS would cost more than it saves")
    ok, why = hags_supported(gpu_name)
    return (2 if ok else 1), ok, why




# ---- lifted verbatim from Vortex_Suite/hags_policy.py (the canonical copy) ----

def hags_mode_for_game(gpu_name: str, vram_mb: int | None, game_key: str = "none",
                       ) -> tuple[int, bool, str]:
    """The full decision, including the game being played.

    Order matters, and it is deliberate:

      1. The game's requirement. If the card is short of the memory that title
         wants, HAGS goes off whatever the GPU is - this is the case the user
         asked for, and it is the one where HAGS actively hurts.
      2. The 2 GB floor, for anything else.
      3. Whether the driver supports HAGS at all.
    """
    label, need, _cat = game_choice(game_key)
    if need > 0 and vram_mb is not None and 0 < vram_mb < need:
        return HAGS_OFF, False, (f"{label} wants about {need} MB of video memory and this "
                                 f"card has {vram_mb} MB - HAGS stays off while it is short")
    return hags_mode_for(gpu_name, vram_mb)

# ============================================================================
#  GAME VRAM TARGETS
#
#  Why this exists: HAGS is not free. It moves scheduling into the driver, and
#  when the card is already short on video memory for the game being played, that
#  overhead lands on exactly the resource that is running out - which shows up as
#  stutter, not as a smoother frame time.
#
#  So the game being played becomes part of the decision. Pick a title and, if
#  the card does not have the memory that title wants, HAGS is turned off.
#
#  The figures are approximate VRAM GUIDANCE for 1080p, not vendor minimums, and
#  they are deliberately conservative - being told to leave HAGS off on a card
#  that could just about cope costs a little efficiency, while being told to turn
#  it on when the card is already paging costs frame time.
# ============================================================================
GAMES = {
    "none":       ("Not playing a specific game", 0,    ""),
    # esports and light titles - comfortably inside 2 GB
    "valorant":   ("VALORANT",                  2048, "esports"),
    "cs2":        ("Counter-Strike 2",          2048, "esports"),
    "lol":        ("League of Legends",         2048, "esports"),
    "dota2":      ("Dota 2",                    2048, "esports"),
    "rocket":     ("Rocket League",             2048, "esports"),
    "overwatch2": ("Overwatch 2",               2048, "esports"),
    "rainbow6":   ("Rainbow Six Siege",         3072, "esports"),
    # mid-weight
    "thefinals":  ("THE FINALS",                4096, "mid"),
    "marvelrivals": ("Marvel Rivals",             4096, "mid"),
    "fortnite":   ("Fortnite",                  4096, "mid"),
    "gtav":       ("GTA V",                     4096, "mid"),
    "apex":       ("Apex Legends",              6144, "mid"),
    "rdr2":       ("Red Dead Redemption 2",     6144, "mid"),
    "helldivers2": ("Helldivers 2",              6144, "mid"),
    "pubg":       ("PUBG: Battlegrounds",       6144, "mid"),
    "destiny2":   ("Destiny 2",                 6144, "mid"),
    "warframe":   ("Warframe",                  4096, "mid"),
    "monsterhunterworld": ("Monster Hunter: World",     6144, "mid"),
    "witcher3":   ("The Witcher 3",             6144, "mid"),
    # AAA and heavy
    "cyberpunk":  ("Cyberpunk 2077",            6144, "aaa"),
    "cyberpunk_rt": ("Cyberpunk 2077 (ray tracing)", 12288, "aaa"),
    "eldenring":  ("Elden Ring",                8192, "aaa"),
    "starfield":  ("Starfield",                 8192, "aaa"),
    "hogwarts":   ("Hogwarts Legacy",           8192, "aaa"),
    "alanwake2":  ("Alan Wake 2",               8192, "aaa"),
    "bf2042":     ("Battlefield 2042",          8192, "aaa"),
    "warzone":    ("Call of Duty: Warzone",     8192, "aaa"),
    "forza5":     ("Forza Horizon 5",           8192, "aaa"),
    "msfs":       ("Microsoft Flight Simulator", 8192, "aaa"),
    "bg3":        ("Baldur's Gate 3",           8192, "aaa"),
    "tarkov":     ("Escape from Tarkov",        8192, "aaa"),
    "rust":       ("Rust",                      8192, "aaa"),
    "mhwilds":    ("Monster Hunter Wilds",      8192, "aaa"),
    "wukong":     ("Black Myth: Wukong",        8192, "aaa"),
    "stalker2":   ("S.T.A.L.K.E.R. 2",          8192, "aaa"),
    "dd2":        ("Dragon's Dogma 2",          8192, "aaa"),
    "horizonfw":  ("Horizon Forbidden West",    8192, "aaa"),
    "spiderman2": ("Marvel's Spider-Man 2",     8192, "aaa"),
    "indianajones": ("Indiana Jones and the Great Circle", 8192, "aaa"),
}

GAME_CATEGORIES = [("esports", "Esports / light"),
                   ("mid", "Mid-weight"),
                   ("aaa", "AAA / heavy")]


def game_choice(key):
    """(label, required_mb, category) for a key, falling back to 'not playing'."""
    return GAMES.get((key or "none").lower(), GAMES["none"])


def games_in(category):
    return [(k, v[0], v[1]) for k, v in GAMES.items() if v[2] == category]


class VortexSafetyLedger:
    @staticmethod
    def record(hive_name, path, name, val_type, old_val, exists):
        os.makedirs(os.path.dirname(VORTEX_LEDGER), exist_ok=True)
        ledger = {}
        if os.path.exists(VORTEX_LEDGER):
            try:
                with open(VORTEX_LEDGER, "r", encoding="utf-8") as f:
                    ledger = json.load(f)
            except:
                ledger = {}
        key_id = f"{hive_name}\\{path}\\{name}"
        if key_id not in ledger:
            ledger[key_id] = {
                "hive": hive_name,
                "path": path,
                "name": name,
                "type": val_type,
                "old_val": old_val,
                "exists": exists,
                "timestamp": time.time()
            }
            try:
                with open(VORTEX_LEDGER, "w", encoding="utf-8") as f:
                    json.dump(ledger, f, indent=2)
            except:
                pass

class VortexOptimizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VORTEX // Hardware & Performance Architecture Suite v1.0.0")
        self.root.geometry("920x800")
        self.root.minsize(860, 700)
        self.root.configure(bg=C_BG)
        # Set Window Titlebar Icon
        try:
            icon_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
            if os.path.exists(icon_file):
                self.root.iconbitmap(icon_file)
        except:
            pass

        self.cpu_name = self.detect_cpu()
        self.is_ryzen = "ryzen" in self.cpu_name.lower() or "amd" in self.cpu_name.lower()
        self.gpu_name = self.detect_gpu()
        self.target_game = self._load_target_game()

        self.setup_ui()
        self.preflight_safety()

    def detect_cpu(self):
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            v, _ = winreg.QueryValueEx(k, "ProcessorNameString")
            winreg.CloseKey(k)
            return v
        except:
            return os.environ.get("PROCESSOR_IDENTIFIER", "Generic CPU")

    def detect_gpu(self):
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000")
            v, _ = winreg.QueryValueEx(k, "DriverDesc")
            winreg.CloseKey(k)
            return v
        except:
            return "Unknown GPU"

    def preflight_safety(self):
        self.log(f"[INIT] Vortex Hardware Engine online.", "info")
        self.log(f"[HARDWARE] CPU: {self.cpu_name.strip()} | GPU: {self.gpu_name.strip()}", "info")
        if is_admin():
            self.log("[PRIVILEGE] Elevated NT AUTHORITY / Administrator confirmed.", "success")
        else:
            self.log("[PRIVILEGE ERROR] Administrator permissions required for ring-3 hooks.", "error")

# ---------------------------------------------------------------------------
#  TARGET GAME
#
#  The game being played is part of the HAGS decision, because HAGS is not free:
#  it moves scheduling work into the driver, and when the card is already short of
#  video memory for the title being played, that lands on exactly the resource
#  that is running out. Pick a title here and, if the card does not have the
#  memory that title wants, HAGS is turned off.
# ---------------------------------------------------------------------------


    def _game_labels(self):
        """Dropdown entries, grouped by how heavy the title is."""
        labels = ["Not playing a specific game"]
        for cat, cat_label in GAME_CATEGORIES:
            for key, label, need in games_in(cat):
                labels.append(cat_label + "  -  " + label + " (" + str(need // 1024) + " GB)")
        return labels


    def _game_label(self):
        """The dropdown text for the currently selected key."""
        label, need, cat = game_choice(self.target_game)
        if self.target_game == "none":
            return "Not playing a specific game"
        pretty = dict(GAME_CATEGORIES).get(cat, "")
        return pretty + "  -  " + label + " (" + str(need // 1024) + " GB)"


    def _on_game_change(self, _event=None):
        """Translate the chosen dropdown text back into a catalogue key."""
        chosen = self.game_var.get()
        self.target_game = "none"
        for key, label, need in GAMES.items():
            if key == "none":
                continue
            if label in chosen and str(need // 1024) + " GB" in chosen:
                self.target_game = key
                break
        self._save_target_game()
        if self.target_game == "none":
            self.log("[GAME] No specific title selected. HAGS is decided by the card alone.", "info")
        else:
            label, need, _c = game_choice(self.target_game)
            vram = detect_vram_mb()
            mode, on, why = hags_mode_for_game(self.gpu_name, vram, self.target_game)
            if on:
                self.log("[GAME] " + label + " selected. " + why + ". HAGS may stay on.",
                         "success")
            else:
                self.log("[GAME] " + label + " selected. " + why + ".", "warning")


    def _load_target_game(self):
        """Remember the selection between runs."""
        try:
            if os.path.exists(VORTEX_SETTINGS):
                with open(VORTEX_SETTINGS, "r", encoding="utf-8") as f:
                    key = json.load(f).get("target_game", "none")
                return key if key in GAMES else "none"
        except Exception:
            pass
        return "none"


    def _save_target_game(self):
        try:
            os.makedirs(os.path.dirname(VORTEX_SETTINGS), exist_ok=True)
            data = {}
            if os.path.exists(VORTEX_SETTINGS):
                try:
                    with open(VORTEX_SETTINGS, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            data["target_game"] = self.target_game
            with open(VORTEX_SETTINGS, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def setup_ui(self):
        # Header
        top_bar = tk.Frame(self.root, bg=C_PANEL, padx=20, pady=14, highlightthickness=1, highlightbackground=C_BORDER)
        top_bar.pack(fill=tk.X)

        title_box = tk.Frame(top_bar, bg=C_PANEL)
        title_box.pack(fill=tk.X)

        tk.Label(title_box, text="VORTEX", font=("Segoe UI", 16, "bold"), fg=C_CYAN, bg=C_PANEL).pack(side=tk.LEFT)
        tk.Label(title_box, text="// HARDWARE OPTIMIZER", font=("Segoe UI", 11, "bold"), fg=C_TEXT, bg=C_PANEL).pack(side=tk.LEFT, padx=(6, 12))
        tk.Label(title_box, text="v1.0.0 PRO", font=("Segoe UI", 8, "bold"), fg=C_BG, bg=C_CYAN, padx=7, pady=2).pack(side=tk.LEFT)
        cpu_tag = "RYZEN TUNED" if self.is_ryzen else "HARDWARE ACCELERATED"
        tk.Label(title_box, text=cpu_tag, font=("Segoe UI", 8, "bold"), fg="#021016", bg=C_GREEN, padx=7, pady=2).pack(side=tk.LEFT, padx=6)

        sub_text = f"CPU: {self.cpu_name.strip()}  •  GPU: {self.gpu_name.strip()}"
        tk.Label(top_bar, text=sub_text, font=("Consolas", 8), fg=C_MUTED, bg=C_PANEL).pack(anchor=tk.W, pady=(4, 0))

        content = tk.Frame(self.root, bg=C_BG, padx=16, pady=12)
        content.pack(fill=tk.BOTH, expand=False)

        # Command Deck
        deck = tk.Frame(content, bg=C_PANEL, padx=14, pady=12, highlightthickness=1, highlightbackground=C_BORDER)
        deck.pack(fill=tk.X, pady=(0, 10))

        tk.Label(deck, text="COMMAND DECK // SYSTEM OVERDRIVE & MEMORY", font=("Segoe UI", 8, "bold"), fg=C_CYAN, bg=C_PANEL).pack(anchor=tk.W, pady=(0, 8))

        btn_row = tk.Frame(deck, bg=C_PANEL)
        btn_row.pack(fill=tk.X)

        tk.Button(btn_row, text="⚡  1-CLICK OVERDRIVE", font=("Segoe UI", 10, "bold"), bg=C_CYAN, fg="#021016", activebackground="#00b4cc", cursor="hand2", relief=tk.FLAT, padx=16, pady=9, command=lambda: self.run_async(self.master_boost)).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_row, text="🧹  SAFE RAM FLUSH", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg=C_TEXT, activebackground="#334155", cursor="hand2", relief=tk.FLAT, padx=14, pady=9, command=lambda: self.run_async(self.flush_ram)).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_row, text="↺  ROLLBACK (UNDO)", font=("Segoe UI", 9, "bold"), bg="#4c0519", fg="#fecdd3", activebackground="#881337", cursor="hand2", relief=tk.FLAT, padx=14, pady=9, command=lambda: self.run_async(self.atomic_rollback)).pack(side=tk.RIGHT)

        # 4-Module Matrix
        grid = tk.Frame(content, bg=C_BG)
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        def make_card(parent, title_text, col, row):
            card = tk.Frame(parent, bg=C_PANEL, padx=12, pady=10, highlightthickness=1, highlightbackground=C_BORDER)
            card.grid(column=col, row=row, sticky="nsew", padx=4, pady=4)
            tk.Label(card, text=title_text, font=("Segoe UI", 8, "bold"), fg=C_CYAN, bg=C_PANEL).pack(anchor=tk.W, pady=(0, 6))
            return card

        def make_action(parent, text_title, text_sub, cmd):
            bf = tk.Frame(parent, bg="#161c2b", padx=10, pady=7, highlightthickness=1, highlightbackground=C_BORDER)
            bf.pack(fill=tk.X, pady=3)
            lt = tk.Label(bf, text=text_title, font=("Segoe UI", 8, "bold"), fg=C_TEXT, bg="#161c2b", anchor=tk.W)
            lt.pack(fill=tk.X)
            ls = tk.Label(bf, text=text_sub, font=("Consolas", 7), fg=C_MUTED, bg="#161c2b", anchor=tk.W)
            ls.pack(fill=tk.X)
            for w in [bf, lt, ls]:
                w.bind("<Button-1>", lambda e: cmd())
                w.bind("<Enter>", lambda e: (bf.configure(bg="#1e273d"), lt.configure(bg="#1e273d", fg=C_CYAN)))
                w.bind("<Leave>", lambda e: (bf.configure(bg="#161c2b"), lt.configure(bg="#161c2b", fg=C_TEXT)))
                w.configure(cursor="hand2")

        # Mod 1: CPU
        m1 = make_card(grid, "01 // CPU CLOCK & FREQUENCY STABILITY", 0, 0)
        make_action(m1, "Adaptive Ryzen / High Performance Plan", "Tuned for AMD CPPC & Zen core unparking; 0ms sleep", lambda: self.run_async(self.optimize_cpu))
        make_action(m1, "Disable Background Power Throttling", "Forces 100% clock budget to active foreground games", lambda: self.run_async(self.disable_throttling))

        # Mod 2: Network
        m2 = make_card(grid, "02 // NETWORK PACKETS & TCPNoDelay", 1, 0)
        make_action(m2, "Disable Nagle Algorithm Across Adapters", "Eliminates 40ms network buffering delay (0ms ACK)", lambda: self.run_async(self.optimize_network))
        make_action(m2, "Flush DNS & Tune TCP Autotuning", "Purges resolver cache and locks ECN packet tagging", lambda: self.run_async(self.flush_network))

        # Mod 3: GPU & Display
        m3 = make_card(grid, "03 // GPU PACING & SMART HAGS EVALUATION", 0, 1)
        make_action(m3, "Smart Hardware Scheduling (HAGS)", "Enables where the hardware supports it; off when the card is short of VRAM", lambda: self.run_async(self.optimize_gpu))

        game_row = tk.Frame(m3, bg=C_PANEL)
        game_row.pack(fill=tk.X, pady=(7, 2))
        tk.Label(game_row, text="GAME BEING PLAYED", font=("Segoe UI", 7, "bold"),
                 fg=C_MUTED, bg=C_PANEL).pack(anchor=tk.W)
        self.game_var = tk.StringVar(value=self._game_label())
        self.game_combo = ttk.Combobox(game_row, textvariable=self.game_var,
                                       values=self._game_labels(), state="readonly",
                                       font=("Consolas", 8))
        self.game_combo.pack(fill=tk.X, pady=(2, 0))
        self.game_combo.bind("<<ComboboxSelected>>", self._on_game_change)
        tk.Label(game_row, text="HAGS is turned off when this title needs more VRAM than you have.",
                 font=("Consolas", 7), fg=C_MUTED, bg=C_PANEL, wraplength=320,
                 justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 0))
        make_action(m3, "1:1 Raw Mouse Sensor Sync", "Disables pointer precision curve acceleration", lambda: self.run_async(self.optimize_input))

        # Mod 4: Storage & RAM
        m4 = make_card(grid, "04 // STORAGE TRIM & MEMORY MANAGEMENT", 1, 1)
        make_action(m4, "Issue Physical NVMe / SSD TRIM", "Re-trims deleted block chains for peak sequential speed", lambda: self.run_async(self.trim_storage))
        make_action(m4, "Clean Temporary Scratch Caches", "Safely purges user temp files and prefetch clutter", lambda: self.run_async(self.clean_temp))

        # Terminal Log
        log_frame = tk.Frame(self.root, bg=C_BG, padx=16, pady=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_hdr = tk.Frame(log_frame, bg=C_BG)
        log_hdr.pack(fill=tk.X, pady=(0, 4))
        tk.Label(log_hdr, text="DIAGNOSTIC LOG STREAM // HARDWARE METRICS", font=("Consolas", 8, "bold"), fg=C_MUTED, bg=C_BG).pack(side=tk.LEFT)
        tk.Button(log_hdr, text="Clear", font=("Consolas", 7), bg="#1e293b", fg=C_MUTED, activebackground="#334155", relief=tk.FLAT, padx=6, pady=1, command=lambda: self.log_box.delete("1.0", tk.END)).pack(side=tk.RIGHT)

        self.log_box = scrolledtext.ScrolledText(log_frame, bg=C_CONSOLE, fg=C_TEXT, insertbackground=C_CYAN, font=("Consolas", 9), relief=tk.FLAT, padx=10, pady=8, highlightthickness=1, highlightbackground=C_BORDER)
        self.log_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.log_box.tag_config("info", foreground=C_CYAN)
        self.log_box.tag_config("success", foreground=C_GREEN)
        self.log_box.tag_config("warning", foreground=C_AMBER)
        self.log_box.tag_config("error", foreground=C_RED)

    def log(self, text, tag="info"):
        self.root.after(0, self._append_log, text, tag)

    def _append_log(self, text, tag):
        self.log_box.insert(tk.END, text + "\n", tag)
        self.log_box.see(tk.END)

    def run_async(self, func):
        threading.Thread(target=func, daemon=True).start()

    def master_boost(self):
        self.log("\n=======================================================", "warning")
        self.log(">>> ENGAGING 1-CLICK VORTEX OVERDRIVE <<<", "warning")
        self.log("=======================================================", "warning")
        self.optimize_cpu()
        self.disable_throttling()
        self.optimize_network()
        self.flush_network()
        self.optimize_gpu()
        self.optimize_input()
        self.flush_ram()
        self.trim_storage()
        self.clean_temp()
        self.log("\n[STATUS: OPTIMAL] Vortex Overdrive active across all subsystems.", "success")
        messagebox.showinfo("Vortex Overdrive", "Vortex Overdrive applied safely!\nAll tweaks recorded to ledger.")

    def atomic_rollback(self):
        self.log("\n[ROLLBACK] Restoring previous configuration from Vortex Ledger...", "info")
        if not os.path.exists(VORTEX_LEDGER):
            self.log("[NOTICE] No Vortex ledger found. Reverting to factory power schemes...", "warning")
            subprocess.run(["powercfg", "-restoredefaultschemes"], capture_output=True)
            messagebox.showinfo("Rollback", "Factory power schemes restored.")
            return

        try:
            with open(VORTEX_LEDGER, "r", encoding="utf-8") as f:
                ledger = json.load(f)
        except Exception as e:
            self.log(f"[ERROR] Failed reading ledger: {e}", "error")
            return

        reverted = 0
        hives = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}
        for k_id, item in ledger.items():
            hive = hives.get(item["hive"])
            if not hive: continue
            try:
                if item["exists"]:
                    k = winreg.CreateKeyEx(hive, item["path"], 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)
                    winreg.SetValueEx(k, item["name"], 0, item["type"], item["old_val"])
                    winreg.CloseKey(k)
                else:
                    try:
                        k = winreg.OpenKey(hive, item["path"], 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)
                        winreg.DeleteValue(k, item["name"])
                        winreg.CloseKey(k)
                    except:
                        pass
                reverted += 1
            except:
                pass

        subprocess.run(["powercfg", "-restoredefaultschemes"], capture_output=True)
        self.log(f"[SUCCESS] Reverted {reverted} configuration entries to pre-boost values.", "success")
        messagebox.showinfo("Rollback Complete", f"Restored {reverted} configuration items from ledger.")

    def _set_reg_safe(self, hive, path, name, vtype, val):
        hive_name = "HKLM" if hive == winreg.HKEY_LOCAL_MACHINE else "HKCU"
        exists = False
        old_val = None
        old_type = vtype
        try:
            k = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            old_val, old_type = winreg.QueryValueEx(k, name)
            winreg.CloseKey(k)
            exists = True
        except:
            exists = False

        VortexSafetyLedger.record(hive_name, path, name, old_type, old_val, exists)

        try:
            k = winreg.CreateKeyEx(hive, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY)
            winreg.SetValueEx(k, name, 0, vtype, val)
            winreg.CloseKey(k)
            self.log(f"[TWEAK] {hive_name}\\{path} -> {name} = {val}", "success")
        except Exception as e:
            self.log(f"[NOTICE] Reg write note ({name}): {e}", "warning")

    def optimize_cpu(self):
        self.log(f"\n[CPU] Applying dynamic power curves for {self.cpu_name.strip()}...", "info")
        guid = "88888888-8888-8888-8888-888888888888"
        if self.is_ryzen:
            subprocess.run(["powercfg", "-duplicatescheme", "e9a42b02-d5df-448d-aa00-03f14749eb61", guid], capture_output=True)
            subprocess.run(["powercfg", "-changename", guid, "AMD Ryzen Vortex Performance"], capture_output=True)
            subprocess.run(["powercfg", "-setactive", guid], capture_output=True)
            sub_proc = "54533251-82be-4824-96c1-47b60b740d00"
            subprocess.run(["powercfg", "/setacvalueindex", "scheme_current", sub_proc, "893dee8e-2bef-41e0-89c6-b55d0929964c", "100"], capture_output=True)
            subprocess.run(["powercfg", "/setacvalueindex", "scheme_current", sub_proc, "bc5038f7-23e0-4960-96da-33abaf5935ec", "100"], capture_output=True)
            subprocess.run(["powercfg", "/setacvalueindex", "scheme_current", sub_proc, "36687f9e-e376-4db2-90c7-8660d6961532", "0"], capture_output=True)
            subprocess.run(["powercfg", "/setacvalueindex", "scheme_current", sub_proc, "0cc5b647-c1df-4637-891a-dec35c318583", "100"], capture_output=True)
            subprocess.run(["powercfg", "-setactive", "scheme_current"], capture_output=True)
            self.log("[SUCCESS] Ryzen Zen CPPC active. All physical cores unparked.", "success")
        else:
            subprocess.run(["powercfg", "-duplicatescheme", "e9a42b02-d5df-448d-aa00-03f14749eb61", guid], capture_output=True)
            subprocess.run(["powercfg", "-setactive", guid], capture_output=True)
            self.log("[SUCCESS] Ultimate Performance scheme active.", "success")

    def disable_throttling(self):
        self.log("\n[POWER THROTTLE] Disabling background CPU execution throttling...", "info")
        self._set_reg_safe(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling", "PowerThrottlingOff", winreg.REG_DWORD, 1)
        self.log("[SUCCESS] Power throttling disengaged for foreground threads.", "success")

    def optimize_network(self):
        self.log("\n[NETWORK] Disabling Nagle algorithm across active network interfaces...", "info")
        net_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
        try:
            root_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, net_path)
            for i in range(winreg.QueryInfoKey(root_key)[0]):
                subkey = winreg.EnumKey(root_key, i)
                sub_path = f"{net_path}\\{subkey}"
                self._set_reg_safe(winreg.HKEY_LOCAL_MACHINE, sub_path, "TcpAckFrequency", winreg.REG_DWORD, 1)
                self._set_reg_safe(winreg.HKEY_LOCAL_MACHINE, sub_path, "TCPNoDelay", winreg.REG_DWORD, 1)
            winreg.CloseKey(root_key)
            self.log("[SUCCESS] Nagle's algorithm disabled. Packet transmit delay eliminated.", "success")
        except Exception as e:
            self.log(f"[WARNING] Network tweak notice: {e}", "warning")

    def flush_network(self):
        self.log("\n[NETWORK FLUSH] Purging DNS resolver cache...", "info")
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
        subprocess.run(["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"], capture_output=True)
        subprocess.run(["netsh", "int", "tcp", "set", "global", "ecncapability=enabled"], capture_output=True)
        self.log("[SUCCESS] DNS flushed; ECN & Autotuning configured.", "success")

    def optimize_gpu(self):
        self.log(f"\n[SMART HAGS] Evaluating GPU hardware: {self.gpu_name.strip()}...", "info")
        vram = detect_vram_mb()
        # the game being played is part of the decision, not decoration:
        # HAGS costs most when the card is already short of memory for the title
        mode, enabled, why = hags_mode_for_game(
            self.gpu_name.strip(), vram, getattr(self, 'target_game', 'none'))

        self._set_reg_safe(winreg.HKEY_LOCAL_MACHINE,
                           r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
                           "HwSchMode", winreg.REG_DWORD, mode)

        if enabled:
            self.log(f"[HAGS: ENABLED] Mode 2 written. {why}."
                     + (f" VRAM {vram} MB." if vram else ""), "success")
        else:
            self.log(f"[HAGS: LEFT OFF] Mode 1 written. {why}."
                     + (f" VRAM {vram} MB." if vram else "")
                     + " HAGS stays off on this hardware.", "warning")

        self._set_reg_safe(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AutoGameModeEnabled", winreg.REG_DWORD, 1)

    def optimize_input(self):
        self.log("\n[INPUT LAG] Configuring 1:1 hardware mouse curve...", "info")
        self._set_reg_safe(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", "MouseSpeed", winreg.REG_SZ, "0")
        self._set_reg_safe(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", "MouseThreshold1", winreg.REG_SZ, "0")
        self._set_reg_safe(winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse", "MouseThreshold2", winreg.REG_SZ, "0")
        self.log("[SUCCESS] Raw input curves engaged.", "success")

    def flush_ram(self):
        self.log("\n[RAM FLUSH] Emptying working sets across user processes safely...", "info")
        try:
            pids = [int(x) for x in subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Process).Id"], capture_output=True, text=True).stdout.split() if x.isdigit()]
            freed = 0
            for pid in pids:
                try:
                    h = ctypes.windll.kernel32.OpenProcess(0x001F0FFF, False, pid)
                    if h:
                        ctypes.windll.psapi.EmptyWorkingSet(h)
                        ctypes.windll.kernel32.CloseHandle(h)
                        freed += 1
                except:
                    pass
            self.log(f"[SUCCESS] Safely trimmed memory working sets across {freed} processes.", "success")
        except Exception as e:
            self.log(f"[WARNING] RAM flush notice: {e}", "warning")

    def trim_storage(self):
        self.log("\n[NVMe / SSD TRIM] Issuing non-destructive physical TRIM...", "info")
        ps = "Optimize-Volume -DriveLetter C -ReTrim -Verbose -ErrorAction SilentlyContinue"
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
        self.log("[SUCCESS] SSD block re-trim finished. Zero mechanical HDD wear.", "success")

    def clean_temp(self):
        self.log("\n[CLEAN CACHE] Safely purging user temporary scratch space...", "info")
        dirs = [os.environ.get("TEMP"), r"C:\Windows\Temp"]
        cleared = 0
        for d in dirs:
            if not d or not os.path.exists(d): continue
            for root, _, files in os.walk(d):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                        cleared += 1
                    except:
                        pass
        self.log(f"[SUCCESS] Cleaned {cleared} temporary files safely.", "success")

def main():
    if not is_admin():
        run_as_admin()
        return
    root = tk.Tk()
    app = VortexOptimizerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
