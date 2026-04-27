import gurobipy as gp
from gurobipy import GRB
import numpy as np

# ── Data ──────────────────────────────────────────────────────────
# Generate random returns for 10 bonds over 100 days (scenarios).
np.random.seed(42)  # For reproducibility
T = 500    # number of scenarios (days)
N = 100     # number of bonds (assets)
# Simulate correlated returns to better mimic realistic asset returns
mean_returns = np.random.uniform(0.005, 0.015, size=N)
# Simulate a random but positive semi-definite covariance matrix
random_matrix = np.random.normal(size=(N, N))
cov_matrix = np.dot(random_matrix, random_matrix.T) / N**2  # Shrink for realism
returns = np.random.multivariate_normal(mean_returns, cov_matrix, size=T)

T, N = returns.shape   # T=4 scenarios, N=3 assets
alpha = 0.75           # confidence level
kappa = 0.03           # CVaR budget (max 3% average tail loss)

# ── Model ─────────────────────────────────────────────────────────
m = gp.Model("cvar_example")
m.setParam("OutputFlag", 0)   # suppress solver output

# ── Decision Variables ────────────────────────────────────────────
w    = m.addVars(N, lb=0.0, name="w")         # portfolio weights
zeta = m.addVar(lb=-GRB.INFINITY, name="zeta") # VaR level (can be negative)
u    = m.addVars(T, lb=0.0, name="u")          # overflow per scenario

# ── Objective: maximize average return ────────────────────────────
avg_return = gp.quicksum(
    returns[s, i] * w[i]
    for s in range(T)
    for i in range(N)
) / T

m.setObjective(avg_return, GRB.MAXIMIZE)

# ── Constraints ───────────────────────────────────────────────────

# 1. Fully invested
m.addConstr(gp.quicksum(w[i] for i in range(N)) == 1, name="budget")

# 2. Overflow definition: u_s >= -portfolio_return_s - zeta
for s in range(T):
    portfolio_loss_s = -gp.quicksum(returns[s, i] * w[i] for i in range(N))
    m.addConstr(u[s] >= portfolio_loss_s - zeta, name=f"overflow_{s}")

# 3. CVaR constraint: zeta + 1/((1-alpha)*T) * sum(u) <= kappa
m.addConstr(
    zeta + (1.0 / ((1 - alpha) * T)) * gp.quicksum(u[s] for s in range(T)) <= kappa,
    name="cvar"
)

# ── Solve ─────────────────────────────────────────────────────────
m.optimize()

# ── Results ───────────────────────────────────────────────────────
print("Optimal weights:")
for i in range(N):
    print(f"  w[{i+1}] = {w[i].X:.4f}")

print("\nNon-zero weights:")
for i in range(N):
    if w[i].X > 0:
        print(f"  w[{i+1}] = {w[i].X:.4f}")

print(f"\nzeta (VaR level) = {zeta.X:.4f}")
print(f"u (overflows)    = {[round(u[s].X, 4) for s in range(T)]}")
print(f"Avg return       = {m.ObjVal:.4f}")