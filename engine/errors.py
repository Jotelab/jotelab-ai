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


class ChainSpecError(EngineError):
    """A chained (mixed) problem spec is malformed (chain design doc).

    Raised at validation, before any part is generated: fewer than two parts,
    a missing/unknown ``receive`` variable, or a ``receive`` not among that
    part's givens.
    """

    def __init__(self, reason):
        self.reason = reason
        super().__init__(f"[mixed] invalid chain spec: {reason}")


class UnsanctionedLinkError(EngineError):
    """A chain link is dimensionally fine but not a vetted physical composition.

    Matching units are necessary, not sufficient: ``free-fall`` measures a
    falling speed down-positive and ``upward-throw`` a launch speed up-positive,
    so feeding one into the other is ``m/s`` into ``m/s`` while silently
    reversing the axis — the problem never says the body bounced. The engine
    cannot judge that on its own (it has no model of the *scenario*, only of the
    equations), so admissible compositions are enumerated by hand in
    ``engine.chain.SANCTIONED_LINKS``, each with a written justification.

    Raised at validation, before any part is generated.
    """

    def __init__(self, from_topic, from_find, to_topic, to_receive):
        self.from_topic = from_topic
        self.from_find = from_find
        self.to_topic = to_topic
        self.to_receive = to_receive
        super().__init__(
            f"[mixed] {from_topic}.{from_find} -> {to_topic}.{to_receive} is not a "
            f"sanctioned link: the units line up, but no one has stated why the "
            f"composition is physically meaningful. Add it to "
            f"engine.chain.SANCTIONED_LINKS with a narrative, or pick another pair."
        )


class IncompatibleLinkError(EngineError):
    """A chain link's units don't match (chain design doc).

    The receiving given of one part must carry the same unit as the previous
    part's find; raised at validation, before any part is generated.
    """

    def __init__(self, topic, symbol, receive_unit, feed_unit):
        self.topic = topic
        self.symbol = symbol
        self.receive_unit = receive_unit
        self.feed_unit = feed_unit
        super().__init__(
            f"[{topic}] link into {symbol!r} expects {receive_unit}, but the "
            f"previous part's answer is {feed_unit}"
        )
