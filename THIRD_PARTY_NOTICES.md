# Third-party notices

This snapshot does not bundle a third-party mathematical text, a derived
mathematical corpus, or a generated database snapshot. The independent logic
demonstrations use the retained public logical core.

Dependencies retain their own licenses and are not relicensed by `LICENSE.md`.
Exact JavaScript versions and integrity hashes are in
`frontend/package-lock.json`; beta Python versions are in
`deploy/beta/requirements.lock`. The tables below identify metadata inspected
for this update, rather than granting permission for an entire binary image.

## Frontend dependency updates

Compared with the preceding public snapshot, the following lock entries were
added or updated. Existing dependencies remain subject to their own notices.

| Package | Locked version | Declared license | Use |
| --- | --- | --- | --- |
| `@playwright/test` | 1.63.0 | Apache-2.0 | Development/test |
| `commander` | 15.0.0 | MIT | Runtime dependency |
| `katex` | 0.18.9 | MIT | Runtime dependency |
| `playwright` | 1.63.0 | Apache-2.0 | Development/test |
| `playwright-core` | 1.63.0 | Apache-2.0 | Development/test |
| `source-map-js` | 1.2.2 | BSD-3-Clause | Development/test |

Frontend builds include third-party JavaScript and KaTeX fonts. KaTeX's MIT
notice also covers its distributed fonts; retain upstream copyright and license
files when redistributing build artifacts. Playwright browser downloads, if
installed for testing, are separate artifacts with their own notices.

## Beta Python runtime lock

The lock targets Linux x86_64 CPython 3.13.18. Installed distribution metadata
matched the locally available locked packages; uvloop metadata came from its
reviewed target wheel, recorded in `deploy/beta/requirements.target-metadata.json`.
The target CI must also match that metadata against the installed distribution.
Licenses below are the packages' declared identifiers (or license classifiers).

| Package | Locked version | Declared license |
| --- | --- | --- |
| `alembic` | 1.18.5 | MIT |
| `annotated-doc` | 0.0.4 | MIT |
| `annotated-types` | 0.7.0 | MIT |
| `anyio` | 4.14.2 | MIT |
| `click` | 8.4.2 | BSD-3-Clause |
| `fastapi` | 0.139.0 | MIT |
| `greenlet` | 3.5.3 | MIT AND PSF-2.0 |
| `h11` | 0.16.0 | MIT |
| `httptools` | 0.8.0 | MIT |
| `idna` | 3.18 | BSD-3-Clause |
| `mako` | 1.3.12 | MIT |
| `markupsafe` | 3.0.3 | BSD-3-Clause |
| `psycopg` | 3.3.5 | LGPL-3.0-only |
| `psycopg-binary` | 3.3.5 | LGPL-3.0-only |
| `pydantic` | 2.13.4 | MIT |
| `pydantic-core` | 2.46.4 | MIT |
| `python-dotenv` | 1.2.2 | BSD-3-Clause |
| `pyyaml` | 6.0.3 | MIT |
| `sqlalchemy` | 2.0.51 | MIT |
| `starlette` | 1.3.1 | BSD-3-Clause |
| `typing-extensions` | 4.16.0 | PSF-2.0 |
| `typing-inspection` | 0.4.2 | MIT |
| `uvicorn` | 0.50.1 | BSD-3-Clause |
| `uvloop` | 0.23.0 | MIT / Apache-2.0 (dual license) |
| `watchfiles` | 1.2.0 | MIT |
| `websockets` | 16.0 | BSD-3-Clause |

`psycopg-binary` wheels contain native libraries, including libpq and TLS
libraries. Their bundled license files are part of the required review of the
actual platform wheel; the Python package's LGPL identifier does not describe
all embedded libraries. See the [Psycopg installation documentation](https://www.psycopg.org/psycopg3/docs/basic/install.html).
uvloop's wheel metadata declares MIT and Apache license classifiers and includes
`LICENSE-MIT` and `LICENSE-APACHE`; preserve both upstream files when
redistributing the wheel or an image containing it. Windows-only `colorama`
and `tzdata` are outside this deployment lock. The deployment's system time-zone
database must be checked separately. Preserve all distribution license and
notice files, including bundled native library notices.

## Deployment containers

| Configuration | Base images referenced |
| --- | --- |
| Generic API / database | `python:3.12-slim`, `postgres:16` |
| Generic frontend build / serving | `node:20-alpine`, `caddy:2-alpine` |
| Beta API / database | `python:3.13.18-slim-bookworm`, `postgres:18.6` |
| Beta frontend build / serving | `node:22.23.4-alpine`, `caddy:2.11.7-alpine / caddy:2.11.7-builder` |

These images are fetched at build/deployment time, not bundled in the source
snapshot. Locally built `dem-beta-api` and `dem-beta-web` images inherit their
base layers and add the locked dependencies or built frontend. The API beta
image additionally installs Debian packages and PostgreSQL client tools.

Python, Node.js, PostgreSQL and Caddy have their own upstream licenses; base
images also contain operating-system packages with separate licenses. Caddy
uses [Apache-2.0](https://github.com/caddyserver/caddy/blob/master/LICENSE).
The official [PostgreSQL image documentation](https://github.com/docker-library/docs/blob/master/postgres/README.md)
explains that additional software in images has its own terms. Retain license,
notice and copyright material from the actual images, wheels and frontend
packages when distributing binaries. This source inventory is not a completed
license inventory of a built multi-platform image.


## Frontend build/test security update

The distributed dependency records remain unchanged. The following development
packages changed; all declare MIT in the npm registry metadata and lock:
`vite` 8.1.6, `vitest` and `@vitest/{expect,mocker,pretty-format,runner,snapshot,spy,utils}`
4.1.12, `undici` 7.30.1, `rolldown` and its `@rolldown/binding-*` platform packages
1.1.5, and `@oxc-project/types` 0.139.0. Retain their upstream license files.
