from __future__ import annotations

from pathlib import Path

REGISTRY = Path("docs/development_model_registry.md")

REPLACEMENTS = {
    "| p4/h10 global | `(6,3,14)`；global p4 | 53,084 | 21,824 | 8,184,464 | 40,151,936 | `0.001872161` | `0.001882317` | `0.596619520` | `0.401498163` | `2.35e-11` | build `35.64 s`；MUMPS setup `13.36 s` | `success`，但未达高阶收敛 |":
    "| p4/h10 global | `(6,3,14)`；global p4 | 53,084 | 21,824 | 8,184,464 | 40,151,936 | `0.001872161` | `0.001882317` | `0.596619520` | `0.401498163` | `2.35e-11` | peak `历史未冻结`；build `35.64 s`；MUMPS setup `13.36 s` | `success`，但未达高阶收敛 |",
    "| p5/h10 global | `(6,3,14)`；global p5 | 101,815 | 35,000 | 20,140,928 | 101,062,900 | `0.000785714` | `0.000794886` | `0.602483954` | `0.396721160` | `1.25e-11` | build/setup/solve `24.72/36.48/0.077 s` | `success`，接近 p6 |":
    "| p5/h10 global | `(6,3,14)`；global p5 | 101,815 | 35,000 | 20,140,928 | 101,062,900 | `0.000785714` | `0.000794886` | `0.602483954` | `0.396721160` | `1.25e-11` | peak `历史未冻结`；build/setup/solve `24.72/36.48/0.077 s` | `success`，接近 p6 |",
}

NOTE_AFTER = (
    "| fixed p5-trace/p6-interior h13 | `(6,2,12)` | 89,740 | 20,120 | 11,013,212 | 36,273,200 | `0.000756117570` | `0.000765246512` | `0.602682451672` | `0.396552301816` | `5.81e-12` | accuracy peak `6.411 GiB`；canonical setup peak约 `5.03 GiB`；cold/warm non-KSP `19.410/6.696 s` | `controlled_negative`；当前预算内最强点 |\n"
)
NOTE = (
    "\n**峰值内存口径说明：**p4/h10与p5/h10的同表记录保存了rows、NNZ、factor、物理量和阶段时间，但没有冻结单独的per-model峰值内存；因此显式写为`历史未冻结`，不能空着也不能由p5/p6 pair peak反推。p6/h10同时有隔离direct peak `15.964 GiB`和后续Task035c MPI8 static Full3D peak `14.722 GiB`两套不同source/生命周期authority，二者不能混写。\n"
)


def main() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS.items():
        if old not in text:
            raise RuntimeError(f"target row not found: {old[:120]}")
        text = text.replace(old, new, 1)
    if NOTE.strip() not in text:
        if NOTE_AFTER not in text:
            raise RuntimeError("note insertion anchor not found")
        text = text.replace(NOTE_AFTER, NOTE_AFTER + NOTE, 1)

    # Guard against returning to blank/ambiguous peak cells in the static table.
    required = [
        "p4/h10 global | `(6,3,14)`；global p4 | 53,084 | 21,824",
        "peak `历史未冻结`；build `35.64 s`",
        "p5/h10 global | `(6,3,14)`；global p5 | 101,815 | 35,000",
        "peak `历史未冻结`；build/setup/solve `24.72/36.48/0.077 s`",
        "p6/h10同时有隔离direct peak `15.964 GiB`",
    ]
    for token in required:
        if token not in text:
            raise RuntimeError(f"static peak backfill check failed: {token}")
    REGISTRY.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
