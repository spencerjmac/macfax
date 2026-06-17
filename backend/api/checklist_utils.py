"""Shared helpers for Crystal Ball-style championship checklists (NCAA + NBA)."""


def _item(key, label, passed, value, threshold, details=""):
    return {
        "key":       key,
        "label":     label,
        "pass":      passed,
        "value":     value,
        "threshold": threshold,
        "details":   details,
    }
