# Opt-in list pagination

`GET /formulas`, `/theorems`, `/axioms`, `/definitions`, and `/tags` accept:

- `limit`: 1–500 items. Omit both `limit` and `cursor` to keep the existing full-array response.
- `cursor`: the `X-Next-Cursor` value from the previous response. If only a cursor is supplied, the limit is 50.

The response body is always an array. `X-Next-Cursor` is present only when another matching item exists. Keep the same filters while following a cursor. The cursor encodes the last returned ID as base64. Invalid cursors return HTTP 422.

Paged results are in ascending ID order. The unpaged tags endpoint retains its existing alphabetical order. Pagination does not create a database snapshot: newly inserted higher IDs can appear on subsequent pages.

Filtering happens in SQL before the limit. Existing name/description search, ANY matching tag filters, and theorem status filters retain their meanings. `/formulas` additionally supports `type=proposition|term`, `head_symbol_id` (the symbol at token position 0), and `contains_symbol_id` (the symbol at any token position). These filters can be combined with paging.

`/theorems`, `/axioms`, and `/definitions` also accept repeatable
`exclude_tag_id`. An item carrying **any** excluded tag is omitted. This is
independent of `tag_id`: inclusive matching remains ANY, and an item that
matches an included tag is still omitted when it also matches an excluded tag.

The CORS configuration exposes `X-Next-Cursor` to the frontend. `/symbols` continues to return the whole symbol table.

`contains_symbol_id` uses an SQL `EXISTS` condition, so formulas containing repeated occurrences are returned once. Both symbol filters require positive IDs; an unknown positive ID returns an empty array.

New databases include `ix_formula_token_symbol_formula` on `(symbol_id, formula_id)`. Existing migration-managed databases need revision `20260906_0001` (`alembic upgrade head`). `create_all()` does not add indexes to an existing table. For an existing SQLite database created without Alembic, add this index through its schema maintenance process:

```sql
CREATE INDEX IF NOT EXISTS ix_formula_token_symbol_formula
ON formula_token (symbol_id, formula_id);
```

This completes UX Phase 0.5. The `type` parameter's English values map to the existing Japanese formula-type names in the database.
