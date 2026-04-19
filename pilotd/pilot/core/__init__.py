"""
Agent core. Populated in M1+ by porting from the reference agent — see the
port-vs-rewrite matrix in the private PLAN spec.

Target modules (left intentionally absent at scaffold time):

    agent.py            observe/think/act loop
    vision.py           Anthropic vision + tool-use
    window_capture.py   iPhone Mirroring window capture
    input_simulator.py  CGEvent/cliclick tap/type/swipe
    element_detector.py Set-of-Mark overlay, ScreenGraph
    smart_capture.py    differential region capture
    safety.py           rate/keyword/blocked-app gate
    session.py          per-step recorder
    planner.py          task -> 2..15 steps
    workflow.py         YAML engine, abort_if, on_success
    background_mode.py  background runner
    usage.py            cost tracker
    config.py           config/env overrides
    utils.py            macos version gate, retry helpers
"""
