"""
Огонь и Вода — 2D платформер с локальным сетевым мультиплеером
Запуск: python main.py
"""

import pygame
import sys
import random
import threading
from enum import Enum

from network import NetworkManager, NetworkRole
from levels import LEVELS, get_level
from player import Player, PlayerType

# ───────────────────────────────────────────
#  Константы
# ───────────────────────────────────────────
SCREEN_W, SCREEN_H = 1024, 600
FPS = 60
TILE = 40

# Цвета
C_BG        = (15,  15,  25)
C_FIRE      = (255, 100,  30)
C_FIRE2     = (255, 200,  50)
C_WATER     = ( 30, 130, 255)
C_WATER2    = (100, 200, 255)
C_PLATFORM  = ( 60,  60,  80)
C_LAVA      = (200,  40,  10)
C_POOL      = ( 10,  60, 150)
C_DOOR_F    = (200,  80,   0)
C_DOOR_W    = (  0,  80, 200)
C_DOOR_OPEN = ( 60, 180,  60)
C_BTN_F     = (180,  60,   0)
C_BTN_W     = (  0,  60, 180)
C_BTN_ON    = ( 80, 200,  80)
C_WHITE     = (255, 255, 255)
C_GRAY      = (120, 120, 140)
C_DARK      = ( 30,  30,  45)
C_GREEN     = ( 50, 220, 100)
C_RED       = (220,  50,  50)
C_YELLOW    = (255, 220,  50)

class GameState(Enum):
    MENU        = "menu"
    LEVEL_SELECT= "level_select"
    NET_SETUP   = "net_setup"
    WAITING     = "waiting"
    ROLE_SHOW   = "role_show"
    PLAYING     = "playing"
    WIN         = "win"
    DEAD        = "dead"

# ───────────────────────────────────────────
#  Вспомогательные UI-компоненты
# ───────────────────────────────────────────
class Button:
    def __init__(self, rect, text, color=C_PLATFORM, text_color=C_WHITE):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.text_color = text_color
        self.hover = False

    def draw(self, surf, font):
        col = tuple(min(255, c + 30) for c in self.color) if self.hover else self.color
        pygame.draw.rect(surf, col, self.rect, border_radius=10)
        pygame.draw.rect(surf, C_WHITE, self.rect, 2, border_radius=10)
        lbl = font.render(self.text, True, self.text_color)
        surf.blit(lbl, lbl.get_rect(center=self.rect.center))

    def update(self, mx, my):
        self.hover = self.rect.collidepoint(mx, my)

    def clicked(self, event):
        return (event.type == pygame.MOUSEBUTTONDOWN and
                event.button == 1 and self.rect.collidepoint(event.pos))


class InputBox:
    def __init__(self, rect, placeholder=""):
        self.rect = pygame.Rect(rect)
        self.text = ""
        self.placeholder = placeholder
        self.active = False

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.unicode.isprintable():
                self.text += event.unicode

    def draw(self, surf, font):
        border = C_WATER if self.active else C_GRAY
        pygame.draw.rect(surf, C_DARK, self.rect, border_radius=8)
        pygame.draw.rect(surf, border, self.rect, 2, border_radius=8)
        txt = self.text if self.text else self.placeholder
        col = C_WHITE if self.text else C_GRAY
        lbl = font.render(txt, True, col)
        surf.blit(lbl, (self.rect.x + 10, self.rect.centery - lbl.get_height()//2))


# ───────────────────────────────────────────
#  Класс Game
# ───────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Огонь и Вода")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.clock  = pygame.time.Clock()

        self._init_fonts()
        self._init_menu()

        self.state       = GameState.MENU
        self.level_idx   = 0
        self.net         = None
        self.player_type = None   # PlayerType.FIRE / WATER (local)
        self.players     = {}     # {PlayerType: Player}
        self.level_data  = None
        self.role_timer  = 0
        self.win_timer   = 0
        self.dead_timer  = 0
        self.anim_tick   = 0
        self.particles   = []
        self.buttons_state = {}   # id -> pressed
        self.doors_state   = {}   # id -> open

    def _init_fonts(self):
        self.font_big   = pygame.font.SysFont("segoeui", 52, bold=True)
        self.font_mid   = pygame.font.SysFont("segoeui", 30)
        self.font_small = pygame.font.SysFont("segoeui", 22)
        self.font_tiny  = pygame.font.SysFont("segoeui", 16)

    def _init_menu(self):
        cx = SCREEN_W // 2
        # [ИЗМЕНЕНИЕ] Удалён одиночный режим — только LAN-кооператив и выбор уровня
        self.menu_btns = [
            Button((cx-130, 240, 260, 54), "Мультиплеер (LAN)", C_PLATFORM),
            Button((cx-130, 310, 260, 54), "Выбор уровня",      C_PLATFORM),
            Button((cx-130, 380, 260, 54), "Выход",             (80, 30, 30)),
        ]
        self.level_btns = [
            Button((cx-200 + (i%5)*90, 200 + (i//5)*90, 75, 55),
                   f"Ур.{i+1}", C_PLATFORM)
            for i in range(10)
        ]
        self.level_back = Button((cx-60, 500, 120, 44), "Назад", (60, 30, 60))

        # Сеть
        self.net_input  = InputBox((cx-150, 280, 300, 44), "192.168.1.x")
        self.net_host   = Button((cx-160, 350, 150, 44), "Создать сервер", C_BTN_F)
        self.net_join   = Button((cx+10,  350, 150, 44), "Подключиться",  C_BTN_W)
        self.net_back   = Button((cx-60,  430, 120, 44), "Назад", (60, 30, 60))
        self.net_msg    = ""

    # ──────────────────── главный цикл ────────────────────
    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.anim_tick += 1
            events = pygame.event.get()

            for e in events:
                if e.type == pygame.QUIT:
                    self._quit()

            if self.state == GameState.MENU:
                self._update_menu(events)
                self._draw_menu()
            elif self.state == GameState.LEVEL_SELECT:
                self._update_level_select(events)
                self._draw_level_select()
            elif self.state == GameState.NET_SETUP:
                self._update_net_setup(events)
                self._draw_net_setup()
            elif self.state == GameState.WAITING:
                self._update_waiting()
                self._draw_waiting()
            elif self.state == GameState.ROLE_SHOW:
                self._update_role_show(dt)
                self._draw_role_show()
            elif self.state == GameState.PLAYING:
                self._update_playing(dt, events)
                self._draw_playing()
            elif self.state == GameState.WIN:
                self._update_win(dt, events)
                self._draw_win()
            elif self.state == GameState.DEAD:
                self._update_dead(dt, events)
                self._draw_dead()

            pygame.display.flip()

    # ──────────────────── MENU ────────────────────
    def _update_menu(self, events):
        mx, my = pygame.mouse.get_pos()
        for b in self.menu_btns:
            b.update(mx, my)
        for e in events:
            # [ИЗМЕНЕНИЕ] Одиночный режим удалён — индексы сдвинуты
            if self.menu_btns[0].clicked(e):   # Мультиплеер
                self.state = GameState.NET_SETUP
            if self.menu_btns[1].clicked(e):   # Выбор уровня
                self.state = GameState.LEVEL_SELECT
            if self.menu_btns[2].clicked(e):   # Выход
                self._quit()

    def _draw_menu(self):
        self._draw_bg()
        title = self.font_big.render("Ogon  i  Voda", True, C_WHITE)
        self.screen.blit(title, title.get_rect(center=(SCREEN_W//2, 120)))
        # Подзаголовок
        sub = self.font_small.render("Kooperativny platformer", True, C_GRAY)
        self.screen.blit(sub, sub.get_rect(center=(SCREEN_W//2, 175)))

        # [ИЗМЕНЕНИЕ] Эмодзи заменены на цветные прямоугольники-иконки
        import math
        phase = self.anim_tick * 0.05
        fy = 120 + int(math.sin(phase) * 8)
        wy = 120 + int(math.sin(phase + 3.14) * 8)
        # Иконка огня (оранжевый треугольник)
        fire_x, fire_y = SCREEN_W//2 - 240, fy - 20
        pygame.draw.polygon(self.screen, C_FIRE,
                            [(fire_x+20, fire_y), (fire_x, fire_y+40), (fire_x+40, fire_y+40)])
        pygame.draw.polygon(self.screen, C_FIRE2,
                            [(fire_x+20, fire_y+8), (fire_x+8, fire_y+40), (fire_x+32, fire_y+40)])
        # Иконка воды (синий круг + волна)
        water_x, water_y = SCREEN_W//2 + 190, wy
        pygame.draw.circle(self.screen, C_WATER, (water_x+20, water_y+20), 20)
        pygame.draw.circle(self.screen, C_WATER2, (water_x+20, water_y+20), 12)

        for b in self.menu_btns:
            b.draw(self.screen, self.font_mid)

    # ──────────────────── LEVEL SELECT ────────────────────
    def _update_level_select(self, events):
        mx, my = pygame.mouse.get_pos()
        for b in self.level_btns:
            b.update(mx, my)
        self.level_back.update(mx, my)
        for e in events:
            for i, b in enumerate(self.level_btns):
                if b.clicked(e):
                    self.level_idx = i
                    self.net = None
                    self.player_type = PlayerType.FIRE
                    self._start_level(i)
            if self.level_back.clicked(e):
                self.state = GameState.MENU

    def _draw_level_select(self):
        self._draw_bg()
        title = self.font_mid.render("Выбор уровня", True, C_WHITE)
        self.screen.blit(title, title.get_rect(center=(SCREEN_W//2, 140)))
        for i, b in enumerate(self.level_btns):
            col = C_GREEN if i < self.level_idx else C_PLATFORM
            b.color = col
            b.draw(self.screen, self.font_small)
        self.level_back.draw(self.screen, self.font_small)

    # ──────────────────── NET SETUP ────────────────────
    def _update_net_setup(self, events):
        mx, my = pygame.mouse.get_pos()
        self.net_host.update(mx, my)
        self.net_join.update(mx, my)
        self.net_back.update(mx, my)
        for e in events:
            self.net_input.handle(e)
            if self.net_host.clicked(e):
                self._start_server()
            if self.net_join.clicked(e):
                self._join_server()
            if self.net_back.clicked(e):
                self.state = GameState.MENU

    def _draw_net_setup(self):
        self._draw_bg()
        title = self.font_mid.render("Сетевая игра (LAN)", True, C_WHITE)
        self.screen.blit(title, title.get_rect(center=(SCREEN_W//2, 160)))
        ip_lbl = self.font_small.render("IP-адрес для подключения:", True, C_GRAY)
        self.screen.blit(ip_lbl, (SCREEN_W//2 - 150, 250))
        self.net_input.draw(self.screen, self.font_small)
        self.net_host.draw(self.screen, self.font_small)
        self.net_join.draw(self.screen, self.font_small)
        self.net_back.draw(self.screen, self.font_small)
        if self.net_msg:
            col = C_RED if "Ошибка" in self.net_msg else C_YELLOW
            msg = self.font_small.render(self.net_msg, True, col)
            self.screen.blit(msg, msg.get_rect(center=(SCREEN_W//2, 495)))

    def _start_server(self):
        self.net = NetworkManager(NetworkRole.SERVER)
        self.net_msg = "Запуск сервера..."
        def _serve():
            try:
                self.net.start_server(self.level_idx)
                self.player_type = PlayerType.FIRE
                self.state = GameState.WAITING
            except Exception as ex:
                self.net_msg = f"Ошибка: {ex}"
        threading.Thread(target=_serve, daemon=True).start()

    def _join_server(self):
        ip = self.net_input.text.strip() or "127.0.0.1"
        self.net = NetworkManager(NetworkRole.CLIENT)
        self.net_msg = f"Подключение к {ip}..."
        def _conn():
            try:
                lvl_idx = self.net.connect_to_server(ip)
                self.level_idx   = lvl_idx
                self.player_type = PlayerType.WATER
                self.state = GameState.WAITING
            except Exception as ex:
                self.net_msg = f"Ошибка: {ex}"
        threading.Thread(target=_conn, daemon=True).start()

    # ──────────────────── WAITING ────────────────────
    def _update_waiting(self):
        if self.net and self.net.is_connected():
            self._start_level(self.level_idx)

    def _draw_waiting(self):
        self._draw_bg()
        dots = "." * ((self.anim_tick // 20) % 4)
        msg = self.font_mid.render(f"Ожидание второго игрока{dots}", True, C_WHITE)
        self.screen.blit(msg, msg.get_rect(center=(SCREEN_W//2, SCREEN_H//2)))
        hint = self.font_small.render("Нажмите ESC для отмены", True, C_GRAY)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_W//2, SCREEN_H//2 + 50)))
        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE]:
            self.net = None
            self.state = GameState.MENU

    # ──────────────────── ROLE SHOW ────────────────────
    def _update_role_show(self, dt):
        self.role_timer -= dt
        if self.role_timer <= 0:
            self.state = GameState.PLAYING

    def _draw_role_show(self):
        self._draw_bg()
        # [ИЗМЕНЕНИЕ] Эмодзи заменены на текст
        if self.player_type == PlayerType.FIRE:
            color = C_FIRE
            name  = "OGON  [FIRE]"
            ctrl  = "Upravlenie: WASD"
            rule  = "Izbegay vody i luzh!"
        else:
            color = C_WATER
            name  = "VODA  [WATER]"
            ctrl  = "Upravlenie: strelki"
            rule  = "Izbegay ognya i lavy!"

        lbl = self.font_big.render(f"Ty igraesh za {name}", True, color)
        self.screen.blit(lbl, lbl.get_rect(center=(SCREEN_W//2, SCREEN_H//2 - 40)))
        c = self.font_mid.render(ctrl, True, C_WHITE)
        self.screen.blit(c, c.get_rect(center=(SCREEN_W//2, SCREEN_H//2 + 30)))
        r = self.font_small.render(rule, True, C_GRAY)
        self.screen.blit(r, r.get_rect(center=(SCREEN_W//2, SCREEN_H//2 + 75)))

        bar_w = int((self.role_timer / 2.5) * 300)
        pygame.draw.rect(self.screen, color,
                         (SCREEN_W//2 - 150, SCREEN_H//2 + 120, bar_w, 6), border_radius=3)

    # ──────────────────── START LEVEL ────────────────────
    def _start_level(self, idx):
        self.level_idx    = idx
        self.level_data   = get_level(idx)
        self.buttons_state = {b["id"]: False for b in self.level_data.get("buttons", [])}
        self.doors_state   = {d["id"]: False for d in self.level_data.get("doors",   [])}
        self.particles     = []

        # Спавн игроков
        sp_f = self.level_data["spawn_fire"]
        sp_w = self.level_data["spawn_water"]
        self.players = {
            PlayerType.FIRE:  Player(sp_f[0], sp_f[1], PlayerType.FIRE),
            PlayerType.WATER: Player(sp_w[0], sp_w[1], PlayerType.WATER),
        }
        self.role_timer = 2.5
        self.state = GameState.ROLE_SHOW

    # ──────────────────── PLAYING ────────────────────
    def _update_playing(self, dt, events):
        keys = pygame.key.get_pressed()

        for e in events:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.state = GameState.MENU
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                self._start_level(self.level_idx)
                return

        # [ИЗМЕНЕНИЕ] Только мультиплеер — нет одиночного режима
        if not self.net or not self.net.is_connected():
            # Сеть потеряна — показываем меню
            self.state = GameState.MENU
            return

        local = self.players[self.player_type]
        remote_type = PlayerType.WATER if self.player_type == PlayerType.FIRE else PlayerType.FIRE
        remote = self.players[remote_type]

        # Локальный ввод
        if self.player_type == PlayerType.FIRE:
            local.handle_input_wasd(keys)
        else:
            local.handle_input_arrows(keys)

        # Синхронизация по сети
        self.net.send_state(local.x, local.y, local.vx, local.vy, local.on_ground)
        data = self.net.recv_state()
        if data:
            remote.x, remote.y, remote.vx, remote.vy, remote.on_ground = data

        platforms = self.level_data["platforms"]
        for p in self.players.values():
            p.update(dt, platforms)

        self._update_buttons()
        self._update_particles(dt)

        if self._check_death():
            self.dead_timer = 2.0
            self.state = GameState.DEAD
            return

        if self._check_win():
            self.win_timer = 3.0
            self.state = GameState.WIN

    def _update_buttons(self):
        btns  = self.level_data.get("buttons", [])
        doors = self.level_data.get("doors",   [])

        for b in btns:
            br = pygame.Rect(b["x"]*TILE, b["y"]*TILE, TILE, TILE//2)
            pressed = False
            for p in self.players.values():
                pr = pygame.Rect(p.x, p.y, p.w, p.h)
                if pr.colliderect(br):
                    pressed = True
            self.buttons_state[b["id"]] = pressed

        for d in doors:
            required = d.get("requires", [])
            self.doors_state[d["id"]] = all(self.buttons_state.get(r, False) for r in required)

    def _check_death(self):
        traps   = self.level_data.get("traps", [])
        fire_p  = self.players[PlayerType.FIRE]
        water_p = self.players[PlayerType.WATER]
        fire_r  = pygame.Rect(fire_p.x,  fire_p.y,  fire_p.w,  fire_p.h)
        water_r = pygame.Rect(water_p.x, water_p.y, water_p.w, water_p.h)

        for t in traps:
            tr = pygame.Rect(t["x"]*TILE, t["y"]*TILE, t["w"]*TILE, t["h"]*TILE)
            if t["type"] == "lava":
                # [ИЗМЕНЕНИЕ] Огонь НЕ погибает в лаве — только Вода
                if water_r.colliderect(tr):
                    return True
            elif t["type"] == "pool":
                # Огонь погибает в луже; Вода — нет
                if fire_r.colliderect(tr):
                    return True

        # [ИЗМЕНЕНИЕ] Коллизия персонажей: при соприкосновении — смерть обоих
        # Используем слегка уменьшенный hitbox чтобы исключить ложные срабатывания на соседних платформах
        fire_inner  = pygame.Rect(fire_p.x + 4,  fire_p.y + 4,  fire_p.w - 8,  fire_p.h - 4)
        water_inner = pygame.Rect(water_p.x + 4, water_p.y + 4, water_p.w - 8, water_p.h - 4)
        if fire_inner.colliderect(water_inner):
            return True

        # Падение за экран
        for p in self.players.values():
            if p.y > SCREEN_H + 100:
                return True
        return False

    def _check_win(self):
        exits = self.level_data.get("exits", [])
        fire_p  = self.players[PlayerType.FIRE]
        water_p = self.players[PlayerType.WATER]
        fire_in = water_in = False
        for ex in exits:
            er = pygame.Rect(ex["x"]*TILE, ex["y"]*TILE, TILE, TILE*2)
            if ex["type"] == "fire"  and pygame.Rect(fire_p.x,  fire_p.y,  fire_p.w,  fire_p.h).colliderect(er):
                fire_in = True
            if ex["type"] == "water" and pygame.Rect(water_p.x, water_p.y, water_p.w, water_p.h).colliderect(er):
                water_in = True
        return fire_in and water_in

    def _update_particles(self, dt):
        # Добавляем частицы вокруг игроков
        for ptype, player in self.players.items():
            if random.random() < 0.3:
                color = (C_FIRE if ptype == PlayerType.FIRE else C_WATER)
                self.particles.append({
                    "x": player.x + player.w//2 + random.randint(-8, 8),
                    "y": player.y + random.randint(0, player.h),
                    "vx": random.uniform(-30, 30),
                    "vy": random.uniform(-60, -20),
                    "life": random.uniform(0.3, 0.7),
                    "color": color,
                    "size": random.randint(2, 5),
                })
        for p in self.particles:
            p["x"]    += p["vx"] * dt
            p["y"]    += p["vy"] * dt
            p["life"] -= dt
        self.particles = [p for p in self.particles if p["life"] > 0]

    def _draw_playing(self):
        self._draw_bg()
        self._draw_level()
        for p in self.particles:
            alpha = int(255 * p["life"] / 0.7)
            s = max(1, p["size"])
            pygame.draw.circle(self.screen, p["color"], (int(p["x"]), int(p["y"])), s)
        for player in self.players.values():
            player.draw(self.screen, self.anim_tick)
        self._draw_hud()

    def _draw_level(self):
        ld = self.level_data
        # Платформы
        for plat in ld["platforms"]:
            r = pygame.Rect(plat[0]*TILE, plat[1]*TILE, plat[2]*TILE, plat[3]*TILE)
            pygame.draw.rect(self.screen, C_PLATFORM, r, border_radius=4)
            pygame.draw.rect(self.screen, (90, 90, 110), r, 2, border_radius=4)

        # Ловушки
        for t in ld.get("traps", []):
            r = pygame.Rect(t["x"]*TILE, t["y"]*TILE, t["w"]*TILE, t["h"]*TILE)
            col = C_LAVA if t["type"] == "lava" else C_POOL
            pygame.draw.rect(self.screen, col, r, border_radius=3)
            # Анимация волны
            for i in range(0, r.width, 12):
                import math
                wave_y = r.y + int(math.sin((self.anim_tick * 0.1) + i * 0.3) * 3)
                pygame.draw.circle(self.screen,
                    (255, 80, 10) if t["type"] == "lava" else (50, 100, 200),
                    (r.x + i, wave_y), 3)

        # Кнопки
        for b in ld.get("buttons", []):
            pressed = self.buttons_state.get(b["id"], False)
            col = C_BTN_ON if pressed else (C_BTN_F if b["type"] == "fire" else C_BTN_W)
            r = pygame.Rect(b["x"]*TILE, b["y"]*TILE, TILE, TILE//2)
            pygame.draw.rect(self.screen, col, r, border_radius=4)
            # [ИЗМЕНЕНИЕ] Эмодзи заменены на текст
            lbl = self.font_tiny.render("BTN", True, C_WHITE)
            self.screen.blit(lbl, lbl.get_rect(center=r.center))

        # Двери
        for d in ld.get("doors", []):
            opened = self.doors_state.get(d["id"], False)
            if opened:
                continue
            col = C_DOOR_F if d["type"] == "fire" else C_DOOR_W
            r = pygame.Rect(d["x"]*TILE, d["y"]*TILE, TILE, d["h"]*TILE)
            pygame.draw.rect(self.screen, col, r, border_radius=4)
            # [ИЗМЕНЕНИЕ] Эмодзи двери заменена на полосатый узор
            for stripe_y in range(r.y + 4, r.y + r.height - 4, 8):
                pygame.draw.line(self.screen, C_WHITE, (r.x + 4, stripe_y), (r.x + r.width - 4, stripe_y), 1)
            lbl = self.font_tiny.render("DOOR", True, C_WHITE)
            self.screen.blit(lbl, lbl.get_rect(center=r.center))

        # Выходы
        for ex in ld.get("exits", []):
            col = C_FIRE if ex["type"] == "fire" else C_WATER
            r = pygame.Rect(ex["x"]*TILE, ex["y"]*TILE, TILE, TILE*2)
            import math
            glow = abs(math.sin(self.anim_tick * 0.07)) * 30
            gcol = tuple(min(255, int(c + glow)) for c in col)
            pygame.draw.rect(self.screen, gcol, r, border_radius=6)
            pygame.draw.rect(self.screen, C_WHITE, r, 2, border_radius=6)
            # [ИЗМЕНЕНИЕ] Эмодзи заменены на букву F / W
            icon_text = "F" if ex["type"] == "fire" else "W"
            icon_col  = C_FIRE2 if ex["type"] == "fire" else C_WATER2
            lbl = self.font_mid.render(icon_text, True, icon_col)
            self.screen.blit(lbl, lbl.get_rect(center=r.center))

    def _draw_hud(self):
        # [ИЗМЕНЕНИЕ] Эмодзи в HUD заменены на текст
        lv = self.font_small.render(f"Level {self.level_idx+1}", True, C_WHITE)
        self.screen.blit(lv, (10, 10))
        role_name = "FIRE" if self.player_type == PlayerType.FIRE else "WATER"
        role_col  = C_FIRE if self.player_type == PlayerType.FIRE else C_WATER
        rl = self.font_small.render(f"You: {role_name}", True, role_col)
        self.screen.blit(rl, (SCREEN_W - rl.get_width() - 10, 10))
        hints = ["R - restart", "ESC - menu"]
        for i, h in enumerate(hints):
            lbl = self.font_tiny.render(h, True, C_GRAY)
            self.screen.blit(lbl, (10, SCREEN_H - 20 - i*18))

    # ──────────────────── WIN / DEAD ────────────────────
    def _update_win(self, dt, events):
        self.win_timer -= dt
        for e in events:
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_RETURN:
                    next_lvl = min(self.level_idx + 1, len(LEVELS) - 1)
                    self._start_level(next_lvl)
                if e.key == pygame.K_r:
                    self._start_level(self.level_idx)
                if e.key == pygame.K_ESCAPE:
                    self.state = GameState.MENU

    def _draw_win(self):
        self._draw_playing()
        # [ИЗМЕНЕНИЕ] Убран SRCALPHA (требует специального display mode) — используем fill с alpha через set_alpha
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(140)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))
        # [ИЗМЕНЕНИЕ] Эмодзи заменены на текст
        lbl = self.font_big.render("*** POBEDA! ***", True, C_YELLOW)
        self.screen.blit(lbl, lbl.get_rect(center=(SCREEN_W//2, SCREEN_H//2 - 40)))
        hint = self.font_mid.render("Enter - next  |  R - retry  |  ESC - menu", True, C_WHITE)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_W//2, SCREEN_H//2 + 30)))

    def _update_dead(self, dt, events):
        self.dead_timer -= dt
        for e in events:
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_RETURN, pygame.K_r):
                    self._start_level(self.level_idx)
                if e.key == pygame.K_ESCAPE:
                    self.state = GameState.MENU

    def _draw_dead(self):
        self._draw_playing()
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(140)
        overlay.fill((80, 0, 0))
        self.screen.blit(overlay, (0, 0))
        # [ИЗМЕНЕНИЕ] Эмодзи заменены на текст
        lbl = self.font_big.render("--- GAME OVER ---", True, C_RED)
        self.screen.blit(lbl, lbl.get_rect(center=(SCREEN_W//2, SCREEN_H//2 - 40)))
        hint = self.font_mid.render("R / Enter - retry  |  ESC - menu", True, C_WHITE)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_W//2, SCREEN_H//2 + 30)))

    # ──────────────────── Общий фон ────────────────────
    def _draw_bg(self):
        self.screen.fill(C_BG)
        # Тонкий градиент сверху
        for i in range(60):
            alpha = 80 - i
            col = (20, 20, 35)
            pygame.draw.line(self.screen, col, (0, i), (SCREEN_W, i))

    def _quit(self):
        if self.net:
            self.net.close()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()