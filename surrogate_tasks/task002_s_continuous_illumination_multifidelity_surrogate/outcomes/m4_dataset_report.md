# M4 compact dataset report — not built by Gate

The production dataset was intentionally not created. Review V5 requires exact
coverage of all 96 training and 16 frozen-validation points, with every sample
passing leakage, ledger, runtime-topology, numerical and resource Gates.

The campaign stopped at training index 40 with:

```text
training measured_pass = 56 / 96
training failed_numerical_gate = 1
training not_run = 39
frozen validation measured_pass = 0 / 16
dataset sample_count = 0
```

The 56 passing records remain immutable diagnostic campaign artifacts but were
not assembled into a partial production dataset. Validation responses were not
generated or inspected. No feature, transform, kernel, model or acquisition
selection occurred.

The formal-record adapter and independent exact-design checker are implemented
and synthetic-tested; they were not used to falsely certify incomplete data.
