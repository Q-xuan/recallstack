from repowiki.core.models import FileInfo
from repowiki.core.modules import FOLD_NAME, ROOT_NAME, group_into_modules, module_index


def _files(spec: dict[str, int]) -> list[FileInfo]:
    return [
        FileInfo(path=path, size=lines * 40, language="python", lines=lines)
        for path, lines in spec.items()
    ]


def _big(prefix: str, count: int, lines: int) -> dict[str, int]:
    return {f"{prefix}/mod{i}.py": lines for i in range(count)}


def test_a_large_package_is_split_by_its_subdirectories():
    """One page cannot carry a 5000-line package.

    Grouping by first path segment alone gave `frontend` a single page for nine
    thousand lines while a nine-line directory got one of its own.
    """
    files = _files({**_big("app/api", 8, 300), **_big("app/db", 8, 300)})

    groups = group_into_modules(files)

    assert set(groups) == {"app/api", "app/db"}


def test_small_packages_are_left_whole():
    files = _files(_big("app/api", 8, 10))

    groups = group_into_modules(files)

    assert set(groups) == {"app"}


def test_loose_files_keep_a_page_beside_their_subdirectories():
    files = _files({
        "app/main.py": 400,
        "app/settings.py": 400,
        **_big("app/api", 8, 300),
    })

    groups = group_into_modules(files)

    assert groups.keys() >= {"app", "app/api"}
    assert {f.path for f in groups["app"]} == {"app/main.py", "app/settings.py"}


def test_repository_root_files_get_their_own_module():
    files = _files({"README.md": 40, "Makefile": 30, "pyproject.toml": 20})

    groups = group_into_modules(files)

    assert set(groups) == {ROOT_NAME}


def test_trivial_directories_are_folded_together():
    """A nine-line directory should not sit in the sidebar next to a subsystem."""
    files = _files({
        **_big("app", 8, 300),
        ".claude/settings.json": 4,
        "fixtures/sample.txt": 5,
    })

    groups = group_into_modules(files)

    assert ".claude" not in groups
    assert "fixtures" not in groups
    assert {f.path for f in groups[FOLD_NAME]} == {".claude/settings.json", "fixtures/sample.txt"}


def test_splitting_spends_the_budget_on_the_largest_package_first():
    """The budget caps subdivision, not the count of real top-level directories.

    Once it is exhausted the remaining packages stay whole, so a repository with
    one dominant package subdivides that one rather than fragmenting evenly.
    """
    files = _files({
        **_big("big/a", 4, 900), **_big("big/b", 4, 900),
        **_big("small/a", 4, 200), **_big("small/b", 4, 200),
    })

    groups = group_into_modules(files, max_modules=3)

    assert groups.keys() == {"big/a", "big/b", "small"}


def test_every_file_lands_in_exactly_one_module():
    files = _files({
        **_big("app/api", 8, 300),
        **_big("app/db", 8, 300),
        "README.md": 20,
        ".claude/x.json": 3,
    })

    groups = group_into_modules(files)
    index = module_index(groups)

    assert set(index) == {f.path for f in files}
    assert sum(len(v) for v in groups.values()) == len(files)
