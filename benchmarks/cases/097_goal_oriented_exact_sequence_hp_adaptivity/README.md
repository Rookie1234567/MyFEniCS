# Case097：保持 exact sequence 的局部 h/p 自适应

## 当前身份

```text
case_id = 097_goal_oriented_exact_sequence_hp_adaptivity
task = Task035d
geometry = Task034 fixed rectangular block grating
ordinary_default_changed = false
```

Case097 是 Task035d 的统一证据入口。当前已建立 Phase A
reference-cell 与小网格 authority；在 A1–A4 完整通过前不运行
`p6/h10` variable-p PDE。

## Phase A 当前能力

- p4/p5/p6 hexahedral N1curl edge、face、cell DoF 目录；
- 通过 `basix.compute_interpolation_operator` 建立低阶到 p6 的真实嵌入，
  不假定数组前缀；
- 逐实体 `edge <= face <= cell` exact-sequence 闭包；
- 配套 Qp 标量空间、离散 gradient、`curl(grad)`、rank/nullity 审计；
- `active --E_K--> p6 local container` 与
  `E_K^H A_K,p6 E_K`；
- active cell-interior static condensation 与 p6 容器 field recovery；
- 单 cell、两共享-face cell、`2×2×2`、serial/MPI2；
- x、y 和双周期实体 orbit、Floquet pullback 与角点闭合；
- inactive p6 模式不获得 global row。

Basix 0.10 的 custom element 对同类实体默认复用第一个实体的
transformation template。因此 heterogeneous edge/face degree 不调用
custom-element `T_apply`；Case097 显式选用每个实体相应 p4/p5/p6
标准元素的 Basix transformation block，并保存审计。

## 证据

```text
records/reference_active_space_authority_v1.json
records/mpi2_fixture_authority_v1.json
records/compact_authority_v1.json
```

前两份记录分别必须由真实 serial 和 MPI2 进程生成。两者都是低成本
reference/topology fixture，不启动 Maxwell PDE。

## 复现

```bash
cd /home/Projects/MyFEniCS
source scripts/activate_myfenics_wsl.sh

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_reference_authority.py \
  --mode serial

mpiexec -n 2 python \
  benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_reference_authority.py \
  --mode mpi2

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_reference_authority.py \
  --mode manifest

python benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/generate_reference_authority.py \
  --mode check
```

后续 Phase B–F 的 p-only、h-only、combined hp、12 通道和资源记录继续放在
本 Case 中，但不得把尚未运行的条目写成通过。
