"""Opt-in persistent geometric support and actual native projected scoring."""

import numpy as np
from scipy.optimize import minimize

from src.solvers.neural_wave_moments import Patch


class EvaluationLimit(Exception):
    pass


def clip_wave_q(q, k0):
    if not np.isfinite(k0) or k0 <= 0:
        raise ValueError("POSITIVE_PHYSICAL_K0_REQUIRED")
    return np.clip(q, -4*k0, 4*k0)


def bounded_direction_optimize(
    objective, q0, seed_value, bound, maxiter=12, maxeval=18, denominator=1.0
):
    """Keep the best *evaluated* complete proposal; never evaluate result.x again."""
    calls, best = [], [np.array(q0, copy=True), seed_value]

    def evaluate(flat):
        if len(calls) >= maxeval:
            raise EvaluationLimit
        q = flat.reshape(q0.shape)
        value = objective(q)
        calls.append(
            dict(
                score=value[0],
                gradient_norm=float(np.linalg.norm(value[4])),
                q=q.tolist(),
            )
        )
        if value[0] >= best[1][0]:
            best[:] = [q.copy(), value]
        return -value[0] / denominator, -value[4].ravel()

    status, message = -1, "ACTUAL_EVALUATION_LIMIT"
    try:
        result = minimize(
            evaluate,
            q0.ravel(),
            jac=True,
            method="L-BFGS-B",
            bounds=[(-bound, bound)] * q0.size,
            options=dict(
                maxiter=maxiter,
                maxfun=maxeval,
                maxls=12,
                ftol=1e-12,
                gtol=1e-10,
                maxcor=10,
            ),
        )
        status, message = int(result.status), str(result.message)
    except EvaluationLimit:
        pass
    return (
        best[0],
        best[1],
        dict(
            executed=True,
            function_calls=len(calls),
            actual_evaluation_limit=maxeval,
            scipy_status=status,
            messages=message,
            initial_gradient_norm=calls[0]["gradient_norm"] if calls else 0.0,
            final_gradient_norm=calls[-1]["gradient_norm"] if calls else 0.0,
            last_trial=calls[-1] if calls else None,
            evaluated_trajectory=calls,
            extra_result_evaluation_count=0,
        ),
    )


class MultiscaleSupportPolicy:
    def __init__(self, geometry, moments):
        from src.solvers.neural_wave_greedy import patch_inventory

        bounds = np.array(geometry["bounds_nm"])
        self.global_patch = Patch(
            tuple(bounds.mean(1)),
            tuple(bounds[:, 1] - bounds[:, 0]),
            level=-1,
            kind="global",
        )
        self.pools = [patch_inventory(geometry, level) for level in range(3)]
        self.rows = {
            p: np.unique(
                moments.rows[moments.cells(p)][moments.rows[moments.cells(p)] >= 0]
            )
            for pool in self.pools
            for p in pool
        }
        self.rotation = [p for pool in self.pools for p in pool if len(self.rows[p])]
        self.ports = [p for p in self.rotation if p.center[2] in bounds[2]]

    def preselect(self, sensitivity, iteration):
        result = [self.global_patch]
        records = []
        for level, count in enumerate((2, 1, 2)):
            scores = [
                (
                    float(
                        np.vdot(
                            sensitivity[self.rows[p]], sensitivity[self.rows[p]]
                        ).real
                    )
                    / len(self.rows[p]),
                    i,
                    p,
                )
                for i, p in enumerate(self.pools[level])
                if len(self.rows[p])
            ]
            scores.sort(key=lambda item: (-item[0], item[1]))
            result.extend(v[2] for v in scores[:count])
            records.extend(
                dict(level=level, index=i, score=s) for s, i, _ in scores[:count]
            )
        rotation = self.rotation[iteration % len(self.rotation)]
        port = self.ports[iteration % len(self.ports)]
        result.extend((rotation, port))
        result = list(dict.fromkeys(result))
        for p in (
            self.rotation[iteration % len(self.rotation) :]
            + self.rotation[: iteration % len(self.rotation)]
        ):
            if len(result) == 8:
                break
            if p not in result:
                result.append(p)
        return result, rotation, records

    def select(
        self,
        action,
        space,
        moments,
        dictionary,
        width,
        iteration,
        resolution_step,
        screen_seeds=8,
        k0=2 * np.pi / 5.0,
    ):
        from src.solvers.neural_wave_greedy import variable_projection

        sensitivity = action.apply(space.r, adjoint=True)
        patches, forced, preselection = self.preselect(sensitivity, iteration)
        # First eight proposals are global physical seeds, identical for both routes.
        start = 1 + (len(dictionary) - 1) // 4
        physical = list(range(start, start + 7)) + [0]
        if iteration < 8:
            patches = [self.global_patch]
        preliminary = []
        for index, p in enumerate(patches):
            q = dictionary[
                [
                    physical[iteration]
                    if iteration < 8
                    else (iteration * screen_seeds) % len(dictionary)
                ]
            ]
            try:
                value = variable_projection(
                    action, space, moments, p, q, gradient=False
                )
                preliminary.append((value[0], index, p))
            except ValueError as error:
                if str(error) != "DEGENERATE_NEW_DIRECTION":
                    raise
        preliminary.sort(key=lambda item: (-item[0], item[1]))
        finalists = [v[2] for v in preliminary[:2]]
        mandatory = (iteration + 1) % 8 == 0 and iteration >= 8
        if mandatory and forced not in finalists:
            finalists = finalists[:1] + [forced]
        all_candidates = []
        for p in finalists:
            candidates = []
            seeds = (
                [dictionary[[physical[iteration]]]]
                if iteration < 8
                else [
                    dictionary[
                        (iteration * screen_seeds + j + np.arange(width) * 7)
                        % len(dictionary)
                    ].copy()
                    for j in range(screen_seeds)
                ]
            )
            for q in seeds:
                try:
                    v = variable_projection(
                        action, space, moments, p, q, gradient=False
                    )
                    candidates.append((v[0], q, v))
                except ValueError as error:
                    if str(error) != "DEGENERATE_NEW_DIRECTION":
                        raise
            if candidates and iteration >= 8:
                base = max(candidates, key=lambda v: v[0])[1]
                for axis in range(3):
                    for sign in (-1, 1):
                        q = base.copy()
                        q[:, axis] += sign * resolution_step
                        q = clip_wave_q(q, k0)
                        try:
                            v = variable_projection(
                                action, space, moments, p, q, gradient=False
                            )
                            candidates.append((v[0], q, v))
                        except ValueError as error:
                            if str(error) != "DEGENERATE_NEW_DIRECTION":
                                raise
            if candidates:
                all_candidates.append(
                    (max(candidates, key=lambda v: v[0])[0], p, candidates)
                )
        if not all_candidates:
            raise ValueError("DEGENERATE_NEW_DIRECTION")
        _, patch, candidates = max(all_candidates, key=lambda v: v[0])
        from dataclasses import asdict

        return (
            patch,
            candidates,
            dict(
                preselection=preselection,
                preliminary=[dict(patch=asdict(p), score=s) for s, _, p in preliminary],
                fully_scored=[asdict(p) for p in finalists],
                forced_rotation_fully_scored=mandatory,
                selected=asdict(patch),
                original_projected_score=max(candidates, key=lambda v: v[0])[0],
            ),
        )
