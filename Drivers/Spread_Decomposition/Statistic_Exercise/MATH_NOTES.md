# HW3: Mathematical Foundation

## 1. Logit & Logistic Regression

**Logit (log-odds):**
$$\text{logit}(p) = \log\left(\frac{p}{1-p}\right)$$

**Logistic regression (inverse logit):**
$$P(Y=1|X) = \frac{e^{\eta}}{1+e^{\eta}} = \frac{1}{1+e^{-\eta}}$$

where $\eta = \beta_0 + \beta_1 X_1 + \beta_2 X_2 + \cdots$

---

## 2. Maximum Likelihood Estimation

**Log-likelihood for binary outcome:**
$$\ell(\beta) = \sum_{i=1}^{n} \left[ y_i \log(p_i) + (1-y_i)\log(1-p_i) \right]$$

where $p_i = P(Y_i=1|X_i)$ under the model.

---

## 3. Deviance Test (LRT)

**Test statistic:**
$$D = 2(\ell_{\text{full}} - \ell_{\text{reduced}}) \sim \chi^2_{\Delta df}$$

Under $H_0$: reduced model is sufficient.

**p-value:** $P(\chi^2_{\Delta df} > D)$

---

## 4. Pseudo-$R^2$ Metrics

| Metric | Formula |
|--------|---------|
| **McFadden** | $R^2_M = 1 - \frac{\ell_{\text{model}}}{\ell_{\text{null}}}$ |
| **Cox-Snell** | $R^2_{CS} = 1 - \exp\left(\frac{2}{n}(\ell_{\text{null}} - \ell_{\text{model}})\right)$ |
| **Nagelkerke** | $R^2_N = \frac{R^2_{CS}}{1 - \exp(2\ell_{\text{null}}/n)}$ |
| **Tjur** | $D = \overline{p}_1 - \overline{p}_0$ (mean predicted prob: events vs. non-events) |

---

## 5. Piecewise Logistic Regression

**Three-tier model** (thresholds $T_1, T_2$):

Define tier indicators:
- $A = \mathbb{1}(\text{Age} \leq T_1)$
- $B = \mathbb{1}(T_1 < \text{Age} \leq T_2)$
- $C$ = baseline (no indicator)

**Linear predictor:**
$$\eta = \beta_0 + \beta_1 \text{Age} + \beta_2 \text{Age}^2 + \beta_3 A + \beta_4 B + \beta_5 (\text{Age} \cdot A) + \beta_6 (\text{Age} \cdot B) + \beta_7 (\text{Age}^2 \cdot A) + \beta_8 (\text{Age}^2 \cdot B)$$

**Optimization:** Choose $(T_1, T_2)$ to maximize $\sum_{j=1}^{3} \ell_j$, the total log-likelihood across all three tiers.

---

## 6. Model Comparison

**Strategy:** Fit three separate models within tiers, or one unified model with tier indicators + interactions.

Both approaches yield equivalent log-likelihoods:
$$\ell_{\text{unified}} = \ell_{\text{tier 1}} + \ell_{\text{tier 2}} + \ell_{\text{tier 3}}$$
