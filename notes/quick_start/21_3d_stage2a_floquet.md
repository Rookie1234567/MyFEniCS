# 3D Stage 2A 双 Floquet

```bash
python src/main.py --preset 3d_stage2a_floquet_smoke
```

Stage 2A 在 Stage 1 上增加 x、y 两组 Bloch/Floquet 从属自由度约束。`auto` 在 p=1 使用拓扑边配对，在 p=2 使用高阶 trace 配对；角点和边交汇处必须只有一致的主从关系。

重点查看：x/y phase probe、从属 DOF 数、角点一致性、约束后矩阵行数和解析场误差。`sparse_facet` 只是历史 p=1 别名，不是 p=2 正式路径。

公式见 [`../theory/floquet_periodicity.md`](../theory/floquet_periodicity.md)，实现见 [`../reference/code_walkthrough/21_3d_floquet_and_pml.md`](../reference/code_walkthrough/21_3d_floquet_and_pml.md)。
