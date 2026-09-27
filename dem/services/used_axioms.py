"""One definition of the axioms a proof depends on.

`ProofService.list_used_axioms()` answers the question for a single proof and
`AxiomService.list_theorems_provable_in_system()` for every verified proof at
once.  Both read their dependency edges and their defining-axiom filter from
here so that the two cannot start counting dependencies differently
(`docs/design/kernel/trust-boundary.md` §5 rule 5; a third implementation had
already drifted once).

A proof depends on

* every proof it applies in a ``theorem`` step, and
* the existence/uniqueness proof behind every ``function_desc`` definition
  whose defining axiom it cites in an ``axiom`` step -- the symbol exists only
  because that proof does, so its assumptions are assumptions of the citing
  proof,

and it uses every axiom cited by a step of any proof it depends on,
transitively.  Defining axioms themselves are conservative scaffolding rather
than object-theory assumptions, so a system comparison drops them
(`DefinitionAxioms.drop_defining()`).
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from dem.db.models.definition import Definition
from dem.db.models.inference import Axiom
from dem.db.models.theorem import ProofStep

# SQLite caps the parameters of a single statement, so long id lists are sent
# in chunks.  The statement count stays bounded by the number of ids, never by
# the shape of the proof graph.
_ID_CHUNK = 500


def is_defining_axiom(axiom: Axiom) -> bool:
    """Whether this axiom only introduces a defined symbol.

    Such an axiom is conservative over the object theory: it proves nothing
    that is statable without the defined symbol.  Requiring a system to list
    it would make every system that uses a definition look weaker than it is.
    """
    return axiom.definition_id is not None


@dataclass(frozen=True)
class DefinitionAxioms:
    """Which axioms define a symbol, and what each descriptive symbol rests on."""

    defining_axiom_ids: frozenset[int]
    existence_proof_ids: Mapping[int, int]

    def drop_defining(self, axiom_ids: Iterable[int]) -> frozenset[int]:
        return frozenset(
            axiom_id for axiom_id in axiom_ids if axiom_id not in self.defining_axiom_ids
        )

    def existence_proofs_for(self, axiom_ids: Iterable[int]) -> set[int]:
        return {
            proof_id
            for proof_id in (self.existence_proof_ids.get(axiom_id) for axiom_id in axiom_ids)
            if proof_id is not None
        }


def load_definition_axioms(
    session: Session, axiom_ids: Collection[int] | None = None
) -> DefinitionAxioms:
    """Read the defining axioms: all of them, or only the ones given."""
    defining: set[int] = set()
    existence: dict[int, int] = {}
    for chunk in _chunks(axiom_ids):
        stmt = (
            select(Axiom.id, Definition.kind, Definition.existence_uniqueness_proof_id)
            .outerjoin(Definition, Axiom.definition_id == Definition.id)
            .where(Axiom.definition_id.is_not(None))
        )
        if chunk is not None:
            stmt = stmt.where(Axiom.id.in_(chunk))
        for axiom_id, kind, existence_proof_id in session.execute(stmt):
            defining.add(axiom_id)
            if kind == "function_desc" and existence_proof_id is not None:
                existence[axiom_id] = existence_proof_id
    return DefinitionAxioms(frozenset(defining), existence)


@dataclass(frozen=True)
class ProofEdges:
    """The axiom and theorem-application steps of proofs, read as a graph."""

    direct_axiom_ids: Mapping[int, frozenset[int]]
    applied_proof_ids: Mapping[int, frozenset[int]]

    def proof_ids(self) -> set[int]:
        return set(self.direct_axiom_ids) | set(self.applied_proof_ids)

    def reached_proof_ids(
        self, proof_id: int, definition_axioms: DefinitionAxioms
    ) -> frozenset[int]:
        """The proofs this one depends on: the lemmas it applies plus the
        existence proof behind every descriptive symbol it cites."""
        return frozenset(
            self.applied_proof_ids.get(proof_id, frozenset())
            | definition_axioms.existence_proofs_for(
                self.direct_axiom_ids.get(proof_id, frozenset())
            )
        )


def load_proof_edges(session: Session, proof_ids: Collection[int] | None = None) -> ProofEdges:
    """Read the dependency-bearing steps of all proofs, or of the ones given."""
    direct: dict[int, set[int]] = {}
    applied: dict[int, set[int]] = {}
    for chunk in _chunks(proof_ids):
        stmt = select(
            ProofStep.proof_id,
            ProofStep.step_kind,
            ProofStep.axiom_id,
            ProofStep.applied_proof_id,
        ).where(
            or_(
                and_(ProofStep.step_kind == "axiom", ProofStep.axiom_id.is_not(None)),
                and_(
                    ProofStep.step_kind == "theorem",
                    ProofStep.applied_proof_id.is_not(None),
                ),
            )
        )
        if chunk is not None:
            stmt = stmt.where(ProofStep.proof_id.in_(chunk))
        for proof_id, step_kind, axiom_id, applied_proof_id in session.execute(stmt):
            if step_kind == "axiom":
                direct.setdefault(proof_id, set()).add(axiom_id)
            else:
                applied.setdefault(proof_id, set()).add(applied_proof_id)
    return ProofEdges(
        {proof_id: frozenset(ids) for proof_id, ids in direct.items()},
        {proof_id: frozenset(ids) for proof_id, ids in applied.items()},
    )


def used_axiom_ids_for_proof(
    session: Session,
    proof_id: int,
    known: Mapping[int, frozenset[int]] | None = None,
) -> frozenset[int]:
    """The axioms one proof uses, reading one layer of the graph per query.

    `known` maps proof ids to results already computed, so a shared lemma ends
    the walk early (AGENTS.md rule 7)."""
    known = known or {}
    axiom_ids: set[int] = set()
    seen = {proof_id}
    frontier = [proof_id]
    while frontier:
        edges = load_proof_edges(session, frontier)
        definition_axioms = load_definition_axioms(
            session,
            {axiom_id for node in frontier for axiom_id in edges.direct_axiom_ids.get(node, ())},
        )
        next_frontier: list[int] = []
        for node in frontier:
            axiom_ids.update(edges.direct_axiom_ids.get(node, ()))
            for reached in edges.reached_proof_ids(node, definition_axioms):
                if reached in seen:
                    continue
                seen.add(reached)
                cached = known.get(reached)
                if cached is None:
                    next_frontier.append(reached)
                else:
                    axiom_ids.update(cached)
        frontier = next_frontier
    return frozenset(axiom_ids)


def used_axiom_ids_by_proof(
    edges: ProofEdges, definition_axioms: DefinitionAxioms
) -> dict[int, frozenset[int]]:
    """The axioms every proof uses; proofs absent from the result use none.

    The whole graph is already in `edges`, so each proof is evaluated once and
    a lemma shared by many proofs is not re-traversed per citing proof
    (AGENTS.md rule 7).  Strongly connected components are collapsed
    (iterative Tarjan) so a citation cycle cannot make the result depend on
    traversal order."""
    reached = {
        proof_id: edges.reached_proof_ids(proof_id, definition_axioms)
        for proof_id in edges.proof_ids()
    }
    result: dict[int, frozenset[int]] = {}
    index: dict[int, int] = {}
    lowlink: dict[int, int] = {}
    stack: list[int] = []
    on_stack: set[int] = set()
    for root in reached:
        if root in index:
            continue
        work = [(root, iter(reached[root]))]
        index[root] = lowlink[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        while work:
            node, successors = work[-1]
            for successor in successors:
                if successor not in index:
                    index[successor] = lowlink[successor] = len(index)
                    stack.append(successor)
                    on_stack.add(successor)
                    work.append((successor, iter(reached.get(successor, ()))))
                    break
                if successor in on_stack:
                    lowlink[node] = min(lowlink[node], index[successor])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                if lowlink[node] != index[node]:
                    continue
                component: list[int] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                # Tarjan emits components after every component they cite, so
                # successors outside this one are already final.
                axiom_ids: set[int] = set()
                for member in component:
                    axiom_ids.update(edges.direct_axiom_ids.get(member, ()))
                    for successor in reached.get(member, ()):
                        if successor in result:
                            axiom_ids.update(result[successor])
                frozen = frozenset(axiom_ids)
                for member in component:
                    result[member] = frozen
    return result


def _chunks(ids: Collection[int] | None) -> list[list[int] | None]:
    if ids is None:
        return [None]
    ordered = list(ids)
    if not ordered:
        return []
    return [ordered[start : start + _ID_CHUNK] for start in range(0, len(ordered), _ID_CHUNK)]
