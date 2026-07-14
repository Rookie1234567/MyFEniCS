# Task032 新旧目录 smoke 记录

## 1. 最终状态

```text
status = PASS_AFTER_MINIMAL_BASELINE_REPAIR
hybrid_solver_code_started = false
heavy_artifacts_tracked = false
```

## 2. Python compile/import 与 condensation action

在 `myfenics-stage4:task28`、新目录挂载 `/work` 下执行：

```text
python -m compileall -q src benchmarks
import src.solvers.condensed_dtn
import src.solvers.mpc_form_action
import src.solvers.dtn_port_3d
python -m unittest src.test.test_22_condensed_dtn
```

结果：

```text
compile/import = PASS
condensation/action contract = 8 tests passed
```

## 3. 最小 3D Stage4 smoke 与基线修复

原始命令第一次运行在网格生成前失败：

```text
python src/main.py --preset 3d_stage4a_flat_layer_direct
ValueError: Stage-4 grating x bounds must lie inside one periodic cell.
```

根因是 `_STAGE4_FLAT_3D` 把周期改为 `10 x 10 nm`，却遗漏把从普通 Stage4 preset 继承的 `50 x 50 x 50 nm` 光栅块清零。显式传入三个零尺寸后，同一 Stage4 路径完整通过，证明 Docker mount、网格、DtN direct 和 RTA 链正常。

新库内进行最小修复：

```text
src/main.py:
  grating_width_x = 0
  grating_width_y = 0
  grating_height = 0

src/test/test_27_main_preset_contract.py:
  新增 flat preset 不含 grating block 的合同测试
```

修复后：

```text
test_27_main_preset_contract.py = 9 passed, 53 subtests passed
原始 preset 命令 = PASS
FE DoF = 636
direct true relative residual = 1.0778801361351688e-14
R_total = 0.0005938078681733072
T_total = 0.9914679685241553
A_volume_total = 0.007938223607668554
energy closure = -2.7755575615628914e-15
elapsed = 9.015 s
peak RSS = 284.523 MB
```

重型输出：

```text
benchmarks/artifacts/task032_phase0/case020_stage4a_flat_fixed/
```

## 4. 现有 h5 MPI4 target direct

执行：

```text
mpiexec -n 4 python src/main.py \
  --preset 3d_target_grating_direct_h5 \
  --results-root benchmarks/artifacts/task032_phase0/case021_target_h5
```

结果：

```text
status = PASS
FE DoF = 44,698
DtN auxiliary modes = 80
solver = MUMPS direct
iterations = 1
direct true relative residual = 1.3033331305056201e-11
R_total = 0.0890216029364411
T_total = 0.44258827865712663
A_volume_total = 0.46839011840655354
energy closure = 1.212363542890671e-13
elapsed = 23.849 s
simultaneous total peak RSS = 2367.133 MB
```

重型输出：

```text
benchmarks/artifacts/task032_phase0/case021_target_h5/
```

## 5. Gate 判断

```text
new path = PASS
Docker mount = PASS
relative artifact path = PASS
complex PETSc/DOLFINx = PASS
compile/import = PASS
minimum Stage4 = PASS after scoped preset repair
existing direct h5 MPI4 = PASS
condensation/action contract = PASS
git diff --check = PASS
```

因此 Phase 0 迁移 Gate 通过。上述修复属于旧能力恢复，不是 Hybrid solver 实现；Phase 1 可从已记录的 clean reference 设计开始。
