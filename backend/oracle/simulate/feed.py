"""How each person's feed is chosen in the society.

Three styles:
- word_of_mouth: you see your own contacts' posts you haven't seen yet, newest first. Nothing
  travels beyond the people you know unless someone you know says it again in their own words.
- ranked: a Facebook-style feed. The share of slots filled with posts from people you aren't
  connected to is Meta's own figure for US Facebook feeds (Widely Viewed Content Report, Q2 2026:
  36.6% of views unconnected, 49.6% from friends, groups and followed pages; the 13.8% "other" left out).
- viral: a TikTok-style feed. Only 10.3% of videos watched come from accounts the viewer follows
  (Zannettou et al. 2024, CHI, data donated by 347 users, 9.2 million views).

Within each pool posts are ranked by how much attention a story keeps after that many days
(Wikipedia pageviews, research/news.attention; a round is a day) times their engagement in
Facebook's own "meaningful social interactions" points (internal note, Dec 2017, reported by
CNN 2021): a like 1, a reshare without text 5, a comment 30. Feeds don't repeat a post you have
already been shown. The ranker is plain arithmetic, so the same inputs and seed give the same feeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import networkx as nx
import numpy as np

from ..research.news import attention

FeedStyle = Literal["word_of_mouth", "ranked", "viral"]

FEED_SIZE = 5  # posts on this topic per person per day: a setting, see docs/no-assumptions.md

# Share of feed slots given to posts from people you aren't connected to.
UNCONNECTED = {
    "ranked": round(36.6 / (36.6 + 49.6), 4),  # Meta Widely Viewed Content Report, US, Q2 2026
    "viral": round(1 - 0.103, 4),  # Zannettou et al. 2024: 10.3% of TikTok views from followed accounts
}

# Facebook's meaningful-social-interaction points (2018 weights, reported by CNN, Oct 2021).
POINTS = {"likes": 1.0, "reshares": 5.0, "replies": 30.0}

LABELS = {
    "word_of_mouth": "Word of mouth",
    "ranked": "Ranked feed",
    "viral": "Viral",
}


def engagement(it: dict[str, Any]) -> float:
    """Facebook's interaction points: a like 1, a reshare 5, a reply 30."""
    return sum(w * it.get(k, 0) for k, w in POINTS.items())


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
    the feed: None for a contact's own post) and `score`. Without an rng the number of
    unconnected slots is the rounded expectation; with one it is drawn slot by slot.
    """
    contacts = set(g.neighbors(pid))
    already = fs.seen.get(pid, set())
    fresh = [it for it in talk if it["author"] != pid and (rnd - 1) - it["round"] >= 0 and it["id"] not in already]
    if style not in UNCONNECTED:
        recent = [it for it in fresh if it["author"] in contacts]
        recent.sort(key=lambda it: (-it["round"], -(it["agrees"] + it["disagrees"]), it["id"]))
        return [{**it, "via": None} for it in recent[:FEED_SIZE]]

    two_hop = {n2 for n in contacts for n2 in g.neighbors(n)} - contacts - {pid}
    pools: dict[bool, list[tuple[float, dict[str, Any]]]] = {True: [], False: []}
    for it in fresh:
        age = (rnd - 1) - it["round"]
        sharers = fs.resharers.get(it["id"], set()) & contacts
        if it["author"] in contacts:
            kind, via = "contact", None
        elif sharers:
            kind, via = "reshared", names.get(sorted(sharers)[0])
        elif it["author"] in two_hop:
            kind, via = "two_hop", None
        else:
            kind, via = "stranger", None
        score = attention(age) * (1 + engagement(it))
        pools[kind in ("contact", "reshared")].append((score, {**it, "via": why_shown(kind, via), "score": round(score, 3)}))
    for pool in pools.values():
        pool.sort(key=lambda s: (-s[0], s[1]["id"]))
    share = UNCONNECTED[style]
    n_out = int(rng.binomial(FEED_SIZE, share)) if rng is not None else round(FEED_SIZE * share)
    take_out = min(n_out, len(pools[False]))
    take_in = min(FEED_SIZE - take_out, len(pools[True]))
    take_out = min(FEED_SIZE - take_in, len(pools[False]))  # an empty pool's slots go to the other
    chosen = pools[True][:take_in] + pools[False][:take_out]
    chosen.sort(key=lambda s: (-s[0], s[1]["id"]))
    return [it for _, it in chosen]


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
