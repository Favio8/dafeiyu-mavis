"""Visual fallback prerequisites only. No screenshot upload or coordinate executor."""
from dataclasses import dataclass

from .contracts import Observation
from .policy import PolicyDenied


@dataclass(frozen=True)
class VisualConsent:
    """Host UI authorization scoped to one observed context, never model-provided."""
    context_digest: str
    screen_upload: bool = False
    vision_verified: bool = False
    low_risk_region_verified: bool = False


def validate_visual_request(observation: Observation, consent: VisualConsent, *, current_digest: str) -> tuple[int, int, int, int]:
    """Return the authorized physical crop only when every prerequisite is satisfied."""
    if not consent.screen_upload or not consent.vision_verified:
        raise PolicyDenied("VISION_OR_UPLOAD_UNAVAILABLE")
    if not consent.low_risk_region_verified or observation.own_ui or observation.integrity != "medium":
        raise PolicyDenied("VISUAL_RISK_UNKNOWN")
    if not (current_digest == observation.context_digest == consent.context_digest):
        raise PolicyDenied("VISUAL_CONTEXT_CHANGED")
    left, top, right, bottom = observation.bounds
    if right <= left or bottom <= top or (right - left) * (bottom - top) > 16_000_000:
        raise PolicyDenied("INVALID_CROP")
    return observation.bounds
