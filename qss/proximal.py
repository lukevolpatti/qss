from tracemalloc import start
import numpy as np

# Separable functions // proximal operator:
# 0: f(x) = 0 // prox(v) = v
# 1: f(x) = |x| // prox(v) = prox(v) = S_{1/rho}(v)

# f(x) = 0
def g_zero(v):
    return 0


def prox_zero(rho, v):
    return v


# f(x) = |x|
def g_abs(v):
    return np.abs(v)


def prox_abs(rho, v):
    return np.maximum(v - 1 / rho, 0) - np.maximum(-v - 1 / rho, 0)


# f(x) = I(x >= 0)
def g_indge0(v):
    valid = np.all(v >= 0)
    if valid:
        return 0
    else:
        return np.inf


def prox_indge0(rho, v):
    y = v
    y[np.where(v < 0)] = 0
    return y


# f(x) = I(0 <= x <= 1)
def g_indbox01(v):
    valid = np.all(np.logical_and(v >= 0, v <= 1))
    if valid:
        return 0
    else:
        return np.inf


def prox_indbox01(rho, v):
    v[v >= 1] = 1
    v[v <= 0] = 0
    return v


# f(x) = I(x == 0)
def g_is_zero(v):
    valid = np.all(v == 0)
    if valid:
        return 0
    else:
        return np.inf


def prox_is_zero(rho, v):
    return np.zeros(len(v))


g_funcs = {
    "zero": g_zero,
    "abs": g_abs,
    "indge0": g_indge0,
    "indbox01": g_indbox01,
    "is_zero": g_is_zero,
}

prox_ops = {
    "zero": prox_zero,
    "abs": prox_abs,
    "indge0": prox_indge0,
    "indbox01": prox_indbox01,
    "is_zero": prox_is_zero,
}


def apply_g_funcs(g_list, x):
    y = np.zeros(len(x))
    for g in g_list:
        func_name = g["g"]
        if "args" in g and "weight" in g["args"]:
            weight = g["args"]["weight"]
        else:
            weight = 1
        if "args" in g and "scale" in g["args"]:
            scale = g["args"]["scale"]
        else:
            scale = 1
        if "args" in g and "shift" in g["args"]:
            shift = g["args"]["shift"]
        else:
            shift = 0
        start_index, end_index = g["range"]

        func = g_funcs[func_name]
        y[start_index:end_index] = weight * func(
            scale * x[start_index:end_index] - shift
        )
    return np.sum(y)


def apply_prox_ops(rho, equil_scaling, g_list, x):
    for g in g_list:
        prox_op_name = g["g"]
        if "args" in g and "weight" in g["args"]:
            weight = g["args"]["weight"]
        else:
            weight = 1
        if "args" in g and "scale" in g["args"]:
            scale = g["args"]["scale"]
        else:
            scale = 1
        if "args" in g and "shift" in g["args"]:
            shift = g["args"]["shift"]
        else:
            shift = 0
        start_index, end_index = g["range"]

        new_scale = equil_scaling[start_index:end_index] * scale
        new_rho = rho / (weight * new_scale**2)

        prox = prox_ops[prox_op_name]
        x[start_index:end_index] = (
            prox(new_rho, new_scale * x[start_index:end_index] - shift) + shift
        ) / new_scale
    return x


def get_subdifferential(g_list, x, target):
    output = np.zeros(len(x))
    for g in g_list:
        func_name = g["g"]
        start_index, end_index = g["range"]
        if func_name == "abs":
            for i in range(start_index, end_index):
                if x[i] == 0:
                    if target[i] > 1:
                        output[i] = -1
                    elif target[i] < -1:
                        output[i] = 1
                    else:
                        output[i] = -target[i]
                elif x[i] > 0:
                    output[i] = 1
                elif x[i] < 0:
                    output[i] = -1
    # print(output)
    return output
