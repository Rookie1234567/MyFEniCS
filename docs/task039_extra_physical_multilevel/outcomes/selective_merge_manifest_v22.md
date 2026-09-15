# Task39extra Review V21 / Response V22：Selective merge manifest

本 manifest 只定义审阅边界，不表示已经批准 merge。当前分支仍是 `task39extra`；Z1 base=`f9e16c21b936673b5a2dadcf52d2c344e61aabe8`，本轮文档开始前的 source/current pre-Z5 HEAD=`f8d0fbf3da48fd3cbe5cc3a226dbff3feb1d9b48`。Z5 没有新增 PDE、没有实现新 PC，也没有把 B 的资源阻断改写成数值失败。ordinary default unchanged，master merge approval=`false`。

## 分组合并表

| 依赖组 | 范围/文件 | 数值行为是否改变 | 测试与 fresh evidence | 建议合入顺序与边界 |
|---|---|---|---|---|
| production numerical/core | V21 opt-in runner/profile 及其依赖：`src/runners/physical_dual_cell_condensed_robustness_v21.py`、`src/runners/physical_dual_cell_condensed_lowmem_v20.py`、`src/runners/physical_retained_outer_adapter.py`、`src/runners/physical_p4_schur_v14.py`、`src/geometry/v21_frozen_plan.py`、`src/geometry/mesh_builder_3d.py`、`src/common/config_3d.py`、`src/io/input_schema.py`、`src/io/input_validation.py`、`src/io/physical_intermediate_profile.py`；对应 `input/task39extra/v21_*.dat` 及 tracked `outcomes/records/v21_frozen_geometry_mesh_plan.json`（输入身份依赖，不能作为可丢弃 raw artifact） | V21 增加冻结实体、h7.5 网格及尺寸/身份参数化；J 桥、BAL_H/H6 和准确 p4 作用保持原算法。Z5 仅文档，旧 profile/default 不变 | A fresh Z2 run：source=`863ec3bcd7eead867795284db11fc39e758a6f08`，residual=`9.756517234801763e-7`，independent A6=`9.756517234802322e-7`，65/65 checker；B fresh Z3 只到 p4 CSR/symbolic capacity stop，不能作为完整 solver pass | 只有在 ChatGPT 最终给出 merge approval 且用户授权后，按 source/profile、input、runner 依赖整体审阅；不得单独合入默认配置；B 的 `10131000000 B` 是 request policy，不是性能承诺 |
| reusable runner/watchdog | `scripts/run_case.py`、`scripts/run_case_in_user_service.sh`、`src/runners/task038_launcher.py`、`src/runners/task038_full3d_iterative.py`、资源 watchdog/ledger 相关已资格化入口 | Z5 未新增 runner/watchdog 逻辑；运行身份和 parent/worker/systemd 分类必须保持可区分 | B raw root、`z3_root_stop_audit.json`、`z3_resource_stop_compact.json`；tree RSS=`2318045184 B`，worker RSS/PSS=`2318233600/2287882240 B`，swap=`0 B`，descendants cleared；A resource authority 也已保存 | 与 production/profile 依赖一起审阅；不要用 B 的 `WORKER_FAILED` 覆盖 worker `RESOURCE_CONTROLLED_STOP`，也不要把它写成 OOM |
| checker/benchmark | `benchmarks/check_dual_condensed_robustness_v21.py`、`src/test/test_task39extra_v21_checker.py`、`src/test/test_task39extra_v21_z1_profile.py`、`src/test/test_260_task038_input_schema.py`、`input/README.md` 与输入 schema/benchmark contract | checker 从 raw evidence 重算并保留历史兼容；没有重写 raw events 或 raw schema；B checker 不运行 | A current/recheck=`65/65`，checker source SHA=`acbad332f35ccf3302fb027335b93ed399941c2a937012c86f2cc51f3beabcb6`；original failed copy 保留，失败项为 `release_timeline`/`summary_schema`；Z1 preformal=`99 passed`，repair path=`49 passed` | 先审 checker/contract，再审 PDE 结果；49、99、65 是不同集合，不能相加；不使用 `--no-verify` 或伪造 B pass |
| compact evidence/docs | `docs/task039_extra_physical_multilevel/outcomes/records/dual_condensed_robustness_v21_compact.json`、`dual_condensed_robustness_v21_decision.json`、`dual_condensed_robustness_v21.md`、`../response_v22.md`、`outcomes/summary.md`、`outcomes/test_summary.md`、`docs/development_progress.md`、`docs/development_model_registry.md`、`records/run_index.json`、本 manifest | 仅更新证据索引和审阅边界；不改变 solver | A/B/C/O10 四模型 aggregate；B p4 CSR exact hashes、raw/oriented class `12/26`、local cache=`24541920 B`、symbolic rows/NNZ/INFOG、capacity arithmetic；Z5 frozen authority：50 files/26 old profiles/changed 0/passed true，SHA=`880534b2c2bb72939669ef098cb809510b666930101a74a0a1312905e0b3a5b3` | 最后合入 docs/evidence；必须与 run index 和 raw paths 一致；不删除历史 V20/V19/V18 negative/unknown |
| research-only | B raw run root、`results/.../v21_events.jsonl`、p4 assembly/symbolic stop audit、大型原始 geometry arrays、saved cost comparison；tracked frozen plan 属于上方输入身份依赖 | 不提升为 production default；B 的 global p4 trace factor scaling/替代方案仅为下一研究问题 | B p4 CSR `84680×84680`、NNZ=`32320342` 已 materialize；numeric factor allocation/used entries/RSS、p6 cache、outer solve/residual/physical output 均 `not_run`；h7.5 owned cells=`990`，neutral alignment planes 已记录 | 保留 ignored/raw artifacts和 hash-bound path；研究证据可随 docs 合入，但不能把 request 当 measured memory，也不能凭 A RSS 外推 h7.5 |
| do-not-merge | C `Z4_NOTCH_H7P5`（未运行）、任何新的 PC、未测 numeric factor memory/entries/RSS 叙述、未授权新 heavy case、master 合并、把历史 unknown/negative 改写为 pass | 明确禁止 | C 无 worker；B checker=`not_run`；无新增 PDE | 除非未来新 review 明确授权并重新资格化，否则不合入；本轮最终状态 `LOCAL_REVIEWED_REMOTE_PUSH_PENDING_AUTH` |

## 依赖和证据顺序

推荐审阅/合入顺序为：

1. frozen source/input/profile/geometry identity；确认 formal run source 与文档 closeout source 不混淆。
2. runner/watchdog/ledger 和 checker contract；确认 parent/worker/systemd 三层终态与资源口径保持原样。
3. A fresh PASS 与 B resource-controlled stop 的 compact/decision；确认 C 仍为 `not_run_by_review_condition`。
4. outcomes、progress、registry、run index 和本 manifest；确认历史账本未覆盖。

Fresh evidence identity：A run root 为 `results/euv_grazing1_phi0/task39extra_v21_z2_notch_h10__full3d_iterative__mpi1__Mna/20260915T053102.148718Z`；B run root 为 `results/euv_grazing1_phi0/task39extra_v21_z3_original_h7p5__full3d_iterative__mpi1__Mna/20260915T065308.474983Z`。几何 plan 的 notch union 为 `x=[16.5,33.5] nm`、`y=[0,8.333333333333334] nm`、`z=[40,80] nm`，8 entities；h7.5 每轴 `[9,5,22]`、990 owned cells，不能改写为旧 720 或 uniform multiplier。

成本比较文件 `benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z5_root_saved_cost_comparison.json` 的 SHA256 为 `87975d656484936f6b3ca1ca067bd539fd6a752a91a98acb8816fd2e6fe1d577`。它只绑定 O10/A 已保存单步、BAL_H、p4 setup/symbolic/numeric fields；不填 B/C 迭代增长，不把 form cache event time 当完整 workflow time。

最终 merge 必须等待 ChatGPT 最终 merge approval 和用户授权；主控的本轮执行把关不等于合入批准。提交及远端同步状态以最终回复和 Git ref 为准。
