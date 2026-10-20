"""String markers for pages that are not the cited content."""
import json, os


# Notice pages served by the checker's own network web filter (not by the cited site). They are
# specific to the network the checker runs in, so they are read from a local, unpublished file:
# local/internal_markers.json  {"filter_markers": ["..."]}  or the env var CITEDRIFT_FILTER_MARKERS ("a|b|c").
def _load_filter_markers():
    env = os.environ.get("CITEDRIFT_FILTER_MARKERS")
    if env:
        return tuple(x for x in env.split("|") if x)
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "local",
                     "internal_markers.json")
    if os.path.exists(p):
        return tuple(json.load(open(p)).get("filter_markers", []))
    return ()


FILTER_MARKERS = _load_filter_markers()

# Bot walls / interstitials served by the cited site or its CDN.
CHALLENGE_MARKERS = ("just a moment", "cf-chl", "captcha", "verify you are human", "are you a robot",
                     "access denied", "attention required", "request blocked", "pardon our interruption",
                     "enable javascript and cookies", "verify that you're not a robot",
                     "verify you're not a robot", "javascript is disabled", "human verification", "client challenge",
                     "checking your browser", "please enable js", "robot challenge")

# Navigation statuses that interstitials use before handing over the real page. A browser visit that only
# reached the page after one of these counts as a bot wall: we do not count passing a bot check as access.
INTERSTITIAL_STATUSES = (202, 401, 403, 429, 503)
