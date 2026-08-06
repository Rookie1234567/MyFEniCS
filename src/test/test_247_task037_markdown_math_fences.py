from scripts.fix_task37_markdown_math import _unsupported_tokens, transform_markdown


def test_display_math_uses_fenced_blocks_and_preserves_code():
    source = (
        "before `\\[code\\]` and inline \\[x\\].\n"
        "\\[\n"
        "a = b\n"
        "\\]\n"
        "$$\n"
        "c = d\n"
        "$$\n"
        "```python\n"
        'value = r"\\[keep\\] $$"\n'
        "```\n"
        "~~~text\n"
        "tilde $$ keep\n"
        "~~~\n"
        "inline `$$`.\n"
    )
    expected = (
        "before `\\[code\\]` and inline $x$.\n"
        "```math\n"
        "a = b\n"
        "```\n"
        "```math\n"
        "c = d\n"
        "```\n"
        "```python\n"
        'value = r"\\[keep\\] $$"\n'
        "```\n"
        "~~~text\n"
        "tilde $$ keep\n"
        "~~~\n"
        "inline `$$`.\n"
    )

    normalized = transform_markdown(source)
    assert normalized == expected
    assert _unsupported_tokens(normalized) == []
    assert transform_markdown(normalized) == normalized
