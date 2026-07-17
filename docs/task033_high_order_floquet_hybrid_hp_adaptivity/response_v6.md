# 对 `review_report_v5.md` 的回复

## 总体处置

接受 Review V5 的证据边界和直接执行顺序。D0、D1、D2 已全部完成，随后停止数值
campaign：

```text
D0 evidence/document convergence = completed
D1 p3/h10 = negative_not_equal_accuracy
D1 conditional p3/h7.5 = equal_accuracy_engineering_positive_with_qualification
D2 native variable-p H(curl) = not_qualified_fail_closed
h adaptivity = not started; waits for new review
whole original Task33 = partial
whole branch merge = not yet approved
```

没有运行 `M240`、`p3/h3`、p4 target、adaptive、buffer 或 0.7 nm PDE。

## D0：口径与来源兼容性

- 历史 `phaseC_summary.json` 已加 superseded 身份，当前结论由同阶
  `full3d_closure_summary.json` 管理；
- `hybrid_vs_full3d_summary.md` 不再把旧 p3 C0 否决写成当前状态；
- pure-3D full3D 与 Hybrid Phase6 的数值源兼容性已做 fail-closed 审计：
  12 个 numerical-kernel blob 完全一致，Phase6 规范化 AST 一致；
- `uniform_p_h_matrix.csv` 已减缩为有决策价值的行；
- selective merge manifest 已同步，但没有声称整分支获准合并。

## D1：p3 fixed-order 等精度

执行严格遵循 stop ladder。先完成 `p3/h10` C0、direct、Hybrid M120/M160；
它虽然只用 1.980 GiB 完成 direct，但相对 provisional p3/h5 reference 的
R/T/A、体吸收、五平面 E/H、接口 E/H 和逐阶指标全部劣于 p2/h3，因此判为
accuracy negative，并解锁 `p3/h7.5`。

`p3/h7.5` direct 使用 3.667 GiB、零 swap，true residual `6.449e-12`。
其所有规定物理误差均不劣于 p2/h3。Hybrid M120/M160 均通过 16 项 Gate，
M120→M160 已收敛；M160 相对同网格 direct 的 R/T/A 差不超过 `1.264e-6`。

以 p2/h3 Hybrid M160 为 baseline，p3/h7.5 M160：

| FE DoF | local-system rows | total rows | factor-inventory NNZ | memory | time |
|---:|---:|---:|---:|---:|---:|
| 2.571x | 2.567x | 2.548x | 3.557x | 1.606x | 1.331x |

因此结论是带资格的工程正信号。资格条件保持不变：p3/h5 是最佳可用离散参考，
不是连续解，也未网格收敛；结论不外推到一般几何、p4、0.7 nm 或 arbitrary p/h。

`p3/h10` 的 Hybrid M120/M160 只有 sampled interface H Gate 未过，且 M 增加后
不改善。这不是继续 M240 的理由；其 direct 等精度已经失败，按审阅规则终止。

## D2：variable-p / hp

在冻结 Docker 环境直接审计了 DOLFINx/Basix/UFL 版本和公开 API。mixed element、
submesh、mixed-topology form 均存在，但它们不证明 cellwise variable-degree
Nédélec 的切向连续、周期 p 同步、orientation、trace 或 MPI ownership。

因此按 Review V5 fail closed：

- 不实现 bespoke unequal-p constraint/mortar；
- 不启动 target-scale variable-p PDE；
- 因没有原生可靠路线，不触发 p2/p3 microfixture；
- 只提交 fixed-p subdomain zoning 设计和未来重启条件。

该负结论只适用于当前冻结环境和现有证据，不宣称未来 DOLFINx/Basix 永远不能支持。

## 全任务回顾与后续

新增 `outcomes/task33_completion_matrix.md`，逐项对账原 task Phase 0–8、最终 14 个
问题、全部 Task33 review/response/outcomes 文档，并明确：

- 已完成：高阶 Floquet、p3/p4 QEP/trace、p3/h5 closure、p4 resource gate、
  Review V5 D0/D1/D2；
- 暂不完成：p2 h-adaptive、variable-p target prototype、interface buffer、
  更新后的 1 TiB/0.7 nm 推演、21-role formal manifest；
- 当前 Task034 只能把 p3/h7.5、M160、10/110 nm 当作 current-scale provisional
  candidate，不能称最终离散。

下一步不应继续自动计算。按 Review V5，先复审 D1/D2 summary；只有新的明确批准
才能启动最后的 p2 conforming graded-h / h-adaptive 阶段。buffer 等待 defect
geometry，p4 等待更大资源或合格低内存算法，1 TiB 推演等待 measured adaptive
compression。
