comfy_plugins = [
    # put comfyui custom node id here
    # IMPORTANT: node id from comfyui registry (Not node name)
]

comfy_plugins_ext = [
    # External downloads (via git).
    # {
    #     "url": "URL",
    #     "branch": "BRANCH", # Branch or Tag name
    #     "requirements": "pyproject.toml requirements.txt", 
    #     "install": "install.py", # or "setup.py"
    #     "dependencies": "numpy<2 setuptools<=81 kernels~=0.12.0", # optional packages, or in case there are dependencies issue with other custom nodes
    # },
    {
        # Fix error 405 when saving a workflow
        "url": "https://github.com/Echoflare/ComfyUI-Reverse-Proxy-Fix.git",
        "branch": "main",
    },
