import re
from pathlib import Path

from app.main import SEED_CATEGORIES

OLD_CONSTANT = "CATEGORY_" + "HIERARCHY"
GROUPS = list(SEED_CATEGORIES)
SUBCATEGORIES = [c for cats in SEED_CATEGORIES.values() for c in cats]
DB_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:sqlalchemy|app\.database|app\.repositories|app\.models)\b", re.M)


def _violations(services_root: Path) -> list[str]:
    found = []
    for path in sorted(services_root.rglob("*.py")):
        text = path.read_text()
        rel = path.relative_to(services_root).as_posix()
        in_agents = "agents" in path.relative_to(services_root).parts[:-1]
        if OLD_CONSTANT in text:
            found.append(f"{rel}: old taxonomy constant")
        if in_agents:
            if any(g in text for g in GROUPS):
                found.append(f"{rel}: seed group name in agents")
            if any(f'"{c}"' in text or f"'{c}'" in text for c in SUBCATEGORIES):
                found.append(f"{rel}: seed subcategory literal in agents")
            if DB_IMPORT.search(text):
                found.append(f"{rel}: DB import in agents")
        elif sum(g in text for g in GROUPS) >= 2:
            found.append(f"{rel}: copy of the taxonomy")
    return found


def test_real_services_tree_is_clean():
    assert _violations(Path(__file__).resolve().parents[1] / "app" / "services") == []


def test_guard_catches_each_violation_type(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    (tmp_path / "x.py").write_text(f"{OLD_CONSTANT} = {{}}\n")
    (agents / "y.py").write_text('X = "Home Expenses"\n')
    (agents / "z.py").write_text("from app.repositories import CategoryRepository\n")
    (tmp_path / "w.py").write_text('A = "Home Expenses"\nB = "Health Care"\n')
    (tmp_path / "v.py").write_text('A = "Insurance, Tax & Bank Fees"\n')

    found = " | ".join(_violations(tmp_path))

    for name in ("x.py", "y.py", "z.py", "w.py"):
        assert name in found
    assert "v.py" not in found
