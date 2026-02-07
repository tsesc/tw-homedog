"""Preset configuration templates for quick bot setup."""

from tw_homedog.regions import REGION_CODES

TEMPLATES: list[dict] = [
    {
        "id": "buy_family_taipei",
        "name": "台北家庭自住",
        "description": "內湖/南港/文山/士林/北投 2000-4000萬 30坪+",
        "mode": "buy",
        "region": REGION_CODES["台北市"],
        "districts": ["內湖區", "南港區", "文山區", "士林區", "北投區"],
        "price_min": 2000,
        "price_max": 4000,
        "min_ping": 30,
        "keywords_exclude": ["頂加", "工業宅"],
    },
    {
        "id": "buy_single_taipei",
        "name": "台北單身首購",
        "description": "中山/松山/大安/信義/南港 1000-2000萬 15坪+",
        "mode": "buy",
        "region": REGION_CODES["台北市"],
        "districts": ["中山區", "松山區", "大安區", "信義區", "南港區"],
        "price_min": 1000,
        "price_max": 2000,
        "min_ping": 15,
        "keywords_exclude": ["頂加", "工業宅"],
    },
    {
        "id": "buy_invest_newtaipei",
        "name": "新北投資置產",
        "description": "板橋/中和/永和/新莊/三重/汐止/林口 800-1500萬 15坪+",
        "mode": "buy",
        "region": REGION_CODES["新北市"],
        "districts": ["板橋區", "中和區", "永和區", "新莊區", "三重區", "汐止區", "林口區"],
        "price_min": 800,
        "price_max": 1500,
        "min_ping": 15,
        "keywords_exclude": ["頂加", "工業宅"],
    },
    {
        "id": "buy_family_taoyuan",
        "name": "桃園家庭",
        "description": "桃園/中壢/八德/龜山/蘆竹 800-1500萬 30坪+",
        "mode": "buy",
        "region": REGION_CODES["桃園市"],
        "districts": ["桃園區", "中壢區", "八德區", "龜山區", "蘆竹區"],
        "price_min": 800,
        "price_max": 1500,
        "min_ping": 30,
        "keywords_exclude": ["頂加", "工業宅"],
    },
    {
        "id": "buy_family_taichung",
        "name": "台中家庭",
        "description": "西屯/南屯/北屯/北/西/南 1000-2500萬 30坪+",
        "mode": "buy",
        "region": REGION_CODES["台中市"],
        "districts": ["西屯區", "南屯區", "北屯區", "北區", "西區", "南區"],
        "price_min": 1000,
        "price_max": 2500,
        "min_ping": 30,
        "keywords_exclude": ["頂加", "工業宅"],
    },
    {
        "id": "rent_single_taipei",
        "name": "台北租屋",
        "description": "大安/中山/松山/信義 15000-30000/月 10坪+",
        "mode": "rent",
        "region": REGION_CODES["台北市"],
        "districts": ["大安區", "中山區", "松山區", "信義區"],
        "price_min": 15000,
        "price_max": 30000,
        "min_ping": 10,
        "keywords_exclude": ["頂加", "分租"],
    },
]


def get_template(template_id: str) -> dict | None:
    """Get a template by its ID. Returns None if not found."""
    for t in TEMPLATES:
        if t["id"] == template_id:
            return t
    return None


def apply_template(template_id: str) -> dict:
    """Convert a template to a flat dict ready for db_config.set_many().

    Raises KeyError if template_id not found.
    """
    t = get_template(template_id)
    if t is None:
        raise KeyError(f"Template not found: {template_id}")

    result = {
        "search.mode": t["mode"],
        "search.region": t["region"],
        "search.districts": t["districts"],
        "search.price_min": t["price_min"],
        "search.price_max": t["price_max"],
    }
    if t.get("min_ping") is not None:
        result["search.min_ping"] = t["min_ping"]
    if t.get("keywords_exclude"):
        result["search.keywords_exclude"] = t["keywords_exclude"]
    return result
