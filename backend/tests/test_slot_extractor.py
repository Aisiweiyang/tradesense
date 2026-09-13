"""Slot extraction tests incl. multi-field updates and negations."""
from app.services.slot_extractor import detect_language, extract_slots


def _fields(result):
    return {u.field: u for u in result.updates}


def test_language_detection():
    assert detect_language("I need 500 bottles") == "en"
    assert detect_language("我们需要500个保温杯") == "zh"


def test_spec_example_message1():
    r = extract_slots("I need 500 blue stainless-steel bottles.")
    f = _fields(r)
    assert f["product"].normalized == "insulated_bottle"
    assert f["material"].normalized == "stainless steel"
    assert f["color"].normalized == "blue"
    assert f["quantity"].normalized == "500"


def test_spec_example_message2_overrides():
    r = extract_slots("Actually, make them black, increase the quantity to 1,000, and ship to Hamburg.")
    f = _fields(r)
    assert f["color"].normalized == "black"
    assert f["quantity"].normalized == "1000"
    assert f["destination_port"].normalized == "Hamburg"
    assert f["destination_country"].normalized == "DE"


def test_multi_field_single_message():
    r = extract_slots("We need 2,000 ceramic mugs, DDP Dubai, gift box, our logo on each.")
    f = _fields(r)
    assert f["incoterm"].normalized == "DDP"
    assert f["packaging"].normalized == "gift box"
    assert f["customization"].normalized == "logo_print"


def test_conflicting_colors_flagged():
    r = extract_slots("Please quote 5,000 lunch boxes in green and navy blue.")
    color = _fields(r)["color"]
    assert color.conflict is True
    assert color.status_hint == "conflicting"


def test_unconstrained_color():
    r = extract_slots("Quote 1,000 travel mugs FOB Felixstowe. Any color is fine.")
    f = _fields(r)
    assert f["color"].unconstrained is True
    assert f["color"].normalized == "__unconstrained__"


def test_certification_extraction():
    r = extract_slots("FDA and LFGB required for the US market, also BPA free.")
    assert set(_fields(r)["certification"].normalized.split("|")) == {"FDA", "LFGB", "BPA-free"}


def test_volume_spec_normalization():
    f = _fields(extract_slots("looking for 17oz water bottles"))
    assert f["spec"].normalized.endswith("ml")  # 17oz ≈ 503ml
    f = _fields(extract_slots("we need 500ml bottles"))
    assert f["spec"].normalized == "500ml"
