"""Deterministic wall-clock selection and foreground-only scheduling."""

from datetime import datetime, timedelta
from random import Random

import pytest

from bilibili_downloader.gui.widgets.mascot_animation import (
    CLIPS,
    PERIODS,
    AnimationPlayer,
    period_for,
)


class FakeClock:
    def __init__(self, hour=10):
        self.wall = datetime(2026, 10, 21, hour)
        self.seconds = 0.0

    def now(self):
        return self.wall

    def monotonic(self):
        return self.seconds

    def advance(self, milliseconds):
        self.seconds += milliseconds / 1000
        self.wall += timedelta(milliseconds=milliseconds)


def make_player(hour=10, available=CLIPS):
    clock = FakeClock(hour)
    player = AnimationPlayer(available, now=clock.now, clock=clock.monotonic, rng=Random(7))
    player.resume()
    return player, clock


def step(player, clock):
    clock.advance(player.delay_ms + 0.01)
    player.tick()


def finish_action(player, clock):
    for _ in range(20):
        if player.clip == "idle":
            return
        step(player, clock)
    pytest.fail("action failed to finish")


def next_action(player, clock):
    finish_action(player, clock)
    for _ in range(100):
        step(player, clock)
        if player.clip != "idle":
            return player.clip
    pytest.fail("action was never scheduled")


@pytest.mark.parametrize("hour,minute,expected", [
    (0, 0, "night"), (4, 59, "night"), (5, 0, "morning"),
    (8, 59, "morning"), (9, 0, "day"), (11, 59, "day"),
    (12, 0, "afternoon"), (17, 59, "afternoon"),
    (18, 0, "evening"), (22, 59, "evening"),
    (23, 0, "night"), (23, 59, "night"),
])
def test_local_period_boundaries(hour, minute, expected):
    assert period_for(datetime(2026, 10, 21, hour, minute)).key == expected


@pytest.mark.parametrize("hour,period", list(zip((6, 10, 14, 20, 1), PERIODS)))
def test_entry_action_and_shuffle_bag_cover_every_action(hour, period):
    player, clock = make_player(hour)
    assert player.clip == period.actions[0]
    sequence = [player.clip] + [next_action(player, clock) for _ in range(11)]
    assert all(a != b for a, b in zip(sequence, sequence[1:]))
    for start in range(0, len(sequence), 3):
        assert set(sequence[start:start + 3]) == set(period.actions)


def test_idle_deadline_is_15_to_30_seconds_and_survives_idle_loops():
    player, clock = make_player()
    finish_action(player, clock)
    delay = player.idle_remaining_ms
    assert 15000 <= delay <= 30000
    started = clock.seconds
    while player.clip == "idle":
        step(player, clock)
    assert (clock.seconds - started) * 1000 == pytest.approx(delay, abs=2)


def test_pause_preserves_partial_frame_and_idle_wait_without_catchup():
    player, clock = make_player()
    finish_action(player, clock)
    clock.advance(350)
    player.pause()
    remaining = player.remaining_ms
    wait = player.idle_remaining_ms
    clock.advance(24 * 60 * 60 * 1000)
    player.tick()
    player.pause()
    player.resume()
    assert player.clip == "idle"
    assert player.remaining_ms == remaining
    assert player.idle_remaining_ms == wait
    clock.advance(100)
    player.tick()
    assert player.idle_remaining_ms == pytest.approx(wait - 100)


def test_pause_during_action_resumes_same_frame():
    player, clock = make_player()
    clock.advance(70)
    player.pause()
    clock.advance(60000)
    player.resume()
    assert player.clip == "cheer"
    assert player.frame_index == 0
    assert player.remaining_ms == pytest.approx(110)


def test_cross_period_finishes_current_action_then_changes_caption_and_pool():
    player, clock = make_player(8)
    clock.wall = datetime(2026, 10, 21, 9)
    step(player, clock)
    assert player.period.key == "morning"
    assert player.clip == "stretch"
    for _ in range(10):
        if player.period.key == "day":
            break
        step(player, clock)
    assert player.period == PERIODS[1]
    assert player.clip == "cheer"
    assert player.frame_index == 0


def test_resume_in_new_period_discards_old_action_and_wait():
    player, clock = make_player()
    finish_action(player, clock)
    player.pause()
    clock.wall = datetime(2026, 10, 21, 23)
    clock.seconds += 10 * 60 * 60
    player.resume()
    assert player.period.key == "night"
    assert player.clip == "yawn"
    assert player.frame_index == 0
    assert player.idle_remaining_ms is None


def test_midnight_stays_in_night_period_and_clock_change_does_not_skip_frames():
    player, clock = make_player(23)
    clock.wall = datetime(2026, 10, 22, 0)
    player.pause()
    player.resume()
    assert player.clip == "yawn"
    clock.wall = datetime(2026, 10, 21, 4)  # Local timezone/clock moved backwards.
    step(player, clock)
    assert player.period.key == "night"
    assert player.frame_index == 1


def test_idle_rechecks_wall_clock_without_changing_monotonic_wait():
    player, clock = make_player()
    finish_action(player, clock)
    clock.wall = datetime(2026, 10, 21, 6)
    step(player, clock)
    assert player.period.key == "morning"
    assert player.clip == "stretch"


def test_delayed_callback_advances_only_one_frame():
    player, clock = make_player()
    clock.advance(60000)
    player.tick()
    assert player.clip == "cheer"
    assert player.frame_index == 1
    assert player.remaining_ms == player.durations[1]


def test_missing_actions_are_skipped_and_legacy_idle_keeps_running():
    player, clock = make_player(10, ("idle", "read"))
    assert player.clip == "read"
    assert next_action(player, clock) == "read"
    idle, clock = make_player(10, ("idle",))
    assert idle.clip == "idle"
    assert idle.idle_remaining_ms is None
    for _ in range(20):
        step(idle, clock)
    assert idle.clip == "idle"
    static, _ = make_player(10, ())
    assert not static.running
