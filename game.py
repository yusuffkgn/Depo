"""Undertale-inspired bullet hell battle implemented with pygame.

This module defines the full game loop, player, enemy, attacks and
animation systems that produce a cinematic battle sequence with multiple
phases.  The code focuses on readability while featuring a wide variety
of attack mechanics that mirror and expand on classic Undertale
encounters.
"""
from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Sequence, Tuple, TypeAlias

import pygame

SCREEN_SIZE = (960, 720)
FPS = 60
BASE_ARENA_RECT = pygame.Rect(0, 0, 420, 260)
SAVE_FILE = Path("savegame.json")

Color = Tuple[int, int, int]
Vec2: TypeAlias = pygame.Vector2


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def load_save_data() -> dict:
    if SAVE_FILE.exists():
        try:
            with SAVE_FILE.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            pass
    return {"best_time": {"Story": 0.0, "Challenge": 0.0, "Nightmare": 0.0}}


def store_save_data(data: dict) -> None:
    with SAVE_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


# ---------------------------------------------------------------------------
# Game entities
# ---------------------------------------------------------------------------


@dataclass
class Player:
    arena: pygame.Rect
    difficulty_scale: float
    max_hp: int = 40
    heart_color: Color = (255, 90, 120)
    slow_color: Color = (255, 255, 255)
    position: Vec2 = field(default_factory=lambda: Vec2(0, 0))
    velocity: Vec2 = field(default_factory=lambda: Vec2(0, 0))
    hp: float = 40
    invuln_timer: float = 0.0
    gravity: float = 0.0
    jump_strength: float = 9.5
    move_speed: float = 170.0
    friction: float = 0.92
    airborne: bool = False
    slow_move_factor: float = 0.45

    def __post_init__(self) -> None:
        self.hp = self.max_hp
        self.position = Vec2(self.arena.centerx, self.arena.centery)

    def reset_state(self, arena: pygame.Rect) -> None:
        self.arena = arena.copy()
        self.position = Vec2(self.arena.centerx, self.arena.centery)
        self.velocity = Vec2()
        self.gravity = 0.0
        self.airborne = False

    def damage(self, amount: float) -> None:
        if self.invuln_timer <= 0:
            scaled = amount * self.difficulty_scale
            self.hp = max(0.0, self.hp - scaled)
            self.invuln_timer = 0.65

    def heal_full(self) -> None:
        self.hp = self.max_hp
        self.invuln_timer = 0.0

    def set_gravity(self, gravity: float) -> None:
        if gravity == 0:
            self.airborne = False
            self.velocity.y = 0
        self.gravity = gravity

    def update(self, pressed: Sequence[bool], dt: float) -> None:
        speed = self.move_speed
        if pressed[pygame.K_LSHIFT] or pressed[pygame.K_RSHIFT]:
            speed *= self.slow_move_factor
            heart_color = self.slow_color
        else:
            heart_color = self.heart_color
        self.current_color = heart_color

        direction = Vec2(
            (pressed[pygame.K_RIGHT] or pressed[pygame.K_d])
            - (pressed[pygame.K_LEFT] or pressed[pygame.K_a]),
            (pressed[pygame.K_DOWN] or pressed[pygame.K_s])
            - (pressed[pygame.K_UP] or pressed[pygame.K_w]),
        )
        if self.gravity != 0:
            direction.y = 0
            if (pressed[pygame.K_UP] or pressed[pygame.K_w]) and not self.airborne:
                self.velocity.y = -self.jump_strength
                self.airborne = True
        if direction.length_squared() > 0:
            direction = direction.normalize()
        self.velocity.x = direction.x * speed
        if self.gravity == 0:
            self.velocity.y = direction.y * speed
        else:
            self.velocity.y += self.gravity * dt * 60
            self.velocity.y = min(self.velocity.y, 12)

        self.position += self.velocity * dt

        if self.gravity != 0:
            if self.position.y >= self.arena.bottom - 12:
                self.position.y = self.arena.bottom - 12
                self.velocity.y *= -self.friction
                if abs(self.velocity.y) < 0.1:
                    self.velocity.y = 0
                self.airborne = False
        else:
            if not self.arena.top <= self.position.y <= self.arena.bottom:
                self.position.y = min(max(self.position.y, self.arena.top), self.arena.bottom)

        if not self.arena.left <= self.position.x <= self.arena.right:
            self.position.x = min(max(self.position.x, self.arena.left), self.arena.right)

        if self.invuln_timer > 0:
            self.invuln_timer = max(0.0, self.invuln_timer - dt)

    def draw(self, surface: pygame.Surface) -> None:
        blink = int(pygame.time.get_ticks() / 60) % 2 == 0
        if self.invuln_timer > 0 and blink:
            return
        pygame.draw.polygon(
            surface,
            self.current_color,
            [
                (self.position.x, self.position.y + 8),
                (self.position.x - 8, self.position.y),
                (self.position.x - 4, self.position.y - 8),
                (self.position.x, self.position.y - 4),
                (self.position.x + 4, self.position.y - 8),
                (self.position.x + 8, self.position.y),
            ],
        )


@dataclass
class Bullet:
    position: Vec2
    velocity: Vec2
    radius: float
    color: Color
    damage: float
    life: float = 6.0
    sprite: Callable[[pygame.Surface, Vec2, float], None] | None = None
    rotation_speed: float = 0.0
    angle: float = 0.0

    def update(self, dt: float) -> None:
        self.position += self.velocity * dt
        self.angle += self.rotation_speed * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface) -> None:
        if self.sprite:
            self.sprite(surface, self.position, self.angle)
        else:
            pygame.draw.circle(surface, self.color, self.position, self.radius)

    def collides(self, point: Vec2) -> bool:
        return self.position.distance_to(point) < self.radius


def create_star_sprite(color: Color, inner: float, outer: float, points: int = 5) -> Callable[[pygame.Surface, Vec2, float], None]:
    base_surface = pygame.Surface((outer * 2 + 2, outer * 2 + 2), pygame.SRCALPHA)
    center = Vec2(base_surface.get_width() / 2, base_surface.get_height() / 2)
    angle_step = math.pi / points
    vertices: List[Tuple[float, float]] = []
    for i in range(points * 2):
        radius = outer if i % 2 == 0 else inner
        angle = i * angle_step - math.pi / 2
        vertices.append((center.x + math.cos(angle) * radius, center.y + math.sin(angle) * radius))
    pygame.draw.polygon(base_surface, color, vertices)

    def _draw(surface: pygame.Surface, pos: Vec2, angle: float) -> None:
        rotated = pygame.transform.rotozoom(base_surface, -math.degrees(angle), 1.0)
        rect = rotated.get_rect(center=pos)
        surface.blit(rotated, rect)

    return _draw


def create_spear_sprite(color: Color, length: int, width: int) -> Callable[[pygame.Surface, Vec2, float], None]:
    base_surface = pygame.Surface((length, width * 2), pygame.SRCALPHA)
    pygame.draw.polygon(
        base_surface,
        color,
        [(0, width), (length - width, 0), (length, width), (length - width, width * 2)],
    )

    def _draw(surface: pygame.Surface, pos: Vec2, angle: float) -> None:
        rotated = pygame.transform.rotozoom(base_surface, -math.degrees(angle), 1.0)
        rect = rotated.get_rect(center=pos)
        surface.blit(rotated, rect)

    return _draw


def create_blossom_sprite(color: Color, radius: int) -> Callable[[pygame.Surface, Vec2, float], None]:
    base_surface = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
    center = Vec2(base_surface.get_width() / 2, base_surface.get_height() / 2)
    for i in range(6):
        angle = i * math.pi / 3
        offset = Vec2(math.cos(angle), math.sin(angle)) * radius
        pygame.draw.circle(base_surface, color, center + offset, radius)
    pygame.draw.circle(base_surface, (255, 255, 255), center, radius * 0.7)

    def _draw(surface: pygame.Surface, pos: Vec2, angle: float) -> None:
        rotated = pygame.transform.rotozoom(base_surface, -math.degrees(angle), 1.0)
        rect = rotated.get_rect(center=pos)
        surface.blit(rotated, rect)

    return _draw


STAR_SPRITE = create_star_sprite((255, 220, 120), 6, 18, 6)
SPEAR_SPRITE = create_spear_sprite((120, 200, 255), 120, 14)
BLOSSOM_SPRITE = create_blossom_sprite((255, 180, 220), 12)


class AttackPattern:
    name: str = "Base"

    def __init__(self, arena: pygame.Rect, difficulty: str):
        self.arena = arena
        self.timer = 0.0
        self.duration = 12.0
        self.difficulty = difficulty
        self.bullets: List[Bullet] = []
        self.platforms: List[pygame.Rect] = []
        self.gravity = 0.0
        self.ticks = 0

    def update(self, player: Player, dt: float) -> None:
        self.timer += dt
        self.ticks += 1
        for bullet in list(self.bullets):
            bullet.update(dt)
            if bullet.life <= 0 or not self.arena.inflate(220, 120).collidepoint(bullet.position):
                self.bullets.remove(bullet)

        self.spawn(player, dt)
        if self.gravity != player.gravity:
            player.set_gravity(self.gravity)
        self.update_platforms(dt)

        for bullet in self.bullets:
            if bullet.collides(player.position):
                player.damage(bullet.damage)
        if self.gravity != 0:
            self.handle_platform_collisions(player)

    def is_finished(self) -> bool:
        return self.timer > self.duration

    def spawn(self, player: Player, dt: float) -> None:
        raise NotImplementedError

    def draw(self, surface: pygame.Surface) -> None:
        for rect in self.platforms:
            pygame.draw.rect(surface, (170, 210, 255), rect, border_radius=6)
        for bullet in self.bullets:
            bullet.draw(surface)

    def update_platforms(self, dt: float) -> None:
        pass

    def handle_platform_collisions(self, player: Player) -> None:
        for plat in self.platforms:
            if plat.collidepoint(player.position.x, player.position.y + 8):
                player.position.y = plat.top - 8
                player.velocity.y = 0
                player.airborne = False
                break

    def arena_style(self) -> Tuple[Color, Color]:
        return (40, 40, 40), (255, 255, 255)


class SpiralBlossom(AttackPattern):
    name = "Blooming Spiral"

    def __init__(self, arena: pygame.Rect, difficulty: str):
        super().__init__(arena, difficulty)
        self.duration = 11.0
        self.spawn_interval = 0.35 if difficulty == "Story" else 0.28 if difficulty == "Challenge" else 0.22
        self.base_speed = 140 if difficulty == "Story" else 170 if difficulty == "Challenge" else 210
        self.blossom_color = (255, 170, 210)
        self.ring_radius = 36

    def spawn(self, player: Player, dt: float) -> None:
        if self.timer < 1.0:
            return
        if (self.timer - dt) // self.spawn_interval != self.timer // self.spawn_interval:
            angle_offset = (self.timer * 1.8) % (math.pi * 2)
            for i in range(6):
                angle = angle_offset + i * math.pi / 3
                direction = Vec2(math.cos(angle), math.sin(angle))
                speed = self.base_speed * (1.0 + 0.15 * math.sin(self.timer * 2.0 + i))
                velocity = direction * speed
                position = Vec2(self.arena.center) + direction * (20 + self.ring_radius)
                bullet = Bullet(position, velocity, 16, (255, 220, 220), damage=4, sprite=BLOSSOM_SPRITE, rotation_speed=1.5)
                self.bullets.append(bullet)

    def arena_style(self) -> Tuple[Color, Color]:
        return (30, 12, 22), (255, 180, 220)


class GravityPlatforms(AttackPattern):
    name = "Celestial Platforms"

    def __init__(self, arena: pygame.Rect, difficulty: str):
        super().__init__(arena, difficulty)
        self.duration = 14.0
        self.gravity = 18
        self.spawn_interval = 0.9 if difficulty == "Story" else 0.7 if difficulty == "Challenge" else 0.55
        self.platform_speed = 45 if difficulty == "Story" else 55 if difficulty == "Challenge" else 70
        self.platforms = [pygame.Rect(arena.left + 40, arena.centery, 110, 18), pygame.Rect(arena.right - 150, arena.centery - 70, 120, 18)]

    def update_platforms(self, dt: float) -> None:
        for rect in self.platforms:
            rect.x += math.sin(self.timer * 1.5 + rect.y * 0.05) * self.platform_speed * dt

    def spawn(self, player: Player, dt: float) -> None:
        if self.timer < 1.5:
            return
        if (self.timer - dt) // self.spawn_interval != self.timer // self.spawn_interval:
            origin = random.choice([Vec2(self.arena.left + 20, self.arena.top + 20), Vec2(self.arena.right - 20, self.arena.top + 40)])
            target = Vec2(player.position.x, self.arena.bottom - 24)
            direction = (target - origin).normalize()
            speed = 220 if self.difficulty == "Story" else 260 if self.difficulty == "Challenge" else 310
            bullet = Bullet(origin, direction * speed, 12, (150, 200, 255), damage=5, sprite=SPEAR_SPRITE, rotation_speed=2.5)
            self.bullets.append(bullet)
        if random.random() < dt * (0.8 if self.difficulty == "Story" else 1.2 if self.difficulty == "Challenge" else 1.5):
            x = random.uniform(self.arena.left + 20, self.arena.right - 20)
            velocity = Vec2(0, random.uniform(220, 320))
            bullet = Bullet(Vec2(x, self.arena.top - 40), velocity, 10, (255, 180, 120), damage=3)
            bullet.rotation_speed = 3
            self.bullets.append(bullet)

    def arena_style(self) -> Tuple[Color, Color]:
        return (15, 25, 45), (150, 200, 255)


class PrismRain(AttackPattern):
    name = "Prism Rain"

    def __init__(self, arena: pygame.Rect, difficulty: str):
        super().__init__(arena, difficulty)
        self.duration = 13.5
        self.spawn_interval = 0.3 if difficulty == "Story" else 0.24 if difficulty == "Challenge" else 0.18
        self.base_speed = 190 if difficulty == "Story" else 230 if difficulty == "Challenge" else 280
        self.gravity = 0

    def spawn(self, player: Player, dt: float) -> None:
        phase = int(self.timer * 2) % 4
        if (self.timer - dt) // self.spawn_interval != self.timer // self.spawn_interval:
            angles = []
            if phase == 0:
                angles = [math.pi / 4, math.pi * 3 / 4]
            elif phase == 1:
                angles = [math.pi / 6, math.pi * 5 / 6]
            elif phase == 2:
                angles = [0, math.pi]
            else:
                angles = [math.pi / 3, math.pi * 2 / 3, math.pi * 5 / 3]
            for angle in angles:
                direction = Vec2(math.cos(angle), math.sin(angle))
                speed = self.base_speed * (1 + 0.1 * math.sin(self.timer * 3 + angle))
                start = Vec2(self.arena.center) + direction * (self.arena.width // 2)
                bullet = Bullet(start, direction * -speed, 9, (120, 255, 220), damage=2.7, sprite=STAR_SPRITE, rotation_speed=2.2)
                self.bullets.append(bullet)
        if random.random() < dt * 0.6:
            offset = random.uniform(-self.arena.width * 0.4, self.arena.width * 0.4)
            start = Vec2(self.arena.centerx + offset, self.arena.top - 30)
            velocity = Vec2(math.sin(self.timer * 2 + offset * 0.05) * 40, self.base_speed * 0.8)
            bullet = Bullet(start, velocity, 8, (80, 240, 255), damage=2.5)
            bullet.rotation_speed = 4.2
            self.bullets.append(bullet)

    def arena_style(self) -> Tuple[Color, Color]:
        return (12, 32, 32), (120, 255, 220)


class LaserCascade(AttackPattern):
    name = "Aurora Cascade"

    def __init__(self, arena: pygame.Rect, difficulty: str):
        super().__init__(arena, difficulty)
        self.duration = 10.5
        self.beams: List[Tuple[pygame.Rect, float, float]] = []
        self.telegraph_time = 1.2 if difficulty == "Story" else 1.0 if difficulty == "Challenge" else 0.8
        self.cascade_interval = 0.7 if difficulty == "Story" else 0.55 if difficulty == "Challenge" else 0.45
        self.damage = 6.0

    def spawn(self, player: Player, dt: float) -> None:
        if self.timer < 1.0:
            return
        if (self.timer - dt) // self.cascade_interval != self.timer // self.cascade_interval:
            lane_width = self.arena.width // 5
            lane = random.randint(0, 4)
            rect = pygame.Rect(self.arena.left + lane * lane_width, self.arena.top - 40, lane_width, self.arena.height + 80)
            start_time = self.timer
            beam_color_phase = random.uniform(0, 2 * math.pi)
            self.beams.append((rect, start_time, beam_color_phase))

        for beam in list(self.beams):
            rect, start_time, color_phase = beam
            if self.timer - start_time >= self.telegraph_time:
                expanded = rect.inflate(0, 30)
                if expanded.collidepoint(player.position.x, player.position.y):
                    player.damage(self.damage * dt * 2.6)
            if self.timer - start_time > self.telegraph_time + 0.9:
                self.beams.remove(beam)

    def draw(self, surface: pygame.Surface) -> None:
        super().draw(surface)
        for rect, start_time, phase in self.beams:
            elapsed = max(0.0, self.timer - start_time)
            progress = min(1.0, elapsed / self.telegraph_time)
            color = (
                int(120 + 120 * math.sin(phase + elapsed * 3)),
                int(120 + 120 * math.sin(phase + elapsed * 3 + math.pi * 2 / 3)),
                int(120 + 120 * math.sin(phase + elapsed * 3 + math.pi * 4 / 3)),
            )
            telegraph_surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            alpha = int(80 + 120 * progress)
            telegraph_surface.fill((*color, alpha))
            surface.blit(telegraph_surface, rect)
            if elapsed > self.telegraph_time:
                intensity = min(255, int(180 + (elapsed - self.telegraph_time) * 420))
                laser_surface = pygame.Surface(rect.size, pygame.SRCALPHA)
                pygame.draw.rect(laser_surface, (*color, intensity), laser_surface.get_rect())
                glow = pygame.transform.smoothscale(laser_surface, (rect.width, rect.height))
                surface.blit(glow, rect)

    def arena_style(self) -> Tuple[Color, Color]:
        return (10, 12, 28), (150, 200, 255)


ATTACK_ROTATION = [SpiralBlossom, PrismRain, GravityPlatforms, LaserCascade]


@dataclass
class EnemyPhase:
    hp_threshold: float
    palette: Tuple[Color, Color, Color]
    attack_indices: Tuple[int, ...]


class Enemy:
    def __init__(self, name: str, difficulty: str):
        self.name = name
        self.max_hp = 240
        self.hp = self.max_hp
        self.phase_index = 0
        self.difficulty = difficulty
        self.phases = [
            EnemyPhase(0.75, ((100, 140, 220), (70, 100, 180), (40, 60, 120)), (0, 1)),
            EnemyPhase(0.5, ((220, 140, 160), (200, 80, 120), (80, 20, 60)), (2, 1, 0)),
            EnemyPhase(0.25, ((120, 220, 200), (40, 120, 120), (12, 50, 60)), (3, 2, 1, 0)),
            EnemyPhase(0.0, ((255, 240, 240), (180, 60, 60), (60, 16, 16)), (3, 2, 1, 0)),
        ]
        self.current_attack: AttackPattern | None = None
        self.attack_queue: List[int] = []
        self.attack_timer = 0.0
        self.slash_effect_time = -1.0

    def update(self, player: Player, arena: pygame.Rect, dt: float) -> None:
        if self.current_attack is None:
            self.start_next_attack(arena)
        else:
            self.current_attack.update(player, dt)
            self.attack_timer += dt
            if self.current_attack.is_finished():
                self.hp = max(0.0, self.hp - 18)
                self.current_attack = None
                self.attack_timer = 0.0
                self.slash_effect_time = pygame.time.get_ticks() / 1000.0
        self.update_phase(player)

    def update_phase(self, player: Player) -> None:
        ratio = self.hp / self.max_hp
        while self.phase_index < len(self.phases) - 1 and ratio <= self.phases[self.phase_index].hp_threshold:
            self.phase_index += 1
            player.invuln_timer = 1.5
            player.set_gravity(0)

    def start_next_attack(self, arena: pygame.Rect) -> None:
        if not self.attack_queue:
            phase = self.phases[self.phase_index]
            indices = list(phase.attack_indices)
            random.shuffle(indices)
            self.attack_queue.extend(indices)
        next_index = self.attack_queue.pop(0)
        attack_cls = ATTACK_ROTATION[next_index]
        self.current_attack = attack_cls(arena.copy(), self.difficulty)

    def draw(self, surface: pygame.Surface, position: Tuple[int, int]) -> None:
        phase = self.phases[self.phase_index]
        base_color, accent_color, shadow_color = phase.palette
        wobble = math.sin(pygame.time.get_ticks() * 0.003) * 8
        enemy_rect = pygame.Rect(0, 0, 220, 120)
        enemy_rect.center = position
        pygame.draw.ellipse(surface, shadow_color, enemy_rect.inflate(60, 50))
        body_rect = enemy_rect.copy()
        pygame.draw.ellipse(surface, base_color, body_rect)
        eye_offset = 34
        for direction in (-1, 1):
            eye_center = (body_rect.centerx + eye_offset * direction, body_rect.centery - 10 + wobble)
            pygame.draw.circle(surface, accent_color, eye_center, 18)
            pupil_offset = math.sin(pygame.time.get_ticks() * 0.004 + direction) * 6
            pygame.draw.circle(surface, (10, 10, 20), (eye_center[0] + pupil_offset, eye_center[1]), 8)
        mouth_rect = pygame.Rect(0, 0, 110, 30)
        mouth_rect.center = (body_rect.centerx, body_rect.centery + 24)
        pygame.draw.ellipse(surface, accent_color, mouth_rect)
        inner_rect = mouth_rect.inflate(-30, -16)
        pygame.draw.ellipse(surface, (30, 0, 0), inner_rect)

        name_font = pygame.font.Font(None, 40)
        name_surf = name_font.render(self.name, True, accent_color)
        surface.blit(name_surf, name_surf.get_rect(center=(body_rect.centerx, body_rect.top - 26)))

        if self.slash_effect_time > 0:
            elapsed = pygame.time.get_ticks() / 1000.0 - self.slash_effect_time
            if elapsed < 0.6:
                draw_slash(surface, body_rect.center, elapsed)
            else:
                self.slash_effect_time = -1.0


def draw_slash(surface: pygame.Surface, center: Tuple[int, int], elapsed: float) -> None:
    slash_length = 420
    slash_width = 10
    speed = 820
    offset = elapsed * speed
    alpha = max(0, 255 - int(elapsed * 420))
    color = (255, 255, 255, alpha)
    slash_surface = pygame.Surface((slash_length, slash_width * 4), pygame.SRCALPHA)
    pygame.draw.rect(slash_surface, color, (0, slash_width, slash_length, slash_width * 2))
    for i in range(3):
        pygame.draw.rect(
            slash_surface,
            (255, 200 - i * 40, 120, alpha // (i + 1)),
            (0, slash_width - i * 4, slash_length, slash_width * 2 + i * 8),
        )
    slash_surface = pygame.transform.rotate(slash_surface, -35)
    rect = slash_surface.get_rect(center=(center[0] - offset, center[1] + offset * 0.4))
    surface.blit(slash_surface, rect)


class Arena:
    def __init__(self, base_rect: pygame.Rect):
        self.base_rect = base_rect
        self.rect = base_rect.copy()
        self.animation_time = 0.0

    def update(self, attack: AttackPattern | None, dt: float) -> None:
        self.animation_time += dt
        target = self.base_rect.copy()
        if attack:
            wobble = math.sin(self.animation_time * 3.0) * 12
            if isinstance(attack, GravityPlatforms):
                target = target.inflate(-20, -60)
                target.move_ip(0, wobble)
            elif isinstance(attack, SpiralBlossom):
                target = target.inflate(60, -30)
                target.move_ip(math.sin(self.animation_time) * 20, 0)
            elif isinstance(attack, LaserCascade):
                target = target.inflate(-40, -20)
                target.move_ip(math.sin(self.animation_time * 4) * 14, math.cos(self.animation_time * 4) * 14)
            else:
                target = target.inflate(0, -40)
                target.move_ip(0, wobble * 0.5)
        else:
            target = target.inflate(20 * math.sin(self.animation_time * 2) + 5, 12 * math.sin(self.animation_time * 2 + math.pi / 4))
        self.rect = self.rect.inflate((target.width - self.rect.width) * dt * 5, (target.height - self.rect.height) * dt * 5)
        self.rect.center = (
            self.rect.centerx + (target.centerx - self.rect.centerx) * dt * 5,
            self.rect.centery + (target.centery - self.rect.centery) * dt * 5,
        )

    def draw(self, surface: pygame.Surface, attack: AttackPattern | None) -> None:
        surface_rect = self.rect.inflate(40, 40)
        fill = pygame.Surface(surface_rect.size, pygame.SRCALPHA)
        if attack:
            interior, border = attack.arena_style()
        else:
            interior, border = (30, 30, 30), (230, 230, 230)
        pygame.draw.rect(fill, (*interior, 200), fill.get_rect(), border_radius=18)
        pygame.draw.rect(fill, (*border, 255), fill.get_rect(), 6, border_radius=18)
        surface.blit(fill, fill.get_rect(center=self.rect.center))


class Background:
    def __init__(self):
        self.orbs = [
            [Vec2(random.uniform(0, SCREEN_SIZE[0]), random.uniform(0, SCREEN_SIZE[1])), random.uniform(20, 60), random.uniform(0.2, 0.6)]
            for _ in range(28)
        ]

    def update(self, dt: float) -> None:
        for orb in self.orbs:
            orb[0].y += orb[2] * 30 * dt
            if orb[0].y > SCREEN_SIZE[1] + 30:
                orb[0].y = -30
                orb[0].x = random.uniform(0, SCREEN_SIZE[0])

    def draw(self, surface: pygame.Surface, palette: Tuple[Color, Color, Color]) -> None:
        base, glow, accent = palette
        gradient = pygame.Surface(SCREEN_SIZE)
        for y in range(SCREEN_SIZE[1]):
            t = y / SCREEN_SIZE[1]
            color = (
                int(base[0] * (1 - t) + glow[0] * t),
                int(base[1] * (1 - t) + glow[1] * t),
                int(base[2] * (1 - t) + glow[2] * t),
            )
            pygame.draw.line(gradient, color, (0, y), (SCREEN_SIZE[0], y))
        surface.blit(gradient, (0, 0))
        for pos, radius, speed in self.orbs:
            pygame.draw.circle(surface, accent, (int(pos.x), int(pos.y)), int(radius * 0.4), width=2)
            pygame.draw.circle(surface, glow, (int(pos.x), int(pos.y)), int(radius * 0.6), width=1)


class SlashCinematic:
    def __init__(self):
        self.active = False
        self.timer = 0.0

    def play(self) -> None:
        self.active = True
        self.timer = 0.0

    def update(self, dt: float) -> None:
        if self.active:
            self.timer += dt
            if self.timer > 1.0:
                self.active = False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.active:
            return
        slash_count = 6
        for i in range(slash_count):
            t = (self.timer + i * 0.1) % 1.0
            alpha = max(0, 255 - int(t * 320))
            length = 600
            width = 30
            slash_surface = pygame.Surface((length, width), pygame.SRCALPHA)
            pygame.draw.rect(slash_surface, (255, 255, 255, alpha), (0, 0, length, width))
            pygame.draw.rect(slash_surface, (255, 200, 120, alpha // 2), (0, width // 4, length, width // 2))
            slash_surface = pygame.transform.rotate(slash_surface, -45 + math.sin(self.timer * 6 + i) * 10)
            rect = slash_surface.get_rect(center=(SCREEN_SIZE[0] / 2 + math.sin(t * 6 + i) * 120, SCREEN_SIZE[1] / 2))
            surface.blit(slash_surface, rect)


class TitleScreen:
    def __init__(self, background: Background):
        self.background = background
        self.font_large = pygame.font.Font(None, 96)
        self.font_small = pygame.font.Font(None, 36)
        self.options = ["Story", "Challenge", "Nightmare"]
        self.selection = 0
        self.pulse_timer = 0.0

    def update(self, dt: float) -> None:
        self.pulse_timer += dt

    def draw(self, surface: pygame.Surface, best_times: dict) -> None:
        title = self.font_large.render("RESONANT SOUL", True, (255, 255, 255))
        surface.blit(title, title.get_rect(center=(SCREEN_SIZE[0] / 2, 140)))

        for i, option in enumerate(self.options):
            is_selected = i == self.selection
            base_color = (255, 200, 120) if is_selected else (200, 200, 220)
            pulse = 1.0 + 0.1 * math.sin(self.pulse_timer * 4 + i)
            text = self.font_small.render(f"{option} Mode", True, base_color)
            rendered = pygame.transform.rotozoom(text, math.sin(self.pulse_timer * 3 + i) * (4 if is_selected else 0), pulse)
            rect = rendered.get_rect(center=(SCREEN_SIZE[0] / 2, 280 + i * 80))
            surface.blit(rendered, rect)
            best = best_times.get(option, 0.0)
            if best:
                best_text = self.font_small.render(f"Best survival: {best:.1f}s", True, (200, 240, 255))
                surface.blit(best_text, best_text.get_rect(center=(SCREEN_SIZE[0] / 2, rect.bottom + 24)))

        hint = self.font_small.render("Press ENTER to challenge Nova Seraph", True, (220, 180, 255))
        surface.blit(hint, hint.get_rect(center=(SCREEN_SIZE[0] / 2, SCREEN_SIZE[1] - 80)))

    def handle_input(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_DOWN, pygame.K_s):
                self.selection = (self.selection + 1) % len(self.options)
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.selection = (self.selection - 1) % len(self.options)
            elif event.key == pygame.K_RETURN:
                return self.options[self.selection]
        return None


class HUD:
    def __init__(self):
        self.font = pygame.font.Font(None, 30)
        self.big_font = pygame.font.Font(None, 48)

    def draw(self, surface: pygame.Surface, player: Player, enemy: Enemy, survival_time: float, difficulty: str) -> None:
        hp_ratio = player.hp / player.max_hp
        hp_bar_rect = pygame.Rect(40, SCREEN_SIZE[1] - 100, 280, 24)
        pygame.draw.rect(surface, (80, 20, 20), hp_bar_rect.inflate(8, 8), border_radius=8)
        inner_rect = hp_bar_rect.inflate(-4, -4)
        fill_width = int(inner_rect.width * hp_ratio)
        pygame.draw.rect(surface, (220, 60, 80), (inner_rect.left, inner_rect.top, fill_width, inner_rect.height), border_radius=6)
        pygame.draw.rect(surface, (255, 255, 255), inner_rect, 2, border_radius=6)

        hp_text = self.big_font.render(f"HP {int(player.hp)}/{player.max_hp}", True, (255, 220, 220))
        surface.blit(hp_text, (hp_bar_rect.left, hp_bar_rect.top - 42))

        enemy_text = self.font.render(f"{enemy.name} {int(enemy.hp)} / {enemy.max_hp}", True, (255, 255, 255))
        surface.blit(enemy_text, (SCREEN_SIZE[0] - 320, 40))

        timer_text = self.font.render(f"Survival: {survival_time:.1f}s", True, (200, 255, 200))
        surface.blit(timer_text, (SCREEN_SIZE[0] - 320, 80))

        diff_text = self.font.render(f"Difficulty: {difficulty}", True, (220, 200, 255))
        surface.blit(diff_text, (SCREEN_SIZE[0] - 320, 110))


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Resonant Soul")
        self.screen = pygame.display.set_mode(SCREEN_SIZE)
        self.clock = pygame.time.Clock()
        self.background = Background()
        self.title_screen = TitleScreen(self.background)
        self.hud = HUD()
        self.slash = SlashCinematic()

        self.save_data = load_save_data()

        self.state = "title"
        self.enemy = Enemy("Nova Seraph", "Story")
        self.player = Player(BASE_ARENA_RECT.copy(), difficulty_scale=1.0)
        self.arena = Arena(BASE_ARENA_RECT.copy())
        self.difficulty = "Story"
        self.survival_time = 0.0

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif self.state == "title":
                    selected = self.title_screen.handle_input(event)
                    if selected:
                        self.start_battle(selected)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            if self.state == "title":
                self.update_title(dt)
            elif self.state == "battle":
                self.update_battle(dt)
            elif self.state == "defeat":
                self.update_defeat(dt)

            pygame.display.flip()

        store_save_data(self.save_data)
        pygame.quit()

    def update_title(self, dt: float) -> None:
        self.background.update(dt)
        self.title_screen.update(dt)
        self.draw_title()

    def update_battle(self, dt: float) -> None:
        self.background.update(dt)
        pressed = pygame.key.get_pressed()
        self.player.update(pressed, dt)
        self.enemy.update(self.player, self.arena.rect, dt)
        self.arena.update(self.enemy.current_attack, dt)
        self.survival_time += dt
        self.slash.update(dt)
        if self.player.hp <= 0:
            self.state = "defeat"
            best = self.save_data.setdefault("best_time", {}).get(self.difficulty, 0.0)
            if self.survival_time > best:
                self.save_data["best_time"][self.difficulty] = round(self.survival_time, 1)
            store_save_data(self.save_data)
        self.draw_battle()

    def update_defeat(self, dt: float) -> None:
        self.background.update(dt)
        self.draw_defeat()
        keys = pygame.key.get_pressed()
        if keys[pygame.K_RETURN]:
            self.state = "title"

    def start_battle(self, difficulty: str) -> None:
        difficulty_scale = {"Story": 0.8, "Challenge": 1.0, "Nightmare": 1.35}[difficulty]
        self.difficulty = difficulty
        self.enemy = Enemy("Nova Seraph", difficulty)
        self.player = Player(self.arena.rect.copy(), difficulty_scale)
        self.player.heal_full()
        self.arena = Arena(BASE_ARENA_RECT.copy())
        self.survival_time = 0.0
        self.state = "battle"
        self.slash.play()

    def draw_title(self) -> None:
        palette = ((14, 12, 24), (40, 30, 60), (120, 80, 140))
        self.background.draw(self.screen, palette)
        self.title_screen.draw(self.screen, self.save_data.get("best_time", {}))

    def draw_battle(self) -> None:
        phase = self.enemy.phases[self.enemy.phase_index]
        self.background.draw(self.screen, phase.palette)
        self.enemy.draw(self.screen, (SCREEN_SIZE[0] // 2, 150))
        self.arena.draw(self.screen, self.enemy.current_attack)
        arena_surface = pygame.Surface(self.arena.rect.size, pygame.SRCALPHA)
        if self.enemy.current_attack:
            self.enemy.current_attack.draw(arena_surface)
        self.player.draw(arena_surface)
        self.screen.blit(arena_surface, self.arena.rect)
        self.hud.draw(self.screen, self.player, self.enemy, self.survival_time, self.difficulty)
        self.slash.draw(self.screen)

    def draw_defeat(self) -> None:
        palette = ((20, 0, 0), (40, 10, 10), (120, 40, 40))
        self.background.draw(self.screen, palette)
        font_big = pygame.font.Font(None, 120)
        font_small = pygame.font.Font(None, 40)
        defeat = font_big.render("DEFEATED", True, (255, 180, 180))
        self.screen.blit(defeat, defeat.get_rect(center=(SCREEN_SIZE[0] / 2, 220)))
        prompt = font_small.render("Press ENTER to try again", True, (255, 220, 220))
        self.screen.blit(prompt, prompt.get_rect(center=(SCREEN_SIZE[0] / 2, 420)))
        stats = font_small.render(f"Survival time: {self.survival_time:.1f}s", True, (200, 255, 200))
        self.screen.blit(stats, stats.get_rect(center=(SCREEN_SIZE[0] / 2, 470)))
        best = self.save_data.get("best_time", {}).get(self.difficulty, 0.0)
        best_text = font_small.render(f"Best for {self.difficulty}: {best:.1f}s", True, (220, 200, 255))
        self.screen.blit(best_text, best_text.get_rect(center=(SCREEN_SIZE[0] / 2, 520)))


if __name__ == "__main__":
    Game().run()
