

def test_expired_quote_creates_task_once(db, org):
    """过期报价自动建"报价已过期"待办：当天到期不算过期、任务只建一次、隔离。"""
    from datetime import datetime, timedelta, timezone

    from app.models import FollowUpTask, Inquiry, Quote
    from app.services.followup import workload_lists

    now = datetime.now(timezone.utc)

    inq = Inquiry(org_id=org.id, title="exp", status="quoted", stage="quoted")
    db.add(inq)
    db.flush()
    q = Quote(org_id=org.id, inquiry_id=inq.id, version=1, status="approved",
              incoterm="FOB", currency="USD", quantity=100, unit_cost=1.0,
              unit_price=2.0, customer_price=2.0, total_amount=200.0, margin_rate=0.15)
    q.valid_until = now - timedelta(days=3)
    db.add(q)
    db.flush()

    ids1 = workload_lists(db, org.id)
    assert q.id in ids1["expired_quotes"]
    tasks = db.query(FollowUpTask).filter_by(org_id=org.id, task_type="quote_expired").all()
    assert len(tasks) == 1
    # 再刷不重复
    ids2 = workload_lists(db, org.id)
    assert len(db.query(FollowUpTask).filter_by(org_id=org.id, task_type="quote_expired").all()) == 1
    assert ids2["expired_quotes"] == ids1["expired_quotes"]

    # 未过期不建任务
    q2 = Quote(org_id=org.id, inquiry_id=inq.id, version=2, status="draft",
               incoterm="FOB", currency="USD", quantity=100, unit_cost=1.0,
               unit_price=2.0, customer_price=2.0, total_amount=200.0, margin_rate=0.15)
    q2.valid_until = now + timedelta(days=5)
    db.add(q2)
    db.flush()
    workload_lists(db, org.id)
    assert len(db.query(FollowUpTask).filter_by(org_id=org.id, task_type="quote_expired").all()) == 1
