# Licensing and distribution notes

## Project source

The root LICENSE contains the standard MIT License and the notice “Copyright (c) 2026 Hermes CRM contributors.” pyproject.toml declares the same license. Retain that notice and license when redistributing the source. The contributor label is not a legal determination of copyright ownership or copyrightability.

The source package contains original CRM implementation, tests, documentation and synthetic sample data. It does not bundle Hermes source, React, fonts, icons, third-party media, Python dependencies, database files or credential material. Product names identify compatibility and design references, not affiliation or endorsement.

## Separately installed dependencies

The following direct-dependency licenses were checked against installed package metadata on November 6, 2026. Version ranges in pyproject.toml may resolve differently later; recheck the versions actually distributed or deployed.

| Package checked | Version checked | Declared license |
| --- | --- | --- |
| FastAPI | 0.141.1 | MIT |
| SQLAlchemy | 2.1.8 | MIT |
| Pydantic | 2.13.4 | MIT |
| Uvicorn | 0.52.1 | BSD-3-Clause |
| cryptography (checked November 7) | 50.0.0 | Apache-2.0 OR BSD-3-Clause |
| psycopg, optional PostgreSQL driver | 3.3.8 | LGPL-3.0-only |
| psycopg-binary, optional PostgreSQL wheel | 3.3.8 | LGPL-3.0-only |
| pytest, test only | 9.2.0 | MIT |
| HTTPX, test only | 0.28.1 | BSD-3-Clause |
| PyYAML, test only (checked November 7) | 6.0.3 | MIT |

The installed cryptography dependency also uses separately distributed native dependencies; the checked cffi 2.1.1 metadata declares MIT-0. No cryptographic dependency or binary is vendored.

The MIT license for this project does not relicense these dependencies. The optional PostgreSQL driver is imported as a separate package and is not vendored into this source archive. Distributing an executable, container or environment containing dependencies requires preserving their applicable notices and meeting their license terms, including any bundled native libraries and LGPL obligations. That binary-distribution review is outside this source-only package review.

The native pane imports React and @hermes/plugin-sdk from the Hermes host. It does not redistribute either. The component test harness uses separately installed React and react-test-renderer 19.3.0 (MIT). Hermes' own license continues to govern the host and SDK.

## Review scope

Source and archive checks look for accidental private records, secrets, personal paths and bundled artifacts; they cannot guarantee the absence of every possible legal or security issue. No dependency vulnerability certification, legal opinion, production-security audit or hosted-service verification is claimed. See VERIFICATION.md for runtime tests and remaining release gates.
