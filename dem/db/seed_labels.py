"""Display labels for the A-only public Hilbert seed.

The lookup helpers remain generic because manually authored definitions and
theorems use the same services. No bundled theorem catalogue lives here.
"""

from __future__ import annotations

from collections.abc import Callable


AXIOM_NAME_TRANSLATIONS = {
    "hilbert_k": "ヒルベルト公理K",
    "hilbert_s": "ヒルベルト公理S",
    "hilbert_forall_elim": "全称除去公理",
    "hilbert_forall_distribution": "全称分配公理",
    "hilbert_eq_refl": "等号反射律公理",
    "hilbert_eq_subst": "等号代入公理",
    "hilbert_forall_const_intro": "定数命題の全称導入公理",
    "hilbert_peirce": "パース公理",
}

AXIOM_SYSTEM_NAME_TRANSLATIONS = {
    "hilbert_core": "ヒルベルト体系（コア）",
    "hilbert_classical": "ヒルベルト体系（古典）",
}

THEOREM_NAME_TRANSLATIONS: dict[str, str] = {}


def definition_axiom_name(name: str) -> str:
    return f"{name} 定義公理"


def seed_axiom_name(name: str) -> str:
    if name.endswith(" axiom"):
        return definition_axiom_name(name.removesuffix(" axiom"))
    return AXIOM_NAME_TRANSLATIONS.get(name, name)


def seed_axiom_system_name(name: str) -> str:
    return AXIOM_SYSTEM_NAME_TRANSLATIONS.get(name, name)


def seed_theorem_name(name: str) -> str:
    return THEOREM_NAME_TRANSLATIONS.get(name, name)


def axiom_lookup_names(name: str) -> tuple[str, ...]:
    return _lookup_names(name, AXIOM_NAME_TRANSLATIONS, seed_axiom_name)


def axiom_system_lookup_names(name: str) -> tuple[str, ...]:
    return _lookup_names(name, AXIOM_SYSTEM_NAME_TRANSLATIONS, seed_axiom_system_name)


def theorem_lookup_names(name: str) -> tuple[str, ...]:
    return (name, seed_theorem_name(name))


def axiom_formula_remark(name: str) -> str:
    return f"{seed_axiom_name(name)}の論理式"


def theorem_conclusion_formula_remark(name: str) -> str:
    return f"{seed_theorem_name(name)}の結論"


def theorem_premise_formula_remark(name: str, index: int | None = None) -> str:
    suffix = "" if index is None else f"{index + 1}"
    return f"{seed_theorem_name(name)}の前提{suffix}"


def definition_body_formula_remark(name: str) -> str:
    return f"{name} の定義本体"


def definition_axiom_formula_remark(name: str) -> str:
    return f"{name} の定義公理式"


def seed_proof_name(theorem_name: str) -> str:
    return f"{seed_theorem_name(theorem_name)}のシード証明"


def _lookup_names(
    name: str,
    translations: dict[str, str],
    localize: Callable[[str], str],
) -> tuple[str, ...]:
    names = {name, localize(name)}
    for old_name, new_name in translations.items():
        if name == new_name:
            names.add(old_name)
    if name.endswith(" axiom"):
        names.add(definition_axiom_name(name.removesuffix(" axiom")))
    elif name.endswith(" 定義公理"):
        names.add(f"{name.removesuffix(' 定義公理')} axiom")
    return tuple(names)
