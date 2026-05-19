import customtkinter as ctk, ctypes, logging, queue, json, os, pyperclip, datetime
from pathlib import Path
from PIL import Image, ImageTk
from core.config import get_window_pos
from core.data import CHAMPION_HEX, CHAMP_TFTACADEMY, ITEM_TFTACADEMY, pt_item, pt_augment
from core.memory_db import MemoryDB
from . import styles

def make_drag(hwnd, w):
    u = ctypes.windll.user32
    def d(e): u.ReleaseCapture(); u.SendMessageW(hwnd, 0x00A1, 2, 0)
    w.bind("<Button-1>", d)

PROJECT_DIR = Path(__file__).parent.parent
IMG_DIR = PROJECT_DIR / "data" / "images"
IMG_DIR.mkdir(parents=True, exist_ok=True)

# TFT Academy assets (Set 17)
TFTACADEMY_BASE = "https://assets.tftacademy.com"
CHAMP_IMG_BASE = f"{TFTACADEMY_BASE}/champions/champion_icons/"
ITEM_IMG_BASE = f"{TFTACADEMY_BASE}/items/"

IMG_CACHE = {}

def _download_img(url, path, size):
    if path.exists():
        return _load_img(path, size)
    try:
        import requests
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            path.write_bytes(r.content)
            return _load_img(path, size)
    except Exception as e:
        logging.debug(f"Download img failed {url}: {e}")
    return None

def _load_img(path, size):
    key = f"{path}_{size}"
    if key in IMG_CACHE:
        return IMG_CACHE[key]
    try:
        img = Image.open(path).resize(size, Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        IMG_CACHE[key] = photo
        return photo
    except Exception:
        return None

def get_augment_img(name, size=28):
    if not name: return None
    clean = name.replace(" ", "").replace("'", "").replace(".", "").replace("-", "")
    path = IMG_DIR / f"aug_{clean}_{size}.webp"
    url = f"{TFTACADEMY_BASE}/augments/{clean}.webp"
    return _download_img(url, path, size)


class ToolTip:
    """Tooltip simples para widgets tkinter"""
    def __init__(self, widget, text="", delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self._after_id = None
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)
    
    def _on_enter(self, event=None):
        self._after_id = self.widget.after(self.delay, self._show_tip)
    
    def _on_leave(self, event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide_tip()
    
    def _show_tip(self):
        if not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = ctk.CTkLabel(tw, text=self.text, font=styles.FONTS["small"],
                            fg_color="#313244", corner_radius=4, padx=6, pady=3)
        label.pack()
    
    def _hide_tip(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
    
    def update_text(self, text):
        self.text = text


def get_champion_img(name, size=56):
    if not name: return None
    tft_name = CHAMP_TFTACADEMY.get(name, name.replace(" ", "").replace("'", "").replace("&", "").replace(".", ""))
    path = IMG_DIR / f"champ_{tft_name}_{size}.webp"
    url = f"{CHAMP_IMG_BASE}TFT17_{tft_name}.webp"
    return _download_img(url, path, size)

def get_item_img(name, size=32):
    if not name: return None
    clean = ITEM_TFTACADEMY.get(name, name.replace(" ", "").replace("'", "").replace(".", "").replace("-", ""))
    if not clean.startswith("TFT"):
        clean = f"TFT_Item_{clean}"
    path = IMG_DIR / f"item_{clean}_{size}.webp"
    url = f"{ITEM_IMG_BASE}{clean}.webp"
    return _download_img(url, path, size)

class UnitRow(ctk.CTkFrame):
    def __init__(self, parent, champ_name, items=None, is_tank=False, size=56):
        super().__init__(parent, fg_color="transparent")
        img = get_champion_img(champ_name, size)
        if img:
            lbl = ctk.CTkLabel(self, image=img, text="")
            lbl.image = img
            lbl.pack(padx=4, pady=(0, 2))
        name_color = "#f38ba8" if is_tank else "#f9e2af"
        lbl = ctk.CTkLabel(self, text=champ_name, font=styles.FONTS["body"], text_color=name_color)
        lbl.pack(padx=4, pady=(0, 2))
        if items:
            for item in items:
                item_pt = pt_item(item)
                lbl = ctk.CTkLabel(self, text=item_pt, font=styles.FONTS["body"], text_color="#a6adc8", padx=6)
                lbl.pack(padx=2, pady=(0, 1))

class OpponentCard(ctk.CTkFrame):
    """3 estados: vivo -> lutando (✗) -> morto (✗✗) -> reset"""
    def __init__(self, parent, name, info, callback):
        super().__init__(parent, fg_color="transparent")
        self.name = name
        self.info = info
        self.state = 0  # 0=vivo, 1=lutando, 2=morto
        self.callback = callback
        self._build()
        self.lbl.bind("<Button-1>", self._click)
    def _build(self):
        for w in self.winfo_children(): w.destroy()
        if self.state == 0:
            prefix, color = "", "#cdd6f4"
        elif self.state == 1:
            prefix, color = "✗ ", "#f9e2af"
        else:
            prefix, color = "✗✗ ", "#f38ba8"
        txt = prefix + self.name
        if self.info.get("rank"): txt += f" ({self.info['rank']})"
        self.lbl = ctk.CTkLabel(self, text=txt, font=styles.FONTS["small"], text_color=color, cursor="hand2")
        self.lbl.pack(side="left", padx=2)
    def _click(self, e):
        self.state = (self.state + 1) % 3
        self._build()
        self.callback()
    @property
    def alive(self):
        return self.state == 0

class Overlay:
    def __init__(self, cfg, q, cmd_q=None):
        self.cfg, self.q = cfg, q
        self.cmd_q = cmd_q if cmd_q else None
        self.last_game_id = None
        self.opp_cards = []
        self._last_update_time = 0  # Throttling
        self._last_riot_key_check = 0  # Riot key status throttling
        self._streamer_safe = False  # Modo streamer-safe
        w, h, a = cfg["window"]["width"], cfg["window"]["height"], cfg["window"]["alpha"]
        x, y = get_window_pos(cfg, w, h)
        self.root = ctk.CTk()
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.overrideredirect(False)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", a)
        self.root.deiconify()
        self.root.update()
        self.theme = styles.get(cfg.get("ui",{}).get("theme","dark"))
        self.feedback_frame = None
        self._build()
        self.root.after(100, self._loop)
        self.root.bind("<Escape>", lambda e: self._close())
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        # Barra superior
        bar = ctk.CTkFrame(self.root, fg_color=self.theme["bg2"], height=44, corner_radius=10)
        bar.pack(fill="x", padx=10, pady=(10, 6))
        make_drag(self.root.winfo_id(), bar)
        ctk.CTkLabel(bar, text="TFT AI Overlay v5.0", font=styles.FONTS["title"], text_color=self.theme["green"]).pack(side="left", padx=14, pady=8)
        self.rate_limit_lbl = ctk.CTkLabel(bar, text="", font=styles.FONTS["small"], text_color=self.theme["yellow"])
        self.rate_limit_lbl.pack(side="right", padx=8, pady=8)
        self.riot_key_lbl = ctk.CTkLabel(bar, text="", font=styles.FONTS["small"], text_color=self.theme["txt2"])
        self.riot_key_lbl.pack(side="right", padx=8, pady=8)
        ctk.CTkLabel(bar, text="[Esc] Fechar | Arraste", font=styles.FONTS["small"], text_color=self.theme["txt2"]).pack(side="right", padx=14, pady=8)

        # Status
        self.status = ctk.CTkLabel(self.root, text="Conectando...", font=styles.FONTS["title"], text_color=self.theme["txt1"])
        self.status.pack(pady=(6, 6))

        # Frame principal com scroll
        main = ctk.CTkScrollableFrame(self.root, fg_color=self.theme["bg3"], corner_radius=12)
        main.pack(fill="both", expand=True, padx=14, pady=8)

        # Input manual (ouro/nivel/augment)
        ctk.CTkLabel(main, text="Contexto Manual (opcional)", font=styles.FONTS["head"], text_color="#a6adc8").pack(anchor="w", padx=10, pady=(6, 2))
        manual_frame = ctk.CTkFrame(main, fg_color="transparent")
        manual_frame.pack(fill="x", padx=10, pady=(0, 6))
        
        ctk.CTkLabel(manual_frame, text="Nivel:", font=styles.FONTS["body"], text_color="#cdd6f4").pack(side="left", padx=(0, 2))
        self.level_var = ctk.StringVar(value="auto")
        level_entry = ctk.CTkEntry(manual_frame, width=50, font=styles.FONTS["body"], textvariable=self.level_var)
        level_entry.pack(side="left", padx=2)
        
        ctk.CTkLabel(manual_frame, text="Ouro:", font=styles.FONTS["body"], text_color="#cdd6f4").pack(side="left", padx=(10, 2))
        self.gold_var = ctk.StringVar(value="auto")
        gold_entry = ctk.CTkEntry(manual_frame, width=50, font=styles.FONTS["body"], textvariable=self.gold_var)
        gold_entry.pack(side="left", padx=2)
        
        ctk.CTkLabel(manual_frame, text="Augment:", font=styles.FONTS["body"], text_color="#cdd6f4").pack(side="left", padx=(10, 2))
        self.manual_aug_var = ctk.StringVar(value="")
        aug_entry = ctk.CTkEntry(manual_frame, width=100, font=styles.FONTS["body"], textvariable=self.manual_aug_var, placeholder_text="opcional")
        aug_entry.pack(side="left", padx=2)
        
        # Botao reanalisar (logo abaixo do input manual)
        reanalyze_btn = ctk.CTkButton(main, text="Reanalisar com IA", command=self._reanalyze, fg_color="#f9e2af", text_color="#181825", height=38, font=styles.FONTS["body"])
        reanalyze_btn.pack(pady=4, padx=10, fill="x")
        
        # Augments registrados (exibicao)
        self.registered_augments_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.registered_augments_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.registered_augments_lbl = ctk.CTkLabel(self.registered_augments_frame, text="", font=styles.FONTS["body"], text_color="#cba6f7", wraplength=480)
        self.registered_augments_lbl.pack(anchor="w")
        self.next_augments_lbl = ctk.CTkLabel(self.registered_augments_frame, text="", font=styles.FONTS["body"], text_color="#f9e2af", wraplength=480)
        self.next_augments_lbl.pack(anchor="w")

        # Titulo da composicao
        ctk.CTkLabel(main, text="Composicao Sugerida", font=styles.FONTS["head"], text_color="#89b4fa").pack(anchor="w", padx=10, pady=(6, 2))
        self.comp_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.comp_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.comp_lbl = ctk.CTkLabel(self.comp_frame, text="-", font=styles.FONTS["body"], text_color="#cdd6f4", justify="left", wraplength=480)
        self.comp_lbl.pack(side="left")
        self.viab_lbl = ctk.CTkLabel(self.comp_frame, text="", font=styles.FONTS["body"], text_color="#a6e3a1")
        self.viab_lbl.pack(side="right", padx=6)
        self.nova_lbl = ctk.CTkLabel(self.comp_frame, text="", font=styles.FONTS["body"], text_color="#f9e2af")
        self.nova_lbl.pack(side="right", padx=6)
        self.wr_lbl = ctk.CTkLabel(self.comp_frame, text="", font=styles.FONTS["body"], text_color="#a6e3a1")
        self.wr_lbl.pack(side="right", padx=6)

        # Risco de contestacao
        self.contest_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.contest_frame.pack(fill="x", padx=10, pady=(0, 4))
        self.contest_lbl = ctk.CTkLabel(self.contest_frame, text="", font=styles.FONTS["body"], text_color="#cdd6f4", justify="left", wraplength=480)
        self.contest_lbl.pack(anchor="w")

        # Botao copiar (logo abaixo da composicao sugerida)
        copy_btn = ctk.CTkButton(main, text="Copiar Composicao", command=self._copy_comp, fg_color="#89b4fa", text_color="#181825", height=38, font=styles.FONTS["body"])
        copy_btn.pack(pady=4, padx=10, fill="x")

        # Comps alternativas
        ctk.CTkLabel(main, text="Comps Alternativas", font=styles.FONTS["head"], text_color="#a6adc8").pack(anchor="w", padx=10, pady=(6, 2))
        self.alt_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.alt_frame.pack(fill="x", padx=10, pady=(0, 6))

        # Oponentes
        ctk.CTkLabel(main, text="Oponentes (clique: vivo -> lutando ✗ -> morto ✗✗ -> reset)", font=styles.FONTS["head"], text_color="#f38ba8").pack(anchor="w", padx=10, pady=(6, 2))
        self.opp_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.opp_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.prox_lbl = ctk.CTkLabel(main, text="", font=styles.FONTS["body"], text_color="#a6e3a1", wraplength=480)
        self.prox_lbl.pack(anchor="w", padx=10, pady=(0, 4))

        # Prompt gerado (para revisao)
        ctk.CTkLabel(main, text="Prompt Enviado", font=styles.FONTS["head"], text_color="#cba6f7").pack(anchor="w", padx=10, pady=(6, 2))
        self.prompt_lbl = ctk.CTkLabel(main, text="-", font=styles.FONTS["body"], text_color="#a6adc8", justify="left", wraplength=480)
        self.prompt_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # Unidades
        ctk.CTkLabel(main, text="Unidades", font=styles.FONTS["head"], text_color="#89b4fa").pack(anchor="w", padx=10, pady=(6, 2))
        self.units_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.units_frame.pack(fill="x", padx=10, pady=(0, 6))

        # Augments
        ctk.CTkLabel(main, text="Augments Sugeridos", font=styles.FONTS["head"], text_color="#cba6f7").pack(anchor="w", padx=10, pady=(6, 2))
        self.augments_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.augments_frame.pack(fill="x", padx=10, pady=(0, 6))
        
        # Botao registrar augment (logo abaixo dos augments sugeridos)
        aug_btn = ctk.CTkButton(main, text="Registrar Augment", command=self._register_augment, fg_color="#cba6f7", text_color="#181825", height=38, font=styles.FONTS["body"])
        aug_btn.pack(pady=4, padx=10, fill="x")

        # Posicionamento
        ctk.CTkLabel(main, text="Posicionamento", font=styles.FONTS["head"], text_color="#89b4fa").pack(anchor="w", padx=10, pady=(6, 2))
        self.pos_lbl = ctk.CTkLabel(main, text="-", font=styles.FONTS["body"], text_color="#cdd6f4", justify="left", wraplength=480)
        self.pos_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # Guia de niveis
        ctk.CTkLabel(main, text="Guia por Nivel", font=styles.FONTS["head"], text_color="#f9e2af").pack(anchor="w", padx=10, pady=(6, 2))
        self.levels_lbl = ctk.CTkLabel(main, text="-", font=styles.FONTS["body"], text_color="#cdd6f4", justify="left", wraplength=480)
        self.levels_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # Dicas de gameplay
        ctk.CTkLabel(main, text="Dicas de Gameplay", font=styles.FONTS["head"], text_color="#f5c2e7").pack(anchor="w", padx=10, pady=(6, 2))
        self.dicas_lbl = ctk.CTkLabel(main, text="-", font=styles.FONTS["body"], text_color="#cdd6f4", justify="left", wraplength=480)
        self.dicas_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # Contra
        ctk.CTkLabel(main, text="Contra", font=styles.FONTS["head"], text_color="#89b4fa").pack(anchor="w", padx=10, pady=(6, 2))
        self.contra_lbl = ctk.CTkLabel(main, text="-", font=styles.FONTS["body"], text_color="#cdd6f4", justify="left", wraplength=480)
        self.contra_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # Motivo
        ctk.CTkLabel(main, text="Motivo", font=styles.FONTS["head"], text_color="#89b4fa").pack(anchor="w", padx=10, pady=(6, 2))
        self.motivo_lbl = ctk.CTkLabel(main, text="-", font=styles.FONTS["body"], text_color="#cdd6f4", justify="left", wraplength=480)
        self.motivo_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # Botoes (exportar + streamer no final)
        export_btn = ctk.CTkButton(main, text="Exportar Historico", command=self._export_history, fg_color="#89b4fa", text_color="#181825", height=38, font=styles.FONTS["body"])
        export_btn.pack(pady=4, padx=10, fill="x")
        
        self.streamer_btn = ctk.CTkButton(main, text="Modo Streamer: OFF", command=self._toggle_streamer_safe, 
                                          fg_color="#45475a", text_color="#cdd6f4", height=38, font=styles.FONTS["body"])
        self.streamer_btn.pack(pady=4, padx=10, fill="x")
        
        # Armazena dados atuais para copia
        self.current_data = {}

        # Historico de partidas recentes (3 ultimas com W/L)
        self.match_history_frame = ctk.CTkFrame(self.root, fg_color=self.theme["bg2"], height=34, corner_radius=8)
        self.match_history_frame.pack(side="bottom", fill="x", padx=10, pady=(4, 0))
        self.match_history_frame.pack_propagate(False)
        ctk.CTkLabel(self.match_history_frame, text="Recentes:", font=styles.FONTS["body"], text_color=self.theme["txt2"]).pack(side="left", padx=(8, 4))
        self.match_history_icons = []
        for _ in range(3):
            lbl = ctk.CTkLabel(self.match_history_frame, text="-", font=styles.FONTS["body"], text_color=self.theme["txt2"])
            lbl.pack(side="left", padx=4)
            self.match_history_icons.append(lbl)
        
        # Historico texto
        self.history_label = ctk.CTkLabel(self.root, text="", font=styles.FONTS["body"], text_color=self.theme["txt2"])
        self.history_label.pack(side="bottom", pady=(6, 0))
        
        # Rodape de conformidade
        self.compliance_lbl = ctk.CTkLabel(
            self.root,
            text="Assistente de analise contextual. Dados historicos. Decisao final e sua.",
            font=styles.FONTS["body"],
            text_color=self.theme["txt2"]
        )
        self.compliance_lbl.pack(side="bottom", pady=(0, 10))

    def _copy_comp(self):
        try:
            d = self.current_data
            if not d or not d.get("comp"):
                self.status.configure(text="Nenhuma composicao disponivel para copiar.")
                return
            
            # Usa o codigo pre-gerado via API LCU se disponivel
            import_code = d.get("import_code", "")
            if import_code:
                pyperclip.copy(import_code)
                self.status.configure(text=f"Codigo copiado! Cole no planejador de equipe.")
                return
            
            # Fallback: gera string hex
            units = d.get("units", [])
            hex_codes = []
            for unit in units:
                code = CHAMPION_HEX.get(unit)
                if code:
                    hex_codes.append(code)
            hex_codes += ["00"] * (10 - len(hex_codes))
            
            if hex_codes:
                from core.config import get_tft_set
                tft_set = get_tft_set()
                import_string = "01" + "".join(hex_codes) + tft_set
                pyperclip.copy(import_string)
                self.status.configure(text=f"Codigo copiado! ({len(units)} unidades)")
            else:
                self.status.configure(text="Nenhum campeao valido encontrado.")
        except Exception as e:
            self.status.configure(text=f"Erro ao copiar: {str(e)}")

    def _reanalyze(self):
        if self.cmd_q:
            # Envia augment manual se preenchido
            manual_aug = self.manual_aug_var.get().strip()
            self.cmd_q.put({"action": "reanalyze", "manual_augment": manual_aug})
            if manual_aug:
                self.status.configure(text=f"Reanalise solicitada com augment '{manual_aug}'...")
                # Adiciona ao display local
                current_registered = self.current_data.get("registered_augments", [])
                if manual_aug not in current_registered:
                    current_registered.append(manual_aug)
                    self.current_data["registered_augments"] = current_registered
                    aug_text = "Registrados: " + ", ".join([pt_augment(a) for a in current_registered])
                    self.registered_augments_lbl.configure(text=aug_text)
            else:
                self.status.configure(text="Reanalise solicitada...")
        else:
            self.status.configure(text="Erro: sem conexao com o modulo de analise.")

    def _register_augment(self):
        """Abre dialogo para registrar augment escolhido"""
        if self.feedback_frame:
            return  # Ja tem dialogo aberto
        
        def submit_augment(augment_name):
            if self.cmd_q:
                self.cmd_q.put({"action": "register_augment", "augment": augment_name})
                self.status.configure(text=f"Augment '{augment_name}' registrado!")
            self.feedback_frame.destroy()
            self.feedback_frame = None
        
        self.feedback_frame = ctk.CTkFrame(self.root, fg_color=self.theme["bg2"], corner_radius=8)
        self.feedback_frame.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(self.feedback_frame, text="Qual augment voce pegou?", font=styles.FONTS["head"]).pack(padx=20, pady=(10, 5))
        
        # Campo de entrada
        entry = ctk.CTkEntry(self.feedback_frame, width=200, font=styles.FONTS["body"], placeholder_text="Nome do augment...")
        entry.pack(padx=20, pady=5)
        entry.focus()
        
        def on_confirm():
            val = entry.get().strip()
            if val:
                submit_augment(val)
        
        ctk.CTkButton(self.feedback_frame, text="Confirmar", command=on_confirm, fg_color="#a6e3a1", text_color="#181825").pack(pady=5)
        ctk.CTkButton(self.feedback_frame, text="Cancelar", command=lambda: (self.feedback_frame.destroy(), setattr(self, 'feedback_frame', None))).pack(pady=(0, 10))
        entry.bind("<Return>", lambda e: on_confirm())

    def _export_history(self):
        """Exporta historico de partidas para CSV e JSON"""
        import datetime
        try:
            from core.memory_db import MemoryDB
            mem = MemoryDB()
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            export_dir = Path("data/exports")
            export_dir.mkdir(parents=True, exist_ok=True)
            
            csv_path = export_dir / f"historico_{timestamp}.csv"
            json_path = export_dir / f"historico_{timestamp}.json"
            
            success_csv = mem.export_csv(str(csv_path))
            success_json = mem.export_json(str(json_path))
            
            if success_csv and success_json:
                self.status.configure(text=f"Historico exportado para data/exports/")
            elif success_csv:
                self.status.configure(text=f"CSV exportado: {csv_path}")
            elif success_json:
                self.status.configure(text=f"JSON exportado: {json_path}")
            else:
                self.status.configure(text="Erro ao exportar historico")
        except Exception as e:
            self.status.configure(text=f"Erro: {str(e)}")

    def _toggle_streamer_safe(self):
        """Ativa/desativa modo streamer-safe"""
        self._streamer_safe = not self._streamer_safe
        if self._streamer_safe:
            self.streamer_btn.configure(text="Modo Streamer: ON", fg_color="#f38ba8")
            self.status.configure(text="Modo streamer ativado - nomes ocultos")
        else:
            self.streamer_btn.configure(text="Modo Streamer: OFF", fg_color="#45475a")
            self.status.configure(text="Modo streamer desativado")
        
        # Atualiza oponentes visiveis
        self._update_opponent_display()

    def _anonymize_name(self, name: str) -> str:
        """Anonimiza nome para modo streamer-safe"""
        if not self._streamer_safe:
            return name
        # Retorna apenas as 2 primeiras letras + ***
        if len(name) > 2:
            return name[:2] + "***"
        return "***"

    def _update_opponent_display(self):
        """Atualiza exibicao dos oponentes baseado no modo streamer-safe"""
        for card in self.opp_cards:
            display_name = self._anonymize_name(card.name)
            card.lbl.configure(text=display_name)

    def _switch_comp(self, comp_name):
        d = self.current_data
        alt = d.get("alt_comps", [])
        for ac in alt:
            if ac.get("name") == comp_name:
                self.comp_lbl.configure(text=comp_name)
                self.viab_lbl.configure(text="")
                self.pos_lbl.configure(text=ac.get("posicionamento", "-"))
                self.levels_lbl.configure(text=ac.get("levels", "-"))
                self.dicas_lbl.configure(text=ac.get("dicas", "-"))
                self.contra_lbl.configure(text="-")
                self.motivo_lbl.configure(text=f"Comp alternativa (sem analise de IA)")
                # Atualiza unidades com itens abaixo do nome
                for w in self.units_frame.winfo_children(): w.destroy()
                units = ac.get("units", [])
                items_info = ac.get("core_items", {})
                if units:
                    row = ctk.CTkFrame(self.units_frame, fg_color="transparent")
                    row.pack(fill="x")
                    tanks_set = set(ac.get("tanks", []))
                    for u in units:
                        unit_items = items_info.get(u, [])
                        UnitRow(row, u, items=unit_items, is_tank=(u in tanks_set)).pack(side="left", padx=4)
                # Atualiza augments
                for w in self.augments_frame.winfo_children(): w.destroy()
                raw_augments = ac.get("augments", "")
                if isinstance(raw_augments, str):
                    aug_list = [a.strip() for a in raw_augments.split(",") if a.strip()]
                else:
                    aug_list = raw_augments if isinstance(raw_augments, list) else []
                if aug_list:
                    aug_text = " | ".join([pt_augment(a) for a in aug_list])
                    ctk.CTkLabel(self.augments_frame, text=aug_text, font=styles.FONTS["body"], text_color="#cdd6f4", justify="left", wraplength=480).pack(anchor="w")
                # Atualiza dados atuais
                self.current_data["comp"] = comp_name
                self.current_data["units"] = units
                self.current_data["core_items"] = items_info
                self.current_data["import_code"] = ""
                self.current_data["posicionamento"] = ac.get("posicionamento", "")
                self.current_data["tanks"] = ac.get("tanks", [])
                self.current_data["levels"] = ac.get("levels", "")
                self.current_data["dicas"] = ac.get("dicas", "")
                self.current_data["augments"] = aug_list
                # Mantem augments registrados
                registered = self.current_data.get("registered_augments", [])
                if registered:
                    aug_text = "Registrados: " + ", ".join([pt_augment(a) for a in registered])
                    self.registered_augments_lbl.configure(text=aug_text)
                else:
                    self.registered_augments_lbl.configure(text="")
                # Proximos augments
                next_augs = ac.get("next_augments", [])
                if next_augs:
                    next_text = "Proximos augments: " + ", ".join(next_augs)
                    self.next_augments_lbl.configure(text=next_text)
                else:
                    self.next_augments_lbl.configure(text="")
                self.status.configure(text=f"Comp alterada para: {comp_name}")
                break

    def _update_comp(self, data):
        self.current_data = data
        self.comp_lbl.configure(text=data.get("comp", "-"))
        viab = data.get("viabilidade", None)
        if viab is not None:
            color = "#a6e3a1" if viab >= 70 else "#f9e2af" if viab >= 40 else "#f38ba8"
            self.viab_lbl.configure(text=f"[{viab}% viavel]", text_color=color)
        else:
            self.viab_lbl.configure(text="")
        
        # Risco de contestacao
        contest_warning = data.get("contest_warning", "")
        contest_risk = data.get("contest_risk", "")
        if contest_warning:
            if contest_risk == "ALTA":
                c_color = "#f38ba8"
            elif contest_risk == "MEDIA":
                c_color = "#f9e2af"
            else:
                c_color = "#a6e3a1"
            self.contest_lbl.configure(text=contest_warning, text_color=c_color)
        else:
            self.contest_lbl.configure(text="")
        
        # Comps alternativas
        for w in self.alt_frame.winfo_children(): w.destroy()
        alt_comps = data.get("alt_comps", [])
        if alt_comps:
            for ac in alt_comps:
                name = ac.get("name", "")
                tier = ac.get("tier", "")
                win_rate = ac.get("win_rate", "")
                tooltip_text = f"{name} (Tier {tier})"
                if win_rate:
                    tooltip_text += f"\nWin Rate: {win_rate}%"
                tooltip_text += "\nClique para ver detalhes"
                
                btn = ctk.CTkButton(self.alt_frame, text=f"{name} (T{tier})", width=100, height=24,
                                    font=styles.FONTS["small"], fg_color="#313244", hover_color="#45475a",
                                    command=lambda n=name: self._switch_comp(n))
                btn.pack(side="left", padx=2)
                ToolTip(btn, text=tooltip_text)
        
        # Nova sugestao?
        gid = data.get("game_id", None)
        if gid is not None and gid != self.last_game_id:
            self.last_game_id = gid
            self.opp_cards = []
            self._next_idx = 0
            self.nova_lbl.configure(text="[NOVA!]")
            self.root.after(8000, lambda: self.nova_lbl.configure(text=""))

        # Win rate
        wr = data.get("comp_win_rate", "")
        avg = data.get("comp_avg_placement", "")
        games = data.get("comp_games", "")
        wr_parts = []
        if wr:
            wr_parts.append(f"WR: {wr}%")
        if avg:
            wr_parts.append(f"Avg: {avg}")
        if games:
            wr_parts.append(f"{games} jogos")
        self.wr_lbl.configure(text=" | ".join(wr_parts) if wr_parts else "")
        # Oponentes interativos
        opps = data.get("opponents", [])
        if opps and not self.opp_cards:
            for w in self.opp_frame.winfo_children(): w.destroy()
            row = ctk.CTkFrame(self.opp_frame, fg_color="transparent")
            row.pack(fill="x")
            self.opp_cards = []
            self._next_idx = 0
            for o in opps:
                if isinstance(o, dict):
                    name = self._anonymize_name(o.get("name","?"))
                    card = OpponentCard(row, name, {"rank": o.get("rank",""), "avg": o.get("avg","")}, self._predict_next)
                else:
                    name = self._anonymize_name(str(o))
                    card = OpponentCard(row, name, {}, self._predict_next)
                card.pack(side="left", padx=3, pady=1)
                self.opp_cards.append(card)
            self._predict_next()
        
        # Prompt (com anonymizacao em modo streamer-safe)
        prompt_txt = data.get("prompt", "")
        if prompt_txt:
            # Limita o tamanho do prompt exibido
            display_prompt = prompt_txt[:500] + "..." if len(prompt_txt) > 500 else prompt_txt
            # Em modo streamer-safe, anonymiza nomes no prompt
            if self._streamer_safe:
                import re
                # Remove PUUIDs (strings longas hex)
                display_prompt = re.sub(r'[0-9a-f]{32,}', '[PUUID]', display_prompt)
                # Remove nomes de jogadores (sequencias de palavras antes de #)
                display_prompt = re.sub(r'\w+#\w+', '[Jogador]', display_prompt)
            self.prompt_lbl.configure(text=display_prompt)
        else:
            self.prompt_lbl.configure(text="(sem prompt)")
        
        self.pos_lbl.configure(text=data.get("posicionamento", "-"))
        self.levels_lbl.configure(text=data.get("levels", "-"))
        self.dicas_lbl.configure(text=data.get("dicas", "-"))
        self.contra_lbl.configure(text=data.get("contra", "-"))
        self.motivo_lbl.configure(text=data.get("motivo", "-"))

        # Unidades com imagens e itens abaixo do nome
        for w in self.units_frame.winfo_children(): w.destroy()
        units = data.get("units", [])
        items_info = data.get("core_items", {})
        if units:
            row = ctk.CTkFrame(self.units_frame, fg_color="transparent")
            row.pack(fill="x")
            tanks_set = set(data.get("tanks", []))
            for u in units:
                unit_items = items_info.get(u, [])
                UnitRow(row, u, items=unit_items, is_tank=(u in tanks_set)).pack(side="left", padx=4)

        # Augments (texto apenas)
        for w in self.augments_frame.winfo_children(): w.destroy()
        raw_augments = data.get("augments", "")
        if isinstance(raw_augments, str):
            aug_list = [a.strip() for a in raw_augments.split(",") if a.strip()]
        else:
            aug_list = raw_augments if isinstance(raw_augments, list) else []
        if aug_list:
            aug_text = " | ".join([pt_augment(a) for a in aug_list])
            ctk.CTkLabel(self.augments_frame, text=aug_text, font=styles.FONTS["body"], text_color="#cdd6f4", justify="left", wraplength=480).pack(anchor="w")
        
        # Augments registrados pelo usuario
        registered = data.get("registered_augments", [])
        if registered:
            aug_text = "Registrados: " + ", ".join([pt_augment(a) for a in registered])
            self.registered_augments_lbl.configure(text=aug_text)
        else:
            self.registered_augments_lbl.configure(text="")

        # Proximos augments
        next_augs = data.get("next_augments", [])
        if next_augs:
            next_text = "Proximos augments: " + ", ".join(next_augs)
            self.next_augments_lbl.configure(text=next_text)
        else:
            self.next_augments_lbl.configure(text="")

    def _predict_next(self):
        alive = [c for c in self.opp_cards if c.alive]
        if len(alive) <= 1:
            self.prox_lbl.configure(text="")
            return
        if not hasattr(self, "_next_idx"):
            self._next_idx = 0
        self._next_idx = self._next_idx % len(alive)
        prox = alive[self._next_idx]
        self._next_idx += 1
        self.prox_lbl.configure(text=f"Proximo: {prox.name} (estimativa)")

    def _show_feedback(self, data):
        if self.feedback_frame: return
        from core.memory_db import MemoryDB
        mem = MemoryDB()
        def submit(followed, rating=3):
            mem.log_match({
                "ts": datetime.datetime.now().isoformat(),
                "comp": data.get("comp", ""), "placement": data.get("placement", 8),
                "won": data.get("placement", 8) <= 4, "followed": followed, "rating": rating,
                "traits": "[]", "stage": "Post", "gold": 0, "level": 0
            })
            self.feedback_frame.destroy()
            self.feedback_frame = None
            self.q.put({"status": "Registrado. Bom jogo!"})
        self.feedback_frame = ctk.CTkFrame(self.root, fg_color=self.theme["bg2"], corner_radius=8)
        self.feedback_frame.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(self.feedback_frame, text=f"{data.get('placement', '?')} lugar. A sugestao foi util?", font=styles.FONTS["head"]).pack(padx=20, pady=10)
        for r in range(1, 6):
            ctk.CTkButton(self.feedback_frame, text="*"*r, width=30, command=lambda rt=r: submit(True, rt)).pack(side="left", padx=2, pady=5)
        ctk.CTkButton(self.feedback_frame, text="Segui", command=lambda: submit(True)).pack(side="left", padx=5)
        ctk.CTkButton(self.feedback_frame, text="Ignorei", fg_color=self.theme["red"], command=lambda: submit(False)).pack(side="left", padx=5)

    def _loop(self):
        try:
            while not self.q.empty():
                d = self.q.get_nowait()
                if d.get("status") == "end_of_game":
                    self._show_feedback(d)
                    continue
                if "status" in d:
                    self.status.configure(text=d["status"])
                    continue
                
                # Throttling: so atualiza se mudou de fato
                comp_changed = d.get("comp", "") != self.current_data.get("comp", "")
                game_changed = d.get("game_id") != self.current_data.get("game_id")
                
                if not comp_changed and not game_changed:
                    # So atualiza labels que podem mudar sem mudar comp
                    if d.get("viabilidade") != self.current_data.get("viabilidade"):
                        self._update_comp(d)
                    continue
                
                ctx = MemoryDB().get_context()
                if ctx["total"] > 0:
                    top = ctx.get("top_comps", [])
                    top_text = ""
                    for c in top:
                        top_text += f" {c['comp']}({c['w']}%)"
                    self.history_label.configure(text=f"{ctx['total']} partidas | {ctx['win_rate']}% WR{top_text}")
                self.status.configure(text="Atualizado")
                self._update_comp(d)
            
            # Atualiza status da chave Riot a cada 5s (countdown)
            import time
            now = time.time()
            if now - self._last_riot_key_check > 5:
                self._last_riot_key_check = now
                try:
                    from core.riot_key_manager import riot_key_mgr
                    icon = riot_key_mgr.status_icon
                    countdown = riot_key_mgr.countdown_text
                    self.riot_key_lbl.configure(text=f"{icon} {countdown}")
                except Exception as e:
                    logging.debug(f"Riot key status unavailable: {e}")
                
                # Rate limit visual
                try:
                    from core.api_wrapper import safe_req
                    if safe_req.is_rate_limited:
                        secs = safe_req.rate_limit_seconds_remaining
                        self.rate_limit_lbl.configure(text=f"⏳ Rate limit: {secs}s")
                    else:
                        self.rate_limit_lbl.configure(text="")
                except Exception as e:
                    logging.debug(f"Rate limit status unavailable: {e}")
        except queue.Empty:
            pass
        self.root.after(100, self._loop)

    def _close(self, e=None):
        from core.config import save_config
        c = self.cfg["window"]
        c["x"], c["y"] = self.root.winfo_x(), self.root.winfo_y()
        save_config(self.cfg)
        self.root.destroy()
        if self.cmd_q:
            self.cmd_q.put({"action": "quit"})

    def run(self):
        print("Overlay iniciando...")
        self.root.mainloop()
