#This is the final LSTM model with leave-one-site-out cross-validation

from model.model import Model
from preprocess import prepare_df
from sklearn.metrics import r2_score
import torch
import pandas as pd
import argparse
import torch.nn.functional as F
import numpy as np
from plotly import graph_objects as go
import operator



# Parse arguments 
parser = argparse.ArgumentParser(description='CV LSTM')

parser.add_argument('-gpu', '--gpu', default=None, type=str,
                      help='indices of GPU to enable ')

parser.add_argument('-e', '--n_epochs', default=None, type=int,
                      help='number of cv epochs ()')

parser.add_argument('-c', '--conditional',  type=int,
                      help='enable conditioning')

args = parser.parse_args()
DEVICE = torch.device("cuda:" + args.gpu)
torch.manual_seed(40)

#importing data
data = pd.read_csv('utils/df_imputed.csv', index_col=0)
data = data.drop(columns='date')
raw = pd.read_csv('data/df_20210510.csv', index_col=0)['GPP_NT_VUT_REF']
raw = raw[raw.index != 'CN-Cng']

df_sensor, df_meta, df_gpp = prepare_df(data)
sites = raw.index.unique()

INPUT_FEATURES = len(df_sensor[0].columns) 
HIDDEN_DIM = 256
CONDITIONAL_FEATURES = len(df_meta[0].columns)
masks = []
for s in sites:
    mask = raw[raw.index == s].isna().values
    masks.append(list(map(operator.not_, mask)))

cv_r2 = []
sites = []
cv_pred = [[] for s in range(len(df_sensor))]
for s in range(len(df_sensor)):
    #remove the site for testing
    sites_to_train = list(range(len(df_sensor)))
    sites_to_train.remove(s)
    
    #prepare dataframe for training
    x_train = [df_sensor[i].values for i in sites_to_train]
    conditional_train = [df_meta[i].values for i in sites_to_train]
    y_train = [df_gpp[i].values.reshape(-1,1) for i in sites_to_train]

    x_test = df_sensor[s].values 
    conditional_test = df_meta[s].values
    y_test = df_gpp[s].values.reshape(-1,1) 

    #import the model
    model = Model(INPUT_FEATURES, CONDITIONAL_FEATURES, HIDDEN_DIM, args.conditional, 1).to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters())

    r2 = []
    for epoch in range(args.n_epochs):
        train_loss = 0.0
        train_r2 = 0.0
        model.train()
        for (x, y, conditional) in zip(x_train, y_train, conditional_train):
            x = torch.FloatTensor(x).to(DEVICE)
            y = torch.FloatTensor(y).to(DEVICE)
            c = torch.FloatTensor(conditional).to(DEVICE)
            y_pred = model(x, c)
            optimizer.zero_grad()
            loss = F.mse_loss( y_pred, y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
            train_r2 += r2_score(y_true=y.detach().cpu().numpy(), y_pred=y_pred.detach().cpu().numpy())
        
        model.eval()
        with torch.no_grad():
                x = torch.FloatTensor(x_test).to(DEVICE)
                y = torch.FloatTensor(y_test).to(DEVICE)
                c = torch.FloatTensor(conditional_test).to(DEVICE)
                y_pred = model(x, c)
                test_loss = F.mse_loss( y_pred, y)
                test_r2 = r2_score(y_true=y.detach().cpu().numpy()[masks[s]], y_pred=y_pred.detach().cpu().numpy()[masks[s]])
                r2.append(test_r2)
                if test_r2 >= max(r2):
                    cv_pred[s] = y_pred.detach().cpu().numpy().flatten().tolist()
    
    cv_r2.append(max(r2))
    sites.append(df_sensor[s].index[0])
    print(f"Test Site: {df_sensor[s].index[0]} R2: {cv_r2[s]}")
    print("CV R2 cumulative mean: ", np.mean(cv_r2), " +- ", np.std(cv_r2))
    print("-------------------------------------------------------------------")
    
#save the dataframe of the prediction   
d = {"Site": sites, "Predictions": cv_pred}
df = pd.DataFrame(d)
df.to_csv("lstm_simple_predictions.csv")



    
