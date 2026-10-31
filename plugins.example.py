comfy_plugins = [
    # Custom nodes used in workflow_api.json are installed automatically.
    # Add a node here only if ComfyUI still reports it as missing.
    # IMPORTANT: node id from comfyui registry (Not node name)
]

comfy_plugins_ext = [
    # External custom nodes installed directly from git.
    # {
    #     "url": "https://github.com/owner/repo.git",
    #     "branch": "main",  # optional; omit to use the repo's default branch
    #     "requirements": ["requirements.txt", "pyproject.toml"],  # optional req files
    #     "install": "install.py",  # optional install script (.py)
    #     "ext_deps": ["numpy<2", "setuptools<=81"],  # optional extra pip packages
    # },
]
