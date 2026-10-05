# V27：真实R输入重现及安全拒绝

本轮要恢复的是外部模式的完整数值清单。它决定边界载荷和投影的复数方向/归一化；仅有相同名称不够。新选核范围与封存事务通过资格后，已使用冻结数学执行一次真实生成。**运行正常完成，但原清单逐字节不符，因此B0/B1没有运行。**

| 固定原值与保存重算 / measured | 要求 | 本轮值与分类 |
| --- | --- | --- |
| manifest字节数 / B | 36,244,923 | 36,263,033；多18,110，FAIL |
| 完整manifest SHA256 | 52d7ec80… | 7dd07d71…，FAIL；下文保留完整SHA |
| 唯一有序mode key / 项 | 32060 | 32060；四个side/极化组各8015，PASS |
| key SHA256 | 03c1965c… | 相同，PASS |
| 模型物理身份 SHA256 | a855565b… | 相同，PASS；不能替代数值清单hash |
| inventory身份 SHA256 | 39b457c3… | daa1f7dd…，FAIL；它含manifest身份 |
| 原生生成/FE/factor/solve/NN | 仅一次R | 1/0/0/0/0；不等于全模式q60资格 |
| 保存身份与拒绝 | 原始文件完整、失败不准入 | 43份Git源码和manifest封存/独立重开；最终ledger/B标记均未创建 |

要求manifest `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d`；实际 `7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e`。实际inventory `daa1f7dd1092ebe148ce173219559c6e60105800e374570bfdf872408a38952c`；要求 `39b457c3f0b9d8db5f85a8f1482734513d48670c017d4c8060cae734bdcd0c12`。

[输入记录](records/input_reproduction_v27.json)绑定未改的失败文件、实际ABI和一次调用claim。claim里的PENDING_OR_UNKNOWN表示调用前防重复凭据，不是科学最终状态；最终状态从保存candidate及独立重算得到。大manifest留ignored，未写入Git，也没有改旧原件hash或把新receipt冒充历史ledger。

实际环境是原合格native prefix，NumPy2.5.3、PETSc3.25.6 complex128/int32、Basix0.10.0、MPI1/math1；使用原c354afa数学/源dat/物理身份。原manifest正文依然缺失，不能测逐数值差，更不能确定ABI或JSON长度是根因。只读复核确认当前canonical JSON读回一致，**不证明与原数值相同**；没有第二候选、数值库扫描或精度/序列化调整。

选核修复只扩大内层检查的候选范围至经验证的pin前允许范围，未放宽资源门。真实两层新样本均选择CPU12并保持原邻线程保护；原60秒PSI检查通过。R全链81.936506s，watchdog子段18.688100s；同时身份匹配终端树峰437,981,184B、自身swap0、hard2GiB。监督前峰未保留。全部费用、原失败和嵌套口径见[资源](records/resource_costs_v27.json)，没有宣称整个研发窗属于最终48小时冷流程。

封存修复已被真实失败出口使用：43份Git blob由固定commit/path校验，manifest作为磁盘artifact校验。独立`validate_stage`核准的是**完整保存的失败收据**；不是数值PASS。实际`validate_originals`返回received=false，实际`commit_recovery`拒绝失败candidate。成功marker-last出口仅有完整fixture资格，真实成功恢复尚未出现。[独立checker](records/independent_checker_v27.json)明确分开这两种证据。

[39项测试与全部早期失败](records/targeted_tests_v27.json)、[run/source](records/run_index_v27.json)、[工程修复](records/repair_log_v27.json)、[Gate](records/gate_decisions_v27.json)、[最小包](records/integration_packet_v27.json)。B0方向/MPC、B1全32060 q60/Decimal及完整RHS/原H、独立B1checker均NOT_RUN_R_BITWISE_REPRODUCTION_FAILED；B2由主线负责，本包不运行。主线/dot分支没有修改，不复制其全域AUTO、旧数组归因、p6恢复或存储。

原场/通道/功率结果及目标仍未资格化；本轮不产生NN收益。旧M3600较好、Mfinal退化、D0否决/D1未运行、所有负结果/UNKNOWN保留。失败属于授权出口，不能用余下时间生成第二个清单或擅自降低原hash门；整批交付后停止等待审阅。

实际GitHub呈现已有限核验：发布`007f61b8ce31224e9547e82a7cf7c70bf8374feb`的两新页标题/开头、全部3表和5张实际目视图可读；浏览器监督19.558924s、同时树峰1,705,955,328B、自身swap0并清场。复用Review V26原视觉收据，不重渲染历史；本seal仅追加呈现/成本收据与尾段文字，尾段及其他导航页未重新视觉核验。[呈现范围](records/render_check_v27.json)。
