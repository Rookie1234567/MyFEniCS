# Stage 2 续接日志

## 2026-06-18 继续定位后的续接点

按用户新规则，普通超时和物理误差不再暂停。本轮继续完成：

```text
1. 串行 3D mesh builder 改为 z 关键平面对齐：
   - physical_z_min
   - interface_z
   - physical_z_max

2. MPI 下暂时使用 create_box fallback：
   - 自定义分布式 z-aligned mesh 在当前 Docker/DOLFINx 栈中会 segfault。
   - fallback 先保证 MPI smoke 能运行。

3. PDE 测试默认参数改为 p2/h300，避免 p1/h700 作为错误验收入口。
```

新增定位结论：

```text
Fresnel serial:
  p2/h150, no PML, no Floquet: R/T = 0.037266/0.940779
  Fresnel 解析 R/T = 0.0337359/0.966264
  说明 2C 串行 Fresnel 有收敛趋势。

Fresnel + Floquet + PML serial:
  p2/h300: R/T = 0.018669/0.935656
  可作为粗网格 smoke，但还不是最终定量验收。

MPI Floquet:
  h900: mismatch 约 1e-15，路径通过。
  h500: mismatch 约 0.57/0.68，物理未通过。
  h300: 5 分钟超时。

PML MPI:
  h900: completed，但 Floquet mismatch 约 0.51，只能算路径 smoke。
```

当前未完成：

```text
1. 提交本轮 mesh/test/doc 更新。
2. 修正 3D MPI Floquet facet pairing/probe transform，使 h500/h300 也可靠。
3. 做 p2/h150 或更细的 Fresnel+PML 定量扫描。
4. 完整 Stage 2 参数扫描。
```

下一步建议：

```text
1. 优先修 MPI Floquet：h500 mismatch 大，说明约束构造在多 facet/多 rank 时不稳。
2. 在 MPI Floquet 修好前，不把 pml_airbox MPI 结果当物理验收。
3. 串行 Fresnel 可以继续 p2/h150、h120 收敛测试，但注意内存。
```

## 2026-06-18 规则更新：只有额度不足才暂停

用户已确认：除非遇到额度不足、工具调用被系统拒绝、或无法继续调用程序，否则不要因为普通失败、超时、误差大而暂停。后续处理规则改为：

```text
物理误差大       -> 继续定位
单个 case 超时   -> 降级网格/缩小 case/改诊断路径后继续
MPI 卡住或超时   -> 先跑更粗 MPI smoke，再定位并行瓶颈
额度不足或执行被拒绝 -> 写续接日志并暂停
```

## 2026-06-18 MPI 超时历史记录

这是规则更新前的历史记录。后续已经继续定位，并补跑了 h900/h500 和 pml_airbox MPI h900。

```text
floquet_airbox normal, MPI 2, p1, h300, direct
mpiexec -n 2 运行超过 5 分钟超时
结果目录只生成 mesh_3d.h5 和 mesh_3d.xdmf
没有 run_summary.json
```

本轮新增实跑结果：

```text
fresnel_interface normal s, p1, h700, serial
  completed，但 R_total/T_total = 0.584166/0.311086
  Fresnel R/T = 0.0337359/0.966264
  判定：2C 路径跑通，物理未通过

fresnel_interface normal p, p1, h700, serial
  completed，但 R_total/T_total = 0.900598/0.286458
  Fresnel R/T = 0.0337359/0.966264
  判定：2C 路径跑通，物理未通过
```

已提交：

```text
e9ea394 Refine 3D stage 2 metrics and comments
815dad0 Add 3D stage 2 test framework
b6629b7 Document 3D stage 2 test plan
62d79f6 Record 3D stage 2 smoke results
```

当前未完成：

```text
1. 修正 3D MPI Floquet h500/h300 的 mismatch/超时问题。
2. 继续串行 Fresnel+PML 更细网格定量扫描。
3. 完整扫描第一轮尚未跑。
```

下一轮建议不要直接继续大扫描，先定位：

```text
1. 先跑 fresnel_interface without PML / without Floquet 的 serial 小算例。
2. 检查 Fresnel total-field 边界是否与材料界面弱式相容。
3. 检查 R/T modal fitting 是否在 PML 或界面附近采样过粗。
4. MPI 先退回 h700 或 h900，确认能出 summary 后再尝试 h300。
```

## 2026-06-18 默认测试后续接点

已完成：

```text
1. Commit e9ea394：Refine 3D stage 2 metrics and comments
2. Commit 815dad0：Add 3D stage 2 test framework
3. Docker complex 环境中 compileall 通过。
4. 默认 unittest 通过：Ran 19 tests, OK, skipped=7。
```

尚未完成：

```text
1. fresnel_interface 物理偏差定位。
2. floquet_airbox MPI 2 h300 超时后的降级 smoke。
3. pml_airbox MPI 2。
4. 完整扫描第一轮。
```

下一轮或下一步优先命令：

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
RUN_STAGE2_PDE_TESTS=1 python3 -m unittest discover -s src/test -p "test_*.py"
```

## 2026-06-18 当前续接点

本轮正在执行综合计划：

```text
Stage 2 收尾
Stage 2 重点代码结构注释
src/test 十层测试框架
notes/test 测试文档
补跑 fresnel_interface、floquet_airbox MPI 2 h300、pml_airbox MPI 2
```

已经完成：

```text
1. 修正 solve_airbox_maxwell_3d.py 的 2B/2C 指标路径：
   - PML reflection proxy 改为数值场上下行波拟合。
   - Fresnel R/T 改为从数值场拟合。
   - power_metrics_3d.json 只在存在数值 R/T 时写出。
   - summary 顶层补充 stage_case、mpi_size、mesh_target_size、nedelec_degree 等字段。

2. 新增 src/test/ 十层测试文件。

3. 新增 notes/test/ 测试说明、验证报告和续接日志。
```

尚未完成：

```text
1. Docker 编译检查。
2. Level 0-3 默认单元测试。
3. PDE 小算例测试。
4. fresnel_interface smoke test。
5. floquet_airbox MPI 2 h300。
6. pml_airbox MPI 2。
7. 回填 stage2_validation_report.md。
8. git commit 分阶段提交。
```

如果额度或 Docker 执行再次中断，下一轮从这里继续：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

然后再补跑 Stage 2 的 Docker/MPI case。
