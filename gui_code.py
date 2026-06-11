import random
import time
import json
import os
import threading
import math

import pygame
from PIL import Image

from modelling_search import BFSBot, AStarBot, DFSBot
from modelling_ensemble import RandomForestBot, XGBBot

# ─────────────────────────────────────────────
#  PALETTE  — Cyberpunk Neon Casino
# ─────────────────────────────────────────────
BG          = ( 10,   5,  20)   # near-black with purple tint
FELT        = ( 10,  80,  50)   # deep casino green
FELT_DARK   = (  5,  50,  30)   # darker green
PANEL       = ( 18,  12,  35)   # dark purple panel
PANEL_BD    = ( 80,  20, 120)   # purple border
GOLD        = (255, 210,   0)   # neon yellow-gold
GOLD_DIM    = (140, 110,   0)
COPPER      = (255, 100,   0)   # neon orange (replaces copper)
CYAN        = (  0, 230, 255)   # electric cyan
NEON_PINK   = (255,  20, 147)   # hot pink accent
NEON_GREEN  = (  0, 255, 100)   # neon green
RED         = (255,  30,  80)   # neon red
GREEN_OK    = (  0, 255, 120)
TEXT        = (210, 200, 240)   # lavender-white
WHITE       = (255, 255, 255)
BLACK       = (  0,   0,   0)
DIS_BG      = ( 35,  28,  55)
DIS_FG      = ( 80,  70, 100)

BOT_OPTIONS = [
    "BFS (Search)",
    "DFS (Search)",
    "A* (Search)",
    "Random Forest (Ensemble)",
    "XGBoost (Ensemble)",
]

# ─────────────────────────────────────────────
#  GAME ENGINE
# ─────────────────────────────────────────────
class DominoEngine:
    def __init__(self):
        self.boneyard, self.player_hand, self.bot_hand = [], [], []
        self.board, self.left_end, self.right_end = [], None, None
        self.reset_game()

    def reset_game(self):
        self.boneyard = [(i, j) for i in range(7) for j in range(i, 7)]
        random.shuffle(self.boneyard)
        self.player_hand = [self.boneyard.pop() for _ in range(7)]
        self.bot_hand    = [self.boneyard.pop() for _ in range(7)]
        self.board, self.left_end, self.right_end = [], None, None
        self.player_last_pass = (-1, -1)
        self.bot_last_pass    = (-1, -1)

    def get_valid_moves(self, hand):
        if not self.board:
            return [(t, 'first') for t in hand]
        valid = []
        for t in hand:
            if self.left_end  in t: valid.append((t, 'left'))
            if self.right_end in t: valid.append((t, 'right'))
        return valid

    def play_tile(self, hand, move):
        tile, side = move
        hand.remove(tile)
        if side == 'first':
            self.board.append(tile)
            self.left_end, self.right_end = tile
        elif side == 'left':
            if tile[1] == self.left_end:
                self.board.insert(0, tile);     self.left_end = tile[0]
            else:
                self.board.insert(0, (tile[1], tile[0])); self.left_end = tile[1]
        elif side == 'right':
            if tile[0] == self.right_end:
                self.board.append(tile);        self.right_end = tile[1]
            else:
                self.board.append((tile[1], tile[0]));    self.right_end = tile[0]

    def draw_tile(self, hand):
        if self.boneyard:
            hand.append(self.boneyard.pop()); return True
        return False

    def calculate_score(self, hand):
        return sum(t[0]+t[1] for t in hand)

# ─────────────────────────────────────────────
#  TINY UI PRIMITIVES
# ─────────────────────────────────────────────
def rrect(surf, color, rect, r=10, border=None, bw=2):
    pygame.draw.rect(surf, color, rect, border_radius=r)
    if border:
        pygame.draw.rect(surf, border, rect, bw, border_radius=r)

def txt_c(surf, text, font, color, cx, cy):
    """Solid-color centred text — no glow."""
    s = font.render(text, True, color)
    surf.blit(s, s.get_rect(center=(cx, cy)))

def txt_l(surf, text, font, color, x, y):
    """Solid-color left-aligned text — no glow."""
    s = font.render(text, True, color)
    surf.blit(s, (x, y))

# glow() kept as internal helper ONLY for the scanline effect on board;
# all visible text now calls txt_c / txt_l directly.
def _neon_outline(surf, text, font, color, cx, cy):
    """Thin 1-pixel outline for a crisp neon look — no blurry glow passes."""
    dark = tuple(max(0, c - 120) for c in color)
    s = font.render(text, True, dark)
    r = s.get_rect(center=(cx, cy))
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        surf.blit(s, (r.x + dx, r.y + dy))
    txt_c(surf, text, font, color, cx, cy)

# ─────────────────────────────────────────────
#  BUTTON
# ─────────────────────────────────────────────
class Button:
    def __init__(self, rect, label, font,
                 fg=CYAN, bg=PANEL, bd=COPPER,
                 hfg=BG, hbg=COPPER, r=9):
        self.rect  = pygame.Rect(rect)
        self.label = label
        self.font  = font
        self.fg, self.bg, self.bd   = fg, bg, bd
        self.hfg, self.hbg         = hfg, hbg
        self.r       = r
        self.enabled = True
        self.hovered = False

    def draw(self, surf):
        if not self.enabled:
            rrect(surf, DIS_BG, self.rect, self.r, (60, 40, 80), 1)
            s = self.font.render(self.label, True, DIS_FG)
            surf.blit(s, s.get_rect(center=self.rect.center))
            return
        bg = self.hbg if self.hovered else self.bg
        fg = self.hfg if self.hovered else self.fg
        rrect(surf, bg, self.rect, self.r, self.bd, 2)
        s = self.font.render(self.label, True, fg)
        surf.blit(s, s.get_rect(center=self.rect.center))

    def on(self, ev):
        if ev.type == pygame.MOUSEMOTION:
            self.hovered = self.enabled and self.rect.collidepoint(ev.pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.enabled and self.rect.collidepoint(ev.pos):
                return True
        return False

# ─────────────────────────────────────────────
#  TEXT INPUT
# ─────────────────────────────────────────────
class TextInput:
    def __init__(self, rect, font, default=""):
        self.rect    = pygame.Rect(rect)
        self.font    = font
        self.text    = default
        self.active  = False
        self._blink  = True
        self._t      = 0

    @property
    def value(self): return self.text

    def draw(self, surf):
        bd = GOLD if self.active else COPPER
        rrect(surf, PANEL, self.rect, 8, bd, 2)
        disp = self.text + ("|" if self.active and self._blink else "")
        s = self.font.render(disp, True, CYAN)
        surf.blit(s, s.get_rect(center=self.rect.center))

    def update(self, ms):
        self._t += ms
        if self._t > 500:
            self._blink = not self._blink; self._t = 0

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(ev.pos)
        if ev.type == pygame.KEYDOWN and self.active:
            if ev.key == pygame.K_BACKSPACE: self.text = self.text[:-1]
            elif ev.key not in (pygame.K_RETURN, pygame.K_TAB):
                if len(self.text) < 20: self.text += ev.unicode

# ─────────────────────────────────────────────
#  DROPDOWN  — draws on top of everything else
#  via a z-order flag; call draw_overlay() last
# ─────────────────────────────────────────────
class Dropdown:
    def __init__(self, rect, options, font):
        self.rect    = pygame.Rect(rect)
        self.options = options
        self.font    = font
        self.idx     = 0
        self.open    = False
        self.hi      = -1
        self.enabled = True

    @property
    def selected(self): return self.options[self.idx]

    def draw(self, surf):
        """Draw only the collapsed header bar (never the open list here)."""
        bg = DIS_BG if not self.enabled else PANEL
        fg = DIS_FG if not self.enabled else CYAN
        bd = (60, 40, 80) if not self.enabled else COPPER
        rrect(surf, bg, self.rect, 8, bd, 2)
        s = self.font.render(self.selected, True, fg)
        surf.blit(s, s.get_rect(midleft=(self.rect.x + 10, self.rect.centery)))
        if self.enabled:
            ax, ay = self.rect.right - 18, self.rect.centery
            arrow_color = NEON_PINK if self.open else COPPER
            pygame.draw.polygon(surf, arrow_color,
                [(ax - 6, ay - 4), (ax + 6, ay - 4), (ax, ay + 5)])

    def draw_overlay(self, surf):
        """Draw the open list on top of everything — call this last in draw()."""
        if not self.open or not self.enabled:
            return
        ih = self.rect.height
        total_h = len(self.options) * ih
        # Draw a solid backdrop so it covers sibling widgets
        backdrop = pygame.Rect(self.rect.x - 1, self.rect.bottom - 1,
                               self.rect.width + 2, total_h + 2)
        pygame.draw.rect(surf, PANEL_BD, backdrop, border_radius=6)

        for i, opt in enumerate(self.options):
            r = pygame.Rect(self.rect.x, self.rect.bottom + i * ih,
                            self.rect.width, ih)
            ibg = NEON_PINK if i == self.hi else (30, 18, 50)
            ifg = BLACK      if i == self.hi else CYAN
            rrect(surf, ibg, r, 4, COPPER, 1)
            s2 = self.font.render(opt, True, ifg)
            surf.blit(s2, s2.get_rect(midleft=(r.x + 10, r.centery)))

    def handle(self, ev):
        """
        Returns:
            True   — an option was selected (idx changed)
            'consumed' — click was inside the open list area (nothing selected,
                         but the event must NOT propagate to buttons behind)
            False  — event not relevant to this dropdown
        """
        if not self.enabled: return False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.rect.collidepoint(ev.pos):
                self.open = not self.open
                return 'consumed'   # header click: don't let it fall through
            if self.open:
                ih = self.rect.height
                # Check if the click is anywhere inside the open list area
                list_rect = pygame.Rect(self.rect.x, self.rect.bottom,
                                        self.rect.width,
                                        len(self.options) * ih)
                if list_rect.collidepoint(ev.pos):
                    for i in range(len(self.options)):
                        r = pygame.Rect(self.rect.x, self.rect.bottom + i * ih,
                                        self.rect.width, ih)
                        if r.collidepoint(ev.pos):
                            self.idx = i; self.open = False; return True
                    self.open = False
                    return 'consumed'   # clicked in list area but no item hit
                # Click outside the dropdown — close it but let event propagate
                self.open = False
        if ev.type == pygame.MOUSEMOTION and self.open:
            ih = self.rect.height
            self.hi = -1
            for i in range(len(self.options)):
                r = pygame.Rect(self.rect.x, self.rect.bottom + i * ih,
                                self.rect.width, ih)
                if r.collidepoint(ev.pos): self.hi = i
        return False

# ─────────────────────────────────────────────
#  THEMED MODAL
# ─────────────────────────────────────────────
class Modal:
    def __init__(self, font_title, font_body, font_btn):
        self.ft, self.fb, self.fbtn = font_title, font_body, font_btn
        self.visible = False
        self.title   = ""
        self.lines   = []
        self.buttons = []
        self.result  = None
        self._color  = GOLD
        self._built  = False
        self._btn_labels = []

    def show(self, title, body_lines, btn_labels, color=GOLD):
        self.title   = title
        self.lines   = body_lines
        self._color  = color
        self.result  = None
        self.visible = True
        self.buttons = []
        self._btn_labels = btn_labels
        self._built  = False

    def _build_buttons(self, W, H, box):
        n = len(self._btn_labels)
        bw, bh = 160, 42
        gap = 20
        total = n * bw + (n - 1) * gap
        sx = box.centerx - total // 2
        by = box.bottom - bh - 22
        self.buttons = []
        for i, lbl in enumerate(self._btn_labels):
            bx = sx + i * (bw + gap)
            btn = Button((bx, by, bw, bh), lbl, self.fbtn,
                         fg=BG, bg=self._color, bd=self._color,
                         hfg=self._color, hbg=PANEL)
            self.buttons.append(btn)
        self._built = True

    def draw(self, surf):
        if not self.visible: return
        W, H = surf.get_size()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 180))
        surf.blit(ov, (0, 0))

        bw, bh = min(560, W - 80), 280
        box = pygame.Rect(W // 2 - bw // 2, H // 2 - bh // 2, bw, bh)
        rrect(surf, PANEL, box, 16, self._color, 3)
        stripe = pygame.Rect(box.x + 3, box.y + 3, box.width - 6, 40)
        pygame.draw.rect(surf, tuple(c // 4 for c in self._color), stripe,
                         border_radius=13)

        # Solid title — no glow
        txt_c(surf, self.title, self.ft, self._color, box.centerx, box.y + 28)

        pygame.draw.line(surf, self._color,
                         (box.x + 20, box.y + 55), (box.right - 20, box.y + 55), 1)

        y = box.y + 72
        for line in self.lines:
            s = self.fb.render(line, True, TEXT)
            surf.blit(s, s.get_rect(centerx=box.centerx, y=y))
            y += 30

        if not self._built:
            self._build_buttons(W, H, box)

        for b in self.buttons:
            b.draw(surf)

    def handle(self, ev):
        if not self.visible: return
        for b in self.buttons:
            if b.on(ev):
                self.result = b.label
                self.visible = False

# ─────────────────────────────────────────────
#  ACTION POPUP  (Draw / Pass prompt)
# ─────────────────────────────────────────────
class ActionPopup:
    def __init__(self, font_h, font_b, font_btn):
        self.fh, self.fb, self.fbtn = font_h, font_b, font_btn
        self.visible = False
        self._action = None
        self._btn = None
        self.triggered = False

    def show(self, action: str, board_rect: pygame.Rect):
        self.visible   = True
        self.triggered = False
        self._action   = action
        bx = board_rect.centerx
        by = board_rect.centery

        pw, ph = 320, 140
        px = bx - pw // 2
        py = by - ph // 2
        self._box = pygame.Rect(px, py, pw, ph)

        bw, bh = 200, 42
        btn_rect = (px + pw // 2 - bw // 2, py + ph - bh - 18, bw, bh)
        if action == 'draw':
            label      = "Draw Tile"
            color      = CYAN
            self._msg  = "No valid moves!"
            self._sub  = "Draw a tile from the boneyard."
        else:
            label      = "Pass Turn"
            color      = COPPER
            self._msg  = "Boneyard is empty!"
            self._sub  = "No moves available — pass your turn."

        self._btn = Button(btn_rect, label, self.fbtn,
                           fg=BG, bg=color, bd=color,
                           hfg=color, hbg=PANEL)

    def hide(self):
        self.visible = False

    def draw(self, surf):
        if not self.visible or self._btn is None: return
        box   = self._box
        color = CYAN if self._action == 'draw' else COPPER
        sh = pygame.Surface((box.width + 8, box.height + 8), pygame.SRCALPHA)
        sh.fill((0, 0, 0, 120))
        surf.blit(sh, (box.x - 4, box.y - 4))

        rrect(surf, PANEL, box, 14, color, 3)
        stripe = pygame.Rect(box.x + 3, box.y + 3, box.width - 6, 36)
        pygame.draw.rect(surf, tuple(c // 4 for c in color), stripe,
                         border_radius=12)
        # Solid text — no glow
        txt_c(surf, self._msg, self.fh, color, box.centerx, box.y + 22)
        pygame.draw.line(surf, color,
                         (box.x + 20, box.y + 44), (box.right - 20, box.y + 44), 1)
        txt_c(surf, self._sub, self.fb, TEXT, box.centerx, box.y + 72)
        self._btn.draw(surf)

    def handle(self, ev):
        if not self.visible or self._btn is None: return
        if self._btn.on(ev):
            self.triggered = True
            self.visible   = False

# ─────────────────────────────────────────────
#  LEADERBOARD OVERLAY
# ─────────────────────────────────────────────
class LeaderboardOverlay:
    def __init__(self, leaderboard: dict, font_h, font_b, font_s):
        self.lb = leaderboard
        self.fh, self.fb, self.fs = font_h, font_b, font_s
        self.visible = False
        self.dd = Dropdown((0, 0, 300, 38), BOT_OPTIONS, font_s)
        self.close_btn = Button((0, 0, 140, 40), "Close", font_b)

    def show(self):
        self.visible = True

    def _layout(self, W, H):
        bw = min(700, W - 60)
        bh = min(500, H - 80)
        self._box = pygame.Rect(W // 2 - bw // 2, H // 2 - bh // 2, bw, bh)
        self.dd.rect = pygame.Rect(
            self._box.centerx - 150, self._box.y + 58, 300, 38)
        self.close_btn.rect = pygame.Rect(
            self._box.centerx - 70, self._box.bottom - 54, 140, 40)

    def draw(self, surf):
        if not self.visible: return
        W, H = surf.get_size()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        surf.blit(ov, (0, 0))
        self._layout(W, H)
        box = self._box
        rrect(surf, PANEL, box, 16, GOLD, 3)
        # Solid title
        txt_c(surf, "GLOBAL LEADERBOARDS", self.fh, GOLD,
              box.centerx, box.y + 28)
        pygame.draw.line(surf, COPPER,
                         (box.x + 20, box.y + 52), (box.right - 20, box.y + 52), 1)

        txt_c(surf, "Select Model:", self.fs, COPPER, box.centerx, box.y + 72)
        self.dd.draw(surf)

        cols = [("Username", 0.35), ("Fastest Time", 0.38), ("Wins", 0.27)]
        hx = box.x + 20
        hy = box.y + 108
        for hdr, frac in cols:
            cw = int(box.width * frac) - 8
            txt_l(surf, hdr, self.fs, COPPER, hx + 4, hy)
            hx += cw + 8
        pygame.draw.line(surf, COPPER,
                         (box.x + 10, hy + 20), (box.right - 10, hy + 20), 1)

        sel  = self.dd.selected
        data = self.lb.get(sel, {})
        rows = []
        if isinstance(data, dict):
            for u, s in data.items():
                if isinstance(s, dict):
                    ft = s.get("fastest_time", "N/A")
                    if isinstance(ft, float) and ft == float('inf'): ft = "N/A"
                    elif isinstance(ft, (int, float)): ft = f"{ft:.1f}s"
                    rows.append((u, str(ft), str(s.get("wins", 0))))
        rows.sort(key=lambda x: int(x[2]) if x[2].isdigit() else 0, reverse=True)

        ry = hy + 28
        for ri, (u, ft, w) in enumerate(rows[:12]):
            row_rect = pygame.Rect(box.x + 10, ry - 2, box.width - 20, 24)
            rbg = (28, 18, 48) if ri % 2 == 0 else PANEL
            rrect(surf, rbg, row_rect, 4)
            vals = [u, ft, w]
            rx2 = box.x + 20
            for vi, (v, frac) in enumerate(zip(vals, [0.35, 0.38, 0.27])):
                cw = int(box.width * frac) - 8
                vc = GOLD if vi == 2 else TEXT
                txt_l(surf, v, self.fs, vc, rx2 + 4, ry)
                rx2 += cw + 8
            ry += 26

        self.close_btn.draw(surf)
        # Draw dropdown overlay LAST so it appears above table rows
        self.dd.draw_overlay(surf)

    def handle(self, ev):
        if not self.visible: return False
        dd_result = self.dd.handle(ev)
        if dd_result:
            return False   # dropdown consumed the click; don't close overlay
        if self.close_btn.on(ev):
            self.visible = False; return True
        return False

# ─────────────────────────────────────────────
#  MAIN GAME
# ─────────────────────────────────────────────
class DominoGame:
    TILE_W = 80
    TILE_H = 40

    def __init__(self):
        pygame.init()
        info = pygame.display.Info()
        self.W = min(info.current_w, 1440)
        self.H = min(info.current_h - 50, 900)
        self.screen = pygame.display.set_mode(
            (self.W, self.H), pygame.RESIZABLE)
        pygame.display.set_caption("High Roller Dominoes: Player vs AI")
        self.clock = pygame.time.Clock()

        self._fonts()
        self._load_assets()

        self.leaderboard_file = "leaderboard.json"
        self.leaderboard = self._load_lb()

        # ── game state
        self.engine  = DominoEngine()
        self.bot     = None
        self.player_turn        = True
        self.consecutive_passes = 0
        self.game_active        = False
        self.is_paused          = False
        self.game_over          = False
        self.game_over_drawn    = False

        # ── timer
        self.accumulated_time = 0.0
        self.last_ms          = 0
        self.timer_running    = False

        # ── interaction
        self.hand_coords   = []
        self.left_end_cx   = 0
        self.left_end_cy   = 0
        self.right_end_cx  = 0
        self.right_end_cy  = 0
        self.clicked_tile  = None
        self.drag_item_idx = None
        self.drag_x = self.drag_y = 0
        self.drag_surf = None
        self.press_x = self.press_y = 0
        self._dragged_tile = None
        self._dbl_tile = None
        self._dbl_t    = 0

        # ── status / board notification
        self.status_msg   = "Place your bets and press Start Game to deal!"
        self.status_color = GOLD
        self.board_notif_msg   = ""   # notification shown above bot info on board
        self.board_notif_color = CYAN

        # ── overlays
        self.modal        = Modal(self.fn_title, self.fn_med, self.fn_btn)
        self.action_popup = ActionPopup(self.fn_med, self.fn_small, self.fn_btn)
        self.lb_overlay   = LeaderboardOverlay(
            self.leaderboard, self.fn_title, self.fn_med, self.fn_small)

        # ── bot sync
        self.bot_thinking  = False
        self.pending_modal = None

        # ── page
        self.page = "login"

        self._build_login()
        self._build_game()

    # ── fonts ──────────────────────────────────
    def _fonts(self):
        # Try a monospace/tech font for cyberpunk feel, fall back gracefully
        def f(sz, bold=False):
            for name in ("Courier New", "Consolas", "Lucida Console", "Georgia"):
                try:
                    fnt = pygame.font.SysFont(name, sz, bold=bold)
                    if fnt: return fnt
                except:
                    pass
            return pygame.font.Font(None, sz)
        self.fn_title = f(32, True)
        self.fn_large = f(26, True)
        self.fn_med   = f(19)
        self.fn_small = f(15)
        self.fn_tiny  = f(13)
        self.fn_btn   = f(17, True)
        self.fn_timer = f(22, True)
        # Board-specific larger bold fonts (fix 4)
        self.fn_board_notif = f(18, True)
        self.fn_board_info  = f(20, True)
        self.fn_board_sub   = f(16, True)

    # ── tile assets ────────────────────────────
    def _load_assets(self):
        self.tile_surfs = {}
        adir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        if not os.path.exists(adir):
            print("Warning: assets/ not found"); return
        for i in range(7):
            for j in range(i, 7):
                path = os.path.join(adir, f"{i} {j}.png")
                if not os.path.exists(path): continue
                orig = Image.open(path).convert('RGBA')
                if orig.width > orig.height:
                    orig = orig.transpose(Image.ROTATE_270)
                base = orig.resize((self.TILE_H, self.TILE_W),
                                   Image.Resampling.LANCZOS)
                rots = {
                    'N': base,
                    'E': base.transpose(Image.ROTATE_90),
                    'S': base.transpose(Image.ROTATE_180),
                    'W': base.transpose(Image.ROTATE_270),
                }
                for ori, img in rots.items():
                    self.tile_surfs[f"{i}_{j}_{ori}"] = self._p2s(img)
                    if i != j:
                        rev = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
                        self.tile_surfs[f"{j}_{i}_{ori}"] = self._p2s(
                            rots[rev[ori]])

    @staticmethod
    def _p2s(pil_img):
        data = pil_img.tobytes()
        return pygame.image.fromstring(data, pil_img.size, "RGBA").convert_alpha()

    def _tile(self, a, b, orient, scale=1.0):
        key  = f"{a}_{b}_{orient}"
        surf = self.tile_surfs.get(key)
        if surf is None:
            surf = self._fallback(a, b, orient)
        if scale != 1.0:
            nw = max(1, int(surf.get_width() * scale))
            nh = max(1, int(surf.get_height() * scale))
            surf = pygame.transform.smoothscale(surf, (nw, nh))
        return surf

    def _fallback(self, a, b, orient, scale=1.0):
        tw = self.TILE_H if orient in ('N', 'S') else self.TILE_W
        th = self.TILE_W if orient in ('N', 'S') else self.TILE_H
        tw, th = max(1, int(tw * scale)), max(1, int(th * scale))
        s = pygame.Surface((tw, th), pygame.SRCALPHA)
        s.fill((240, 235, 220, 255))
        pygame.draw.rect(s, (50, 50, 50), (0, 0, tw, th), 2)
        if orient in ('N', 'S'):
            pygame.draw.line(s, (100, 100, 100), (0, th // 2), (tw, th // 2), 1)
        else:
            pygame.draw.line(s, (100, 100, 100), (tw // 2, 0), (tw // 2, th), 1)
        f2 = pygame.font.Font(None, max(8, int(14 * scale)))
        t1 = f2.render(str(a), True, (20, 20, 20))
        t2 = f2.render(str(b), True, (20, 20, 20))
        if orient in ('N', 'S'):
            s.blit(t1, t1.get_rect(center=(tw // 2, th // 4)))
            s.blit(t2, t2.get_rect(center=(tw // 2, 3 * th // 4)))
        else:
            s.blit(t1, t1.get_rect(center=(tw // 4, th // 2)))
            s.blit(t2, t2.get_rect(center=(3 * tw // 4, th // 2)))
        return s

    # ── leaderboard I/O ───────────────────────
    def _load_lb(self):
        default = {b: {} for b in BOT_OPTIONS}
        try:
            with open(self.leaderboard_file) as f:
                data = json.load(f)
            for b in BOT_OPTIONS:
                if b not in data or not isinstance(data[b], dict):
                    data[b] = {}
            return data
        except:
            return default

    def _save_lb(self):
        with open(self.leaderboard_file, "w") as f:
            json.dump(self.leaderboard, f, indent=4)

    # ─────────────────────────────────────────
    #  UI LAYOUT BUILDERS
    # ─────────────────────────────────────────
    def _build_login(self):
        W, H = self.W, self.H
        bw   = 380
        cx   = W // 2
        top  = H // 2 - 195

        self.li_name  = TextInput(
            (cx - bw // 2, top + 80, bw, 46), self.fn_med, default="HighRoller")
        self.li_dd    = Dropdown(
            (cx - bw // 2, top + 185, bw, 44), BOT_OPTIONS, self.fn_small)
        self.li_enter = Button(
            (cx - bw // 2, top + 292, bw, 50), "ENTER CASINO", self.fn_btn,
            fg=BG, bg=GOLD, bd=NEON_PINK, hfg=GOLD, hbg=PANEL)
        self.li_lb    = Button(
            (cx - bw // 2, top + 358, bw, 44), "VIEW LEADERBOARD", self.fn_med,
            fg=CYAN, bg=PANEL, bd=COPPER, hfg=BG, hbg=CYAN)

    def _build_game(self):
        W, H = self.W, self.H
        PW   = 215
        PX   = 14
        PY   = 14
        PH   = H - 28
        self.panel_rect = pygame.Rect(PX, PY, PW, PH)

        bx  = PX + 10
        bw  = PW - 20
        bh  = 40

        y   = PY + 125
        gap = 8

        self.gm_dd = Dropdown(
            (bx, PY + 82, bw, 38), BOT_OPTIONS, self.fn_tiny)

        def btn(label, fg=CYAN, bg=PANEL, bd=COPPER):
            nonlocal y
            b = Button((bx, y, bw, bh), label, self.fn_small,
                       fg=fg, bg=bg, bd=bd, hfg=BG, hbg=bd)
            y += bh + gap
            return b

        self.gm_start  = btn("Start Game",  fg=GOLD,     bd=GOLD)
        self.gm_pause  = btn("Pause Game",  fg=CYAN,     bd=CYAN)
        y += 4
        self.gm_lb     = btn("Leaderboard", fg=NEON_GREEN, bd=NEON_GREEN)
        self.gm_logout = btn("Log Out",     fg=RED,      bd=RED)

        # Board area
        BX = PX + PW + 10
        BY = PY
        BW = W - BX - 14
        BH = H - 28
        self.board_rect = pygame.Rect(BX, BY, BW, BH)
        self.action_popup_rect = self.board_rect

    # ─────────────────────────────────────────
    #  GAME LOGIC WRAPPERS
    # ─────────────────────────────────────────
    def _set_bot(self):
        sel = self.gm_dd.selected
        if   sel == "XGBoost (Ensemble)":       self.bot = XGBBot()
        elif sel == "Random Forest (Ensemble)":  self.bot = RandomForestBot()
        elif sel == "BFS (Search)":              self.bot = BFSBot()
        elif sel == "DFS (Search)":              self.bot = DFSBot()
        elif sel == "A* (Search)":               self.bot = AStarBot()

    def _reset_game_state(self):
        """Reset all game state to defaults (used on logout and new game)."""
        self.engine.reset_game()
        self.bot             = None
        self.player_turn     = True
        self.consecutive_passes = 0
        self.game_active     = False
        self.is_paused       = False
        self.game_over       = False
        self.game_over_drawn = False
        self.accumulated_time = 0.0
        self.last_ms          = 0
        self.timer_running    = False
        self.bot_thinking     = False
        self.pending_modal    = None
        self.hand_coords      = []
        self.drag_item_idx    = None
        self.drag_surf        = None
        self._dragged_tile    = None
        self._dbl_tile        = None
        self._dbl_t           = 0
        self.action_popup.hide()
        self.modal.visible    = False
        self.board_notif_msg  = ""
        # Reset button labels to their defaults and re-apply enabled state
        self.gm_start.label = "Start Game"
        self.gm_pause.label = "Pause Game"
        self._update_btns()

    def start_game(self):
        self._set_bot()
        self.engine.reset_game()
        self.consecutive_passes = 0
        self.is_paused   = False
        self.game_active = True
        self.game_over   = False
        self.game_over_drawn = False
        self.accumulated_time = 0.0
        self.last_ms     = pygame.time.get_ticks()
        self.timer_running = True
        self.gm_pause.label = "Pause Game"
        self.gm_start.label = "Restart Game"
        self.action_popup.hide()
        self.modal.visible = False
        self.bot_thinking  = False
        self.board_notif_msg = ""

        self.player_turn = random.choice([True, False])
        if self.player_turn:
            self.set_status(f"Game started vs {self.bot.name}! You go first.", GOLD)
            self.set_board_notif(f"Game started! You go first.", GOLD)
        else:
            self.set_status(f"Game started vs {self.bot.name}! Bot goes first.", CYAN)
            self.set_board_notif(f"Game started! Bot goes first.", CYAN)
            threading.Timer(0.5, self._bot_thread).start()
        self._update_btns()

    def toggle_pause(self):
        if not self.game_active: return
        self.is_paused = not self.is_paused
        self.gm_pause.label = "Resume Game" if self.is_paused else "Pause Game"
        msg = "Game Paused." if self.is_paused else "Game Resumed."
        col = COPPER if self.is_paused else GOLD
        self.set_status(msg, col)
        self.set_board_notif(msg, col)
        self.action_popup.hide()
        if not self.is_paused and not self.player_turn:
            threading.Timer(0.3, self._bot_thread).start()
        self._update_btns()

    def player_draw(self):
        self.action_popup.hide()
        if self.engine.draw_tile(self.engine.player_hand):
            self.set_status("You drew a tile.", TEXT)
            self.set_board_notif("You drew a tile from the boneyard.", TEXT)
        self._update_btns()

    def player_pass(self):
        self.action_popup.hide()
        self.consecutive_passes += 1
        self.set_status("You passed your turn.", TEXT)
        self.set_board_notif("You passed your turn.", COPPER)
        if self.consecutive_passes >= 2:
            self._handle_blocked()
        else:
            self.player_turn = False
            self._update_btns()
            threading.Timer(0.8, self._bot_thread).start()

    # ── bot ────────────────────────────────────
    def _bot_thread(self):
        if not self.game_active or self.is_paused or self.bot_thinking:
            return
        self.bot_thinking = True
        self.set_status(f"{self.bot.name} is calculating odds...", CYAN)
        self.set_board_notif(f"{self.bot.name} is thinking...", CYAN)
        time.sleep(0.9)
        move = self.bot.choose_move(self.engine)
        self._exec_bot(move)
        self.bot_thinking = False

    def _exec_bot(self, move):
        if not self.game_active or self.is_paused: return
        if move:
            self.engine.play_tile(self.engine.bot_hand, move)
            self.consecutive_passes = 0
            msg = f"{self.bot.name} played [{move[0][0]}|{move[0][1]}]."
            self.set_status(msg, CYAN)
            self.set_board_notif(msg, NEON_PINK)
        else:
            if self.engine.boneyard:
                self.engine.draw_tile(self.engine.bot_hand)
                msg = f"{self.bot.name} drew a tile. Still their turn..."
                self.set_status(msg, CYAN)
                self.set_board_notif(msg, CYAN)
                threading.Timer(1.0, self._bot_thread).start()
                return
            else:
                self.consecutive_passes += 1
                msg = f"{self.bot.name} passed. Your turn!"
                self.set_status(msg, GOLD)
                self.set_board_notif(msg, GOLD)

        if self.consecutive_passes >= 2:
            self._handle_blocked()
        else:
            self._check_win()
            if self.game_active:
                self.player_turn = True
                self._update_btns()

    # ── win / end ──────────────────────────────
    def _check_win(self):
        if not self.engine.player_hand:
            self.game_active = False
            self.game_over   = True
            threading.Timer(0.3, lambda: self._end(won=True)).start()
        elif not self.engine.bot_hand:
            self.game_active = False
            self.game_over   = True
            threading.Timer(0.3, lambda: self._end(won=False)).start()

    def _handle_blocked(self):
        self.game_active = False
        self.game_over   = True
        p = self.engine.calculate_score(self.engine.player_hand)
        b = self.engine.calculate_score(self.engine.bot_hand)
        if p < b:
            threading.Timer(0.1, lambda: self._end(won=True,  blocked=True)).start()
        elif b < p:
            threading.Timer(0.1, lambda: self._end(won=False, blocked=True)).start()
        else:
            self.pending_modal = (
                "TIE GAME",
                ["Both players are blocked with equal scores.", "Better luck next time!"],
                ["OK"], COPPER)
            self._update_btns()

    def _end(self, won, blocked=False):
        self.timer_running = False
        bot_model   = self.gm_dd.selected
        player_name = self.li_name.value or "Anonymous"

        if bot_model not in self.leaderboard:
            self.leaderboard[bot_model] = {}
        if player_name not in self.leaderboard[bot_model]:
            self.leaderboard[bot_model][player_name] = {
                "wins": 0, "fastest_time": float('inf')}

        stats = self.leaderboard[bot_model][player_name]
        if won:
            stats["wins"] = stats.get("wins", 0) + 1
            best = stats.get("fastest_time", float('inf'))
            if isinstance(best, str): best = float('inf')
            if self.accumulated_time < best:
                stats["fastest_time"] = self.accumulated_time
        self._save_lb()

        mins, secs = divmod(int(self.accumulated_time), 60)
        tstr   = f"{mins:02d}:{secs:02d}"
        reason = "blocked" if blocked else "empty hand"

        if won:
            self.pending_modal = (
                "YOU WIN!",
                [f"You beat {bot_model}", f"Time: {tstr}  |  Reason: {reason}"],
                ["Play Again", "Main Menu"], GOLD)
        else:
            self.pending_modal = (
                "GAME OVER",
                [f"{bot_model} wins this round.", f"Time: {tstr}  |  Reason: {reason}"],
                ["Play Again", "Main Menu"], RED)

        self._update_btns()

    def _update_btns(self):
        # Pause only clickable during an active, non-over game
        self.gm_pause.enabled = self.game_active and not self.game_over
        # Leaderboard when not mid-game or when paused
        self.gm_lb.enabled    = not self.game_active or self.is_paused or self.game_over
        # Dropdown: allow model switch when game not active, paused, or game over
        self.gm_dd.enabled    = not self.game_active or self.is_paused or self.game_over

    def set_status(self, msg, color=GOLD):
        self.status_msg   = msg
        self.status_color = color

    def set_board_notif(self, msg, color=CYAN):
        self.board_notif_msg   = msg
        self.board_notif_color = color

    # ── action popup trigger ───────────────────
    def _check_action_popup(self):
        if not self.game_active or not self.player_turn or self.is_paused:
            return
        if self.action_popup.visible:
            return
        valid = self.engine.get_valid_moves(self.engine.player_hand)
        if not valid:
            if self.engine.boneyard:
                self.action_popup.show('draw', self.board_rect)
            else:
                self.action_popup.show('pass', self.board_rect)

    # ─────────────────────────────────────────
    #  DRAWING
    # ─────────────────────────────────────────
    def draw(self):
        self.screen.fill(BG)
        if self.page == "login":
            self._draw_login()
        else:
            self._draw_game()
        # Overlays (always on top)
        if self.lb_overlay.visible:
            self.lb_overlay.draw(self.screen)
        if self.action_popup.visible:
            self.action_popup.draw(self.screen)
        if self.modal.visible:
            self.modal.draw(self.screen)
        pygame.display.flip()

    # ── LOGIN ──────────────────────────────────
    def _draw_login(self):
        W, H = self.W, self.H
        # Dark gradient background with purple tint
        for y in range(H):
            t = y / H
            r = int(10 + t * 8)
            g = int(5 + t * 4)
            b = int(20 + t * 12)
            pygame.draw.line(self.screen, (r, g, b), (0, y), (W, y))

        # Felt oval
        pygame.draw.ellipse(self.screen, FELT_DARK,
                            (W // 2 - 420, H // 2 - 290, 840, 580))
        pygame.draw.ellipse(self.screen, FELT,
                            (W // 2 - 400, H // 2 - 270, 800, 540))
        pygame.draw.ellipse(self.screen, COPPER,
                            (W // 2 - 400, H // 2 - 270, 800, 540), 3)
        # Extra neon rim
        pygame.draw.ellipse(self.screen, NEON_PINK,
                            (W // 2 - 402, H // 2 - 272, 804, 544), 1)

        bw  = 380
        cx  = W // 2
        top = H // 2 - 195

        # Panel box
        box = pygame.Rect(cx - bw // 2 - 16, top - 16, bw + 32, 420)
        rrect(self.screen, PANEL, box, 18, GOLD, 2)
        # Inner neon border
        inner = pygame.Rect(box.x + 4, box.y + 4, box.width - 8, box.height - 8)
        pygame.draw.rect(self.screen, NEON_PINK, inner, 1, border_radius=15)

        # Title — solid, no glow
        txt_c(self.screen, "HIGH ROLLERS DOMINOES",
              self.fn_large, GOLD, cx, top + 26)
        txt_c(self.screen, "[  ]  [  ]  [  ]  [  ]",
              self.fn_med, NEON_PINK, cx, top + 50)
        pygame.draw.line(self.screen, COPPER,
                         (cx - 160, top + 68), (cx + 160, top + 68), 1)

        # Labels
        txt_c(self.screen, "Enter Nickname:", self.fn_small, COPPER, cx, top + 64)
        self.li_name.draw(self.screen)

        txt_c(self.screen, "Select Opponent:", self.fn_small, COPPER, cx, top + 170)
        # Draw dropdown header BEFORE overlay
        self.li_dd.draw(self.screen)

        self.li_enter.draw(self.screen)
        self.li_lb.draw(self.screen)

        # Draw dropdown OVERLAY last so it covers buttons
        self.li_dd.draw_overlay(self.screen)

    # ── GAME ───────────────────────────────────
    def _draw_game(self):
        self._draw_panel()
        self._draw_board()
        # Draw game panel dropdown overlay LAST so it covers sibling buttons
        self.gm_dd.draw_overlay(self.screen)

    def _draw_panel(self):
        r  = self.panel_rect
        rrect(self.screen, PANEL, r, 14, PANEL_BD, 2)
        # Inner neon accent line
        pygame.draw.rect(self.screen, NEON_PINK,
                         (r.x + 3, r.y + 3, r.width - 6, r.height - 6),
                         1, border_radius=12)

        cx = r.centerx
        PX = r.x; PY = r.y; PW = r.width

        # Title — solid
        txt_c(self.screen, "High Rollers",
              self.fn_med, GOLD, cx, PY + 18)
        pygame.draw.line(self.screen, NEON_PINK,
                         (PX + 10, PY + 34), (PX + PW - 10, PY + 34), 1)

        # Timer
        mins, secs = divmod(int(self.accumulated_time), 60)
        tc = GREEN_OK if self.timer_running else DIS_FG
        txt_c(self.screen, f"{mins:02d}:{secs:02d}",
              self.fn_timer, tc, cx, PY + 54)

        # Dropdown label + dropdown (header only; overlay drawn after board)
        txt_c(self.screen, "Opponent:", self.fn_tiny, COPPER, cx, PY + 72)
        self.gm_dd.draw(self.screen)

        # Buttons
        self.gm_start.draw(self.screen)
        self.gm_pause.draw(self.screen)
        self.gm_lb.draw(self.screen)
        self.gm_logout.draw(self.screen)

        # Status message at bottom
        pygame.draw.line(self.screen, NEON_PINK,
                         (PX + 10, r.bottom - 80), (PX + PW - 10, r.bottom - 80), 1)
        words = self.status_msg.split()
        lines, cur = [], []
        for w in words:
            test = " ".join(cur + [w])
            if self.fn_tiny.size(test)[0] < PW - 16:
                cur.append(w)
            else:
                lines.append(" ".join(cur)); cur = [w]
        if cur: lines.append(" ".join(cur))
        sy = r.bottom - 74
        for ln in lines[:5]:
            s = self.fn_tiny.render(ln, True, self.status_color)
            self.screen.blit(s, s.get_rect(centerx=cx, y=sy))
            sy += 14

    def _draw_board(self):
        r  = self.board_rect
        cx = r.centerx
        cy = r.centery

        # Felt background
        rrect(self.screen, FELT, r, 16, COPPER, 2)
        # Neon rim
        pygame.draw.rect(self.screen, NEON_PINK, r, 1, border_radius=16)
        ow, oh = r.width - 36, r.height - 36
        pygame.draw.ellipse(self.screen, FELT_DARK,
                            (r.x + 18, r.y + 18, ow, oh))
        pygame.draw.ellipse(self.screen, COPPER,
                            (r.x + 18, r.y + 18, ow, oh), 2)

        if not self.game_active and not self.engine.board and not self.game_over:
            txt_c(self.screen, "Press Start Game to deal!",
                  self.fn_large, GOLD, cx, cy)
            return

        # ── Board notification (above bot info) ──
        if self.board_notif_msg:
            txt_c(self.screen, self.board_notif_msg,
                  self.fn_board_notif, self.board_notif_color, cx, r.y + 18)

        # Bot info (below notification)
        bot_name = self.bot.name if self.bot else "Bot"
        txt_c(self.screen,
              f"{bot_name}  |  {len(self.engine.bot_hand)} tiles",
              self.fn_board_info, GOLD, cx, r.y + 42)
        txt_c(self.screen,
              f"Boneyard: {len(self.engine.boneyard)} tiles",
              self.fn_board_sub, TEXT, cx, r.y + 66)

        # Board tiles
        self._draw_board_tiles(r)

        # Pause overlay
        if self.is_paused:
            ov = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 160))
            self.screen.blit(ov, r.topleft)
            txt_c(self.screen, "PAUSED", self.fn_large, RED, cx, cy)
            return

        # Player hand
        self._draw_hand(r)

        txt_c(self.screen, "YOUR HAND", self.fn_tiny, COPPER, cx, r.bottom - 20)

    def _draw_board_tiles(self, r):
        layout = []
        if not self.engine.board:
            return

        jx, jy     = 0, 0
        state      = 'GOING_EAST'
        dv         = (1, 0)
        tiles_dir  = 0
        MAX_H, MAX_V = 9, 2

        for i, tile in enumerate(self.engine.board):
            v1, v2    = tile
            is_double = (v1 == v2)
            if dv[0] != 0:
                orient = 'N' if is_double else ('E' if dv[0] > 0 else 'W')
            else:
                orient = 'E' if is_double else ('N' if dv[1] > 0 else 'S')
            L = 40 if is_double else 80

            if tiles_dir == 0 and i > 0:
                pd = layout[-1]['dir']
                if pd[0] != 0 and dv[1] != 0: jx -= pd[0] * 20
                elif pd[1] != 0 and dv[0] != 0: jy -= pd[1] * 20

            tcx = jx + dv[0] * L / 2
            tcy = jy + dv[1] * L / 2
            layout.append({'tile': tile, 'cx': tcx, 'cy': tcy,
                           'orient': orient, 'dir': dv})
            jx += dv[0] * L; jy += dv[1] * L
            tiles_dir += 1
            lim = MAX_H if dv[0] != 0 else MAX_V
            if tiles_dir >= lim:
                tiles_dir = 0
                if   state == 'GOING_EAST':    state, dv = 'GOING_SOUTH_1', (0, 1)
                elif state == 'GOING_SOUTH_1': state, dv = 'GOING_WEST',   (-1, 0)
                elif state == 'GOING_WEST':    state, dv = 'GOING_SOUTH_2', (0, 1)
                elif state == 'GOING_SOUTH_2': state, dv = 'GOING_EAST',   (1, 0)

        if not layout: return

        min_x = min(l['cx'] for l in layout)
        max_x = max(l['cx'] for l in layout)
        min_y = min(l['cy'] for l in layout)
        max_y = max(l['cy'] for l in layout)

        safe_w = r.width  - 60
        safe_h = r.height - 290
        lw = max_x - min_x + 80
        lh = max_y - min_y + 80
        scale = min(
            safe_w / lw if lw > safe_w else 1.0,
            safe_h / lh if lh > safe_h else 1.0,
            1.0)

        cx_board = r.x + r.width // 2
        cy_board = r.y + int(r.height * 0.42)
        off_x = cx_board - ((min_x + max_x) / 2) * scale
        off_y = cy_board - ((min_y + max_y) / 2) * scale

        if layout:
            self.left_end_cx  = layout[0]['cx']  * scale + off_x
            self.left_end_cy  = layout[0]['cy']  * scale + off_y
            self.right_end_cx = layout[-1]['cx'] * scale + off_x
            self.right_end_cy = layout[-1]['cy'] * scale + off_y

        for item in layout:
            v1, v2 = item['tile']
            s  = self._tile(v1, v2, item['orient'], scale)
            dx = item['cx'] * scale + off_x
            dy = item['cy'] * scale + off_y
            self.screen.blit(s, s.get_rect(center=(int(dx), int(dy))))

    def _draw_hand(self, r):
        self.hand_coords = []
        hand = self.engine.player_hand
        if not hand: return

        valid     = self.engine.get_valid_moves(hand) if self.game_active else []
        valid_set = {m[0] for m in valid}

        tw   = self.TILE_H + 12
        totw = len(hand) * tw - 12
        sx   = r.x + r.width // 2 - totw // 2
        ty   = r.bottom - 140

        for i, tile in enumerate(hand):
            tx = sx + i * tw
            if (tile in valid_set and self.player_turn
                    and self.game_active and not self.is_paused):
                pulse = int(128 + 100 * math.sin(pygame.time.get_ticks() / 280.0))
                gsurf = pygame.Surface((self.TILE_H + 12, self.TILE_W + 12),
                                       pygame.SRCALPHA)
                pygame.draw.rect(gsurf, (0, 230, 255, pulse),
                                 (0, 0, self.TILE_H + 12, self.TILE_W + 12),
                                 border_radius=7)
                self.screen.blit(gsurf, (tx - 6, ty - 6))

            if (self.drag_item_idx is not None and self.drag_item_idx == i):
                rect = pygame.Rect(tx, ty, self.TILE_H, self.TILE_W)
                rrect(self.screen, (20, 10, 40), rect, 5, COPPER, 1)
                self.hand_coords.append(
                    (tx, tx + self.TILE_H, ty, ty + self.TILE_W, tile, i))
                continue

            s = self._tile(tile[0], tile[1], 'N')
            self.screen.blit(s, (tx, ty))
            self.hand_coords.append(
                (tx, tx + self.TILE_H, ty, ty + self.TILE_W, tile, i))

        if self.drag_item_idx is not None and self.drag_surf is not None:
            mx, my = self.drag_x, self.drag_y
            self.screen.blit(self.drag_surf,
                (mx - self.drag_surf.get_width() // 2,
                 my - self.drag_surf.get_height() // 2))

    # ─────────────────────────────────────────
    #  EVENTS
    # ─────────────────────────────────────────
    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT: return False
            if ev.type == pygame.VIDEORESIZE:
                self.W = getattr(ev, 'w', ev.x if hasattr(ev, 'x') else self.W)
                self.H = getattr(ev, 'h', ev.y if hasattr(ev, 'y') else self.H)
                self.screen = pygame.display.set_mode(
                    (self.W, self.H), pygame.RESIZABLE)
                self._build_login()
                self._build_game()

            if self.modal.visible:
                self.modal.handle(ev)
                if self.modal.result:
                    self._on_modal(self.modal.result)
                continue

            if self.lb_overlay.visible:
                self.lb_overlay.handle(ev)
                continue

            if self.action_popup.visible:
                self.action_popup.handle(ev)
                if self.action_popup.triggered:
                    if self.action_popup._action == 'draw':
                        self.player_draw()
                    else:
                        self.player_pass()
                continue

            if self.page == "login":
                self._ev_login(ev)
            else:
                self._ev_game(ev)
        return True

    def _on_modal(self, result):
        if result == "Play Again":
            self.start_game()
        elif result in ("Main Menu", "OK"):
            self._reset_game_state()
            self.page       = "login"
            self.set_status("Place your bets and press Start Game to deal!", GOLD)

    def _ev_login(self, ev):
        self.li_name.handle(ev)
        dd_result = self.li_dd.handle(ev)
        # If dropdown consumed this click (open/close or list area), don't
        # forward the event to the buttons behind it.
        if dd_result:
            return
        if self.li_enter.on(ev): self._enter_game()
        if self.li_lb.on(ev):
            self.lb_overlay.show()

    def _enter_game(self):
        self.gm_dd.idx = self.li_dd.idx
        self._reset_game_state()
        self.page = "game"

    def _ev_game(self, ev):
        dd_result = self.gm_dd.handle(ev)
        # If the dropdown consumed this click (toggled open/close or a list row
        # was hit), do NOT forward the event to any buttons beneath it.
        if dd_result:
            return

        if self.gm_start.on(ev):  self.start_game()
        if self.gm_pause.on(ev):  self.toggle_pause()
        if self.gm_lb.on(ev):     self.lb_overlay.show()
        if self.gm_logout.on(ev):
            self._reset_game_state()
            self.page = "login"
            self.set_status("Place your bets and press Start Game to deal!", GOLD)

        if not self.game_active or not self.player_turn or self.is_paused:
            return

        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._on_press(ev.pos)
        elif ev.type == pygame.MOUSEMOTION:
            if self.drag_item_idx is not None:
                self.drag_x, self.drag_y = ev.pos
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            if self.drag_item_idx is not None:
                self._on_release(ev.pos)

    def _on_press(self, pos):
        mx, my = pos
        for x1, x2, y1, y2, tile, idx in self.hand_coords:
            if x1 <= mx <= x2 and y1 <= my <= y2:
                now = pygame.time.get_ticks()
                if self._dbl_tile == tile and now - self._dbl_t < 400:
                    self._dbl_tile = None
                    self._play_auto(tile, pos)
                    return
                self._dbl_tile = tile
                self._dbl_t    = now
                self.drag_item_idx = idx
                self.drag_surf = self._tile(tile[0], tile[1], 'N')
                self.drag_x, self.drag_y = mx, my
                self.press_x, self.press_y = mx, my
                self._dragged_tile = tile
                return

    def _play_auto(self, tile, pos):
        valid = self.engine.get_valid_moves(self.engine.player_hand)
        moves = [m for m in valid if m[0] == tile]
        if not moves:
            self.set_status("That tile doesn't match either end!", RED)
            self.set_board_notif("That tile doesn't match either end!", RED)
            return
        if len(moves) > 1:
            dl = (pos[0] - self.left_end_cx) ** 2 + (pos[1] - self.left_end_cy) ** 2
            dr = (pos[0] - self.right_end_cx) ** 2 + (pos[1] - self.right_end_cy) ** 2
            side = 'left' if dl <= dr else 'right'
            move = next((m for m in moves if m[1] == side), moves[0])
        else:
            move = moves[0]
        self._apply(move)

    def _on_release(self, pos):
        tile = getattr(self, '_dragged_tile', None)
        idx  = self.drag_item_idx
        self.drag_item_idx = None
        self.drag_surf     = None
        if tile is None: return

        mx, my = pos
        for x1, x2, y1, y2, _t, _i in self.hand_coords:
            if x1 <= mx <= x2 and y1 <= my <= y2:
                self.set_status("Move cancelled — tile returned to hand.", TEXT)
                self.set_board_notif("Move cancelled.", TEXT)
                return

        valid = self.engine.get_valid_moves(self.engine.player_hand)
        moves = [m for m in valid if m[0] == tile]
        if not moves:
            self.set_status("Invalid move! Doesn't match either end.", RED)
            self.set_board_notif("Invalid move! Doesn't match either end.", RED)
            return

        if len(moves) > 1:
            dl = (mx - self.left_end_cx) ** 2 + (my - self.left_end_cy) ** 2
            dr = (mx - self.right_end_cx) ** 2 + (my - self.right_end_cy) ** 2
            move = next(
                (m for m in moves if m[1] == ('left' if dl < dr else 'right')),
                moves[0])
        else:
            move = moves[0]
        self._apply(move)

    def _apply(self, move):
        self.engine.play_tile(self.engine.player_hand, move)
        msg = f"You played [{move[0][0]}|{move[0][1]}]."
        self.set_status(msg, NEON_GREEN)
        self.set_board_notif(msg, NEON_GREEN)
        self.consecutive_passes = 0
        self._check_win()
        if self.game_active:
            self.player_turn = False
            self._update_btns()
            threading.Timer(0.9, self._bot_thread).start()

    # ─────────────────────────────────────────
    #  MAIN LOOP
    # ─────────────────────────────────────────
    def update(self):
        now = pygame.time.get_ticks()
        dt  = now - self.last_ms
        if self.timer_running and self.game_active and not self.is_paused:
            self.accumulated_time += dt / 1000.0
        self.last_ms = now

        self.li_name.update(dt)

        if self.pending_modal and not self.modal.visible:
            title, lines, btns, color = self.pending_modal
            self.pending_modal = None
            self.modal.show(title, lines, btns, color)

        if self.page == "game":
            self._check_action_popup()

        if self.page == "login":
            pos = pygame.mouse.get_pos()
            for b in [self.li_enter, self.li_lb]:
                b.hovered = b.rect.collidepoint(pos)

    def run(self):
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(60)
        pygame.quit()

if __name__ == "__main__":
    DominoGame().run()