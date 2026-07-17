# Model and Dataset Provenance

```text
dataset schema = myfenics.neural_local_pc.dataset.v1
checkpoint schema = myfenics.neural_local_pc.v1
seed = 20260717
validation seed = 20260718
operator fingerprint = 7db8f8bd7e82b3ec495314a73243997a87ca627a485827df79587ce6b3713184
checkpoint SHA-256 = 6cec9065c52665176f0314f336adf0138d53050a812f882e95d056b745c28e7a
backend = PyTorch 2.7.1+cu118 / cuda:0
runtime export = frozen NumPy POD-MLP
online training = false
qualification = synthetic_smoke_only
```

The dataset, CSR arrays, checkpoint and profiler data are under `benchmarks/artifacts/cases/090/toy_smoke/` and intentionally ignored by Git. The checksum is recorded only to make the local artifact auditable; it is not a production checkpoint.

## Real h5 slab-9 candidate

```text
training operator fingerprint = 0fe7e9f597345f6a10bd924ebc43e15198815e151654173c0659d7dbf0306784
checkpoint SHA-256 = 5ae59f8cfea869ecd49ccba285fc9fbb24eda04e5a2e02680f34c5c71c6a9d6a
dataset samples = 480 (384 train / 96 validation)
real train-run samples = 128 RHS + 128 ILU residual
independent validation-run samples = 32 RHS + 32 ILU residual
POD rank / hidden / epochs = 256 / 512 / 1000
input/output POD energy = 0.968459 / 0.998762
training time = 8.987873 s on cuda:0
runtime model bytes = 45,094,912
qualification = research_only_engineering_negative
```

The primary and independent captures use different h5 executions and strides. Only slabs whose operator fingerprints matched exactly across runs were eligible; representative slabs 0, 9 and 15 were exported. Slab 9 alone was trained and run because its Lane-B validation passed. All heavy artifacts remain Git-ignored.
