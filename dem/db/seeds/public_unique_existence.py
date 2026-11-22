"""Checked logic-only proofs for the public unique-existence quantifier."""

from dem.db.seeds.public_relation_definitions import register_definitions
from dem.db.seeds.public_relations_data import STATEMENTS
from dem.db.seeds.public_set_tools import Builder, completed
from dem.services.definition import DefinitionService


PACKAGE = "unique-existence"
STATEMENTS = STATEMENTS[:4]
THEOREM_NAMES = tuple(name for name, _, _ in STATEMENTS)


def seed_public_unique_existence(session):
    definitions = DefinitionService(session)
    if completed(session, THEOREM_NAMES, ("∃! 定義公理",), (), ("∃!",)):
        return
    register_definitions(session, PACKAGE)
    axiom = definitions.get_axiom(definitions.get_by_name("∃!").id)
    proofs = UniqueExistenceProofs(session, PACKAGE)
    proofs.seed(axiom.name)


class UniqueExistenceProofs(Builder):
    substitution_variables = ("i", "j", "l")

    def seed(self, definition_axiom):
        def predicate(variable):
            return self.op("φ¹", self.atom(variable))

        def equal(left, right):
            return self.eq(self.atom(left), self.atom(right))

        def uniqueness(witness):
            return self.all("x", self.imp(predicate("x"), equal("x", witness)))

        def start(index):
            return self.start(tuple(map(self.parse, STATEMENTS[index][1])))

        def finish(index):
            name, premises, conclusion = STATEMENTS[index]
            self.finish(name, self.parse(conclusion), premises=tuple(map(self.parse, premises)))

        expanded_body = self.conj(predicate("i"), uniqueness("i"))

        value, all_equal = start(0)
        expanded = self.ei(self.pair(value, all_equal), "i", expanded_body, self.atom("t"))
        self.iff_out(self.ax(definition_axiom), expanded, True)
        finish(0)

        given, = start(1)
        expanded = self.iff_out(self.ax(definition_axiom), given)
        witness = self.assume(expanded_body)
        existence = self.ei(self.left(witness), "i", predicate("i"), self.atom("i"))
        self.ee(expanded, "i", witness, existence)
        finish(1)

        given, sy, st = start(2)
        expanded = self.iff_out(self.ax(definition_axiom), given)
        witness = self.assume(expanded_body)
        all_equal = self.right(witness)
        yi = self.mp(self.ui(all_equal, self.atom("y"), "j"), sy)
        ti = self.mp(self.ui(all_equal, self.atom("t"), "j"), st)
        # Transport t = t along t = i, then transport y = i along i = t.
        it = self.transport(ti, self.refl(self.atom("t")), "j", equal("j", "t"))
        yt = self.transport(it, yi, "j", equal("y", "j"))
        self.ee(expanded, "i", witness, yt)
        finish(2)

        existence, pairwise = start(3)
        witness = self.assume(predicate("i"))
        value = self.assume(predicate("x"))
        equality = self.apply(
            self.ui(self.ui(pairwise, self.atom("x"), "j"), self.atom("i"), "j"),
            value, witness,
        )
        all_equal = self.gen(self.close(value, equality), "x")
        introduction = self.cite(THEOREM_NAMES[0], terms={"t": self.atom("i")},
                                 args=(witness, all_equal))
        self.ee(existence, "i", witness, introduction)
        finish(3)
