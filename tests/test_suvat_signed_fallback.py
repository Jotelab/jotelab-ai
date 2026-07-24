"""Signed-fallback root selection for SUVAT (spec 2026-07-24)."""

import sympy

from templates.suvat import a, root_select, s, t, u, v


def test_lone_negative_v_accepted_at_medium():
    assert root_select([sympy.Integer(-8)], v, "medium") == -8


def test_lone_negative_s_accepted_at_hard():
    assert root_select([sympy.Integer(-150)], s, "hard") == -150


def test_lone_negative_a_accepted_at_medium():
    assert root_select([sympy.Integer(-10)], a, "medium") == -10


def test_negative_rejected_at_easy():
    assert root_select([sympy.Integer(-8)], v, "easy") is None


def test_negative_t_always_rejected():
    assert root_select([sympy.Integer(-3)], t, "medium") is None


def test_negative_u_not_eligible():
    # u is not a signed-fallback variable (a launch speed's sign is a
    # narrative choice, not a solved direction).
    assert root_select([sympy.Integer(-5)], u, "medium") is None


def test_positive_root_still_wins_over_negative():
    assert root_select([sympy.Integer(-8), sympy.Integer(3)], v, "medium") == 3


def test_smallest_magnitude_negative_picked():
    assert root_select([sympy.Integer(-8), sympy.Integer(-3)], v, "medium") == -3


def test_speed_cap_still_applies_to_negative_v():
    assert root_select([sympy.Integer(-500)], v, "medium") is None
