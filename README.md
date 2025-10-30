# Colab Setup Utilities
The `setup` package bundles helpers that prepare a private GitHub project to run smoothly inside Google Colab. These routines remove repetitive manual steps around authentication, repository synchronization, dependency installation, and notebook execution.

## Module Layout
- `setup/__init__.py` re-exports the public helper functions for concise imports, for example `from setup import clone_or_update_repo`.
- `setup/project.py` contains the implementations described in this document.

## Key Functions
- **store_credentials_from_env**: Reads GitHub credentials from environment variables (defaults `GITHUB_USERNAME`, `GITHUB_TOKEN`), writes them to `~/.netrc`, and applies strict file permissions so authenticated git operations can proceed non-interactively.
- **ensure_project_name**: Retrieves the project name from the `PROJECT_NAME` environment variable or prompts for it once, then caches the result back into the environment for consistency across helpers.
- **clone_or_update_repo**: Clones `https://github.com/<owner>/<project>.git` when absent or fast-forwards an existing checkout using `git pull --ff-only`, returning the resolved project path.
- **change_directory**: Switches the current working directory to the provided path and returns the resolved location, useful right before running project-specific commands.
- **setup_google_drive_project**: Mounts Google Drive through `google.colab.drive`, ensures a project directory under `MyDrive/projects`, manages a `/project` symlink, and exports the resulting location via `PROJECT_DIR`.
- **setup_vscode_tunnel**: Installs `vscode-colab` on demand, authenticates, and starts a VS Code tunnel named after the project so you can connect from the desktop client.
- **install_project_requirements**: Detects the installed PyTorch/CUDA versions, builds the matching PyTorch Geometric wheel index URL, upgrades `pip`, and installs dependencies from `requrment.txt`, returning the wheel index used.
- **execute_notebook**: Executes a notebook (default `eval.ipynb`) headlessly via `nbconvert`, applies a configurable timeout, and writes the executed notebook to `eval_output.ipynb` (or a provided path).

Together these utilities let you authenticate, mount storage, sync code, configure dependencies, and run evaluation notebooks with minimal manual intervention in Colab.