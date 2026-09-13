"""Multilingual normalization layer: colors, materials, currencies, countries,
ports, incoterms, certifications, quantities, prices, dates, packaging and
product-concept synonyms.

Design rules:
- keep the ORIGINAL expression; normalization only adds canonical forms
- dictionaries are extensible data, logic is small and testable
"""
from __future__ import annotations

import calendar
import hashlib
import re
from datetime import datetime, timedelta, timezone

# ----------------------------------------------------------------------------- colors
COLORS = {
    "blue": "blue", "navy": "navy blue", "sky blue": "sky blue", "light blue": "sky blue",
    "black": "black", "matte black": "matte black", "white": "white", "red": "red",
    "green": "green", "dark green": "dark green", "yellow": "yellow", "orange": "orange",
    "purple": "purple", "pink": "pink", "gray": "gray", "grey": "gray", "silver": "silver",
    "gold": "gold", "rose gold": "rose gold", "brown": "brown", "beige": "beige",
    "wood": "wood", "wooden": "wood", "transparent": "transparent", "clear": "transparent",
    "teal": "teal", "turquoise": "teal", "maroon": "maroon", "cream": "cream",
    "蓝色": "blue", "深蓝": "navy blue", "黑色": "black", "白色": "white", "红色": "red",
    "绿色": "green", "黄色": "yellow", "橙色": "orange", "紫色": "purple", "粉色": "pink",
    "灰色": "gray", "银色": "silver", "金色": "gold", "木纹色": "wood", "透明": "transparent",
}
def _alt(keyword: str, plural: bool = False) -> str:
    """Word-bounded regex alternative; spaces also accept hyphens.
    plural=True allows an optional 's'/'es' before the trailing boundary."""
    core = re.escape(keyword).replace(r"\ ", r"[\s\-]+")
    tail = r"(?:es|s)?" if plural else ""
    return r"(?<![A-Za-z0-9])" + core + tail + r"(?![A-Za-z0-9])"


_COLOR_RE = re.compile(
    "(" + "|".join(_alt(k) for k in sorted((k for k in COLORS if k.isascii()), key=len, reverse=True))
    + ")", re.IGNORECASE)
_COLOR_ZH_RE = re.compile("|".join(sorted((k for k in COLORS if not k.isascii()), key=len, reverse=True)))

# ----------------------------------------------------------------------------- materials
MATERIALS = {
    "304 stainless steel": "stainless steel 304", "18/8 stainless steel": "stainless steel 304",
    "ss304": "stainless steel 304", "sus304": "stainless steel 304", "304": "stainless steel 304",
    "316 stainless steel": "stainless steel 316", "ss316": "stainless steel 316",
    "201 stainless steel": "stainless steel 201", "ss201": "stainless steel 201",
    "stainless steel": "stainless steel", "stainless": "stainless steel",
    "borosilicate glass": "borosilicate glass", "high borosilicate glass": "borosilicate glass",
    "glass": "glass", "plastic": "plastic", "pp": "pp plastic", "abs": "abs plastic",
    "tritan": "tritan", "pe": "pe plastic", "petg": "petg", "silicone": "silicone",
    "ceramic": "ceramic", "aluminum": "aluminum", "aluminium": "aluminum",
    "bamboo": "bamboo", "copper": "copper", "iron": "iron", "steel": "steel",
    "纸": "paper", "皮革": "leather", "pu": "pu leather", "polyester": "polyester", "cotton": "cotton",
    "不锈钢": "stainless steel", "304不锈钢": "stainless steel 304", "316不锈钢": "stainless steel 316",
    "玻璃": "glass", "高硼硅玻璃": "borosilicate glass", "塑料": "plastic", "硅胶": "silicone",
    "陶瓷": "ceramic", "铝合金": "aluminum", "竹木": "bamboo", "铜": "copper",
}

# ----------------------------------------------------------------------------- currencies
CURRENCIES = {
    "usd": "USD", "$": "USD", "us$": "USD", "usd$": "USD", "dollar": "USD", "dollars": "USD",
    "美元": "USD", "美金": "USD",
    "eur": "EUR", "€": "EUR", "euro": "EUR", "euros": "EUR", "欧元": "EUR",
    "gbp": "GBP", "£": "GBP", "pound": "GBP", "pounds": "GBP", "英镑": "GBP",
    "cny": "CNY", "rmb": "CNY", "¥": "CNY", "元": "CNY", "人民币": "CNY", "renminbi": "CNY",
    "jpy": "JPY", "aud": "AUD", "cad": "CAD", "aed": "AED", "sar": "SAR", "chf": "CHF", "hkd": "HKD",
}

# ----------------------------------------------------------------------------- countries (alias -> (canonical, iso2))
COUNTRIES = {
    "germany": ("Germany", "DE"), "deutschland": ("Germany", "DE"), "德国": ("Germany", "DE"),
    "usa": ("United States", "US"), "united states": ("United States", "US"), "u.s.": ("United States", "US"),
    "us": ("United States", "US"), "america": ("United States", "US"), "united states of america": ("United States", "US"),
    "美国": ("United States", "US"),
    "uk": ("United Kingdom", "GB"), "united kingdom": ("United Kingdom", "GB"), "britain": ("United Kingdom", "GB"),
    "great britain": ("United Kingdom", "GB"), "england": ("United Kingdom", "GB"), "英国": ("United Kingdom", "GB"),
    "france": ("France", "FR"), "法国": ("France", "FR"),
    "netherlands": ("Netherlands", "NL"), "holland": ("Netherlands", "NL"), "荷兰": ("Netherlands", "NL"),
    "italy": ("Italy", "IT"), "意大利": ("Italy", "IT"),
    "spain": ("Spain", "ES"), "西班牙": ("Spain", "ES"),
    "poland": ("Poland", "PL"), "波兰": ("Poland", "PL"),
    "sweden": ("Sweden", "SE"), "瑞典": ("Sweden", "SE"),
    "norway": ("Norway", "NO"), "挪威": ("Norway", "NO"),
    "denmark": ("Denmark", "DK"), "丹麦": ("Denmark", "DK"),
    "finland": ("Finland", "FI"), "芬兰": ("Finland", "FI"),
    "switzerland": ("Switzerland", "CH"), "瑞士": ("Switzerland", "CH"),
    "austria": ("Austria", "AT"), "奥地利": ("Austria", "AT"),
    "belgium": ("Belgium", "BE"), "比利时": ("Belgium", "BE"),
    "ireland": ("Ireland", "IE"), "爱尔兰": ("Ireland", "IE"),
    "portugal": ("Portugal", "PT"), "葡萄牙": ("Portugal", "PT"),
    "greece": ("Greece", "GR"), "希腊": ("Greece", "GR"),
    "czech republic": ("Czech Republic", "CZ"), "czech": ("Czech Republic", "CZ"), "捷克": ("Czech Republic", "CZ"),
    "hungary": ("Hungary", "HU"), "匈牙利": ("Hungary", "HU"),
    "romania": ("Romania", "RO"), "罗马尼亚": ("Romania", "RO"),
    "ukraine": ("Ukraine", "UA"), "乌克兰": ("Ukraine", "UA"),
    "russia": ("Russia", "RU"), "俄罗斯": ("Russia", "RU"),
    "turkey": ("Turkey", "TR"), "türkiye": ("Turkey", "TR"), "土耳其": ("Turkey", "TR"),
    "uae": ("United Arab Emirates", "AE"), "united arab emirates": ("United Arab Emirates", "AE"),
    "阿联酋": ("United Arab Emirates", "AE"),
    "saudi arabia": ("Saudi Arabia", "SA"), "saudi": ("Saudi Arabia", "SA"), "ksa": ("Saudi Arabia", "SA"),
    "沙特": ("Saudi Arabia", "SA"), "沙特阿拉伯": ("Saudi Arabia", "SA"),
    "qatar": ("Qatar", "QA"), "卡塔尔": ("Qatar", "QA"),
    "kuwait": ("Kuwait", "KW"), "科威特": ("Kuwait", "KW"),
    "oman": ("Oman", "OM"), "阿曼": ("Oman", "OM"),
    "bahrain": ("Bahrain", "BH"), "巴林": ("Bahrain", "BH"),
    "israel": ("Israel", "IL"), "以色列": ("Israel", "IL"),
    "egypt": ("Egypt", "EG"), "埃及": ("Egypt", "EG"),
    "south africa": ("South Africa", "ZA"), "南非": ("South Africa", "ZA"),
    "nigeria": ("Nigeria", "NG"), "尼日利亚": ("Nigeria", "NG"),
    "kenya": ("Kenya", "KE"), "肯尼亚": ("Kenya", "KE"),
    "morocco": ("Morocco", "MA"), "摩洛哥": ("Morocco", "MA"),
    "canada": ("Canada", "CA"), "加拿大": ("Canada", "CA"),
    "mexico": ("Mexico", "MX"), "墨西哥": ("Mexico", "MX"),
    "brazil": ("Brazil", "BR"), "巴西": ("Brazil", "BR"),
    "argentina": ("Argentina", "AR"), "阿根廷": ("Argentina", "AR"),
    "chile": ("Chile", "CL"), "智利": ("Chile", "CL"),
    "colombia": ("Colombia", "CO"), "哥伦比亚": ("Colombia", "CO"),
    "peru": ("Peru", "PE"), "秘鲁": ("Peru", "PE"),
    "australia": ("Australia", "AU"), "澳洲": ("Australia", "AU"), "澳大利亚": ("Australia", "AU"),
    "new zealand": ("New Zealand", "NZ"), "新西兰": ("New Zealand", "NZ"),
    "japan": ("Japan", "JP"), "日本": ("Japan", "JP"),
    "south korea": ("South Korea", "KR"), "korea": ("South Korea", "KR"), "韩国": ("South Korea", "KR"),
    "india": ("India", "IN"), "印度": ("India", "IN"),
    "vietnam": ("Vietnam", "VN"), "越南": ("Vietnam", "VN"),
    "thailand": ("Thailand", "TH"), "泰国": ("Thailand", "TH"),
    "malaysia": ("Malaysia", "MY"), "马来西亚": ("Malaysia", "MY"),
    "indonesia": ("Indonesia", "ID"), "印尼": ("Indonesia", "ID"), "印度尼西亚": ("Indonesia", "ID"),
    "philippines": ("Philippines", "PH"), "菲律宾": ("Philippines", "PH"),
    "singapore": ("Singapore", "SG"), "新加坡": ("Singapore", "SG"),
    "pakistan": ("Pakistan", "PK"), "巴基斯坦": ("Pakistan", "PK"),
    "bangladesh": ("Bangladesh", "BD"), "孟加拉": ("Bangladesh", "BD"),
    "sri lanka": ("Sri Lanka", "LK"), "斯里兰卡": ("Sri Lanka", "LK"),
    "kazakhstan": ("Kazakhstan", "KZ"), "哈萨克斯坦": ("Kazakhstan", "KZ"),
    "dubai": ("United Arab Emirates", "AE"),  # city commonly used as destination
}

# ----------------------------------------------------------------------------- ports (alias -> (canonical_port, country, iso2))
PORTS = {
    "hamburg": ("Hamburg", "Germany", "DE"), "port of hamburg": ("Hamburg", "Germany", "DE"),
    "汉堡": ("Hamburg", "Germany", "DE"),
    "bremerhaven": ("Bremerhaven", "Germany", "DE"), "不来梅哈芬": ("Bremerhaven", "Germany", "DE"),
    "rotterdam": ("Rotterdam", "Netherlands", "NL"), "鹿特丹": ("Rotterdam", "Netherlands", "NL"),
    "antwerp": ("Antwerp", "Belgium", "BE"), "antwerpen": ("Antwerp", "Belgium", "BE"), "安特卫普": ("Antwerp", "Belgium", "BE"),
    "felixstowe": ("Felixstowe", "United Kingdom", "GB"), "费利克斯托": ("Felixstowe", "United Kingdom", "GB"),
    "southampton": ("Southampton", "United Kingdom", "GB"),
    "london gateway": ("London Gateway", "United Kingdom", "GB"),
    "le havre": ("Le Havre", "France", "FR"), "勒阿弗尔": ("Le Havre", "France", "FR"),
    "genoa": ("Genoa", "Italy", "IT"), "genova": ("Genoa", "Italy", "IT"), "热那亚": ("Genoa", "Italy", "IT"),
    "naples": ("Naples", "Italy", "IT"),
    "valencia": ("Valencia", "Spain", "ES"), "巴伦西亚": ("Valencia", "Spain", "ES"),
    "barcelona": ("Barcelona", "Spain", "ES"),
    "algeciras": ("Algeciras", "Spain", "ES"),
    "piraeus": ("Piraeus", "Greece", "GR"), "比雷埃夫斯": ("Piraeus", "Greece", "GR"),
    "gdansk": ("Gdansk", "Poland", "PL"), "格但斯克": ("Gdansk", "Poland", "PL"),
    "gothenburg": ("Gothenburg", "Sweden", "SE"),
    "oslo": ("Oslo", "Norway", "NO"),
    "aarhus": ("Aarhus", "Denmark", "DK"),
    "helsinki": ("Helsinki", "Finland", "FI"),
    "istanbul": ("Istanbul", "Turkey", "TR"), "伊斯坦布尔": ("Istanbul", "Turkey", "TR"),
    "mersin": ("Mersin", "Turkey", "TR"),
    "odessa": ("Odessa", "Ukraine", "UA"),
    "novorossiysk": ("Novorossiysk", "Russia", "RU"),
    "jebel ali": ("Jebel Ali", "United Arab Emirates", "AE"), "dubai": ("Jebel Ali", "United Arab Emirates", "AE"),
    "杰贝阿里": ("Jebel Ali", "United Arab Emirates", "AE"), "迪拜": ("Jebel Ali", "United Arab Emirates", "AE"),
    "dammam": ("Dammam", "Saudi Arabia", "SA"), "达曼": ("Dammam", "Saudi Arabia", "SA"),
    "jeddah": ("Jeddah", "Saudi Arabia", "SA"), "吉达": ("Jeddah", "Saudi Arabia", "SA"),
    "doha": ("Doha", "Qatar", "QA"), "多哈": ("Doha", "Qatar", "QA"),
    "kuwait city": ("Kuwait City", "Kuwait", "KW"),
    "sohar": ("Sohar", "Oman", "OM"), "muscat": ("Muscat", "Oman", "OM"),
    "alexandria": ("Alexandria", "Egypt", "EG"), "port said": ("Port Said", "Egypt", "EG"),
    "durban": ("Durban", "South Africa", "ZA"), "cape town": ("Cape Town", "South Africa", "ZA"),
    "lagos": ("Lagos", "Nigeria", "NG"), "拉各斯": ("Lagos", "Nigeria", "NG"),
    "mombasa": ("Mombasa", "Kenya", "KE"),
    "casablanca": ("Casablanca", "Morocco", "MA"),
    "new york": ("New York", "United States", "US"), "ny": ("New York", "United States", "US"), "纽约": ("New York", "United States", "US"),
    "los angeles": ("Los Angeles", "United States", "US"), "l.a.": ("Los Angeles", "United States", "US"), "洛杉矶": ("Los Angeles", "United States", "US"),
    "long beach": ("Long Beach", "United States", "US"),
    "oakland": ("Oakland", "United States", "US"),
    "seattle": ("Seattle", "United States", "US"), "西雅图": ("Seattle", "United States", "US"),
    "savannah": ("Savannah", "United States", "US"),
    "charleston": ("Charleston", "United States", "US"),
    "norfolk": ("Norfolk", "United States", "US"),
    "houston": ("Houston", "United States", "US"), "休斯顿": ("Houston", "United States", "US"),
    "miami": ("Miami", "United States", "US"), "迈阿密": ("Miami", "United States", "US"),
    "vancouver": ("Vancouver", "Canada", "CA"), "温哥华": ("Vancouver", "Canada", "CA"),
    "toronto": ("Toronto", "Canada", "CA"),
    "manzanillo": ("Manzanillo", "Mexico", "MX"),
    "santos": ("Santos", "Brazil", "BR"), "桑托斯": ("Santos", "Brazil", "BR"),
    "rio de janeiro": ("Rio de Janeiro", "Brazil", "BR"),
    "buenos aires": ("Buenos Aires", "Argentina", "AR"),
    "san antonio": ("San Antonio", "Chile", "CL"),
    "buenaventura": ("Buenaventura", "Colombia", "CO"),
    "callao": ("Callao", "Peru", "PE"),
    "sydney": ("Sydney", "Australia", "AU"), "悉尼": ("Sydney", "Australia", "AU"),
    "melbourne": ("Melbourne", "Australia", "AU"), "墨尔本": ("Melbourne", "Australia", "AU"),
    "brisbane": ("Brisbane", "Australia", "AU"),
    "fremantle": ("Fremantle", "Australia", "AU"),
    "auckland": ("Auckland", "New Zealand", "NZ"),
    "yokohama": ("Yokohama", "Japan", "JP"), "tokyo": ("Tokyo", "Japan", "JP"),
    "osaka": ("Osaka", "Japan", "JP"), "kobe": ("Kobe", "Japan", "JP"),
    "busan": ("Busan", "South Korea", "KR"), "釜山": ("Busan", "South Korea", "KR"),
    "mumbai": ("Mumbai", "India", "IN"), "nhava sheva": ("Nhava Sheva", "India", "IN"),
    "chennai": ("Chennai", "India", "IN"),
    "ho chi minh": ("Ho Chi Minh", "Vietnam", "VN"), "haiphong": ("Haiphong", "Vietnam", "VN"),
    "laem chabang": ("Laem Chabang", "Thailand", "TH"), "bangkok": ("Bangkok", "Thailand", "TH"),
    "port klang": ("Port Klang", "Malaysia", "MY"), "penang": ("Penang", "Malaysia", "MY"),
    "jakarta": ("Jakarta", "Indonesia", "ID"), "surabaya": ("Surabaya", "Indonesia", "ID"),
    "manila": ("Manila", "Philippines", "PH"),
    "singapore port": ("Singapore", "Singapore", "SG"),
    "karachi": ("Karachi", "Pakistan", "PK"), "port qasim": ("Port Qasim", "Pakistan", "PK"),
    "chittagong": ("Chittagong", "Bangladesh", "BD"),
    "colombo": ("Colombo", "Sri Lanka", "LK"),
}

# ----------------------------------------------------------------------------- incoterms
INCOTERMS = {
    "exw": "EXW", "ex works": "EXW", "工厂交货": "EXW",
    "fob": "FOB", "free on board": "FOB", "离岸价": "FOB",
    "cif": "CIF", "cost insurance and freight": "CIF", "到岸价": "CIF",
    "ddp": "DDP", "delivered duty paid": "DDP", "双清包税": "DDP",
    "cfr": "CFR", "cnf": "CFR", "c&f": "CFR",
    "dap": "DAP", "fca": "FCA", "cpt": "CPT", "cip": "CIP", "fas": "FAS",
}

# ----------------------------------------------------------------------------- certifications
CERTIFICATIONS = {
    "fda": "FDA", "u.s. fda": "FDA", "fda approved": "FDA",
    "lfgb": "LFGB", "德国食品级": "LFGB",
    "ce": "CE",
    "rohs": "RoHS",
    "fcc": "FCC",
    "bpa free": "BPA-free", "bpa-free": "BPA-free", "bpafree": "BPA-free", "不含双酚a": "BPA-free",
    "food grade": "food_grade", "food contact": "food_grade", "食品级": "food_grade", "食品接触": "food_grade",
    "prop 65": "CA Prop 65", "ca prop 65": "CA Prop 65", "california prop 65": "CA Prop 65", "ca65": "CA Prop 65",
    "sgs": "SGS", "iso9001": "ISO9001", "iso 9001": "ISO9001",
    "bsci": "BSCI", "sedex": "SEDEX", "cpc": "CPC",
    "ec 1935/2004": "EC1935/2004", "(ec) no 1935/2004": "EC1935/2004", "ec1935/2004": "EC1935/2004", "1935/2004": "EC1935/2004",
    "reach": "REACH", "gs": "GS", "ul": "UL", "bis": "BIS", "saso": "SASO", "halal": "HALAL",
    "kc": "KC", "fsc": "FSC", "gots": "GOTS",
}

# ----------------------------------------------------------------------------- product concepts
PRODUCT_CONCEPTS = {
    "insulated_bottle": {
        "label_zh": "保温杯", "label_en": "Insulated bottle",
        "aliases": ["vacuum flask", "vacuum bottle", "insulated bottle", "insulated water bottle",
                     "thermal bottle", "thermo flask", "thermos flask", "thermos bottle", "thermos",
                     "double wall bottle", "double-wall bottle", "insulated tumbler", "keep warm cup",
                     "vacuum insulated bottle", "stainless steel bottle", "stainless bottle",
                     "保温杯", "保温瓶", "真空杯", "双层真空水瓶", "保温水壶",
                     "thermos cup"],
    },
    "water_bottle": {
        "label_zh": "塑料/运动水杯", "label_en": "Water bottle",
        "aliases": ["water bottle", "sports bottle", "sports bottle", "sport bottle", "plastic water bottle",
                     "sipper bottle", "tritan bottle", "gym bottle", "shaker bottle", "水杯", "运动水壶",
                     "塑料水杯", "吸管杯", "straight drinking cup"],
    },
    "travel_mug": {
        "label_zh": "车载杯", "label_en": "Travel mug",
        "aliases": ["travel mug", "coffee tumbler", "tumbler", "car mug", "car cup", "车用杯", "车载保温杯", "汽车杯"],
    },
    "mug": {
        "label_zh": "马克杯", "label_en": "Mug",
        "aliases": ["mug", "coffee mug", "ceramic mug", "coffee cup", "sublimation mug", "enamel mug",
                     "马克杯", "陶瓷杯", "咖啡杯", "骨瓷杯"],
    },
    "glass_cup": {
        "label_zh": "玻璃杯", "label_en": "Glass cup",
        "aliases": ["glass cup", "glass tumbler", "drinking glass", "glassware", "borosilicate cup",
                     "water glass", "glass", "玻璃杯", "玻璃水杯", "水玻璃杯"],
    },
    "food_container": {
        "label_zh": "保鲜盒/饭盒", "label_en": "Food container",
        "aliases": ["lunch box", "food container", "bento box", "food storage container",
                     "meal prep container", "lunchbox", "饭盒", "保鲜盒", "便当盒", "餐盒"],
    },
    "kettle": {
        "label_zh": "保温壶", "label_en": "Insulated jug/kettle",
        "aliases": ["thermos jug", "insulated jug", "thermal jug", "vacuum jug", "teapot", "kettle",
                     "保温壶", "保温瓶胆壶", "热水壶"],
    },
    "gift_set": {
        "label_zh": "礼品套装", "label_en": "Gift set",
        "aliases": ["gift set", "gift box set", "corporate gift", "promotional gift", "promotional set",
                     "礼品套装", "礼盒套装", "商务礼品"],
    },
    "coffee_maker": {
        "label_zh": "咖啡器具", "label_en": "Coffee maker",
        "aliases": ["french press", "moka pot", "pour over", "coffee maker", "手冲壶", "法压壶", "摩卡壶", "咖啡壶"],
    },
    "baby_bottle": {
        "label_zh": "婴童用品", "label_en": "Baby bottle",
        "aliases": ["baby bottle", "feeding bottle", "sippy cup", "奶瓶", "儿童水杯", "婴儿水杯"],
    },
    "cooler_bag": {
        "label_zh": "保温袋", "label_en": "Cooler bag",
        "aliases": ["cooler bag", "lunch bag", "insulated bag", "保温袋", "冰包", "午餐包"],
    },
}

# ----------------------------------------------------------------------------- packaging
PACKAGING = {
    "color box": "color box", "colour box": "color box", "彩盒": "color box", "彩盒包装": "color box",
    "gift box": "gift box", "礼盒": "gift box",
    "white box": "white box", "白盒": "white box",
    "blister card": "blister card", "blister": "blister card", "吸卡": "blister card",
    "bulk": "bulk packing", "bulk packing": "bulk packing", "散装": "bulk packing",
    "poly bag": "poly bag", "opp bag": "poly bag", "opp袋": "poly bag", "胶袋": "poly bag",
    "display box": "display box", "展示盒": "display box",
    "custom packaging": "custom packaging", "customized packaging": "custom packaging", "定制包装": "custom packaging",
    "mail box": "mail box", "快递盒": "mail box",
}

# ----------------------------------------------------------------------------- quantity parsing
_QTY_RE = re.compile(
    r"(\d[\d,.\s]*\s*(?:k\b)?)\s*(hundred|thousand|pcs|pieces|piece|pc|units|unit|sets|set|dozen|dz|gross|pairs?|k pieces|k pcs)?",
    re.IGNORECASE)
_ZH_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ZH_QTY_RE = re.compile(r"([一二两三四五六七八九])([百千])?\s*(个|只|件|套|支|条)?")

_UNIT_MAP = {
    "pc": "pcs", "pcs": "pcs", "piece": "pcs", "pieces": "pcs", "units": "pcs", "unit": "pcs",
    "set": "sets", "sets": "sets", "dozen": "dozens", "dz": "dozens", "gross": "gross",
    "pair": "pairs", "pairs": "pairs", "个": "pcs", "只": "pcs", "件": "pcs", "套": "sets",
    "支": "pcs", "条": "pcs", "百": None, "千": None, "hundred": None, "thousand": None,
}

_PRICE_RE = re.compile(
    r"(?:(usd|eur|gbp|cny|rmb|aed|aud|cad|\$|€|£|￥|美元|美金|欧元|英镑|元|us\$)\s*)?"
    r"(\d+(?:[.,]\d+)?)"
    r"(?:\s*(?:-|to|~|—)\s*(\d+(?:[.,]\d+)?)?)?"
    r"\s*((?:usd|eur|gbp|cny|rmb|\$|€|£|￥|us\$|美元|美金|欧元|英镑|元)\s*)?"
    r"(?:/|per\s+|每个|每只|每个)?\s*(pc|piece|pcs|unit|个|只|件)?", re.IGNORECASE)

_LEAD_DAYS_RE = re.compile(r"(?:within|in|lead\s*time(?:\s*of)?|delivery(?:\s*time)?:?|交期|交货期|生产周期)\D{0,12}(\d{1,3})\s*(?:days?|working\s*days?|天|个工作日)", re.IGNORECASE)
_MONTHS = {m.lower(): i + 1 for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i + 1 for i, m in enumerate(calendar.month_abbr) if m})


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def _num(s: str) -> float | None:
    s = s.replace(",", "").replace("，", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_number(token: str) -> float | None:
    """'5,000' -> 5000.0; '5k' -> 5000.0; '2-3k' -> take upper (3000)."""
    t = token.strip().lower()
    t = re.sub(r"\s+", "", t)
    m = re.match(r"^(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?(k)?$", t)
    if not m:
        return _num(t)
    a = float(m.group(1))
    b = float(m.group(2)) if m.group(2) else None
    val = b if b is not None else a
    if m.group(3):
        val *= 1000
    return val


# numbers immediately followed by these words are NOT quantities
_NON_QTY_UNITS = ("days", "day", "ml", "oz", "kg", "lb", "cm", "mm", "inch", "%",
                  "usd", "eur", "gbp", "cny", "hours", "years", "working days")
_PRICE_PREFIX = re.compile(
    r"(?:price|usd|eur|gbp|cny|rmb|[\$€£]|budget|cost|@)\s*\d", re.IGNORECASE)
_QTY_UNIT_SUFFIX = re.compile(
    r"\s*(pcs|pieces|piece|pc|units?|sets?|dozen|dz|gross|pairs?)\b", re.IGNORECASE)


def parse_quantity(text: str) -> dict | None:
    """Extract quantity with unit. Returns {value:int, unit, raw} or None.

    Preference: explicit quantity units (pcs/sets/...) > 'k'-suffixed numbers >
    the largest bare number that is not a price / date / volume / weight.
    """
    lower = text.lower()
    zh = _ZH_QTY_RE.search(text)
    with_unit, k_suffixed, bare = [], [], []
    for mm in _QTY_RE.finditer(lower):
        raw_num = mm.group(1)
        val = parse_number(raw_num)
        if val is None or val < 1:
            continue
        unit_raw = (mm.group(2) or "").lower()
        start, end = mm.span(1)
        prefix = lower[max(0, start - 14):start]
        if _PRICE_PREFIX.search(prefix + raw_num):
            continue
        if unit_raw in _UNIT_MAP and _UNIT_MAP[unit_raw] is not None:
            with_unit.append((mm, val, unit_raw))
            continue
        suffix = lower[end:end + 16]
        if _QTY_UNIT_SUFFIX.match(suffix):
            with_unit.append((mm, val, _QTY_UNIT_SUFFIX.match(suffix).group(1).lower()))
            continue
        if raw_num.replace(",", "").rstrip().lower().endswith("k"):
            k_suffixed.append((mm, val, ""))
            continue
        if any(w in suffix for w in _NON_QTY_UNITS):
            continue
        bare.append((mm, val, ""))
    pool = with_unit or k_suffixed or bare
    if not pool:
        if zh:
            n = _ZH_NUM.get(zh.group(1))
            if n:
                mult = 100 if zh.group(2) == "百" else (1000 if zh.group(2) == "千" else 1)
                return {"value": int(n * mult), "unit": "pcs", "raw": zh.group(0)}
        return None
    mm, val, unit_raw = max(pool, key=lambda x: x[1])
    unit = _UNIT_MAP.get(unit_raw, "pcs") or "pcs"
    return {"value": int(val), "unit": unit, "raw": mm.group(0).strip()}


PRICE_TRIGGER_KEYWORDS = ["price", "budget", "cost", "$", "usd", "eur", "€", "£",
                          "target", "目标价", "价格", "预算", "单价"]


def parse_target_price(text: str) -> dict | None:
    """Extract target/budget price: currency + value (+per unit).

    A quantity usually appears BEFORE the price wording in real inquiries
    ("need 1,000 pcs ... target price USD 6/pc"), so we first search after the
    last price keyword; only fall back to the whole text if that yields nothing.
    """
    lower = text.lower()
    if not any(k in lower for k in PRICE_TRIGGER_KEYWORDS):
        return None
    m = None
    keyword_positions = [lower.rfind(k.lower()) for k in PRICE_TRIGGER_KEYWORDS
                         if k.lower() in lower]
    if keyword_positions:
        start = min(max(keyword_positions), max(0, len(text) - 1))
        m = _PRICE_RE.search(text, start)
    if m is None:
        m = _PRICE_RE.search(text)
    if not m:
        return None
    cur_raw = (m.group(1) or m.group(4) or "USD").lower()
    currency = CURRENCIES.get(cur_raw, CURRENCIES.get(cur_raw.strip("$€£￥"), "USD"))
    val = _num(m.group(2))
    val_hi = _num(m.group(3)) if m.group(3) else None
    if val is None:
        return None
    value = val_hi if val_hi is not None else val
    per = (m.group(5) or "pcs").lower()
    per = "pcs" if per in ("pc", "piece", "pcs", "unit", "个", "只", "件") else per
    return {"value": round(value, 4), "currency": currency, "per": per, "raw": m.group(0).strip()}


def normalize_color(text: str) -> str | None:
    m = _COLOR_RE.search(text)
    if m:
        return COLORS.get(m.group(0).lower())
    m = _COLOR_ZH_RE.search(text)
    if m:
        return COLORS.get(m.group(0))
    return None


def find_colors(text: str) -> list[str]:
    """All distinct colors in the text (for conflict detection)."""
    found = []
    for m in _COLOR_RE.finditer(text):
        c = COLORS.get(m.group(0).lower())
        if c and c not in found:
            found.append(c)
    for m in _COLOR_ZH_RE.finditer(text):
        c = COLORS.get(m.group(0))
        if c and c not in found:
            found.append(c)
    return found


def normalize_material(text: str) -> str | None:
    lower = text.lower()
    best = None
    for k, v in MATERIALS.items():
        if k.isascii():
            if re.search(_alt(k), lower) and (best is None or len(k) > len(best[0])):
                best = (k, v)
        elif k in text and (best is None or len(k) > len(best[0])):
            best = (k, v)
    return best[1] if best else None


def normalize_currency(token: str) -> str | None:
    return CURRENCIES.get(token.strip().lower(), CURRENCIES.get(token.strip()))


def normalize_country(text: str) -> tuple | None:
    lower = text.lower().strip()
    if lower in COUNTRIES:
        return COUNTRIES[lower]
    for alias, val in sorted(COUNTRIES.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(alias) + r"\b", lower):
            return val
    for alias, val in COUNTRIES.items():
        if not alias.isascii() and alias in text:
            return val
    return None


def normalize_port(text: str) -> tuple | None:
    lower = text.lower().strip()
    if lower in PORTS:
        return PORTS[lower]
    for alias, val in sorted(PORTS.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(alias) + r"\b", lower):
            return val
    for alias, val in PORTS.items():
        if not alias.isascii() and alias in text:
            return val
    return None


def resolve_place(text: str) -> dict | None:
    """Try port first, then country. Returns {kind, value, country, iso2, raw}."""
    port = normalize_port(text)
    if port:
        return {"kind": "port", "value": port[0], "country": port[1], "iso2": port[2], "raw": text.strip()}
    country = normalize_country(text)
    if country:
        return {"kind": "country", "value": country[0], "country": country[0], "iso2": country[1], "raw": text.strip()}
    return None


def normalize_incoterm(text: str) -> str | None:
    lower = text.lower()
    m = re.search(r"\b(exw|fob|cif|ddp|cfr|cnf|c&f|dap|fca|cpt|cip|fas)\b", lower)
    if m:
        return INCOTERMS[m.group(1)]
    for alias, val in INCOTERMS.items():
        if not alias.isascii() and alias in text:
            return val
    for alias in ("ex works", "free on board", "cost insurance and freight", "delivered duty paid"):
        if alias in lower:
            return INCOTERMS[alias]
    return None


def normalize_certifications(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for alias, canon in sorted(CERTIFICATIONS.items(), key=lambda kv: -len(kv[0])):
        if alias.isascii():
            if re.search(_alt(alias), lower) and canon not in found:
                found.append(canon)
        elif alias in text and canon not in found:
            found.append(canon)
    return found


def canonical_product(text: str) -> dict | None:
    """Map a free-text product mention to a canonical concept (longest alias wins).

    English aliases match case-insensitively with plural ('s'/'es') and
    hyphen/space tolerance, so "vacuum insulated bottles" and
    "stainless-steel bottles" both hit.
    """
    lower = text.lower()
    best = None

    def consider(concept, alias, meta):
        nonlocal best
        if best is None or len(alias) > len(best["alias"]):
            best = {"concept": concept, "alias": alias, "label_zh": meta["label_zh"],
                    "label_en": meta["label_en"], "raw": text.strip()}

    for concept, meta in PRODUCT_CONCEPTS.items():
        for alias in meta["aliases"]:
            a = alias.lower()
            if a.isascii():
                if re.search(_alt(a, plural=True), lower):
                    consider(concept, a, meta)
            elif alias in text:
                consider(concept, alias, meta)
    return best


def concept_synonyms(concept: str) -> list[str]:
    return list(PRODUCT_CONCEPTS.get(concept, {}).get("aliases", []))


def concept_labels(concept: str) -> dict:
    meta = PRODUCT_CONCEPTS.get(concept, {})
    return {"label_zh": meta.get("label_zh", concept), "label_en": meta.get("label_en", concept)}


def normalize_packaging(text: str) -> str | None:
    lower = text.lower()
    best = None
    for k, v in PACKAGING.items():
        if (k.isascii() and k in lower) or (not k.isascii() and k in text):
            if best is None or len(k) > len(best[0]):
                best = (k, v)
    return best[1] if best else None


CUSTOM_PATTERNS = [
    (re.compile(r"\b(our|company|client'?s?)\s+(own\s+)?logo\b|\blogo\b|\bprinted\b|\bprint(ing)?\b|silk.?screen|laser|engrav|印花|丝印|激光|刻字|印logo|印字", re.I), "logo_print"),
    (re.compile(r"\boem\b", re.I), "OEM"),
    (re.compile(r"\bodm\b", re.I), "ODM"),
    (re.compile(r"custom(ized)?\s+(packaging|box|color|design)|定制|自定义包装", re.I), "custom_design"),
]


def detect_customization(text: str) -> list[str]:
    found = []
    for rx, val in CUSTOM_PATTERNS:
        if rx.search(text) and val not in found:
            found.append(val)
    return found


NEGATION_PATTERNS = [
    (re.compile(r"\bany\s+colou?r\b|\bno\s+(color|colour)\s+(preference|requirement)|\bcolou?r\s+(doesn'?t|does\s*not)\s+matter\b|颜色无所谓|颜色都可以|随便什么颜色", re.I), "color"),
    (re.compile(r"\bany\s+material\b|材质无所谓|材质都可以", re.I), "material"),
    (re.compile(r"\bno\s+logo\b|\bwithout\s+logo\b|不带logo|不要logo", re.I), "customization"),
    (re.compile(r"\bpackaging\s+(is\s+)?(not|no)\s+(an?\s+)?(issue|important)|包装无所谓|包装都可以", re.I), "packaging"),
]


def detect_unconstrained(text: str) -> list[str]:
    """Fields the buyer explicitly says they have no constraint on."""
    return [field for rx, field in NEGATION_PATTERNS if rx.search(text)]


def parse_lead_time(text: str, today: datetime | None = None) -> dict | None:
    """Return {days:int} or {date:'YYYY-MM-DD'}; None when not found."""
    today = today or datetime.now(timezone.utc)
    m = _LEAD_DAYS_RE.search(text)
    if m:
        return {"days": int(m.group(1)), "raw": m.group(0).strip()}
    dm = re.search(r"\b(by|before|until)\s+(\d{4}-\d{1,2}-\d{1,2})\b", text, re.IGNORECASE)
    if dm:
        try:
            d = datetime.strptime(dm.group(2), "%Y-%m-%d")
            days = max((d - today).days, 0)
            return {"days": days, "raw": dm.group(0).strip()}
        except ValueError:
            pass
    dm = re.search(r"\b(by|before|until)\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\b", text, re.IGNORECASE)
    if dm and dm.group(3).lower() in _MONTHS:
        month = _MONTHS[dm.group(3).lower()]
        day = int(dm.group(2))
        try:
            d = datetime(today.year + (1 if month < today.month else 0), month, day, tzinfo=timezone.utc)
            return {"days": max((d - today).days, 0), "raw": dm.group(0).strip()}
        except ValueError:
            return None
    dm = re.search(r"\b(by|before|until)\s+([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", text, re.IGNORECASE)
    if dm and dm.group(2).lower() in _MONTHS:
        month = _MONTHS[dm.group(2).lower()]
        day = int(dm.group(3))
        try:
            d = datetime(today.year + (1 if month < today.month else 0), month, day, tzinfo=timezone.utc)
            return {"days": max((d - today).days, 0), "raw": dm.group(0).strip()}
        except ValueError:
            return None
    em = re.search(r"\b(end\s+of)\s+([A-Za-z]+)\b", text, re.IGNORECASE)
    if em and em.group(2).lower() in _MONTHS:
        month = _MONTHS[em.group(2).lower()]
        year = today.year + (1 if month < today.month else 0)
        d = datetime(year, month, calendar.monthrange(year, month)[1], tzinfo=timezone.utc)
        return {"days": max((d - today).days, 0), "raw": em.group(0).strip()}
    return None
