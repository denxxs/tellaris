"""How each person's feed is chosen in the society.

Three styles:
- word_of_mouth: you see your own contacts' recent posts, newest first. Nothing travels
  beyond the people you know unless someone you know says it again in their own words.
- ranked: a platform-style feed. Every recent post is a candidate; each gets a score from
  how fresh it is, how much engagement it has (likes, reshares, replies) and how close you
  are to it (your contact wrote it, a contact reshared it, a friend of a friend, or a stranger).
- viral: the same ranker with engagement weighted much more heavily and strangers' posts
  pushed further, so a few popular posts reach most people.

The ranker is plain arithmetic, so the same inputs and seed always give the same feeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import networkx as nx
import numpy as np

from ..research.news import attention

FeedStyle = Literal["word_of_mouth", "ranked", "viral"]

FEED_SIZE = 5


@dataclass(frozen=True)
class Weights:
    contact: float
    reshared: float
    two_hop: float
    stranger: float
    engagement: float  # how much each like/reshare/reply lifts a post
    power: float  # >1 makes popular posts pull away from the rest


STYLES: dict[str, Weights] = {
    "ranked": Weights(contact=1.0, reshared=0.8, two_hop=0.25, stranger=0.03, engagement=0.3, power=1.0),
    "viral": Weights(contact=1.0, reshared=0.9, two_hop=0.45, stranger=0.25, engagement=1.0, power=1.6),
}

LABELS = {
    "word_of_mouth": "Word of mouth",
    "ranked": "Ranked feed",
    "viral": "Viral",
}


def engagement(it: dict[str, Any]) -> float:
    """Likes count once, replies one and a half times, reshares twice."""
    return it.get("likes", 0) + 1.5 * it.get("replies", 0) + 2.0 * it.get("reshares", 0)


@dataclass
class FeedState:
    """Who has reshared and seen what, kept across rounds."""

    resharers: dict[str, set[str]] = field(default_factory=dict)  # item id -> people who reshared it
    seen: dict[str, set[str]] = field(default_factory=dict)  # person -> item ids already shown
    liked: dict[str, set[str]] = field(default_factory=dict)  # person -> item ids they liked


def why_shown(kind: str, via: str | None) -> str | None:
    if kind == "contact":
        return None
    if kind == "reshared":
        return f"reshared by {via}" if via else "reshared by a contact"
    if kind == "two_hop":
        return "a friend of a friend"
    return "popular outside your circle"


def pick(
    style: str,
    pid: str,
    rnd: int,
    talk: list[dict[str, Any]],
    g: nx.Graph,
    fs: FeedState,
    names: dict[str, str],
    rng: np.random.Generator | None = None,
) -> list[dict[str, Any]]:
    """The items person `pid` sees in round `rnd`, best first.

    Returns shallow copies with two extra keys for the prompt and the UI: `via` (why it is in
    the feed: None for a contact's own post) and `score`.
    """
    contacts = set(g.neighbors(pid))
    if style not in STYLES:
        recent = [it for it in talk if it["round"] >= rnd - 2 and it["author"] in contacts]
        recent.sort(key=lambda it: (-it["round"], -(it["agrees"] + it["disagrees"])))
        return [{**it, "via": None} for it in recent[:FEED_SIZE]]

    w = STYLES[style]
    two_hop = {n2 for n in contacts for n2 in g.neighbors(n)} - contacts - {pid}
    already = fs.seen.get(pid, set())
    scored: list[tuple[float, dict[str, Any]]] = []
    for it in talk:
        age = (rnd - 1) - it["round"]
        if it["author"] == pid or age < 0:
            continue
        sharers = fs.resharers.get(it["id"], set()) & contacts
        if it["author"] in contacts:
            kind, close, via = "contact", w.contact, None
        elif sharers:
            kind, close = "reshared", w.reshared
            via = names.get(sorted(sharers)[0])
        elif it["author"] in two_hop:
            kind, close, via = "two_hop", w.two_hop, None
        else:
            kind, close, via = "stranger", w.stranger, None
        # A round is a day (the network is daily contacts); a post keeps the share of attention a news
        # story keeps after that many days (Wikipedia pageviews, research/news.attention).
        score = close * attention(age) * (1 + w.engagement * engagement(it)) ** w.power
        if it["id"] in already:
            score *= 0.3  # feeds rarely show the same thing twice
        if rng is not None:
            score *= 0.9 + 0.2 * float(rng.random())
        scored.append((score, {**it, "via": why_shown(kind, via), "score": round(score, 3)}))
    scored.sort(key=lambda s: (-s[0], s[1]["id"]))
    return [it for _, it in scored[:FEED_SIZE]]


def record_seen(fs: FeedState, pid: str, shown: list[dict[str, Any]], item_by_id: dict[str, dict[str, Any]], g: nx.Graph) -> None:
    """Count how far each item travelled: everyone it was shown to, and those outside its author's circle."""
    already = fs.seen.setdefault(pid, set())
    for v in shown:
        if v["id"] in already:
            continue
        already.add(v["id"])
        it = item_by_id.get(v["id"])
        if it is None:
            continue
        it["seen"] = it.get("seen", 0) + 1
        if it.get("author") and not g.has_edge(pid, it["author"]):
            it["seen_outside"] = it.get("seen_outside", 0) + 1


def apply_engagement(
    fs: FeedState, pid: str, name: str, likes: list[str], reshare: str | None, shown_ids: set[str], item_by_id: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    """Apply one person's likes and reshare to items they were actually shown. Returns (likes, reshares) counted."""
    n_likes = 0
    mine = fs.liked.setdefault(pid, set())
    for iid in dict.fromkeys(likes[:3]):
        if iid in shown_ids and iid in item_by_id and iid not in mine:  # one like per person per post
            mine.add(iid)
            item_by_id[iid]["likes"] = item_by_id[iid].get("likes", 0) + 1
            n_likes += 1
    if reshare and reshare in shown_ids and reshare in item_by_id:
        sharers = fs.resharers.setdefault(reshare, set())
        if pid not in sharers:
            sharers.add(pid)
            it = item_by_id[reshare]
            it["reshares"] = it.get("reshares", 0) + 1
            by = it.setdefault("reshared_by", [])
            if len(by) < 8:
                by.append({"id": pid, "name": name})
            return n_likes, 1
    return n_likes, 0


def travel_summary(style: str, talk: list[dict[str, Any]], people: int) -> dict[str, Any]:
    """How far posts travelled in this run."""
    seen = [it.get("seen", 0) for it in talk]
    outside = sum(it.get("seen_outside", 0) for it in talk)
    total_seen = sum(seen)
    top = sorted(talk, key=lambda it: (-it.get("seen", 0), -engagement(it), it["id"]))[:5]
    return {
        "style": style,
        "label": LABELS.get(style, style),
        "likes": sum(it.get("likes", 0) for it in talk),
        "reshares": sum(it.get("reshares", 0) for it in talk),
        "views": total_seen,
        "outside_share": round(outside / total_seen, 3) if total_seen else 0.0,
        "avg_reach": round(total_seen / len(talk), 2) if talk else 0.0,
        "top_reach": round(max(seen) / people, 3) if seen and people else 0.0,
        "travelled": [
            {
                "id": it["id"], "author": it["author"], "author_name": it["author_name"], "country": it.get("country"),
                "text": it["text"], "p": it.get("p"), "seen": it.get("seen", 0), "seen_outside": it.get("seen_outside", 0),
                "likes": it.get("likes", 0), "reshares": it.get("reshares", 0), "replies": it.get("replies", 0),
                "share": round(it.get("seen", 0) / people, 3) if people else 0.0,
            }
            for it in top if it.get("seen", 0)
        ],
    }
