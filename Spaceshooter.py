import arcade
import math
import random
import sqlite3
from pathlib import Path
from datetime import datetime



# config

SCREEN_WIDTH = 1100
SCREEN_HEIGHT = 700
SCREEN_TITLE = "SPACE DEFENDER"

BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / "assets"
DB_PATH = BASE_DIR / "space_defender.db"

# every image is optional, if a file is missing the game draws the
# ship/enemy/powerup with shapes instead
IMAGE_FILES = {
    "player": "player.png",
    "enemy": "enemy.png",
    "fast": "enemy_fast.png",
    "tank": "enemy_tank.png",
    "health": "powerup_health.png",
    "rapid": "powerup_rapid.png",
    "shield": "powerup_shield.png",
    "spread": "powerup_spread.png",
}

PLAYER_SPEED = 360
PLAYER_RADIUS = 24
PLAYER_MAX_HEALTH = 100
PLAYER_INVINCIBILITY = 1.0

DASH_SPEED_MULT = 3.2
DASH_TIME = 0.16
DASH_COOLDOWN = 1.4

BULLET_SPEED = 850
BULLET_RADIUS = 4
NORMAL_FIRE_RATE = 0.18
RAPID_FIRE_RATE = 0.07

NORMAL_ENEMY_SPEED_MIN = 90
NORMAL_ENEMY_SPEED_MAX = 150
FAST_ENEMY_SPEED_MIN = 170
FAST_ENEMY_SPEED_MAX = 260

INITIAL_SPAWN_INTERVAL = 0.85
MIN_SPAWN_INTERVAL = 0.20

POWERUP_DROP_CHANCE = 0.15
RAPID_DURATION = 8.0
SPREAD_DURATION = 10.0

KILLS_PER_LEVEL = 12
COMBO_WINDOW = 2.0

POINTS = {"normal": 10, "fast": 20, "tank": 50}
CONTACT_DAMAGE = {"normal": 15, "fast": 20, "tank": 30}

STAR_COUNT = 140
PARTICLES_PER_EXPLOSION = 20

WHITE = (255, 255, 255)
CYAN = (0, 220, 255)
YELLOW = (255, 225, 80)
ORANGE = (255, 140, 40)
RED = (255, 60, 70)
GREEN = (70, 235, 120)
BLUE = (80, 140, 255)
PINK = (255, 110, 220)
PURPLE = (170, 80, 240)
GRAY = (170, 180, 195)



# database

class Database:
    '''
    Tiny sqlite wrapper. One file next to the script,
    two tables: players and scores.
    '''

    def __init__(self, path):
        self.path = path
        self.initialize()

    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self):
        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    created_at TEXT NOT NULL,
                    last_played TEXT
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player_id INTEGER NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    survival_seconds REAL NOT NULL DEFAULT 0,
                    played_at TEXT NOT NULL,
                    FOREIGN KEY (player_id) REFERENCES players(id)
                )
            """)

            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_scores_player ON scores(player_id)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_scores_score ON scores(score DESC)"
            )
            db.commit()

    def get_or_create_player(self, name):
        clean_name = " ".join(name.strip().split())
        now = datetime.now().isoformat(timespec="seconds")

        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM players WHERE name = ?",
                (clean_name,)
            ).fetchone()

            if row:
                db.execute(
                    "UPDATE players SET last_played = ? WHERE id = ?",
                    (now, row["id"])
                )
                db.commit()
                return dict(row)

            cursor = db.execute(
                "INSERT INTO players (name, created_at, last_played) VALUES (?, ?, ?)",
                (clean_name, now, now)
            )
            db.commit()

            return {
                "id": cursor.lastrowid,
                "name": clean_name,
                "created_at": now,
                "last_played": now,
            }

    def save_score(self, player_id, score, level, survival_seconds):
        now = datetime.now().isoformat(timespec="seconds")

        with self.connect() as db:
            db.execute(
                """
                INSERT INTO scores (player_id, score, level, survival_seconds, played_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (player_id, int(score), int(level), float(survival_seconds), now)
            )
            db.execute(
                "UPDATE players SET last_played = ? WHERE id = ?",
                (now, player_id)
            )
            db.commit()

    def get_best_score(self, player_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT COALESCE(MAX(score), 0) AS best FROM scores WHERE player_id = ?",
                (player_id,)
            ).fetchone()
            return int(row["best"])

    def get_player_stats(self, player_id):
        with self.connect() as db:
            row = db.execute(
                """
                SELECT
                    COUNT(*) AS games,
                    COALESCE(MAX(score), 0) AS best,
                    COALESCE(MAX(level), 1) AS best_level,
                    COALESCE(MAX(survival_seconds), 0) AS best_time
                FROM scores
                WHERE player_id = ?
                """,
                (player_id,)
            ).fetchone()
            return dict(row)

    def get_leaderboard(self, limit=10):
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT
                    p.name,
                    MAX(s.score) AS score,
                    MAX(s.level) AS level,
                    MAX(s.survival_seconds) AS survival_seconds
                FROM scores s
                JOIN players p ON p.id = s.player_id
                GROUP BY p.id, p.name
                ORDER BY score DESC, level DESC, survival_seconds DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]



# helpers
def distance(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


_textures = {}


def get_texture(name):
    # load once and remember, loading a png on every spawn gets slow fast
    if name not in _textures:
        texture = None
        path = ASSET_DIR / IMAGE_FILES[name]

        try:
            if path.exists():
                texture = arcade.load_texture(str(path))
        except Exception as error:
            print(f"Could not load {path}: {error}")

        _textures[name] = texture

    return _textures[name]


_text_cache = {}


def text(msg, x, y, color, size, anchor_x="left", anchor_y="baseline", bold=False):
    # arcade.draw_text rebuilds the text object every frame and eats fps,
    # so keep arcade.Text objects around and just move them
    key = (msg, size, anchor_x, anchor_y, bold)
    label = _text_cache.get(key)

    if label is None:
        if len(_text_cache) > 500:
            _text_cache.clear()

        label = arcade.Text(
            msg,
            x,
            y,
            color=color,
            font_size=size,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            bold=bold,
        )
        _text_cache[key] = label

    label.x = x
    label.y = y
    label.color = color
    label.draw()


def place(points, x, y, angle_deg, scale=1.0):
    # rotate + move a shape that was drawn facing right (+x)
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)

    return [
        (x + (px * c - py * s) * scale, y + (px * s + py * c) * scale)
        for px, py in points
    ]


def draw_glow(x, y, radius, color, alpha=40, layers=3):
    # cheap glow: a few fat low-alpha circles stacked up
    for i in range(layers):
        arcade.draw_circle_filled(
            x,
            y,
            radius * (1 + i * 0.7),
            (color[0], color[1], color[2], max(4, int(alpha / (i + 1)))),
        )



# ship shapes

SHIP_BODY = [(30, 0), (10, 9), (-14, 11), (-20, 0), (-14, -11), (10, -9)]
SHIP_WING_L = [(8, 8), (-12, 26), (-22, 26), (-14, 8)]
SHIP_WING_R = [(8, -8), (-12, -26), (-22, -26), (-14, -8)]

DRONE_SHAPE = [(24, 0), (-4, 17), (-20, 10), (-12, 0), (-20, -10), (-4, -17)]
DART_SHAPE = [(28, 0), (-14, 10), (-6, 0), (-14, -10)]


def draw_player_ship(x, y, angle, thrust=0.3, scale=1.0):
    # flame first so the hull covers the base of it
    flame = 8 + 16 * thrust + random.uniform(0, 6)

    tail = place([(-20, 0)], x, y, angle, scale)[0]
    draw_glow(tail[0], tail[1], 7 * scale, ORANGE, 55, 3)

    outer = place([(-17, 6), (-17 - flame, 0), (-17, -6)], x, y, angle, scale)
    inner = place([(-17, 3), (-17 - flame * 0.6, 0), (-17, -3)], x, y, angle, scale)
    arcade.draw_polygon_filled(outer, (255, 120, 30, 230))
    arcade.draw_polygon_filled(inner, (255, 240, 160, 255))

    for wing in (SHIP_WING_L, SHIP_WING_R):
        pts = place(wing, x, y, angle, scale)
        arcade.draw_polygon_filled(pts, (40, 95, 180))
        arcade.draw_polygon_outline(pts, (120, 200, 255), 1)

    hull = place(SHIP_BODY, x, y, angle, scale)
    arcade.draw_polygon_filled(hull, (205, 222, 250))
    arcade.draw_polygon_outline(hull, CYAN, 2)

    cockpit = place([(8, 0), (10, 2)], x, y, angle, scale)
    arcade.draw_circle_filled(cockpit[0][0], cockpit[0][1], 5.5 * scale, (0, 170, 230))
    arcade.draw_circle_filled(cockpit[1][0], cockpit[1][1], 2 * scale, (200, 245, 255))


# background

class Star:
    TINTS = [(255, 255, 255), (190, 215, 255), (255, 240, 200)]

    def __init__(self, layer=1):
        self.layer = layer
        self.x = random.uniform(0, SCREEN_WIDTH)
        self.y = random.uniform(0, SCREEN_HEIGHT)
        self.phase = random.uniform(0, math.tau)
        self.tint = random.choice(self.TINTS)

        if layer == 1:
            self.speed = random.uniform(20, 45)
            self.size = random.uniform(1, 1.5)
        elif layer == 2:
            self.speed = random.uniform(45, 80)
            self.size = random.uniform(1.5, 2.5)
        else:
            self.speed = random.uniform(80, 130)
            self.size = random.uniform(2, 3)

    def update(self, delta_time):
        self.y -= self.speed * delta_time

        if self.y < 0:
            self.y = SCREEN_HEIGHT
            self.x = random.uniform(0, SCREEN_WIDTH)

    def draw(self, clock):
        alpha = int(150 + 105 * math.sin(clock * 2.5 + self.phase))
        color = (self.tint[0], self.tint[1], self.tint[2], alpha)

        if self.layer == 3:
            # closest layer gets a little streak so it feels faster
            arcade.draw_line(
                self.x, self.y, self.x, self.y + self.speed * 0.05,
                color, self.size,
            )
        else:
            arcade.draw_circle_filled(self.x, self.y, self.size, color)


class Backdrop:
    '''
    Gradient sky, slow drifting nebula clouds and one big planet.
    Nothing here reacts to the game, it's just scenery.
    '''

    def __init__(self):
        palette = [(90, 40, 170), (30, 90, 180), (160, 40, 120), (20, 130, 140)]

        # x, y, radius, color, drift speed
        self.blobs = [
            [
                random.uniform(0, SCREEN_WIDTH),
                random.uniform(0, SCREEN_HEIGHT),
                random.uniform(120, 260),
                random.choice(palette),
                random.uniform(6, 14),
            ]
            for _ in range(6)
        ]

        self.planet_x = 900
        self.planet_y = 500

    def update(self, delta_time):
        for blob in self.blobs:
            blob[1] -= blob[4] * delta_time

            if blob[1] < -blob[2]:
                blob[1] = SCREEN_HEIGHT + blob[2]
                blob[0] = random.uniform(0, SCREEN_WIDTH)

        self.planet_x -= 4 * delta_time

        if self.planet_x < -150:
            self.planet_x = SCREEN_WIDTH + 150

    def draw(self):
        bands = 14
        band_h = SCREEN_HEIGHT / bands

        for i in range(bands):
            t = i / (bands - 1)
            color = (int(3 + 8 * t), int(5 + 10 * t), int(16 + 22 * t))
            arcade.draw_lrbt_rectangle_filled(
                0, SCREEN_WIDTH, i * band_h, (i + 1) * band_h + 1, color,
            )

        for x, y, radius, color, _ in self.blobs:
            for layer in range(4):
                arcade.draw_circle_filled(
                    x, y, radius * (1 - layer * 0.22),
                    (color[0], color[1], color[2], 10),
                )

        px, py = self.planet_x, self.planet_y
        arcade.draw_circle_filled(px, py, 90, (22, 30, 70))
        arcade.draw_circle_filled(px - 14, py + 14, 72, (40, 58, 120, 210))
        arcade.draw_circle_filled(px - 26, py + 26, 40, (70, 100, 170, 90))
        arcade.draw_circle_outline(px, py, 94, (120, 170, 255, 50), 4)



# effects

class Particle:
    def __init__(self, x, y, color=ORANGE, speed=(50, 220), life=(0.25, 0.65),
                 size=(2, 5), angle=None, spread=math.tau, drag=0.97,
                 max_alpha=255):
        self.x = x
        self.y = y

        if angle is None:
            direction = random.uniform(0, math.tau)
        else:
            direction = angle + random.uniform(-spread / 2, spread / 2)

        velocity = random.uniform(*speed)
        self.velocity_x = math.cos(direction) * velocity
        self.velocity_y = math.sin(direction) * velocity

        self.life = random.uniform(*life)
        self.max_life = self.life
        self.radius = random.uniform(*size)
        self.color = color
        self.drag = drag
        self.max_alpha = max_alpha

    def update(self, delta_time):
        self.x += self.velocity_x * delta_time
        self.y += self.velocity_y * delta_time
        self.velocity_x *= self.drag
        self.velocity_y *= self.drag
        self.life -= delta_time

    def draw(self):
        if self.life <= 0:
            return

        ratio = self.life / self.max_life
        arcade.draw_circle_filled(
            self.x,
            self.y,
            self.radius * (0.4 + 0.6 * ratio),
            (self.color[0], self.color[1], self.color[2], int(self.max_alpha * ratio)),
        )


class Shockwave:
    def __init__(self, x, y, max_radius=60, color=WHITE):
        self.x = x
        self.y = y
        self.max_radius = max_radius
        self.color = color
        self.life = 0.35
        self.max_life = 0.35

    def update(self, delta_time):
        self.life -= delta_time

    def draw(self):
        t = 1 - max(0, self.life) / self.max_life
        arcade.draw_circle_outline(
            self.x,
            self.y,
            5 + self.max_radius * t,
            (self.color[0], self.color[1], self.color[2], int(200 * (1 - t))),
            3,
        )


class FloatingText:
    def __init__(self, x, y, message, color, size=16):
        self.x = x
        self.y = y
        self.message = message
        self.color = color
        self.size = size
        self.life = 0.9
        self.max_life = 0.9

    def update(self, delta_time):
        self.y += 45 * delta_time
        self.life -= delta_time

    def draw(self):
        alpha = int(255 * max(0, self.life) / self.max_life)
        text(
            self.message, self.x, self.y,
            (self.color[0], self.color[1], self.color[2], alpha),
            self.size, anchor_x="center", bold=True,
        )


# bullet
class Bullet:
    def __init__(self, x, y, angle, color=YELLOW):
        self.x = x
        self.y = y
        self.angle = angle
        self.color = color

        radians = math.radians(angle)
        self.velocity_x = math.cos(radians) * BULLET_SPEED
        self.velocity_y = math.sin(radians) * BULLET_SPEED

        self.radius = BULLET_RADIUS
        self.life = 2.0

    def update(self, delta_time):
        self.x += self.velocity_x * delta_time
        self.y += self.velocity_y * delta_time
        self.life -= delta_time

    def draw(self):
        # stretched line behind the bullet = motion trail
        tail_x = self.x - self.velocity_x * 0.035
        tail_y = self.y - self.velocity_y * 0.035

        arcade.draw_line(
            tail_x, tail_y, self.x, self.y,
            (self.color[0], self.color[1], self.color[2], 110), 5,
        )
        draw_glow(self.x, self.y, self.radius, self.color, 70, 3)
        arcade.draw_circle_filled(self.x, self.y, self.radius, WHITE)

    def is_dead(self):
        return (
            self.life <= 0
            or self.x < -50
            or self.x > SCREEN_WIDTH + 50
            or self.y < -50
            or self.y > SCREEN_HEIGHT + 50
        )


# power ups
POWERUP_INFO = {
    "health": (GREEN, "HULL REPAIR", "Restores 30 hull"),
    "rapid": (YELLOW, "RAPID FIRE", "Shoots much faster"),
    "shield": (BLUE, "SHIELD", "Blocks one hit"),
    "spread": (PINK, "SPREAD SHOT", "Fires three bullets"),
}


def draw_powerup_icon(kind, x, y, s=1.0):
    if kind == PowerUp.HEALTH:
        arcade.draw_lrbt_rectangle_filled(x - 7 * s, x + 7 * s, y - 2.5 * s, y + 2.5 * s, WHITE)
        arcade.draw_lrbt_rectangle_filled(x - 2.5 * s, x + 2.5 * s, y - 7 * s, y + 7 * s, WHITE)

    elif kind == PowerUp.RAPID:
        bolt = [
            (x + 2 * s, y + 9 * s), (x - 6 * s, y - 1 * s), (x - 1 * s, y - 1 * s),
            (x - 3 * s, y - 9 * s), (x + 6 * s, y + 2 * s), (x + 1 * s, y + 2 * s),
        ]
        arcade.draw_polygon_filled(bolt, WHITE)

    elif kind == PowerUp.SHIELD:
        arcade.draw_circle_outline(x, y, 7 * s, WHITE, 2)

    else:
        for dx in (-7, 0, 7):
            arcade.draw_line(x, y - 6 * s, x + dx * s, y + 7 * s, WHITE, 2)


class PowerUp:
    HEALTH = "health"
    RAPID = "rapid"
    SHIELD = "shield"
    SPREAD = "spread"

    def __init__(self, x, y, power_type):
        self.base_x = x
        self.x = x
        self.y = y
        self.type = power_type
        self.radius = 18
        self.speed = 80
        self.age = random.uniform(0, 3)

    def update(self, delta_time):
        self.age += delta_time
        self.y -= self.speed * delta_time
        # sways a bit while it falls, easier to notice
        self.x = self.base_x + math.sin(self.age * 2) * 20

    def draw(self):
        color = POWERUP_INFO[self.type][0]
        pulse = 1 + 0.12 * math.sin(self.age * 6)

        draw_glow(self.x, self.y, 20 * pulse, color, 45, 3)

        texture = get_texture(self.type)

        if texture:
            arcade.draw_texture_rect(
                texture,
                arcade.LBWH(self.x - 20, self.y - 20, 40, 40),
                angle=self.age * 120,
            )
            return

        arcade.draw_circle_filled(self.x, self.y, self.radius, (10, 16, 30))
        arcade.draw_circle_outline(self.x, self.y, self.radius * pulse, color, 2)
        draw_powerup_icon(self.type, self.x, self.y)


# enemy

class Enemy:
    NORMAL = "normal"
    FAST = "fast"
    TANK = "tank"

    def __init__(self, enemy_type, level):
        self.type = enemy_type

        side = random.choice(["top", "bottom", "left", "right"])
        margin = 60

        if side == "top":
            self.x = random.uniform(0, SCREEN_WIDTH)
            self.y = SCREEN_HEIGHT + margin
        elif side == "bottom":
            self.x = random.uniform(0, SCREEN_WIDTH)
            self.y = -margin
        elif side == "left":
            self.x = -margin
            self.y = random.uniform(0, SCREEN_HEIGHT)
        else:
            self.x = SCREEN_WIDTH + margin
            self.y = random.uniform(0, SCREEN_HEIGHT)

        self.angle = 0
        self.spin = random.uniform(0, 360)
        self.flash = 0

        if enemy_type == self.NORMAL:
            self.radius = 22
            self.health = 1
            self.speed = random.uniform(
                NORMAL_ENEMY_SPEED_MIN + level * 5,
                NORMAL_ENEMY_SPEED_MAX + level * 7,
            )
            self.texture_key = "enemy"

        elif enemy_type == self.FAST:
            self.radius = 17
            self.health = 1
            self.speed = random.uniform(
                FAST_ENEMY_SPEED_MIN + level * 7,
                FAST_ENEMY_SPEED_MAX + level * 10,
            )
            self.texture_key = "fast"

        else:
            self.radius = 32
            self.health = 4
            self.speed = random.uniform(60 + level * 3, 95 + level * 4)
            self.texture_key = "tank"

        self.max_health = self.health

    def update(self, player_x, player_y, delta_time):
        dx = player_x - self.x
        dy = player_y - self.y

        self.angle = math.degrees(math.atan2(dy, dx))
        radians = math.radians(self.angle)

        self.x += math.cos(radians) * self.speed * delta_time
        self.y += math.sin(radians) * self.speed * delta_time

        self.spin += 90 * delta_time

        if self.flash > 0:
            self.flash -= delta_time

    def draw(self):
        texture = get_texture(self.texture_key)

        if texture:
            size = self.radius * 2.5
            arcade.draw_texture_rect(
                texture,
                arcade.LBWH(self.x - size / 2, self.y - size / 2, size, size),
                angle=self.angle,
            )
            return

        hit = self.flash > 0

        if self.type == self.NORMAL:
            draw_glow(self.x, self.y, 20, (255, 50, 70), 28, 2)
            pts = place(DRONE_SHAPE, self.x, self.y, self.angle)
            arcade.draw_polygon_filled(pts, WHITE if hit else (200, 40, 62))
            arcade.draw_polygon_outline(pts, (255, 130, 150), 2)
            core = place([(2, 0)], self.x, self.y, self.angle)[0]
            arcade.draw_circle_filled(core[0], core[1], 4, (255, 220, 120))

        elif self.type == self.FAST:
            draw_glow(self.x, self.y, 14, PURPLE, 30, 2)
            pts = place(DART_SHAPE, self.x, self.y, self.angle)
            arcade.draw_polygon_filled(pts, WHITE if hit else (150, 55, 220))
            arcade.draw_polygon_outline(pts, (225, 170, 255), 2)

        else:
            hexagon = [
                (math.cos(math.radians(a)) * self.radius,
                 math.sin(math.radians(a)) * self.radius)
                for a in range(0, 360, 60)
            ]
            draw_glow(self.x, self.y, 26, (255, 150, 40), 26, 2)

            outer = place(hexagon, self.x, self.y, self.spin)
            inner = place(hexagon, self.x, self.y, -self.spin, 0.55)

            arcade.draw_polygon_filled(outer, WHITE if hit else (190, 105, 30))
            arcade.draw_polygon_outline(outer, (255, 205, 110), 3)
            arcade.draw_polygon_filled(inner, (85, 42, 14))

            # core goes red as it gets hurt
            heat = 1 - self.health / self.max_health
            arcade.draw_circle_filled(
                self.x, self.y, 7,
                (255, int(210 - 150 * heat), int(90 - 60 * heat)),
            )

            if self.health < self.max_health:
                bar_w = 46
                left = self.x - bar_w / 2
                top = self.y + self.radius + 12
                arcade.draw_lrbt_rectangle_filled(left, left + bar_w, top, top + 5, (50, 20, 20))
                arcade.draw_lrbt_rectangle_filled(
                    left, left + bar_w * self.health / self.max_health,
                    top, top + 5, ORANGE,
                )

    def is_off_screen(self):
        margin = 100

        return (
            self.x < -margin
            or self.x > SCREEN_WIDTH + margin
            or self.y < -margin
            or self.y > SCREEN_HEIGHT + margin
        )



# player

class Player:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = SCREEN_WIDTH / 2
        self.y = SCREEN_HEIGHT / 2
        self.angle = 90
        self.speed = PLAYER_SPEED
        self.radius = PLAYER_RADIUS
        self.health = PLAYER_MAX_HEALTH
        self.shield = False
        self.invincible_timer = 0

        self.dash_timer = 0
        self.dash_cooldown = 0
        self.dash_dir = (1, 0)
        self.last_move = (0, 0)
        self.moving = False
        self.thrust = 0.2

    def update(self, keys, mouse_x, mouse_y, delta_time):
        move_x = 0
        move_y = 0

        if arcade.key.UP in keys or arcade.key.W in keys:
            move_y += 1
        if arcade.key.DOWN in keys or arcade.key.S in keys:
            move_y -= 1
        if arcade.key.LEFT in keys or arcade.key.A in keys:
            move_x -= 1
        if arcade.key.RIGHT in keys or arcade.key.D in keys:
            move_x += 1

        self.moving = bool(move_x or move_y)

        if self.moving:
            length = math.hypot(move_x, move_y)
            move_x /= length
            move_y /= length
            self.last_move = (move_x, move_y)

        if self.dash_timer > 0:
            dx, dy = self.dash_dir
            self.x += dx * self.speed * DASH_SPEED_MULT * delta_time
            self.y += dy * self.speed * DASH_SPEED_MULT * delta_time
            self.dash_timer -= delta_time
        elif self.moving:
            self.x += move_x * self.speed * delta_time
            self.y += move_y * self.speed * delta_time

        self.x = clamp(self.x, self.radius, SCREEN_WIDTH - self.radius)
        self.y = clamp(self.y, self.radius, SCREEN_HEIGHT - self.radius)

        self.angle = math.degrees(math.atan2(mouse_y - self.y, mouse_x - self.x))

        if self.invincible_timer > 0:
            self.invincible_timer -= delta_time

        if self.dash_cooldown > 0:
            self.dash_cooldown -= delta_time

        # flame length eases toward its target instead of snapping
        target = 1.0 if (self.moving or self.dash_timer > 0) else 0.2
        self.thrust += (target - self.thrust) * min(1, delta_time * 8)

    def try_dash(self):
        if self.dash_cooldown > 0 or self.dash_timer > 0:
            return False

        if self.moving:
            self.dash_dir = self.last_move
        else:
            radians = math.radians(self.angle)
            self.dash_dir = (math.cos(radians), math.sin(radians))

        self.dash_timer = DASH_TIME
        self.dash_cooldown = DASH_COOLDOWN
        # tiny i-frame window so dashing through an enemy is a real move
        self.invincible_timer = max(self.invincible_timer, DASH_TIME + 0.1)
        return True

    def take_damage(self, amount):
        if self.invincible_timer > 0:
            return False

        if self.shield:
            self.shield = False
            self.invincible_timer = PLAYER_INVINCIBILITY
            return False

        self.health -= amount
        self.invincible_timer = PLAYER_INVINCIBILITY
        return True

    def draw(self, clock):
        blinking = (
            self.invincible_timer > 0
            and self.dash_timer <= 0
            and int(self.invincible_timer * 12) % 2 == 0
        )

        if not blinking:
            texture = get_texture("player")

            if texture:
                size = 64
                arcade.draw_texture_rect(
                    texture,
                    arcade.LBWH(self.x - size / 2, self.y - size / 2, size, size),
                    angle=self.angle,
                )
            else:
                draw_player_ship(self.x, self.y, self.angle, self.thrust)

        if self.shield:
            wobble = 2 * math.sin(clock * 6)
            arcade.draw_circle_filled(self.x, self.y, 38, (80, 140, 255, 28))
            arcade.draw_circle_outline(self.x, self.y, 38 + wobble, (120, 170, 255, 220), 3)
            arcade.draw_circle_outline(self.x, self.y, 43 - wobble, (120, 170, 255, 90), 1)



# game window

class SpaceShooter(arcade.Window):
    MENU = "menu"
    NAME_ENTRY = "name_entry"
    LEADERBOARD = "leaderboard"
    CONTROLS = "controls"
    PLAYING = "playing"
    PAUSED = "paused"
    GAME_OVER = "game_over"

    def __init__(self):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)

        self.db = Database(DB_PATH)

        # two cameras: the world one shakes, the gui one never moves
        self.world_camera = arcade.Camera2D()
        self.gui_camera = arcade.Camera2D()

        self.state = self.MENU
        self.menu_items = ["START GAME", "LEADERBOARD", "CONTROLS", "EXIT"]
        self.menu_index = 0

        self.keys = set()
        self.mouse_x = SCREEN_WIDTH / 2
        self.mouse_y = SCREEN_HEIGHT / 2
        self.mouse_down = False

        self.player = Player()

        self.bullets = []
        self.enemies = []
        self.powerups = []
        self.particles = []
        self.shockwaves = []
        self.floaters = []

        self.score = 0
        self.high_score = 0
        self.best_at_start = 0
        self.level = 1
        self.kills = 0
        self.time_alive = 0
        self.clock = 0

        self.combo = 0
        self.combo_timer = 0

        self.enemy_spawn_timer = INITIAL_SPAWN_INTERVAL
        self.shoot_timer = 0
        self.rapid_fire_timer = 0
        self.spread_timer = 0

        self.shake = 0
        self.flash_timer = 0
        self.banner_timer = 0

        self.player_id = None
        self.player_name = ""
        self.name_input = ""

        self.last_score = 0
        self.last_level = 1
        self.last_survival = 0
        self.new_record = False

        self.leaderboard_rows = []

        self.backdrop = Backdrop()
        self.stars = [
            Star(random.choice([1, 1, 1, 2, 2, 3]))
            for _ in range(STAR_COUNT)
        ]

    
    # state management
    def change_state(self, new_state):
        self.state = new_state
        # system cursor only gets in the way of the crosshair
        self.set_mouse_visible(new_state != self.PLAYING)

    def select_player(self):
        clean_name = " ".join(self.name_input.strip().split())

        if not clean_name:
            return

        clean_name = clean_name[:24]

        player = self.db.get_or_create_player(clean_name)

        self.player_id = player["id"]
        self.player_name = player["name"]
        self.high_score = self.db.get_best_score(self.player_id)

        self.start_game()

    def start_game(self):
        self.player.reset()

        self.bullets.clear()
        self.enemies.clear()
        self.powerups.clear()
        self.particles.clear()
        self.shockwaves.clear()
        self.floaters.clear()

        self.score = 0
        self.level = 1
        self.kills = 0
        self.time_alive = 0
        self.best_at_start = self.high_score
        self.new_record = False

        self.combo = 0
        self.combo_timer = 0

        self.enemy_spawn_timer = INITIAL_SPAWN_INTERVAL
        self.shoot_timer = 0
        self.rapid_fire_timer = 0
        self.spread_timer = 0

        self.shake = 0
        self.flash_timer = 0
        self.banner_timer = 0

        self.change_state(self.PLAYING)

    def finish_game(self):
        self.last_score = self.score
        self.last_level = self.level
        self.last_survival = self.time_alive
        self.new_record = self.score > 0 and self.score > self.best_at_start

        # one last big boom where the ship was
        self.explosion(self.player.x, self.player.y, big=True)
        self.add_shake(14)

        if self.player_id is not None:
            self.db.save_score(
                self.player_id, self.score, self.level, self.time_alive,
            )
            self.high_score = self.db.get_best_score(self.player_id)

        self.change_state(self.GAME_OVER)

 
    # drawing


    def on_draw(self):
        self.clear()
        self.gui_camera.use()

        self.backdrop.draw()

        for star in self.stars:
            star.draw(self.clock)

        if self.state == self.MENU:
            self.draw_menu()
        elif self.state == self.NAME_ENTRY:
            self.draw_name_entry()
        elif self.state == self.LEADERBOARD:
            self.draw_leaderboard()
        elif self.state == self.CONTROLS:
            self.draw_controls()
        else:
            offset_x = random.uniform(-self.shake, self.shake) if self.shake > 0 else 0
            offset_y = random.uniform(-self.shake, self.shake) if self.shake > 0 else 0

            self.world_camera.position = (
                SCREEN_WIDTH / 2 + offset_x,
                SCREEN_HEIGHT / 2 + offset_y,
            )
            self.world_camera.use()
            self.draw_world()

            self.gui_camera.use()
            self.draw_screen_fx()
            self.draw_hud()
            self.draw_banner()

            if self.state == self.PLAYING:
                self.draw_crosshair()
            elif self.state == self.PAUSED:
                self.draw_pause()
            elif self.state == self.GAME_OVER:
                self.draw_game_over()

    def draw_world(self):
        for wave in self.shockwaves:
            wave.draw()

        for particle in self.particles:
            particle.draw()

        for powerup in self.powerups:
            powerup.draw()

        for bullet in self.bullets:
            bullet.draw()

        for enemy in self.enemies:
            enemy.draw()

        if self.player.health > 0:
            self.player.draw(self.clock)

        for floater in self.floaters:
            floater.draw()

    # ---------------- menu ----------------

    def draw_menu(self):
        center_x = SCREEN_WIDTH / 2
        pulse = 0.5 + 0.5 * math.sin(self.clock * 2)

        # ship hovering above the title
        bob = math.sin(self.clock * 1.6) * 6
        draw_player_ship(center_x, 640 + bob, 90, 0.7 + 0.3 * pulse, 0.9)

        # fake glow/shadow for the title, same text drawn twice
        text("SPACE DEFENDER", center_x + 3, 537, (0, 160, 255, 140), 46,
             anchor_x="center", bold=True)
        text("SPACE DEFENDER", center_x, 540, WHITE, 46,
             anchor_x="center", bold=True)

        text("ARCADE EDITION", center_x, 505, CYAN, 14,
             anchor_x="center", bold=True)

        if self.player_name:
            text(f"PLAYER  {self.player_name}", center_x, 465, GRAY, 15,
                 anchor_x="center")

        start_y = 385
        spacing = 62

        for index, item in enumerate(self.menu_items):
            selected = index == self.menu_index
            y = start_y - index * spacing

            if selected:
                draw_glow(center_x, y + 13, 130, CYAN, 8, 2)
                arcade.draw_lrbt_rectangle_filled(
                    330, 770, y - 12, y + 38, (15, 70, 105, 220),
                )
                arcade.draw_lrbt_rectangle_outline(
                    330, 770, y - 12, y + 38, (0, 220, 255, 180), 2,
                )
                text(">", 355 + pulse * 6, y, CYAN, 22, anchor_y="center", bold=True)

            text(
                item, center_x, y,
                CYAN if selected else GRAY,
                22, anchor_x="center", anchor_y="center", bold=selected,
            )

        text("UP / DOWN  select        ENTER  confirm", center_x, 60, GRAY, 13,
             anchor_x="center")

    # ---------------- name entry ----------------

    def draw_name_entry(self):
        center_x = SCREEN_WIDTH / 2

        text("PLAYER PROFILE", center_x, 500, WHITE, 36,
             anchor_x="center", bold=True)
        text("ENTER YOUR NAME", center_x, 445, CYAN, 16,
             anchor_x="center", bold=True)

        draw_glow(center_x, 362, 200, CYAN, 6, 2)
        arcade.draw_lrbt_rectangle_filled(300, 800, 330, 395, (8, 15, 32, 230))
        arcade.draw_lrbt_rectangle_outline(300, 800, 330, 395, CYAN, 2)

        cursor = "_" if int(self.clock * 2) % 2 == 0 else ""
        text(self.name_input + cursor, 330, 352, WHITE, 24)

        text("Type your name, BACKSPACE to delete", center_x, 275, GRAY, 13,
             anchor_x="center")
        text("Use the same name again to keep your best score", center_x, 250,
             (120, 135, 160), 12, anchor_x="center")

        text("ENTER  start game", center_x, 205, YELLOW, 17,
             anchor_x="center", bold=True)
        text("ESC  back", center_x, 172, GRAY, 13, anchor_x="center")

    # ---------------- leaderboard ----------------

    def draw_leaderboard(self):
        center_x = SCREEN_WIDTH / 2

        text("LEADERBOARD", center_x, 570, WHITE, 38,
             anchor_x="center", bold=True)
        text("TOP PILOTS", center_x, 535, CYAN, 13, anchor_x="center")

        arcade.draw_lrbt_rectangle_filled(215, 885, 95, 505, (6, 12, 28, 215))
        arcade.draw_lrbt_rectangle_outline(215, 885, 95, 505, (0, 220, 255, 140), 2)

        if not self.leaderboard_rows:
            text("No scores recorded yet.", center_x, 300, GRAY, 18,
                 anchor_x="center")
        else:
            header_y = 470

            for label, x in (("#", 245), ("PLAYER", 305), ("SCORE", 620),
                             ("LEVEL", 740), ("TIME", 820)):
                text(label, x, header_y, CYAN, 14, bold=True)

            medals = {1: (255, 215, 80), 2: (205, 210, 220), 3: (215, 140, 80)}

            for index, row in enumerate(self.leaderboard_rows, start=1):
                y = header_y - index * 36
                is_me = row["name"].lower() == self.player_name.lower()

                if is_me:
                    arcade.draw_lrbt_rectangle_filled(
                        225, 875, y - 9, y + 24, (0, 160, 220, 45),
                    )
                elif index % 2 == 0:
                    arcade.draw_lrbt_rectangle_filled(
                        225, 875, y - 9, y + 24, (255, 255, 255, 10),
                    )

                rank_color = medals.get(index, WHITE)

                text(str(index), 245, y, rank_color, 15, bold=index <= 3)
                text(row["name"][:22], 305, y, CYAN if is_me else WHITE, 15)
                text(str(row["score"]), 620, y, YELLOW, 15, bold=True)
                text(str(row["level"]), 740, y, GRAY, 15)
                text(f"{row['survival_seconds']:.1f}s", 820, y, GRAY, 15)

        text("ESC  back to menu", center_x, 55, GRAY, 13, anchor_x="center")

    # ---------------- controls ----------------

    def draw_controls(self):
        center_x = SCREEN_WIDTH / 2

        text("CONTROLS", center_x, 585, WHITE, 38, anchor_x="center", bold=True)

        controls = [
            ("ARROWS / WASD", "Move"),
            ("MOUSE", "Aim"),
            ("SPACE / CLICK", "Fire"),
            ("SHIFT", "Dash (short i-frames)"),
            ("P", "Pause / resume"),
            ("ESC", "Back / menu"),
        ]

        y = 490

        for key_name, action in controls:
            width = len(key_name) * 11 + 30

            arcade.draw_lrbt_rectangle_filled(
                300 - width / 2, 300 + width / 2, y - 16, y + 18, (15, 25, 48),
            )
            arcade.draw_lrbt_rectangle_outline(
                300 - width / 2, 300 + width / 2, y - 16, y + 18, YELLOW, 2,
            )
            text(key_name, 300, y, YELLOW, 14, anchor_x="center",
                 anchor_y="center", bold=True)
            text(action, 440, y, WHITE, 16, anchor_y="center")

            y -= 56

        text("POWER-UPS", 790, 535, CYAN, 16, anchor_x="center", bold=True)

        y = 480

        for kind in ("health", "rapid", "shield", "spread"):
            color, name, desc = POWERUP_INFO[kind]

            draw_glow(660, y, 16, color, 40, 2)
            arcade.draw_circle_filled(660, y, 18, (10, 16, 30))
            arcade.draw_circle_outline(660, y, 18, color, 2)
            draw_powerup_icon(kind, 660, y)

            text(name, 700, y + 4, color, 14, bold=True)
            text(desc, 700, y - 16, GRAY, 12)

            y -= 66

        text("Kills in quick succession build a combo multiplier.",
             center_x, 110, GRAY, 12, anchor_x="center")
        text("ESC  back to menu", center_x, 65, CYAN, 13, anchor_x="center")

    # ---------------- in game ----------------

    def draw_crosshair(self):
        x = self.mouse_x
        y = self.mouse_y

        firing = arcade.key.SPACE in self.keys or self.mouse_down
        radius = 13 if firing else 10

        arcade.draw_circle_outline(x, y, radius, CYAN, 2)
        arcade.draw_circle_filled(x, y, 1.5, WHITE)

        arcade.draw_line(x - 19, y, x - 6, y, CYAN, 1)
        arcade.draw_line(x + 6, y, x + 19, y, CYAN, 1)
        arcade.draw_line(x, y - 19, x, y - 6, CYAN, 1)
        arcade.draw_line(x, y + 6, x, y + 19, CYAN, 1)

    def draw_screen_fx(self):
        # red flash when you take a hit
        if self.flash_timer > 0:
            arcade.draw_lrbt_rectangle_filled(
                0, SCREEN_WIDTH, 0, SCREEN_HEIGHT,
                (255, 0, 0, int(100 * self.flash_timer / 0.35)),
            )

        # pulsing red edge when hull is low
        if 0 < self.player.health <= 30 and self.state == self.PLAYING:
            pulse = 0.5 + 0.5 * math.sin(self.clock * 8)
            alpha = int(40 + 70 * pulse)
            edge = 14

            arcade.draw_lrbt_rectangle_filled(0, SCREEN_WIDTH, 0, edge, (255, 0, 0, alpha))
            arcade.draw_lrbt_rectangle_filled(0, SCREEN_WIDTH, SCREEN_HEIGHT - edge, SCREEN_HEIGHT, (255, 0, 0, alpha))
            arcade.draw_lrbt_rectangle_filled(0, edge, 0, SCREEN_HEIGHT, (255, 0, 0, alpha))
            arcade.draw_lrbt_rectangle_filled(SCREEN_WIDTH - edge, SCREEN_WIDTH, 0, SCREEN_HEIGHT, (255, 0, 0, alpha))

    def draw_stat(self, label, value, x, color=WHITE):
        text(label, x, SCREEN_HEIGHT - 26, (120, 140, 170), 10, bold=True)
        text(value, x, SCREEN_HEIGHT - 58, color, 22, bold=True)

    def draw_hud(self):
        top = SCREEN_HEIGHT - 72

        arcade.draw_lrbt_rectangle_filled(0, SCREEN_WIDTH, top, SCREEN_HEIGHT, (3, 5, 15, 215))
        arcade.draw_line(0, top, SCREEN_WIDTH, top, (0, 200, 255, 110), 2)

        text(self.player_name.upper(), 25, SCREEN_HEIGHT - 42, CYAN, 15, bold=True)

        self.draw_stat("SCORE", f"{self.score:06d}", 240)
        self.draw_stat("LEVEL", str(self.level), 450, CYAN)
        self.draw_stat("BEST", f"{self.high_score:06d}", 570, GRAY)

        if self.combo >= 2:
            mult = min(5, 1 + self.combo // 5)
            self.draw_stat("COMBO", f"x{mult}  ({self.combo})", 780, ORANGE)

            bar_w = 150
            ratio = max(0, self.combo_timer) / COMBO_WINDOW
            arcade.draw_lrbt_rectangle_filled(780, 780 + bar_w, top + 6, top + 10, (60, 35, 15))
            arcade.draw_lrbt_rectangle_filled(780, 780 + bar_w * ratio, top + 6, top + 10, ORANGE)

        # hull bar, 20 little segments
        text("HULL", 25, 42, WHITE, 11, bold=True)

        health = max(0, self.player.health)
        filled = math.ceil(health / 5)

        if health > 60:
            health_color = GREEN
        elif health > 30:
            health_color = YELLOW
        else:
            health_color = RED

        for i in range(20):
            left = 80 + i * 12
            color = health_color if i < filled else (45, 22, 28)
            arcade.draw_lrbt_rectangle_filled(left, left + 10, 40, 56, color)

        text(f"{health}%", 330, 42, WHITE, 12)

        # dash cooldown
        text("DASH", 25, 20, WHITE, 11, bold=True)

        ready = 1 - max(0, self.player.dash_cooldown) / DASH_COOLDOWN
        arcade.draw_lrbt_rectangle_filled(80, 320, 20, 27, (20, 35, 50))
        arcade.draw_lrbt_rectangle_filled(
            80, 80 + 240 * ready, 20, 27,
            CYAN if ready >= 1 else (0, 120, 160),
        )

        # active buffs, bottom right
        effects = []

        if self.player.shield:
            effects.append(("SHIELD", 1.0, BLUE))
        if self.rapid_fire_timer > 0:
            effects.append(("RAPID", self.rapid_fire_timer / RAPID_DURATION, YELLOW))
        if self.spread_timer > 0:
            effects.append(("SPREAD", self.spread_timer / SPREAD_DURATION, PINK))

        y = 25

        for label, ratio, color in effects:
            x = SCREEN_WIDTH - 240
            text(label, x, y, color, 12, bold=True)
            arcade.draw_lrbt_rectangle_filled(x + 80, x + 210, y, y + 7, (25, 30, 45))
            arcade.draw_lrbt_rectangle_filled(x + 80, x + 80 + 130 * ratio, y, y + 7, color)
            y += 24

    def draw_banner(self):
        if self.banner_timer <= 0 or self.state != self.PLAYING:
            return

        alpha = int(255 * min(1, self.banner_timer / 0.6))
        y = SCREEN_HEIGHT / 2 + 150

        text(f"LEVEL {self.level}", SCREEN_WIDTH / 2, y,
             (255, 255, 255, alpha), 52, anchor_x="center", bold=True)
        text("they're getting faster...", SCREEN_WIDTH / 2, y - 34,
             (0, 220, 255, alpha), 15, anchor_x="center")

    def draw_pause(self):
        arcade.draw_lrbt_rectangle_filled(0, SCREEN_WIDTH, 0, SCREEN_HEIGHT, (0, 0, 0, 170))

        text("PAUSED", SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 + 20, WHITE, 42,
             anchor_x="center", bold=True)
        text("press P to resume", SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2 - 30, CYAN, 16,
             anchor_x="center")

    def draw_game_over(self):
        arcade.draw_lrbt_rectangle_filled(0, SCREEN_WIDTH, 0, SCREEN_HEIGHT, (0, 0, 0, 195))

        center_x = SCREEN_WIDTH / 2

        arcade.draw_lrbt_rectangle_filled(310, 790, 120, 500, (10, 12, 26, 235))
        arcade.draw_lrbt_rectangle_outline(310, 790, 120, 500, (255, 60, 70, 200), 2)

        text("MISSION FAILED", center_x, 440, RED, 42, anchor_x="center", bold=True)
        text(f"PILOT  {self.player_name}", center_x, 395, CYAN, 17, anchor_x="center")
        text(f"SCORE  {self.last_score}", center_x, 345, WHITE, 28,
             anchor_x="center", bold=True)
        text(f"LEVEL {self.last_level}     SURVIVED {self.last_survival:.1f}s",
             center_x, 308, GRAY, 15, anchor_x="center")

        if self.new_record:
            # blinks so you can't miss it
            if int(self.clock * 3) % 2 == 0:
                text("NEW PERSONAL BEST!", center_x, 262, YELLOW, 20,
                     anchor_x="center", bold=True)
        else:
            text(f"PERSONAL BEST  {self.high_score}", center_x, 262, YELLOW, 17,
                 anchor_x="center", bold=True)

        text("ENTER  play again", center_x, 195, CYAN, 17,
             anchor_x="center", bold=True)
        text("ESC  menu", center_x, 160, GRAY, 13, anchor_x="center")

    # update
    def on_update(self, delta_time):
        self.clock += delta_time

        for star in self.stars:
            star.update(delta_time)

        self.backdrop.update(delta_time)

        if self.state == self.GAME_OVER:
            # let the last explosion finish playing
            self.update_effects(delta_time)
            return

        if self.state != self.PLAYING:
            return

        self.time_alive += delta_time
        player = self.player

        player.update(self.keys, self.mouse_x, self.mouse_y, delta_time)
        self.player_trails()

        self.shoot_timer -= delta_time
        self.rapid_fire_timer = max(0, self.rapid_fire_timer - delta_time)
        self.spread_timer = max(0, self.spread_timer - delta_time)

        if self.combo_timer > 0:
            self.combo_timer -= delta_time

            if self.combo_timer <= 0:
                self.combo = 0

        if arcade.key.SPACE in self.keys or self.mouse_down:
            self.shoot()

        self.enemy_spawn_timer -= delta_time

        if self.enemy_spawn_timer <= 0:
            self.spawn_enemy()
            self.enemy_spawn_timer = max(
                MIN_SPAWN_INTERVAL,
                INITIAL_SPAWN_INTERVAL - self.level * 0.045,
            )

        for bullet in self.bullets[:]:
            bullet.update(delta_time)

            if bullet.is_dead():
                self.bullets.remove(bullet)

        for enemy in self.enemies[:]:
            enemy.update(player.x, player.y, delta_time)

            if enemy.type == Enemy.FAST and random.random() < 0.6:
                self.particles.append(Particle(
                    enemy.x, enemy.y, PURPLE,
                    speed=(5, 30), life=(0.2, 0.35), size=(2, 4), max_alpha=160,
                ))

            for bullet in self.bullets[:]:
                if distance(bullet.x, bullet.y, enemy.x, enemy.y) < bullet.radius + enemy.radius:
                    self.bullets.remove(bullet)

                    enemy.health -= 1
                    enemy.flash = 0.08
                    self.sparks(enemy.x, enemy.y)

                    if enemy.health <= 0:
                        self.destroy_enemy(enemy)

                    break

            if enemy not in self.enemies:
                continue

            if distance(enemy.x, enemy.y, player.x, player.y) < enemy.radius + player.radius:
                damaged = player.take_damage(CONTACT_DAMAGE[enemy.type])

                self.explosion(enemy.x, enemy.y)
                self.enemies.remove(enemy)

                if damaged:
                    self.add_shake(10)
                    self.flash_timer = 0.35
                    self.combo = 0
                    self.combo_timer = 0
                elif player.invincible_timer > 0 and player.dash_timer <= 0:
                    # shield just popped
                    self.shockwaves.append(Shockwave(player.x, player.y, 70, BLUE))
                    self.floaters.append(FloatingText(player.x, player.y + 30, "SHIELD DOWN", BLUE, 14))

                if player.health <= 0:
                    self.finish_game()
                    return

            elif enemy.is_off_screen():
                self.enemies.remove(enemy)

        for powerup in self.powerups[:]:
            powerup.update(delta_time)

            if powerup.y < -50:
                self.powerups.remove(powerup)
                continue

            if distance(powerup.x, powerup.y, player.x, player.y) < powerup.radius + player.radius:
                self.collect_powerup(powerup)

        self.update_effects(delta_time)

    def update_effects(self, delta_time):
        for particle in self.particles[:]:
            particle.update(delta_time)

            if particle.life <= 0:
                self.particles.remove(particle)

        # keep the list sane if things get really chaotic
        if len(self.particles) > 600:
            del self.particles[:len(self.particles) - 600]

        for wave in self.shockwaves[:]:
            wave.update(delta_time)

            if wave.life <= 0:
                self.shockwaves.remove(wave)

        for floater in self.floaters[:]:
            floater.update(delta_time)

            if floater.life <= 0:
                self.floaters.remove(floater)

        self.shake = max(0, self.shake - 40 * delta_time)

        if self.flash_timer > 0:
            self.flash_timer -= delta_time

        if self.banner_timer > 0:
            self.banner_timer -= delta_time

  
    # gameplay helpers

    def add_shake(self, amount):
        self.shake = max(self.shake, amount)

    def player_trails(self):
        player = self.player
        back = math.radians(player.angle + 180)

        if player.moving and random.random() < 0.8:
            tail_x = player.x + math.cos(back) * 20
            tail_y = player.y + math.sin(back) * 20

            self.particles.append(Particle(
                tail_x, tail_y, ORANGE,
                speed=(60, 140), life=(0.15, 0.3), size=(2, 4),
                angle=back, spread=0.5, max_alpha=200,
            ))

        if player.dash_timer > 0:
            # afterimage while dashing
            self.particles.append(Particle(
                player.x, player.y, CYAN,
                speed=(0, 10), life=(0.25, 0.35), size=(14, 18), max_alpha=70,
            ))

    def spawn_enemy(self):
        roll = random.random()

        tank_chance = 0 if self.level < 3 else min(0.15, 0.03 * (self.level - 2))
        fast_chance = min(0.35, 0.08 + self.level * 0.015)

        if roll < tank_chance:
            enemy_type = Enemy.TANK
        elif roll < tank_chance + fast_chance:
            enemy_type = Enemy.FAST
        else:
            enemy_type = Enemy.NORMAL

        self.enemies.append(Enemy(enemy_type, self.level))

    def shoot(self):
        if self.shoot_timer > 0:
            return

        player = self.player
        radians = math.radians(player.angle)
        muzzle = 32

        bullet_x = player.x + math.cos(radians) * muzzle
        bullet_y = player.y + math.sin(radians) * muzzle

        if self.spread_timer > 0:
            offsets = (-12, 0, 12)
            color = PINK
        else:
            offsets = (0,)
            color = (90, 230, 255) if self.rapid_fire_timer > 0 else YELLOW

        for offset in offsets:
            self.bullets.append(Bullet(bullet_x, bullet_y, player.angle + offset, color))

        # tiny muzzle flash
        for _ in range(3):
            self.particles.append(Particle(
                bullet_x, bullet_y, color,
                speed=(80, 200), life=(0.08, 0.16), size=(2, 3),
                angle=radians, spread=0.8, max_alpha=220,
            ))

        self.shoot_timer = (
            RAPID_FIRE_RATE if self.rapid_fire_timer > 0 else NORMAL_FIRE_RATE
        )

    def destroy_enemy(self, enemy):
        if enemy not in self.enemies:
            return

        self.enemies.remove(enemy)

        # combo: kill again inside the window and the chain keeps going
        if self.combo_timer > 0:
            self.combo += 1
        else:
            self.combo = 1

        self.combo_timer = COMBO_WINDOW

        multiplier = min(5, 1 + self.combo // 5)
        points = POINTS[enemy.type] * multiplier

        self.score += points
        self.kills += 1
        self.high_score = max(self.high_score, self.score)

        self.floaters.append(FloatingText(
            enemy.x, enemy.y, f"+{points}",
            ORANGE if enemy.type == Enemy.TANK else YELLOW,
            20 if enemy.type == Enemy.TANK else 15,
        ))

        self.explosion(enemy.x, enemy.y, big=enemy.type == Enemy.TANK)

        new_level = self.kills // KILLS_PER_LEVEL + 1

        if new_level > self.level:
            self.level = new_level
            self.banner_timer = 2.2

        drop_chance = 0.6 if enemy.type == Enemy.TANK else POWERUP_DROP_CHANCE

        if random.random() < drop_chance:
            kind = random.choice([
                PowerUp.HEALTH, PowerUp.RAPID, PowerUp.SHIELD, PowerUp.SPREAD,
            ])
            self.powerups.append(PowerUp(enemy.x, enemy.y, kind))

    def explosion(self, x, y, big=False):
        count = PARTICLES_PER_EXPLOSION * (2 if big else 1)

        for _ in range(count):
            self.particles.append(Particle(
                x, y,
                random.choice([ORANGE, YELLOW, RED]),
                speed=(50, 300 if big else 220),
                size=(2, 6 if big else 5),
            ))

        # bright core flash
        self.particles.append(Particle(
            x, y, WHITE, speed=(0, 20), life=(0.12, 0.18),
            size=(14, 20) if big else (9, 13), max_alpha=230,
        ))

        self.shockwaves.append(Shockwave(x, y, 90 if big else 50, ORANGE))
        self.add_shake(7 if big else 3)

    def sparks(self, x, y):
        for _ in range(5):
            self.particles.append(Particle(
                x, y, YELLOW, speed=(60, 200), life=(0.1, 0.25), size=(1.5, 3),
            ))

    def collect_powerup(self, powerup):
        if powerup not in self.powerups:
            return

        self.powerups.remove(powerup)

        color = POWERUP_INFO[powerup.type][0]
        label = POWERUP_INFO[powerup.type][1]

        if powerup.type == PowerUp.HEALTH:
            self.player.health = min(PLAYER_MAX_HEALTH, self.player.health + 30)
            label = "+30 HULL"
        elif powerup.type == PowerUp.RAPID:
            self.rapid_fire_timer = RAPID_DURATION
        elif powerup.type == PowerUp.SHIELD:
            self.player.shield = True
        elif powerup.type == PowerUp.SPREAD:
            self.spread_timer = SPREAD_DURATION

        self.floaters.append(FloatingText(
            self.player.x, self.player.y + 36, label, color, 15,
        ))
        self.shockwaves.append(Shockwave(self.player.x, self.player.y, 55, color))

        for _ in range(10):
            self.particles.append(Particle(self.player.x, self.player.y, color))

   
    # keyboard

    def on_key_press(self, key, modifiers):
        self.keys.add(key)

        if self.state == self.MENU:
            if key in (arcade.key.UP, arcade.key.W):
                self.menu_index = (self.menu_index - 1) % len(self.menu_items)

            elif key in (arcade.key.DOWN, arcade.key.S):
                self.menu_index = (self.menu_index + 1) % len(self.menu_items)

            elif key == arcade.key.ENTER:
                selected = self.menu_items[self.menu_index]

                if selected == "START GAME":
                    self.name_input = self.player_name
                    self.change_state(self.NAME_ENTRY)

                elif selected == "LEADERBOARD":
                    # query once here, not 60 times a second in on_draw
                    self.leaderboard_rows = self.db.get_leaderboard(10)
                    self.change_state(self.LEADERBOARD)

                elif selected == "CONTROLS":
                    self.change_state(self.CONTROLS)

                elif selected == "EXIT":
                    self.close()

            return

        if self.state == self.NAME_ENTRY:
            if key == arcade.key.ENTER:
                self.select_player()
            elif key == arcade.key.BACKSPACE:
                self.name_input = self.name_input[:-1]
            elif key == arcade.key.ESCAPE:
                self.change_state(self.MENU)

            return

        if self.state in (self.LEADERBOARD, self.CONTROLS):
            if key == arcade.key.ESCAPE:
                self.change_state(self.MENU)

            return

        if key == arcade.key.P:
            if self.state == self.PLAYING:
                self.change_state(self.PAUSED)
            elif self.state == self.PAUSED:
                self.change_state(self.PLAYING)

            return

        if self.state == self.PLAYING:
            if key in (arcade.key.LSHIFT, arcade.key.RSHIFT):
                self.player.try_dash()

        elif self.state == self.GAME_OVER:
            if key == arcade.key.ENTER:
                self.start_game()
            elif key == arcade.key.ESCAPE:
                self.change_state(self.MENU)

    def on_key_release(self, key, modifiers):
        self.keys.discard(key)

    def on_text(self, text_input):
        # printable characters, only used on the name screen
        if self.state != self.NAME_ENTRY:
            return

        if text_input in ("\n", "\r"):
            return

        if text_input.isprintable() and len(self.name_input) < 24:
            self.name_input += text_input


    # mouse
    def on_mouse_motion(self, x, y, dx, dy):
        self.mouse_x = x
        self.mouse_y = y

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.mouse_x = x
        self.mouse_y = y

    def on_mouse_press(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.mouse_down = True

    def on_mouse_release(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT:
            self.mouse_down = False


def main():
    SpaceShooter()
    arcade.run()


if __name__ == "__main__":
    main()