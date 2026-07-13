# 参数扫描与新案例

## 新案例原则

1. 从物理最接近的命名 preset 或 benchmark config 复制，不修改 canonical record。
2. 新建 case label 和独立输出目录。
3. 同时记录几何、材料、波长、角度、偏振、p、h、MPI、边界、求解器和 Git 身份。
4. 首先跑粗网格/Stage 前置验证，再投入 h=2。
5. 任何偏离都标记 `experimental_unqualified`，直到直接法或解析解交叉验证。

## 最小扫描矩阵

| 目的 | 至少变化 |
|---|---|
| 网格收敛 | 三个 h；比较 R/T/A、场积分与 DoF |
| PML 收敛 | 厚度 x alpha，且保持物理区网格可比 |
| DtN 截断 | auto propagation 与更宽诊断集合 |
| 端口位置 | 两个合法 probe/截断面位置 |
| 吸收 | 复折射率、无损极限与体积分闭合 |
| 迭代鲁棒性 | h、角度或材料每次只改一个，并保留三种残差 |

## 研究脚本

- `src/studies/run_2d_euv_validation.py`：2D 网格/厚度/方法扫描。
- `src/studies/run_3d_matrix_scale.py`：装配规模与内存外推；不是完整求解。
- `src/studies/run_3d_memory_profile.py`：子进程树 RSS/swap/OOC 监控。
- `benchmarks/run_workstation_iterative.py`：只用于限定 target case，不应变成任意参数扫描器。

新功能完成后同时补：Theory 公式、Walkthrough 调用链、`benchmarks/cases/` 说明、machine-readable record 和契约测试。
