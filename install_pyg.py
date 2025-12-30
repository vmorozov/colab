
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

def install_pyg(downgrade_torch: bool = True,dry_run=False,dependencies: str = "pyg_lib torch_scatter torch_sparse torch_cluster torch_spline_conv") -> None:
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
        #generate cndidades by downgrading torch_version by 0.1
        candidates = [torch_version]
        for i in range(5):
            candidates.append(str(float(torch_version) - 0.1))
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
        "torch_geometric"
    ]
    if dependencies:
        pkgs.append(dependencies.split(" "))
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


if __name__ == "__main__":
    install_pyg()
    install_project_requirements()