"""Grouping scanned files into the modules the wiki documents.

One rule, shared by the analyzer (which writes a page per module) and by the
dependency graph (which draws edges between them), so a diagram can never point
at a module that has no page.

Module names are real repository paths — ``src/recallstack/learning``, not
``learning``. A reader who wants the code should be able to paste the title into
their editor. The sidebar shortens them for display; that is a presentation
concern and stays in the wiki builder.
"""

from __future__ import annotations

from repowiki.core.models import FileInfo

# A module large enough that one page cannot honestly describe it. Both bounds
# have to hold: twenty tiny config files still read fine as a single page, and a
# lone 3000-line file is over the limit but has no subdirectories to split into.
SPLIT_MIN_LINES = 1200
SPLIT_MIN_FILES = 6

# How many path segments a module name may have. Past three the names get long
# and the pages get thin -- a leaf directory is usually the right unit.
MAX_DEPTH = 3

# Total pages the module budget can buy. Splitting spends it on the largest
# module first, so a repository with one huge package and forty small ones
# subdivides the package rather than the noise.
MAX_MODULES = 24

# Under this a module is a footnote, not a chapter. Folding them together keeps
# a nine-line `.claude/` from taking a sidebar slot next to a core subsystem.
FOLD_MAX_LINES = 60
FOLD_NAME = "misc"

# Files that live at the repository root belong to no directory; they still need
# a page, since this is where the README and build config live.
ROOT_NAME = "root"


def _lines(files: list[FileInfo]) -> int:
    return sum(f.lines or 0 for f in files)


def _depth(name: str) -> int:
    return name.count("/") + 1 if name else 0


def _children_of(prefix: str, files: list[FileInfo]) -> dict[str, list[FileInfo]]:
    """Split `files` by their next path segment below `prefix`.

    Files sitting directly in `prefix` stay under `prefix` itself, so a
    directory that holds both loose files and subdirectories keeps a page of
    its own for the loose ones.
    """
    base = _depth(prefix)
    out: dict[str, list[FileInfo]] = {}
    for f in files:
        parts = f.path.split("/")
        if len(parts) <= base + 1:
            out.setdefault(prefix, []).append(f)
        else:
            child = "/".join(parts[: base + 1])
            out.setdefault(child, []).append(f)
    return out


def _splittable(name: str, files: list[FileInfo]) -> bool:
    return (
        _depth(name) < MAX_DEPTH
        and len(files) >= SPLIT_MIN_FILES
        and _lines(files) >= SPLIT_MIN_LINES
    )


def _fold_tiny(groups: dict[str, list[FileInfo]]) -> dict[str, list[FileInfo]]:
    tiny = [n for n, fs in groups.items() if _lines(fs) < FOLD_MAX_LINES]
    if len(tiny) < 2:
        return groups
    folded = {n: fs for n, fs in groups.items() if n not in tiny}
    folded[FOLD_NAME] = [f for n in tiny for f in groups[n]]
    return folded


def group_into_modules(
    files: list[FileInfo],
    *,
    max_modules: int = MAX_MODULES,
) -> dict[str, list[FileInfo]]:
    """Group files into documentable modules, largest-first.

    Starts from top-level directories and repeatedly subdivides whichever module
    is still too large for one page, until nothing qualifies or the budget runs
    out. Grouping by first path segment alone gives a 9000-line ``frontend``
    page next to a 9-line ``.claude`` one.
    """
    groups = _children_of("", list(files))
    blocked: set[str] = set()

    while len(groups) < max_modules:
        candidates = [n for n, fs in groups.items() if n not in blocked and _splittable(n, fs)]
        if not candidates:
            break
        target = max(candidates, key=lambda n: _lines(groups[n]))

        children = _children_of(target, groups[target])
        if not children or set(children) == {target}:
            # Every file sits directly here; there is nothing below to split on.
            blocked.add(target)
            continue

        del groups[target]
        groups.update(children)

    if root := groups.pop("", None):
        groups[ROOT_NAME] = root
    return _fold_tiny(groups)


def module_index(groups: dict[str, list[FileInfo]]) -> dict[str, str]:
    """Reverse index: file path -> the module that documents it.

    Derived from the grouping rather than recomputed from path prefixes, which
    would disagree with it wherever `misc` folding moved a file.
    """
    return {f.path: name for name, files in groups.items() for f in files}
