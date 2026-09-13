"""Clarification recommender tests: priority order + explanation + split score."""
from app.services.clarification import build_candidates


def _values(**kw):
    base = {f: {"value": "", "normalized": "", "status": "unknown"} for f in
            ("product", "material", "color", "spec", "quantity", "target_price",
             "destination_country", "destination_port", "incoterm", "packaging",
             "customization", "certification", "lead_time", "payment_terms")}
    base.update(kw)
    return base


def test_regulatory_first_for_food_contact(db, org):
    values = _values(product={"value": "Insulated bottle", "normalized": "insulated_bottle",
                              "status": "active"})
    candidates = build_candidates(db, org.id, values)
    assert candidates[0]["field"] == "certification"
    assert "FDA" in candidates[0]["reason"] or "LFGB" in candidates[0]["reason"]


def test_quote_blockers_next(db, org):
    values = _values(product={"value": "Mug", "normalized": "mug", "status": "active"},
                     certification={"value": "FDA", "normalized": "FDA", "status": "active"})
    candidates = build_candidates(db, org.id, values)
    fields = [c["field"] for c in candidates]
    # all quote-blocking fields asked before preferences
    for blocker in ("quantity", "incoterm", "destination_country"):
        assert blocker in fields
        assert "报价" in next(c for c in candidates if c["field"] == blocker)["reason"] or \
               "必需" in next(c for c in candidates if c["field"] == blocker)["reason"]
    blocker_positions = [fields.index(b) for b in ("quantity", "incoterm")]
    pref_positions = [fields.index(f) for f in fields if f in ("lead_time", "payment_terms")]
    if pref_positions:
        assert max(blocker_positions) < min(p[0] for p in [(pp,) for pp in pref_positions])


def test_conflict_overrides_preferences(db, org):
    values = _values(product={"value": "Mug", "normalized": "mug", "status": "active"},
                     quantity={"value": "500", "normalized": "500", "status": "active"},
                     incoterm={"value": "FOB", "normalized": "FOB", "status": "active"},
                     destination_country={"value": "US", "normalized": "US", "status": "active"},
                     certification={"value": "FDA", "normalized": "FDA", "status": "active"},
                     color={"value": "red or blue", "normalized": "red|blue", "status": "conflicting"})
    candidates = build_candidates(db, org.id, values)
    assert candidates[0]["field"] == "color"
    assert "矛盾" in candidates[0]["reason"]


def test_every_question_has_reason_and_bilingual(db, org):
    values = _values()
    for c in build_candidates(db, org.id, values):
        assert c["reason"].strip()
        assert c["question_en"].strip() and c["question_zh"].strip()


def test_split_score_bounds():
    from app.services.clarification import _split_score

    class P:
        color = ""
        spec = ""

    half = [P() for _ in range(4)]
    for i, p in enumerate(half):
        p.color = "red" if i < 2 else ""
    score = _split_score(half, "color")
    assert abs(score - 1.0) < 1e-9  # p=0.5 maximizes discrimination
    uniform = [P() for _ in range(3)]
    score = _split_score(uniform, "color")
    assert score == 0.0  # p=0 or 1 → no discrimination
