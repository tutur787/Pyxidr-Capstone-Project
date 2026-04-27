# CVaR — Meeting Notes
### FABN Portfolio Optimization | Pyxidr Capstone

---

## 1. What Problem Are We Solving?

Our FABN portfolio earns a **spread**: the difference between what our bond portfolio yields and what we owe on the FABN liability. We want to maximize that spread.

But bond prices move every day. Some days are normal. Some days are ugly — spreads widen, prices drop, correlations break down. Our optimizer, as it stands, chases yield without any regard for how bad things could get on the worst days.

**CVaR is how we fix that.** It lets us say: *"maximize spread, but don't let the tail risk exceed a threshold we're comfortable with."*

---

## 2. Building Intuition: The Loss Distribution

Given portfolio weights **w**, our portfolio has a return each day. Flip the sign — that's the **loss**.

Line up 500 days of portfolio losses from smallest to largest. You get a distribution:

```
Frequency
    │
    │     ████
    │    ██████
    │   ████████
    │  ██████████
    │ ████████████░░░░░
    └──────────────────────────────▶ Loss
                  ↑        ↑
                VaR      CVaR
             (threshold)  (avg of tail)
```

The right tail — the rare, bad days — is what we want to control.

---

## 3. VaR — Value at Risk

> **"What is the loss I will not exceed, 95% of the time?"**

At confidence level **α = 0.95**, VaR is the **95th percentile of the loss distribution**.

**In plain Python** (for fixed weights):

```python
losses = -(returns @ w)             # loss = negative return
VaR_95 = np.percentile(losses, 95)  # that's literally it
```

**The problem with VaR:** It tells you where the tail starts, but nothing about how bad the tail is. Two portfolios can have the same VaR but very different tail severities.

---

## 4. CVaR — Conditional Value at Risk

> **"Given that I'm already in the worst 5% of days — what is my average loss?"**

CVaR is the **expected loss, conditional on being beyond the VaR threshold**.

$$\text{CVaR}_\alpha = \mathbb{E}[\text{Loss} \mid \text{Loss} \geq \text{VaR}_\alpha]$$

**In plain Python** (for fixed weights):

```python
losses = -(returns @ w)
VaR_95 = np.percentile(losses, 95)
CVaR_95 = losses[losses >= VaR_95].mean()   # average of the worst 5%
```

**CVaR is always ≥ VaR.** It's a stricter, more informative measure of tail risk.

### VaR vs CVaR — Quick Comparison

| | VaR | CVaR |
|---|---|---|
| Question answered | What's the loss threshold? | What's the avg loss in the tail? |
| Captures tail severity? | No | Yes |
| Convex / LP-friendly? | **No** | **Yes** |
| Better for optimization? | No | Yes |

---

## 5. The Core Problem with Optimizing CVaR Directly

The Python formulas above work fine when **w is fixed**. But in our optimizer, **w is the decision variable** — we're solving for it.

`np.percentile()` is not differentiable. You can't optimize through a percentile. The solver has no way to reason about it.

This is where the **Rockafellar-Uryasev (2000) reformulation** comes in. It rewrites CVaR in a form that is **linear in the decision variables**, so it plugs directly into our existing LP.

---

## 6. The Rockafellar-Uryasev Reformulation

### Variables and Notation

| Symbol | What it is |
|---|---|
| $T$ | Number of historical scenarios (trading days) |
| $N$ | Number of bonds |
| $\mathbf{w}$ | Portfolio weights — our main decision variable (N-vector) |
| $\mathbf{r}_s$ | Vector of bond returns on day $s$ (N-vector) |
| $L_s(\mathbf{w})$ | Portfolio loss on scenario $s$ |
| $\alpha$ | Confidence level, e.g. 0.95 |
| $\zeta$ | A new decision variable — the VaR threshold (scalar) |
| $u_s$ | A new decision variable per scenario — the "overflow" (T-vector) |
| $\kappa$ | User-defined CVaR budget (the one knob you set) |

The portfolio loss on scenario $s$ is:

$$L_s(\mathbf{w}) = -\mathbf{r}_s^\top \mathbf{w}$$

(Loss = negative return. If the portfolio returned +2%, loss = −2%. If it dropped 3%, loss = +3%.)

---

### The Key Idea: Overflow Variables

For each scenario $s$, define $u_s$ as **how much scenario $s$ sticks out above the VaR threshold $\zeta$**:

$$u_s = \max\big(L_s(\mathbf{w}) - \zeta, \; 0\big)$$

Visually:

```
Loss axis
    │
    │                              ← u_s: how far above ζ
    │                    ●  ●  ●
────┼──────────────────────────────  ← ζ  (VaR threshold)
    │     ● ● ● ● ● ● ●●●●
    │
    └──────────────────────────────▶ scenarios (sorted by loss)
```

Scenarios below ζ have $u_s = 0$ — they don't contribute to the tail average. Only the bad ones (above ζ) have $u_s > 0$.

---

### The CVaR Formula

The Rockafellar-Uryasev result says:

$$\text{CVaR}_\alpha(\mathbf{w}) = \min_{\zeta} \left[ \zeta + \frac{1}{(1-\alpha) \cdot T} \sum_{s=1}^{T} u_s \right]$$

**Breaking this down piece by piece:**

- $\zeta$ — the baseline (the VaR level). The solver finds the optimal value automatically.
- $\sum u_s / T$ — the average overflow across **all** scenarios (most are zero)
- Dividing by $(1 - \alpha)$ — re-scales to the tail. If $\alpha = 0.95$, only 5% of scenarios have $u_s > 0$, so this division ensures we're averaging over that 5% specifically
- At the optimal $\zeta$, **the whole expression equals CVaR**

The key breakthrough: the $\max(\cdot, 0)$ in the definition of $u_s$ can be replaced by two **linear inequality constraints**:

$$u_s \geq L_s(\mathbf{w}) - \zeta \quad \forall s$$

$$u_s \geq 0 \quad \forall s$$

No max(), no percentile(), no sorting. Just linear inequalities. This is why CVaR is LP-friendly and VaR is not.

---

## 7. Adding CVaR as a Constraint to Our Optimizer

### Our Current Optimizer (Simplified)

$$\max_{\mathbf{w}} \quad \underbrace{\mathbf{y}^\top \mathbf{w}}_{\text{yield}} - \underbrace{r_{\text{FABN}}}_{\text{FABN coupon}} - \underbrace{\text{TC}(\mathbf{w}, \mathbf{w}_{\text{prev}})}_{\text{transaction costs}}$$

Subject to:

$$\mathbf{d}^\top \mathbf{w} = D_{\text{liab}} \quad \text{(duration matching)}$$

$$\text{C1}(\mathbf{w}) \leq \text{C1}_{\text{max}}, \quad \text{C3}(\mathbf{w}) \leq \text{C3}_{\text{max}} \quad \text{(RBC constraints)}$$

$$\mathbf{1}^\top \mathbf{w} = 1, \quad \mathbf{w} \geq 0 \quad \text{(standard portfolio constraints)}$$

**Decision variables:** $\mathbf{w}$ (N weights)

---

### With CVaR Added

We add **two new sets of decision variables** and **three new constraints**.

**New decision variables:**

$$\zeta \in \mathbb{R} \quad \text{(the VaR threshold — solver finds this automatically)}$$

$$\mathbf{u} \in \mathbb{R}^T_{\geq 0} \quad \text{(one overflow variable per historical day — solver finds these too)}$$

**Three new constraints:**

$$\text{(1)} \quad u_s \geq -\mathbf{r}_s^\top \mathbf{w} - \zeta \quad \forall \, s = 1, \ldots, T \quad \text{(overflow definition)}$$

$$\text{(2)} \quad u_s \geq 0 \quad \forall \, s \quad \text{(overflows are non-negative)}$$

$$\text{(3)} \quad \zeta + \frac{1}{(1-\alpha) \cdot T} \sum_{s=1}^{T} u_s \leq \kappa \quad \text{(CVaR cap)}$$

Everything else stays exactly the same.

---

### What Each Constraint Is Doing

| Constraint | Role |
|---|---|
| (1) + (2) | **Define** $u_s$ — bookkeeping. Links $u_s$, $\mathbf{w}$, and $\zeta$ together linearly. |
| (3) | **Enforces** the risk limit. This is the actual CVaR constraint. |

**Important:** Constraints (1) and (2) alone do nothing to limit risk. Without constraint (3), the solver would set all $u_s = 0$ and $\zeta = -\infty$ and ignore them entirely. Constraint (3) is what gives them purpose.

---

### The New Decision Variable Count

| Variable | Count | Defined by |
|---|---|---|
| $\mathbf{w}$ | $N = 104$ | You (main portfolio weights) |
| $\zeta$ | $1$ | Solver |
| $\mathbf{u}$ | $T \approx 500$ | Solver |

**Total:** ~605 decision variables. Modern LP solvers handle this trivially.

---

## 8. How to Choose $\kappa$

$\kappa$ is the **only parameter you introduce**. Three practical approaches:

**Option 1 — Benchmark against static baseline.**
Run the static portfolio, compute its CVaR empirically, set $\kappa$ slightly below that. Now the dynamic portfolio is *required* to have better tail risk than the static one.

**Option 2 — Use a meaningful loss threshold.**
"We cannot afford to lose more than 2% on average in bad scenarios." Set $\kappa = 0.02$.

**Option 3 — Sweep $\kappa$ and plot the frontier.**
Run the optimizer for multiple values of $\kappa$ from tight to loose. Plot CVaR vs. spread. This gives a **risk-return frontier** — analogous to the efficient frontier in mean-variance optimization — and lets you show the tradeoff clearly.

---

## 9. Why This Fits Our Project Narrative

Our problem statement says:
> *"dynamic reoptimization exceeds baseline industry standard performance"*

Right now "performance" means spread. Adding CVaR lets us make a much stronger claim:

> **"Our dynamic strategy earns higher spread AND maintains lower tail risk than the static baseline — particularly on volatility trigger dates."**

Our trigger dates are precisely the moments when tail risk spikes. A CVaR constraint that activates on those dates forces the optimizer to rotate away from risky positions during stress periods — which is exactly the "dynamic value over static" story at the core of our situational analysis.

---

## 10. Gurobipy — How the Code Works

Below is the full example script with every line explained.

```python
import gurobipy as gp
from gurobipy import GRB
import numpy as np
```

`gurobipy` is the Python interface to the Gurobi solver. `GRB` gives us constants like `GRB.MAXIMIZE` and `GRB.INFINITY`.

---

```python
returns = np.array([
    [ 0.04,  0.02,  0.01],   # scenario 1
    [-0.03,  0.01,  0.02],   # scenario 2
    [ 0.01, -0.04,  0.03],   # scenario 3
    [-0.02,  0.03, -0.05],   # scenario 4
])

T, N = returns.shape   # T=4 scenarios, N=3 assets
alpha = 0.75           # confidence level
kappa = 0.03           # CVaR budget: tolerate at most 3% avg tail loss
```

`returns` is a $T \times N$ matrix — each row is one historical day, each column is one asset. Same structure as our Bloomberg data.

---

```python
m = gp.Model("cvar_example")
m.setParam("OutputFlag", 0)
```

Creates a Gurobi model object. `OutputFlag=0` suppresses the solver's verbose logging. Remove this line if you want to see what the solver is doing.

---

```python
w    = m.addVars(N, lb=0.0, name="w")
zeta = m.addVar(lb=-GRB.INFINITY, name="zeta")
u    = m.addVars(T, lb=0.0, name="u")
```

This is where all decision variables are declared.

- `w`: N variables, lower bound 0 (long-only). `m.addVars(N)` creates `w[0], w[1], ..., w[N-1]`.
- `zeta`: 1 scalar. **Critical:** `lb=-GRB.INFINITY` because ζ can be negative. Gurobi's default lower bound is 0, which would silently break the CVaR math.
- `u`: T variables, lower bound 0. This enforces constraint (2) implicitly via the variable bound — more efficient than a separate constraint.

---

```python
avg_return = gp.quicksum(
    returns[s, i] * w[i]
    for s in range(T)
    for i in range(N)
) / T

m.setObjective(avg_return, GRB.MAXIMIZE)
```

Builds the objective: average portfolio return across all scenarios. `gp.quicksum` is Gurobi's efficient version of Python's `sum()` — use it whenever summing over decision variables. `GRB.MAXIMIZE` tells the solver to maximize.

---

```python
m.addConstr(gp.quicksum(w[i] for i in range(N)) == 1, name="budget")
```

The "fully invested" constraint: weights must sum to 1.

---

```python
for s in range(T):
    portfolio_loss_s = -gp.quicksum(returns[s, i] * w[i] for i in range(N))
    m.addConstr(u[s] >= portfolio_loss_s - zeta, name=f"overflow_{s}")
```

Constraint (1): the overflow definition. For each scenario $s$, `portfolio_loss_s` computes $L_s(\mathbf{w}) = -\mathbf{r}_s^\top \mathbf{w}$ as a Gurobi **linear expression** (not a number — because `w` is a decision variable). Then we add the constraint $u_s \geq L_s(\mathbf{w}) - \zeta$.

This loop adds T separate constraints, one per scenario. Combined with `lb=0.0` on `u`, this fully defines constraints (1) and (2).

---

```python
m.addConstr(
    zeta + (1.0 / ((1 - alpha) * T)) * gp.quicksum(u[s] for s in range(T)) <= kappa,
    name="cvar"
)
```

Constraint (3): the actual CVaR cap. This is the one constraint that limits tail risk. Translates directly from the formula:

$$\zeta + \frac{1}{(1-\alpha) \cdot T} \sum_{s=1}^{T} u_s \leq \kappa$$

---

```python
m.optimize()
```

Hands the problem to the Gurobi solver. It finds the values of all decision variables ($\mathbf{w}$, $\zeta$, $\mathbf{u}$) that maximize the objective while satisfying all constraints.

---

```python
print("Optimal weights:")
for i in range(N):
    print(f"  w[{i+1}] = {w[i].X:.4f}")

print(f"\nzeta (VaR level) = {zeta.X:.4f}")
print(f"u (overflows)    = {[round(u[s].X, 4) for s in range(T)]}")
print(f"Avg return       = {m.ObjVal:.4f}")
```

After solving, `.X` retrieves the optimal value of each decision variable. `m.ObjVal` is the optimal objective value. Notice that `zeta.X` gives you the portfolio's VaR at level α as a free byproduct — you never had to ask for it explicitly.

---

## 11. Summary

| Concept | One-line description |
|---|---|
| VaR | The loss threshold you exceed only $(1-\alpha)$% of the time |
| CVaR | The average loss on the days you exceed VaR |
| $\zeta$ | Auxiliary decision variable — becomes VaR at the optimum |
| $u_s$ | Auxiliary decision variable — measures how bad scenario $s$ is |
| $\kappa$ | The only user-set parameter — your CVaR tolerance |
| Constraints (1)+(2) | Define what $u_s$ means — bookkeeping |
| Constraint (3) | The actual risk limit — enforces CVaR $\leq \kappa$ |

**The bottom line:** We add 1 scalar + T overflow variables and 3 constraint groups to our existing LP. The problem stays linear, the solver handles it natively, and we gain a principled, regulatorily-respected measure of tail risk control.