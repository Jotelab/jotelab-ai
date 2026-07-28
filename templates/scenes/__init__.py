"""Scene compiler package (spec 2026-07-29): scene document -> system template."""

from .compile import compile_scene
from .ontology import SceneError

__all__ = ["compile_scene", "SceneError"]
