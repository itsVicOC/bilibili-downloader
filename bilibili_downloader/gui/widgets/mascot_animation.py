"""Clock-injected, Qt-independent animation timing for Xiao Liu."""

from dataclasses import dataclass
from datetime import datetime
from random import Random
from time import monotonic

FRAME_SIZE = 40
FRAME_DURATIONS = (1600, 650, 80, 120, 80, 1470)
ACTION_DURATIONS = (180, 260, 420, 420, 420, 420, 260, 180)


@dataclass(frozen=True)
class AnimationClip:
    key: str
    name: str
    durations: tuple[int, ...]

    @property
    def asset(self):
        return f"xiaoliu_{self.key}.png"


CLIPS = {
    key: AnimationClip(key, name, durations)
    for key, name, durations in (
        ("idle", "轻待机", FRAME_DURATIONS),
        ("wave", "挥手", ACTION_DURATIONS),
        ("stretch", "伸懒腰", ACTION_DURATIONS),
        ("tiptoe", "踮脚张望", ACTION_DURATIONS),
        ("hop", "小跳", ACTION_DURATIONS),
        ("cheer", "加油", ACTION_DURATIONS),
        ("read", "翻书", ACTION_DURATIONS),
        ("sip", "喝饮料", ACTION_DURATIONS),
        ("dance", "碎步轻舞", ACTION_DURATIONS),
        ("stargaze", "看星星", ACTION_DURATIONS),
        ("yawn", "打哈欠", ACTION_DURATIONS),
        ("doze", "抱膝打盹", (200, 500, 1000, 1000, 1000, 1000, 1000, 300)),
    )
}


@dataclass(frozen=True)
class DayPeriod:
    key: str
    name: str
    caption: str
    actions: tuple[str, ...]


PERIODS = (
    DayPeriod("morning", "清晨", "早安，元气出发", ("stretch", "wave", "tiptoe")),
    DayPeriod("day", "上午", "专注收藏，一起加油", ("cheer", "hop", "read")),
    DayPeriod("afternoon", "午后", "午后时光，慢慢来吧", ("sip", "stretch", "read")),
    DayPeriod("evening", "傍晚", "星光亮起，陪你收藏", ("stargaze", "dance", "wave")),
    DayPeriod("night", "深夜", "夜深啦，记得休息", ("yawn", "doze", "stargaze")),
)


def period_for(when: datetime) -> DayPeriod:
    """Use the supplied local wall clock, including local timezone changes."""
    for end_hour, period in zip((9, 12, 18, 23), PERIODS):
        if 5 <= when.hour < end_hour:
            return period
    return PERIODS[-1]


class AnimationPlayer:
    """Advance one painted frame at a time; never catch up missed animations."""

    def __init__(self, available, *, now=None, clock=None, rng=None):
        self.available = frozenset(available) & CLIPS.keys()
        self.now = now or datetime.now
        self.clock = clock or monotonic
        self.rng = rng if rng is not None else Random()
        self.period = period_for(self.now())
        self.clip = "idle"
        self.frame_index = 0
        self.remaining_ms = float(FRAME_DURATIONS[0])
        self.idle_remaining_ms = None
        self.running = False
        self._started = False
        self._last_tick = None
        self._bag = []
        self._last_action = None

    @property
    def durations(self):
        return CLIPS[self.clip].durations

    @property
    def delay_ms(self):
        delay = self.remaining_ms
        if self.clip == "idle" and self.idle_remaining_ms is not None:
            delay = min(delay, self.idle_remaining_ms)
        return max(1, round(delay))

    def _consume_elapsed(self):
        current = self.clock()
        elapsed = max(0.0, (current - self._last_tick) * 1000)
        self._last_tick = current
        self.remaining_ms -= elapsed
        if self.clip == "idle" and self.idle_remaining_ms is not None:
            self.idle_remaining_ms -= elapsed

    def _start_clip(self, key):
        self.clip = key
        self.frame_index = 0
        self.remaining_ms = float(self.durations[0])

    def _actions(self):
        return [key for key in self.period.actions if key in self.available]

    def _enter_period(self, period):
        self.period = period
        actions = self._actions()
        self._bag = actions[1:]
        self.rng.shuffle(self._bag)
        self._last_action = actions[0] if actions else None
        self.idle_remaining_ms = None
        self._start_clip(actions[0] if actions else "idle")

    def _next_action(self):
        if not self._bag:
            self._bag = self._actions()
            self.rng.shuffle(self._bag)
            if len(self._bag) > 1 and self._bag[0] == self._last_action:
                self._bag[0], self._bag[1] = self._bag[1], self._bag[0]
        if self._bag:
            self._last_action = self._bag.pop(0)
            self._start_clip(self._last_action)
            self.idle_remaining_ms = None
        else:
            self.idle_remaining_ms = None

    def resume(self):
        if self.running or "idle" not in self.available:
            return
        current = period_for(self.now())
        if not self._started or current != self.period:
            self._enter_period(current)
        self._started = True
        self.running = True
        self._last_tick = self.clock()

    def pause(self):
        if self.running:
            self._consume_elapsed()
        self.running = False
        self._last_tick = None

    def tick(self):
        if not self.running:
            return
        self._consume_elapsed()
        current = period_for(self.now())
        if self.clip == "idle" and current != self.period:
            self._enter_period(current)
        elif self.clip == "idle" and self.idle_remaining_ms is not None and self.idle_remaining_ms <= 0:
            self._next_action()
        elif self.remaining_ms <= 0:
            if self.frame_index + 1 < len(self.durations):
                self.frame_index += 1
                self.remaining_ms = float(self.durations[self.frame_index])
            elif current != self.period:
                self._enter_period(current)
            else:
                self._start_clip("idle")
                # Repeated idle loops retain the same visible-time deadline.
                if self.idle_remaining_ms is None and self._actions():
                    self.idle_remaining_ms = float(self.rng.randint(15000, 30000))
