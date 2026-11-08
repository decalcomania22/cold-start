"""Dev-set ceilings: how much of each remaining gap the data can support at all (WRITEUP, "How far can it go").
usage: python tools/ceiling.py output.json   (needs data/dev/answers)"""
import json, os, sys, collections, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")
import check

chats, msgs, seed, ans = check.load_input(os.path.join(ROOT, "data", "dev"))
out = json.load(open(sys.argv[1], encoding="utf-8"))
by_id = {m["id"]: m for m in msgs}
cc = {c["chat_id"]: c for c in chats}
sent = collections.Counter(m["sender_id"] for m in msgs)
one2one = {p for c in chats if not c["is_group"] for p in c["participants"] if p != "ME"}
seeded = set((seed.get("circles") or {}))

print("=== CIRCLES")
ours = {p["id"]: p["circle"] for p in out["people"]}
scored = [p for p in ans["people"] if p["id"] not in seeded]
wrong = [p for p in scored if ours.get(p["id"]) != p["circle"]]
silent = [p for p in wrong if sent[p["id"]] == 0]
fewer3 = [p for p in wrong if 0 < sent[p["id"]] < 3]
print(f"scored {len(scored)}, wrong {len(wrong)}; of the wrong: {len(silent)} never send a message, "
      f"{len(fewer3)} send 1-2; {sum(p['id'] in one2one for p in wrong)} have a 1:1")
print("  confusions:", collections.Counter((p["circle"], ours.get(p["id"])) for p in wrong).most_common(8))
for p in wrong:
    print(f"   {p['id']:5} key={p['circle']:9} ours={ours.get(p['id']):9} sent={sent[p['id']]:3} 1:1={p['id'] in one2one}")

print("\n=== ORGANISATIONS")
matched, n_a, n_o = check.match_orgs(out, ans)
for o in ans["organisations"]:
    mem = check.org_members(o["id"], ans["chats"], ans["people"])
    ev = [x for x in mem if x.startswith("c:")]
    j = matched.get(o["id"], (None, 0))[1]
    print(f"  {o['name']:12} members={len(mem):2} chats={len(ev):2} ours_jaccard={j:.2f}")
print(f"  score now {sum(v[1] for v in matched.values()) / max(n_a, n_o):.3f}; if every org with evidence "
      f"matched perfectly and DaaS/Farmhouse stayed missed: {5 / max(n_a, n_o):.3f}")

print("\n=== CHATS")
tie = {t["chat_id"]: t for t in out["chats"]}
for c in ans["chats"]:
    t = tie.get(c["chat_id"], {})
    ok = (t.get("person") == c.get("person")) if "person" in c else (
        t.get("organisation") is not None and matched.get(c["organisation"], (None,))[0] == t.get("organisation"))
    if not ok:
        print(f"  miss {c['chat_id']} '{cc[c['chat_id']]['name'][:30]}' key={c} ours={t}")

print("\n=== LOOPS")
L = ans["open_loops"]
srcs = [tuple(a["source_msgs"]) for a in L]
uniq_first = len({s[0] for s in srcs})
src_count = collections.Counter(x for a in L for x in a["source_msgs"])
shared = sum(1 for a in L if any(src_count[x] > 1 for x in a["source_msgs"]))
# one predicted loop matches at most one answer loop; a source shared by k answer loops can match only k
# of them if we emit it k times. Emitting one loop per source: max matched = maximum matching (greedy ok here)
used, got = set(), 0
for a in L:
    for x in a["source_msgs"]:
        if x not in used:
            used.add(x); got += 1; break
print(f"answer loops {len(L)}; loops sharing a source with another loop: {shared}; "
      f"max matchable with one loop per source: {got} (recall cap {got / len(L):.2f})")
kinds = collections.Counter()
for a in L:
    m = by_id[a["source_msgs"][0]]
    body = (m.get("body") or "").strip()
    if re.match(r"^\[(photo|video|image|document|sticker)\]", body, re.I) or m["kind"] in ("image_caption", "document"):
        kinds["media/document source"] += 1
    elif len(body) < 15:
        kinds["source under 15 chars"] += 1
    if cc[m["chat_id"]]["is_group"] and len(cc[m["chat_id"]]["participants"]) > 6:
        kinds["in a group of 7+"] += 1
print("  hard sources:", dict(kinds))
done = [a for a in L if a["status"] == "done"]
no_close = [a for a in done if not [x for x in (a.get("closing_msgs") or []) if x in by_id]]
print(f"done loops {len(done)}; with no closing message in the data: {len(no_close)} "
      f"(status must be guessed; a wrong guess on an open loop costs 1)")
# score ceilings
for R in (got / len(L),):
    for P in (0.20, 0.30, 0.50, 1.0):
        f1 = 2 * P * R / (P + R)
        print(f"  found score if recall={R:.2f} and precision={P:.2f}: {f1 * 14:.1f}/14;"
              f" closed ceiling at that recall: {R * 14:.1f}/14")
pairs, used = [], set()
for l in out["open_loops"]:
    for j, a in enumerate(L):
        if j not in used and l["source_msg"] in a["source_msgs"]:
            used.add(j); pairs.append((l, a)); break
print(f"  ours: predicted {len(out['open_loops'])}, matched {len(pairs)} "
      f"(P {len(pairs) / len(out['open_loops']):.2f}, R {len(pairs) / len(L):.2f})")
