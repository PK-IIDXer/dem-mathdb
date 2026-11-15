"""Checked logic-only proofs for the public unique-existence quantifier."""

from dem.db.seeds.public_relation_definitions import register_definitions
from dem.db.seeds.public_relations_data import STATEMENTS
from dem.db.seeds.public_set_tools import Builder, completed
from dem.services.definition import DefinitionService


PACKAGE = "unique-existence"
STATEMENTS = STATEMENTS[:4]
THEOREM_NAMES = tuple(name for name, _ in STATEMENTS)


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

        def finish(index, assumptions, result):
            for assumption in reversed(assumptions):
                result = self.close(assumption, result)
            name, statement = STATEMENTS[index]
            self.finish(name, self.parse(statement))
            self.start()

        unique = self.quant("∃!", "x", predicate("x"))
        exists = self.some("x", predicate("x"))
        expanded_body = self.conj(predicate("i"), uniqueness("i"))

        value = self.assume(predicate("t"))
        all_equal = self.assume(uniqueness("t"))
        expanded = self.ei(self.pair(value, all_equal), "i", expanded_body, self.atom("t"))
        finish(0, (value, all_equal), self.iff_out(self.ax(definition_axiom), expanded, True))

        given = self.assume(unique)
        expanded = self.iff_out(self.ax(definition_axiom), given)
        witness = self.assume(expanded_body)
        existence = self.ei(self.left(witness), "i", predicate("i"), self.atom("i"))
        finish(1, (given,), self.ee(expanded, "i", witness, existence))

        given = self.assume(unique)
        sy, st = self.assume(predicate("y")), self.assume(predicate("t"))
        expanded = self.iff_out(self.ax(definition_axiom), given)
        witness = self.assume(expanded_body)
        all_equal = self.right(witness)
        yi = self.mp(self.ui(all_equal, self.atom("y"), "j"), sy)
        ti = self.mp(self.ui(all_equal, self.atom("t"), "j"), st)
        # Transport t = t along t = i, then transport y = i along i = t.
        it = self.transport(ti, self.refl(self.atom("t")), "j", equal("j", "t"))
        yt = self.transport(it, yi, "j", equal("y", "j"))
        finish(2, (given, sy, st), self.ee(expanded, "i", witness, yt))

        existence = self.assume(exists)
        pairwise = self.assume(self.all("x", self.all("y", self.imp(
            predicate("x"), self.imp(predicate("y"), equal("x", "y"))))))
        witness = self.assume(predicate("i"))
        value = self.assume(predicate("x"))
        equality = self.apply(
            self.ui(self.ui(pairwise, self.atom("x"), "j"), self.atom("i"), "j"),
            value, witness,
        )
        all_equal = self.gen(self.close(value, equality), "x")
        introduction = self.cite(THEOREM_NAMES[0], terms={"t": self.atom("i")})
        finish(3, (existence, pairwise), self.ee(
            existence, "i", witness, self.apply(introduction, witness, all_equal),
        ))

