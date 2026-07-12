# 下一步决策

## 已关闭

1. h=2 matrix-free 与 explicit action：MPI1/MPI4 均通过。
2. 旧后台运行：确认 ILU2 setup swap thrashing 并终止。
3. 流式 checkpoint：`progress.json` 与 residual CSV 已实现。
4. 16 slab/ILU1 低内存 PC：100 步 strong gate 通过。

## 不再重复

以下方向已有充分负证据：restart 300、shift 0.3、coarse 32、全传播谐波、inner 两步、BiCGStab(2)、TFQMR、GCR 长跑、缺陷校正、在线残差 enrichment、单机 ILU2。

## 下一项真正值得做的工作

1. 建立 GenEO/局部谱 coarse space：从重叠 slab 的低能广义特征向量自动提取困难模式，不再手工增加 Fourier hats。
2. 或更换包含 HPDDM 的 PETSc complex 镜像，测试 GCRODR 与 PCHPDDM 两层 Schwarz；当前镜像 `PETSc 3.24.0` 报告 `hpddm=False`。
3. 以当前基线 `7.051153443515814e-4` 为硬门，候选在 100/600 步不能改善至少 20% 即停止。
4. 达到 `1e-6` 后立即计算 official R/T/A，再做 MPI topology PC；不要提前做参数 sweep。
5. h=2 direct/OOC 只允许 baseline 与一次 memory-ordering 尝试，避免重新陷入 swap 消耗。

当前推荐研究起点：

```text
matrix-free F-C H^-1 D
+ FGMRES(100)
+ 16 physical z slabs
+ shifted local ILU1, beta=0.1
+ 24 z coarse intervals
```
