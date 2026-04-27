#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct 22 16:38:31 2025

@author: eloibernier
"""
#############################################################################################################
########################################### D I C T I O N N A R Y ###########################################
#############################################################################################################


#Train_Data into LakeView
#replace TRate_name by TLakeView_name
#n_TRate_name by n_TLakeView_name

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

# Read the Lakeview
LakeView = pandas.read_excel('/Users/eloibernier/Documents/MS-ADS/2025FallSemester/Statistics/HW/HW2/LakeViewTownshipHomeSale.xlsx')




#############################################################################################################
#################################     F O R W A R D   S E L E C T I O N    ##################################
#############################################################################################################

target_name = 'Sale Price'
y_train = numpy.log(LakeView[target_name])


# Forward Selection



# needed variable:
TLakeView_name = LakeView.columns.to_list()    
#replace TRate_name
int_name = ['Bedrooms','Full Baths','Half Baths','Fireplaces','Garage Size',
                   'Building Square Feet','Land Square Feet','Tract Median Income']
cat_name = ['Attic Type','Basement Finish','Central Air Conditioning','Central Heating',
                    'Wall Material',"O'Hare Noise Indicator",'Road Proximity', 'Roof Material']

TLakeView_name =  int_name + cat_name



n_TLakeView_name = len(TLakeView_name)

train_data = LakeView[TLakeView_name].dropna().reset_index(drop = True)

n_sample = train_data.shape[0]


for category in cat_name:
    mode_cat = LakeView[category].mode()[0]
    ordered_mode = [mode_cat] + [c for c in train_data[category].unique() if c != mode_cat]
    train_data[category] = pandas.Categorical(train_data[category], categories=ordered_mode, ordered = True)



## create a dictionnary of dummy variable:
    
    
dummies_dictionnary = {
    category: pandas.get_dummies(train_data[[category]], columns=[category], drop_first=True, dtype=float)
    for category in cat_name
}

enter_threshold = 0.05
q_show_diary = True
step_diary = []

var_in_model = ['Intercept']



# The FSig is the sixth element in each row of the FTest
def takeFSig(s):
    return s[7] #### 6 or 7



# Step 0: Enter Intercept
X0 = pandas.DataFrame(index=train_data.index)   # or: X0 = pandas.DataFrame({'const': 1.0}, index=LakeView.index)
X0.insert(0, 'Intercept', 1.0)
result_list = Regression.LinearRegression(X0, y_train)
m0 = len(result_list[5])

SST = numpy.sum(numpy.square(y_train - numpy.mean(y_train)))


# residual_variance = result_list[2] and residual_df = result_list[3]
SSE0 = result_list[2] * result_list[3]
r_square = 1.0 - (SSE0 / SST)



step_diary.append([0, 'Intercept', SSE0, m0, r_square] + 5 * [numpy.nan])

candidate = TLakeView_name


## Forward Selection Steps
for iStep in range(n_TLakeView_name):
    FTest = []
    for pred in candidate:
        if pred in cat_name:
            Candidate_for_X = dummies_dictionnary[pred]
        else:
            Candidate_for_X =  train_data[[pred]]
        column_to_join = [columns for columns in Candidate_for_X.columns if columns not in X0.columns]
        Candidate_for_X = Candidate_for_X[[column_to_join]]
        X = X0.join(Candidate_for_X)

        result_list = Regression.LinearRegression(X, y_train)
        print(result_list)
        m1 = len(result_list[5])
        SSE1 = result_list[2] * result_list[3]
        r_square = 1.0 - (SSE1 / SST)

        df_numer = m1 - m0
        df_denom = n_sample - m1
        if (df_numer > 0 and df_denom > 0):
            FStat = ((SSE0 - SSE1) / df_numer) / (SSE1 / df_denom)
            FSig = f.sf(FStat, df_numer, df_denom)
            FTest.append([pred, SSE1, m1, r_square, FStat, df_numer, df_denom, FSig])

    # Show F Test results for the current step
    if (q_show_diary): 
        print('\n===== F Test Results for the Current Forward Step =====')
        print('Step Number: ', iStep)
        print('Step Diary:')
        print('[Variable Candidate | Residual Sum of Squares | N Non-Aliased Parameters | R-Square | F Stat | F DF1 | F DF2 | F Sig]')
        for row in FTest:
            print(row)

    FTest.sort(key = takeFSig, reverse = False)
    FSig = takeFSig(FTest[0])
    if (FSig <= enter_threshold):
        enter_var = FTest[0][0]
        SSE0 = FTest[0][1]
        m0 = FTest[0][2]
        step_diary.append([iStep+1] + FTest[0])
        X = train_data[[enter_var]]
        if enter_var in cat_name:
            add = dummies_dictionnary[enter_var]
        else:
            add = train_data[[enter_var]]
        column_to_join = [columns for columns in Candidate_for_X.columns if columns not in X0.columns]
        add = add[column_to_join]
        X0 = X0.join(X)
        var_in_model.append(enter_var)
        candidate.remove(enter_var)
    else:
        break

forward_summary = pandas.DataFrame(step_diary, columns = ['Step', 'Variable Entered', 'Residual Sum of Squares', 'N Non-Aliased Parameters', 'R-Square', 'F Stat', 'F DF1', 'F DF2', 'F Sig'])

