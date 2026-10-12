"""Conservative extraction: uncertain fields stay blank for human review."""
import re
from utils.constants import FIELDS
from collections import Counter

EMAIL = re.compile(r'[A-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}', re.I)
WEBSITE = re.compile(r'\b(?:https?://|www\.)[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[^\s]*)?|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:com|in|org|net|co|io|biz|edu)(?:/[^\s]*)?', re.I)
PHONE = re.compile(r'(?<!\w)(?:\+\s*\d{1,3}[\s.-]*)?(?:\(?\d{2,5}\)?[\s.-]*)?\d[\d\s().-]{6,}\d(?!\w)')
DESIGNATION = re.compile(r'\b(?:director|manager|engineer|consultant|founder|co-founder|ceo|cto|cfo|partner|proprietor|president|head|executive|officer|architect|designer|specialist|representative|marketing|procurement|sales)\b', re.I)
COMPANY = re.compile(r'\b(?:pvt\.?|private|limited|ltd\.?|llp|inc\.?|industries|solutions|technologies|engineering|chemicals|enterprises|corporation|company|group|associates|industry)\b', re.I)
ADDRESS = re.compile(r'\b(?:address|road|street|lane|avenue|floor|building|plot|sector|gidc|estate|nagar|industrial park|suite|office|block|marg|square|rd\.)\b', re.I)
STATES = ('Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Delhi', 'Chandigarh', 'Puducherry', 'Jammu and Kashmir', 'Ladakh')
CITY_STATES = {'Navi Mumbai': 'Maharashtra', 'Mumbai': 'Maharashtra', 'Thane': 'Maharashtra', 'Pune': 'Maharashtra', 'Nashik': 'Maharashtra',
               'Nagpur': 'Maharashtra', 'Aurangabad': 'Maharashtra', 'Kolhapur': 'Maharashtra', 'Ahmedabad': 'Gujarat', 'Vadodara': 'Gujarat',
               'Surat': 'Gujarat', 'Rajkot': 'Gujarat', 'Bengaluru': 'Karnataka', 'Bangalore': 'Karnataka', 'Mysuru': 'Karnataka', 'Chennai': 'Tamil Nadu',
               'Coimbatore': 'Tamil Nadu', 'Hyderabad': 'Telangana', 'Kolkata': 'West Bengal', 'New Delhi': 'Delhi', 'Noida': 'Uttar Pradesh',
               'Lucknow': 'Uttar Pradesh', 'Kanpur': 'Uttar Pradesh', 'Gurugram': 'Haryana', 'Gurgaon': 'Haryana', 'Jaipur': 'Rajasthan',
               'Indore': 'Madhya Pradesh', 'Bhopal': 'Madhya Pradesh', 'Kochi': 'Kerala', 'Visakhapatnam': 'Andhra Pradesh', 'Patna': 'Bihar',
               'Bhubaneswar': 'Odisha', 'Raipur': 'Chhattisgarh', 'Ludhiana': 'Punjab'}
FREE_MAIL = ('gmail', 'yahoo', 'hotmail', 'outlook', 'rediffmail', 'icloud', 'live', 'aol', 'protonmail', 'zoho')
COUNTRIES = ('India','United States', 'USA', 'United Kingdom', 'UK', 'United Arab Emirates', 'UAE', 'Canada', 'Australia', 'Singapore', 'Germany', 'France', 'Japan', 'China', 'South Africa', 'New Zealand')

def unique(values):
    return list(dict.fromkeys(values))

def parse_contact(text):
    # OCR often inserts a space after a dot inside email local parts.
    text = re.sub(r'([A-Za-z0-9_%+-]+(?:\s*\.\s*[A-Za-z0-9_%+-]+)+)\s*@',
                  lambda match: re.sub(r'\s+', '', match.group(1)) + '@', text)
    # Icons beside phone/email/address rows are read as stray symbols.
    joined = []
    for line in (re.sub(r'^[^\w+(]+', '', line).strip() for line in text.splitlines()):
        # Wide letter spacing can split a title across lines ("PAR" / "TNER").
        if joined and re.fullmatch(r'[A-Za-z]{2,7}', line) and re.fullmatch(r'[A-Za-z]{2,7}', joined[-1]) and DESIGNATION.fullmatch(joined[-1] + line):
            joined[-1] += line
        else:
            joined.append(line)
    text = '\n'.join(joined)
    result = dict.fromkeys(FIELDS, '')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    emails = unique(EMAIL.findall(text))
    for field, value in zip(('email', 'alternate_email'), emails):
        result[field] = value
    without_emails = EMAIL.sub('', text)
    sites = unique(match.group().rstrip('.,;)') for match in WEBSITE.finditer(without_emails))
    result['website'] = sites[0] if sites else ''
    mobiles, landlines = [], []
    for line in lines:
        # Do not consume multiline addresses or numeric identifiers.
        if re.search(r'\b(?:gst|gstin|tax|registration|pin|zip)\s*[:#]', line, re.I):
            continue
        for match in PHONE.finditer(line):
            value = re.sub(r'\s+', ' ', match.group()).strip(' .-')
            # A preceding icon can be recognized as a separate '1'. Retain the actual
            # ten-digit Indian number, while keeping explicitly printed country prefixes.
            if re.fullmatch(r'1\s+[6-9](?:[\s.-]*\d){9}', value):
                value = value.split(' ', 1)[1]
            value = re.sub(r'^\+\s+', '+', value)
            digits = re.sub(r'\D', '', value)
            if not 10 <= len(digits) <= 15:
                continue
            # '+' is often misread or detached ("#91…", "+ 9186…"); restore a uniform format.
            if re.fullmatch(r'91[6-9]\d{9}', digits):
                value = f'+91 {digits[2:7]} {digits[7:]}'
            if re.search(r'\b(?:tel|telephone|landline|fax)\b', line, re.I):
                landlines.append(value)
            elif re.fullmatch(r'(?:91|0)?[6-9]\d{9}', digits) or re.search(r'\b(?:mob|mobile|cell|whatsapp)\b', line, re.I) or value.startswith('+') and not digits.startswith('91'):
                mobiles.append(value)
            else:
                landlines.append(value)
    for field, value in zip(('mobile_number', 'alternate_mobile'), unique(mobiles)):
        result[field] = value
    result['telephone_number'] = next(iter(unique(landlines)), '')
    address_lines = []
    for line in lines:
        if ADDRESS.search(line) or re.search(r'\b(?:pin|postal|zip)\b', line, re.I) or any(re.search(r'\b' + re.escape(s) + r'\b', line, re.I) for s in STATES):
            address_lines.append(line)
    result['full_address'] = '\n'.join(address_lines)
    # Address continuations often have no street keyword, especially district/PIN lines.
    for i, line in enumerate(lines):
        if line in address_lines:
            for following in lines[i+1:i+3]:
                if EMAIL.search(following) or re.search(r'\b(?:mob|mobile|tel|email)\b', following, re.I):
                    break
                if re.search(r'\b(?:taluka|dist\.?|district|at-|nagar|west|east)\b|\b[1-9]\d{2}\s?\d{3}\b', following, re.I):
                    if following not in address_lines:
                        address_lines.append(following)
    address_lines.sort(key=lambda line: lines.index(line))
    address_lines = [re.split(r'\b(?:Mob\.?|E-?mail)\s*:', line, flags=re.I)[0].strip(' ,+|') for line in address_lines]
    result['full_address'] = '\n'.join(address_lines)
    # Line breaks act as separators; trailing commas were stripped above.
    address = ', '.join(address_lines)
    pin = re.search(r'(?<!\d)[1-9]\d{2}\s?\d{3}(?!\d)', address)
    if pin:
        result['pin_code'] = re.sub(r'\s', '', pin.group())
    for state in STATES:
        if re.search(r'\b' + re.escape(state) + r'\b', text, re.I):
            result['state'] = state
            # City before explicit state on a comma-separated address.
            city = re.search(r'(?:^|,)\s*([A-Za-z][A-Za-z .-]{1,35})\s*,\s*' + re.escape(state), address)
            if city:
                result['city'] = city.group(1).strip()
            break
    if not result['city']:
        for city, state in CITY_STATES.items():
            if re.search(r'\b' + re.escape(city) + r'\b', address, re.I):
                result['city'] = city
                result['state'] = result['state'] or state
                break
    for country in COUNTRIES:
        if re.search(r'\b' + re.escape(country) + r'\b', text, re.I):
            result['country'] = country
            break
    # Explicit field labels override positional heuristics, supporting less typical layouts.
    labels = {'name': 'name|contact', 'designation': 'designation|title', 'company_name': 'company|organisation|organization', 'city': 'city', 'state': 'state', 'country': 'country'}
    for field, label in labels.items():
        match = re.search(r'^(?:' + label + r')\s*:\s*(.+)$', text, re.I | re.M)
        if match:
            result[field] = match.group(1).strip()
    candidates = []
    for line in lines:
        if EMAIL.search(line) or WEBSITE.search(line) or any(ch.isdigit() for ch in line) or line in address_lines or ':' in line:
            continue
        if DESIGNATION.search(line):
            if not result['designation']:
                result['designation'] = line
        elif COMPANY.search(line):
            if not result['company_name']:
                result['company_name'] = line
        elif re.fullmatch(r'[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .\'-]+', line) and 2 <= len(line.split()) <= 4 and all(len(word.strip(".'-")) >= 2 for word in line.split()):
            candidates.append(line)
    if not result['name'] and candidates:
        designation_index = next((i for i, line in enumerate(lines) if line == result['designation']), None)
        preceding = [line for line in candidates if designation_index is not None and lines.index(line) < designation_index]
        result['name'] = preceding[-1] if preceding else candidates[0]
    if result['name'] and result['designation'] and not result['company_name']:
        brands = [line for line in candidates if line != result['name'] and line.isupper()]
        if brands:
            result['company_name'] = brands[0]
    if result['company_name'] in lines:
        index = lines.index(result['company_name'])
        if index > 0:
            prefix = lines[index-1]
            if re.fullmatch(r'[A-Z]{3,25}', prefix) and prefix != result['name'] and not DESIGNATION.search(prefix):
                result['company_name'] = prefix + ' ' + result['company_name']
    if not any(result[key] for key in ('designation','email','mobile_number','company_name')):
        brands=[line for line in lines if re.fullmatch(r'[A-Z]{3,}(?: [A-Z]{3,}){0,3}',line) and line not in STATES and line not in COUNTRIES]
        if brands:
            result['company_name'] = brands[0]
            result['name'] = ''
    return result

def phone_key(value):
    digits = re.sub(r'\D', '', value)
    return digits[-10:] if len(digits) >= 10 else digits

def email_key(value):
    return value.casefold()

def one_edit(a, b):
    """True when strings differ by at most one substituted, inserted or dropped character."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i+1:] or (len(a) == len(b) and a[i+1:] == b[i+1:])

def similar_email(a, b):
    return a.rpartition('@')[2] == b.rpartition('@')[2] and one_edit(a, b)

def cluster(contacts, fields, key, similar, weights):
    """Group readings of one value. Variants within one edit merge only when no single
    reading contains both, so genuinely distinct sequential numbers stay separate."""
    groups = []
    for index, contact in enumerate(contacts):
        for field in fields:
            value = contact.get(field, '').strip()
            if not value:
                continue
            k = key(value)
            group = next((g for g in groups if k in g['keys']), None) or next(
                (g for g in groups if index not in g['members'] and any(similar(k, other) for other in g['keys'])), None)
            if group is None:
                group = {'votes': Counter(), 'keys': set(), 'members': set()}
                groups.append(group)
            group['votes'][value] += weights[index]
            group['keys'].add(k)
            group['members'].add(index)
    # Stable sort: ties keep the first (best-ranked) reading.
    groups.sort(key=lambda g: sum(g['votes'].values()), reverse=True)
    for g in groups:
        g['value'] = max(g['votes'], key=g['votes'].get)
    return groups

def merge_contacts(contacts, combine_addresses=False, weights=None):
    """Combine complementary readings; preserve conflicting suggestions for review.
    Optional weights (e.g. OCR confidence) let reliable readings outvote noisy ones."""
    weights = list(weights) if weights else [1] * len(contacts)
    merged = dict.fromkeys(FIELDS, '')
    alternatives = {}
    for field in FIELDS:
        values = unique(c.get(field, '').strip() for c in contacts if c.get(field, '').strip())
        if values:
            votes = Counter()
            for c, weight in zip(contacts, weights):
                if c.get(field, '').strip():
                    votes[' '.join(c[field].split()).casefold()] += weight
            if field == 'full_address':
                # A fuller reading of the same address also earns the votes of its fragments.
                flat = lambda value: ' '.join(value.split()).casefold()
                support = {value: sum(votes[key] for key in votes if key in flat(value)) for value in values}
                merged[field] = max(values, key=support.get)
            else:
                merged[field] = max(values, key=lambda value: votes[' '.join(value.split()).casefold()])
        if len(values) > 1:
            alternatives[field] = values
    if combine_addresses:
        lines = unique(line.strip() for contact in contacts for line in contact.get('full_address', '').splitlines() if line.strip())
        merged['full_address'] = '\n'.join(lines)
    mobile_keys = set()
    for fields, key, similar in ((('email', 'alternate_email'), email_key, similar_email),
                                 (('mobile_number', 'alternate_mobile'), phone_key, one_edit)):
        groups = cluster(contacts, fields, key, similar, weights)
        values = [g['value'] for g in groups]
        for index, field in enumerate(fields):
            merged[field] = values[index] if index < len(values) else ''
        if len(values) > 2:
            alternatives[fields[0]] = values
        if 'mobile' in fields[0]:
            mobile_keys = {k for g in groups for k in g['keys']}
            spare = values[2] if len(values) > 2 else ''
    # A misread copy of a mobile is not a separate landline.
    landlines = [g['value'] for g in cluster(contacts, ('telephone_number',), phone_key, one_edit, weights)
                 if not any(one_edit(k, m) for k in g['keys'] for m in mobile_keys)]
    merged['telephone_number'] = landlines[0] if landlines else spare
    return merged, alternatives

def company_from_domain(merged, alternatives):
    """Use the business email/web domain to repair or suggest the company name."""
    # A stylised logo may lose letters ("ATATVA"); the business domain spells it fully.
    domain = re.sub(r'^(?:https?://)?(?:www\.)?', '', merged['website'] or merged['email'].rpartition('@')[2], flags=re.I).split('.')[0].casefold()
    compact = re.sub(r'[^a-z]', '', merged['company_name'].casefold())
    if domain and domain not in FREE_MAIL and not merged['company_name']:
        alternatives['company_name'] = unique(alternatives.get('company_name', []) + [domain.upper()])
    elif domain and domain not in FREE_MAIL and merged['company_name'].isupper() and ' ' not in merged['company_name'].strip() \
            and 4 <= len(compact) < len(domain) and compact in domain:
        alternatives.setdefault('company_name', [merged['company_name']])
        merged['company_name'] = domain.upper()
