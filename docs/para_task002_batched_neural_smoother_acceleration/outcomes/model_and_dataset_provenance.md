# 模型与数据 provenance

沿用 PARA-Task001 独立 capture：slab 9 dataset 共 480 个样本，train/validation 为 384/96；ILU-residual correction 使用独立 seed/time 段的 128 train + 32 validation。operator exact fingerprint 为 `0fe7e9f597345f6a10bd924ebc43e15198815e151654173c0659d7dbf0306784`。

最终模型是 complex128 POD/ridge rank 32，在 `fenics-ml` 的 `cuda:0`、PyTorch 2.7.1+cu118、Quadro RTX 8000 上离线构造；无 bias、无 activation、无在线训练。checkpoint SHA-256 为 `53314b6939dd9baed3bd60e730e11d1f8a8460b5b36176d8bbe73e9f5cd26a77`。fingerprint/checksum 不匹配时 fail closed。重型来源和派生物保持 Git ignored。
