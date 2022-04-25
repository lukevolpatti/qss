import numpy as np
import cvxpy as cp
import scipy as sp
import qss
import time
import pytest
from tests import testutil


def test_l1_trend_filtering_big():
    lmda = 3000

    # set length of signal
    T = int(1e5)
    # set random seed
    np.random.seed(42)
    # construct signal out of 5 segments
    pwl = np.r_[
        np.linspace(0, 3, num=T // 4),
        np.linspace(3, 1.5, num=T // 6),
        np.linspace(1.5, -3, num=T // 6),
        np.linspace(-3, -2.5, num=T // 4),
        np.linspace(-2.5, 0, num=T // 6 + 2),
    ]
    # add Gaussian noise
    y = pwl + 0.2 * np.random.randn(T)

    m1 = sp.sparse.eye(m=T - 2, n=T, k=0)
    m2 = sp.sparse.eye(m=T - 2, n=T, k=1)
    m3 = sp.sparse.eye(m=T - 2, n=T, k=2)
    D = m1 - 2 * m2 + m3

    # CVXPY
    x = cp.Variable(T)
    objective = cp.Minimize(0.5 * cp.sum_squares(y - x) + lmda * cp.norm(D @ x, 1))
    constraints = []
    prob = cp.Problem(objective, constraints)
    t0 = time.time()

    # QSS
    data = {}
    data["P"] = sp.sparse.diags(np.concatenate([np.ones(T), np.zeros(T - 2)]))
    data["q"] = -np.concatenate([y, np.zeros(T - 2)])
    data["r"] = 0.5 * y.T @ y
    data["b"] = np.zeros(T - 2)
    data["g"] = [{"g": "abs", "range": (T, 2 * T - 2)}]
    data["A"] = sp.sparse.hstack([lmda * D, -sp.sparse.identity(T - 2)])
    solver = qss.QSS(data, eps_abs=1e-4, eps_rel=1e-4, alpha=1.8, rho=0.005)

    qss_res = testutil.compare_qss_cvxpy(prob, solver)

    print("Real objective values:")
    print(
        0.5 * np.linalg.norm(y - x.value) ** 2
        + lmda * np.linalg.norm(D @ x.value, ord=1)
    )
    print(
        0.5 * np.linalg.norm(y - qss_res[:T]) ** 2
        + lmda * np.linalg.norm(D @ qss_res[:T], ord=1)
    )


def test_lp_big():
    np.random.seed(1234)
    dim = 100
    constr_dim = 30

    c = 10 * (np.random.rand(dim) - 0.3)
    A = sp.sparse.random(constr_dim, dim, density=0.1, format="csc")
    b = 2 * np.random.rand(constr_dim)

    data = {}
    data["P"] = sp.sparse.csc_matrix((dim + constr_dim, dim + constr_dim))
    data["q"] = np.concatenate([c, np.zeros(constr_dim)])
    data["r"] = 0
    data["A"] = sp.sparse.hstack([A, -sp.sparse.eye(constr_dim)])
    data["b"] = b
    data["g"] = [
        {"g": "indge0", "range": (0, dim)},
        {"g": "indge0", "args": {"scale": -1}, "range": (dim, dim + constr_dim)},
    ]

    # CVXPY
    x = cp.Variable(dim)
    objective = cp.Minimize(c @ x)
    constraints = [A @ x <= b, x >= 0]
    prob = cp.Problem(objective, constraints)

    # QSS
    solver = qss.QSS(data)

    qss_res = testutil.compare_qss_cvxpy(prob, solver)
