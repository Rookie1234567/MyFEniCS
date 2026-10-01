# Response V18：GMRES修复及两库残差推进完成，完整资格未通过

执行Review V15全部可做路径：F0合格；两库G64各16周期/G256各8周期；从原V17 GK独立续算R；冻结后一次独立FE审核8状态。严格同离散资格**0/8**，无原方程1e-6通过点、official R/T/A、神经训练增量或目标48小时资格。

| 冻结状态／相同0.7nm micro | R逻辑步 | 原Schur≤1e-6 | 原native≤1e-6 | 独立total-native≤1e-6 | 散射E≤1e-4 | 散射curl≤1e-4 | 完整资格 |
|---|---|---|---|---|---|---|---|
| V17-GPOLY | 6347 | 0.000490220469 | 0.000190109352 | 6.59678284e-05 | 0.000265162174 | 0.0002631196 | FAIL |
| GPOLY-G64-FINAL | — | 0.000342957826 | 0.000133000342 | 4.6151037e-05 | 0.000264299472 | 0.000263170384 | FAIL |
| GPOLY-G256-FINAL | — | 0.000119313169 | 4.6270098e-05 | 1.60556956e-05 | 0.000263932632 | 0.000263799296 | FAIL |
| GPOLY-R-FINAL | 12831 | 0.000146307718 | 5.67386864e-05 | 1.96882894e-05 | 8.07999012e-05 | 7.9819259e-05 | FAIL |
| V17-GNN | 6119 | 0.000594477082 | 0.00023054046 | 7.99973983e-05 | 0.000249203787 | 0.000245918456 | FAIL |
| GNN-G64-FINAL | — | 0.000415112408 | 0.000160982162 | 5.58607113e-05 | 0.000247818583 | 0.00024593027 | FAIL |
| GNN-G256-FINAL | — | 0.000146167412 | 5.6684275e-05 | 1.96694086e-05 | 0.0002455494 | 0.000245237444 | FAIL |
| GNN-R-FINAL | 11903 | 0.000199556375 | 7.73887167e-05 | 2.68538372e-05 | 0.000100199131 | 9.87496399e-05 | FAIL |

G256使原残差下降约75%，散射场变化很小。R的GPOLY散射E/curl已过1e-4，但原Schur1.46307718165e-4与最大通道功率差1.58806402928e-6仍FAIL；GNN-R散射E1.00199130834e-4，不能四舍五入PASS，功率/能量亦FAIL。恢复/端口/identity/slave检查通过，参考实际native1.43744486619e-12保留。选点在读REF7前按原rho冻结为两库G256，验证后没有改选或回训。

GMRES公共close仍返回完整z，caller只切出40port，维数18144/40/18184；真实dat→stage→GMRES→save→audit及返回后故障恢复通过。每个proposed先保存再close/audit，info1是周期用尽。R每16完整递推/每64场先保存再audit，无G→R混接、意外修复/资源重入/GK重启均0。GPOLY/GNN逻辑12831/11903、新GK6484/5784，因各冻结B10000s收口，不是已证实停滞。

新增正式one-run监督wall **19905.129134s**（5.529203h）；V6起formal下界 **57413.555143s**。旧辅助unknown保持。同时整树采样峰 **2576646144B（2.399689GiB）**，own swap/VRAM **0B**，全部成本为shared-workstation。

统一库wall9948.695334/9947.008413s，G214.851938/215.844722s；S+SH32017、audit265、新A/image QR0。MPI1、实际选核CPU0、数学/Torch1、Loader0、独立cache/自有锁，.5秒整树监督；无cgroup委派，不宣称连续kernel限额。未触资源上限、PSI重入0；共享影响/性能INCONCLUSIVE，不承诺零干扰。candidate无global p4 factor、新S、正规方程或fallback；独立native审核包含原FE装配成本。

唯一worktree/branch/upstream为`/home/fenics/Projects/NN-Lab`、`task42_neural_coarse_inverse`、`origin/task42_neural_coarse_inverse`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。正式run actual source全部`d3e5800ee379168ca33bc3dae595de1c8aa71063`，后置checker source`eb97b4214d4d0a4969ea4eb0038300f0ab214efa`，最终交付完整HEAD以回执和最终回复实际报告，不能冒充run source。保留原0.7nm/384hex/p3/q15/40ports、canonical用户材料及原hash；没有新参考LU或训练。

小测试最终45 passed、reader15 passed、raw EVIDENCE_CONSISTENT；8dat实际schema/stage与validate/compileall通过，首轮2夹具失败与全部费用保留。不声称CI/Ruff/full pytest。旧task/review/response/raw及负结果保留，summary/tests/changed_files、导航及两总账同步。[完整结果](outcomes/gmres_repair_residual_completion_v18.md)、[run/source](outcomes/records/run_index_v18.json)、[Gate](outcomes/records/qualification_and_dispatch_v18.json)、[费用](outcomes/records/resource_costs_v18.json)。GitHub精确页未取得视觉证据，NOT_VERIFIED；本地表格/公式检查另列。

未运行首次pass抛光、新p4参考、最大模型、GPU、p6或merge，均超本批资格/范围。唯一下一建议：仅建议下一份review授权后，对本轮已冻结的GPOLY-R-FINAL做一次固定G256原方程校正，并冻结前后状态、独立比较场与通道功率。它检验R的场改善能否在进一步压低原残差时保留；不新增基、PC、训练、参考或restart扫描，本批不实施，也不保证通过。

清理自身负载，只推送本执行分支后停止等待review。
