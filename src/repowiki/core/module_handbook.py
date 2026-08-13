"""Deterministic DeepWiki-style module docs when the LLM pass is skipped or fails.

A failed write must not resurrect a file tree or method catalog. The page still
explains one flow, names types as roles in that flow, and treats files as evidence.
"""

from __future__ import annotations

from repowiki.core.context_pack import harvest_symbols
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    CallChain,
    Citation,
    FileDoc,
    FileInfo,
    ModuleDoc,
    Symbol,
    TermTip,
)
from repowiki.core.modules import ROOT_NAME

LOAD_BEARING_CAP = 6

_INVENTORY_NOTES = (
    "submodule",
    "entry point is",
    "entrypoint is",
    "methods",
    "lib.rs",
    "file tree",
)


def fallback_module_doc(
    name: str,
    files: list[FileInfo],
    *,
    language: str = "en",
    graph: DependencyGraph | None = None,
    notes: str = "",
) -> ModuleDoc:
    """Handbook-shaped ModuleDoc from scanned files — no method dump."""
    zh = _is_zh(language)
    files = list(files or [])
    bearing = _load_bearing(files, graph)
    primary = bearing[0] if bearing else None
    symbols = (
        harvest_symbols((primary.content or primary.preview or ""), limit=3) if primary else []
    )

    purpose = _usable_notes(notes) or _purpose(name, zh)
    description = _description(name, primary, zh)
    chain, impl = _flow(name, bearing, symbols, graph, zh)
    return ModuleDoc(
        name=name,
        purpose=purpose,
        description=description,
        implementation_details=impl,
        call_chains=[chain] if chain else [],
        edge_cases=_edge_cases(bearing, zh),
        files=[_file_doc(f, primary, symbols if f is primary else [], zh) for f in bearing],
        citations=_citations(bearing, symbols),
        term_tips=_term_tips(zh),
    )


def _is_zh(language: str) -> bool:
    code = (language or "en").strip().lower()
    return code.startswith("zh") or code.startswith("cn")


def _usable_notes(notes: str) -> str:
    text = (notes or "").strip()
    if not text:
        return ""
    low = text.lower()
    if any(token in low for token in _INVENTORY_NOTES):
        return ""
    return text


def _purpose(name: str, zh: bool) -> str:
    if name == ROOT_NAME:
        return (
            "读完本页，你要能讲清仓库根上的 README/配置如何启动一次运行，而不是把根目录当清单。"
            if zh
            else "After this page you should be able to say how README/config at the repo root starts a run — not recite the root listing."
        )
    return (
        f"读完本页，你要能不靠目录讲清 `{name}` 在一次调用里做什么、缺了它哪条能力会断。"
        if zh
        else f"After this page you should be able to explain, without a file tree, what `{name}` does on one call and what breaks if it disappears."
    )


def _description(name: str, primary: FileInfo | None, zh: bool) -> str:
    if name == ROOT_NAME:
        return (
            "根目录页讲启动与配置约定。文件只是证据：先看 README 或入口配置承诺了什么，再进模块页跟一条请求。"
            if zh
            else "The root page is about boot and config contracts. Files are evidence: read what README or entry config promises, then follow one request on a module page."
        )
    cite = _cite(primary, None) if primary else f"`{name}`"
    if zh:
        return (
            f"`{name}` 被上游调进来，再把工作交给本页证据里的类型。"
            f"一次真实路径从 {cite} 开始；如果这一层消失，调用方将无法把请求做到底。"
            "下面只跟这一条快乐路径，不把 crate 当目录念，也不给 struct 列方法。"
        )
    return (
        f"`{name}` is called from upstream and hands work to the types cited below. "
        f"One real path starts at {cite}; if this layer disappeared, callers could not finish the request. "
        "This page follows that happy path — not a crate inventory, not a method list."
    )


def _flow(
    name: str,
    bearing: list[FileInfo],
    symbols: list[Symbol],
    graph: DependencyGraph | None,
    zh: bool,
) -> tuple[CallChain | None, str]:
    if not bearing:
        return None, ""
    primary = bearing[0]
    hops = bearing[1:3]
    role = f"`{symbols[0].name}`" if symbols else f"`{name}`"
    cite0 = _cite(primary, symbols[0] if symbols else None)

    steps = [
        (
            f"一次调用从 {cite0} 进入 `{name}`，由 {role} 接住。"
            if zh
            else f"A call enters `{name}` at {cite0}, where {role} takes over."
        )
    ]
    if hops:
        steps.append(
            f"{role} 把控制交给 {_cite(hops[0], None)}。"
            if zh
            else f"{role} hands control to {_cite(hops[0], None)}."
        )
    if len(hops) > 1:
        steps.append(
            f"状态或副作用落在 {_cite(hops[1], None)}。"
            if zh
            else f"State or a side effect lands in {_cite(hops[1], None)}."
        )
    elif graph is not None:
        nxt = _next_import(primary.path, graph, {f.path for f in bearing})
        if nxt:
            steps.append(
                f"随后走进 `{nxt}`（仍在这条路径上）。"
                if zh
                else f"It then walks into `{nxt}` (still on this path)."
            )
    if len(steps) < 2:
        steps.append(
            f"若 {role} 不存在，上游没有下一跳可走。"
            if zh
            else f"If {role} disappeared, upstream would have no next hop."
        )

    chain = CallChain(
        name="一次调用" if zh else "One call",
        description=(
            f"从 {cite0} 跟到本模块交出控制权。"
            if zh
            else f"Follow one call from {cite0} until this module hands off."
        ),
        steps=steps,
        files=[f.path for f in bearing[:4]],
    )
    impl = (
        f"快乐路径不从目录名开始，而从 {cite0} 开始。{role} 是这条链上的角色，不是接口清单上的一行。"
        f"顺着上面的步骤看控制流和状态；文件列表只证明这些行存在。"
        if zh
        else f"The happy path starts at {cite0}, not at a folder name. {role} is a role on that path, "
        "not a row in an interface catalog. Follow the steps for control flow and state; "
        "the file list only proves those lines exist."
    )
    return chain, impl


def _next_import(path: str, graph: DependencyGraph, in_module: set[str]) -> str | None:
    if path not in graph.graph:
        return None
    for dst in graph.graph.successors(path):
        if dst in in_module and dst != path:
            return dst
        if dst != path:
            return dst
    return None


def _load_bearing(files: list[FileInfo], graph: DependencyGraph | None) -> list[FileInfo]:
    if not files:
        return []

    def score(f: FileInfo) -> tuple:
        deg = 0
        if graph is not None and f.path in graph.graph:
            deg = graph.graph.in_degree(f.path) + graph.graph.out_degree(f.path)
        leaf = f.path.rsplit("/", 1)[-1].lower()
        hub = 1 if leaf in {"lib.rs", "mod.rs", "main.py", "main.rs", "mod.py", "__init__.py"} else 0
        return (
            1 if f.is_entrypoint else 0,
            hub,
            deg,
            f.lines or 0,
            -len(f.path),
        )

    ordered = sorted(files, key=score, reverse=True)
    seen: set[str] = set()
    out: list[FileInfo] = []
    for f in ordered:
        if f.path in seen:
            continue
        seen.add(f.path)
        out.append(f)
        if len(out) >= LOAD_BEARING_CAP:
            break
    return out


def _file_doc(f: FileInfo, primary: FileInfo | None, symbols: list[Symbol], zh: bool) -> FileDoc:
    if primary is not None and f.path == primary.path:
        if symbols:
            purpose = (
                f"快乐路径上的 `{symbols[0].name}` 落在这里"
                if zh
                else f"`{symbols[0].name}` on the happy path lives here"
            )
        else:
            purpose = "快乐路径从这里进来" if zh else "the happy path enters here"
    else:
        purpose = "路径上的下一跳" if zh else "the next hop on the path"
    return FileDoc(path=f.path, purpose=purpose, key_symbols=[])


def _cite(f: FileInfo, symbol: Symbol | None) -> str:
    line = symbol.line if symbol and symbol.line else 1
    loc = f"`{f.path}:{line}`"
    if symbol and symbol.name:
        return f"{loc} (`{symbol.name}`)"
    return loc


def _citations(bearing: list[FileInfo], symbols: list[Symbol]) -> list[Citation]:
    if not bearing:
        return []
    primary = bearing[0]
    first = symbols[0] if symbols else None
    cites = [
        Citation(
            path=primary.path,
            start_line=first.line if first and first.line else 1,
            symbol=first.name if first else "",
        )
    ]
    for f in bearing[1:4]:
        cites.append(Citation(path=f.path))
    return cites


def _edge_cases(bearing: list[FileInfo], zh: bool) -> list[str]:
    blob = "\n".join((f.content or f.preview or "") for f in bearing[:3]).lower()
    cases: list[str] = []
    if any(tok in blob for tok in ("unwrap(", "expect(", "panic!", ".unwrap()")):
        cases.append(
            "失败被 `unwrap`/`expect`/`panic` 变成进程崩溃时，调用方看不到可恢复错误。"
            if zh
            else "When failure is `unwrap`/`expect`/`panic`, callers never see a recoverable error."
        )
    if any(tok in blob for tok in ("mutex", "rwlock", "lock(", ".lock()")):
        cases.append(
            "锁未释放或被 poison 时，会话会卡住而不是干净地结束。"
            if zh
            else "If a lock is held or poisoned, the session stalls instead of ending cleanly."
        )
    if any(tok in blob for tok in ("resize", "sigwinch")):
        cases.append(
            "窗口 resize 到达时如果 PTY 已死，写入会失败，必须当成会话结束而不是重试。"
            if zh
            else "A resize after the PTY is dead must end the session, not retry the write."
        )
    if "child" in blob or "waitpid" in blob or "killed" in blob:
        cases.append(
            "子进程退出后仍去读屏，会读到空或 EIO；快乐路径在这里结束。"
            if zh
            else "Reading the screen after the child exits yields empty output or EIO; the happy path stops there."
        )
    if not cases and bearing:
        path = bearing[0].path
        cases.append(
            f"若 `{path}` 无法被调用，本模块的快乐路径根本不会开始。"
            if zh
            else f"If `{path}` cannot be called, this module's happy path never starts."
        )
    return cases[:4]


def _term_tips(zh: bool) -> list[TermTip]:
    if zh:
        return [
            TermTip(
                term="happy path",
                tip="一条真实调用从进到出；本页用它当骨架，而不是用文件树当骨架。",
            ),
            TermTip(
                term="PTY",
                tip="伪终端：字节在进程与控制器之间流动。把它当管道，不要当目录名。",
            ),
        ]
    return [
        TermTip(
            term="happy path",
            tip="One real call from ingress to effect; this page uses it as the spine, not the file tree.",
        ),
        TermTip(
            term="PTY",
            tip="A pseudo-terminal: bytes between a process and its controller. Treat it as a pipe, not a folder name.",
        ),
    ]
