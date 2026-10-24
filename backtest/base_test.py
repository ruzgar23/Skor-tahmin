import sys; sys.path.insert(0, sys.path[0]); from lib import *
R = load(); A = collections.defaultdict(Acc)
for m in R:
    if not m["o"]: continue
    g = grade(m["o"])
    if not g: continue
    fam, key, p, tier = g
    A[(tier, "all")].add(m, key, p); A[(tier, fam)].add(m, key, p)
for k in sorted(A, key=lambda k: (-k[0], k[1])): print(A[k].row(f"{['','Düşük','Orta','Güçlü'][k[0]]} {k[1]}"))
