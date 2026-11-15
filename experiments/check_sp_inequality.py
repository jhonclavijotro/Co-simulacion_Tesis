"""
Numerical audit of:  S_p >= kappa * n^(1-p/2) * V(e)^(p/2)
with V(e) = 0.5 e^T H e, H = L + diag(b),
S_p = 0.5 * sum_{i,j} a_ij |e_i-e_j|^p (ordered pairs) + sum_i b_i |e_i|^p.

Reports rho = S_p / (n^(1-p/2) V^(p/2)) and rho_m = S_p / (m^(1-p/2) V^(p/2))
with m = |E| + #{i: b_i>0}.  rho bounded below  ==> claim survives for that family.
"""
import numpy as np

def build(n, edges, b=None, a=1.0):
    A = np.zeros((n, n))
    for (i, j) in edges:
        A[i, j] = A[j, i] = a
    L = np.diag(A.sum(1)) - A
    b = np.zeros(n) if b is None else np.asarray(b, float)
    H = L + np.diag(b)
    return A, L, H, b

def Sp(e, A, b, p):
    n = len(e)
    s = 0.0
    for i in range(n):
        for j in range(n):
            if i != j:
                s += A[i, j] * abs(e[i] - e[j]) ** p
    return 0.5 * s + float(np.sum(b * np.abs(e) ** p))

def V(e, H):
    return 0.5 * float(e @ H @ e)

def rho(n, e, A, b, H, p):
    v = V(e, H)
    m = int((A > 0).sum() // 2) + int(np.sum(b > 0))
    sp = Sp(e, A, b, p)
    if v <= 1e-14 * max(1.0, float(e @ e)):
        return None
    return sp / (n ** (1 - p / 2) * v ** (p / 2)), sp / (m ** (1 - p / 2) * v ** (p / 2))

print("=== (i) identity checks ===")
rng = np.random.default_rng(0)
n = 12
edges = [(i, j) for i in range(n) for j in range(i + 1, n)]
A, L, H, b = build(n, edges, b=np.ones(n) * 0.3)
e = rng.normal(size=n)
lhs = float(e @ L @ e)
rhs = 0.5 * sum(A[i, j] * (e[i] - e[j]) ** 2 for i in range(n) for j in range(n))
print(f"  x^T L x = {lhs:.10f} | 0.5*sum a_ij (x_i-x_j)^2 = {rhs:.10f} | diff {abs(lhs-rhs):.2e}")
print(f"  S_2 = {Sp(e, A, b, 2):.10f} | e^T H e = {float(e @ H @ e):.10f} (=> S_2 = 2V)")
print(f"  lambda_1..3 of L = {np.sort(np.linalg.eigvalsh(L))[:3]}")

print("\n=== (ii) dense complete graph, balanced +/-1/sqrt(n), p=4 ===")
for n in [10, 20, 40, 80, 160, 320]:
    edges = [(i, j) for i in range(n) for j in range(i + 1, n)]
    A, L, H, b = build(n, edges)
    e = np.array([1.0] * (n // 2) + [-1.0] * (n - n // 2)) / np.sqrt(n)
    r = rho(n, e, A, b, H, 4)
    m = n * (n - 1) // 2
    print(f"  n={n:4d} m={m:6d}  rho_n={r[0]:8.4f}  rho_m={r[1]:8.4f}")

print("\n=== (iii) sparse path graph, e_i = i - mean, p=4 ===")
for n in [10, 20, 40, 80, 160, 320]:
    edges = [(i, i + 1) for i in range(n - 1)]
    A, L, H, b = build(n, edges)
    e = np.arange(n, dtype=float)
    e -= e.mean()
    r = rho(n, e, A, b, H, 4)
    m = n - 1
    print(f"  n={n:4d} m={m:6d}  rho_n={r[0]:8.4f}  rho_m={r[1]:8.4f}")

print("\n=== (iv) sparse path + b_i=1, random e, p in {1.5, 2, 4} ===")
for p in [1.5, 2.0, 4.0]:
    out = []
    for n in [10, 40, 160, 640]:
        edges = [(i, i + 1) for i in range(n - 1)]
        A, L, H, b = build(n, edges, b=np.ones(n))
        e = rng.normal(size=n)
        r = rho(n, e, A, b, H, p)
        out.append(f"n={n}:rho_n={r[0]:.4f},rho_m={r[1]:.4f}")
    print(f"  p={p}: " + "  ".join(out))

print("\n=== (v) p=1.5, spike vector, complete graph (stress the n^(1-p/2) factor) ===")
for n in [10, 40, 160, 640]:
    edges = [(i, j) for i in range(n) for j in range(i + 1, n)]
    A, L, H, b = build(n, edges)
    e = np.zeros(n); e[0] = 1.0
    for p in [1.5]:
        r = rho(n, e, A, b, H, p)
        print(f"  n={n:4d} p={p}  rho_n={r[0]:8.4f}  rho_m={r[1]:8.4f}")

print("\n=== (vi) worst-case scan: min rho_m over random graphs/vectors, p=4 ===")
worst = np.inf
worst_cfg = None
for trial in range(400):
    n = int(rng.integers(6, 25))
    k = int(rng.integers(1, max(2, n * (n - 1) // 2 + 1)))
    allp = [(i, j) for i in range(n) for j in range(i + 1, n)]
    edges = [allp[t] for t in rng.choice(len(allp), size=min(k, len(allp)), replace=False)]
    b = rng.uniform(0, 2, size=n) * (rng.random(n) < 0.4)
    A, L, H, bb = build(n, edges, b=b)
    e = rng.normal(size=n)
    r = rho(n, e, A, bb, H, 4)
    if r and r[1] < worst:
        worst = r[1]; worst_cfg = (n, len(edges), int(np.sum(bb > 0)))
print(f"  min rho_m = {worst:.4f} at (n,|E|,supp b) = {worst_cfg}  [theory predicts lower bound 2^(p/2)=4]")
