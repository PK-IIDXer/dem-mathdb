from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models.tag import AxiomTag, DefinitionTag, Tag, TheoremTag
from dem.db.ordering import utf8_sort_key
from dem.errors import NotFoundError, ValidationError

# entity_kind -> (junction model, its FK column name pointing at the tagged entity)
_JUNCTION_MODELS: dict[str, tuple[type, str]] = {
    "axiom": (AxiomTag, "axiom_id"),
    "theorem": (TheoremTag, "theorem_id"),
    "definition": (DefinitionTag, "definition_id"),
}


class TagService:
    """Flat tag CRUD plus attach/detach against axioms, theorems, and
    definitions. "Field" tags (集合論, 論理学, ...) are just tags by
    convention -- there is no separate schema concept for them."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(self, name: str) -> Tag:
        name = name.strip()
        if not name:
            raise ValidationError("tag name must not be empty")
        existing = self._session.scalar(select(Tag).where(Tag.name == name))
        if existing is not None:
            return existing
        tag = Tag(name=name)
        self._session.add(tag)
        self._session.flush()
        return tag

    def get(self, id: int) -> Tag:
        row = self._session.get(Tag, id)
        if row is None:
            raise NotFoundError("Tag", id)
        return row

    def list_all(self) -> list[Tag]:
        return list(
            self._session.scalars(
                select(Tag).order_by(utf8_sort_key(Tag.name), Tag.id)
            )
        )

    def attach(self, entity_kind: str, entity_id: int, tag_id: int) -> None:
        model, fk_name = self._junction(entity_kind)
        self.get(tag_id)
        existing = self._session.get(model, {fk_name: entity_id, "tag_id": tag_id})
        if existing is None:
            self._session.add(model(**{fk_name: entity_id, "tag_id": tag_id}))
            self._session.flush()

    def detach(self, entity_kind: str, entity_id: int, tag_id: int) -> None:
        model, fk_name = self._junction(entity_kind)
        existing = self._session.get(model, {fk_name: entity_id, "tag_id": tag_id})
        if existing is not None:
            self._session.delete(existing)
            self._session.flush()

    def list_for(self, entity_kind: str, entity_id: int) -> list[Tag]:
        model, fk_name = self._junction(entity_kind)
        rows = self._session.scalars(
            select(Tag)
            .join(model, model.tag_id == Tag.id)
            .where(getattr(model, fk_name) == entity_id)
            .order_by(utf8_sort_key(Tag.name), Tag.id)
        )
        return list(rows)

    def _junction(self, entity_kind: str) -> tuple[type, str]:
        if entity_kind not in _JUNCTION_MODELS:
            raise ValidationError(f"unknown taggable entity kind: {entity_kind!r}")
        return _JUNCTION_MODELS[entity_kind]
