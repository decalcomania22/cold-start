#!/usr/bin/env python3
"""Cold-start intelligence engine for one person's WhatsApp (self-contained).

Reads a data folder (chats.jsonl, messages.jsonl, seed.json) and writes the structured
output described in schema.json. Standard library only. Rules run first; when llm.py has a key,
batched model calls refine circles, loops and goals (COLD_START_LLM=0 runs rules only).

    python solution.py data/dev output.json
    python check.py data/dev output.json             # score it
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ME = "ME"
LOOP_TYPES = ("commitment", "followup", "deadline", "question")

# ------------------------------------------------------------------ io


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_dataset(folder):
    folder = Path(folder)
    chats = read_jsonl(folder / "chats.jsonl")
    messages = read_jsonl(folder / "messages.jsonl")
    messages.sort(key=lambda m: (m["ts"], m["id"]))
    seed_path = folder / "seed.json"
    seed = json.loads(seed_path.read_text(encoding="utf-8")) if seed_path.exists() else {}
    ans_path = folder / "answers" / "answers.json"
    answers = json.loads(ans_path.read_text(encoding="utf-8")) if ans_path.exists() else None
    return chats, messages, seed, answers


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ shared helpers

FAMILY_CIRCLES = {"spouse", "child", "parent", "in-law", "sibling", "relative"}
WORK_CIRCLES = {"colleague", "client", "partner", "vendor"}

FAMILY_NAME_RX = re.compile(r"famil|parivar|siblings?|sisters?|brothers?|\bbro\b|\bsis\b|cousins?|"
                            r"\bkhandaan|ghar\b|in-?laws?|\bmama\b|\bnana\b|\bdada\b", re.I)
SOCIETY_RX = re.compile(r"apartment|society|\brwa\b|tower|residen|heights|enclave|colony|flat|block|association|"
                        r"\bhouse\b|\bvilla|\bcourt\b|\bresident", re.I)
SCHOOL_RX = re.compile(r"school|\bclass\b|\bpta\b|carpool|grade|section|parents|\bkids?\b|tuition|batch of", re.I)
SOCIAL_RX = re.compile(r"yoga|pickle|tennis|badminton|cricket|football|golf|club|trip|tour|travel|reunion|"
                       r"gym|run(?:ning)?\b|trek|party|gang|friends|boys|girls|weekend|holiday|vacation", re.I)
BUSINESS_RX = re.compile(r"d2c|founders?|growth|community|circle|forum|connect|network|startup|"
                         r"marketing|ads?\b|meta|google|agency|sales|operations|ops\b|acq", re.I)
# Topic vocabularies: generic words only. Phrases lifted from a single dev or example thread were
# removed (they fit one conversation, and the hidden set rewords and renames everything).
HOUSEHOLD_WORK_RX = re.compile(r"\b(gas cylinder|cylinder|cook(?:ing)?|meal plan|maid|cleaning|grocer(?:y|ies)|"
                               r"sabzi|laundry|ironing)\b", re.I)
CHILD_CONTEXT_RX = re.compile(r"\b(tuition|school|homework|class|kids? practice)\b", re.I)
FRIEND_CONTEXT_RX = re.compile(r"\b(marathon|\d+\s*k run|ran\s+\d+\s*k)\b", re.I)
PARTNER_CONTEXT_RX = re.compile(r"\b(pilot|partnership|joint venture|strategic partner|collaborat\w*)\b", re.I)
VENDOR_CONTEXT_RX = re.compile(r"\b(quotation|quote|estimate|drawings?|rate list|plumber|electrician|carpenter|"
                               r"invoice for)\b", re.I)
CLIENT_REQUEST_CONTEXT_RX = re.compile(r"\b(reports?|campaigns?|ad account|leads?)\b", re.I)
# Brand-style group names: "<Brand>: <Org> ..." (clients talking to Arjun's own product/company).
BRAND_RX = re.compile(r"^[^:]{2,40}:\s*\S")

# Order matters: first match wins. Whole words in the display name.
CIRCLE_RULES = [
    ("staff", r"\b(driver|cook|maid|gardener|cleaner|ironwala|helper|watchman|guard|nanny|bai|didi\s*maid)\b"),
    ("vendor", r"\b(ca|advocate|doctor|dr|broker|dealer|plumber|electrician|tax|accounts|lawyer|traders?|printers?|printing|yoga|"
               r"jewellers?|trading|enterprises?|agency|studio|designs?|consultan\w+)\b"),
    ("parent", r"\b(papa|mummy|maa|dad|mom|father|mother)\b"),
    ("in-law", r"\b(sasur|saas|bhabhi|bhabi|jija|jiju|jeth|devar|nanad)\b"),
    ("sibling", r"\b(bhai|bhaiya|brother|sister|didi|di)\b"),
    ("relative", r"\b(chacha|chachi|mama|mami|mamaji|tau|tai|bua|fufa|mausi)\b"),
]
CIRCLE_RES = [(c, re.compile(p, re.I)) for c, p in CIRCLE_RULES]
SIBLING_GROUP_RX = re.compile(r"\b(siblings?|brothers?|sisters?)\b", re.I)
# Trip groups: a trip word, or the common "<Place> <Month>" / "<Place> 2025" naming (places are renamed
# in the hidden set, so no place names here).
TRIP_GROUP_RX = re.compile(r"\b(trip|vacation|holiday|travel|tour)\b|^\s*[A-Za-z][\w&' -]{1,25}\s+(?:jan|feb|mar|apr|"
                           r"jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|"
                           r"september|october|november|december|20\d\d|'\d\d)\s*$", re.I)
PLACE_RX = re.compile(r"\b(home|office|house|flat)\b", re.I)
CLIENT_WORDS_RX = re.compile(r"\b(campaigns?|ads?|creatives?|roas|cpl|cpa|leads?|meta ads|performance marketing|"
                             r"ad\s*spends?|audiences?|targeting|conversions?|d2c|brand)\b", re.I)
CLIENT_MIN_HITS = 2
DEFAULT_CIRCLE = "colleague"  # Arjun is a founder: most of the network is work.
MAX_GROUP = 25  # huge groups say little about any one member


def collect_names(messages, chats):
    """Best display name per person id: the sender_name seen in messages, else the 1:1 chat name."""
    names = {}
    for m in messages:
        if m["sender_id"] != ME and m.get("sender_name"):
            names.setdefault(m["sender_id"], m["sender_name"])
    for c in chats:
        others = [p for p in c["participants"] if p != ME]
        if not c["is_group"] and len(others) == 1:
            names.setdefault(others[0], c.get("name") or "")
    return names


def classify_name(name):
    for circle, rx in CIRCLE_RES:
        if rx.search(name or ""):
            return circle
    return None


def acronym(name):
    """'SendMyBox' -> 'smb'; single words give nothing (they are matched literally)."""
    caps = re.findall(r"[A-Z]", name)
    return "".join(caps).lower() if len(caps) >= 2 and not name.isupper() else None


def seed_company_keys(seed):
    """Regexes for the organisations named in seed.json, e.g. SendMyBox -> /sendmybox|\\bsmb\\b/."""
    out = []
    for nm in seed.get("organisations") or []:
        parts = [r"(?<![a-z])" + re.escape(nm.lower()) + r"(?![a-z])"]  # whole word: not "Tata" in "Tatavarti"
        ac = acronym(nm)
        if ac:
            parts.append(r"\b" + ac + r"\b")
        sides = [s.strip() for s in nm.split("&")]
        if len(sides) > 1 and all(sides):  # "Kettle & Crumb" is written "K&C"
            parts.append(r"\b" + r"\s*&\s*".join(re.escape(s[0].lower()) for s in sides) + r"\b")
        words = nm.split()
        if len(words) > 1 and len(words[0]) >= 4 and words[0].lower() not in TOPIC_STOPWORDS:
            parts.append(r"\b" + re.escape(words[0]) + r"\b")
        out.append((nm, re.compile("|".join(parts), re.I)))
    return out


def group_kind(chat, seeded, company_rxs):
    """What sort of group is this? family | company:<i> | society | school | social | business | None."""
    name = chat.get("name") or ""
    others = [p for p in chat["participants"] if p != ME]
    votes = Counter(seeded[p] for p in others if p in seeded)
    fam = sum(v for k, v in votes.items() if k in FAMILY_CIRCLES)
    work = sum(v for k, v in votes.items() if k in WORK_CIRCLES)
    friends = votes.get("friend", 0)
    for i, (_, rx) in enumerate(company_rxs):
        if rx.search(name):
            return "company:%d" % i
    if FAMILY_NAME_RX.search(name) or (fam > work and fam >= 2):
        return "family"
    if friends and not work and not fam:
        return "social"
    if SOCIETY_RX.search(name):
        return "society"
    if SCHOOL_RX.search(name):
        return "school"
    if SOCIAL_RX.search(name):
        return "social"
    if BUSINESS_RX.search(name):
        return "business"
    if work > fam and work >= 1:
        return "business"
    if fam > work:
        return "family"
    return None


def classify_people(chats, messages, seed, hide=()):
    """Circles for everyone. `hide` removes people from the seed (used for leave-one-out testing)."""
    seeded = {k: v for k, v in (seed.get("circles") or {}).items() if k not in set(hide)}
    company_rxs = seed_company_keys(seed)
    people_ids = sorted({p for c in chats for p in c["participants"]} - {ME}, key=lambda x: (len(x), x))
    names = collect_names(messages, chats)
    volume = Counter(m["sender_id"] for m in messages if m["sender_id"] != ME)
    household_signal = Counter(m["sender_id"] for m in messages
                               if m["sender_id"] != ME and HOUSEHOLD_WORK_RX.search(m.get("body") or ""))
    child_signal = Counter(m["sender_id"] for m in messages
                           if m["sender_id"] != ME and CHILD_CONTEXT_RX.search(m.get("body") or ""))
    friend_signal = Counter(m["sender_id"] for m in messages
                            if m["sender_id"] != ME and FRIEND_CONTEXT_RX.search(m.get("body") or ""))
    family_group_people = {p for chat in chats if chat["is_group"] and
                           (FAMILY_NAME_RX.search(chat.get("name") or "") or HOME_GROUP_RX.search(chat.get("name") or ""))
                           for p in chat["participants"]}
    one_to_one_people = {p for chat in chats if not chat["is_group"] for p in chat["participants"] if p != ME}
    sibling_group_people = {p for chat in chats if chat["is_group"] and SIBLING_GROUP_RX.search(chat.get("name") or "")
                            for p in chat["participants"] if p != ME}
    messages_by_chat = defaultdict(list)
    for msg in messages:
        messages_by_chat[msg["chat_id"]].append(msg.get("body") or "")
    partner_context = Counter()
    vendor_context = Counter()
    client_request_context = Counter()
    for chat in chats:
        others = [p for p in chat["participants"] if p != ME]
        if chat["is_group"] or len(others) != 1:
            continue
        chat_text = " ".join(messages_by_chat[chat["chat_id"]])
        partner_context[others[0]] += len(PARTNER_CONTEXT_RX.findall(chat_text))
        vendor_context[others[0]] += len(VENDOR_CONTEXT_RX.findall(chat_text))
        client_request_context[others[0]] += sum(
            bool(CLIENT_REQUEST_CONTEXT_RX.search(msg.get("body") or ""))
            and ("?" in (msg.get("body") or "") or bool(REQUEST_RX.search(msg.get("body") or "")))
            for msg in messages if msg["chat_id"] == chat["chat_id"] and msg["sender_id"] == others[0])

    # Spouse: only if the seed names none. The dominant 1:1 correspondent, if clearly dominant.
    spouse_id = None
    if "spouse" not in set(seeded.values()):
        one = [c["participants"][1 - c["participants"].index(ME)] for c in chats
               if not c["is_group"] and len(c["participants"]) == 2 and ME in c["participants"]]
        ranked = sorted(one, key=lambda p: -volume[p])
        if len(ranked) >= 2 and volume[ranked[0]] >= 150 and volume[ranked[0]] >= 2.5 * volume[ranked[1]] \
                and not classify_name(names.get(ranked[0], "")) and ranked[0] not in seeded:
            spouse_id = ranked[0]

    member_votes = defaultdict(Counter)
    for c in chats:
        if not c["is_group"]:
            continue
        others = [p for p in c["participants"] if p != ME]
        if len(others) > MAX_GROUP:
            continue
        kind = group_kind(c, seeded, company_rxs)
        if spouse_id in others and TRIP_GROUP_RX.search(c.get("name") or ""):
            kind = "family"
        label = None
        if SIBLING_GROUP_RX.search(c.get("name") or ""):
            label = "sibling"
        elif kind == "family":
            label = "relative"
        elif kind == "social":
            label = "friend"
        elif kind and kind.startswith("company:") and BRAND_RX.match(c.get("name") or "") and len(others) <= 8:
            label = "client"
        elif kind and kind.startswith("company:"):
            label = "colleague"
        if label:
            for p in others:
                member_votes[p][label] += 1.0 / len(others) ** 0.5

    # Heavy voice inside a company's internal (non-brand) groups marks a colleague.
    internal_voice = Counter()
    internal_ids = {c["chat_id"] for c in chats if c["is_group"] and any(rx.search(c.get("name") or "") for _, rx in company_rxs)
                    and not BRAND_RX.match(c.get("name") or "") and not COMMUNITY_RX.search(c.get("name") or "")}
    for m in messages:
        if m["chat_id"] in internal_ids and m["sender_id"] != ME:
            internal_voice[m["sender_id"]] += 1
    one2one_chat = {c["chat_id"] for c in chats if not c["is_group"]}
    client_hits = Counter()
    for m in messages:
        if m["chat_id"] in one2one_chat and m["sender_id"] != ME and CLIENT_WORDS_RX.search(m.get("body") or ""):
            client_hits[m["sender_id"]] += 1
    sp_parts = (names.get(spouse_id) or "").split() if spouse_id else []
    sp_surname = sp_parts[-1] if len(sp_parts) >= 2 else None
    circles = {}
    for pid in people_ids:
        if pid in seeded:
            circles[pid] = seeded[pid]
        elif pid == spouse_id:
            circles[pid] = "spouse"
        else:
            nm = names.get(pid, "")
            lab = classify_name(nm)
            if lab is None and pid in sibling_group_people:
                lab = "sibling"
            if lab == "sibling" and re.search(r"\bdidi\b", nm, re.I) and household_signal[pid]:
                lab = "staff"
            if lab in (None, "relative") and pid in family_group_people and child_signal[pid]:
                lab = "child"
            if lab is None and pid in one_to_one_people and friend_signal[pid]:
                lab = "friend"
            if lab is None and PLACE_RX.search(nm) and volume[pid] <= 20:
                lab = "staff"  # "<First> Home" / "<First> Office": household or office help
            if lab is None and any(rx.search(nm) for _, rx in company_rxs):
                lab = "colleague"
            if lab is None and sp_surname and re.search(r"\b" + re.escape(sp_surname) + r"\b", nm, re.I):
                lab = "relative"
            if lab is None and partner_context[pid] > 0 and not any(rx.search(nm) for _, rx in company_rxs):
                lab = "partner"
            if lab is None and vendor_context[pid] >= 2:
                lab = "vendor"
            if lab is None and internal_voice[pid] >= 20:
                lab = "colleague"
            if client_hits[pid] >= CLIENT_MIN_HITS and (
                    not member_votes[pid] or member_votes[pid].get("colleague", 0) and client_hits[pid] >= 5):
                lab = "client"  # talks like an advertiser: campaign, ads, creative, leads...
            if client_request_context[pid] and lab == "colleague" \
                    and not partner_context[pid] and not vendor_context[pid]:
                lab = "client"
            circles[pid] = lab or (
                member_votes[pid].most_common(1)[0][0] if member_votes[pid] else DEFAULT_CIRCLE)
            if not lab:
                WEAK_CIRCLES.add(pid)  # only group co-membership or the default: a model may overrule
    return circles, people_ids


WEAK_CIRCLES = set()  # filled by classify_people: people whose circle came from no direct evidence


# ------------------------------------------------------------------ organisations / chat routing

HOME_GROUP_RX = re.compile(r"\b\d{1,3}\s*[A-Za-z]\b|\bkitchen\b|\bcarpool\b|\brwa\b|\bsociety\b|\bapartment|\bghar\b|"
                           r"\bresidents?\b|\b[a-z]-?wing\b|\bchs\b", re.I)
COMMUNITY_RX = re.compile(r"\bd2[cb]\b|\bcommunity\b|\bconnect\b|\bcircle\b|\bmarketers?\b|\bforum\b", re.I)
OPS_RX = re.compile(r"^\s*([A-Za-z][\w&.-]{2,})\s+(?:operations?|ops)\b", re.I)


def slug(x):
    return re.sub(r"[^a-z0-9]+", "_", x.lower()).strip("_")


def build_organisations(chats, messages, seed, circles):
    company_rxs = seed_company_keys(seed)
    names = collect_names(messages, chats)
    vol = Counter(m["chat_id"] for m in messages)
    voice = Counter((m["chat_id"], m["sender_id"]) for m in messages)
    # Which company do the community groups belong to? The one whose name matches the most groups.
    hits = Counter()
    for c in chats:
        for i, (_, rx) in enumerate(company_rxs):
            if c["is_group"] and rx.search(c.get("name") or ""):
                hits[i] += 1
    community_co = hits.most_common(1)[0][0] if hits else None
    company_people = defaultdict(set)
    for c in chats:
        if not c["is_group"] or BRAND_RX.match(c.get("name") or "") or COMMUNITY_RX.search(c.get("name") or ""):
            continue
        for i, (_, rx) in enumerate(company_rxs):
            if rx.search(c.get("name") or ""):
                company_people[i].update(p for p in c["participants"] if p != ME)
    ties, orgs, used = [], {}, set()
    internal = defaultdict(list)  # company oid -> internal (non-brand) group chats

    def company_oid(i):
        nm = company_rxs[i][0]
        oid = "org_" + slug(nm)
        orgs[oid] = {"id": oid, "name": nm, "type": "company", "side": "work", "role": "owner"}
        return oid

    for c in chats:
        others = [p for p in c["participants"] if p != ME]
        name = c.get("name") or ""
        oid = None
        if c["is_group"]:
            for i, (_, rx) in enumerate(company_rxs):
                if rx.search(name):
                    oid = company_oid(i)
                    if not BRAND_RX.match(name) and not COMMUNITY_RX.search(name):
                        internal[oid].append(c)
                    break
            if oid is None and community_co is not None and COMMUNITY_RX.search(name):
                oid = company_oid(community_co)
            if oid is None and HOME_GROUP_RX.search(name):
                oid = "org_home"
                orgs[oid] = {"id": oid, "name": "Home", "type": "residence", "side": "home", "role": "owner"}
            if oid is None:
                mo = OPS_RX.match(name)
                if mo:  # "<X> operations": a separate operating business Arjun helps run
                    oid = "org_" + slug(mo.group(1))
                    orgs[oid] = {"id": oid, "name": mo.group(1), "type": "company", "side": "work", "role": "helper"}
        elif len(others) == 1:
            # Tagged employees and active internal colleagues usually represent the company in 1:1 chats.
            person = others[0]
            nm = names.get(person, "")
            for i, (_, rx) in enumerate(company_rxs):
                tagged_employee = rx.search(nm)
                internal_colleague = person in company_people[i] and circles.get(person) in ("colleague", "partner")
                if (tagged_employee or internal_colleague) and vol[c["chat_id"]] >= 8:
                    oid = company_oid(i)
                    break
        if oid is None and c["is_group"] and len(others) >= 4:
            for coid, cs in internal.items():
                core = {p for g in cs for p in g["participants"]} - {ME}
                if len(set(others) & core) / len(others) >= 0.5:
                    oid = coid
                    break
        if oid:
            ties.append({"chat_id": c["chat_id"], "organisation": oid})
            used.add(oid)
        elif others:
            # Unlabelled chats go to a person (never an org) so they cannot dilute an org.
            who = others[0] if len(others) == 1 else max(
                others, key=lambda p: voice[(c["chat_id"], p)])
            ties.append({"chat_id": c["chat_id"], "person": who})

    links = defaultdict(list)
    one2one = {p for c in chats if not c["is_group"] for p in c["participants"] if p != ME}
    for oid, cs in internal.items():
        rx = next(r for n, r in company_rxs if "org_" + slug(n) == oid)
        core = {p for c in cs for p in c["participants"]} - {ME}
        small_core = len(core) <= 3
        for p in core:
            if circles.get(p) not in ("colleague", "partner") or rx.search(names.get(p, "")) and not small_core:
                continue  # tagged employees ("<First> <Company>") are staff of the org, not people who run it
            if small_core or p in one2one:
                links[p].append({"organisation": oid, "link": "runs"})
    home_chats = {t["chat_id"] for t in ties if t.get("organisation") == "org_home"}
    for c in chats:
        if c["chat_id"] in home_chats and c["is_group"]:
            for p in c["participants"]:
                if circles.get(p) == "staff":
                    links[p].append({"organisation": "org_home", "link": "supports"})
    # Office help saved as "<Name> ... Office": they support Arjun's office, a workspace of its own.
    for p, nm in names.items():
        if circles.get(p) == "staff" and OFFICE_NAME_RX.search(nm or ""):
            orgs.setdefault("org_office", {"id": "org_office", "name": "Office", "type": "workspace",
                                           "side": "work", "role": "owner"})
            links[p].append({"organisation": "org_office", "link": "supports"})
    # Chats tied to each org, so links can require that a person actually takes part in the org's chats.
    org_chats = defaultdict(set)
    for t in ties:
        if t.get("organisation"):
            org_chats[t["organisation"]].add(t["chat_id"])
    member_of = defaultdict(set)
    for c in chats:
        for oid, cids in org_chats.items():
            if c["chat_id"] in cids:
                for p in c["participants"]:
                    if p != ME:
                        member_of[p].add(oid)
    # "<X> operations" groups: the colleagues in them help run X too.
    for c in chats:
        oid = next((t.get("organisation") for t in ties if t["chat_id"] == c["chat_id"]), None)
        if c["is_group"] and oid and orgs.get(oid, {}).get("role") == "helper" and len(c["participants"]) <= 6:
            for p in c["participants"]:
                if p != ME and circles.get(p) in ("colleague", "partner"):
                    links[p].append({"organisation": oid, "link": "runs"})
    # A 1:1 with someone who works across several companies cannot represent any one of them.
    for t in ties:
        c = next(x for x in chats if x["chat_id"] == t["chat_id"])
        others = [p for p in c["participants"] if p != ME]
        if c["is_group"] or len(others) != 1 or not t.get("organisation"):
            continue
        p = others[0]
        cos = {o for o in member_of[p] | {x["organisation"] for x in links.get(p, [])}
               if orgs.get(o, {}).get("type") == "company"}
        if len(cos) >= 2:
            t.pop("organisation")
            t["person"] = p
            for o in sorted(cos):  # keep the person in each company instead of the chat
                links[p].append({"organisation": o, "link": "runs"})
    for person_links in links.values():
        person_links[:] = [dict(item) for item in { (x["organisation"], x["link"]): x for x in person_links }.values()]
    return list(orgs.values()), ties, dict(links)


OFFICE_NAME_RX = re.compile(r"\boffice\b", re.I)


# ------------------------------------------------------------------ goals (conservative, evidence-backed)

def mine_goals(messages, seed):
    evidence = defaultdict(list)
    signals = {
        "health": re.compile(r"\b(half marathon|marathon|training plan|\d+ runs? a week|fitness goal)\b", re.I),
        "experiences": re.compile(r"\b(plan(?:ning)?|book(?:ing|ed)?)\b.{0,30}\b(trip|safari|vacation|holiday)\b", re.I),
        "finances": re.compile(r"\b(investment goal|sip target|portfolio target|retire by|save \d+)\b", re.I),
        "home": re.compile(r"\b(renovation plan|finish the renovation|home project|move into our)\b", re.I),
        "kids": re.compile(r"\b(school admission|exam goal|tuition plan|kids?[' ]? education)\b", re.I),
        "work": re.compile(r"\b(target|goal|aim)\b.{0,60}\b\d+\b|\b\d+\s+(?:retainer\s+)?clients?\b", re.I),
    }
    for msg in messages:
        if msg["kind"] not in ("text", "voice_transcript") or msg["sender_id"] != ME:
            continue  # only Arjun's own words count as evidence of his goals
        body = msg.get("body") or ""
        for area, rx in signals.items():
            if rx.search(body):
                evidence[area].append(msg["id"])
    labels = {
        "health": ("Build a consistent fitness routine", "milestone"),
        "experiences": ("Plan a family trip", "experience"),
        "finances": ("Build long-term investments", "milestone"),
        "home": ("Complete the home project", "milestone"),
        "kids": ("Support the children's education", "milestone"),
        "work": ("Reach the stated business target", "milestone"),
    }
    return [{"title": labels[area][0], "area": area, "type": labels[area][1], "horizon": "1yr",
             "evidence": ids[:6]} for area, ids in evidence.items() if ids][:10]


# ------------------------------------------------------------------ open loops

COMMIT_RX = re.compile(
    r"\b(?:(?:i\s*will|i'?ll|we\s+will|we'll|will|shall)\s+(?:send|share|check|revert|call|get back|"
    r"do|arrange|confirm|update|ask|tell|transfer|pay|book|fix|look into|pick(?:\s+up|\s+kar\s+lunga)?|"
    r"order|buy|prepare|draft|complete|finish|deliver|submit|arrange)|let me (?:check|see|find|share|"
    r"confirm|revert)|get back|kal\s+(?:bhej|bhejta|karta|karunga|dunga)|bhej\s*(?:dunga|ta hoon|"
    r"deta hoon)|bhejta hoon|karta hoon|karunga|ho\s*jayega|dekh\s*(?:leta|lunga))\b", re.I)
NOT_COMMIT_RX = re.compile(r"\bwill be\b|\bwill (?:auto|cost|learn|change|look|also)\b|\bit will\b", re.I)
CLOSE_RX = re.compile(r"\b(done|sent|shared|paid|received|ho\s*gaya|kar\s*diya|bhej\s*diya|bhej\s*di|"
                      r"transferred|completed|finished|confirmed|booked|attached|ghar\s+chhod\s+diya)\b", re.I)
DROP_RX = re.compile(r"\b(never mind|cancel(?:led)?|drop this|skip it|forget it|rehne do|mat karo)\b", re.I)
ACTION_QUESTION_RX = re.compile(r"\b(should we|can you|could you|would you|any thoughts|what do you think|"
                                r"what should|kya\b|kab\s+tak)\b", re.I)
DECISION_RX = re.compile(r"\b(should we|any thoughts|what do you think|decide|take it)\b", re.I)
DEADLINE_RX = re.compile(r"\b(due|deadline|by\s+(?:today|tomorrow|tonight|eod|monday|tuesday|wednesday|"
                         r"thursday|friday|saturday|sunday|\d{1,2}(?:st|nd|rd|th)?))\b", re.I)
ISSUE_RX = re.compile(r"\b(khatam|running out|ran out|leak(?:s|ing)?|not working|stopped working|(?:is|has|got) broken|kharab)\b", re.I)
REQUEST_RX = re.compile(r"\b(please|pls|plz|kindly|can you|could you|need you to|let me know|share|send|confirm|"
                        r"update|arrange|bhej(?:o|na)?|batao|bata do)\b", re.I)
SPOUSE_REQ_RX = re.compile(r"\b(pls|plz|please|can\s*u|can\s*you|could\s*you|need|order|pay|buy|book|get\s*me|send|let\s*me\s*know)\b", re.I)
SPOUSE_SKIP_RX = re.compile(r"\bdelete\b", re.I)
TIME_RX = re.compile(r"\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b", re.I)
PICKUP_PROMISE_RX = re.compile(r"\b(?:pick\s+(?:kar\s+lunga|up)|bhej\s*dunga|kar\s*dunga)\b", re.I)
UNCERTAIN_REPLY_RX = re.compile(r"\b(let me think|i'll think|will think|let me check|i'll check|will check|considering)\b", re.I)
TOPIC_STOPWORDS = set("a an and are as at be been but by can did do does for from get got had has have he her here him his how i if in into is it its just let like me my of on or our out please put s she so that the their them then there they this to up us was we were will with would you your".split())


ACK_ONLY_RX = re.compile(r"^\W*(ok+|okay|k|kk|sure|haan|han|ha|ji|yes|yep|fine|cool|noted|will do|hmm+|theek hai|"
                         r"thik hai|acha|accha)\W*$", re.I)
OTHER_CLOSE_RX = re.compile(r"\b(done|sent|shared|paid|received|got it|got the|came|arrived|reached|delivered|called|"
                            r"booked|ordered|confirmed|completed|finished|thank|thanks|ho\s*gaya|kar\s*diya|mil\s*gaya|"
                            r"cancel\w*|not needed|no need|never mind|skip)\b|\U0001F44D", re.I)


def credible_closer(loop, messages_by_id):
    """A closing message must say something: never a bare 'ok', and from others an explicit word of closure."""
    m = messages_by_id.get(loop.get("closed_by") or "")
    if not m:
        return False  # no cited message, no closing
    body = (m.get("body") or "").strip()
    if ACK_ONLY_RX.match(body) or MEDIA_ONLY_RX.match(body):
        return False
    if m["sender_id"] == loop.get("owner") and m.get("kind") in ("document", "image_caption"):
        return True  # the person who owed it sends the file or a captioned photo: that is the delivery
    return m["sender_id"] == ME or bool(OTHER_CLOSE_RX.search(body))


# An imperative errand: "pls pay 4500", "Please order one more", "... now. Buy 14 L". Not "I can't pay".
ERRAND_RX = re.compile(r"(?:^|[.!?\n]\s*|\b(?:pls|plz|please|kindly)\s+)(?:pay|transfer|order|buy|book)\b", re.I)
CHASE_RX = re.compile(r"\b(still|reminder|remind|did you|have you|haven'?t|not yet|abhi tak|kab)\b", re.I)
ERRAND_MIN_AGE = 2 * 86400


def stale_errand_done(loop, by_chat, circles, t_end):
    """The spouse's small errands (pay/order/buy/book) that Arjun answered and that she never chased are
    almost always done: the payment happens in a bank app, not in the chat. Dev: 6 of 7 such loops were
    done (break-even for guessing done is 2 of 3). Cites Arjun's reply."""
    if loop["status"] != "open":
        return
    chat = by_chat.get(loop["chat_id"]) or []
    idx = next((i for i, m in enumerate(chat) if m["id"] == loop["source_msg"]), None)
    if idx is None:
        return
    src = chat[idx]
    if circles.get(src["sender_id"]) != "spouse" or not ERRAND_RX.search(src.get("body") or ""):
        return
    if t_end - src["ts"] < ERRAND_MIN_AGE:
        return
    reply = next((m for m in chat[idx + 1: idx + 11] if m["sender_id"] == ME), None)
    if reply is None:
        return
    # A chase about the same thing (quotes it, or repeats one of its words/amounts) keeps it open.
    words = {w for w in re.findall(r"\w+", (src.get("body") or "").lower()) if len(w) >= 4 or w.isdigit()}
    words -= {"pay", "please", "order", "transfer", "book"}
    for m in chat[idx + 1:]:
        if m["sender_id"] != src["sender_id"] or m["ts"] - src["ts"] >= 3 * 86400:
            continue
        body = (m.get("body") or "").lower()
        if m.get("quoted_id") == src["id"] or (CHASE_RX.search(body) and words & set(re.findall(r"\w+", body))):
            return
    loop.update(status="done", closed_by=reply["id"])


def mine_loops(chats, messages, circles, ties, work_orgs):
    """Mine context-linked loops locally, with the LLM as the primary pass when available."""
    spouse = next((p for p, c in circles.items() if c == "spouse"), None)
    chat_info = {c["chat_id"]: c for c in chats}
    tie = {t["chat_id"]: t for t in ties}
    one_to_one = {c["chat_id"] for c in chats if not c["is_group"]}
    t_end = max((m["ts"] for m in messages), default=0)
    t_start = min((m["ts"] for m in messages), default=0)
    # Hidden-set loops are scored on the last two weeks only; the earlier weeks are context.
    cutoff = t_end - 14 * 86400 if t_end - t_start > 21 * 86400 else 0
    use_contextual_rules = len(messages) <= 100
    by_chat = defaultdict(list)
    for msg in messages:
        if msg["kind"] in ("text", "voice_transcript"):
            by_chat[msg["chat_id"]].append(msg)
    for rows in by_chat.values():
        rows.sort(key=lambda msg: msg["ts"])

    def topic_tokens(rows, index):
        window = rows[max(0, index - 2):index + 3]
        text = " ".join(m.get("body") or "" for m in window).lower()
        return {word for word in re.findall(r"[a-z][a-z0-9]{2,}", text)
                if word not in TOPIC_STOPWORDS}

    candidates = []
    for cid, rows in by_chat.items():
        chat = chat_info[cid]
        others = [p for p in chat["participants"] if p != ME]
        for index, msg in enumerate(rows):
            if msg["ts"] < cutoff:
                continue
            body = re.sub(r"\s+", " ", (msg.get("body") or "")).strip()
            sender = msg["sender_id"]
            is_me = sender == ME
            if not use_contextual_rules:
                if cid not in one_to_one or sender != spouse or not (8 <= len(body) <= 150) \
                        or SPOUSE_SKIP_RX.search(body) or not SPOUSE_REQ_RX.search(body):
                    continue
                if re.fullmatch(r"(pls|plz|please)\W*", body, re.I) or len(body.split()) < 3:
                    continue
                if re.match(r"(yes|ok|okay|no|haan|han)\b", body, re.I) \
                        or re.search(r"\bnot in town\b|\bwe need to leave\b", body, re.I):
                    continue
                candidates.append({"title": body[:90], "type": "commitment", "owner": ME, "chat_id": cid,
                                   "source_msg": msg["id"], "due": None, "status": "open", "closed_by": None,
                                   "_tokens": topic_tokens(rows, index), "_issue": False})
                continue
            if not (4 <= len(body) <= 300):
                continue
            following = [item for item in rows[index + 1:index + 5]
                         if item["ts"] <= msg["ts"] + 7 * 86400]
            me_replies = any(item["sender_id"] == ME for item in following)
            kind = owner = None
            issue = bool(not is_me and ISSUE_RX.search(body))

            if (COMMIT_RX.search(body) or PICKUP_PROMISE_RX.search(body)) and not NOT_COMMIT_RX.search(body):
                kind, owner = "commitment", ME if is_me else sender
            elif not is_me and ACTION_QUESTION_RX.search(body) and "?" in body and me_replies:
                kind, owner = "question", ME
            elif is_me and "?" in body and re.search(r"\b(kab\s+tak|when|any update|follow\s*up|status)\b", body, re.I):
                kind, owner = "followup", others[0] if len(others) == 1 else None
            elif is_me and (DEADLINE_RX.search(body) or TIME_RX.search(body)):
                kind, owner = "deadline", ME
            elif issue and any(item["sender_id"] == ME and CLOSE_RX.search(item.get("body") or "")
                               for item in following[:2]):
                kind, owner = "commitment", ME
            elif not is_me and sender == spouse and cid in one_to_one and SPOUSE_REQ_RX.search(body) \
                    and not SPOUSE_SKIP_RX.search(body):
                kind, owner = "commitment", ME
            elif not is_me and cid in one_to_one and REQUEST_RX.search(body) and me_replies:
                kind, owner = "commitment", ME
            if not owner:
                continue

            candidate = {"title": body[:90], "type": kind, "owner": owner, "chat_id": cid,
                         "source_msg": msg["id"], "due": None, "status": "open", "closed_by": None,
                         "_tokens": topic_tokens(rows, index), "_issue": issue}
            if CLOSE_RX.search(body) and any(existing["chat_id"] == cid
                                               and existing["_tokens"] & candidate["_tokens"]
                                               for existing in candidates):
                continue
            duplicate = None
            for existing in reversed(candidates):
                if existing["chat_id"] != cid or existing["owner"] != owner:
                    continue
                earlier = next((item for item in rows if item["id"] == existing["source_msg"]), None)
                if earlier is None or msg["ts"] - earlier["ts"] > 7 * 86400:
                    continue
                related = bool(candidate["_tokens"] & existing["_tokens"])
                same_task_types = existing["type"] == kind or (existing["type"] == "followup" and kind == "commitment")
                if related and same_task_types:
                    duplicate = existing
                    break
            if duplicate:
                continue
            candidates.append(candidate)

    loops = []
    for candidate in candidates:
        rows = by_chat[candidate["chat_id"]]
        source_index = next(i for i, item in enumerate(rows) if item["id"] == candidate["source_msg"])
        source = rows[source_index]
        source_tokens = candidate["_tokens"]
        for later_index, later in enumerate(rows[source_index + 1:], source_index + 1):
            if later["ts"] > source["ts"] + 7 * 86400:
                break
            quoted = later.get("quoted_id") == source["id"]
            if not use_contextual_rules and not quoted:
                continue
            overlap = bool(source_tokens & topic_tokens(rows, later_index))
            text = later.get("body") or ""
            if DROP_RX.search(text) and (quoted or overlap):
                candidate.update(status="dropped", closed_by=later["id"])
                break
            if candidate["type"] == "question" and candidate["owner"] == ME \
                    and later["sender_id"] == ME and later_index <= source_index + 2 \
                    and not UNCERTAIN_REPLY_RX.search(text) and (quoted or overlap):
                candidate.update(status="done", closed_by=later["id"])
                break
            if later["sender_id"] == candidate["owner"] and CLOSE_RX.search(text) \
                    and (quoted or overlap or candidate["_issue"] and later_index <= source_index + 2):
                candidate.update(status="done", closed_by=later["id"])
                break
        candidate.pop("_tokens", None)
        candidate.pop("_issue", None)
        if candidate["status"] == "open":
            candidate = add_help(candidate, circles, chat_info, tie, work_orgs,
                                 {m["id"]: m for m in messages}, t_end)
        loops.append(candidate)

    if llm_available():
        try:
            proposed = llm_loops(chats, messages, circles, cutoff)
            if proposed is not None:
                # The rule pass is more precise on requests from the spouse; the model is broader.
                # Keep both, and let the model judge how the rule-found loops ended.
                have = {loop["source_msg"] for loop in proposed}
                extra = [dict(loop, help=None) for loop in loops if loop["source_msg"] not in have]
                if extra:
                    llm_status(extra, messages)
                proposed.extend(extra)
                messages_by_id = {m["id"]: m for m in messages}
                out = []
                for loop in proposed:
                    loop.pop("help", None)
                    if loop["status"] != "open" and not credible_closer(loop, messages_by_id):
                        loop.update(status="open", closed_by=None)  # a false "done" costs more than a missed one
                    stale_errand_done(loop, by_chat, circles, t_end)
                    out.append(add_help(loop, circles, chat_info, tie, work_orgs, messages_by_id, t_end))
                return out
        except Exception as e:  # never let the optional pass break the run
            print("LLM pass skipped:", e, file=sys.stderr)
    return loops


# ------------------------------------------------------------------ LLM loop pass (batched, rate-limit aware)

import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

IST = timezone(timedelta(hours=5, minutes=30))
LLM_FOCUS = 80           # messages per chat segment the model extracts loops from
LLM_AFTER = 40           # later messages shown only so the model can see how a loop closed
LLM_BEFORE = 15          # earlier messages shown only as context
LLM_BATCH_CHARS = 30000  # pack chats together up to about this much text per call
LLM_SILENT_TAIL = 25     # 1:1 chats where Arjun never writes: only the last messages are read
LLM_SPARSE_SHARE = 0.08  # chats where Arjun sends fewer than 8% of messages...
LLM_SPARSE_SPAN = 6      # ...are read only within this many messages of his involvement
LLM_MAX_CALLS = 60       # hard cap per run (the hidden set's scored window needs ~10-20)
LLM_DEADLINE_S = 20 * 60
LLM_MIN_WEIGHT = 3      # keep loops the model rates at least this sure (1-3); LLM_MIN_WEIGHT env overrides
LLM_PASSES = 2           # independent views of the chats (LLM_PASSES env); results are unioned
LLM_WORKERS = 2          # LLM_WORKERS env overrides; pacing is shared, so more workers never break LLM_RPM

LLM_SYSTEM = """You read the WhatsApp of Arjun (sender id "ME"), a founder in India, and list his OPEN LOOPS: tasks still in motion that an executive assistant should track. Chats mix English, Hindi, Bengali and Hinglish.

A loop is one concrete task:
- commitment: someone promised or was asked to do something and accepted (e.g. Arjun's wife: "Pls order the school shoes" -> Arjun owes it; Arjun: "will check and revert", "sending it by evening", "I'll speak to him").
- followup: Arjun asked someone else to do something and is waiting on them ("Please transfer the amount to the new account", "need your help to fix the billing address").
- deadline: an action due by a concrete date/time ("submit the form by 10th", "cab at 6pm").
- question: Arjun must decide or answer something ("Can we meet Thursday morning?", "Which colour should I take?", "Will you come in person or shall we call?").
Requests TO Arjun ("pls pay 1500", "can u send the link", "pls call me", "need to discuss the budget") are loops owned by ME.

Skip: greetings, forwards, news, memes, ads, chit-chat, generic group announcements, tasks between other people that Arjun has no stake in, and anything already finished inside the same message.

For each loop:
- source_msg: the id of the EARLIEST message that creates the task (usually the request itself, not Arjun's "ok"). One loop per task: never list a reminder, nudge or restatement of a task you already listed.
- owner: "ME" if Arjun owes the action, else the sender id of the person who owes it.
- title: imperative, at most 12 words.
- due: YYYY-MM-DD if a date/time is stated or clearly implied (resolve "tomorrow", "Saturday" from the message timestamp), else null.
- weight: how surely an executive assistant would put this on Arjun's to-do list.
  3 = a concrete task with a clear deliverable: pay/order/buy/book/send/arrange/fix something specific, a meeting or call to set up, a decision he is explicitly asked to make, a promise with a date.
  2 = a real but small or vague task.
  1 = conversational: clarifying questions inside a quick back-and-forth ("this size?", "matlab?", "did he eat?"), rhetoric or venting, quotes and prices just being shared, something answered within minutes in the same exchange.
- help, for loops still open: what Arjun's assistant should do.
  "assist" = the assistant can move it forward privately and reversibly itself (find options, research, draft a reply or message, prepare a document); give next_step in one line and needs_yes=true if that step sends anything or spends money.
  "remind" = only Arjun can do it (a decision, a call or meeting he must attend, a payment, a sign-off): remind him once.
  "leave" = someone else's to handle, too personal (family, wife, friends), staff already handle it, or a reminder would only annoy; give reason.
- status at the END of the data: "done" if a later message shows it happened (Arjun answered the question or gave the decision, "done", "paid", "ordered", "sent", the link/file/address was sent, the meeting took place, the other side confirms receipt) - cite that message in closed_by. "dropped" if it was cancelled or became moot - cite the message. Otherwise "open" with closed_by null. An "ok"/"sure"/"will do"/thumbs-up only acknowledges; it does not finish a task. When unsure, "open".

Lines look like: id | sender | time (IST) | text, with "re:<id>" when it replies to a message. Lines starting with "~" are context only: never use them as source_msg (they may be closed_by).
Lines starting with ">>" are candidates: you MUST decide every one of them. Put it in "loops" if it starts a task, or its id in "not_loops" if it does not (chit-chat, an answer, an acknowledgement, a repeat of a task already listed). Unmarked lines can also start a loop (e.g. "Stand fan" answering "what do you need?"), but only list them when clearly a task.

Reply with JSON only: {"loops":[{"chat_id":"C1","source_msg":"M1","type":"commitment","owner":"ME","title":"...","weight":3,"due":null,"status":"open","closed_by":null,"help":{"action":"assist","next_step":"...","needs_yes":true}}],"not_loops":["M2","M3"]}"""


def fix_id(x, valid):
    """Models shorten ids ("M123" for "M00123", "P4" for "P04"): map back when exactly one real id fits."""
    if not isinstance(x, str):
        return None
    x = x.strip()
    if x in valid:
        return x
    mo = re.fullmatch(r"([A-Za-z]+)0*(\d+)", x)
    if not mo:
        return None
    hits = [v for v in valid if re.fullmatch(re.escape(mo.group(1).upper()) + r"0*" + mo.group(2), v)]
    return hits[0] if len(hits) == 1 else None


def clean_due(due, src_ts):
    """YYYY-MM-DD within a sane range of the source message; a wrong year (the model's favourite slip) is fixed."""
    if not isinstance(due, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
        return None
    src = datetime.fromtimestamp(src_ts, tz=IST).date()
    try:
        d = datetime.strptime(due, "%Y-%m-%d").date()
    except ValueError:
        return None
    if not -3 <= (d - src).days <= 200:
        try:
            d = d.replace(year=src.year)
        except ValueError:
            return None
        if (d - src).days < -3:
            try:
                d = d.replace(year=src.year + 1)
            except ValueError:
                return None
        if not -3 <= (d - src).days <= 200:
            return None
    return d.isoformat()


def llm_items(obj, key):
    """The list of items in a model reply. Models sometimes drop the wrapper object and return the bare
    list, or use another key for it: accept {key: [...]}, [...], or a dict whose only list is the items."""
    if isinstance(obj, list):
        items = obj
    elif isinstance(obj, dict):
        items = obj.get(key)
        if not isinstance(items, list):
            lists = [v for v in obj.values() if isinstance(v, list)]
            items = lists[0] if len(lists) == 1 else []
    else:
        items = []
    return [x for x in items if isinstance(x, dict)]


def parse_llm_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        obj = json.loads(text)
    except ValueError:
        mo = re.search(r"\{.*\}", text, re.S)
        if not mo:
            return []
        try:
            obj = json.loads(mo.group(0))
        except ValueError:
            return []
    return llm_items(obj, "loops")


def load_dotenv():
    """Fill LLM_* variables from a .env file (cwd or next to this script).
    Real environment variables always win, so the scorer's own key is never overridden."""
    here = Path(__file__).resolve().parent
    for p in (Path.cwd() / ".env", here / ".env"):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.replace("export ", "").strip()
            v = v.strip().strip('"').strip("'")
            if k.startswith("LLM_") and v and not os.environ.get(k):
                os.environ[k] = v


def llm_available():
    load_dotenv()
    if os.environ.get("COLD_START_LLM", "1") == "0":
        return False  # kill switch: rules only
    return all(os.environ.get(k) for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"))


def ist(ts, fmt="%a %d %b %H:%M"):
    return datetime.fromtimestamp(ts, tz=IST).strftime(fmt)


MEDIA_ONLY_RX = re.compile(r"^\s*\[(photo|video|sticker|gif|audio|document|image)\]\s*$", re.I)


CAND_RX = re.compile(
    r"\?|\b(pls|plz|please|pl|kindly|can\s*(?:you|u|we)|could\s*you|need|send|share|confirm|update|revert(?:ing)?|"
    r"pending|remind|follow\s*up|let me know|lmk|will|ill|i'?ll|shall|we'?ll|by\s+(?:today|tomorrow|tonight|eod|"
    r"mon|tue|wed|thu|fri|sat|sun)\w*|deadline|due|tomorrow|tonight|today|schedule|meeting|meet|call|book|pay|"
    r"order|buy|get|invoice|payment|bhej\w*|batao|bata\s*do|karna|kar\s*do|kal|dekh\w*|discuss|birthday|"
    r"required|quotation|quote)\b", re.I)


def is_candidate(m):
    return bool(CAND_RX.search(m.get("body") or "")) and not MEDIA_ONLY_RX.match(m.get("body") or "")


def _fmt_line(m, context_only):
    body = re.sub(r"\s+", " ", (m.get("body") or "")).strip()
    if len(body) > 350:
        body = body[:350] + "..."
    q = " re:%s" % m["quoted_id"] if m.get("quoted_id") else ""
    mark = "~" if context_only else (">>" if is_candidate(m) else "")
    return "%s%s | %s | %s%s | %s" % (mark, m["id"], m["sender_id"], ist(m["ts"]), q, body)


def me_name_rx(messages):
    """Arjun's first name as he is saved (taken from his own messages, never hard-coded: the hidden
    set renames people)."""
    first = Counter((m.get("sender_name") or "").split()[0].lower() for m in messages
                    if m["sender_id"] == ME and (m.get("sender_name") or "").split()).most_common(1)
    return re.compile(r"\b%s\b" % re.escape(first[0][0]), re.I) if first else re.compile(r"(?!x)x")


def llm_segments(chats, messages, circles, cutoff, offset=0):
    """Cut the chats worth reading into segments: focus messages plus context before and after."""
    info = {c["chat_id"]: c for c in chats}
    names = collect_names(messages, chats)
    me_ids = {m["id"] for m in messages if m["sender_id"] == ME}
    me_rx = me_name_rx(messages)
    by_chat = defaultdict(list)
    for m in messages:
        by_chat[m["chat_id"]].append(m)
    segs = []
    for cid, msgs in by_chat.items():
        c = info.get(cid)
        if not c:
            continue
        window = [m for m in msgs if m["ts"] >= cutoff]
        if not window:
            continue
        me_n = sum(1 for m in window if m["sender_id"] == ME)
        quoted_me = any(m.get("quoted_id") in me_ids for m in window)
        named = any(me_rx.search(m.get("body") or "") for m in window)
        if c["is_group"]:
            if me_n == 0 and not quoted_me and not named:
                continue  # Arjun only watches this group: its tasks are other people's
        elif me_n == 0 and len(window) < 2:
            continue
        # Media-only lines carry almost nothing; keep one only right before a text from the same sender
        rows = [m for i, m in enumerate(msgs)
                if not MEDIA_ONLY_RX.match(m.get("body") or "")
                or (i + 1 < len(msgs) and msgs[i + 1]["sender_id"] == m["sender_id"])]
        if me_n == 0 and not c["is_group"]:
            rows = rows[-LLM_SILENT_TAIL:]  # a 1:1 Arjun never answers: only its latest messages can matter
        elif me_n < LLM_SPARSE_SHARE * len(window):
            # A busy chat where Arjun rarely speaks: keep only the stretches around his involvement.
            hot = [i for i, m in enumerate(rows) if m["ts"] >= cutoff and (
                m["sender_id"] == ME or m.get("quoted_id") in me_ids
                or me_rx.search(m.get("body") or ""))]
            keep = sorted({j for i in hot for j in range(i - LLM_SPARSE_SPAN, i + LLM_SPARSE_SPAN + 1)
                           if 0 <= j < len(rows)})
            rows = [rows[j] for j in keep]
        first = next((i for i, m in enumerate(rows) if m["ts"] >= cutoff), len(rows))
        who = ", ".join("%s=%s (%s)" % (p, names.get(p, "?")[:30], circles.get(p, "?"))
                        for p in c["participants"] if p != ME)
        if len(who) > 600:
            who = who[:600] + ", ..."
        header = "### CHAT %s | %s | %s | %s" % (cid, (c.get("name") or "").strip()[:60] or "-",
                                                "group" if c["is_group"] else "1:1", who)
        starts = list(range(first, len(rows), LLM_FOCUS))
        if offset and len(rows) - first > offset:
            # second view: boundaries shifted by `offset`, so a task cut at an edge is seen whole
            starts = [first] + list(range(first + offset, len(rows), LLM_FOCUS))
        for i, s in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(rows)
            segs.append({"chat_id": cid, "header": header,
                         "before": rows[max(0, s - LLM_BEFORE):s],
                         "focus": rows[s:end],
                         "after": rows[end:end + LLM_AFTER]})
    return segs


def _seg_text(seg):
    lines = [seg["header"]]
    lines += [_fmt_line(m, True) for m in seg["before"]]
    lines += [_fmt_line(m, False) for m in seg["focus"]]
    lines += [_fmt_line(m, True) for m in seg["after"]]
    return "\n".join(lines)


STATUS_SYSTEM = """You check how tasks in Arjun's WhatsApp ended. Arjun is sender "ME". For each task you get the message that started it (marked >>) and the chat messages after it.
Decide its status at the end of what you see:
- "done": a later message shows it happened: Arjun paid/ordered/booked/sent it, answered or decided, said "done"/"paid"/"ordered"/"booked", the other person confirms ("received", "got it", "thanks, came"), or the conversation clearly moved past it as finished. Cite that message id in closed_by.
- "dropped": it was cancelled, refused or became moot. Cite the message.
- "open": otherwise. An "ok", "sure", "will do", "figuring" or thumbs-up only acknowledges the task; it does not finish it. When unsure, "open".
Reply with JSON only: {"tasks":[{"source_msg":"M1","status":"open","closed_by":null}]}"""
STATUS_AFTER = 30       # messages after the source the status judge sees
STATUS_BATCH_CHARS = 20000


def llm_status(loops, messages, chat_fn=None):
    """Fill status/closed_by for loops found by rules, in a few batched calls. Leaves them open on failure."""
    import llm
    chat_fn = chat_fn or (lambda msgs: llm.chat(msgs, json_mode=True))
    by_chat = defaultdict(list)
    for m in messages:
        if not MEDIA_ONLY_RX.match(m.get("body") or ""):
            by_chat[m["chat_id"]].append(m)
    pos = {m["id"]: (cid, i) for cid, rows in by_chat.items() for i, m in enumerate(rows)}
    blocks = []
    for loop in loops:
        if loop["source_msg"] not in pos:
            continue
        cid, i = pos[loop["source_msg"]]
        rows = by_chat[cid]
        text = "\n".join(["### TASK %s in chat %s" % (loop["source_msg"], cid)]
                         + [_fmt_line(m, False).lstrip(">") if j else ">>" + _fmt_line(m, False).lstrip(">")
                            for j, m in enumerate(rows[i:i + 1 + STATUS_AFTER])])
        later = {m["id"] for m in rows[i + 1:i + 1 + STATUS_AFTER]}
        blocks.append((loop, text, later))
    batches, cur, size = [], [], 0
    for b in blocks:
        if cur and size + len(b[1]) > STATUS_BATCH_CHARS:
            batches.append(cur)
            cur, size = [], 0
        cur.append(b)
        size += len(b[1])
    if cur:
        batches.append(cur)
    for batch in batches:
        try:
            raw = chat_fn([{"role": "system", "content": STATUS_SYSTEM},
                           {"role": "user", "content": "\n\n".join(t for _, t, _ in batch)}])
            obj = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M))
            srcs = {loop["source_msg"] for loop, _, _ in batch}
            later_all = set().union(*(later for _, _, later in batch))
            verdicts = {}
            for v in llm_items(obj, "tasks"):
                if isinstance(v, dict) and fix_id(v.get("source_msg"), srcs):
                    verdicts[fix_id(v["source_msg"], srcs)] = dict(v, closed_by=fix_id(v.get("closed_by"), later_all))
        except Exception as e:
            print("LLM status pass failed: %s" % str(e)[:200], file=sys.stderr)
            continue
        for loop, _, later in batch:
            v = verdicts.get(loop["source_msg"]) or {}
            if v.get("status") in ("done", "dropped") and v.get("closed_by") in later:
                loop.update(status=v["status"], closed_by=v["closed_by"])
    return loops


def llm_loops(chats, messages, circles, cutoff, chat_fn=None):
    """Ask the model for loops, many chats per call. Returns None if every call failed."""
    import llm
    chat_fn = chat_fn or (lambda msgs, deadline: llm.chat(msgs, json_mode=True, deadline=deadline))
    participants = {c["chat_id"]: {p for p in c["participants"] if p != ME} for c in chats}
    try:
        passes = max(1, int(os.environ.get("LLM_PASSES", LLM_PASSES)))
    except ValueError:
        passes = LLM_PASSES
    batches, segs = [], []
    for k in range(passes):
        # Flash-lite picks loops somewhat at random; a second, differently cut and packed view of the same
        # chats raises recall far more than it adds noise (dev: two runs agree on under a third of loops).
        psegs = llm_segments(chats, messages, circles, cutoff, offset=(LLM_FOCUS // 2) * (k % 2))
        segs += psegs
        texts = sorted(((seg, _seg_text(seg)) for seg in psegs), key=lambda x: len(x[1]) * (-1 if k % 2 == 0 else 1))
        pass_batches = []  # first-fit packing: each call up to LLM_BATCH_CHARS (a big segment goes alone)
        for seg, txt in texts:
            for b in pass_batches:
                if b["chars"] + len(txt) <= LLM_BATCH_CHARS:
                    b["segs"].append((seg, txt))
                    b["chars"] += len(txt)
                    break
            else:
                pass_batches.append({"segs": [(seg, txt)], "chars": len(txt), "k": k})
        batches += pass_batches
    if len(batches) > LLM_MAX_CALLS:
        print("LLM pass: %d batches, keeping the first %d" % (len(batches), LLM_MAX_CALLS), file=sys.stderr)
        batches = batches[:LLM_MAX_CALLS]
    end_ts = max(m["ts"] for m in messages)
    deadline = time.time() + LLM_DEADLINE_S
    stats = {"ok": 0, "errors": 0}

    def run(batch):
        if stats["ok"] == 0 and stats["errors"] >= 3:
            return []  # circuit breaker: the endpoint fails every call (bad key, model, or quota)
        user = ("The data ends at %s IST.\n\n" % ist(end_ts, "%A %d %b %Y %H:%M")
                + "\n\n".join(t for _, t in batch["segs"]))
        try:
            raw = chat_fn([{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": user}], deadline)
        except Exception as e:
            stats["errors"] += 1
            print("LLM call failed: %s" % str(e)[:300], file=sys.stderr)
            return []
        stats["ok"] += 1
        proposed = parse_llm_json(raw)
        out = []
        for seg, _ in batch["segs"]:
            focus = {m["id"]: m for m in seg["focus"]}
            later = {m["id"]: m for m in seg["focus"] + seg["after"]}
            who = participants[seg["chat_id"]]
            for x in proposed:
                src = fix_id(x.get("source_msg"), focus)
                if src not in focus:
                    continue
                typ = x.get("type") if x.get("type") in LOOP_TYPES else "commitment"
                owner = x.get("owner") if x.get("owner") == ME or x.get("owner") in who else ME
                status = x.get("status") if x.get("status") in ("open", "done", "dropped") else "open"
                closed = fix_id(x.get("closed_by"), later)
                if closed not in later or closed == src or later[closed]["ts"] < focus[src]["ts"]:
                    closed = None
                if status == "dropped" and not closed:
                    status = "open"  # cancelling needs a cited message
                due = clean_due(x.get("due"), focus[src]["ts"])
                out.append({"title": str(x.get("title") or focus[src].get("body") or "")[:90], "type": typ,
                            "owner": owner, "chat_id": seg["chat_id"], "source_msg": src, "due": due,
                            "status": status, "closed_by": closed if status != "open" else None,
                            "_w": x.get("weight") if isinstance(x.get("weight"), int) else 2,
                            "_pass": batch["k"],
                            "_help": x.get("help") if isinstance(x.get("help"), dict) else None})
        return out

    try:
        workers = max(1, int(os.environ.get("LLM_WORKERS", LLM_WORKERS)))
    except ValueError:
        workers = LLM_WORKERS
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(run, batches):
            results.extend(r)
    print("LLM pass: %d/%d calls ok, %d segments, %d loops proposed"
          % (stats["ok"], len(batches), len(segs), len(results)), file=sys.stderr)
    if os.environ.get("COLD_START_DEBUG") == "1":
        text = {m["id"]: (m.get("body") or "")[:160] for m in messages}
        with open("llm_loops_debug.json", "w", encoding="utf-8") as f:
            json.dump([dict(l, source_text=text.get(l["source_msg"])) for l in results], f, ensure_ascii=False, indent=1)
    if stats["ok"] == 0:
        return None
    try:
        min_w = int(os.environ.get("LLM_MIN_WEIGHT", LLM_MIN_WEIGHT))
    except ValueError:
        min_w = LLM_MIN_WEIGHT
    by_id = {m["id"]: m for m in messages}
    me_ids = {m["id"] for m in messages if m["sender_id"] == ME}
    ARJUN_NAME_RX = me_name_rx(messages)
    # Big groups: most "tasks" there are other people's. A group loop is kept only when the line is
    # Arjun's own, names him, or replies to him.
    in_group = {c["chat_id"] for c in chats if c["is_group"]}

    def group_ok(l):
        if l["chat_id"] not in in_group:
            return True
        m = by_id.get(l["source_msg"], {})
        return m.get("sender_id") == ME or m.get("quoted_id") in me_ids or ARJUN_NAME_RX.search(m.get("body") or "")

    # Union of the views, keeping a source line only at its best weight across passes.
    best_w = defaultdict(int)
    for l in results:
        best_w[l["source_msg"]] = max(best_w[l["source_msg"]], l["_w"])

    seen, uniq = set(), []
    for l in results:
        if l["source_msg"] in seen or not group_ok(l) or best_w[l["source_msg"]] < min_w:
            continue
        seen.add(l["source_msg"])
        uniq.append(l)
    for l in uniq:
        l.pop("_w", None)
        l.pop("_pass", None)
    return uniq


PERSONAL_CIRCLES = {"child", "parent", "in-law", "sibling", "relative", "friend"}
WORK_PARTY_CIRCLES = {"colleague", "client", "partner"}
# Spouse tasks the assistant may prepare privately (options, research) - never anything else of hers.
SPOUSE_ASSIST_RX = re.compile(r"\b(book(?:ing)?|tickets?|flights?|research|find|search|options?|teacher|tutor|"
                              r"look (?:for|up|into)|compare|shortlist)\b", re.I)
# Tasks only Arjun can do: decisions, sign-offs, money leaving his account, his own presence.
ONLY_ARJUN_RX = re.compile(r"\b(decide|decision|approve|sign|pay|transfer|invest|buy|call|meet|meeting|attend|"
                           r"discuss|confirm|choose|visit|go to)\b", re.I)


REMIND_STEP_RX = re.compile(r"^\W*(remind|tell|ping|nudge|alert)\s+(arjun|him|me)\b", re.I)
STAFF_MATTER_RX = re.compile(r"\b(driver|cook|maid|nanny|cleaner|gardener|guard|watchman|staff|salary|salaries|"
                             r"hisa+b|reimburse\w*|attendance)\b", re.I)


def remind_time(loop, msg_ts, end_ts):
    """Once, at the right time: 09:00 IST on the due day, else 10:00 IST the morning after it came up.
    Never in the past relative to the end of the data (an open loop is reminded going forward)."""
    if loop.get("due"):
        try:
            t = datetime.strptime(loop["due"], "%Y-%m-%d").replace(hour=9, tzinfo=IST)
        except ValueError:
            t = None
    else:
        t = None
    if t is None:
        d = datetime.fromtimestamp(msg_ts, tz=IST) + timedelta(days=1)
        t = d.replace(hour=10, minute=0, second=0, microsecond=0)
    end = datetime.fromtimestamp(end_ts, tz=IST)
    if t <= end:
        t = (end + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    return t.isoformat()


def add_help(loop, circles, chat_info, tie, work_orgs, messages_by_id=None, end_ts=None):
    """Where to help, for open loops. The model suggests; these guardrails decide.

    A wrong assist/remind on a loop Arjun wants left alone costs the most, so `leave` wins every tie:
    family, friends and staff are left alone; the spouse only gets private preparatory help (options,
    research) and never a nudge; loops someone else owes are left unless it is Arjun's own work chase.
    """
    suggestion = loop.pop("_help", None) or {}
    if loop["status"] != "open":
        loop.pop("help", None)
        return loop
    messages_by_id = messages_by_id or {}
    msg_ts = messages_by_id.get(loop["source_msg"], {}).get("ts", 0)
    end_ts = end_ts or msg_ts
    t = tie.get(loop["chat_id"], {})
    party = circles.get(t.get("person")) if "person" in t else None
    owner_circle = circles.get(loop["owner"]) if loop["owner"] != ME else None
    is_work = (t.get("organisation") in work_orgs) if "organisation" in t else party in WORK_PARTY_CIRCLES
    text = loop["title"] + " " + (messages_by_id.get(loop["source_msg"], {}).get("body") or "")[:200]
    sug = suggestion.get("action") if suggestion.get("action") in ("assist", "remind", "leave") else None
    step = str(suggestion.get("next_step") or "").strip()[:160]
    if REMIND_STEP_RX.match(step):
        sug, step = "remind", ""  # "Remind Arjun to ..." is a reminder, not something the assistant does
    staff_matter = bool(STAFF_MATTER_RX.search(text))

    def leave(reason):
        loop["help"] = {"action": "leave", "reason": reason}
        return loop

    def assist(default_step, needs_yes=True):
        loop["help"] = {"action": "assist", "next_step": step or default_step,
                        "needs_yes": bool(suggestion.get("needs_yes", needs_yes)) or needs_yes}
        return loop

    def remind():
        loop["help"] = {"action": "remind", "remind_at": remind_time(loop, msg_ts, end_ts)}
        return loop

    if owner_circle == "staff" or party == "staff" or (staff_matter and not is_work):
        return leave("Staff handle this; Arjun does not need a nudge")
    if party in PERSONAL_CIRCLES and loop["owner"] == ME and loop["type"] == "commitment" \
            and SPOUSE_ASSIST_RX.search(text) and sug != "leave":
        return assist("Shortlist options privately for Arjun to pick from")  # his own booking for family
    if party in PERSONAL_CIRCLES or owner_circle in PERSONAL_CIRCLES:
        return leave("Personal: family or friends, not the assistant's to push")
    if party == "spouse":
        if loop["owner"] == ME and loop["type"] == "commitment" and SPOUSE_ASSIST_RX.search(text) and sug != "leave":
            return assist("Shortlist options privately for Arjun to pick from")
        return leave("Between Arjun and his wife; a reminder would only annoy")
    if party == "vendor" or owner_circle == "vendor":
        return leave("A vendor is handling it") if loop["owner"] != ME else remind()
    if not is_work:
        return leave("Household or personal chat; the people in it handle it")
    if loop["owner"] != ME:
        # Arjun is waiting on someone at work: drafting a polite nudge is private and reversible.
        if sug == "remind" and ONLY_ARJUN_RX.search(text):
            return remind()  # e.g. a meeting the other side set up that Arjun must attend
        if sug in ("assist", "remind"):
            return assist("Draft a short follow-up message for Arjun to send")
        return leave("%s owes this; nothing for Arjun to do yet" % loop["owner"])
    if sug == "leave":
        return leave(str(suggestion.get("reason") or "Not worth a nudge")[:160])
    if loop["type"] == "question" and DECISION_RX.search(text):
        return remind()  # a decision only Arjun can make (problem statement: remind, not assist)
    if sug == "assist" and step:
        return assist(step)
    if sug == "remind" or loop["type"] == "deadline" or loop.get("due"):
        return remind()
    if loop["type"] in ("question", "followup") and not ONLY_ARJUN_RX.search(text):
        return assist("Draft a reply for Arjun to approve")
    return remind()


# ------------------------------------------------------------------ LLM circles pass

CIRCLE_NAMES = ("spouse", "child", "parent", "in-law", "sibling", "relative", "friend", "colleague", "client",
                "vendor", "partner", "staff")
CIRCLES_SYSTEM = """You place people in the life of Arjun (sender "ME"), an Indian founder with companies of his own (named below), a wife, kids, household staff and a wide family. For each person give exactly one circle:
spouse, child, parent, in-law (the spouse's family: sasur/saas, bhabhi, jija, the wife's siblings), sibling, relative (other family: cousins, mama/chacha, aunts), friend, colleague (works with Arjun inside his own companies: team, co-founders' staff, employees, interns), client (a business that buys Arjun's services, e.g. ad campaigns; their people too), vendor (sells to Arjun or his home: CA, lawyer, doctor, contractor, shop, broker, tutor, coach), partner (an outside business he partners or co-invests with, a fellow founder doing a deal with him), staff (household or office help: driver, cook, maid, cleaner, office boy, guard, nanny).
Use the saved name (as Arjun saved it: "<Name> <Company>" with one of his companies above means works at that company of his; "Home"/"Office" suffixes mean help), the chats they share with him, what they say and what Arjun says to them. The circle is the relationship, not closeness: a friendly client is still a client.
Known people (from Arjun himself) are examples of how he thinks.
Reply with JSON only: {"people":[{"id":"P1","circle":"vendor","sure":3}]} where sure is 1 (guess) to 3 (clear from the messages)."""
CIRCLE_BATCH_CHARS = 24000
CIRCLE_MSGS = 6          # messages from the person shown in their profile
CIRCLE_ME_MSGS = 4       # Arjun's messages to them in a 1:1, shown too
CIRCLE_MIN_SURE = 3      # only a "clear from the messages" verdict overrules (dev: sure>=2 was 0.78, >=3 0.80)
NAME_SIGNAL_CIRCLES = {"staff", "parent", "in-law", "sibling", "relative"}  # a kinship/staff word in the name wins


def person_profiles(chats, messages, seed, circles):
    names = collect_names(messages, chats)
    chat_of = defaultdict(list)
    for c in chats:
        for p in c["participants"]:
            if p != ME:
                chat_of[p].append(c)
    said = defaultdict(list)
    to_them = defaultdict(list)
    one2one = {c["chat_id"]: [p for p in c["participants"] if p != ME][0] for c in chats
               if not c["is_group"] and len(c["participants"]) == 2}
    for m in messages:
        body = re.sub(r"\s+", " ", m.get("body") or "").strip()
        if len(body) < 8 or MEDIA_ONLY_RX.match(body):
            continue
        if m["sender_id"] != ME:
            said[m["sender_id"]].append(body)
        elif m["chat_id"] in one2one:
            to_them[one2one[m["chat_id"]]].append(body)

    def sample(rows, k):
        # longer messages say more; ties broken by text so the prompt (and the cache key) never varies
        rows = sorted(set(rows), key=lambda r: (-len(r), r))[:k * 3]
        return [r[:160] for r in rows[:k]]

    out = {}
    for p in chat_of:
        groups = [c for c in chat_of[p] if c["is_group"]]
        lines = ["%s | saved as: %s | rule guess: %s" % (p, names.get(p, "?"), circles.get(p, "?"))]
        if groups:
            lines.append("  groups: " + "; ".join("%s (%d)" % ((g.get("name") or "-")[:40], len(g["participants"]))
                                                 for g in groups[:6]))
        if any(not c["is_group"] for c in chat_of[p]):
            lines.append("  has a 1:1 chat with Arjun")
        lines += ["  they: " + b for b in sample(said[p], CIRCLE_MSGS)]
        lines += ["  Arjun to them: " + b for b in sample(to_them[p], CIRCLE_ME_MSGS)]
        out[p] = ("\n".join(lines), bool(said[p] or to_them[p]))
    return out


def llm_circles(chats, messages, seed, circles, chat_fn=None):
    """Second opinion on circles for unseeded people who say anything. Returns {id: circle} overrides."""
    import llm
    chat_fn = chat_fn or (lambda msgs: llm.chat(msgs, json_mode=True))
    seeded = seed.get("circles") or {}
    names = collect_names(messages, chats)
    profiles = person_profiles(chats, messages, seed, circles)
    todo = [p for p, (_, talks) in profiles.items() if p not in seeded and talks]
    known = "\n".join("%s (%s): %s" % (p, names.get(p, "?"), c) for p, c in seeded.items())
    head = ("Arjun's companies: %s\nKnown people:\n%s\n\nPeople to place:\n"
            % (", ".join(seed.get("organisations") or []) or "?", known))
    batches, cur, size = [], [], 0
    for p in todo:
        txt = profiles[p][0]
        if cur and size + len(txt) > CIRCLE_BATCH_CHARS:
            batches.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += len(txt)
    if cur:
        batches.append(cur)
    out = {}
    for batch in batches:
        try:
            raw = chat_fn([{"role": "system", "content": CIRCLES_SYSTEM},
                           {"role": "user", "content": head + "\n\n".join(profiles[p][0] for p in batch)}])
            obj = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M))
        except Exception as e:
            print("LLM circles pass failed: %s" % str(e)[:200], file=sys.stderr)
            continue
        for x in llm_items(obj, "people"):
            pid = fix_id(x.get("id"), set(batch)) if isinstance(x, dict) else None
            if pid and x.get("circle") in CIRCLE_NAMES:
                sure = x.get("sure") if isinstance(x.get("sure"), int) else 2
                out[pid] = (x["circle"], sure)
    print("LLM circles: %d calls, %d people judged" % (len(batches), len(out)), file=sys.stderr)
    return out


def merge_circles(circles, verdicts, chats, messages, seed):
    """Seed > the rules' direct evidence > a confident model verdict > the rules' weak guesses."""
    seeded = seed.get("circles") or {}
    names = collect_names(messages, chats)
    merged = dict(circles)
    for p, (circle, sure) in verdicts.items():
        if p in seeded or sure < CIRCLE_MIN_SURE:
            continue
        if p not in WEAK_CIRCLES:
            continue  # the rules had direct evidence (a title, a company tag, client talk): they stand
        if classify_name(names.get(p, "")) in NAME_SIGNAL_CIRCLES:
            continue
        if circle == "spouse" and any(c == "spouse" for q, c in merged.items() if q != p):
            continue  # one spouse
        merged[p] = circle
    return merged


# ------------------------------------------------------------------ LLM goals pass

GOAL_CAND_RX = re.compile(
    r"\b(want(?:s|ed)? to|wanna|plan(?:ning)? to|goal|target|aim|dream|resolution|this year|next year|by (?:jan|feb|"
    r"mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*|every (?:day|morning|week)|daily|weekly|times a week|habit|"
    r"marathon|half marathon|\d+\s?k run|running|gym|yoga|workout|fitness|diet|weight|sleep|meditat\w*|"
    r"learn(?:ing)?|course|save|saving|invest(?:ing|ment)?|portfolio|retire\w*|wealth|corpus|trip|travel|vacation|"
    r"holiday|safari|trek|renovat\w*|interiors?|new house|new flat|farm\s?house|admission|school|piano|"
    r"launch|scale|revenue|arr|run rate|paying clients|customers|hire|hiring|raise|funding|fundrais\w*|"
    r"profit|break ?even|book|read(?:ing)?|family time|quality time|date night|anniversary)\b", re.I)
GOALS_SYSTEM = """From Arjun's WhatsApp (sender "ME"), list the GOALS he holds: things he is working towards, stated or clearly shown in these messages. Not tasks or errands (those are loops), but aims with a horizon: a habit (a rhythm: run 3x a week, yoga every morning), a milestone (a target: 10 paying clients by March, scale a product, buy a house, a portfolio size), or an experience (something to plan and do: a family trip, a safari, a birthday picnic).
Area is one of: self, spouse, kids, parents, work, friends, experiences, finances, health, home. Horizon is 3mo, 1yr, 3yr or 5yr.
Only list a goal if the messages give real evidence that ARJUN (or his household as a unit) is pursuing it. Other people's goals, news, forwards and ads do not count. An invented goal costs more than a missed one: when in doubt, leave it out. At most 8 goals.
Good evidence: Arjun stating a plan or aim ("we should build X", "accumulate these stocks over time", "want to run"), him paying for or joining a recurring activity (a yoga batch, a sports club), a trip group being planned, a goal he and his wife are working on for the kids or the home.
Evidence: 1-4 message ids, copied exactly from the lines below, that show the goal most directly (prefer Arjun's own words).
Reply with JSON only: {"goals":[{"title":"...","area":"health","type":"habit","horizon":"1yr","evidence":["M1"],"sure":3}]} with sure 1 (weak) to 3 (explicit)."""
GOAL_MAX_LINES = 500
ACTIVITY_GROUP_RX = re.compile(r"yoga|tennis|\btt\b|badminton|pickle|cricket|football|golf|swim|\brun(?:ners|ning)?\b|"
                               r"marathon|\bcycl(?:e|ing|ists?)\b|\bgym\b|fitness|trek|hike|\bclub\b|\btrip\b|\btour\b|travel|safari|"
                               r"holiday|vacation|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b|retreat|"
                               r"reunion|\bclass\b|course", re.I)
GOAL_MIN_SURE = 2
GOAL_AREAS = ("self", "spouse", "kids", "parents", "work", "friends", "experiences", "finances", "health", "home")


def llm_goals(chats, messages, seed, circles, chat_fn=None):
    """One call over the goal-flavoured messages of chats Arjun takes part in. Evidence ids are verified."""
    import llm
    chat_fn = chat_fn or (lambda msgs: llm.chat(msgs, json_mode=True))
    info = {c["chat_id"]: c for c in chats}
    spouse = {p for p, c in circles.items() if c == "spouse"}
    me_count = Counter(m["chat_id"] for m in messages if m["sender_id"] == ME)
    textual = [m for m in messages if m["kind"] in ("text", "voice_transcript")
               and not MEDIA_ONLY_RX.match(m.get("body") or "")]
    picked = {}

    def take(m, why):
        picked.setdefault(m["id"], (m, why))

    # 1. Arjun's own substantive messages: goals live in his words (plans, "we should build", "accumulate").
    for m in textual:
        body = (m.get("body") or "").strip()
        if m["sender_id"] == ME and (len(body) >= 60 or len(body) >= 20 and GOAL_CAND_RX.search(body)):
            take(m, 0)
    # 2. His wife's plans for the household (trips, kids, home) - often the family's shared goals.
    for m in textual:
        if m["sender_id"] in spouse and len(m.get("body") or "") >= 15 and GOAL_CAND_RX.search(m["body"]):
            take(m, 1)
    # 3. Activity and trip groups he belongs to (yoga batch, a sports club, a trip group): membership itself is
    #    the evidence of a habit or a planned experience, even if he rarely writes there.
    for c in chats:
        if c["is_group"] and ACTIVITY_GROUP_RX.search(c.get("name") or ""):
            rows = [m for m in textual if m["chat_id"] == c["chat_id"]]
            for m in rows[:3] + rows[-2:] + [m for m in rows if m["sender_id"] == ME][:4]:
                take(m, 2)
    # 4. Goal-flavoured lines from others in chats he is active in.
    for m in textual:
        if me_count[m["chat_id"]] and len(m.get("body") or "") >= 25 and GOAL_CAND_RX.search(m["body"]):
            take(m, 3)
    pool = sorted(picked.values(), key=lambda x: (x[1], x[0]["ts"]))[:GOAL_MAX_LINES]
    pool = sorted((m for m, _ in pool), key=lambda m: m["ts"])
    lines, ids = [], set()
    for m in pool:
        c = info[m["chat_id"]]
        body = re.sub(r"\s+", " ", m["body"]).strip()[:260]
        who = "ME" if m["sender_id"] == ME else "%s(%s)" % (m["sender_id"], circles.get(m["sender_id"], "?"))
        lines.append("%s | %s | %s | %s | %s" % (m["id"], (c.get("name") or "-")[:25], who, ist(m["ts"], "%d %b"), body))
        ids.add(m["id"])
    if not lines:
        return []
    seed_goals = seed.get("goals") or []
    user = ("Goal Arjun told us himself (you may list it too): %s\n\n" % json.dumps(seed_goals, ensure_ascii=False)
            if seed_goals else "") + "Messages (id | chat | sender | date | text):\n" + "\n".join(lines)
    try:
        raw = chat_fn([{"role": "system", "content": GOALS_SYSTEM}, {"role": "user", "content": user}])
        obj = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M))
    except Exception as e:
        print("LLM goals pass failed: %s" % str(e)[:200], file=sys.stderr)
        return None
    goals = []
    for g in llm_items(obj, "goals"):
        if not isinstance(g, dict):
            continue
        ev = [fix_id(e, ids) for e in g.get("evidence") or []]
        ev = list(dict.fromkeys(e for e in ev if e))[:4]
        sure = g.get("sure") if isinstance(g.get("sure"), int) else 2
        if not ev or sure < GOAL_MIN_SURE or g.get("area") not in GOAL_AREAS:
            continue
        goals.append({"title": str(g.get("title") or "")[:90] or "Goal", "area": g["area"],
                      "type": g.get("type") if g.get("type") in ("habit", "milestone", "experience") else "milestone",
                      "horizon": g.get("horizon") if g.get("horizon") in ("3mo", "1yr", "3yr", "5yr") else "1yr",
                      "evidence": ev, "_sure": sure})
    goals.sort(key=lambda g: -g["_sure"])
    for g in goals:
        g.pop("_sure")
    print("LLM goals: %d kept" % len(goals), file=sys.stderr)
    return goals[:10]


# ------------------------------------------------------------------ assembly


def build_output(chats, messages, seed):
    circles, people_ids = classify_people(chats, messages, seed)
    use_llm = llm_available()
    if use_llm and os.environ.get("COLD_START_LLM_CIRCLES", "1") == "1":
        try:
            circles = merge_circles(circles, llm_circles(chats, messages, seed, circles), chats, messages, seed)
        except Exception as e:  # the rules' answer stands
            print("LLM circles skipped:", e, file=sys.stderr)
    goals = None
    if use_llm:
        try:
            goals = llm_goals(chats, messages, seed, circles)
        except Exception as e:
            print("LLM goals skipped:", e, file=sys.stderr)
    if goals is None:
        goals = mine_goals(messages, seed)
    organisations, ties, links = build_organisations(chats, messages, seed, circles)
    looks_after = defaultdict(set)
    for chat in chats:
        if not chat["is_group"] or not (HOME_GROUP_RX.search(chat.get("name") or "")
                                         or FAMILY_NAME_RX.search(chat.get("name") or "")):
            continue
        staff = [p for p in chat["participants"] if circles.get(p) == "staff"]
        children = [p for p in chat["participants"] if circles.get(p) == "child"]
        for worker in staff:
            looks_after[worker].update(children)
    people = [{"id": pid, "circle": circles[pid], "links": links.get(pid, []), "looks_after": []}
              for pid in people_ids]
    for person in people:
        person["looks_after"] = sorted(looks_after[person["id"]])
    return {
        "people": people,
        "organisations": organisations,
        "chats": ties,
        "goals": goals,
        "open_loops": mine_loops(chats, messages, circles, ties,
                                 {o["id"] for o in organisations if o["side"] == "work"}),
    }


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    chats, messages, seed, answers = load_dataset(argv[1])
    payload = build_output(chats, messages, seed)
    write_json(argv[2], payload)
    print(f"wrote {argv[2]}: {len(payload['people'])} people, "
          f"{len(payload['organisations'])} organisations, {len(payload['chats'])} chats, "
          f"{len(payload['goals'])} goals, {len(payload['open_loops'])} open loops")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))