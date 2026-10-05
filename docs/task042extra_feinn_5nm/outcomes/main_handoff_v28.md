# V28主线接入包：已实际消费，尚未接入主线

状态 **READY_FOR_MAIN_OPT_IN_NOT_INGESTED**。这份包提供原尺寸模式清单和两个代表面经过独立核验的边界数组，让接收方先核对输入身份、原H、坐标/方向和入射载荷，再决定是否显式接入自己的求解器。它没有替主线完成全域装配、全场解或存储后端资格；接入与后续运行仍按主线自己的合同。

| 必须一致的接收对象 | 本批实际值 / 相对位置 |
| --- | --- |
| instance / schema | W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28 / 显式schema2 |
| 包根，本机真实可用 | `benchmarks/artifacts/task42extra/w1_receiver/v28/u28/bundle_consume/bundle/` |
| 新目录实际资格包根 | `benchmarks/artifacts/task42extra/w1_receiver/v28/u28/bundle_consume/relocated_package/` |
| package_manifest SHA256 / bytes | 664e4ad412e818553c0172060b9e158f7edb06a1a90539a40370985b1aa8a5a9 / 152633 |
| 文件 / 实际数据量 | 1043文件 / 1625383207B；相对路径、bytes和SHA均逐个重开；ready标记另在成功清场后发布 |
| 原模式清单 | `input/mode_manifest.json`；SHA7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e、36263033B |
| 配置 / 独立分母定义 | `input/resolved_config.json` / `input/reference_definition.json` |
| 原数组 | `raw/chunk_index.json`及其中相对布局、模式≤64的1004个完整chunk、见证作用、入射和oracle文件 |
| 消费器 / 最终准入 | `consumer.py`和`code/`；`READY_FOR_MAIN_OPT_IN_NOT_INGESTED.json`最后写，consumer_cleared=true |
| 历史身份声明 | 旧原件未恢复，旧数值等价UNKNOWN；新包不能冒充旧52d7ec80…manifest或ledger |

包内provenance保留原运行绝对路径，作为历史来源；**活跃消费数据依赖仅为包内相对路径**，不借这些原路径重求数组。没有新git clone，没有伪造下载URL，没有要求用户clone/install/run。这里给出真实本机可消费目录，跨机传输/断电恢复未资格化。

实际独立进程在新`relocated_package/`根以`python -I -B consumer.py`运行，读取同一manifest和所有数组，再独立重算32060模式字段和1218328项边界数值门；不是仅核文件hash或status。失败0，最坏原分母相对9.595725209727146e-11。最后成功监督与清场后，两份包的ready标记均发布。[消费者原收据](records/consumer_receipt_v28.json)绑定实际新目录、进程结果、数值CSV、文件数量和两个相同manifest；[run index](records/run_index_v28.json)绑定实际source82b74b2e7b2afa9660595cea37730c77b591e877。

接收端的只读重验接口如下。这是复现接口说明，本支已完成的新目录验收不会为了说明再跑第三遍；主线执行须在其授权及资源门下运行。

```bash
cd /home/fenics/Projects/NN-Lab-V2
source scripts/activate_task42extra.sh pure
cd benchmarks/artifacts/task42extra/w1_receiver/v28/u28/bundle_consume/relocated_package
python -I -B consumer.py --package . --output ../recipient_check_unique
```

正常接收不要加`--qualification-only`：它只用于ready发布前的本批资格进程。默认消费入口要求已经封存的ready及一致package_manifest，并从原数组重算数值门。输出必须是新的唯一目录，partial或身份不一致均拒绝。

新清单、B、D、H、参考面、物理入射RHS和q60 profile必须同一个instance。主线不能复用历史清单的B/D/H或端口因子拼成新实例，不能把representative_facet资格当全域装配或全场误差证书。B/D不是默认互为共轭转置；极化/参考面/Floquet及MPC只采用本包的原定义，不拟合整体相位，也不裁微小内部迹。

| 允许说明 / 未验证出口 | 状态 |
| --- | --- |
| 新输入独立科学资格、两个p阶全部模式代表面、实际独立目录消费 | 已完成，见[Gate](records/gate_decisions_v28.json) |
| 主线实际接入及全32060模式全域装配、MPC/内部恢复 | NOT_INGESTED / NOT_RUN，本包不代主线执行 |
| 体场原残差、总/散射E/H/curl、六样本、散射复通道、R/T/A/A_volume | NOT_RUN，没有全局PDE场 |
| 新Maxwell因子/solve、Gram、NN、B2局部LU、W2/dot存储 | 0 / NOT_RUN，没有新增许可 |
| 原尺寸最终目标与NN | FULL_TARGET_NOT_QUALIFIED / FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT |

下一步由主线在自己的有效合同内消费这一明确新身份，检查实际接入差异；本支不修改其他分支、不merge master、不自动继续训练或原尺寸全局求解。所有历史较好态、最终退化、失败、UNKNOWN及成本保留。
