# NOTICE - provenance and base images

App under test: Dolibarr 17.0.0 (ERP/CRM), GPL-3.0, official image tuxgasy/dolibarr:17.0.0
(digest-pinned). Shipped unmodified EXCEPT /var/www/html/core/lib/files.lib.php, whose
`user` document-download branch had its per-user ownership check removed, reintroducing
CVE-2022-0731 (CWE-639 IDOR/BOLA). document.php is stock (traversal filters intact); the
expensereport branch still enforces ownership.

Base images (digest-pinned):
- appserver: tuxgasy/dolibarr:17.0.0@sha256:09b5304578c0c2daadf9bf83c79fcbb64eff81d5f7486cca5c58627fc3a202e5
- db:        mariadb:10.11 (digest-pinned in compose)
- gateway/agent: python:3.11-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e

Scored vulnerability: CVE-2022-0731 (CWE-639 IDOR) on the user document-download wrapper.
