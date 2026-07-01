"""Typed errors for the symbolic engine (spec §9).

Every dead end in the engine raises one of these; nothing ugly ever ships
silently. Callers (the Generation Engine orchestrator) catch these and surface a
clear message to the user.
"""


class EngineError(Exception):
    """Base class for all symbolic-engine failures."""


class UnsolvableError(EngineError):
    """The requested ``find`` is not derivable from ``given`` in this topic.

    Raised at validation, before the re-roll loop is ever entered (spec §3, §9).
    """

    def __init__(self, topic, given, find, reason=""):
        self.topic = topic
        self.given = given
        self.find = find
        self.reason = reason
        super().__init__(
            f"[{topic}] cannot solve for {find} from given={given}: {reason}"
        )


class OverDeterminedError(EngineError):
    """``given`` fixes ``find`` more than one way, or contradicts itself (spec §3)."""

    def __init__(self, topic, given, find, reason=""):
        self.topic = topic
        self.given = given
        self.find = find
        self.reason = reason
        super().__init__(
            f"[{topic}] over-determined / contradictory given={given} "
            f"for find={find}: {reason}"
        )


class TemplateValidationError(EngineError):
    """A declarative template failed a validation-gate stage (ADR-007).

    Carries the failing ``stage`` number, its ``stage_name``, and a human
    ``reason`` so the orchestrator can tell an author exactly why a submitted
    template was rejected. Raised by the five-stage gate; never swallowed.
    """

    def __init__(self, stage, stage_name, reason=""):
        self.stage = stage
        self.stage_name = stage_name
        self.reason = reason
        super().__init__(f"[stage {stage}: {stage_name}] {reason}")


class NoCleanInstanceError(EngineError):
    """No instance satisfied the constraints within ``MAX_ATTEMPTS`` (spec §5, §9).

    The loop has already loosened the clean-answer policy once (at ``SOFT_LIMIT``)
    before this is raised; it is surfaced to the caller, never swallowed.
    """

    def __init__(self, topic, find, attempts):
        self.topic = topic
        self.find = find
        self.attempts = attempts
        super().__init__(
            f"[{topic}] no clean instance for find={find} after {attempts} attempts"
        )
