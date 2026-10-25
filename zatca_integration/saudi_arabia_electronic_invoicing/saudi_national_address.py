"""Saudi National Address reference data for ZATCA postal addresses.

ZATCA rejected the address data on sico's invoices as "Inaccurate Seller/Buyer
Address Data ... specifically the Postal Zone (Postal Code) and City Names".
Both come from the same rule set:

* BR-KSA-67 - when the buyer country code (BT-55) is ``SA`` the buyer postal code
  (BT-53) must be 5 digits. A Bahraini ``5021`` is a *valid* postal code, it is
  only refused because the old mapping sent ``SA`` for every address. A Saudi
  address must carry a real 5-digit postal code.
* The City Name (BT-54) must be one of the cities published in the Saudi
  National Address database (Saudi Post / SPL), spelled the official way -
  ``dammam``, ``AL KHUBAR``, ``Ad Dammam`` and ``Damam`` all reach ZATCA as an
  unknown city name.

Reference invoice: ACC-SINV-2026-03376 (site ``sico``), a Bahraini buyer whose
address was emitted with ``IdentificationCode`` SA and postal code ``5021``.

The list below is the National Address city list (cities / governorates) with
their region. ``Zatca Settings`` can extend it for a locality that is missing:

    * ``extra_saudi_cities``          - one additional city name per line
    * ``skip_saudi_city_validation``  - downgrade "unknown city" to a warning
"""

from __future__ import annotations

import difflib
import re
import unicodedata

import frappe
from frappe import _
from frappe.utils import cint

ZATCA_SETTINGS = "Zatca Settings"
SAUDI_ARABIA = "Saudi Arabia"

# A Saudi postal code is exactly 5 digits and never starts with 0 (10000-99999).
POSTAL_CODE_PATTERN = re.compile(r"^[1-9][0-9]{4}$")

# How close a typed city name must be to a National Address city to be corrected
# automatically instead of refused (typos such as "Damam" -> "Dammam").
FUZZY_CUTOFF = 0.84
FUZZY_MIN_LENGTH = 4

# Minimum similarity for "Did you mean ..." suggestions (looser than the
# automatic correction, but close enough to be useful).
SUGGESTION_CUTOFF = 0.8

# How many "Did you mean ..." suggestions an error message shows.
SUGGESTION_LIMIT = 3

# Official city name -> {"region": ..., "arabic": ...}
SAUDI_CITIES = {
    # ------------------------------------------------------------- Riyadh
    "Riyadh": {"region": "Riyadh", "arabic": "الرياض"},
    "Al Kharj": {"region": "Riyadh", "arabic": "الخرج"},
    "Ad Dilam": {"region": "Riyadh"},
    "Al Hayer": {"region": "Riyadh"},
    "Al Hariq": {"region": "Riyadh", "arabic": "الحريق"},
    "Al Aflaj": {"region": "Riyadh", "arabic": "الأفلاج"},
    "Layla": {"region": "Riyadh"},
    "Wadi Ad Dawasir": {"region": "Riyadh", "arabic": "وادي الدواسر"},
    "As Sulayyil": {"region": "Riyadh", "arabic": "السليل"},
    "Al Hayathim": {"region": "Riyadh"},
    "Afif": {"region": "Riyadh", "arabic": "عفيف"},
    "Al Majmaah": {"region": "Riyadh", "arabic": "المجمعة"},
    "Al Muzahimiyah": {"region": "Riyadh", "arabic": "المزاحمية"},
    "Al Quwaiyah": {"region": "Riyadh", "arabic": "القويعية"},
    "Al Ghat": {"region": "Riyadh", "arabic": "الغاط"},
    "Az Zulfi": {"region": "Riyadh", "arabic": "الزلفي"},
    "Shaqra": {"region": "Riyadh", "arabic": "شقراء"},
    "Huraymila": {"region": "Riyadh", "arabic": "حريملاء"},
    "Thadiq": {"region": "Riyadh", "arabic": "ثادق"},
    "Rumah": {"region": "Riyadh", "arabic": "رماح"},
    "Marat": {"region": "Riyadh", "arabic": "مرات"},
    "Dhurma": {"region": "Riyadh", "arabic": "ضرما"},
    "Hotat Bani Tamim": {"region": "Riyadh", "arabic": "حوطة بني تميم"},
    # ------------------------------------------------------------- Makkah
    "Makkah": {"region": "Makkah", "arabic": "مكة المكرمة"},
    "Jeddah": {"region": "Makkah", "arabic": "جدة"},
    "Taif": {"region": "Makkah", "arabic": "الطائف"},
    "Al Lith": {"region": "Makkah", "arabic": "الليث"},
    "Al Qunfudhah": {"region": "Makkah", "arabic": "القنفذة"},
    "Rabigh": {"region": "Makkah", "arabic": "رابغ"},
    "Khulays": {"region": "Makkah", "arabic": "خليص"},
    "Al Kamil": {"region": "Makkah", "arabic": "الكامل"},
    "Al Jumum": {"region": "Makkah", "arabic": "الجموم"},
    "Bahrah": {"region": "Makkah", "arabic": "بحرة"},
    "Mastourah": {"region": "Makkah", "arabic": "المستورة"},
    "Al Muwayh": {"region": "Makkah", "arabic": "المويه"},
    "Maysan": {"region": "Makkah", "arabic": "ميسان"},
    "Turbah": {"region": "Makkah", "arabic": "تربة"},
    "Ranyah": {"region": "Makkah", "arabic": "رنية"},
    "Al Khurmah": {"region": "Makkah", "arabic": "الخرمة"},
    "Adham": {"region": "Makkah", "arabic": "أضم"},
    "Al Ardiyat": {"region": "Makkah", "arabic": "العرضيات"},
    "Ash Shuaibah": {"region": "Makkah"},
    "As Sail Al Kabir": {"region": "Makkah"},
    # ------------------------------------------------------------ Madinah
    "Madinah": {"region": "Madinah", "arabic": "المدينة المنورة"},
    "Yanbu": {"region": "Madinah", "arabic": "ينبع"},
    "Al Ula": {"region": "Madinah", "arabic": "العلا"},
    "Badr": {"region": "Madinah", "arabic": "بدر"},
    "Al Mahd": {"region": "Madinah", "arabic": "المهد"},
    "Khaybar": {"region": "Madinah", "arabic": "خيبر"},
    "Al Henakiyah": {"region": "Madinah", "arabic": "الحناكية"},
    "Wadi Al Fara": {"region": "Madinah", "arabic": "وادي الفرع"},
    "Ar Rayis": {"region": "Madinah", "arabic": "الرايس"},
    "As Suwayriqiyah": {"region": "Madinah", "arabic": "السويرقية"},
    "Al Furaysh": {"region": "Madinah", "arabic": "الفريش"},
    # ------------------------------------------------------------- Qassim
    "Buraydah": {"region": "Qassim", "arabic": "بريدة"},
    "Unaizah": {"region": "Qassim", "arabic": "عنيزة"},
    "Ar Rass": {"region": "Qassim", "arabic": "الرس"},
    "Al Bukayriyah": {"region": "Qassim", "arabic": "البكيرية"},
    "Al Mithnab": {"region": "Qassim", "arabic": "المذنب"},
    "Al Badaya": {"region": "Qassim", "arabic": "البدائع"},
    "Al Asyah": {"region": "Qassim", "arabic": "الأسياح"},
    "An Nabhaniyah": {"region": "Qassim", "arabic": "النبهانية"},
    "Riyadh Al Khabra": {"region": "Qassim", "arabic": "رياض الخبراء"},
    "Uyun Al Jawa": {"region": "Qassim", "arabic": "عيون الجواء"},
    "Ash Shimasiyah": {"region": "Qassim", "arabic": "الشماسية"},
    "Al Khabra": {"region": "Qassim"},
    # ---------------------------------------------------- Eastern Province
    "Dammam": {"region": "Eastern Province", "arabic": "الدمام"},
    "Al Khobar": {"region": "Eastern Province", "arabic": "الخبر"},
    "Dhahran": {"region": "Eastern Province", "arabic": "الظهران"},
    "Jubail": {"region": "Eastern Province", "arabic": "الجبيل"},
    "Qatif": {"region": "Eastern Province", "arabic": "القطيف"},
    "Saihat": {"region": "Eastern Province", "arabic": "سيهات"},
    "Safwa": {"region": "Eastern Province", "arabic": "صفوى"},
    "Ras Tanura": {"region": "Eastern Province", "arabic": "رأس تنورة"},
    "Abqaiq": {"region": "Eastern Province", "arabic": "بقيق"},
    "Al Ahsa": {"region": "Eastern Province", "arabic": "الأحساء"},
    "Hofuf": {"region": "Eastern Province", "arabic": "الهفوف"},
    "Al Mubarraz": {"region": "Eastern Province", "arabic": "المبرز"},
    "Al Uyun": {"region": "Eastern Province", "arabic": "العيون"},
    "Al Badiyah": {"region": "Eastern Province"},
    "Al Khafji": {"region": "Eastern Province", "arabic": "الخفجي"},
    "Hafar Al Batin": {"region": "Eastern Province", "arabic": "حفر الباطن"},
    "An Nairyah": {"region": "Eastern Province", "arabic": "النعيرية"},
    "Qaryat Al Ulya": {"region": "Eastern Province", "arabic": "قرية العليا"},
    "Al Qaisumah": {"region": "Eastern Province", "arabic": "القيصومة"},
    "Tarut": {"region": "Eastern Province", "arabic": "تاروت"},
    "Anak": {"region": "Eastern Province", "arabic": "عنك"},
    "Al Jish": {"region": "Eastern Province", "arabic": "الجش"},
    "Al Qudaih": {"region": "Eastern Province", "arabic": "القديح"},
    "Al Awjam": {"region": "Eastern Province", "arabic": "العوامية"},
    "Haradh": {"region": "Eastern Province", "arabic": "حرض"},
    # ---------------------------------------------------------------- Asir
    "Abha": {"region": "Asir", "arabic": "أبها"},
    "Khamis Mushait": {"region": "Asir", "arabic": "خميس مشيط"},
    "Bisha": {"region": "Asir", "arabic": "بيشة"},
    "An Namas": {"region": "Asir", "arabic": "النماص"},
    "Tanumah": {"region": "Asir", "arabic": "تنومة"},
    "Muhayil": {"region": "Asir", "arabic": "محايل"},
    "Rijal Almaa": {"region": "Asir", "arabic": "رجال ألمع"},
    "Sabt Al Alayah": {"region": "Asir", "arabic": "سبت العلاية"},
    "Al Majardah": {"region": "Asir", "arabic": "المجاردة"},
    "Al Birk": {"region": "Asir", "arabic": "البرك"},
    "Bareq": {"region": "Asir", "arabic": "بارق"},
    "Ahad Rufeidah": {"region": "Asir", "arabic": "أحد رفيدة"},
    "Dhahran Al Janub": {"region": "Asir", "arabic": "ظهران الجنوب"},
    "Tathlith": {"region": "Asir", "arabic": "تثليث"},
    "Sarat Abidah": {"region": "Asir", "arabic": "سراة عبيدة"},
    # --------------------------------------------------------------- Tabuk
    "Tabuk": {"region": "Tabuk", "arabic": "تبوك"},
    "Al Wajh": {"region": "Tabuk", "arabic": "الوجه"},
    "Duba": {"region": "Tabuk", "arabic": "ضبا"},
    "Haql": {"region": "Tabuk", "arabic": "حقل"},
    "Umluj": {"region": "Tabuk", "arabic": "أملج"},
    "Tayma": {"region": "Tabuk", "arabic": "تيماء"},
    "Al Bad": {"region": "Tabuk", "arabic": "البدع"},
    # ---------------------------------------------------------------- Hail
    "Hail": {"region": "Hail", "arabic": "حائل"},
    "Baqaa": {"region": "Hail", "arabic": "بقاع"},
    "Al Ghazalah": {"region": "Hail", "arabic": "الغزالة"},
    "Ash Shinan": {"region": "Hail", "arabic": "الشنان"},
    "Al Hayit": {"region": "Hail", "arabic": "الحائط"},
    "Mawqaq": {"region": "Hail", "arabic": "موقق"},
    "Jubbah": {"region": "Hail", "arabic": "جبة"},
    "As Sulaymi": {"region": "Hail", "arabic": "السليمي"},
    "Samira": {"region": "Hail", "arabic": "سميراء"},
    # --------------------------------------------------- Northern Borders
    "Arar": {"region": "Northern Borders", "arabic": "عرعر"},
    "Rafha": {"region": "Northern Borders", "arabic": "رفحاء"},
    "Turaif": {"region": "Northern Borders", "arabic": "طريف"},
    # --------------------------------------------------------------- Jazan
    "Jazan": {"region": "Jazan", "arabic": "جازان"},
    "Sabya": {"region": "Jazan", "arabic": "صبيا"},
    "Abu Arish": {"region": "Jazan", "arabic": "أبو عريش"},
    "Samtah": {"region": "Jazan", "arabic": "صامطة"},
    "Baysh": {"region": "Jazan", "arabic": "بيش"},
    "Ad Darb": {"region": "Jazan", "arabic": "الدرب"},
    "Al Aydabi": {"region": "Jazan", "arabic": "العيدابي"},
    "Al Aridah": {"region": "Jazan", "arabic": "العريضة"},
    "Al Dayr": {"region": "Jazan", "arabic": "الداير"},
    "Al Harth": {"region": "Jazan", "arabic": "الحرث"},
    "Farasan": {"region": "Jazan", "arabic": "فرسان"},
    "Ash Shuqayq": {"region": "Jazan", "arabic": "الشقيق"},
    # -------------------------------------------------------------- Najran
    "Najran": {"region": "Najran", "arabic": "نجران"},
    "Sharurah": {"region": "Najran", "arabic": "شرورة"},
    "Hubuna": {"region": "Najran", "arabic": "حبونا"},
    "Badr Al Janoub": {"region": "Najran", "arabic": "بدر الجنوب"},
    "Thar": {"region": "Najran", "arabic": "ثار"},
    "Yadamah": {"region": "Najran", "arabic": "يدماة"},
    "Al Kharkhir": {"region": "Najran", "arabic": "الخرخير"},
    # ------------------------------------------------------------ Al Bahah
    "Al Bahah": {"region": "Al Bahah", "arabic": "الباحة"},
    "Baljurashi": {"region": "Al Bahah", "arabic": "بلجرشي"},
    "Al Mandaq": {"region": "Al Bahah", "arabic": "المندق"},
    "Al Aqiq": {"region": "Al Bahah", "arabic": "العقيق"},
    "Al Mikhwah": {"region": "Al Bahah", "arabic": "المخواة"},
    "Qilwah": {"region": "Al Bahah", "arabic": "قلوة"},
    # ------------------------------------------------------------- Al Jouf
    "Sakaka": {"region": "Al Jouf", "arabic": "سكاكا"},
    "Al Qurayyat": {"region": "Al Jouf", "arabic": "القريات"},
    "Dumat Al Jandal": {"region": "Al Jouf", "arabic": "دومة الجندل"},
    "Tabarjal": {"region": "Al Jouf", "arabic": "طبرجل"},
}

# The 13 regions (provinces) of Saudi Arabia - the ISO 3166-2:SA subdivisions.
SAUDI_REGIONS = {
    "Riyadh": "Riyadh",
    "Makkah": "Makkah",
    "Madinah": "Madinah",
    "Qassim": "Qassim",
    "Eastern Province": "Eastern Province",
    "Asir": "Asir",
    "Tabuk": "Tabuk",
    "Hail": "Hail",
    "Northern Borders": "Northern Borders",
    "Jazan": "Jazan",
    "Najran": "Najran",
    "Al Bahah": "Al Bahah",
    "Al Jouf": "Al Jouf",
}

# Spelling variants that are NOT a simple case/space difference from the official
# name. Keys are normalized (see normalize_city_name); values are official names.
CITY_ALIASES = {
    # Riyadh
    "riyad": "Riyadh",
    "riyadh city": "Riyadh",
    "ar riyad": "Riyadh",
    "al riyadh": "Riyadh",
    "al kharj city": "Al Kharj",
    "kharj": "Al Kharj",
    "zulfi": "Az Zulfi",
    "al zulfi": "Az Zulfi",
    "majmaah": "Al Majmaah",
    "majma ah": "Al Majmaah",
    "dawasir": "Wadi Ad Dawasir",
    "wadi aldawasir": "Wadi Ad Dawasir",
    "sulayyil": "As Sulayyil",
    "aflaj": "Al Aflaj",
    "hotat bani tameem": "Hotat Bani Tamim",
    "quwaiya": "Al Quwaiyah",
    "quwaiyah": "Al Quwaiyah",
    # Makkah
    "mecca": "Makkah",
    "makkah al mukarramah": "Makkah",
    "makkah almukarramah": "Makkah",
    "makkah mukarramah": "Makkah",
    "jedda": "Jeddah",
    "jiddah": "Jeddah",
    "taif city": "Taif",
    "at taif": "Taif",
    "qunfudha": "Al Qunfudhah",
    "qunfudah": "Al Qunfudhah",
    "leeth": "Al Lith",
    "rabigh city": "Rabigh",
    # Madinah
    "medina": "Madinah",
    "al madinah": "Madinah",
    "al madinah al munawwarah": "Madinah",
    "madinah al munawwarah": "Madinah",
    "yanbu al bahr": "Yanbu",
    "yanbu al sinaiyah": "Yanbu",
    "al ula city": "Al Ula",
    "alola": "Al Ula",
    # Qassim
    "buraidah": "Buraydah",
    "buraida": "Buraydah",
    "unizah": "Unaizah",
    "anaizah": "Unaizah",
    "rass": "Ar Rass",
    "bukayriah": "Al Bukayriyah",
    "muthnib": "Al Mithnab",
    # Eastern Province
    "damam": "Dammam",
    "damma": "Dammam",
    "dammam city": "Dammam",
    "ad dammam": "Dammam",
    "al dammam": "Dammam",
    "khobar": "Al Khobar",
    "al khubar": "Al Khobar",
    "khubar": "Al Khobar",
    "khober": "Al Khobar",
    "al khober": "Al Khobar",
    "al khobar city": "Al Khobar",
    "jubayl": "Jubail",
    "al jubayl": "Jubail",
    "al jubail": "Jubail",
    "al qatif": "Qatif",
    "qateef": "Qatif",
    "sayhat": "Saihat",
    "al sayhat": "Saihat",
    "ras tannurah": "Ras Tanura",
    "ras tanoura": "Ras Tanura",
    "buqayq": "Abqaiq",
    "buqaiq": "Abqaiq",
    "hafuf": "Hofuf",
    "al hafuf": "Hofuf",
    "al hufuf": "Hofuf",
    "hufuf": "Hofuf",
    "ahsa": "Al Ahsa",
    "al hasa": "Al Ahsa",
    "hasa": "Al Ahsa",
    "mubaraz": "Al Mubarraz",
    "al mubaraz": "Al Mubarraz",
    "mobarraz": "Al Mubarraz",
    "oyun": "Al Uyun",
    "al oyun": "Al Uyun",
    "hafar al batin city": "Hafar Al Batin",
    "hafar albatin": "Hafar Al Batin",
    "khafji": "Al Khafji",
    "an nu ayriyah": "An Nairyah",
    "nu ayriyah": "An Nairyah",
    "al nuayriyah": "An Nairyah",
    "tarout": "Tarut",
    "al tarout": "Tarut",
    "anak city": "Anak",
    "inak": "Anak",
    "al awamiyah": "Al Awjam",
    "awamiyah": "Al Awjam",
    "buqaya": "Abqaiq",
    # Asir
    "khamis mushayt": "Khamis Mushait",
    "khamis musheet": "Khamis Mushait",
    "namas": "An Namas",
    "al namas": "An Namas",
    "muhayel": "Muhayil",
    "mahayel": "Muhayil",
    "rijal al maa": "Rijal Almaa",
    "bisha city": "Bisha",
    # Tabuk
    "tabouk": "Tabuk",
    "al wajh city": "Al Wajh",
    "wajh": "Al Wajh",
    "dhiba": "Duba",
    "umluj city": "Umluj",
    # Hail
    "ha il": "Hail",
    "hayel": "Hail",
    "hail city": "Hail",
    # Northern Borders
    "ar ar": "Arar",
    "rafhaa": "Rafha",
    # Jazan
    "jizan": "Jazan",
    "gizan": "Jazan",
    "samtah": "Samtah",
    "baish": "Baysh",
    "abou arish": "Abu Arish",
    # Najran
    "najran city": "Najran",
    # Al Bahah
    "al baha": "Al Bahah",
    "baha": "Al Bahah",
    "baljorashi": "Baljurashi",
    "almikhwah": "Al Mikhwah",
    # Al Jouf
    "qurayyat": "Al Qurayyat",
    "al qurayat": "Al Qurayyat",
    "dawmat al jandal": "Dumat Al Jandal",
}

_ARTICLE_PREFIXES = ("al ", "ad ", "ar ", "as ", "az ", "at ", "el ")


def normalize_city_name(value: str) -> str:
    """Case / punctuation / diacritic insensitive form of a city name."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("'", " ").replace("\u2019", " ").replace("-", " ")
    text = re.sub(r"[^0-9a-z\u0600-\u06ff ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for suffix in (" city", " municipality", " governorate"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def _strip_article(key: str) -> str:
    for prefix in _ARTICLE_PREFIXES:
        if key.startswith(prefix) and len(key) > len(prefix) + 2:
            return key[len(prefix) :]
    return key


def _keys_for(name: str) -> set[str]:
    key = normalize_city_name(name)
    if not key:
        return set()
    stripped = _strip_article(key)
    return {key, stripped} if stripped != key else {key}


def _city_keys(value: str) -> list[str]:
    """Lookup keys for a typed value, most specific first.

    A postal code or building number typed into the City Name ("Al Jubail
    35717-7459") is ignored instead of refused: ZATCA only reads the name.
    """
    key = normalize_city_name(value)
    if not key:
        return []

    keys: list[str] = []
    for candidate in (key, " ".join(token for token in key.split() if not token.isdigit())):
        for variant in (candidate, _strip_article(candidate)):
            if variant and variant not in keys:
                keys.append(variant)
    return keys


def _script_parts(value: str) -> list[str]:
    """Split "الدمام Dammam" into its Arabic and Latin halves."""
    raw = str(value or "").strip()
    parts = [
        re.sub(r"[^\u0600-\u06ff ]+", " ", raw).strip(),
        re.sub(r"[\u0600-\u06ff]+", " ", raw).strip(),
    ]
    return [part for part in parts if part and part != raw]


def _build_city_index() -> dict[str, str]:
    """normalized spelling (English + Arabic + aliases) -> official city name."""
    index: dict[str, str] = {}
    for name, details in SAUDI_CITIES.items():
        for key in _keys_for(name):
            index.setdefault(key, name)
        arabic = str(details.get("arabic") or "").strip()
        if arabic:
            index.setdefault(normalize_city_name(arabic), name)
    for alias, name in CITY_ALIASES.items():
        index.setdefault(normalize_city_name(alias), name)
    return index


_CITY_INDEX = _build_city_index()


def get_city_validation_settings() -> dict:
    """The city switches on "Zatca Settings".

    ``skip_saudi_city_validation`` turns an unknown city name into a warning and
    ``extra_saudi_cities`` holds additional city names (one per line) for a
    locality that is missing from the list above.
    """
    try:
        values = frappe.db.get_singles_dict(ZATCA_SETTINGS) or {}
    except Exception:
        # Fresh install / tests: no site, no settings table, or the fields are
        # not migrated yet - strict validation with the built-in list applies.
        values = {}

    return {
        "skip_city_validation": bool(cint(values.get("skip_saudi_city_validation"))),
        "extra_cities": [
            line.strip()
            for line in str(values.get("extra_saudi_cities") or "").splitlines()
            if line.strip()
        ],
    }


def city_index() -> dict[str, str]:
    """Built-in index plus the ``extra_saudi_cities`` from Zatca Settings."""
    extra = get_city_validation_settings()["extra_cities"]
    if not extra:
        return _CITY_INDEX

    index = dict(_CITY_INDEX)
    for name in extra:
        for key in _keys_for(name):
            index.setdefault(key, name)
    return index


def canonical_city_name(value: str) -> str | None:
    """The official Saudi National Address spelling, or ``None`` when unknown.

    Matching is forgiving on purpose: letter case ("AL KHUBAR"), articles
    ("Ad Dammam"), transliteration ("Riyad", "Buqayq", "AL HAFUF"), a postal
    code typed after the name ("Al Jubail 35717-7459"), Arabic ("الرياض", also
    "الدمام Dammam") and small typos ("Damam") all resolve to the official
    name, because a data entry difference must not become a ZATCA "inaccurate
    address" finding.
    """
    keys = _city_keys(value)
    if not keys:
        return None

    index = city_index()
    for key in keys:
        if key in index:
            return index[key]

    for part in _script_parts(value):
        for key in _city_keys(part):
            if key in index:
                return index[key]

    for key in keys:
        if len(key) < FUZZY_MIN_LENGTH:
            continue
        match = difflib.get_close_matches(key, index.keys(), n=1, cutoff=FUZZY_CUTOFF)
        if match:
            return index[match[0]]
    return None


def _match_score(query: str, candidate: str) -> float:
    """How well one lookup key matches what the user typed (0 = no match).

    Ranked so a type-ahead list is ordered the way a person expects: the exact
    name, then names that start with the typed text ("kho" -> "Al Khobar"), then
    names with a word that starts with it, and only then a typo ("Damamm" ->
    "Dammam"). A typo must keep the first letter and 80% of the letters, so
    "Mana" no longer answers with "Anak" and a district does not answer with a
    town whose name merely ends the same way.
    """
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 5.0

    stripped_query = _strip_article(query)
    if candidate.startswith(query) or _strip_article(candidate).startswith(stripped_query):
        return 4.0
    if any(word.startswith(query) for word in candidate.split()):
        return 3.0

    if len(query) < FUZZY_MIN_LENGTH:
        return 0.0

    stem, candidate_stem = stripped_query, _strip_article(candidate)
    if not stem or not candidate_stem or stem[0] != candidate_stem[0]:
        return 0.0
    if abs(len(stem) - len(candidate_stem)) > 3:
        # A much shorter query is a prefix, not a typo ("mana" is not "madinah").
        return 0.0
    ratio = difflib.SequenceMatcher(None, stem, candidate_stem).ratio()
    return ratio if ratio >= SUGGESTION_CUTOFF else 0.0


def _rank_city_matches(queries: list[str], index: dict[str, str], penalty: float = 1.0) -> dict:
    """Best score per official city over every lookup key and query."""
    ranked: dict[str, tuple[float, str]] = {}
    for candidate, official in index.items():
        for query in queries:
            score = _match_score(query, candidate) * penalty
            if not score:
                continue
            best = ranked.get(official)
            if best is None or score > best[0]:
                ranked[official] = (score, official)
            break
    return ranked


def suggest_saudi_cities(value: str, limit: int = SUGGESTION_LIMIT) -> list[str]:
    """Official city names close to ``value``, best first, for a form hint.

    Uses the same index as ``canonical_city_name`` (English, Arabic and known
    transliterations), so typing Arabic or "kho" suggests the official name.
    A value no city resembles returns an empty list instead of unrelated
    cities, and each word is tried on its own ("madinah brida" -> "Madinah").
    """
    keys = _city_keys(value)
    if not keys:
        return []

    index = city_index()
    ranked = _rank_city_matches(keys, index)

    words = [word for word in normalize_city_name(value).split() if len(word) >= FUZZY_MIN_LENGTH]
    if len(ranked) < limit and len(words) > 1:
        for official, (score, official_name) in _rank_city_matches(
            words, index, penalty=0.5
        ).items():
            if official not in ranked or score > ranked[official][0]:
                ranked[official] = (score, official_name)

    ordered = sorted(ranked.values(), key=lambda item: (-item[0], item[1]))
    return [official for _, official in ordered[:limit]]


def city_options() -> list[dict]:
    """City Name choices for the type-ahead on the Address form.

    One entry per official city - ``value`` is what is stored, ``region`` and
    ``arabic`` are shown to help pick the right city - plus the extra names from
    ``Zatca Settings`` so an extended list also completes.
    """
    options = [
        {
            "value": name,
            "label": name,
            "region": str(details.get("region") or ""),
            "arabic": str(details.get("arabic") or ""),
        }
        for name, details in SAUDI_CITIES.items()
    ]
    for name in get_city_validation_settings()["extra_cities"]:
        if name not in SAUDI_CITIES:
            options.append({"value": name, "label": name, "region": "", "arabic": ""})
    return options


def is_valid_saudi_postal_code(value: str) -> bool:
    """A Saudi postal code is 5 digits and never starts with 0 (BR-KSA-67)."""
    return bool(POSTAL_CODE_PATTERN.match(str(value or "").strip()))


def is_saudi_country(value: str) -> bool:
    """True for "Saudi Arabia", and for an Address that stores the ISO code."""
    return str(value or "").strip().casefold() in {
        "saudi arabia",
        "kingdom of saudi arabia",
        "ksa",
        "sa",
    }


def validate_zatca_city_name(city_name: str, party_label: str, notify: bool = False) -> str:
    """Return the official City Name, or refuse / warn about an unknown one.

    ``party_label`` names the address in the message ("Seller address (Zatca CSR
    Settings)", "Company type customer", ...). ``notify`` reports a corrected
    spelling to the user (used by the Address form).
    """
    raw = str(city_name or "").strip()
    if not raw:
        frappe.throw(
            _("City Name is required for {0}.").format(party_label),
            title=_("Missing City Name"),
        )

    canonical = canonical_city_name(raw)
    if canonical:
        if canonical != raw and notify:
            frappe.msgprint(
                _('City Name "{0}" was replaced by the Saudi National Address city "{1}".').format(
                    raw, canonical
                ),
                title=_("City Name Corrected"),
                indicator="blue",
            )
        return canonical

    suggestions = suggest_saudi_cities(raw)
    # Point the user at the type-ahead on the form as well as at the closest
    # official names; "Did you mean: none?" only confuses.
    hint = (
        _("Did you mean: {0}?").format(", ".join(suggestions))
        if suggestions
        else _("Clear the City Name and pick the city from the list.")
    )

    if get_city_validation_settings()["skip_city_validation"]:
        frappe.msgprint(
            _(
                'City Name "{0}" is not in the Saudi National Address list; ZATCA may'
                " report the address as inaccurate. {1}"
            ).format(raw, hint),
            title=_("Unverified City Name"),
            indicator="orange",
        )
        return raw

    frappe.throw(
        _(
            'City Name "{0}" is not a Saudi National Address city name, so ZATCA reports'
            " the {1} as inaccurate. {2} If this is a Saudi locality missing from the"
            " list, add it to Zatca Settings > Additional Saudi City Names."
        ).format(raw, party_label, hint),
        title=_("Invalid City Name"),
    )
    return raw


def validate_postal_address_for_zatca(address: dict, party_label: str) -> str:
    """Check a normalized postal address (see ``common_util.build_zatca_address``).

    Only Saudi addresses are checked: BR-KSA-67 applies 5 digits *because* the
    country code is SA, so a Bahraini ``5021`` stays valid. Returns the City
    Name to send, spelled the official way.
    """
    address = address or {}
    if str(address.get("country_code") or "").strip().upper() != "SA":
        return str(address.get("city_name") or "").strip()

    postal = str(address.get("postal_zone") or "").strip()
    if not is_valid_saudi_postal_code(postal):
        frappe.throw(
            _(
                "{0}: Postal Zone must be 5 digits for a Saudi address (BR-KSA-67),"
                ' "{1}" was given.'
            ).format(party_label, postal or _("empty")),
            title=_("Invalid Postal Code"),
        )

    return validate_zatca_city_name(address.get("city_name") or "", party_label)
