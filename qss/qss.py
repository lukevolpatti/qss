import numpy as np
import scipy as sp
import qdldl
import time
from qss import precondition
from qss import matrix
from qss import proximal
from qss import polish
from qss import util


class QSS(object):
    def __init__(
        self,
        data,
        eps_abs=1e-4,
        eps_rel=1e-4,
        alpha=1.4,
        rho=0.1,
        max_iter=np.inf,
        precond=True,
        reg=True,
        use_iter_refinement=True,
        polish=False,
        verbose=False,
    ):
        self._data = data
        self._eps_abs = eps_abs
        self._eps_rel = eps_rel
        self._alpha = alpha
        self._rho = rho
        self._max_iter = max_iter
        self._precond = precond
        self._reg = reg
        self._use_iter_refinement = use_iter_refinement
        self._polish = polish
        self._verbose = verbose
        return

    def solve(self):
        P = self._data["P"]
        q = self._data["q"]
        r = self._data["r"]
        A = self._data["A"]
        b = self._data["b"]
        g = self._data["g"]

        alpha = self._alpha
        rho = self._rho

        if self._verbose:
            print(" ----- QSS: the Quadratic-Separable Solver ----- ")
            print(" -----        author: Luke Volpatti        ----- ")
            solve_start_time = time.time()

        dim = P.shape[0]
        constr_dim = A.shape[0]
        has_constr = True if A.nnz != 0 else False
        if not has_constr:
            constr_dim = 0

        xk = np.zeros(dim)
        zk = np.zeros(dim)
        uk = np.zeros(dim)

        xk1 = np.zeros(dim)
        zk1 = np.zeros(dim)
        uk1 = np.zeros(dim)
        nuk1 = np.zeros(dim)

        equil_scaling = np.ones(dim)
        obj_scale = 1

        # Preconditioning
        if self._precond:
            if self._verbose:
                print("### Preconditioning starts ... ###")
                precond_start_time = time.time()
            # We are now solving for xtilde, where x = equil_scaling * xtilde
            P, q, r, A, b, equil_scaling, obj_scale = precondition.ruiz(P, q, r, A, b)
            if self._verbose:
                print(
                    "### Preconditioning finished in {} seconds. ###".format(
                        time.time() - precond_start_time
                    )
                )

        # Constructing KKT matrix
        if has_constr:
            quad_kkt = matrix.build_kkt(P, A, 0, rho, dim, constr_dim)
            quad_kkt_reg = matrix.build_kkt(P, A, -1e-7, rho, dim, constr_dim)
            F = qdldl.Solver(quad_kkt_reg)
        else:
            quad_kkt = P + rho * sp.sparse.identity(dim)
            F = qdldl.Solver(quad_kkt)

        if self._verbose:
            print("--------------------------------------------------------------")
            print(" iter | objective | primal res | dual res |   rho   | time (s) ")
            print("--------------------------------------------------------------")

        # Main loop
        iter_num = 0
        while True:
            iter_num += 1

            # Update x
            if has_constr:
                if self._use_iter_refinement:
                    kkt_solve = matrix.ir_solve(
                        quad_kkt, F, np.concatenate([-q + rho * (zk - uk), b])
                    )
                    xk1 = kkt_solve[:dim]
                    nuk1 = kkt_solve[dim:]
                else:
                    kkt_solve = F.solve(np.concatenate([-q + rho * (zk - uk), b]))
                    xk1 = kkt_solve[:dim]
                    nuk1 = kkt_solve[dim:]
            else:
                xk1 = F.solve(-q + rho * (zk - uk))

            # Update z
            zk1 = proximal.apply_prox_ops(
                rho / obj_scale, equil_scaling, g, alpha * xk1 + (1 - alpha) * zk + uk
            )

            # Update u
            uk1 = uk + alpha * xk1 + (1 - alpha) * zk - zk1

            # Calculate residuals and objective
            r_prim = np.linalg.norm(xk1 - zk1, ord=np.inf)
            r_dual = np.linalg.norm(rho * (zk - zk1), ord=np.inf)
            obj_val = util.evaluate_objective(P, q, r, g, zk1, obj_scale, equil_scaling)

            # Check if we should print current status
            if self._verbose and (
                iter_num == 1 or iter_num == self._max_iter or iter_num % 25 == 0
            ):
                util.print_status(
                    iter_num,
                    obj_val,
                    r_prim,
                    r_dual,
                    rho,
                    solve_start_time,
                )

            # Check if we should stop
            if iter_num == self._max_iter or (
                iter_num % 10 == 0
                and util.evaluate_stop_crit(
                    xk1, zk, zk1, uk1, dim, rho, self._eps_abs, self._eps_rel
                )
            ):
                # Print status of this last iteration if we haven't already
                if self._verbose and (
                    iter_num != self._max_iter and iter_num % 25 != 0
                ):
                    util.print_status(
                        iter_num, obj_val, r_prim, r_dual, rho, solve_start_time
                    )
                if self._verbose:
                    print("--------------------------------------------------------------")
                print("Finished in", iter_num, "iterations")

                # Polishing
                if self._polish:
                    zk1 = polish.polish(
                        g, zk1, P, q, r, A, b, equil_scaling, obj_scale, dim
                    )

                return (
                    util.evaluate_objective(P, q, r, g, zk1, obj_scale, equil_scaling),
                    equil_scaling * zk1,
                )

            # Update rho
            if iter_num % 10 == 0:
                # Add 1e-30 to denominators to avoid divide by zero
                new_rho_candidate = rho * np.sqrt(
                    r_prim
                    / (r_dual + 1e-30)
                    * np.linalg.norm(rho * uk1)
                    / (
                        max(
                            np.linalg.norm(xk1, ord=np.inf),
                            np.linalg.norm(zk1, ord=np.inf),
                        )
                        + 1e-30
                    )
                )

                # This is for the first iteration
                if new_rho_candidate == 0:
                    new_rho_candidate = rho

                # Check if new rho is different enough from old to warrant update
                if new_rho_candidate / rho > 5 or rho / new_rho_candidate > 5:
                    uk1 = uk1 * rho / new_rho_candidate

                    # Update KKT matrix
                    rho_vec = sp.sparse.diags(
                        np.concatenate([rho * np.ones(dim), np.zeros(constr_dim)])
                    )
                    new_rho_vec = sp.sparse.diags(
                        np.concatenate(
                            [new_rho_candidate * np.ones(dim), np.zeros(constr_dim)]
                        )
                    )
                    quad_kkt = quad_kkt - rho_vec + new_rho_vec
                    if has_constr:
                        quad_kkt_reg = quad_kkt_reg - rho_vec + new_rho_vec
                        F.update(quad_kkt_reg)
                    else:
                        F.update(quad_kkt)

                    rho = new_rho_candidate

            xk = xk1
            zk = zk1
            uk = uk1
