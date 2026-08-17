from repowiki.core.models import FileInfo
from repowiki.core.scanner import build_file_tree, scan_directory


def test_scan_skips_minified_suffixes(tmp_path):
    (tmp_path / "app.min.js").write_text("console.log('packed');", encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log('source');\n", encoding="utf-8")

    files = scan_directory(tmp_path)
    paths = {f.path for f in files}

    assert "app.js" in paths
    assert "app.min.js" not in paths


def test_scan_skips_generated_bundle_lines(tmp_path):
    assets = tmp_path / "src" / "server" / "static" / "assets"
    assets.mkdir(parents=True)
    (assets / "chunk-ABC123.js").write_text("const bundle='" + ("x" * 5000) + "';", encoding="utf-8")
    source = tmp_path / "src" / "main.js"
    source.write_text("export function main() {\n  return 42;\n}\n", encoding="utf-8")

    files = scan_directory(tmp_path)
    paths = {f.path.replace("\\", "/") for f in files}

    assert "src/main.js" in paths
    assert "src/server/static/assets/chunk-ABC123.js" not in paths


def test_scan_respects_gitignore_and_repowikiignore(tmp_path):
    (tmp_path / ".gitignore").write_text("dist/\n*.log\n", encoding="utf-8")
    (tmp_path / ".repowikiignore").write_text("private.md\n", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("console.log('built');\n", encoding="utf-8")
    (tmp_path / "debug.log").write_text("noise\n", encoding="utf-8")
    (tmp_path / "private.md").write_text("local notes\n", encoding="utf-8")
    (tmp_path / "src.py").write_text("print('source')\n", encoding="utf-8")

    paths = {f.path for f in scan_directory(tmp_path)}

    assert "src.py" in paths
    assert "dist/bundle.js" not in paths
    assert "debug.log" not in paths
    assert "private.md" not in paths


def test_scan_skips_real_env_files_but_keeps_example(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=real-secret\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("TOKEN=secret\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")

    paths = {f.path for f in scan_directory(tmp_path)}

    assert ".env" not in paths
    assert ".env.local" not in paths
    assert ".env.example" in paths


def test_scanned_paths_are_posix_so_imports_can_resolve(tmp_path):
    """Nested paths must use forward slashes on every platform.

    Import resolution builds forward-slash candidates and looks them up in the
    set of scanned paths. Emitting native separators here matches nothing on
    Windows, and the dependency graph comes back with zero edges — PageRank
    goes uniform and the graph-derived pages vanish, with no error anywhere.
    """
    pkg = tmp_path / "src" / "app" / "services"
    pkg.mkdir(parents=True)
    (pkg / "users.py").write_text("def get_user(): ...\n", encoding="utf-8")

    paths = {f.path for f in scan_directory(tmp_path)}

    assert "src/app/services/users.py" in paths
    assert not any("\\" in p for p in paths)


def test_scan_walks_packages_before_agents_notes(tmp_path):
    notes = tmp_path / ".agents" / "notes"
    notes.mkdir(parents=True)
    for i in range(40):
        (notes / f"decision-{i:02d}.md").write_text(f"# n{i}\n", encoding="utf-8")
    pkg = tmp_path / "packages" / "core" / "src"
    pkg.mkdir(parents=True)
    (pkg / "index.ts").write_text("export class Harness {}\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# harness\n", encoding="utf-8")

    files = scan_directory(tmp_path, max_files=20)
    paths = [f.path.replace("\\", "/") for f in files]
    assert "packages/core/src/index.ts" in paths
    assert "README.md" in paths


def test_file_tree_collapses_agents_notes_so_packages_remain():
    files = [
        FileInfo(path="README.md", size=8, language="markdown", content="# hi\n"),
        FileInfo(
            path="packages/core/src/index.ts",
            size=20,
            language="typescript",
            content="export class Harness {}\n",
        ),
    ]
    for i in range(80):
        files.append(
            FileInfo(
                path=f".agents/notes/decision-{i:02d}.md",
                size=10,
                language="markdown",
                content=f"# n{i}\n",
            )
        )
    tree = build_file_tree(files, max_lines=30)
    assert "packages" in tree
    assert "index.ts" in tree
    assert "decision-00.md" not in tree
    assert "agent-notes files" in tree
    assert ".agents/" in tree
