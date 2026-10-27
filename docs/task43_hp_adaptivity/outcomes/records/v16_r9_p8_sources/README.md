# V16 轻量证据索引

本目录仅对应 V15 review 的固定 P8 实验。T 两次调用结束；S/F/C/E均未调用。大 trace、resource流、source快照与fixture仍在ignored `benchmarks/artifacts/task43/v16_p8/`。

- [T主验证原始stdout](T_main/worker_stdout.txt)、[XML](T_main/pytest_results.xml)、[主控终态](T_main/terminal_review.json)。实际HEAD c620c96ef98adac4e1caf05e28dae7744e73a328。
- [T恢复原始stdout](T_recovery/worker_stdout.txt)、[XML](T_recovery/pytest_results.xml)、[主控终态](T_recovery/terminal_review.json)。实际HEAD 3b9d5e0adb43f69a1fdf339691b26d7eec506686。
- [最终字节与复用范围](final_byte_scope.json)、[末fixture静态修复](focused_recovery1_resume_fixture_fix.diff)、[静态结果](focused_recovery1_resume_fixture_static_validation.json)。修复后NOT_RERUN。
- [初始旧输入身份核对](root_initial_input_identity.json)、[准备期查找失败](root_static_notes.jsonl)。没有旧场重采样或新PDE。
- [初始18节点](targeted_test_scope.json)、[恢复节点与依据](T_recovery_scope.json)、launch目录中的同字节脚本。S/F/C脚本只静态检查，未执行；不得据脚本存在授予资格。

机器总账为[结果JSON](../v16_r9_p8_results_v1.json)。原始stdout/XML、snapshot与当前最终测试字节严格分开；17通过不等于最终18通过。科学值没有取得，不能解释为P8负响应。
