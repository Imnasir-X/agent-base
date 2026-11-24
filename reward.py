"""Scalar episode reward. Shape is final; training uses it later.

episode = {success, num_turns, latency_ms, actions}
+1.0 on success, -0.005 per turn, -0.0025 per second of latency.
"""


def reward(episode: dict) -> float:
    score = 1.0 if episode.get("success") else 0.0
    score -= 0.005 * int(episode.get("num_turns") or 0)
    score -= 0.0025 * (int(episode.get("latency_ms") or 0) / 1000.0)
    return score
