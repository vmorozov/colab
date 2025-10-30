"""Utility functions for configuring a local clone of a private GitHub project."""

from __future__ import annotations

import importlib
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _require_env(var_name: str) -> str:
    value = os.environ.get(var_name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {var_name} must be set before calling this function.")
    return value


def store_credentials_from_env(username_var: str = "GITHUB_USERNAME", token_var: str = "GITHUB_TOKEN", netrc_path: Optional[Path] = None) -> Path:
    """Persist GitHub credentials from the environment into a ~/.netrc file."""

    username = _require_env(username_var)
    token = _require_env(token_var)

    target_path = Path(netrc_path) if netrc_path is not None else Path.home() / ".netrc"
    content = "".join(
        (
            "machine github.com\n",
            f"login {username}\n",
            f"password {token}\n",
        )
    )
    target_path.write_text(content)
    target_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return target_path


def ensure_project_name(var_name: str = "PROJECT_NAME") -> str:
    """Return the project name from the environment, prompting the user if missing."""

    project_name = os.environ.get(var_name, "").strip()
    if not project_name:
        project_name = input("Enter your project name: ").strip()
        if not project_name:
            raise RuntimeError("Project name is required to continue.")
        os.environ[var_name] = project_name
    return project_name


def clone_or_update_repo(owner: str, project_name: str, destination: Optional[Path] = None) -> Path:
    """Clone a GitHub repository (or fast-forward it if already present)."""

    repo_url = f"https://github.com/{owner}/{project_name}.git"
    target_dir = Path(destination) if destination is not None else Path(project_name)

    if target_dir.exists():
        subprocess.run(["git", "-C", str(target_dir), "pull", "--ff-only"], check=True)
    else:
        subprocess.run(["git", "clone", repo_url, str(target_dir)], check=True)

    return target_dir.resolve()


def change_directory(path: Path) -> Path:
    """Switch the working directory to a given path, returning the resolved location."""

    resolved = Path(path).resolve()
    os.chdir(resolved)
    return resolved


def _torch_versions() -> tuple[str, Optional[str]]:
    try:
        torch = importlib.import_module("torch")
    except ImportError as exc:  # pragma: no cover - best effort guard for missing dependency
        raise RuntimeError("torch must be installed before installing project requirements.") from exc

    torch_version = torch.__version__.split("+")[0]
    cuda_version = getattr(torch.version, "cuda", None)
    return torch_version, cuda_version


def _build_pyg_index() -> str:
    torch_version, cuda_version = _torch_versions()
    cuda_suffix = f"cu{cuda_version.replace('.', '')}" if cuda_version else "cpu"
    return f"https://data.pyg.org/whl/torch-{torch_version}+{cuda_suffix}.html"


def install_project_requirements(requirements_file: Path | str = "requrment.txt") -> str:
    """Install project requirements, returning the PyG index URL that was used."""

    requirements_path = Path(requirements_file)
    if not requirements_path.exists():
        raise FileNotFoundError(f"Missing requirements file at {requirements_path!s}.")

    index_url = _build_pyg_index()
    env = os.environ.copy()
    env["PYG_WHEEL_INDEX"] = index_url

    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True, env=env)
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements_path), "-f", index_url], check=True, env=env)
    return index_url


def execute_notebook(
    input_notebook: Path | str = "eval.ipynb",
    output_notebook: Path | str = "eval_output.ipynb",
    timeout: int = 900,
) -> Path:
    """Execute a notebook with nbconvert and return the output notebook path."""

    output_path = Path(output_notebook)
    command = [
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        str(input_notebook),
        "--output",
        str(output_path),
        f"--ExecutePreprocessor.timeout={timeout}",
    ]
    subprocess.run(command, check=True)
    return output_path.resolve()
