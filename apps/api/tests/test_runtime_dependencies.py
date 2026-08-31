import re
import tomllib
from pathlib import Path


def dependency_name(requirement: str) -> str:
    return re.split(r"[\[<>=!~ ]", requirement.strip(), maxsplit=1)[0].lower()


def test_railway_requirements_match_project_runtime_dependencies() -> None:
    api_root = Path(__file__).parents[1]
    project = tomllib.loads((api_root / "pyproject.toml").read_text())
    project_dependencies = {
        dependency_name(requirement) for requirement in project["project"]["dependencies"]
    }
    railway_dependencies = {
        dependency_name(requirement)
        for requirement in (api_root / "requirements.txt").read_text().splitlines()
        if requirement.strip() and not requirement.lstrip().startswith("#")
    }

    assert railway_dependencies == project_dependencies
