# SPDX-License-Identifier: GPL-3.0-or-later
"""The card grid: places in grid units, pushing cards out of the way, and floating everything up.

Same rules as a vertical-compacting grid layout: a card dropped on another takes its place
(the other swaps above when there is room, otherwise it is pushed down, and the push cascades),
then every card floats up as far as it can. Pure Python, no Qt.
"""


def collides(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _first_collision(items, cid, p):
    for i, o in items.items():
        if i != cid and collides(p, o):
            return o
    return None


def compact(items):
    """items: {id: [x, y, w, h]} -> floated up, no overlaps (changed in place, also returned)."""
    order = sorted(items, key=lambda i: (items[i][1], items[i][0], i))
    done = {}
    for cid in order:
        x, y, w, h = items[cid]
        y = max(0, y)
        while y > 0 and _first_collision(done, cid, [x, y - 1, w, h]) is None:
            y -= 1
        c = _first_collision(done, cid, [x, y, w, h])
        while c is not None:
            y = c[1] + c[3]
            c = _first_collision(done, cid, [x, y, w, h])
        done[cid] = [x, y, w, h]
    items.clear()
    items.update(done)
    return items


def _push(items, cid, user):
    me = items[cid]
    hit = sorted((i for i, o in items.items() if i != cid and collides(me, o)), key=lambda i: (items[i][1], items[i][0]))
    for other in hit:
        o = items[other]
        if not collides(me, o):
            continue
        if user:
            above = [o[0], max(0, me[1] - o[3]), o[2], o[3]]
            if _first_collision(items, other, above) is None:
                items[other] = above
                continue
        items[other] = [o[0], me[1] + me[3], o[2], o[3]]
        _push(items, other, False)


def move(items, cid, x, y):
    p = items[cid]
    items[cid] = [x, max(0, y), p[2], p[3]]
    _push(items, cid, True)
    return compact(items)


def resize(items, cid, w, h):
    p = items[cid]
    items[cid] = [p[0], p[1], w, h]
    _push(items, cid, False)
    return compact(items)


def place_new(items, cid, p):
    """Puts a card back at its remembered place and makes room for it."""
    items[cid] = list(p)
    _push(items, cid, False)
    return compact(items)


def fit_columns(items, cols, min_w):
    """Keeps every card inside `cols` columns (narrower window)."""
    for cid, p in items.items():
        w = max(min_w.get(cid, 1), min(p[2], cols))
        x = min(p[0], max(0, cols - w))
        items[cid] = [x, p[1], w, p[3]]
    # overlaps made by the squeeze are resolved top to bottom
    for cid in sorted(items, key=lambda i: (items[i][1], items[i][0])):
        _push(items, cid, False)
    return compact(items)


def bottom(items):
    return max([p[1] + p[3] for p in items.values()] + [0])
