"""
tests/test_cursor_engine.py

Unit-Tests für brain_input/cursor_engine.py.

Wie bei gesture_classifier.py: reine Logiktests mit synthetischen
HandLandmarks, hier zusätzlich mit einer manuell steuerbaren Fake-Uhr
(statt time.monotonic), damit Doppel-Pinch-/Hold-Timing deterministisch
und ohne echte Wartezeit getestet werden kann.
"""

from __future__ import annotations

import pytest

from brain_input.cursor_engine import (
    CursorAction,
    CursorEngine,
    CursorEvent,
    CursorSettings,
    GestureCursorMapper,
)
from brain_input.gesture_classifier import HandLandmarks

WRIST_POS = (0.5, 0.9, 0.0)


class FakeClock:
    """Manuell vorspulbare Uhr für deterministische Zeit-basierte Tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def make_hand(
    index: bool = False,
    middle: bool = False,
    ring: bool = False,
    pinky: bool = False,
    pinching: bool = False,
    thumb_middle_touch: bool = False,
    spread: float = 1.0,
) -> HandLandmarks:
    """Analog zu tests/test_gesture_classifier.py::make_hand, um Duplikation zu vermeiden minimal erweitert."""
    pinch_point = (0.55, 0.5, 0.0)
    thumb_middle_point = (0.5, 0.6, 0.0)

    def finger(extended_flag: bool, base_x: float, override_tip: tuple[float, float, float] | None = None) -> list:
        mcp = (base_x, 0.6, 0.0)
        if override_tip is not None:
            tip = override_tip
        elif extended_flag:
            tip = (base_x, 0.9 - 0.8 * spread, 0.0)
        else:
            tip = (base_x, 0.82, 0.0)
        return [mcp, mcp, mcp, tip]

    points: list = [WRIST_POS]

    if pinching:
        thumb_tip = pinch_point
    elif thumb_middle_touch:
        thumb_tip = thumb_middle_point
    else:
        thumb_tip = (0.35, 0.6, 0.0)
    points += [(0.4, 0.75, 0.0), (0.38, 0.68, 0.0), (0.37, 0.64, 0.0), thumb_tip]

    index_override = pinch_point if pinching else None
    middle_override = thumb_middle_point if thumb_middle_touch else None

    points += finger(index, 0.6, override_tip=index_override)
    points += finger(middle, 0.5, override_tip=middle_override)
    points += finger(ring, 0.4)
    points += finger(pinky, 0.3)

    return HandLandmarks(points=tuple(points))


class FakeController:
    """Zeichnet jeden Aufruf auf, statt echte Mausaktionen auszuführen."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def move_to(self, x_norm: float, y_norm: float) -> None:
        self.calls.append(("move_to", (x_norm, y_norm)))

    def click(self) -> None:
        self.calls.append(("click", ()))

    def double_click(self) -> None:
        self.calls.append(("double_click", ()))

    def right_click(self) -> None:
        self.calls.append(("right_click", ()))

    def mouse_down(self) -> None:
        self.calls.append(("mouse_down", ()))

    def mouse_up(self) -> None:
        self.calls.append(("mouse_up", ()))

    def scroll(self, amount: float) -> None:
        self.calls.append(("scroll", (amount,)))


class TestPinchClick:
    def test_short_pinch_release_triggers_single_click_after_window(self) -> None:
        clock = FakeClock()
        settings = CursorSettings(double_pinch_window_seconds=0.35, pinch_hold_to_drag_seconds=0.30)
        mapper = GestureCursorMapper(settings=settings, clock=clock)


        events = mapper.process_hand(0, make_hand(pinching=True))
        assert events == []


        events = mapper.process_hand(0, make_hand(pinching=False))
        assert events == []


        clock.advance(0.4)
        events = mapper.process_hand(0, make_hand(pinching=False))
        assert events == [CursorEvent(CursorAction.CLICK, 0)]


class TestDoublePinch:
    def test_second_pinch_within_window_triggers_double_click(self) -> None:
        clock = FakeClock()
        mapper = GestureCursorMapper(settings=CursorSettings(double_pinch_window_seconds=0.35), clock=clock)

        mapper.process_hand(0, make_hand(pinching=True))
        mapper.process_hand(0, make_hand(pinching=False))

        clock.advance(0.1)
        events = mapper.process_hand(0, make_hand(pinching=True))
        assert CursorEvent(CursorAction.DOUBLE_CLICK, 0) in events


class TestPinchHoldDrag:
    def test_holding_pinch_past_threshold_starts_drag(self) -> None:
        clock = FakeClock()
        settings = CursorSettings(pinch_hold_to_drag_seconds=0.30)
        mapper = GestureCursorMapper(settings=settings, clock=clock)

        mapper.process_hand(0, make_hand(index=True, pinching=True))

        clock.advance(0.35)
        events = mapper.process_hand(0, make_hand(index=True, pinching=True))
        assert any(e.action == CursorAction.DRAG_START for e in events)

    def test_releasing_after_drag_start_emits_drag_end(self) -> None:
        clock = FakeClock()
        settings = CursorSettings(pinch_hold_to_drag_seconds=0.30)
        mapper = GestureCursorMapper(settings=settings, clock=clock)

        mapper.process_hand(0, make_hand(pinching=True))
        clock.advance(0.35)
        mapper.process_hand(0, make_hand(pinching=True))

        events = mapper.process_hand(0, make_hand(pinching=False))
        assert any(e.action == CursorAction.DRAG_END for e in events)


class TestRightClick:
    def test_thumb_middle_touch_triggers_right_click_once(self) -> None:
        mapper = GestureCursorMapper()

        events_first = mapper.process_hand(0, make_hand(thumb_middle_touch=True))
        assert CursorEvent(CursorAction.RIGHT_CLICK, 0) in events_first


        events_second = mapper.process_hand(0, make_hand(thumb_middle_touch=True))
        assert CursorEvent(CursorAction.RIGHT_CLICK, 0) not in events_second


class TestSpreadZoom:
    def test_spreading_fingers_emits_zoom_in(self) -> None:
        mapper = GestureCursorMapper()
        mapper.process_hand(0, make_hand(index=True, middle=True, ring=True, pinky=True, spread=0.5))
        events = mapper.process_hand(0, make_hand(index=True, middle=True, ring=True, pinky=True, spread=1.0))
        assert any(e.action == CursorAction.ZOOM_IN for e in events)

    def test_closing_fingers_emits_zoom_out(self) -> None:
        mapper = GestureCursorMapper()
        mapper.process_hand(0, make_hand(index=True, middle=True, ring=True, pinky=True, spread=1.0))
        events = mapper.process_hand(0, make_hand(index=True, middle=True, ring=True, pinky=True, spread=0.5))
        assert any(e.action == CursorAction.ZOOM_OUT for e in events)

    def test_stable_open_hand_emits_release_once(self) -> None:
        mapper = GestureCursorMapper()
        mapper.process_hand(0, make_hand(index=True, middle=True, ring=True, pinky=True, spread=1.0))
        mapper.process_hand(0, make_hand(index=True, middle=True, ring=True, pinky=True, spread=1.0))
        events = mapper.process_hand(0, make_hand(index=True, middle=True, ring=True, pinky=True, spread=1.0))
        assert any(e.action == CursorAction.RELEASE for e in events)


class TestFistGrab:
    def test_closed_fist_triggers_grab_once(self) -> None:
        mapper = GestureCursorMapper()
        events_first = mapper.process_hand(0, make_hand())
        assert CursorEvent(CursorAction.GRAB, 0) in events_first

        events_second = mapper.process_hand(0, make_hand())
        assert CursorEvent(CursorAction.GRAB, 0) not in events_second


class TestPrecisionCursor:
    def test_single_index_finger_emits_precision_move(self) -> None:
        mapper = GestureCursorMapper()
        events = mapper.process_hand(0, make_hand(index=True))
        move_events = [e for e in events if e.action == CursorAction.PRECISION_MOVE]
        assert len(move_events) == 1
        assert move_events[0].x is not None and move_events[0].y is not None


class TestCursorEngineDispatch:
    def test_engine_executes_click_on_controller_and_publishes_audit_event(self) -> None:
        clock = FakeClock()
        published: list = []
        controller = FakeController()
        engine = CursorEngine(
            controller=controller,
            publish_callback=published.append,
            mapper=GestureCursorMapper(clock=clock),
        )

        engine.on_hands([make_hand(pinching=True)])
        engine.on_hands([make_hand(pinching=False)])
        clock.advance(0.4)
        engine.on_hands([make_hand(pinching=False)])

        assert ("click", ()) in controller.calls
        assert any(e.payload.get("cursor_action") == "click" for e in published)

    def test_disabled_engine_still_publishes_but_does_not_execute(self) -> None:
        published: list = []
        controller = FakeController()
        engine = CursorEngine(controller=controller, publish_callback=published.append, enabled=False)

        engine.on_hands([make_hand()])

        assert controller.calls == []
        assert any(e.payload.get("cursor_action") == "grab" and e.payload.get("executed") is False for e in published)

    def test_hand_leaving_frame_resets_its_state(self) -> None:
        published: list = []
        controller = FakeController()
        engine = CursorEngine(controller=controller, publish_callback=published.append)

        engine.on_hands([make_hand()])
        engine.on_hands([])
        engine.on_hands([make_hand()])

        grab_calls = [c for c in controller.calls if c[0] == "mouse_down"]
        assert len(grab_calls) == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))