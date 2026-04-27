"""
Name: LogisticRegression.py
Course: ADSP31014: Statistical Models for Data Science
Author: Ming-Long Lam, Ph.D.
Organization: University of Chicago
Last Modified: November 11, 2024
(C) All Rights Reserved.
"""

import numpy
import pandas

from scipy.special import gammaln
from scipy.stats import norm, t

def SWEEPOperator (pDim, inputM, origDiag, sweepCol = None, tol = 1e-7):
    ''' Implement the SWEEP operator

    Parameter
    ---------
    pDim: dimension of matrix inputM, integer greater than one
    inputM: a square and symmetric matrix, numpy array
    origDiag: the original diagonal elements before any SWEEPing
    sweepCol: a list of columns numbers to SWEEP
    tol: singularity tolerance, positive real

    Return
    ------
    A: negative of a generalized inverse of input matrix
    aliasParam: a list of aliased rows/columns in input matrix
    nonAliasParam: a list of non-aliased rows/columns in input matrix
    '''

    if (sweepCol is None):
        sweepCol = range(pDim)

    aliasParam = []
    nonAliasParam = []

    A = numpy.copy(inputM)
    ANext = numpy.zeros((pDim,pDim))

    for k in sweepCol:
        Akk = A[k,k]
        pivot = tol * abs(origDiag[k])
        if (not numpy.isinf(Akk) and abs(Akk) >= pivot and pivot > 0.0):
            nonAliasParam.append(k)
            ANext = A - numpy.outer(A[:, k], A[k, :]) / Akk
            ANext[:, k] = A[:, k] / abs(Akk)
            ANext[k, :] = ANext[:, k]
            ANext[k, k] = -1.0 / Akk
        else:
            aliasParam.append(k)
        A = ANext
    return (A, aliasParam, nonAliasParam)

def CramerV (xCat, yCat):
   ''' Calculate Cramer V statistic

   Argument:
   ---------
   xCat : a Pandas Series
   yCat : a Pandas Series

   Output:
   -------
   cramerV : Cramer V statistic
   '''

   obsCount = pandas.crosstab(index = xCat, columns = yCat, margins = False, dropna = True)
   xNCat = obsCount.shape[0]
   yNCat = obsCount.shape[1]
    
   if (xNCat > 1 and yNCat > 1):
      cTotal = obsCount.sum(axis = 1)
      rTotal = obsCount.sum(axis = 0)
      nTotal = numpy.sum(rTotal)
      expCount = numpy.outer(cTotal, (rTotal / nTotal))

      # Calculate the Chi-Square statistics
      chiSqStat = ((obsCount - expCount)**2 / expCount).to_numpy().sum()
      cramerV = chiSqStat / nTotal / (min(xNCat, yNCat) - 1.0)
      cramerV = numpy.sqrt(cramerV)
   else:
      cramerV = numpy.NaN

   return (cramerV)

def create_interaction (df1, df2):
    ''' Return the columnwise product of two dataframes (must have same number of rows)

    Parameter
    ---------
    df1: first input data frame
    df2: second input data frame

    Return
    ------
    outDF: the columnwise product of two dataframes
    '''

    name1 = df1.columns
    name2 = df2.columns
    outDF = pandas.DataFrame()
    for col1 in name1:
        outName = col1 + ' * ' + name2
        outDF[outName] = df2.multiply(df1[col1], axis = 'index')
    return(outDF)

def paste_interaction (effectName):
    name1 = ''
    name2 = ''
    aName = effectName.strip() 
    ipos = aName.find('*')
    if (ipos >= 0):
        name1 = aName[:ipos].strip()
        name2 = aName[(ipos+1):].strip()
        if (len(name1) == 0 and len(name2) > 0):
            name1 = name2
            name2 = ''
    else:
        name1 = aName

    return ([name1, name2])

def construct_X_from_spec (data, catPred, intPred, modelSpec, qIntercept = True):

    # Generate the model matrix in the order of model specification
    modelX = data[[]]
    for effect in modelSpec:
        name_list =  paste_interaction(effect)
        name1 = name_list[0]
        if (len(name1) > 0):
            if (name1 in catPred):
               df1 = pandas.get_dummies(data[[name1]].astype('category'), dtype = float)
            else:
               df1 = data[[name1]]
        else:
            df1 = None

        name2 = name_list[1]
        if (len(name2) > 0):
            if (name2 in catPred):
               df2 = pandas.get_dummies(data[[name2]].astype('category'), dtype = float)
            else:
               df2 = data[[name2]]
        else:
           df2 = None

        if (df1 is not None and df2 is not None):
           modelX = modelX.join(create_interaction (df1, df2))
        elif (df1 is not None):
           modelX = modelX.join(df1)

    if (qIntercept):
        modelX.insert(0, 'Intercept', 1.0)

    return (modelX)

def objQuantile (x, w, p, currQ):
    sumLT = 0.0
    sumGT = 0.0
    for vx, vw in zip(x, w):
        if (vx < currQ):   
            sumLT += vw
        elif (vx > currQ):
            sumGT += vw
    objFunc = (1.0 - p) * sumLT - p * sumGT

    return (objFunc)

def findQuantile (x, w, p, nIter = 1000, eps = 1e-14):

    # Set lower bound of the interval to the minimum value
    xLow = numpy.min(x)
    fLow = objQuantile(x, w, p, xLow)

    # Set upper bound of the interval to the maximum value
    xUp = numpy.max(x)
    fUp = objQuantile(x, w, p, xUp)

    # Determine if iteration should start
    qCont = 0
    if (fLow < 0.0 and fUp > 0.0):
        qCont = 1
        xQuantile = xLow - 1.0
    elif (fLow == 0.0):
        xQuantile = xLow
    elif (fUp == 0.0):
        xQuantile = xUp
    else:
        xQuantile = numpy.NaN

    # Perform iterations
    iteration = 0
    while (iteration < nIter and qCont == 1):
        xQuantile_prev = xQuantile
        xQuantile = (xLow + xUp) / 2.0
        fQuantile = objQuantile(x, w, p, xQuantile)

        iteration += 1
        if (abs(xQuantile - xQuantile_prev) < eps):
            qCont = 0
        elif (fQuantile < 0.0):
            xLow = xQuantile
        elif (fQuantile > 0.0):
            xUp = xQuantile

    return (xQuantile)

def binary_model_metric (crossTable, valueEvent, valueNonEvent):
    '''Calculate metrics for a binary classification model

    Parameter
    ---------
    crossTable: a Pandas DataFrame where the predicted event probabilities are the indices,
                and the columns are counts of event and non-event target categories
    valueEvent: Formatted value of target variable that indicates an event
    valueNonEvent: Formatted value of target variable that indicates a non-event

    Return
    ------
    outSeries: Pandas Series that contain the following statistics
               ASE: Average Squared Error
               RASE: Root Average Squared Error
               AUC: Area Under Curve
    '''

    # Number of observations
    nObs = crossTable.sum().sum()

    # Calculate the root average square error
    ase = (numpy.sum(crossTable[valueEvent] * (1.0 - crossTable.index)**2) +
           numpy.sum(crossTable[valueNonEvent] * (0.0 - crossTable.index)**2)) / nObs
    if (ase > 0.0):
        rase = numpy.sqrt(ase)
    else:
        rase = 0.0

    # Calculate the number of concordant, discordant, and tied pairs
    nConcordant = 0.0
    nDiscordant = 0.0
    nTied = 0.0

    # Loop over the predicted event probabilities from the Event column
    predEP = crossTable.index
    eventFreq = crossTable[valueEvent]

    for i in range(len(predEP)):
        eProb = predEP[i]
        eFreq = eventFreq.loc[eProb]
        if (eFreq > 0.0):
            nConcordant = nConcordant + numpy.sum(eFreq * crossTable[valueNonEvent].iloc[eProb > crossTable.index])
            nDiscordant = nDiscordant + numpy.sum(eFreq * crossTable[valueNonEvent].iloc[eProb < crossTable.index])
            nTied = nTied + numpy.sum(eFreq * crossTable[valueNonEvent].iloc[eProb == crossTable.index])

    auc = 0.5 + 0.5 * (nConcordant - nDiscordant) / (nConcordant + nDiscordant + nTied)

    outSeries = pandas.Series({'ASE': ase, 'RASE': rase, 'AUC': auc})
    return(outSeries)

def misclassify_error (crossTable, valueEvent, valueNonEvent, eventProbThreshold = 0.5):
    '''Calculate misclassification error for a binary classification model

    Parameter
    ---------
    crossTable: a Pandas DataFrame where the predicted event probabilities are the indices,
                and the columns are counts of event and non-event target categories
    valueEvent: Formatted value of target variable that indicates an event
    valueNonEvent: Formatted value of target variable that indicates a non-event
    eventProbThreshold: Threshold for event probability to indicate a success

    Return
    ------
    mce: Misclassification Error Rate
    '''

    # Number of observations
    nObs = crossTable.sum().sum()

    # Calculate the misclassification error rate
    nFP = numpy.sum(crossTable[valueNonEvent].iloc[crossTable.index >= eventProbThreshold])
    nFN = numpy.sum(crossTable[valueEvent].iloc[crossTable.index < eventProbThreshold])
    mce = (nFP + nFN) / nObs

    return (mce)

def curve_coordinates (crossTable, valueEvent, valueNonEvent):
    '''Calculate coordinates of the Receiver Operating Characteristics (ROC) curve and
    the Precision Recall (PR) curve

    Classification Convention
    -------------------------
    An observation is classified as Event if the predicted event probability is
    greater than or equal to a given threshold value.

    Parameter
    ---------
    crossTable: a Pandas DataFrame where the predicted event probabilities are the indices,
                and the columns are counts of event and non-event target categories
    valueEvent: Formatted value of target variable that indicates an event
    valueNonEvent: Formatted value of target variable that indicates a non-event

    Return
    ------
    outCurve: Pandas dataframe for the curve coordinates
              Threshold: Event probability threshold of the coordinates
              Sensitivity: Sensitivity coordinate
              OneMinusSpecificity: 1 - Specificity coordinate
              Precision: Precision coordinate
              Recall: Recall coordinate
    '''

    # Aggregate observations by the target values and the predicted probabilities
    threshValue = crossTable.index
    n_thresh = len(threshValue)
    curve_coord = []

    # Find out the number of events and non-events
    n_event = numpy.sum(crossTable[valueEvent])
    n_nonevent = numpy.sum(crossTable[valueNonEvent])

    for i in range(n_thresh):
        thresh = threshValue[i]
        nTP = numpy.sum(crossTable[valueEvent].iloc[threshValue >= thresh])
        nFP = numpy.sum(crossTable[valueNonEvent].iloc[threshValue >= thresh])

        Sensitivity = nTP / n_event
        OneMinusSpecificity = nFP / n_nonevent
        Precision = nTP / (nTP + nFP)
        Recall = Sensitivity
        F1Score = 2.0 / (1.0 / Precision + 1.0 / Recall)

        curve_coord.append([thresh, Sensitivity, OneMinusSpecificity, Precision, Recall, F1Score])

    outCurve = pandas.DataFrame(curve_coord, index = range(n_thresh),
                                columns = ['Threshold', 'Sensitivity', 'OneMinusSpecificity', 'Precision', 'Recall', 'F1 Score'])

    return (outCurve)

def lift_curve_coordinates (crossTable, valueEvent, valueNonEvent):
    '''Calculate coordinates of the Lift Curve

    Classification Convention
    -------------------------
    An observation is classified as Event if the predicted event probability is
    greater than or equal to a given threshold value.

    Parameter
    ---------
    crossTable: a Pandas DataFrame where the predicted event probabilities are the indices,
                and the columns are counts of event and non-event target categories
    valueEvent: Formatted value of target variable that indicates an event
    valueNonEvent: Formatted value of target variable that indicates a non-event

    Return
    ------
    liftCurve: Pandas dataframe for the lift curve coordinates
    accumLiftCurve: Pandas dataframe for the accumulated lift curve coordinates
    '''

    # Get the predicted event probability
    predEventProb = list(crossTable.index)

    # Get the number of observations per probability
    probWeight = crossTable[valueEvent] + crossTable[valueNonEvent]

    # Get the total number of observations
    nObs = probWeight.sum()

    decileCutOff = []
    for p in numpy.arange(0.1, 1.0, 0.1):
        decile = findQuantile (predEventProb, probWeight, p)
        decileCutOff.append(decile)

    nDecile = len(decileCutOff) + 1

    decileIndex = []
    for p in predEventProb:
        iQ = nDecile
        for j in range(1, nDecile):
            if (p > decileCutOff[-j]):
                iQ -= 1
        decileIndex.append(iQ)
    crossTable['Decile Index'] = decileIndex

    # Construct the Lift chart table
    countTable = crossTable.groupby('Decile Index')[[valueEvent, valueNonEvent]].sum()

    decileN = countTable.sum(axis = 1)
    decilePct = 100.0 * (decileN / nObs)
    gainN = countTable[valueEvent]
    totalNResponse = gainN.sum(0)
    gainPct = 100.0 * (gainN /totalNResponse)
    responsePct = 100.0 * (gainN / decileN)
    overallResponsePct = 100.0 * (totalNResponse / nObs)
    lift = responsePct / overallResponsePct

    liftCurve = pandas.DataFrame({'Decile N': decileN, 'Decile %': decilePct, \
                                  'Gain N': gainN, 'Gain %': gainPct, \
                                  'Response %': responsePct, 'Lift': lift})

    # Construct the Accumulative Lift chart table
    accCountTable = countTable.cumsum(axis = 0)
    decileN = accCountTable.sum(axis = 1)
    decilePct = 100.0 * (decileN / nObs)
    gainN = accCountTable[valueEvent]
    gainPct = 100.0 * (gainN / totalNResponse)
    responsePct = 100.0 * (gainN / decileN)
    lift = responsePct / overallResponsePct

    accumLiftCurve = pandas.DataFrame({'Acc. Decile N': decileN, 'Acc. Decile %': decilePct, \
                                       'Acc. Gain N': gainN, 'Acc. Gain %': gainPct, \
                                       'Acc. Response %': responsePct, 'Acc. Lift': lift})

    return ([decileCutOff, liftCurve, accumLiftCurve])

def BinaryLogisticRegression (trainData, catPred, intPred, binaryLabel, eventCategory, \
                              modelSpec, qIntercept = True, \
                              maxIter = 100, maxStep = 7, tolLLK = 1e-3, tolEpsilon = 1e-10, tolSweep = 1e-7):
    ''' Train a Binary Logistic Regression model

    Parameters
    ----------
    trainData: A Pandas DataFrame, rows are observations, columns are features
    catPred: A list of names to columns of trainData, designated as categorical predictors
    intPred: A list of names to columns of trainData, designated as interval predictors
    binaryLabel: A name to a column of trainData, desigated as the binary target variable
    eventCategory: A string that contains the event category
    modelSpec: A list of model effect specifications (main effect and two-way interactions only)
    qIntercept: If True, the model will include the Intercept term. Otherwise, the model has no Intercept term.
    maxIter: Maximum number of iterations
    maxStep: Maximum number of step-halving
    tolLLK: Minimum absolute difference to get a successful step-halving
    tolEpsilon: A surrogate value for zero
    tolSweep: Tolerance for SWEEP Operator

    Return List
    -----------
    outCoefficient: a Pandas DataFrame of regression coefficients, standard errors, and confidence interval
    outCovb: a Pandas DataFrame of covariance matrix of regression coefficients
    outCorb: a Pandas DataFrame of correlation matrix of regression coefficients
    llk: log-likelihood value
    nonAliasParam: a list of non-aliased rows/columns in input matrix
    outIterationTable: a Pandas DataFrame of iteration history table
    labelCategories: A Pandas Series of label variable's categories
    predprob_df: a Pandas DataFrame of event count, total count, and the predicted probabilities
    measure_assoc: a list with 0: McFadden R-squares, 1: Cox & Snell R-squares,
                   2: Nagelkerke R-squares, and  3: Tjur Coefficient of Discrimination
    '''

    predictor_name = catPred + intPred

    # Generate the crosstabulation of predictors by binary label
    if (len(predictor_name) > 0):
        xtab = pandas.crosstab(index = [trainData[pred] for pred in predictor_name],
                               columns = trainData[binaryLabel]).reset_index(drop = False)
        predictor_df = xtab[predictor_name]
        label_count = xtab.drop(columns = predictor_name)
        n_count = label_count.sum(axis = 1)
    else:
        predictor_df = pandas.DataFrame()
        label_count = trainData[binaryLabel].value_counts()
        n_count = label_count.sum()

    # Extract columns of he crosstabulation
    event_count = label_count[eventCategory]
    nonevent_count = n_count -  event_count

    # Generate the model matrix in the order of model specification
    modelX = construct_X_from_spec (predictor_df, catPred, intPred, modelSpec, qIntercept)

    # Initialize the predicted event and non-event probabilities
    if (qIntercept):
        obs_event_prob = numpy.sum(event_count) / numpy.sum(n_count)
        obs_nonevent_prob = 1.0 - obs_event_prob
    else:
        obs_event_prob = 0.5
        obs_nonevent_prob = 0.5

    n_value_comb = modelX.shape[0]
    n_param = modelX.shape[1]
    param_name = modelX.columns

    modelXT = modelX.transpose()

    # Initialize predicted probabilities, parameter estimates, and log-likelihood value
    event_prob = numpy.full(n_value_comb, obs_event_prob)
    nonevent_prob = numpy.full(n_value_comb, obs_nonevent_prob)

    beta = pandas.Series(numpy.zeros(n_param), index = param_name)
    beta[param_name[0]] = numpy.log(obs_event_prob / obs_nonevent_prob)

    llk_constant = numpy.sum(gammaln(n_count + 1.0) - gammaln(event_count + 1.0) - gammaln(nonevent_count + 1.0))
    llk_kernel = numpy.sum(event_count * numpy.log(event_prob) + nonevent_count * numpy.log(nonevent_prob))
    llk = llk_kernel + llk_constant
    llk_kernel_0 = llk_kernel

    # Prepare the iteration history table (Iteration #, Log-Likelihood, N Step-Halving, Beta)
    itList = [0, llk, 0]
    itList.extend(beta)
    iterTable = [itList]

    for it in range(maxIter):
        expected_event_count = n_count * event_prob
        gradient = modelXT.dot(event_count - expected_event_count)
        dispersion = expected_event_count * nonevent_prob
        hessian = - modelXT.dot(dispersion.values.reshape((n_value_comb,1)) * modelX)
        orig_diag = numpy.diag(hessian)
        invhessian, aliasParam, nonAliasParam = SWEEPOperator (n_param, hessian, orig_diag, sweepCol = range(n_param), tol = tolSweep)
        invhessian[:, aliasParam] = 0.0
        invhessian[aliasParam, :] = 0.0
        delta = numpy.matmul(-invhessian, gradient)
        step = 1.0
        for iStep in range(maxStep):
            beta_next = beta - step * delta
            nu_next = modelX.dot(beta_next)
            exp_nu_next = numpy.exp(nu_next)

            event_prob_next = 1.0 / (1.0 + (1.0 / exp_nu_next))
            nonevent_prob_next = 1.0 / (1.0 + exp_nu_next)
            llk_next = numpy.sum(event_count * numpy.log(event_prob_next) + nonevent_count * numpy.log(nonevent_prob_next)) + llk_constant
            if ((llk_next - llk) > - tolLLK):
                break
            else:
                step = 0.5 * step

        diffBeta = beta_next - beta
        beta = beta_next
        llk = llk_next
        event_prob = event_prob_next
        nonevent_prob = nonevent_prob_next
        itList = [it+1, llk, iStep]
        itList.extend(beta)
        iterTable.append(itList)
        if (numpy.linalg.norm(diffBeta) < tolEpsilon or abs(llk) < tolEpsilon):
            break

    it_name = ['Iteration', 'Log-Likelihood', 'N Step-Halving']
    it_name.extend(param_name)
    outIterationTable = pandas.DataFrame(iterTable, columns = it_name)

    # Final covariance matrix
    stderr = numpy.sqrt(numpy.diag(invhessian))
    z95 = norm.ppf(0.975)

    # Final parameter estimates
    outCoefficient = pandas.DataFrame(beta, index = param_name, columns = ['Estimate'])
    outCoefficient['Standard Error'] = stderr
    outCoefficient['Lower 95% CI'] = beta - z95 * stderr
    outCoefficient['Upper 95% CI'] = beta + z95 * stderr

    outCovb = pandas.DataFrame(invhessian, index = param_name, columns = param_name)

    temp_m1_ = numpy.outer(stderr, stderr)
    outCorb = pandas.DataFrame(numpy.divide(invhessian, temp_m1_, out = numpy.zeros_like(invhessian), where = (temp_m1_ != 0.0)),
                               index = param_name, columns = param_name)
    
    labelCategories = label_count.columns

    predprob_df = predictor_df.join(label_count)
    predprob_df = predprob_df.join(pandas.DataFrame({'Total': n_count, 'Predicted Event Probability': event_prob, \
                                                     'Predicted Non-Event Probability': nonevent_prob}))

    # Calculate the measure of association
    llk_kernel = llk - llk_constant
    n_sample = trainData.shape[0]

    R_MF = 1.0 - (llk_kernel / llk_kernel_0)

    R_CS = (2.0 / n_sample) * (llk_kernel_0 - llk_kernel)
    R_CS = 1.0 - numpy.exp(R_CS)

    upbound = (2.0 / n_sample) * llk_kernel_0
    upbound = 1.0 - numpy.exp(upbound)
    R_N = R_CS / upbound

    event_count = label_count[eventCategory]
    S1 = numpy.sum(event_prob * event_count) / numpy.sum(event_count)
    
    nonevent_count = n_count - event_count
    S0 = numpy.sum(event_prob * nonevent_count) / numpy.sum(nonevent_count)
    R_TJ = S1 - S0

    measure_assoc = [R_MF, R_CS, R_N, R_TJ]

    return ([outCoefficient, outCovb, outCorb, llk, nonAliasParam, outIterationTable, labelCategories, predprob_df, measure_assoc])
