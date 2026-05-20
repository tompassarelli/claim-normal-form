"""
Event dispatch system for the helpdesk/CRM application.

Listeners are plain callables registered against string event names.
setup_hooks() bridges the HOOKS dict in config into this system so both
the new event API and the legacy _run_hooks path stay in sync.

Supported event names:
    ticket.created       ticket.updated       ticket.transitioned
    ticket.assigned      ticket.closed        ticket.commented
    ticket.tagged        ticket.deleted
"""

from typing import Any, Callable, Dict, List

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_listeners: Dict[str, List[Callable]] = {}

KNOWN_EVENTS = {
    "ticket.created",
    "ticket.updated",
    "ticket.transitioned",
    "ticket.assigned",
    "ticket.closed",
    "ticket.commented",
    "ticket.tagged",
    "ticket.deleted",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_listener(event_name: str, callback: Callable) -> None:
    """Register *callback* to be called whenever *event_name* is emitted.

    Unknown event names are accepted so that application code can define
    domain-specific events without modifying this module.
    """
    if not callable(callback):
        raise TypeError(f"callback must be callable, got {type(callback)!r}")
    _listeners.setdefault(event_name, []).append(callback)


def emit(event_name: str, **kwargs: Any) -> None:
    """Call every listener registered for *event_name*.

    Passes all keyword arguments through to each callback.  Exceptions
    raised by individual listeners are propagated immediately — callers
    that need fire-and-forget semantics should wrap their listeners in a
    try/except themselves.
    """
    for callback in list(_listeners.get(event_name, [])):
        callback(**kwargs)


# ---------------------------------------------------------------------------
# Legacy hook compatibility
# ---------------------------------------------------------------------------

def _run_hooks(hook_name: str, **kwargs: Any) -> None:
    """Run hooks registered in config.HOOKS under *hook_name*.

    HOOKS values may be either a flat list of callbacks or a dict
    with "pre"/"post" keys mapping to lists. This handles both.
    """
    from config import HOOKS
    entry = HOOKS.get(hook_name, [])
    if isinstance(entry, dict):
        phase = kwargs.pop("_phase", None)
        if phase:
            for fn in entry.get(phase, []):
                fn(**kwargs)
        else:
            for fn in entry.get("pre", []):
                fn(**kwargs)
            for fn in entry.get("post", []):
                fn(**kwargs)
    else:
        for fn in entry:
            fn(**kwargs)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_hooks() -> None:
    """Read config.HOOKS and register each hook as an event listener.

    HOOKS keys are treated as event names directly (e.g. "ticket.created").
    Call this once at application startup after config is fully loaded.
    """
    from config import HOOKS  # imported here to avoid circular import at load time
    for event_name, callbacks in HOOKS.items():
        for cb in callbacks:
            register_listener(event_name, cb)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def reset_events() -> None:
    """Clear all registered listeners.  Intended for use in tests only."""
    _listeners.clear()
