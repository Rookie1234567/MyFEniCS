# Task033 环境与基线

> 阶段更新（2026-07-17）：正式高阶运行绑定 clean source
> `6613f94b91ebc77eb50e74086475c67df46236f6` 与镜像 digest
> `sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d`。
> Phase A tracking/MPI 复测绑定 clean source
> `bb830ba5dd74ced30475402bd6bc6d3c1856c630`；数值装配与求解器相对 Case090 source
> 未变化，并通过严格的 non-numerical descendant audit 复用 Case090。
> Case090 与 QEP 分片已完成；完整 campaign 在 Hybrid `p1/h3/M160`
> middle-plane reconstruction 时因用户缩小范围终止，不是资源或数值崩溃。
>
> Phase B matching-trace 五条 shard 绑定 clean source
> `bd7a6023bde7a7c06d456e702af4b7f9f047b3fc`；独立聚合器绑定 clean source
> `9ac29db45b387d4590de084710abe2cc38b25ffe`。镜像 digest 与上文一致。

## 1. 执行身份

| 字段 | 值 | 单位 / baseline | 数据身份 | 证据 |
|---|---|---|---|---|
| Task | `Task033` | task identity | measured | `../task.md` |
| repository | `C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal` | local checkout | measured | `git rev-parse --show-toplevel` |
| Task032 selective-merge SHA | `77d8bdb81428ceeefa623b6fbfe546408641cf47` | required predecessor | measured | `git show -s 77d8bdb...` |
| Task033 base SHA | `ad4046d7f4a360f2b160b9c196e2f7b8990ac135` | `master` / `origin/master` | measured | `git rev-parse HEAD` |
| selective merge is base ancestor | `true` | ancestry relation | measured | `git merge-base --is-ancestor` |
| current branch | `codex/20260715-task33-high-order-floquet-hybrid-hp` | Task033 execution branch | measured | `git branch --show-current` |
| Phase A source SHA | `bb830ba5dd74ced30475402bd6bc6d3c1856c630` | clean selected-QEP execution source | measured | watchdog source gate |
| Phase B measurement SHA | `bd7a6023bde7a7c06d456e702af4b7f9f047b3fc` | clean matching-trace execution source | measured | five shard source gates |
| Phase B aggregate SHA | `9ac29db45b387d4590de084710abe2cc38b25ffe` | clean fail-closed aggregate source | measured | aggregate tool identity |
| local `master` | `ad4046d7f4a360f2b160b9c196e2f7b8990ac135` | branch tip | measured | `git rev-parse master` |
| `origin/master` | `ad4046d7f4a360f2b160b9c196e2f7b8990ac135` | remote-tracking tip | measured | `git rev-parse origin/master` |
| origin fetch/push | `https://github.com/Rookie1234567/MyFEniCS` | remote URL | measured | `git remote -v` |
| pre-edit worktree | `clean=true` | before Task033 outcomes were created | measured | empty `git status --short` output |
| ordinary default changed | `false` | Task032 / Task033 contract | planned constraint | `../task.md` |
| query window | `2026-07-15 17:44–17:47 +08:00` | Asia/Shanghai | measured | PowerShell `Get-Date` |

The clean attestation above applies to the Task033 base before this outcomes directory was
created. It is not a clean-source attestation for future numerical records. Each formal
record must independently capture its source SHA and require a clean tracked worktree.

## 2. Docker image and numerical stack

| 字段 | 值 | 单位 / baseline | 数据身份 | 证据 |
|---|---|---|---|---|
| image tag | `myfenics-stage4:task28` | qualified local image | measured | `docker image inspect` |
| image ID | `sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d` | content identity | measured | `docker image inspect` |
| RepoDigest | `myfenics-stage4@sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d` | immutable image identity | measured | `docker image inspect` |
| image platform | `linux/amd64` | container platform | measured | `docker image inspect` |
| Docker client/server | `29.5.2 / 29.5.2` | version | measured | `docker version` |
| Docker OS/kernel | `Docker Desktop / 6.6.114.1-microsoft-standard-WSL2` | runtime | measured | `docker info` |
| Python | `3.12.3` | container interpreter | measured | read-only container probe |
| NumPy | `2.2.6` | package version | measured | read-only container probe |
| PETSc / petsc4py | `3.24.0 / 3.24.0` | package version | measured | `PETSc.Sys.getVersion()` |
| SLEPc / slepc4py | `3.24.0 / 3.24.0` | package version | measured | `SLEPc.Sys.getVersion()` |
| DOLFINx | `0.10.0.post2` | package version | measured | `dolfinx.__version__` |
| Basix | `0.10.0` | package version | measured | `basix.__version__` |
| PETSc scalar class | `numpy.complex128` | scalar type | measured | `PETSc.ScalarType` |
| PETSc scalar dtype | `complex128` | scalar dtype | measured | `numpy.dtype(PETSc.ScalarType).name` |

The package probe used a temporary `--read-only` container and did not mount or modify the
repository.

## 3. Memory envelope

| 字段 | 值 | 单位 / baseline | 数据身份 | 证据 |
|---|---:|---|---|---|
| host visible physical memory | 15.584 | GiB | measured | `Win32_OperatingSystem.TotalVisibleMemorySize` |
| host free physical memory at query | 1.811 | GiB | measured snapshot | `Win32_OperatingSystem.FreePhysicalMemory` |
| Task033 nominal hard budget | 14.000 | GiB | task policy | `../task.md` |
| Docker Engine `MemTotal` | 13.6485 | GiB | measured | `docker info .MemTotal` |
| container `memory.max` | `max` | cgroup v2 | measured | read-only container probe |
| effective container upper bound | 13.6485 | GiB; minimum of available numeric limits | derived | Docker Engine `MemTotal`; cgroup reports no tighter numeric cap |
| effective center/warning threshold | 11.2113 | GiB; scaled from `11.5 / 14.0` | derived | Task033 ratio applied to 13.6485 GiB |
| effective conservative-upper threshold | 12.4786 | GiB; scaled from `12.8 / 14.0` | derived | Task033 ratio applied to 13.6485 GiB |
| effective controlled-termination threshold | 12.6736 | GiB; scaled from `13.0 / 14.0` | derived | Task033 ratio applied to 13.6485 GiB |

Because the effective Docker memory ceiling is below 14 GiB, Task033 must use the tighter
derived thresholds above. The low host-free-memory snapshot is also a launch veto for a
large case: every launch must refresh host available memory, Docker/cgroup state and swap
state immediately before execution. No large numerical case was launched during Phase 0.

## 4. Phase 0 历史快照（正式 source freeze 之前）

下表保留 `ad4046d...` 时点的执行前状态；其中 `not_run` 不代表 2026-07-17 的
最终 runtime 状态。

| Gate | 状态 | 数据身份 | 证据 / 后续动作 |
|---|---|---|---|
| Review V2 permits Task033 | pass | measured document audit | `../../task032_hybrid_fem_modal_direct_baseline/review_report_v2.md` |
| selective merge present in base ancestry | pass | measured Git relation | `77d8bdb...` is an ancestor of `ad4046d...` |
| Task033 branch starts at clean `origin/master` | pass | measured pre-edit | branch/base table above |
| complex PETSc environment | pass | measured runtime probe | `complex128` |
| effective memory limit recorded | pass | measured + derived | 13.6485 GiB effective upper bound |
| master lightweight regression | not_run | not_run | execution owner must record the exact test set |
| Case080 checker on Task033 base | not_run | not_run | execution owner must run before Phase 0 is closed |
| final tracked-source-clean record | not_run | not_run | required separately before each formal benchmark |
| large-case memory preflight | not_run | not_run | refresh immediately before any launch |

## 5. 当前正式阶段状态

| Gate | 当前状态 | 证据 |
|---|---|---|
| tracked-source clean | pass | `6613f94b91ebc77eb50e74086475c67df46236f6` |
| Case090 | 144 PDE complete；all core gates pass | stage summary + ignored aggregate hash |
| QEP MPI1 | 36/36 measured shards pass | stage summary + ignored watchdog index hash |
| Phase B matched trace | p2 MPI1、p3/p4 MPI1/MPI4 共 5 条 pass | tracked Phase B aggregate + raw shard SHA256 |
| Phase C target full3D/Hybrid | not started | wait for Phase B review |
| swap/watchdog | zero swap；authority readable | retained watchdog summaries |
| campaign stop | user scope reduction at p1/h3/M160 middle-plane reconstruction | `summary.md`；not a formal solver record |
