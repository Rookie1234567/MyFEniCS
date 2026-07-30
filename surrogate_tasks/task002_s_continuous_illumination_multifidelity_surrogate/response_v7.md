# Task002 Review V6 response：M4D 完成，M4 继续停止

Review V6 Required M4D 已完成。Case117 bulk 没有恢复，冻结四元组没有修改，
training index 41–95、frozen validation、surrogate training 均未运行。

## 完成项

1. 失败几何与中心几何各完成规定的 14 点 50–58° azimuth stencil；窄峰位置和
   强度几乎相同，确认角度/离散主导。
2. 原失败点完成 Ny=3/4/5/6；Ny=3 泄漏 `1.2312e-6`，Ny=4 降到
   `3.2783e-25`，Ny=5/6 保持 roundoff。
3. surface q=auto(21)/31/39/47 的泄漏完全不变，排除欠积分。
4. q63 独立 `E_total` 投影确认 outgoing-S auxiliary amplitude 到约 `7.7e-14`；
   demodulated field 的 n=-3 Fourier fraction 同步随 Ny refinement 消失。
5. actual trace-space Gram audit 显示 bottom-S n=0/n=-3 overlap 从 Ny=3 的
   `0.3630` 降至 Ny=4 的 `2.68e-16`，condition 从 `2.1398` 恢复到 `1.0`。
6. 35 个新 PDE 全部 direct solve 完成、zero swap、cleanup complete；Case118 checker
   12/12 通过。

## 判定

根因是 `Ny=3` 网格诱导的离散 Bragg/trace alias。Route A Ny=4 得到定量支持，
且不需要放宽既有 leakage Gate。

但本轮独立投影发现 outgoing-P auxiliary/direct amplitude 最大差异 `5.25e-3`，
Ny=4 后仍约 `1.84e-3`。该问题与已消失的 S alias 不同，已作为负证据保存。
因此没有自行改变 production mesh、建立新 dataset identity、运行 canary 或恢复 M4；
等待 Review V7 决定 P discrepancy 的 disposition 与 Route A 后续授权。

Clean M4D baseline SHA：

```text
0a53c42397a2e67f64e8f6dae2c680bfe3fe4b95
```

完整说明见 `outcomes/m4_y_alias_diagnosis.md` 和 Case118 records。
