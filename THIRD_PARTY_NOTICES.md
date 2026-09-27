# Third-party notices

This release candidate does not bundle a third-party mathematical text,
derived mathematical corpus, or generated database snapshot.

Runtime and development dependencies are declared in `pyproject.toml` and
`frontend/package.json`; their own licenses govern those packages. They are
not relicensed by this repository.

Building the frontend produces artifacts that include third-party code and
fonts, including KaTeX and its fonts and other JavaScript dependencies. These
assets are not stored in this repository. Before distributing the built
frontend or a Docker image containing it, review and comply with each
component's applicable license terms.
