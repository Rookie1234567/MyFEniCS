# Response V34：Review V30 C0–C2 离线收口

## 状态

Task39extra 本机阶段以 `CLOSED_WITH_QUALIFICATIONS` 收口。用户选择 B 线后，压缩包里的 parent final report / Review V30 与 Task40 N0–N6 文档作为当前权威。此次只使用已有 run 和数组做离线核验，没有启动新 PDE、矩阵装配或 factorization。

## C0：身份与分支

| 检查 | 结果 |
|---|---|
| canonical worktree | `/home/shenjh/Projects/MyFEniCSx_task37_extra`，`task39extra`，upstream `origin/task39extra` |
| 初始身份 | 本地 `e09bd1612c4f6ca5fb5cf3572835748ad5c16207`；fetch 后远端唯一后继 `95dacd01e86f0f7f1d29ee2d5e5a16039bb41871` |
| 更新 | `git merge --ff-only FETCH_HEAD`，快进成功；保留原提交历史 |
| 工作树与运行 | 快进前工作树 clean；未发现旧 Task39 求解器、worker 或 watchdog 进程 |
| 远端探针 | `GIT_TERMINAL_PROMPT=0 git ls-remote origin HEAD` 成功；未遇到密码提示 |

远端 `95dacd0` 已含旧版同名 final report 与 Review V30。按 B 线选择，本提交以包内版本作为当前文档；旧版仍可从 `95dacd0` 历史读取。包内 final report SHA256 为 `44885117a3e5594a25f8138b3428e2a5d65619357bbadc5771a1997eb478fc13`，Review V30 SHA256 为 `faaf35725ea8f11830f31e0acbe408300f0f55ddc92fe8cde16caa4c1537d337`。

## C1：V31 与 V29/V30 离线场、模态对照

比较只读取已保存的完整场向量、同坐标采样、官方 80 元素向量及衍射模态 JSON。三次运行的物理模型 SHA、p4/p6 映射 SHA、80 模态身份、p4 凝聚矩阵 CSR SHA 和网格单元数均相同；各 run input SHA 不同，涉及运行标识以及显式 profile/backend 选择；物理、网格与离散算子身份已核对一致。

| 对照量 | V31–V30 | V31–V29 | 对应限制/阈值 |
|---|---:|---:|---|
| 全场系数向量欧氏相对差 | 0 | `2.2153725762e-14` | 系数欧氏范数，不是 FE 质量加权 L2 或 curl 范数 |
| FE L2 / scaled-curl 相对差 | 0（同一数组） | `1.4028635388e-14 / 3.3312391900e-14` | V29–V30 数值取自既有 compact record；因 V31/V30 全场 NPZ SHA 相同而传递，不是本轮重新计算 |
| 同坐标 E/H 采样相对差 | 全部为 0 | E `1.4636905245e-14`；H `5.9663088620e-14` | 同坐标；远低于 review 的 `1e-4` |
| 界面切向 E/H 相对差 | 全部为 0 | E `1.0970606150e-14`；H `1.4306751440e-13` | 低于 `1e-4` |
| 官方 80 元素向量相对差 | 0 | `1.3897028323e-14` | 80 个 key 次序一致 |
| 模态复振幅相对差 | 0 | `1.9013904913e-14` | 最大绝对差 `1.0988964840e-14` |
| 每模态最大绝对功率差 | 0 | R `7.8271e-15`；T `2.2898e-16` | review 限值 `1e-6` |
| R/T/A_balance/A_volume 最大绝对差 | 0 | `7.83e-15` 量级 | review 限值 `1e-5` |

现有 V31 原 A6 final 与 release 后真残差均为 `9.283162411158934e-7`，低于 `1e-6`；R/T/A 与 80 通道能量闭合沿用原始 run record。离线跨版本一致性补齐了先前缺少的场对照，但没有同离散独立 direct reference；五个原 field-reference checkpoint 仍是 `NOT_ATTEMPTED`，因此 V31 仍为 `DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`，不声称连续极限收敛。

V31 manifest 未逐项保存 OMP/BLAS/MKL/NumExpr 环境变量。worker 记录显示 MPI1、各线程数为 1；不把 worker 字段回填成 manifest 字段。PSS 保持 `disabled/null`，swap 为 `observe-only`。通用 intermediate checker 的 `EVIDENCE_INCOMPLETE` 因 schema 缺少 `physical_intermediate_summary.json`，不属于本 run 的数值 Gate。V31 首次场是 Codex 误停，原始分类枚举仍为 `USER_CONTROLLED_STOP`；i112 残差和无最终场记录保持原样，不被 completion rerun 覆盖。

完整逐文件 SHA、身份字段和比较数值见 [V31 离线对照记录](outcomes/records/projection_layout_v31_offline_comparison_v34.json)；只读比较脚本见 [保存脚本](outcomes/records/projection_layout_v31_offline_compare_v34.py)。FE L2/scaled-curl 的来源是 [V30 compact record](outcomes/records/workstation_guided_local_v30_compact.json)。

## C2：文档与交接

包内 final report / Review V30 已落到标准路径，README、outcomes summary、V31 outcome、run index、test summary、development progress、model registry 与 docs 索引已追加本次收口入口。run index 保留旧条目，只新增 V30 收口项并更新 current pointer。

文档合同和链接检查结果见 [Task39 test summary](outcomes/test_summary.md)。本轮不运行全仓 pytest，不声明 Ruff、MPI2/4、CI 或 GitHub 渲染通过。提交完成后，真实 closeout SHA 将由 Task40 branch provenance 绑定；Task40 原远端创建提交继续保留，不改写为“新建”。

### 结论边界

- 保留 Task39 普通默认、数值源码、全部旧失败和受控停止记录；不合并 master，不迁移工作站。
- 用户选择的 B 线 Task40 N0–N6 将作为唯一活动任务书；远端 A0–A6 历史保留在旧提交中。
- 本收口不新增精度、容量或通用几何资格；0.7 nm 结论由 Task40 的材料、几何和真实 PDE Gate 决定。
