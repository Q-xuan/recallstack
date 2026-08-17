from repowiki.core.path_class import (
    is_agent_memory_path,
    is_product_path,
    name_is_notes_product,
    product_rank,
    prose_treats_notes_as_product,
    repo_is_notes_primary,
)


def test_agent_memory_vs_product_paths():
    assert is_agent_memory_path(".agents/notes/decision-01.md")
    assert is_agent_memory_path(".agents/notes/archived/old.md")
    assert is_agent_memory_path(".i18n.yaml")
    assert not is_agent_memory_path("packages/core/src/index.ts")
    assert not is_agent_memory_path("docs/architecture.md")
    assert is_product_path("packages/core/src/plugin.ts")
    assert is_product_path("apps/dsh/src/main.ts")
    assert is_product_path("README.md")
    assert not is_product_path(".agents/notes/foo.md")


def test_notes_primary_only_when_no_product_tree():
    notes = [f".agents/notes/n{i}.md" for i in range(8)]
    assert repo_is_notes_primary(notes)
    assert not repo_is_notes_primary(notes + ["packages/core/src/index.ts"])


def test_notes_as_product_prose_and_name():
    assert name_is_notes_product("DeepSeek Harness 决策日志仓库（.agents/notes）")
    assert name_is_notes_product("notes 目录层级与生命周期")
    assert not name_is_notes_product("deepseek-harness")
    assert prose_treats_notes_as_product(
        "这个仓库不是 dsh 的源码实现，而是决策日志与架构记忆库。"
    )
    assert not prose_treats_notes_as_product(
        "DeepSeek Harness 是 plugin-based agent harness，决策日志在 `.agents/notes`。"
    )
    assert product_rank("packages/core/src/index.ts") < product_rank(
        ".agents/notes/decision-01.md"
    )
