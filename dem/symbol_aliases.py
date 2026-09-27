"""Built-in parser spellings shared by services and seed migrations."""

BUILTIN_ALIASES: dict[str, str] = {
    r"\forall": "∀",
    "forall": "∀",
    r"\exists": "∃",
    "exists": "∃",
    r"\wedge": "∧",
    "/\\": "∧",
    r"\vee": "∨",
    "\\/": "∨",
    r"\neg": "¬",
    "!": "¬",
    r"\to": "→",
    "->": "→",
    r"\leftrightarrow": "↔",
    "<->": "↔",
}
