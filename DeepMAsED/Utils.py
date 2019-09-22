# import
## batteries
import _pickle as pickle
import os
import sys
import csv
import gzip
import glob
import logging
from collections import defaultdict
## 3rd party
from keras import backend as K
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import IPython
## application


def compute_mean_std(x_tr):
    """
    Given training data (list of contigs), compute mean and std 
    feature-wise. 
    """

    n_feat = x_tr[0].shape[1]
    feat_sum = np.zeros(n_feat)
    feat_sq_sum = np.zeros(n_feat)
    n_el = 0

    for xi in x_tr:
        sum_xi = np.sum(xi, 0)
        sum_sq = np.sum(xi ** 2, 0)
        feat_sum += sum_xi
        feat_sq_sum += sum_sq
        n_el += xi.shape[0]

    mean = feat_sum / n_el
    std = np.sqrt(feat_sq_sum / n_el - mean ** 2)

    return mean, std

def normalize(x, mean, std, max_len):
    """
    DETERIORATED
    Given mean and std vector computed from training data, 
    normalize and return in shape (n, p, 1)
    """
    n_feat = x[0].shape[1]

    for i in range(len(x)):
        x[i] = (x[i] - mean) / std
        num_timesteps = x[i].shape[0]
        if num_timesteps < max_len:
            x[i] = np.concatenate((x[i], 
                                   np.zeros((max_len - num_timesteps, n_feat))), 
                                   0)
        else:
            x[i] = x[i][0:max_len]
        x[i] = np.expand_dims(x[i], 0)
    
    x = np.concatenate(x, 0)
    x = np.expand_dims(x, -1)

    return x

def splitall(path):
    path = os.path.abspath(path)
    allparts = []
    while 1:
        parts = os.path.split(path)
        if parts[0] == path: 
            allparts.insert(0, parts[0])
            break
        elif parts[1] == path:
            allparts.insert(0, parts[1])
            break
        else:
            path = parts[0]
            allparts.insert(0, parts[1])
    return allparts

def find_feature_files(data_path, filename):
    """ Finds feature files & creates.
    Return: {metagenome_id : {assembler : filename}}
    """
    D = defaultdict(dict)
    n_feat_files = 0
    for dirpath, dirnames, files in os.walk(data_path):
        for F in files:
            if F == filename:
                x = splitall(dirpath)
                if len(x) < 4:
                    msg = 'data_path is not structure correctly: {}'
                    raise IOError(msg.format(data_path))
                sim_rep = x[-2]     # simulation rep
                asmbl = x[-1]       # assembler
                D[sim_rep][asmbl] = os.path.join(dirpath, F)
                n_feat_files += 1
                
    return D, n_feat_files
    
def load_features_tr(data_path, max_len=10000, 
                     standard=1, mode='extensive', 
                     pickle_only=False, force_overwrite=False):
    """
    Loads features, pre-process them and returns training. 
    Fuses data from both assemblers. 

    Inputs: 
        data_path: path to directory containing features.pkl
        max_len: fixed length of contigs

    Outputs:
        x, y: lists, where each element comes from one metagenome, and 
          a dictionary with idx -> (metagenome, contig_name)

    #--- input data directory structure --#
    deepmased-sm_output_dir
      |- map
          |- 1
          |  |-- assembler1
          |  |    |_ features.tsv.gz
          |  |-- assembler2
          |  |     |_ features.tsv.gz
          |  |-- assemblerN
          |       |_ features.tsv.gz
          |- 2
          |  |-- assembler1
          |  |    |_ features.tsv.gz
          |  |-- assembler2
          |  |     |_ features.tsv.gz
          |  |-- assemblerN
          |       |_ features.tsv.gz
          |- N
             |-- assembler1
             |    |_ features.tsv.gz
             |-- assembler2
             |     |_ features.tsv.gz
             |-- assemblerN
                  |_ features.tsv.gz
    """
    # finding feature files
    feature_gz_files, n_gz = find_feature_files(data_path, 'features.tsv.gz')
    feature_tsv_files, n_tsv = find_feature_files(data_path, 'features.tsv')
    feature_pkl_files, n_pkl = find_feature_files(data_path, 'features.pkl')
    if n_pkl > 1 and force_overwrite is True:
        msg = 'Found {} pickled feature files. However, --force-overwrite used.'
        msg += ' Re-creating pkl feature files'
        logging.info(msg.format(n_pkl))
    if n_pkl >= 1 and force_overwrite is False:
        msg = 'Found {} pickled feature files. Using these files.'
        logging.info(msg.format(n_pkl))
    elif n_gz >= 1:
        msg = 'Found {} gzip\'ed tsv feature files. Using these files.'
        logging.info(msg.format(n_gz))
        feature_pkl_files = defaultdict(dict)
        for rep,v in feature_gz_files.items():
            for asmbl,F in v.items():
                pklF = os.path.join(os.path.split(F)[0], 'features.pkl')
                feature_pkl_files[rep][asmbl] = pickle_data_b(F, pklF)
    elif n_tsv >= 1:
        msg = 'Found {} uncompressed tsv feature files. Using these files.'
        logging.info(msg.format(n_tsv))
        feature_pkl_files = defaultdict(dict)
        for rep,v in feature_tsv_files.items():
            for asmbl,F in v.items():
                pklF = os.path.join(os.path.split(F)[0], 'features.pkl')
                feature_pkl_files[rep][asmbl] = pickle_data_b(F, pklF)
    else:
        msg = 'Could not find any features files in data_path: {}'
        raise IOError(msg.format(data_path))

    # Pre-process once if not done already
    if pickle_only:
        logging.info('--pickle-only provided; exiting')        
        exit(0)

    # for each simulation rep, combining features from each assembler together
    ## "tech" = assembler
    x, y, ye, yext, n2i = [], [], [], [], []
    for rep,v in feature_pkl_files.items():
        xtech, ytech = [], []
        for tech,filename in v.items():
            with open(filename, 'rb') as feat:
                xi, yi, n2ii = pickle.load(feat)
                xtech.append(xi)
                ytech.append(yi)

        x_in_contig, y_in_contig = [], []
        
        for xi, yi in zip(xtech, ytech):
            for j in range(len(xi)):
                len_contig = xi[j].shape[0]

                idx_chunk = 0
                while idx_chunk * max_len < len_contig:
                    chunked = xi[j][idx_chunk * max_len : (idx_chunk + 1) * max_len, 1:]
            
                    x_in_contig.append(chunked)
                    y_in_contig.append(yi[j])

                    idx_chunk += 1

        # Each element is a metagenome
        x.append(x_in_contig)
        yext.append(np.array(y_in_contig))

    # mode 
    if mode == 'edit':
        y = 100 * np.array(ye)
    elif mode == 'extensive':
        y = yext
    else:
        raise('Mode "{}" currently not supported'.format(mode))

    return x, y


def load_features(data_path, max_len=10000, 
                  standard=1, mode='extensive', technology='megahit', 
                  pickle_only=False):
    """
    Loads features, pre-process them and returns validation data. 

    Inputs: 
        data_path: path to directory containing features.pkl
        max_len: fixed length of contigs
        standard: whether to standardise features.
        technology: assembler, megahit or metaspades.
        pickle_only: only perform pickling prior to testing. One time call. 

    Outputs:
        x, y, i2n: lists, where each element comes from one metagenome, and 
          a dictionary with idx -> (metagenome, contig_name)
    """

    # Pre-process once if not done already
    dirs = os.listdir(data_path)
    for i, f in enumerate(dirs):#os.listdir(data_path):
        current_path = os.path.join(data_path, f, technology)

        if not os.path.exists(os.path.join(current_path, 'features.pkl')):
            logging.info('Populating pickle file...')
            pickle_data_b(current_path, 'features.tsv.gz', 'features_new.pkl')

    if pickle_only: 
        exit()

    x, y, ye, yext, n2i = [], [], [], [], []
    shift = 0
    i2n_all = {}
    for i, f in enumerate(dirs):
        current_path = os.path.join(data_path, f, technology)
        with open(os.path.join(current_path, 'features_new.pkl'), 'rb') as feat:
            features = pickle.load(feat)

        xi, yi, n2ii = features
        
        i2ni = reverse_dict(n2ii)
        
        x_in_contig, y_in_contig = [], []

        n2i_keys = set([])
        for j in range(len(xi)):
            len_contig = xi[j].shape[0]

            idx_chunk = 0
            while idx_chunk * max_len < len_contig:
                chunked = xi[j][idx_chunk * max_len : (idx_chunk + 1) * max_len, 1:]
        
                x_in_contig.append(chunked)
                y_in_contig.append(yi[j])

                i2n_all[len(x_in_contig) - 1 + shift] = (int(f), i2ni[j][0])
                idx_chunk += 1
                n2i_keys.add(i2ni[j][0])

        # Each element is a metagenome
        x.append(x_in_contig)
        yext.append(np.array(y_in_contig))

        #Sanity check
        assert(len(n2i_keys - set(n2ii.keys())) == 0)
        assert(len(set(n2ii.keys()) - n2i_keys) == 0)

        shift = len(i2n_all)

    if mode == 'edit':
        y = 100 * np.array(ye)
    elif mode == 'extensive':
        y = yext
    else:
        raise("Mode currently not supported")

    return x, y, i2n_all


def load_features_nogt(data_path, max_len=10000, 
                      mode='extensive', 
                      pickle_only=False):
    """
    Loads features for real datasets. Filters contigs with low coverage. 

    Inputs: 
        data_path: path to directory containing features.pkl
        max_len: fixed length of contigs

    Outputs:
        x, y, i2n: lists, where each element comes from one metagenome, and 
          a dictionary with idx -> (metagenome, contig_name)
    """

    # Pre-process once if not done already
    dirs = os.listdir(data_path)
    for i,f in enumerate(dirs):
        if not os.path.isdir(f):
            continue
        for g in os.listdir(os.path.join(data_path, f)):
            current_path = os.path.join(data_path, f, g)
            if not os.path.isdir(current_path):
                continue
            if not os.path.exists(os.path.join(current_path, 'features_new.pkl')):
                pickle_data_feat_only(current_path, 'features.tsv.gz', 'features_new.pkl')

    if pickle_only: 
        exit()

    x, y, ye, yext, n2i = [], [], [], [], []
    shift = 0
    i2n_all = {}

    idx_coverage = -2
    for i, f in enumerate(dirs):
        if not os.path.isdir(os.path.join(data_path, f)):
            continue
        for g in os.listdir(os.path.join(data_path, f)):
            current_path = os.path.join(data_path, f, g)
            if not os.path.exists(os.path.join(current_path, 'features_new.pkl')):
                continue
            with open(os.path.join(current_path, 'features_new.pkl'), 'rb') as feat:
                features = pickle.load(feat)

            xi, n2ii = features
            yi = [-1 for i in range(len(xi))]
            
            i2ni = reverse_dict(n2ii)

            x_in_contig, y_in_contig = [], []

            n2i_keys = set([])
            for j in range(len(xi)):
                len_contig = xi[j].shape[0]
                
                #Filter low coverage
                if np.amin(xi[j][:, idx_coverage]) == 0:
                    continue

                idx_chunk = 0
                while idx_chunk * max_len < len_contig:
                    chunked = xi[j][idx_chunk * max_len : (idx_chunk + 1) * max_len, 1:]
            
                    x_in_contig.append(chunked)
                    y_in_contig.append(yi[j])

                    i2n_all[len(x_in_contig) - 1 + shift] = (f, i2ni[j][0])
                    idx_chunk += 1
                    n2i_keys.add(i2ni[j][0])

            # Each element is a metagenome
            x.append(x_in_contig)
            yext.append(np.array(y_in_contig))

            shift = len(i2n_all)

    if mode == 'edit':
        y = 100 * np.array(ye)
    elif mode == 'extensive':
        y = yext
    else:
        raise("Mode currently not supported")
    
    return x, y, i2n_all


def kfold(x, y, idx_lo, k=5):
    """Creating folds for k-fold validation
    k : number of folds
    """
    # check data
    if len(x) < k:
        msg = 'Number of metagenomes is < n-folds: {} < {}'
        raise IOError(msg.format(len(x), k))
    
    # Define validation data
    x_tr, y_tr = [], []
    x_val, y_val = [], []

    # setting fold lower & upper
    meta_per_fold = int(len(x) / k)
    lower = idx_lo * meta_per_fold
    upper = (idx_lo + 1) * meta_per_fold

    # creating folds
    for i, xi in enumerate(x):
        if i < lower or i >= upper: # idx_lo:
            x_tr = x_tr + xi
            y_tr.append(y[i])
        else:
            x_val = x_val + xi
            y_val.append(y[i])

    y_tr = np.concatenate(y_tr)
    y_val = np.concatenate(y_val)

    return x_tr, x_val, y_tr, y_val

def pickle_data_b(features_in, features_out): 
    """
    One time function parsing the csv file and dumping the 
    values of interest into a pickle file. 
    """

    msg = 'Pickling feature data: {} => {}'
    logging.info(msg.format(features_in, features_out))

    feat_contig, target_contig = [], []
    name_to_id = {}

    # Dictionary for one-hot encoding
    letter_idx = defaultdict(int)
    # Idx of letter in feature vector
    idx_tmp = [('A',1) , ('C',2), ('T',3), ('G',4)]

    for k, v in idx_tmp:
        letter_idx[k] = v

    idx = 0
    #Read tsv and process features
    if features_in.endswith('.gz'):
        _open = lambda x: gzip.open(x, 'rt')
    else:
        _open = lambda x: open(x, 'r')
        
    
    with _open(features_in) as f:
        # load
        tsv = csv.reader(f, delimiter='\t')
        col_names = next(tsv)
        # indexing
        w_ext = col_names.index('Extensive_misassembly')
        w_chimera = col_names.index('chimeric')
        # formatting rows
        for row in tsv:
            name_contig = row[0]

            # If name not in set, add previous contig and target to dataset
            if name_contig not in name_to_id:
                if idx != 0:
                    feat_contig.append(np.concatenate(feat, 0))
                    target_contig.append(float(tgt))

                feat = []
               
                #Set target
                tgt = row[w_ext]
                if tgt == '':
                    tgt = 0
                else:
                    tgt = 1

                name_to_id[name_contig] = idx
                idx += 1

            # Feature vec
            feat.append(np.array(5 * [0] + [int(ri) for ri in row[4:(w_chimera - 2)]])[None, :].astype(np.uint8))
            feat[-1][0][letter_idx[row[3]]] = 1

    # Append last
    feat_contig.append(np.concatenate(feat, 0))
    target_contig.append(float(tgt))

    assert(len(feat_contig) == len(name_to_id))

    # Save processed data into pickle file
    with open(features_out, 'wb') as f:
        pickle.dump([feat_contig, target_contig, name_to_id], f)
    return features_out


def pickle_data_feat_only(data_path, features_in, features_out):
    """
    One time function parsing the csv file and dumping the 
    values of interest into a pickle file. 

    No target info, only features (for test without ground truth)
    """
    feat_contig = []
    name_to_id = {}

    # Dictionary for one-hot encoding
    letter_idx = defaultdict(int)
    # Idx of letter in feature vector
    idx_tmp = [('A',1) , ('C',2), ('T',3), ('G',4)]

    for k, v in idx_tmp:
        letter_idx[k] = v

    idx = 0
    #Read tsv and process features
    with gzip.open(os.path.join(data_path, features_in), 'rt') as f:

        tsv = csv.reader(f, delimiter='\t')
        col_names = next(tsv)

        w_sec = col_names.index('num_secondary')

        for row in tsv:
            name_contig = row[1]

            # If name not in set, add previous contig and target to dataset
            if name_contig not in name_to_id:
                if idx != 0:
                    feat_contig.append(np.concatenate(feat, 0))

                feat = []
                name_to_id[name_contig] = idx
                idx += 1

            # Feature vec
            feat.append(np.array(5 * [0] + [int(ri) for ri in row[4:(w_sec - 1)]])[None, :].astype(np.uint8))
            feat[-1][0][letter_idx[row[3]]] = 1

    # Append last
    feat_contig.append(np.concatenate(feat, 0))

    assert(len(feat_contig) == len(name_to_id))

    # Save processed data into pickle file
    with open(os.path.join(data_path, features_out), 'wb') as f:
        pickle.dump([feat_contig, name_to_id], f)

def class_recall(label):
    """
    Custom metric for Keras, computes recall per class. 

    Inputs:
        label: label wrt which recall is to be computed. 
    """
    def metr(y_true, y_pred):
        class_id_preds = K.cast(K.greater(y_pred, 0.5), 'int32')
        y_true = K.cast(y_true, 'int32')
        accuracy_mask = K.cast(K.equal(y_true, label), 'int32')
        class_acc_tensor = K.cast(K.equal(y_true, class_id_preds), 'int32') * accuracy_mask
        class_acc = K.sum(class_acc_tensor) / K.maximum(K.sum(accuracy_mask), 1)
        return class_acc
    return metr

def explained_var(y_true, y_pred):
    """
    Custom metric for Keras, explained variance.  
    """
    return 1  - K.mean((y_true - y_pred) ** 2) / K.var(y_true)

def reverse_dict(d):
    """Flip keys and values
    """
    r_d = {}
    for k, v in d.items():
        if v not in r_d:
            r_d[v] = [k]
        else:
            r_d[v].append(k)
    return r_d


def compute_predictions(n2i, generator, model, save_path):
    """
    Computes predictions for a model and generator, aggregating scores for long contigs.

    Inputs: 
        n2i: dictionary with contig_name -> list of idx corresponding to that contig.
        generator: deepmased data generator
    Output:
        scores: scores for individual contigs
    """

    score_val = model.predict_generator(generator)

    # Compute predictions by aggregating scores for longer contigs
    score_val = score_val.flatten()
    scores = {}

    outfile = os.path.join(save_path, 'predictions.csv')
    write = open(outfile, 'w')
    csv_writer = csv.writer(write, delimiter='\t')
    csv_writer.writerow(['MAG', 'Contig', 'Deepmased score'])
    
    for k in n2i:
        inf = n2i[k][0]
        sup = n2i[k][-1] + 1
        if k[0] not in scores:
            scores[k[0]] = {}
       
        # Make sure contig doesnt appear more than once
        assert(k[1] not in scores[k[0]])

        # Make sure we have predictions for these indices
        if sup > len(score_val):
            continue

        # Make sure all the labels for the contig coincide
        #scores[k[0]][k[1]] = {'pred' : score_val[inf : sup]}
        csv_writer.writerow([k[0], k[1], str(np.mean(score_val[inf : sup]))])
    
    write.close()
    logging.info('File written: {}'.format(outfile))
    #return scores


