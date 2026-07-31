# Task003 training-only data audit

`dataset_id=task002_m4e_p5_ny4_112_v3`; only the 96 training rows were
materialized. Frozen-validation targets were not opened.

## Input coverage

- shape = [96, 4]; ranges = min `[115.0, 16.0, 0.5, 0.0]`, max `[125.0, 18.0, 10.0, 90.0]`
- unique counts by input = [69, 69, 70, 70]
- feature map is fixed to scaled height/width and in-plane wavevector components.

## Aggregate ranges
- `R_total`: min=1.7356792e-05, max=0.64908451, p50=0.003044131
- `T_total`: min=0.0043293988, max=0.63287364, p50=0.35990753
- `A_balance`: min=0.34508055, max=0.89860707, p50=0.52867195
- `A_volume`: min=0.34508055, max=0.89860707, p50=0.52867195

## Structural null and powers

- power tensor shape = [96, 22, 2]; active entries = 1952 / 4224
- selected primary channels (training max >= 1e-6) = 21
- false mask entries remain NaN/null and are never zero-filled into a loss.
- analytic propagation mask matches all 96 training rows for every fixed order.

## Boundary observations

The training design contains sparse exact corner and cutoff anchors. The
deterministic five-fold CV therefore reports their region metrics separately;
no point was deleted or relabelled to improve a Gate.
