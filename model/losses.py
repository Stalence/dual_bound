# Loss functions and their associated gradients

import numpy as np
import time

import torch
import torch.nn.functional as F
from torch_geometric.utils import dense_to_sparse, to_dense_adj, to_torch_csr_tensor, to_torch_coo_tensor
from functools import partial

def get_loss_fn(args):
    if args.problem_type == 'max_cut':
        return max_cut_loss
    elif args.problem_type == 'vertex_cover':
        return partial(vertex_cover_loss, penalty = args.vc_penalty)
    elif args.problem_type == 'max_clique':
        return partial(max_clique_loss, penalty = args.vc_penalty)

# X should have shape (N, r)
def max_cut_loss(X, batch):
    # compute loss
    A = to_torch_csr_tensor(batch.edge_index, batch.edge_weight, size=X.shape[0])
    XX = torch.matmul(X, torch.transpose(X, 0, 1))
    obj = torch.trace(torch.matmul(A, XX)) / 2.

    return obj

def vertex_cover_loss(X, batch, penalty=2):
    # taken from maxcut-80/vertex_cover/graph_utils_vc.py::get_obj_vc_new
    #def get_obj_vc_new(graph_params, conv_vc, A, edge_index, interpolate=0.5, **vc_params):
    '''calculates the stanadard relaxed loss with weights.
    Input:
    graph_params
    conv_vc : the nn to be run
    A: Adjacency matrix for vertex cover this is unweighted
    edge_index: 2xE adjacency list for MessagePassing

    Returns:
    obj: loss
    x : the output after application of the nn
    '''
    N = X.shape[0]
    A = to_dense_adj(batch.edge_index, max_num_nodes=N)[0]
    #if torch.is_grad_enabled():
    #    A = to_dense_adj(edge_index, max_num_nodes=N)[0]
    #else:
    #    A = to_torch_coo_tensor(edge_index, size=N)

    # lift adopts e1 = (1,0,...,0) as 1
    # count number of vertices: \sum_{i \in [N]} w_i(1+x_i)/2
    linear = torch.inner(torch.ones(N).to(X.device) + X[:, 0], batch.node_weight) / 2.

    # now calculate penalty for uncovered edges
    # phi is matrix of dimension N by N for error per edge
    # phi_ij = 1 - <x_i + x_j,e_1> + <x_i,x_j> for (i,j) \in Edges
    # phi_ij = <x_i - e1, x_j - e1> for (i, j) \in Edges
    e1 = torch.zeros_like(X) # (num_edges, hidden)
    e1[:, 0] = 1
    Xm = X - e1
    XX = torch.matmul(Xm, torch.transpose(Xm, 0, 1))
    phi_square = A * (XX * XX)

    # XXX the old calculation
    #XX = torch.matmul(X, torch.transpose(X, 0, 1))
    #x_i = X[:, 0].view(-1, 1) # (N, 1)
    #x_j = torch.transpose(x_i, 0, 1) # (1, N)
    #phi = A - A * (x_i + x_j) + A * XX
    #phi_square = phi * phi
    #print("difference:", torch.linalg.matrix_norm(phi_square - phi * phi))

    # division by 2 because phi_square is symmetric and overcounts by 2
    # division by 2 again because constant penalty/2 * phi^2
    augment = penalty * torch.sum(phi_square) / 4.
    # objective is augmented lagrangian
    obj = linear + augment

    return obj

# we are receiving the _complement_ of the target graph
def max_clique_loss(X, batch, penalty=2):
    return vertex_cover_loss(X, batch, penalty=penalty)

def get_score_fn(args):
    if args.problem_type == 'max_cut':
        return max_cut_score
    elif args.problem_type == 'vertex_cover':
        return vertex_cover_score
    elif args.problem_type == 'max_clique':
        return max_clique_score

def max_cut_score(args, X, example):
    # convert numpy array to torch tensor
    if isinstance(X, np.ndarray):
        X = torch.FloatTensor(X)
    if len(X.shape) == 1:
        X = X[:, None]
    N = example.num_nodes
    E = example.edge_index.shape[1]
    return (E - max_cut_loss(X, example)) / 2.

def vertex_cover_score(args, X, example):
    # convert numpy array to torch tensor
    if isinstance(X, np.ndarray):
        X = torch.FloatTensor(X)
    if len(X.shape) == 1:
        X = X[:, None]
    return - vertex_cover_loss(X, example)

# we are receiving the _complement_ of the target graph
# the score is N - k where k is the vertex cover size
def max_clique_score(args, X, example):
    if isinstance(X, np.ndarray):
        X = torch.FloatTensor(X)
    if len(X.shape) == 1:
        X = X[:, None]
    N = example.num_nodes
    return N - vertex_cover_loss(X, example)
