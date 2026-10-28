"""State restoration and the Starlette private storage contract."""
from itertools import permutations

import pytest
from starlette.datastructures import State

from beta_state import patch_state


def test_starlette_state_storage_contract():
    backing = {}
    state = State(backing)
    assert object.__getattribute__(state, "_state") is backing
    marker = object()
    state.beta_limits = marker
    assert backing["beta_limits"] is marker
    assert "beta_limits" not in state.__dict__
    backing["beta_limits"] = "replacement"
    assert state.beta_limits == "replacement"
    del state.beta_limits
    assert "beta_limits" not in backing
    with pytest.raises(AttributeError):
        getattr(state, "beta_limits")


@pytest.mark.parametrize("present", [False, True])
def test_restore_original_state(request, present):
    original, replacement = object(), object()
    state = State({"beta_limits": original} if present else {})
    undo = patch_state(state, "beta_limits", replacement)
    request.addfinalizer(undo)
    assert state.beta_limits is replacement
    undo()
    undo()  # Explicit cleanup and a later fixture finalizer are both safe.
    if present:
        assert state.beta_limits is original
    else:
        assert not hasattr(state, "beta_limits")


@pytest.mark.parametrize("order", list(permutations(range(3))))
@pytest.mark.parametrize("present", [False, True])
def test_overlapping_fixture_teardown_orders(request, order, present):
    original = object()
    state = State({"beta_limits": original} if present else {})
    values = [object() for _ in range(3)]
    undos = [patch_state(state, "beta_limits", value) for value in values]
    for undo in undos:
        request.addfinalizer(undo)
    active = list(range(3))
    for index in order:
        undos[index]()
        active.remove(index)
        if active:
            assert state.beta_limits is values[active[-1]]
        elif present:
            assert state.beta_limits is original
        else:
            assert not hasattr(state, "beta_limits")


def test_separate_keys_and_state_objects(request):
    first, second = State(), State()
    undos = [patch_state(first, "a", 1), patch_state(first, "b", 2),
             patch_state(second, "a", 3)]
    for undo in undos:
        request.addfinalizer(undo)
    undos[0]()
    assert not hasattr(first, "a")
    assert first.b == 2 and second.a == 3
