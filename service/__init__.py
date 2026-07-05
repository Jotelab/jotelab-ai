"""HTTP service wrapping the symbolic engine (DEVELOPMENT_PLAN §1.1).

Exposes the constrained SymPy engine (:mod:`engine`) and the Data Fidelity
harness (:mod:`harness`) over HTTP so the Next.js web app can call them instead
of computing numbers itself. Two endpoints — ``POST /generate`` and
``POST /verify`` — behind a shared-secret header. No engine logic lives here;
this is a thin transport layer over :func:`engine.loop.generate` and
:func:`harness.verify.verify`.
"""

from service.app import app

__all__ = ["app"]
