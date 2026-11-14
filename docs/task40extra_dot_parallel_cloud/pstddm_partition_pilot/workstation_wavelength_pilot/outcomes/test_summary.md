# 定向测试与只读审核

以下是已经执行的检查，不是未来计划。测试经工作站既有 native complex activation 和受限 user service 执行；没有运行全仓 pytest、MPI2/4 或 GitHub CI。

| source | 检查 | 结果与费用 |
|---|---|---|
| `f1ad2aa51e27aa7ae014cf3a6257da8c1338dffd` | `python -m pytest -q src/test/test_pstddm_workstation_profile.py src/test/test_pstddm_source_transfer.py` | 11 passed、4 subtests passed，pytest 0.87 s；服务父段约2.466 s，不能再与子时间相加。 |
| 同上 | native activation、输入 dry-run、监督器/checker帮助入口 | 完成；服务父段约2.029 s。未将这些视作PDE通过。 |
| `20712b4aa13c5c48aecfdf981ba8fbf97fe26e81` | `python -m pytest -q src/test/test_pstddm_workstation_profile.py -k n2_local_review` | 3 passed、4 deselected，pytest 0.36 s。覆盖缺失历史数组、合格数组与错误数组拒绝。 |
| 同上 | 六场保存数组独立审核 | 各场结果、精确审核进程时间和RSS见 compact；13.5nm N2局部矩阵复算不可用，其余已保存项目仍审核。 |
| 最终文档 | 六组取回manifest/summary/supervision内容hash与原artifact清单一致；JSON可读；文档数值来源核对；`git diff --check` | 完成；未重跑任何PDE。 |

最初13.5nm direct审核的两次activation路径/参数错误，以及N2缺少原pair数组造成的审核失败均留在原attempt JSON。它们不计作PDE重放，不伪补缺失数组。20712b4只增加未来局部数组及计数保存，并让审核对缺失历史证据明确报告限制，未改数值作用。

11项初始测试与后续3项定向测试不是14个全新测试：后续3项在新增审核分支上执行。13.5nm N2定向测试与其审核位于同一约3.085s服务父段，禁止重复计费。其他checker的内部时间不能代替完整service启动成本；无法从现存记录分离的历史准备成本为UNKNOWN。

ABI进口收据SHA256为`280dbdf428d1e85d2ddf792f2f76afbfec7a88e73e21d2d616d4f2c54277b2b9`，实际native Linux、complex128/int32、MPI1/math1；真实路径见[compact](records/compact_v1.json)。不借用Windows/WSL解释器执行正式计算。

## p6 h10编译器接线修复（2026-11-14）

旧失败在已完成凝聚增广装配后、MUMPS symbolic前发生；原`sysconfig.CC`仍含搬迁前WSL路径。修复只为公开PETSc/MUMPS C桥接提供当前资格化prefix内编译器和sysroot，保留旧默认守卫，不改FFCx编译配置、积分、求解控制或资源门。正式runner在FE前加载/核验同一桥接，独立retry保持原h10数学输入。

工作站原ABI下实际2×2 complex128测试完成symbolic、numeric、完整残差及普通KSP对照：残差`2.1593801109342874e-16`，与普通KSP解差0，清理通过，probe内部0.38676974922418594 s；这是API小测试，不是PDE通过。原始`preparation/p6_api_probe/actual_api_result/result.json`。相关7项测试通过（0.102 s），覆盖显式编译器上下文、旧默认、独立retry身份、JIT缓存同数学/ABI/hash与污染拒绝；另实际执行retry dry配置和FE前桥接加载，见`preparation/p6_repair_targeted.log`。不重复全仓测试。失败产生的1048.3153135273606 s费用和原输出保持不变。
