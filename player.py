"""
player.py — Класс игрока с физикой и анимацией
"""

import pygame
from enum import Enum
import math

TILE     = 40
GRAVITY  = 1400   # px/s²
JUMP_V   = -560
SPEED    = 220
SCREEN_H = 600

class PlayerType(Enum):
    FIRE  = "fire"
    WATER = "water"


class Player:
    W = 28
    H = 36

    def __init__(self, tile_x: float, tile_y: float, ptype: PlayerType):
        self.x  = tile_x * TILE
        self.y  = tile_y * TILE
        self.vx = 0.0
        self.vy = 0.0
        self.w  = self.W
        self.h  = self.H
        self.ptype     = ptype
        self.on_ground = False
        self.facing    = 1   # 1 = вправо, -1 = влево
        self.anim_run  = 0   # счётчик анимации бега

        # Цвета
        if ptype == PlayerType.FIRE:
            self.color  = (255, 100, 30)
            self.color2 = (255, 200, 50)
            self.glow   = (255, 60,  10)
        else:
            self.color  = (30,  130, 255)
            self.color2 = (100, 200, 255)
            self.glow   = (10,  80,  200)

    # ─── Ввод ───────────────────────────────────
    def handle_input_wasd(self, keys):
        self.vx = 0
        if keys[pygame.K_a]:
            self.vx = -SPEED
            self.facing = -1
        if keys[pygame.K_d]:
            self.vx = SPEED
            self.facing = 1
        if keys[pygame.K_w] and self.on_ground:
            self.vy = JUMP_V
            self.on_ground = False

    def handle_input_arrows(self, keys):
        self.vx = 0
        if keys[pygame.K_LEFT]:
            self.vx = -SPEED
            self.facing = -1
        if keys[pygame.K_RIGHT]:
            self.vx = SPEED
            self.facing = 1
        if keys[pygame.K_UP] and self.on_ground:
            self.vy = JUMP_V
            self.on_ground = False

    # ─── Физика ─────────────────────────────────
    def update(self, dt: float, platforms: list):
        # Гравитация
        self.vy += GRAVITY * dt
        self.vy  = min(self.vy, 900)

        # Движение X
        self.x += self.vx * dt
        self._resolve_x(platforms)

        # Движение Y
        self.on_ground = False
        self.y += self.vy * dt
        self._resolve_y(platforms)

        # Ограничение экрана по X
        self.x = max(0, min(self.x, 1024 - self.w))

        # Анимация бега
        if abs(self.vx) > 10:
            self.anim_run += 1
        else:
            self.anim_run = 0

    def _resolve_x(self, platforms):
        pr = pygame.Rect(self.x, self.y, self.w, self.h)
        for plat in platforms:
            pr2 = pygame.Rect(plat[0]*TILE, plat[1]*TILE, plat[2]*TILE, plat[3]*TILE)
            if pr.colliderect(pr2):
                if self.vx > 0:
                    self.x = pr2.left - self.w
                elif self.vx < 0:
                    self.x = pr2.right
                self.vx = 0

    def _resolve_y(self, platforms):
        pr = pygame.Rect(self.x, self.y, self.w, self.h)
        for plat in platforms:
            pr2 = pygame.Rect(plat[0]*TILE, plat[1]*TILE, plat[2]*TILE, plat[3]*TILE)
            if pr.colliderect(pr2):
                if self.vy > 0:
                    self.y = pr2.top - self.h
                    self.on_ground = True
                elif self.vy < 0:
                    self.y = pr2.bottom
                self.vy = 0

    # ─── Отрисовка ──────────────────────────────
    def draw(self, surf: pygame.Surface, tick: int):
        cx = int(self.x + self.w // 2)
        cy = int(self.y + self.h // 2)

        # Мягкое свечение (полупрозрачный круг)
        glow_surf = pygame.Surface((80, 80), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*self.glow, 60), (40, 40), 34)
        surf.blit(glow_surf, (cx - 40, cy - 40))

        # Тень
        pygame.draw.ellipse(surf, (0, 0, 0, 80),
                            (int(self.x + 2), int(self.y + self.h - 6), self.w - 4, 8))

        # Тело — прямоугольник со скруглёнными углами
        body_rect = pygame.Rect(int(self.x), int(self.y), self.w, self.h)
        pygame.draw.rect(surf, self.color,  body_rect, border_radius=8)
        pygame.draw.rect(surf, self.color2, body_rect, 2, border_radius=8)

        # Глаза
        eye_y  = int(self.y + 10)
        e_off  = 7 if self.facing == 1 else -3
        pygame.draw.circle(surf, (255, 255, 255), (cx + e_off, eye_y), 5)
        pygame.draw.circle(surf, (30,  30,  30),  (cx + e_off + self.facing, eye_y), 3)

        # Анимированная "шевелюра" (огонь / вода)
        phase = tick * 0.12
        if self.ptype == PlayerType.FIRE:
            for i in range(3):
                fx = int(self.x + 6 + i * 8)
                fh = int(8 + 4 * math.sin(phase + i * 1.2))
                pygame.draw.ellipse(surf, (255, 160, 0),
                                    (fx, int(self.y) - fh, 8, fh + 4))
        else:
            for i in range(3):
                bx = int(self.x + 4 + i * 8)
                bh = int(6 + 3 * math.sin(phase + i * 1.0))
                pygame.draw.ellipse(surf, (80, 180, 255),
                                    (bx, int(self.y) - bh + 2, 8, bh + 3))

        # Ноги (анимация при беге)
        if self.anim_run > 0:
            leg_phase = (tick * 0.2) % (2 * math.pi)
            l1 = int(4 * math.sin(leg_phase))
            l2 = int(4 * math.sin(leg_phase + math.pi))
            pygame.draw.line(surf, self.color2,
                             (int(self.x + 8),  int(self.y + self.h)),
                             (int(self.x + 8),  int(self.y + self.h + 8 + l1)), 3)
            pygame.draw.line(surf, self.color2,
                             (int(self.x + 20), int(self.y + self.h)),
                             (int(self.x + 20), int(self.y + self.h + 8 + l2)), 3)
