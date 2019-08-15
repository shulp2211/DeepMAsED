import numpy as np
from sklearn.metrics import confusion_matrix, roc_curve
from sklearn.metrics import recall_score, roc_auc_score
from sklearn.metrics import precision_recall_curve, average_precision_score
from sklearn.preprocessing import StandardScaler
import argparse
import IPython
import _pickle as pickle

from inspect import signature 

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import os

import itertools
import operator
import bisect


parser = argparse.ArgumentParser()
parser.add_argument('--data_path', default='data', type=str, 
                    help='Where to find feature table.')
parser.add_argument('--ale_path', default='data', type=str, 
                    help='Where to find feature table.')
parser.add_argument('--save_path', default='model', type=str, 
                    help='Where to save training weights and logs.')
args = parser.parse_args()

path_to_models = os.listdir(args.save_path)
auc = []

# With ALE
with open(os.path.join(args.ale_path, '../best_param_ale_train.pkl'), 'rb') as bestp:
    thresh, sc = pickle.load(bestp)

assemblies = os.listdir(args.ale_path)

for model_path in path_to_models:

    if not os.path.exists((os.path.join(args.save_path, model_path, 'final_model.h5'))):
        continue
    
    y, preds = [], []
    preds_ale, y_ale = [], []

    for itech, tech in enumerate(['megahit', 'metaspades']):
        # Get for DeepMAsED
        with open(os.path.join(args.save_path, model_path, 'predictions', 
                               args.data_path.split('/')[-1],  tech + '.pkl'), 'rb') as spred:
            scores = pickle.load(spred)

        for assembly in scores:
            for contig in scores[assembly]:
                y.append(scores[assembly][contig]['y'])
                preds.append(np.mean(scores[assembly][contig]['pred']))

        # Get for ALE
        ale_scores = []
        for mag in assemblies: 
            if not os.path.exists(os.path.join(args.ale_path, mag, tech + '_all.pkl')):
                print("Pickle file not found for " + mag)
                exit()
            with open(os.path.join(args.ale_path, mag, tech + '_all.pkl'), 'rb') as f:
                ale_scores.append(pickle.load(f))

        for i in range(len(ale_scores)):
            if int(assemblies[i]) not in scores:
                continue
            for cont in ale_scores[i]:
                if cont in scores[int(assemblies[i])]: 
                    y_ale.append(scores[int(assemblies[i])][cont]['y'])
                else:
                    # A few contigs are missing
                    continue
                total = 0
                for score in ale_scores[i][cont]:
                    total += np.sum(ale_scores[i][cont][score] < thresh[score])

                preds_ale.append(total / float(len(thresh)) / len(ale_scores[i][cont]['depth']))


    #Sanity check
    assert(np.sum(np.array(y) - np.array(y_ale)) == 0)
    assert(len(preds) == len(preds_ale))


    # PR RE for DeepMAsED
    precision, recall, thr = precision_recall_curve(y, preds)
    with open(os.path.join(args.save_path, model_path, 'predictions/pr_from_training.pkl'), 'wb') as f:
        pickle.dump([precision, recall, thr], f)

    # PR RE for ALE
    precision, recall, thr = precision_recall_curve(y_ale, preds_ale)
    with open(os.path.join(args.ale_path, '../pr_from_training.pkl'), 'wb') as f:
        pickle.dump([precision, recall, thr], f)

