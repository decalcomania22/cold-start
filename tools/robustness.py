"""Unseen-name check: rebuild a dataset with every personal and company name replaced, then score it.
The hidden set renames everyone, so a solution that depends on dev's names loses points here.
usage: python tools/robustness.py [data/dev] [--llm] [--seeds 1,2,3]
Without --llm it runs rules only (free, deterministic); with --llm each copy gets a fresh reply cache."""
import copy, json, os, random, re, shutil, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")
import check, solution as S

SYL = ["ka", "ri", "vo", "lan", "te", "mi", "sha", "ro", "dev", "na", "pi", "ya", "ul", "ben", "jo", "ta", "su", "ker"]
# Words any of the code's regexes match are role/kinship/place words ("Driver", "Mama", "Office"): those
# survive a rename in a real contact list, so they stay. Everything else capitalised is treated as a name.
RXS = [v for v in vars(S).values() if isinstance(v, re.Pattern)] + [r for _, r in S.CIRCLE_RES]


def rename(src, dst, k):
    rnd = random.Random(k)
    rd = lambda f: [json.loads(l) for l in open(os.path.join(src, f), encoding="utf-8")]
    chats, msgs = rd("chats.jsonl"), rd("messages.jsonl")
    seed = json.load(open(os.path.join(src, "seed.json"), encoding="utf-8"))
    fresh = lambda w: (lambda n: n.upper() if w.isupper() else n.capitalize())(
        "".join(rnd.choice(SYL) for _ in range(rnd.choice((2, 3)))))
    mapping = {}
    is_name = lambda w: len(w) >= 3 and w[0].isupper() and not any(r.search(w) for r in RXS)
    new_orgs = []
    for o in seed.get("organisations", []):
        # Rename word by word so the parts stay consistent with the chat names ("Brightside team"), and
        # CamelCase part by part so the acronym does too ("PMA Operations" -> "<new acronym> Operations").
        if " " in o:
            new = " ".join(mapping.setdefault(w.lower(), fresh(w)) if is_name(w) else w for w in o.split())
        elif S.acronym(o):
            new = "".join(fresh("x") for _ in re.findall(r"[A-Z][a-z]*", o))
        else:
            new = mapping.setdefault(o.lower(), fresh(o))
        mapping[o.lower()] = new
        if S.acronym(o) and S.acronym(new) and len(S.acronym(new)) == len(S.acronym(o)):
            mapping[S.acronym(o)] = S.acronym(new).upper()
        new_orgs.append(new)
    for text in [m.get("sender_name") for m in msgs] + [c.get("name") for c in chats]:
        for w in re.findall(r"[A-Za-z]{3,}", text or ""):
            if is_name(w) and w.lower() not in mapping:
                mapping[w.lower()] = fresh(w)
    seed["organisations"] = new_orgs
    rx = re.compile(r"\b(%s)\b" % "|".join(map(re.escape, sorted(mapping, key=len, reverse=True))), re.I)
    sub = lambda t: t and rx.sub(lambda m: mapping[m.group(0).lower()].upper()
                                 if m.group(0).isupper() and len(m.group(0)) > 1 else mapping[m.group(0).lower()], t)
    for m in msgs:
        m["sender_name"], m["body"] = sub(m.get("sender_name")), sub(m.get("body"))
    for c in chats:
        c["name"] = sub(c.get("name"))
    for g in seed.get("goals") or []:
        g["title"] = sub(g.get("title"))
    os.makedirs(dst, exist_ok=True)
    for f, rows in (("chats.jsonl", chats), ("messages.jsonl", msgs)):
        with open(os.path.join(dst, f), "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    json.dump(seed, open(os.path.join(dst, "seed.json"), "w", encoding="utf-8"), ensure_ascii=False)
    shutil.copytree(os.path.join(src, "answers"), os.path.join(dst, "answers"), dirs_exist_ok=True)


def score(folder, out_path):
    chats, msgs, seed, ans = check.load_input(folder)
    out = json.load(open(out_path, encoding="utf-8"))
    if check.validate(out, chats, msgs):
        return None
    w2 = copy.deepcopy(ans)
    w2["loops_scored_from"] = min(m["ts"] for m in msgs) + 7 * 86400  # week 1 as context, like the hidden set
    s, w = check.score(out, ans, seed, msgs), check.score(out, w2, seed, msgs)
    pts = {k: (s[k] or 0) * check.POINTS[k] for k in ("circles", "organisations", "chats", "loops_found", "loops_closed")}
    pts["total"] = sum(pts.values())
    pts["wk2_loops"] = ((w["loops_found"] or 0) + (w["loops_closed"] or 0)) * 14
    return pts


def run(folder, out, tmp, use_llm, tag):
    env = dict(os.environ, COLD_START_LLM="1" if use_llm else "0", LLM_CACHE_DIR=os.path.join(tmp, "cache_" + tag))
    subprocess.run([sys.executable, os.path.join(ROOT, "solution.py"), folder, out], env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return score(folder, out)


def main():
    argv = sys.argv[1:]
    seeds = [1, 2, 3]
    if "--seeds" in argv:
        i = argv.index("--seeds")
        seeds = [int(x) for x in argv[i + 1].split(",")]
        argv = argv[:i] + argv[i + 2:]
    use_llm = "--llm" in argv
    args = [a for a in argv if not a.startswith("--")]
    src = os.path.abspath(args[0] if args else os.path.join(ROOT, "data", "dev"))
    tmp = tempfile.mkdtemp(prefix="robust_")
    rows = [("original", run(src, os.path.join(tmp, "orig.json"), tmp, use_llm, "orig"))]
    for k in seeds:
        d = os.path.join(tmp, "renamed%d" % k)
        rename(src, d, k)
        rows.append(("renamed%d" % k, run(d, os.path.join(tmp, "r%d.json" % k), tmp, use_llm, str(k))))
    print("%s, %s" % (os.path.basename(src), "with the model (fresh cache each)" if use_llm else "rules only"))
    for tag, p in rows:
        print("%-10s " % tag + ("INVALID OUTPUT" if p is None else "  ".join("%s %.1f" % kv for kv in p.items())))
    base = rows[0][1]["total"]
    worst = min(p["total"] for _, p in rows[1:])
    print("worst renamed total %.1f vs original %.1f (drop %.1f)" % (worst, base, base - worst))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
