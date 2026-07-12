# 3D MUMPS OOC 与 BLR

```bash
python src/main.py --preset 3d_stage4b_grating_mumps_ooc
python src/main.py --preset 3d_stage4b_grating_mumps_blr
```

## 两者是什么

| 档位 | MUMPS 控制 | 目标 | 不是 |
|---|---|---|---|
| OOC | `ICNTL(22)=1` | 把部分因子写到案例目录，降低内存压力 | 迭代法 |
| BLR | `ICNTL(35)=1`, `CNTL(7)=1e-5` | 压缩 frontal block 的直接分解 | “迭代求解器 1” |

OOC 成功后清理临时因子；失败时保留并记录大小。BLR 误差阈值会改变因子近似，必须检查线性真残差和 RTA 差异。二者都是 fallback/诊断 profile，不会自动获得 MPI4 迭代生产资格。

MUMPS 官方用户指南把 BLR 配置归入块低秩直接分解，见 <https://mumps-solver.org/doc/userguide_5.8.2.pdf>。代码映射见 [`../reference/code_walkthrough/30_direct_solver_profiles.md`](../reference/code_walkthrough/30_direct_solver_profiles.md)。

## 何时停止

- OOC 目录增长超出磁盘预算；
- BLR 真残差或 RTA 超过 Gate；
- direct RSS 逼近 WSL 内存上限并大量使用 swap；
- 目标只是生产 h=2，此时改用已限定的 MPI4 迭代入口。
