#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Nov  9 17:34:51 2025

@author: eloibernier
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct 22 16:38:31 2025

@author: eloibernier
"""

#############################################################################################################
################################################ I M P O R T  ##############################################
#############################################################################################################

import matplotlib.pyplot as plt
import numpy
import pandas
import sys

import time

from itertools import chain, combinations
from matplotlib.ticker import (AutoMinorLocator, MultipleLocator, FormatStrFormatter)
from scipy.stats import norm, f, shapiro, anderson
from scipy.special import comb
from matplotlib.ticker import (AutoLocator, MultipleLocator, FormatStrFormatter, StrMethodFormatter)
from scipy.stats import poisson, chi2

sys.path.append('/Users/eloibernier/Documents/MS-ADS/2025FallSemester/Statistics/HW/HW2')
import Regression


# Set some options for printing all the columns
numpy.set_printoptions(precision = 10, threshold = sys.maxsize)
numpy.set_printoptions(linewidth = numpy.inf)

pandas.set_option('display.max_columns', None)
pandas.set_option('display.expand_frame_repr', False)
pandas.set_option('max_colwidth', None)

pandas.options.display.float_format = '{:,.10f}'.format

#############################################################################################################
############################################# I M P O R T   C S V  ##########################################
#############################################################################################################

# Read the Claim-history
DrivingHistory = pandas.read_excel('/Users/eloibernier/Documents/MS-ADS/2025FallSemester/Statistics/HW/HW3/claim_history.xlsx')

#############################################################################################################
############################################# Q E S T I O N   1  ##########################################
#############################################################################################################

number_of_driving_hazard = DrivingHistory[DrivingHistory['MVR_PTS']>5]['MVR_PTS'].count()
total_observation = DrivingHistory['ID'].count()

percentage_insurance_hazard = (number_of_driving_hazard/total_observation)*100
print(percentage_insurance_hazard)

##### B.

def logit(p):
    return numpy.log(p / (1 - p))

print(logit(0.3))

def DrivingHazard(k):
    if k > 5:
        return 1
    else:
        return 0

DrivingHistory['Driving_Havard'] = DrivingHistory['MVR_PTS'].apply(DrivingHazard)

Grouped_by_age = DrivingHistory.groupby('AGE').agg(
    Population_by_age = ('AGE', 'count'),
    Number_of_dricing_hazard = ('Driving_Havard', 'sum')
    )

Grouped_by_age['probability_driving_hazard'] = Grouped_by_age['Number_of_dricing_hazard']/Grouped_by_age['Population_by_age']

eps = 1e-9
Grouped_by_age['logit_by_age'] = Grouped_by_age['probability_driving_hazard'].clip(eps, 1-eps).apply(logit)

#Grouped_by_age['logit_by_age'] = Grouped_by_age['probability_driving_hazard'].apply(logit)

#### Histogram

#Studentized Residuals: vertical histogram (bin width 0.05) + horizontal boxplot 
Grouped_by_age['AGE_index'] = Grouped_by_age.index

data = Grouped_by_age[['AGE_index', 'logit_by_age']].copy()

# ✔ Clip logits instead of removing points
clip_min, clip_max = -10, 10
data['logit_by_age'] = data['logit_by_age'].clip(clip_min, clip_max)


# Overall logit (reference line)
total_hazard = DrivingHistory['Driving_Havard'].sum()
total_obs = DrivingHistory.shape[0]
overall_prob = total_hazard / total_obs
overall_logit = logit(overall_prob)

# 4. Histogram bin setup (bin width 1)
bin_width = 1
age_min = int(DrivingHistory['AGE'].min())
age_max = int(DrivingHistory['AGE'].max())
bins = numpy.arange(age_min - 0.5, age_max + 1.5, bin_width)

# 5. Create figure with two subplots
fig, (ax_top, ax_bottom) = plt.subplots(
    2, 1, figsize=(10, 7),
    gridspec_kw={'height_ratios': [3, 1]},
    dpi=200,
    sharex=True
)

# ===== Top: line plot of logit vs age =====
ax_top.plot(
    data['AGE_index'],
    data['logit_by_age'],
    marker='o',
    linestyle='-'
)

# Horizontal reference line at overall logit
ax_top.axhline(overall_logit, linestyle='--', linewidth=1)

# Optional zero-logit line if you want
# ax_top.axhline(0.0, linestyle=':', linewidth=1)


ax_top.set_ylabel('Logit of driving hazard')
ax_top.set_title('Logit of driving hazard versus age of policyholder')

# Sensible y-ticks based on range of logits
y_min = numpy.floor(data['logit_by_age'].min())
y_max = numpy.ceil(data['logit_by_age'].max())
ax_top.set_yticks(numpy.arange(y_min, y_max + 1, 1))

# ===== Bottom: histogram of age (bin width = 1) =====
ax_bottom.hist(DrivingHistory['AGE'], bins=bins)
ax_bottom.set_xlabel('Age of policyholder (years)')
ax_bottom.set_ylabel('Count of policyholders')

# Sensible x-ticks, e.g. every 5 years
ax_bottom.set_xticks(numpy.arange(age_min, age_max + 1, 5))

plt.tight_layout()
plt.show()


#############################################################################################################
############################################# Q E S T I O N   2  ##########################################
#############################################################################################################


import LogisticRegression

# Set some options for printing all the columns
numpy.set_printoptions(precision = 10, threshold = sys.maxsize)
numpy.set_printoptions(linewidth = numpy.inf)

pandas.set_option('display.max_columns', None)
pandas.set_option('display.expand_frame_repr', False)
pandas.set_option('max_colwidth', None)

pandas.options.display.float_format = '{:,.7f}'.format


## create a train table data

DrivingHistory['AGE_Squarred'] = DrivingHistory['AGE'] ** 2

age = ['AGE']
age_squarred = ['AGE_Squarred']
target = ['Driving_Havard']
columns_for_training = ['AGE', 'AGE_Squarred', 'Driving_Havard']

# Train logistic regression
train_data_DrivingHistory = DrivingHistory[columns_for_training]



from scipy.stats import chi2
# (You already read the Excel and built Driving_Havard above)

# 1) Create AGE^2
DrivingHistory['AGE_Squarred'] = DrivingHistory['AGE'] ** 2

# 2) Create a Yes/No target for the LogisticRegression module
DrivingHistory['DrivingHazard'] = DrivingHistory['Driving_Havard'].map({1: 'Yes', 0: 'No'})

# 3) Define predictors and target
cat_pred = []                         # no categorical predictors
int_pred = ['AGE', 'AGE_Squarred']    # both numeric predictors
target = 'DrivingHazard'
event_category = 'Yes'

# 4) Build train_data and drop missing values
columns_for_training = int_pred + [target]
train_data_DrivingHistory = (
    DrivingHistory[columns_for_training]
    .dropna()
    .reset_index(drop=True)
)

# Just to be safe, print a quick head:
print(train_data_DrivingHistory.head())


import LogisticRegression
from scipy.stats import chi2

# Intercept-only model
model_spec = []
result0 = LogisticRegression.BinaryLogisticRegression(
    train_data_DrivingHistory,
    cat_pred,
    int_pred,
    target,
    event_category,
    model_spec
)
param0        = result0[0]
covb0         = result0[1]
corb0         = result0[2]
model_llk0    = result0[3]
nonAlias0     = result0[4]
iter_table0   = result0[5]
labelCats0    = result0[6]
predprob0     = result0[7]
assoc0        = result0[8]   # [McFadden, Cox-Snell, Nagelkerke, Tjur]
model_df0     = len(nonAlias0)

# Model with AGE
model_spec = ['AGE']
result1 = LogisticRegression.BinaryLogisticRegression(
    train_data_DrivingHistory,
    cat_pred,
    int_pred,
    target,
    event_category,
    model_spec
)
param1        = result1[0]
covb1         = result1[1]
corb1         = result1[2]
model_llk1    = result1[3]
nonAlias1     = result1[4]
iter_table1   = result1[5]
labelCats1    = result1[6]
predprob1     = result1[7]
assoc1        = result1[8]
model_df1     = len(nonAlias1)

# Deviance test: add AGE (Model 0 -> Model 1)
deviance_chisq1 = 2.0 * (model_llk1 - model_llk0)
deviance_df1    = model_df1 - model_df0
deviance_sig1   = chi2.sf(deviance_chisq1, deviance_df1)

# Model with AGE and AGE^2
model_spec = ['AGE', 'AGE_Squarred']
result2 = LogisticRegression.BinaryLogisticRegression(
    train_data_DrivingHistory,
    cat_pred,
    int_pred,
    target,
    event_category,
    model_spec
)
param2        = result2[0]
covb2         = result2[1]
corb2         = result2[2]
model_llk2    = result2[3]
nonAlias2     = result2[4]
iter_table2   = result2[5]
labelCats2    = result2[6]
predprob2     = result2[7]
assoc2        = result2[8]
model_df2     = len(nonAlias2)

# Deviance test: add AGE^2 (Model 1 -> Model 2)
deviance_chisq2 = 2.0 * (model_llk2 - model_llk1)
deviance_df2    = model_df2 - model_df1
deviance_sig2   = chi2.sf(deviance_chisq2, deviance_df2)


## 2a 

deviance_table = pandas.DataFrame({
    'Term Added':          ['Intercept', 'AGE', 'AGE_Squarred'],
    'Model DF':            [model_df0, model_df1, model_df2],
    'Log-Likelihood':      [model_llk0, model_llk1, model_llk2],
    'Deviance Chi-Square': [0, deviance_chisq1, deviance_chisq2],
    'Deviance DF':         [0, deviance_df1, deviance_df2],
    'Deviance p-value':    [0, deviance_sig1, deviance_sig2]
})

print(deviance_table)


# assoc2 is the list: [McFadden, Cox-Snell, Nagelkerke, Tjur]
mcfadden   = assoc2[0]
cox_snell  = assoc2[1]
nagelkerke = assoc2[2]
tjur       = assoc2[3]

## 2b

gof_table = pandas.DataFrame({
    'Statistic': [
        'Log-likelihood (final model)',
        'McFadden R-squared',
        'Cox-Snell R-squared',
        'Nagelkerke R-squared',
        "Tjur Coefficient of Discrimination"
    ],
    'Value': [
        model_llk2,
        mcfadden,
        cox_snell,
        nagelkerke,
        tjur
    ]
})

print(gof_table)



#############################################################################################################
############################################# Q E S T I O N   3  ##########################################
#############################################################################################################

best_llk = -numpy.inf
best_T1 = None
best_T2 = None

for T1 in range(20, 36):      # 20 → 35 inclusive
    for T2 in range(50, 71):  # 50 → 70 inclusive
        if T1 >= T2:
            continue

        # Split into three subsets
        tier0 = DrivingHistory.loc[DrivingHistory['AGE'] <= T1]
        tier1 = DrivingHistory.loc[(DrivingHistory['AGE'] > T1) & (DrivingHistory['AGE'] <= T2)]
        tier2 = DrivingHistory.loc[DrivingHistory['AGE'] > T2]

        # Initialize sum of LLKs
        llk_sum = 0

        # Loop through the 3 tiers
        for df in [tier0, tier1, tier2]:
            if df.shape[0] < 1:
                continue  # skip too-small samples
            result = LogisticRegression.BinaryLogisticRegression(
                df[['AGE', 'AGE_Squarred', 'DrivingHazard']],
                [], ['AGE', 'AGE_Squarred'], 'DrivingHazard', 'Yes',
                ['AGE', 'AGE_Squarred']
            )
            llk_sum += result[3]  # result[3] is the model log-likelihood

        # Check if this (T1, T2) is the best so far
        if llk_sum > best_llk:
            best_llk = llk_sum
            best_T1, best_T2 = T1, T2

print("Best thresholds:", best_T1, best_T2)
print("Highest total log-likelihood:", best_llk)

import pandas as pd
import numpy as np
from LogisticRegression import BinaryLogisticRegression


# Prepare a results list
results = []

for T1 in range(20, 36):      # 20 → 35 inclusive
    for T2 in range(50, 71):  # 50 → 70 inclusive
        if T1 >= T2:
            continue

        llk_sum = 0
        valid_tiers = 0

        # Split the data into three tiers
        for tier_df in [
            DrivingHistory.loc[DrivingHistory['AGE'] <= T1],
            DrivingHistory.loc[(DrivingHistory['AGE'] > T1) & (DrivingHistory['AGE'] <= T2)],
            DrivingHistory.loc[DrivingHistory['AGE'] > T2]
        ]:
            if tier_df.shape[0] < 10:
                continue  # skip very small tiers

            try:
                result = BinaryLogisticRegression(
                    tier_df[['AGE', 'AGE_Squarred', 'DrivingHazard']],
                    [], ['AGE', 'AGE_Squarred'],
                    'DrivingHazard', 'Yes',
                    ['AGE', 'AGE_Squarred']
                )
                llk_sum += result[3]   # log-likelihood
                valid_tiers += 1
            except Exception as e:
                print(f"Error at thresholds ({T1}, {T2}): {e}")
                continue

        # Store result only if all 3 tiers were valid
        if valid_tiers == 3:
            results.append({'T1': T1, 'T2': T2, 'Total_LogLikelihood': llk_sum})

# Convert results into DataFrame
llk_df = pd.DataFrame(results)

# Sort by total log-likelihood (descending)
llk_df = llk_df.sort_values(by='Total_LogLikelihood', ascending=False).reset_index(drop=True)

# Display top combinations
print(llk_df.head())

# Save to CSV if needed
llk_df.to_csv('/Users/eloibernier/Documents/MS-ADS/2025FallSemester/Statistics/HW/HW3/threshold_loglikelihoods.csv', index=False)


########### 3 B)


# Re-fit the three tier models using best_T1 and best_T2
tiers = [
    DrivingHistory.loc[DrivingHistory['AGE'] <= best_T1],
    DrivingHistory.loc[(DrivingHistory['AGE'] > best_T1) & (DrivingHistory['AGE'] <= best_T2)],
    DrivingHistory.loc[DrivingHistory['AGE'] > best_T2]
]

total_llk = 0
assoc_values = np.zeros(4)  # [McFadden, Cox-Snell, Nagelkerke, Tjur]
for df in tiers:
    result = BinaryLogisticRegression(
        df[['AGE', 'AGE_Squarred', 'DrivingHazard']],
        [], ['AGE', 'AGE_Squarred'],
        'DrivingHazard', 'Yes',
        ['AGE', 'AGE_Squarred']
    )
    total_llk += result[3]      # add log-likelihood
    assoc_values += np.array(result[8])  # sum each pseudo-R² across tiers

# Average the pseudo-R²s (since they’re scaled measures, not additive)
assoc_values /= 3
mcfadden, cox_snell, nagelkerke, tjur = assoc_values

# Build the goodness-of-fit table
gof_table_3b = pd.DataFrame({
    'Statistic': [
        'Log-likelihood (final piecewise model)',
        'McFadden R-squared',
        'Cox-Snell R-squared',
        'Nagelkerke R-squared',
        "Tjur Coefficient of Discrimination"
    ],
    'Value': [
        total_llk,
        mcfadden,
        cox_snell,
        nagelkerke,
        tjur
    ]
})

print(gof_table_3b)




#########
# Extract optimal thresholds from the grid search results
best_row = llk_df.iloc[0]  # top result (already sorted descending by log-likelihood)
best_T1 = int(best_row['T1'])
best_T2 = int(best_row['T2'])

# Tier dummies
DrivingHistory['Tier_A'] = (DrivingHistory['AGE'] <= best_T1).astype(int)
DrivingHistory['Tier_B'] = ((DrivingHistory['AGE'] > best_T1) &
                            (DrivingHistory['AGE'] <= best_T2)).astype(int)
# Tier C = baseline (no dummy needed)

# AGE squared
DrivingHistory['AGE_Squarred'] = DrivingHistory['AGE'] ** 2

# Interaction terms
DrivingHistory['AGE_Tier_A']  = DrivingHistory['AGE'] * DrivingHistory['Tier_A']
DrivingHistory['AGE_Tier_B']  = DrivingHistory['AGE'] * DrivingHistory['Tier_B']

DrivingHistory['AGE2_Tier_A'] = DrivingHistory['AGE_Squarred'] * DrivingHistory['Tier_A']
DrivingHistory['AGE2_Tier_B'] = DrivingHistory['AGE_Squarred'] * DrivingHistory['Tier_B']

# Build unified predictors list
unified_predictors = [
    'AGE', 'AGE_Squarred',
    'Tier_A', 'Tier_B',
    'AGE_Tier_A', 'AGE_Tier_B',
    'AGE2_Tier_A', 'AGE2_Tier_B'
]

# Training data
train_unified = DrivingHistory[unified_predictors + ['DrivingHazard']].dropna()

# SINGLE piecewise logistic model
result_unified = BinaryLogisticRegression(
    train_unified,
    [],                   # cat_pred
    unified_predictors,   # int_pred
    'DrivingHazard',      # target
    'Yes',                # event_category
    unified_predictors    # model_spec
)

param_unified = result_unified[0]     # coefficient table
llk_unified   = result_unified[3]     # log-likelihood
assoc_unified = result_unified[8]     # [McFadden, Cox–Snell, Nagelkerke, Tjur]

print(param_unified)
print("Unified log-likelihood:", llk_unified)
print("Unified pseudo-R²:", assoc_unified)



#############################################################################################################
############################################# Q U E S T I O N   4  ##########################################
#############################################################################################################

# 1) Observed proportions by age (scatter)
Grouped_by_age = DrivingHistory.groupby('AGE').agg(
    Population_by_age=('AGE', 'count'),
    Number_of_dricing_hazard=('Driving_Havard', 'sum')
)
Grouped_by_age['probability_driving_hazard'] = (
    Grouped_by_age['Number_of_dricing_hazard'] / Grouped_by_age['Population_by_age']
)

# x-axis ages and observed proportions
age_values = Grouped_by_age.index.to_numpy()
obs_props  = Grouped_by_age['probability_driving_hazard'].to_numpy()

# 2) Predicted probabilities from Question 2 model (single quadratic model)
#    param2 = [β0, β1, β2] from the model with AGE and AGE_Squarred
# Replace 'AGE_Squared' with the exact name you see in param2.index
beta0_q2 = param2.loc['Intercept', 'Estimate']
beta1_q2 = param2.loc['AGE', 'Estimate']
beta2_q2 = param2.loc['AGE_Squarred', 'Estimate']  # or 'AGE_Squarred' if that's the index name

print(beta0_q2, beta1_q2, beta2_q2)

age_grid = age_values  # predict at each observed age
age_sq_grid = age_grid ** 2

logit_q2 = beta0_q2 + beta1_q2 * age_grid + beta2_q2 * age_sq_grid
pred_q2  = numpy.exp(logit_q2) / (1 + numpy.exp(logit_q2))


# 3) Predicted probabilities from Question 3 unified piecewise model

best_T1 = 31
best_T2 = 56

# Build a small design matrix for each age in age_grid
age_df = pandas.DataFrame({'AGE': age_grid})

age_df['AGE_Squarred'] = age_df['AGE'] ** 2
age_df['Tier_A'] = (age_df['AGE'] <= best_T1).astype(int)
age_df['Tier_B'] = ((age_df['AGE'] > best_T1) & (age_df['AGE'] <= best_T2)).astype(int)
# Tier C is baseline (no dummy)

age_df['AGE_Tier_A']  = age_df['AGE'] * age_df['Tier_A']
age_df['AGE_Tier_B']  = age_df['AGE'] * age_df['Tier_B']
age_df['AGE2_Tier_A'] = age_df['AGE_Squarred'] * age_df['Tier_A']
age_df['AGE2_Tier_B'] = age_df['AGE_Squarred'] * age_df['Tier_B']

# Coefficients from unified model
beta0_u = param_unified.loc['Intercept', 'Estimate']
beta_age        = param_unified.loc['AGE', 'Estimate']
beta_age2       = param_unified.loc['AGE_Squarred', 'Estimate']
beta_tier_a     = param_unified.loc['Tier_A', 'Estimate']
beta_tier_b     = param_unified.loc['Tier_B', 'Estimate']
beta_age_tier_a = param_unified.loc['AGE_Tier_A', 'Estimate']
beta_age_tier_b = param_unified.loc['AGE_Tier_B', 'Estimate']
beta_age2_tier_a = param_unified.loc['AGE2_Tier_A', 'Estimate']
beta_age2_tier_b = param_unified.loc['AGE2_Tier_B', 'Estimate']

# Logit from unified model for each age
logit_q3 = (
    beta0_u
    + beta_age        * age_df['AGE']
    + beta_age2       * age_df['AGE_Squarred']
    + beta_tier_a     * age_df['Tier_A']
    + beta_tier_b     * age_df['Tier_B']
    + beta_age_tier_a * age_df['AGE_Tier_A']
    + beta_age_tier_b * age_df['AGE_Tier_B']
    + beta_age2_tier_a * age_df['AGE2_Tier_A']
    + beta_age2_tier_b * age_df['AGE2_Tier_B']
)

pred_q3 = numpy.exp(logit_q3) / (1 + numpy.exp(logit_q3))

# (Optional sanity check: shapes must match)
print(age_grid.shape, pred_q3.shape)

# 4) Make the overlay plot
plt.figure(figsize=(10, 6), dpi=200)

# (1) Observed proportions: scatter
plt.scatter(
    age_values, obs_props,
    marker='o',
    edgecolor='black',
    alpha=0.8,
    label='Observed proportion by age'
)

# (2) Question 2 model: line + markers
plt.plot(
    age_grid, pred_q2,
    marker='s',
    linestyle='-',
    label='Q2 model: quadratic logistic'
)

# (3) Question 3 model: piecewise line + markers
plt.plot(
    age_grid, pred_q3,
    marker='^',
    linestyle='--',
    label='Q3 model: Multi-age tiers logistic'
)

plt.xlabel('Age of policyholder (years)')
plt.ylabel('Probability of driving hazard')
plt.title('Observed and Predicted Probabilities of Driving Hazard by Age')

plt.ylim(0, 1)  # probabilities
plt.xlim(age_values.min() - 1, age_values.max() + 1)

plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.show()













