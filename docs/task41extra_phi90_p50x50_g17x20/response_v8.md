# Task41extra Review V8 执行回应：目标行保存数据审核与局部 RHS 反事实

日期：2026-10-21（Asia/Singapore）  
执行分支：task41extra_phi90_p50x50_g17x20  
V8 checker source：3ce1a158e3e0b6556a2e094755adf9b5bd18ae08  
V8 checker contract SHA-256：40bebce4e1845252ff99e9dbe39fc72d626250befdd72c69ef211efd569bc754  
固定窗口 SHA-256：ea6b38c3bc791ace068c75188a562023cae197f7016f110b0b86970891c46c8d  

结论：V8 selected-star 审核完成了目标行两个 incident cells 的局部 RHS 反事实；V6 candidate 原 full-action 两列仍超过 `1e-11`，V8 没有重跑 candidate 全域作用。另一个独立的 saved donor action 重放也失败。顶层 recovery 通过只属于历史 donor；candidate recovery 与 qualification 均未通过，`official_result=false`。

本轮分为两个阶段：较早的 selected-star producer 扫描28,000个单元的 metadata/行映射，并为目标行唯一关联的cell 23352、23493重建缺失的 candidate/reference 局部张量和 R/T/S；没有做全域 FE assembly、PDE 或完整作用求解。之后 checker attempts 1–4 均只读保存报告/数组，其中前三次因 checker 字段或解码错误失败，attempt4完成独立重算。完整身份、分阶段结果、资源成本及新增24个诊断数组的逐项hash见 [V8 compact](outcomes/b0_v8_selected_trace_star_audit_20261021.json)。

## 结果与身份

attempt4 service 为 task41-v8-check-3ce1a158-20261021t092516z，invocation id 为 6e8991ded3534f3aa27e961630bb8374。worker 对保存报告完成只读独立复算：status=COMPLETE、audit_completed=true、data_integrity=true、recovery_passed=true、joint_action_passed=false、qualification_passed=false、candidate_numerical_passed=null、official_result=false。顶层 recovery_passed 表示历史 donor 的恢复重放；它不表示 V6 candidate 的 recovery 或 full action 通过。

checker report 为114,018 B，SHA-256 b12af06f818dd4a93443498371aa653216b1646207418f8eaac265e09ddf78c6；它重验的 candidate producer report SHA-256 为1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f。donor source 为afbe91e5947ed18fb74d7105097e129c1b8b4cc7，donor contract SHA-256 为9e312f86cdd6b15fff9015faf4fb7dce19043fa3798a3f35cf2e57f79149713c；candidate producer source 为35fd1bbf2bca13bd17e89cc79cf7cd825b94411c，producer contract SHA-256 为a6a69b75e48572d59ae73f12a9424b06a3accdca957c6a32b5c72bcf2fb867da。

## Selected-star producer 的范围

producer source `35fd1bbf2bca13bd17e89cc79cf7cd825b94411c` 在 attempt1 对28,000个cell只核对编号、row/MPC归属和incident-cell覆盖，以找出目标行的贡献来源；仅cell 23352、23493需要补取局部candidate/reference张量及R/T/S。目标trace行映射为 **active row 4,766,937 → original full-storage row 15,440,235**。单元23352为tag2/permutation4680，局部选中行375、系数1，坐标SHA-256 `00be22d015fe207dd28a8c246380144e51b8ba2d7a3ff63562dfca38b65024e6`；单元23493为tag1/permutation0，局部行75、系数1，坐标SHA-256 `0fbdca58aeb8061e226f1c298a610bbd63f2f43fa15a6830afd3fa435a667ca6`。每个局部元素882个位置，`I=432..881`、`T=0..431`；这两个位置集合由同一Basix空间的真实`entity_dofs`及保存的cell partition核验，并非假定连续切片。这只是稀疏目标行关联的小范围张量重建，不是28,000个全域张量的重建。producer报告授权数组计数840、保存证据154,632,208 B；此前V6前缀数组按身份复用。

## Checker 故障与最小修正

旧 checker 将 V7 的 grouped-left_full/volume 中间项映射成候选 closure，实际保存字段 star_corrected_volume_closure/full_closure 才是待比较的 closure。两者相差 delta_t+Q，不能互换。attempt3 因此在独立重放时抛出 ValueError；这属于 checker 字段绑定错误，不是生产求解或科学 action 新失败。

修正后候选列0、状态j0、production_original_cell_order 的 grouped-left 为
(-2.516118874422491e-9, -1.3884302795759863e-9)，而重算 closure 与保存候选 closure 一致，为
(-5.5638262968987926e-11, -1.644751242796985e-11)。二者差的绝对值为2.8171442193628875e-9。修正的 checker 将 grouped-left 与 closure 分开保存并复算16个有序 P3 summary rows。参考 closure 是重新计算的；原报告没有可供直接比较的 saved reference closure 字段，因此明确标记这一点，不制造通过结论。

改动只修复 checker 的字段取值和回归；没有改生产矩阵、离散或 action。受控测试为 src/test/test_task41_v8_selected_trace_star.py::test_v8_ordered_summary_keeps_grouped_left_distinct_from_closure，结果1 passed in 0.51 s。资格化 WSL activation preflight 通过，PETSc complex128/int32，相关包来自同一 Linux ABI 栈；git diff --check 通过。

## V6 candidate 的原始 full-action 门：失败

这是本任务的主要 candidate 结果，V8没有重新计算它。原限值为 `1e-11`：

| 列 / 模式 | 绝对 L2 差 | 冻结分母 | 相对误差 | 结论 |
|---|---:|---:|---:|---|
| top / mode 16030 | 3.824090978625035e-7 | 2225.481253487629 | 1.7183209126709868e-10 | FAIL |
| bottom / mode 48090 | 8.051905483782545e-7 | 2225.4807123031883 | 3.6180522433957604e-10 | FAIL |

V6 candidate 初始 recovery forward 相对差为 `1.981377497384616e-11` / `1.979023053583157e-11`，都高于 `1e-11`；same-LU correction 为0次。因此candidate的full action与初始recovery均没有通过。V8没有重跑candidate全域action或candidate recovery，`candidate_numerical_passed=null`。

## 保存 donor 的独立 full-action 重放：仍失败

以下是历史donor的保存向量重放，不是V6 candidate结果。审计把误差最大位置记在reduced action vector中，不能将它称作original full-storage row：

| 列 / 模式 | 绝对 L2 差 | 冻结分母 | 相对误差 | 最大误差行（reduced vector） | 端口差 |
|---|---:|---:|---:|---:|---:|
| top / mode 16030 | 6.770178089430243e-7 | 2225.481253487629 | 3.0421186782950706e-10 | 5,458,716 | 0 |
| bottom / mode 48090 | 1.4225036541037616e-6 | 2225.4807123031883 | 6.391893878206601e-10 | 5,458,716 | 0 |

两列都超过`1e-11`。活动trace行与储存编号的映射另为 **4,766,937 → 15,440,235**。保存donor的recovery重放按原donor身份执行三次同LU修正后，forward误差为`8.452404647963959e-14` / `8.462099738746e-14`并通过；该结果不能覆盖donor action失败，也不能转授为V6 candidate recovery或action通过。

## 目标行与局部 RHS 反事实

审计将 active trace row 4,766,937 映射到 original full-storage row 15,440,235，完整 incident set包含两个实际单元23352、23493；复算304个已保存向量分块值，重新核对production cell order与V6八键observer order下共16个有序summary rows。donor j0/j3使用相同active trace，saved native action/RHS/residual配对检查通过；局部同状态RHS可配对复用。

RHS reduction 将单元内部 RHS 通过凝聚矩阵送到 trace 方程右侧。保存路径先用 T 乘 RHS；反事实则从同一已保存 K、J 和 RHS 计算 -J solve(K,b_i)，也就是先解 Kx=b_i，再由 -Jx 投影。这个局部算法比较用4次新建严格 LU、8次直接 RHS solve，重用j0/j3相同的 b_i；没有重建张量或有限元算子。

| 列 | 原 candidate-reference 投影 g 差 | 局部 RHS 反事实差 | 差距缩小 |
|---|---:|---:|---:|
| top / mode 16030 | 2.433304760925843e-9 | 5.157211896343317e-10 | 约4.72倍 |
| bottom / mode 48090 | 4.976414600781769e-9 | 7.809377196826238e-10 | 约6.37倍 |

这是两个 incident cells、目标行上的局部 candidate/reference 投影差，不是完整作用误差，也没有通过原1e-11门。参考路径自己的 d 没有因此显示改善，不能把该局部差距缩小称为全域根因或生产修复通过。该诊断支持一个可证伪、尚未实施的候选改法：在 `src/solvers/p6_cell_condensed_action.py::reduce_rhs` 中对每个RHS直接求 `K x=b_i`，再算 `-J x`，避免先把 `K^{-1}` 的结果压缩进 `T` 后再乘RHS。代价是每个RHS增加一次三角求解，并需保留或重新取得`J`；完整两列action、candidate recovery与独立checker必须全部重验后才可考虑生产采用。

4个局部 LU 分解累计0.1329756253398955 s，8次 RHS 反事实累计0.03073071874678135 s。24个新增 NPY 产物合计13,085,472 B；此前数组 payload 为14,622,146,704 B，包含本次报告存档后累计14,789,864,384 B，低于16 GiB上限17,179,869,184 B；落盘后剩余空间2,000,087,490,560 B，高于2 GiB保留线。逐数组 SHA-256、dtype、shape、文件字节数在 compact JSON 内。

## signed per-cell 与舍入诊断

局部四矩阵闭合按 `E_R=KR+G`、`E_T=J+TK`、`C_S=S-L-JR`、`E_S=S-L-TG` 计算，并核验恒等式 `E_S=C_S+E_T R-T E_R`。下表为目标行两个incident cells的Frobenius范数；这些是局部诊断量，不能取代full-action门：

| cell / role | `||E_R||_F` | `||E_T||_F` | `||C_S||_F` | `||E_S||_F` | 恒等式余差范数 |
|---|---:|---:|---:|---:|---:|
| 23352 candidate | 7.052450992722958e-10 | 5.798103533389314e-9 | 8.846249516328489e-12 | 7.434234761500625e-10 | 1.1030881298015738e-10 |
| 23352 reference | 7.142416308733377e-10 | 6.175873345787944e-9 | 7.50867773689017e-12 | 8.027642279259724e-10 | 1.1158201553404031e-10 |
| 23493 candidate | 7.490548021088263e-10 | 6.773751191828563e-9 | 7.701313019362266e-12 | 7.725975144379914e-10 | 1.073604575822952e-10 |
| 23493 reference | 7.623058898782803e-10 | 5.745953680186077e-9 | 6.833359571603421e-12 | 8.081901479331808e-10 | 1.0823959216743285e-10 |

compact逐条保留了两个目标单元、candidate/reference、两列与j0/j3的16组有符号局部项，包括`Q`、`Q_regrouped`、`S_action`、`T_r_i`、`delta_t`、局部 RHS及float64/wide结果；同时保留从V6按hash复用的八个前缀单元（cell 26762、26897、0、1、2、5、6、7505）的16条candidate/reference四矩阵缺陷范数，不把它们算作本轮重新构建。宽精度仅将实部、虚部分别用`numpy.longdouble`做乘加和投影；mantissa为63 bits，宽于float64，但不能称作“4倍精度”，正式complex128输出不变。production cell order下，j0−j3 的float64 `d_hat`差约为`3e-11`至`1.1e-10`，宽算术对应值约为`1e-15`至`5.3e-14`；同一局部E_S向量在j0/j3间8/8 bitwise-equal（长度432）。这是求和顺序/精度敏感性的局部证据，不证明它解释了全域candidate action误差。

## Attempt、阶段时间与资源

V8有五个独立service父段。子段已包含在父段中，不另行加总；两个准备阶段没有启动service/worker/FE，准备耗时未记录：

| 阶段 | source / 结果 | 父service s | worker或checker/watchdog s | tree RSS peak B | task cgroup peak B | task swap |
|---|---|---:|---:|---:|---:|---:|
| selected-star producer attempt1 | `35fd1bbf2bca13bd17e89cc79cf7cd825b94411c`；完成局部生产，但service因缺`independent_checker_status`标失败 | 373.167504155 | worker 345.588897674；watchdog 349.561707255 | 9,867,120,640 | 2,619,072,512 | 0 |
| saved checker attempt1 | `6021691906a8d4db48a0261140c6601027ad49a8`；complex-pair解码错误 | 156.272612338 | 114.158354789 | 3,998,121,984 | 851,173,376 | 0 |
| saved checker attempt2 | `19116086b4a7e1828535773fca2342afff9bec1f`；错误要求不存在的`projected_T_r_i`标量字段 | 144.498289824 | 103.058789945 | 3,998,904,320 | 851,288,064 | 0 |
| saved checker attempt3 | `23ba24414a02d9e4e8e921ff97d48d5d1d9d1fe0`；grouped-left/closure字段误绑定 | 173.562185443 | 130.711252598 | 3,966,922,752 | 852,905,984 | 0 |
| saved checker attempt4 | `3ce1a158e3e0b6556a2e094755adf9b5bd18ae08`；审计完成，科学门仍失败 | 157.833339050 | 116.206021597 | 4,001,955,840 | 854,421,504 | 0 |
| **五段父service合计** | **只合计以上五个已知formal service段；不是整轮冷流程成本** | **1005.333930810** | 子段不重复相加 | — | — | — |

两个controller prepare错误分别是r1报告路径误指attempt3而非attempt1，r2重复调用一次性prepare被合同拒绝；都没有service、worker或FE/PDE，成本`UNKNOWN`。所有五个service的后代均已清理、task swap为0；不同段的watchdog RSS与cgroup是不同口径，不相加。receipt/watchdog原始哈希和路径见compact与run index。producer本身另记录preparation_elapsed `21.233616863 s`、worker启动后elapsed `345.588897674 s`，均属于producer阶段，不再叠加到父段合计。attempt4有102个采样、没有触发时间或资源gate。

其他工程诊断包括较早inline LU/RHS试算0.526 s、SHA-256 `ba622405bb15052550443e598fb32472eef8403305d4b5bcf7cf2163322cba57`，仅作工程诊断，不作为正式证据。一次本机preflight脚本的symlink resolve断言写错，调整为检查activation后的`sys.executable`路径后通过；修正前没有启动测试或计算。

## 测试、未运行项与下一步

本轮最终checker source `3ce1a158e3e0b6556a2e094755adf9b5bd18ae08` 的定向mapping回归为1 passed in 0.51 s；前序checker接线修复各自使用对应source的定向测试：`6021691906a8d4db48a0261140c6601027ad49a8`为10 passed/38 deselected（0.59 s首轮、0.62 s最终复验）；`23ba24414a02d9e4e8e921ff97d48d5d1d9d1fe0`为3 passed/8 deselected（0.44 s首轮、0.41 s最终复验，并通过diff-check）。测试命令按source及原始结果列在[test summary](outcomes/test_summary.md)；未保存的独立测试日志hash标为`NOT_RECORDED`。文档收口后只做compact JSON解析、字段与数组计数/字节总和、链接目标和`git diff --check`；没有运行全仓pytest、CI或PDE。曾尝试`python -m ruff`，返回`No module named ruff`，因此Ruff检查未完成；没有为此安装依赖，原错误保留。

完整FE重新组装、生产reduce_rhs修改、完整两列action重验、candidate recovery、200q、global factor、KSP/FGMRES、完整场、A6以及official R/T/A均未运行。16 GiB证据上限、原固定窗口、1e-11门限和数值默认值没有更改。

下一项仅建议由主控评估是否冻结reduce_rhs的局部稳定性改动，并要求完整两列action、candidate recovery与独立checker全部重验后再决定资格。V8本身包含metadata扫描、两个incident cells的局部张量补建与后续saved-only局部诊断；它不能据此进入求解器阶段或宣称官方结果。
