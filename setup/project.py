"""Utility functions for configuring a local clone of a private GitHub project."""

from __future__ import annotations

import importlib
import os
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import os



def tunnel_cloudflare():
    print("--- Starting SSH and Cloudflare Tunnel Setup ---")
    # --- CONFIGURATION ---
    # 1. import from env
    USER_PUBLIC_KEY = _require_env("USER_PUBLIC_KEY")
    CF_TUNNEL_TOKEN = _require_env("CF_TUNNEL_TOKEN")
    CF_DOMAIN = _require_env("CF_DOMAIN")
    # 1. Install Dependencies
    !apt-get update -qq && apt-get install -y openssh-server -qq > /dev/null
    !curl -L --progress-bar https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
    !chmod +x /usr/local/bin/cloudflared
    
    # 2. Configure SSH with Public Key
    !mkdir -p /root/.ssh
    with open("/root/.ssh/authorized_keys", "w") as f:
        f.write(USER_PUBLIC_KEY)
    !chmod 700 /root/.ssh
    !chmod 600 /root/.ssh/authorized_keys
    !service ssh start
    print("[✓] SSH Server started with Public Key authentication.")

    # 3. Launch Cloudflare Tunnel
    # We run this in the background using '&'
    get_ipython().system_raw(f'/usr/local/bin/cloudflared tunnel --no-autoupdate run --token {CF_TUNNEL_TOKEN} > /content/tunnel.log 2>&1 &')
    
    print(f"[✓] Tunnel active. Point {CF_DOMAIN} to this tunnel in Cloudflare Dashboard.")
    print(f"--- You can now connect via: ssh root@{CF_DOMAIN} ---")


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


def setup_google_drive_project(
    project_name: Optional[str] = None,
    *,
    mount_point: str = "/content/gdrive",
    projects_root: str = "/content/gdrive/MyDrive/projects",
    symlink_path: str = "/project",
) -> Path:
    """Mount Google Drive and ensure a project directory exists for the given project."""

    try:
        drive = importlib.import_module("google.colab.drive")
    except ImportError as exc:  # pragma: no cover - accessible only within Colab
        raise RuntimeError("google.colab.drive is unavailable; this helper only works in Google Colab.") from exc

    project_name = project_name or ensure_project_name()
    drive.mount(mount_point, force_remount=False)

    projects_root_path = Path(projects_root)
    projects_root_path.mkdir(parents=True, exist_ok=True)

    symlink_target = projects_root_path
    symlink = Path(symlink_path)
    if symlink.exists():
        if not symlink.is_symlink() or symlink.resolve() != symlink_target:
            raise RuntimeError(
                f"Symlink location {symlink} exists and does not point to {symlink_target}; adjust the notebook configuration."
            )
    else:
        symlink.symlink_to(symlink_target)
    print(f"Google Drive project directory linked to: {symlink_target!s}")
    out_dir = symlink / project_name
    #out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def setup_vscode_tunnel() -> object:
    """Install vscode-colab if needed, log in,"""

    try:
        vscode_colab = importlib.import_module("vscode_colab")
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "vscode-colab"], check=True)
        vscode_colab = importlib.import_module("vscode_colab")

    vscode_colab.login()
    return vscode_colab


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

def install_pyg(downgrade_torch: bool = True,dry_run=False) -> None:
    """Install PyG and dependencies, downgrading PyTorch if necessary."""
    torch_version, cuda_version = _torch_versions()
    print(f"Detected PyTorch version: {torch_version}, CUDA version: {cuda_version or 'CPU only'}")

    if cuda_version:
        cuda_suffix = f"cu{cuda_version.replace('.', '')}"
    else:
        cuda_suffix = "cpu"
    #https://pytorch-geometric.readthedocs.io/en/latest/install/installation.html
    base_url = "https://data.pyg.org/whl"

    def check_url(url: str) -> bool:
        try:
            with urllib.request.urlopen(url) as response:
                return response.status == 200
        except urllib.error.URLError:
            return False

    # Check current version
    current_index_url = f"{base_url}/torch-{torch_version}+{cuda_suffix}.html"
    index_url = None

    if check_url(current_index_url):
        index_url = current_index_url
    elif downgrade_torch:
        # Fallback versions to check
        candidates = [
            "2.8.1",
            "2.8.0",
            "2.7.2",
            "2.7.1",
            "2.7.0",
            "2.6.3",
            "2.6.2",
            "2.6.1",
            "2.6.0",
            "2.5.1",
            "2.5.0",
            "2.4.1",
            "2.4.0",
            "2.3.1",
            "2.3.0",
            "2.2.2",
            "2.2.1",
            "2.2.0",
            "2.1.2",
            "2.1.1",
            "2.1.0",
            "2.0.1",
            "2.0.0",
        ]
        found_version = None
        for ver in candidates:
            if ver == torch_version:
                continue
            url = f"{base_url}/torch-{ver}+{cuda_suffix}.html"
            if check_url(url):
                found_version = ver
                index_url = url
                break

        if found_version:
            print(f"Downgrading PyTorch to {found_version} to match PyG wheels...")
            cmd=[sys.executable, "-m", "pip", "install", f"torch=={found_version}"]
            if not dry_run:
                subprocess.run(
                    cmd,
                    check=True,
                )
            else:
                print(f"[Dry Run] Would run: {' '.join(cmd)}")
        else:
            raise RuntimeError(
                f"Could not find compatible PyG wheels for CUDA {cuda_suffix} and recent PyTorch versions."
            )
    else:
        raise RuntimeError(
            f"PyG wheels not found for torch-{torch_version}+{cuda_suffix} and downgrade_torch is False."
        )

    if index_url is None:
        raise RuntimeError("Could not determine PyG index URL.")

    # Install packages
    print(f"Installing PyG packages using index: {index_url}")
    pkgs = [
        "torch_geometric",
        "pyg_lib",
        "torch_scatter",
        "torch_sparse",
        "torch_cluster",
        "torch_spline_conv",
    ]
    cmd = [sys.executable, "-m", "pip", "install"] + pkgs + ["-f", index_url]
    if not dry_run:
        subprocess.run(cmd, check=True)
    else:
        print(f"[Dry Run] Would run: {' '.join(cmd)}")


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


def run_notebook_in_background(
    input_notebook: Path | str='eval.ipynb',
    output_notebook: Path | str | None = None,
    log_file_path: Path | str | None = None,
    convert_to_script: bool = True,
    bash_script: str | None = None,
    python_executable: str = sys.executable,
) -> subprocess.Popen | None:
    """Convert a notebook to a script and run it in the background, logging output.

    When no log file is provided the script's path is suffixed with ".out" and used.
    """
    #raise error when convert_to_script is False and output_notebook is not provided
    if not convert_to_script and output_notebook is None:
        raise ValueError("output_notebook must be provided when convert_to_script is False.")
    notebook = Path(input_notebook).resolve()
    if notebook.suffix.lower() != ".ipynb":
        raise ValueError(f"Notebook path must end with .ipynb: {notebook!s}")
    if log_file_path is None:
        log_path = Path(str(input_notebook) + ".out")
    else:
        log_path = Path(log_file_path)
    log_path = log_path.expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if bash_script is not None:
        print(f"Making bash script to run notebook {notebook.name!s}, logging to {log_path!s}")
        with open(bash_script, "w") as f:
            f.write("#!/bin/bash\n")
    if convert_to_script:
        script = notebook.with_suffix(".py")
        cmd1=["jupyter", "nbconvert", "--to", "script", str(notebook)]
        if bash_script is not None:
            #append to bash file
            with open(bash_script,"a") as f:
                 f.write(f"{' '.join(cmd1)} > {log_path} 2>&1\n")
        else:
            subprocess.run(cmd1, check=True)
            if not script.exists():
                raise FileNotFoundError(f"Converted script not found at {script!s}")

        cmd = [python_executable, str(script)]
    else:
        cmd=[
        "jupyter",
        "nbconvert",
        "--to",
        "notebook",
        "--execute",
        str(notebook),
        "--output",
        str(output_notebook)
    ]
        
    if bash_script is None:
        print(f"Starting background process for notebook {notebook.name!s}, logging to {log_path!s}")
        with log_path.open("ab") as log_file:
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        return process
    else:
        #return content of bash script
        with open(bash_script,"a") as f:
            f.write(f"{' '.join(cmd)} > {log_path} 2>&1 &\n")
        print(f"Bash script {bash_script} created to run notebook {notebook.name!s}, logging to {log_path!s}")
        return None
