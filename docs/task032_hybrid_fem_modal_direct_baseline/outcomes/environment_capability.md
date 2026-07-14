# Task032 环境能力记录

## 1. 结论

```text
status = PASS
runtime_authority = qualified local Docker image
complex_scalar = PASS
SLEPc PEP = available
SLEPc EPS = available
preferred Task032 eigen route = native PEP / TOAR
```

## 2. 宿主与镜像

```text
host OS = Windows / PowerShell
Docker server = 29.5.2
host Python = 3.13.9 (not the numerical runtime authority)
image = myfenics-stage4:task28
image digest = sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d
image created = 2026-07-12T08:46:56.009717173Z
```

该镜像继续属于 `qualified_local_image`：本机有固定基础镜像，但仓库尚不能在任意 clean machine 上从公开 registry 完整重建。

## 3. 容器数值栈

能力探测实际创建了 SLEPc PEP 和 EPS 对象，并显式选择 TOAR 与 Krylov-Schur：

```text
Python = 3.12.3
NumPy = 2.2.6
DOLFINx = 0.10.0.post2
DOLFINx-MPC import = PASS
Gmsh = 4.15.2
PETSc = 3.24.0
PETSc ScalarType = complex128
SLEPc = 3.24.0
PEP type = toar
EPS type = krylovschur
```

## 4. Task032 决策

Phase 2 的二次传播常数本征问题优先使用原生分布式 SLEPc PEP/TOAR。EPS companion 线性化保留为明确 fallback，不作为第一版默认路线。后续仍必须通过 homogeneous analytic beta、残差、Bloch phase、伪模态过滤和 MPI ownership 测试；“接口可创建”不等于最终 QEP 已资格化。
