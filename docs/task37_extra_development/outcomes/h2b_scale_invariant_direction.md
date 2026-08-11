# H2B-S0 尺度不变方向诊断

本记录对应 Review V9 授权的唯一 H2B-S0 formal campaign。它只判断三种局部 smoother 组合的方向是否值得进入后续 Krylov 预条件器；它不是 PDE 求解，也不是把 checker 的 evidence status=pass 等同于数值算法通过。

## 先用通俗语言说明

S0 把同一个初始残差交给三种固定的局部修正方式：一次性 additive、只向前的 8-color sweep、以及现有的 forward/reverse symmetric sweep。每种方式都生成一个修正 z，再用精确的 full-space B0 action 得到 q=B0*z。rho_star 是在允许一个复数标量步长后，剩余残差与原残差的比值；它回答的是“这个方向即使只选最佳复步长，是否仍可能收缩残差”，而不是只看一次固定单位步长。

本轮没有调颜色、阻尼、PoU 或 source。所有 source、组合、网格、Floquet/MPC、factor store 和 operator 均冻结，结果因此可以作为一个可复核的方向筛选，而不是参数搜索。

## 结论

| 项目 | 结果 | 分类 |
|---|---|---|
| S0 worker payload | 数值 payload 完整，worker RC=0 | measured |
| raw watchdog | status=gate_failed；原因是 terminal-exit unreadable race | measured |
| checker/adjudication | 固定 adjudication 接受证据：28403 个 live samples、processes_gone=true、worker elapsed 1457.519868671001 s、terminal elapsed 1458.4597211719993 s | derived evidence qualification |
| compact status / pass | pass / true | evidence qualification，不代表算法 PASS |
| s0_direction_gate_pass | false | measured |
| 三组合 valid | additive、forward、symmetric 均 valid、finite、deterministic | measured |
| 进入路线 | H2B-P | derived from all three Gate results |
| S0 数值结论 | 三组合无一满足 source rho Gate | measured |

这里的 S0 是对既有 raw 的 retrospective terminal-race adjudication：raw watchdog 本身仍是
gate_failed，不是 watchdog PASS；checker 只是在固定条件闭合后接受这份数值证据。随后提交的
083fb7863375c197437975bb51847682d9240f9a 是 prospective one-recheck fix，只经过实现测试，
没有重跑本次 S0 formal campaign。

Additive 的 gradient、curl、mixed、physical-RHS-like 通过各自 rho Gate；唯一失败的是 checkerboard/high-frequency。Forward 和 symmetric 的五个 source 全部失败。因此 S0 不是算法 PASS，而是严格完成后的方向诊断失败，并按 V9 路由到 H2B-P。

## 冻结范围与资源

| 字段 | 实际值 | 口径 |
|---|---:|---|
| discretization | p6/h10 | measured scope |
| MPI | 1 | measured scope |
| full-space rows | 173802 | measured |
| Floquet identity/constraint rows | 9210 | measured |
| cells / local nloc | 252 / 882 | measured |
| exact classes / unique factors | 24 / 16 | measured |
| factor + metadata | 201933812 B | measured retained factor-store payload |
| process-tree peak | 687476736 B | measured whole S0 online campaign |
| swap | 0 B | measured |
| action closure | additive约 2.85e-17，forward/symmetric约 1.88e-15 以内 | measured；均不超过 1e-11 |

每个 source 的 norm、rho_unit、rho_star、eta、复步长、action closure、重复 SHA 和 timing 均写入 compact；下表集中列出 S0 Gate 所需的完整三策略×五 source 结果。rho_unit、rho_star 和 eta 是 measured；limit 是 V9 fixed Gate；result 是 checker 从实际字段重算的分类。

## 三种组合的完整 source Gate

| 策略 | source | rho_unit | rho_star | eta | limit | result |
|---|---|---:|---:|---:|---:|---|
| additive | gradient-dominated | 0.0002730242318906201 | 0.00027302412076899286 | 0.9999999627289252 | ≤0.95 | PASS |
| additive | curl-dominated | 3.4249244689259526 | 0.7220541849334704 | 0.6918365081578722 | ≤0.95 | PASS |
| additive | mixed | 1.2355059094818321 | 0.7013670818808797 | 0.7128002640669283 | ≤0.85 | PASS |
| additive | checkerboard/high-frequency | 1347.7094525062475 | 0.9594480817867957 | 0.2818853993303786 | ≤0.70 | FAIL |
| additive | physical-RHS-like | 3.9869645084651553 | 0.6642345659875032 | 0.7475242078671475 | ≤0.95 | PASS |
| forward | gradient-dominated | 448862803781.2121 | 0.9999975279886826 | 0.00222351441906436 | ≤0.95 | FAIL |
| forward | curl-dominated | 300168373754.4866 | 0.9999985655405975 | 0.0016937876526127412 | ≤0.95 | FAIL |
| forward | mixed | 428654778865.9087 | 0.9999976700428809 | 0.0021586821642706486 | ≤0.85 | FAIL |
| forward | checkerboard/high-frequency | 869437958182821.5 | 0.9999928721397168 | 0.0037756681197811054 | ≤0.70 | FAIL |
| forward | physical-RHS-like | 200501971346.36578 | 0.9999989316284585 | 0.0014617598397357223 | ≤0.95 | FAIL |
| symmetric | gradient-dominated | 4.542906419782354e24 | 0.9999987736592376 | 0.0015661034015911528 | ≤0.95 | FAIL |
| symmetric | curl-dominated | 2.6341788315209565e24 | 0.999998486619577 | 0.0017397581478094321 | ≤0.95 | FAIL |
| symmetric | mixed | 4.361198568985487e24 | 0.9999989332873225 | 0.0014606245494172044 | ≤0.85 | FAIL |
| symmetric | checkerboard/high-frequency | 7.734935557489985e27 | 0.9999609848199259 | 0.008833393344535185 | ≤0.70 | FAIL |
| symmetric | physical-RHS-like | 1.304855993199958e24 | 0.9999966571876517 | 0.0025856553171886504 | ≤0.95 | FAIL |

S0 的正式 source Gate 是 rho_star，不是 rho_unit。Additive checkerboard 的实际值 0.9594480817867957 高于 0.70，已经足以使 additive 失去资格；其余两种组合也没有任何 source 通过各自上限。所有组合的 deterministic/hash、finite、全空间 norm、无 external slave mask 和 exact action closure 检查仍然成立，这说明本记录是一个完整的数值负结果，而不是 malformed evidence。

## Evidence 与源码身份

| evidence | 路径 | SHA |
|---|---|---|
| source | formal worker source | 053f5cbb577e6e81571748d1580aa3858b5eeece |
| raw | benchmarks/artifacts/task037_extra_development/h2b_s0_053f5cb_run1 | ignored raw |
| compact | benchmarks/cases/101_task37_extra_development/records/h2b_scale_invariant_direction.json | file 44283799e9712aa8e4355fa31e232ce8b3cbf679867c7fface599f3152054637 |
| compact embedded evidence | 同一 compact | c773ba5f96419e9afb433936b348ed5b3f251003b02a7c2e3f3af0e5a675c98f |

Raw 关键文件 SHA：

| 文件 | SHA |
|---|---|
| h2b_s0_watchdog_summary.json | 84952476ee20bac9b9546e72445036c8be96cffffb75948b059284be32db70c7 |
| s0_progress.jsonl | 5e433555d9b05a1af702ebbb5b0ca28ea0f421106b668e902e3b32ccf8320065 |
| s0_root_pid.json | 3661e56608d5442b4829e997e1c282307b34be69bb7492dcfe2904fed0c063a3 |
| s0_stdout.txt | d6dd136d0e4cf3271aecab948fa9aec7992402e23f480a08ed963019eb174ea2 |
| s0_summary.json | db061b8ae90f6349ebb67d7ea8337c3b9356fef27dbc442aa2f28a0eec637476 |
| s0_timeline.jsonl | 6b8189925bc05a8fd8e59fca946d4a0869f3a530da5c2bce0122853786df58e9 |
| stage_progress.jsonl | 7b81d4d446c0328457a9d06fe30347e4b66735d5eb212f2ac0d0198482af1da8 |
| stage_root_pid.json | 368ee0d0c58b02bcd64409d8e5e9a89b2e3006e25ca6264c4b860d521d1b137 |
| stage_stdout.txt | c72b7a05864e1f7b0b1c8c01846192bef8177008c6ab7d49df948b158fd7b5ec |
| stage_summary.json | 34270972814f0ecde604fa7ccad1b43ff8a9e1d7a51b83f320bfaeb1e503080c |
| stage_timeline.jsonl | 9a79ba93c68738dddda057626c1cc786ef0a90ee7ccfa49775181784ac0f5cbd |

正确的复现入口是 qualified activation 后执行 S0 watchdog，再对同一 raw 执行一次 s0-check；本轮文档不重新执行它们。旧 S0 raw、R2 factor store、H2A/H2B 其他 evidence 均未覆盖。

## 停止边界

S0 的 H2B-P 只是 V9 定义的后继路线，不表示 P0 已通过。P0 的唯一 campaign 随后只启动了独立 stage，online 尚未启动，详见 H2B-P0 row-complete patch outcome。P1、H2B-K、H2D、H4、PDE、DtN、field 和 RTA 均未运行。

长期目标“MPI1 full PDE RSS < 2000000000 B、swap=0，并有 direct authority physics comparison”没有在 S0 中测量；687476736 B 是 S0 online campaign 峰值，不能当作 PDE 内存结果。
