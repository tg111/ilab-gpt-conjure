# Dependency security notes

Assessment date: 2026-10-31. A package advisory match is not evidence that an
application path is exploitable. These notes describe the source and build
configuration, not the contents of previously published or installed packages.

## Image and TLS dependencies

- Pillow is pinned to **13.0.0**. PNG EXIF parsing is relevant to untrusted
  reference images and generated images: thumbnail creation calls
  `ImageOps.exif_transpose`, which reads EXIF metadata. The fixed quadratic
  parsing issue is [GHSA-g4qv-2jxx-769h](https://github.com/python-pillow/Pillow/security/advisories/GHSA-g4qv-2jxx-769h).
  Raster validation now limits parser selection to GIF, JPEG, PNG and WebP at
  `Image.open`, while retaining byte, dimension, pixel and frame budgets.
  Existing local reference conversion, including MPO to PNG, remains available.
- The [JPEG draft/scaling advisory](https://github.com/python-pillow/Pillow/security/advisories/GHSA-8g5g-8vmr-9782)
  requires scaling before loading. Current thumbnail functions load through
  `exif_transpose` before calling `thumbnail`; this assessment does not claim
  that path directly triggers that issue. Format restriction alone would not
  fix a JPEG decoder issue, so upgrading Pillow remains necessary.
- certifi is a direct application dependency pinned to **2026.10.23**, including
  wheel/editable installations as well as the runtime lock, after the
  [emSign trust-store correction](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2).
  The application uses it for default outbound HTTPS verification. Explicit
  `SSL_CERT_FILE` / `SSL_CERT_DIR` settings retain their existing behavior;
  owners of custom CA bundles must maintain those bundles separately.
  Certificate and hostname verification are not disabled.

## Runtime and build baseline

- Source startup, CLI and the WebUI server check the minimum Python version
  before starting work: 3.11, or 3.13 on Windows. No specific patch release is
  required, because this fork runs locally. Manual
  WebUI and CLI startup also reject missing, prerelease or older Pillow/certifi
  versions below the security floors (13.0.0 and 2026.10.19). These minimum
  checks do not replace the exact installation lock. Checks report the required
  version without changing global environments.
- The audited PEP 517 backend is **setuptools 84.2.1**. Its
  [legacy Windows wheel-installation advisory](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w)
  is fixed in 84.1.0. This project uses PEP 517, not the affected legacy
  `setup_requires` / `install_as_egg` path; the update is defensive build hygiene.
- Frontend CI uses **Node 22.23.4**, from the
  [October security release](https://nodejs.org/en/blog/vulnerability/october-2026-security-releases).
  Node builds/tests frontend assets; the WebUI server is Python. The project
  version file does not upgrade an existing developer's global Node executable.

## Verification boundaries

Use synthetic images and an isolated local TLS server for regression checks.
Verify allowed uploads, EXIF orientation, thumbnails, format conversion, output
downloads, custom CA acceptance, rejection of unknown CAs/wrong hostnames, and
proxy routing. Do not run resource-exhaustion payloads against a user's service.

Existing running processes must be restarted with updated dependencies and a
patched interpreter to receive the runtime fixes.
