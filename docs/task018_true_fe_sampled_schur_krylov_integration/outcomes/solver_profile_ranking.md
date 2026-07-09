# Solver Profile Ranking

## Ranking

| rank | profile | final true residual | improvement | cost | decision |
|---:|---|---:|---:|---:|---|
| 1 | `residual_outer_zero` | `1.661623468e-3` | `12.914x` | 3 outer cycles | best solver-like profile |
| 2 | initial correction omega `1.0` + continuation | `1.680968603e-3` | `12.766x` | 200 continuation iterations | stable and simple |
| 3 | `residual_outer_baseline_solution` | `1.698334842e-3` | `12.635x` | 3 outer cycles | stable but slightly weaker |
| 4 | projected residual GMRES + final coarse | `1.708423696e-3` | `12.561x` | 1800 callback counts, 350 s | positive but too expensive |
| 5 | one-shot `top_bottom_y` | `1.732413109e-3` | `12.387x` | 3.0 s selected FE RHS | strong but less solver-like |
| 6 | SciPy LGMRES basis rtol `1e-4` one-shot | `2.428625643e-3` | `8.836x` | 17.8 s | useful but weaker |
| 7 | SciPy GMRES basis rtol `1e-6` one-shot | `2.476434247e-3` | `8.665x` | 181.6 s | more accurate FE RHS, weaker correction |
| 8 | `top_bottom_xy` symmetry basis | `2.506458521e-3` | `8.561x` | 172.9 s | symmetry expansion does not help |
| 9 | BiCGStab basis rtol `1e-4` | `4.291210783e-3` | `5.001x` | not converged | positive but not primary |
| 10 | PETSc selected FE-AMS opt-in | failed | - | error 101 | not stable in same process |

## Interpretation

The useful object is not a right additive PC. The useful object is a low-dimensional residual correction space built from `top_bottom_y` selected FE responses. The strongest practical form is:

```text
repeat:
    run bounded FE-AMS segment
    compute true residual r = b - A x
    solve min_alpha ||r - A Z alpha||
    update x <- x + Z alpha
until stagnation
```

The projected GMRES prototype confirms that using `Z` as an augmentation/projection space is viable, but this first prototype is not worth keeping as the leading profile because it costs much more and gives a slightly worse residual.
