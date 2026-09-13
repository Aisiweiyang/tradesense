"""Normalization layer tests: units, currencies, countries, ports, quantities."""
from app.services import normalization as norm


def test_plural_and_hyphen_product_matching():
    assert norm.canonical_product("vacuum insulated bottles")["concept"] == "insulated_bottle"
    assert norm.canonical_product("stainless-steel bottles")["concept"] == "insulated_bottle"
    assert norm.canonical_product("Thermal Bottle")["concept"] == "insulated_bottle"
    assert norm.canonical_product("保温杯")["concept"] == "insulated_bottle"
    assert norm.canonical_product("双层真空水瓶")["concept"] == "insulated_bottle"
    assert norm.canonical_product("ceramic mug")["concept"] == "mug"


def test_color_boundaries_no_false_positive():
    assert norm.normalize_color("required documents") != "red"
    assert norm.find_colors("required") == []
    assert norm.find_colors("matte black with blue lid") == ["matte black", "blue"]
    assert norm.normalize_color("深蓝色") == "navy blue" or norm.normalize_color("深蓝") == "navy blue"


def test_certification_boundaries():
    certs = norm.normalize_certifications("LFGB certification is mandatory")
    assert certs == ["LFGB"]
    certs = norm.normalize_certifications("FDA and BPA-free, CE not required")
    assert "FDA" in certs and "BPA-free" in certs and "CE" in certs


def test_quantity_prefers_explicit_units():
    q = norm.parse_quantity("We need 5,000 pcs of 500ml bottles, delivery within 45 days at USD 4.5")
    assert q["value"] == 5000
    assert q["unit"] == "pcs"


def test_quantity_k_suffix_and_ranges():
    assert norm.parse_quantity("qty 10k")["value"] == 10000
    assert norm.parse_quantity("2,000-3,000 sets")["value"] in (2000, 3000)
    assert norm.parse_quantity("within 45 days") is None
    assert norm.parse_quantity("price 4.5 USD") is None


def test_chinese_quantity():
    q = norm.parse_quantity("保温杯 500个")
    assert q["value"] == 500 and q["unit"] == "pcs"


def test_currency_normalization():
    assert norm.normalize_currency("$") == "USD"
    assert norm.normalize_currency("rmb") == "CNY"
    assert norm.normalize_currency("€") == "EUR"


def test_country_and_port_resolution():
    assert norm.normalize_country("Germany") == ("Germany", "DE")
    assert norm.normalize_country("德国") == ("Germany", "DE")
    assert norm.normalize_country("usa") == ("United States", "US")
    port = norm.resolve_place("ship to Hamburg")
    assert port and port["value"] == "Hamburg" and port["country"] == "Germany"
    port = norm.resolve_place("DDP Dubai")
    assert port and port["country"] == "United Arab Emirates"


def test_incoterm():
    assert norm.normalize_incoterm("quote FOB Hamburg") == "FOB"
    assert norm.normalize_incoterm("EXW price") == "EXW"
    assert norm.normalize_incoterm("cnf") == "CFR"


def test_price_parsing():
    p = norm.parse_target_price("target price around USD 4.5 per piece")
    assert p["currency"] == "USD" and abs(p["value"] - 4.5) < 1e-9
    p = norm.parse_target_price("预算 12 元/个")
    assert p and p["currency"] == "CNY" and p["value"] == 12
    assert norm.parse_target_price("we like the bottles") is None


def test_lead_time():
    assert norm.parse_lead_time("delivery within 45 days")["days"] == 45
    assert norm.parse_lead_time("交期 30 天")["days"] == 30


def test_content_hash_stable():
    assert norm.content_hash("hello") == norm.content_hash("hello")
    # trailing whitespace is stripped so near-identical content dedupes
    assert norm.content_hash("hello") == norm.content_hash("hello ")
    assert norm.content_hash("hello") != norm.content_hash("hello world")
    assert len(norm.content_hash("x")) == 64
