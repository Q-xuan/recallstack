"""Context packing prefers entrypoints and slices large files."""

from __future__ import annotations

from repowiki.core.context_pack import pack_module_context, slice_file
from repowiki.core.models import FileInfo, ModuleOutline


def test_slice_file_keeps_head_and_symbol_windows():
    lines = [f"# line {i}" for i in range(200)]
    lines[80] = "def important():"
    lines[81] = "    return 1"
    text = "\n".join(lines)
    sliced = slice_file(text, max_chars=800)
    assert "def important():" in sliced
    assert "... (truncated)" in sliced
    assert len(sliced) < len(text)


def test_pack_module_context_puts_outlined_entrypoints_first():
    filler = "x = 1\n" * 400
    files = [
        FileInfo(path="app/util.py", size=len(filler), language="python", content=filler, lines=400),
        FileInfo(
            path="app/main.py",
            size=20,
            language="python",
            content="def main():\n    return 1\n",
            lines=2,
            is_entrypoint=True,
        ),
    ]
    plan = ModuleOutline(name="app", depth="standard", key_files=["app/main.py"])
    packed = pack_module_context(files, depth="standard", outline=plan)
    assert packed.index("app/main.py") < packed.index("app/util.py")
    assert "def main():" in packed
