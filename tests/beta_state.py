"""Patch Starlette State without pytest's version-dependent setattr inspection."""

# State attributes live in _state, not __dict__. Work on that storage explicitly;
# test_starlette_state_storage_contract detects changes to this private contract.
_MISSING = object()
_patches = {}


def patch_state(state, name, value):
    """Return an idempotent undo; overlapping fixtures may undo in any order.

    Register the result with request.addfinalizer, so teardown does not depend
    on pytest MonkeyPatch's treatment of proxy attributes or its undo stack.
    """
    backing = object.__getattribute__(state, "_state")
    if not isinstance(backing, dict):
        raise TypeError("Starlette State must store attributes in a dictionary")
    key = (id(backing), name)
    if key not in _patches:
        _patches[key] = (backing, backing.get(name, _MISSING), [])
    storage, original, active = _patches[key]
    entry = (object(), value)
    active.append(entry)
    storage[name] = value
    undone = False

    def undo():
        nonlocal undone
        if undone:
            return
        undone = True
        active.remove(entry)
        if active:
            storage[name] = active[-1][1]
        else:
            del _patches[key]
            if original is _MISSING:
                storage.pop(name, None)
            else:
                storage[name] = original

    return undo
