from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import modal

from models import models, models_ext
from plugins import comfy_plugins

try:
    from plugins import comfy_plugins_ext
except ImportError:
    comfy_plugins_ext = []

root_dir = Path(__file__).parent

COMFY_MODELS_ROOT = Path("/root/comfy/ComfyUI/models")

GPU_TYPE = os.getenv("MODAL_GPU", "L4")
COMFY_VER = os.getenv("COMFY_VER", "latest")

def resolve_model_dir(model_dir: str) -> Path:
    """Resolve model_dir: absolute paths are used as-is, relative paths are
    placed under /root/comfy/ComfyUI/models/ (e.g. "checkpoints")."""
    p = Path(model_dir)
    return p if p.is_absolute() else COMFY_MODELS_ROOT / p


def hf_download(
    repo_id: str,
    filename: str,
    model_dir: str = "checkpoints",
):
    import os
    import subprocess

    # Download model from Hugging Face
    from huggingface_hub import hf_hub_download

    model = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        cache_dir="/cache",
        token=os.environ.get("HF_TOKEN"),
    )

    target_dir = resolve_model_dir(model_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    local_filename = Path(filename).name
    target_path = target_dir / local_filename
    if target_path.exists() or target_path.is_symlink():
        target_path.unlink()
    _ = subprocess.run(
        f"ln -s {model} {target_path}",
        shell=True,
        check=True,
    )
    print(f"Downloaded {repo_id}/{filename} to {target_path}")


def download_external_model(url: str, filename: str, model_dir: str):
    import subprocess

    cache_dir = "/cache"
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    cached_path = Path(cache_dir) / filename
    if not cached_path.exists():
        print(f"Downloading {filename} from {url}...")
        # Use CivitAI token when available
        token_hdr = ""
        if url.startswith("https://civitai.com/") or url.startswith("https://civitai.red/"):
            token = os.environ.get("CIVITAI_TOKEN", "")
            if token:
                token_hdr = f"Authorization: Bearer {token}"
            
        try:
            _ = subprocess.run(
                [
                    "axel",
                    "-H", token_hdr,
                    "-n", "16",
                    "-o", cached_path,
                    url,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            print("STDERR:", e.stderr)
            raise

    target_dir = resolve_model_dir(model_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    # Remove existing file/link if it exists to ensure fresh link
    if target_path.exists() or target_path.is_symlink():
        target_path.unlink()

    # Create symlink
    target_path.symlink_to(cached_path)
    print(f"Linked {filename} to {target_path}")


def download_all():
    for model in models:
        hf_download(model["repo_id"], model["filename"], model["model_dir"])

    for model in models_ext:
        download_external_model(model["url"], model["filename"], model["model_dir"])


vol = modal.Volume.from_name("hf-hub-cache", create_if_missing=True)

# construct images and install deps/custom nodes
image = (
    modal.Image.debian_slim(python_version="3.11")
    .add_local_python_source("models", "plugins", copy=True)
    .apt_install("git", "git-lfs", "libgl1-mesa-dev", "libglib2.0-0", "axel")
    .pip_install_from_requirements(str(root_dir / "requirements_comfy.txt"))
    .run_commands(f"comfy --skip-prompt install --nvidia --version {COMFY_VER}")
    .run_commands("git lfs install")
)

def _hf_secrets() -> list[modal.Secret]:
    """Prefer Modal Secret 'huggingface-secret'; fall back to local HF_TOKEN
    env. Public models work even when both are absent (warned)."""
    try:
        s = modal.Secret.from_name("huggingface-secret")
        s.hydrate()  # from_name is lazy, force the existence check here
        return [s]
    except modal.exception.NotFoundError:
        hf_token = os.environ.get("HF_TOKEN", "")
        civ_token = os.environ.get("CIVITAI_TOKEN", "")
        if not hf_token:
            print(
                "Warning: no Modal Secret 'huggingface-secret' and no HF_TOKEN env. "
                "Public models will download with throttled bandwidth; "
                "gated models will fail."
            )
        return [modal.Secret.from_dict({"HF_TOKEN": hf_token, "CIVITAI_TOKEN": civ_token})]

# download models
image = image.env(
    {"HF_HUB_ENABLE_HF_TRANSFER": "1", "HF_XET_HIGH_PERFORMANCE": "1"}
).run_function(download_all, volumes={"/cache": vol}, secrets=_hf_secrets())


# setup custom nodes
workflow_file_path = Path(__file__).parent / "workflow_api.json"
if workflow_file_path.exists():
    image = image.add_local_file(
        workflow_file_path, "/root/workflow_api.json", copy=True
    ).run_commands("comfy node install-deps --workflow=/root/workflow_api.json")
else:
    print(
        f"Warning: {workflow_file_path} not found. API endpoint might not work without a workflow."
    )

if comfy_plugins:
    image = image.run_commands("comfy node install " + " ".join(comfy_plugins))


def install_ext_plugin(image: modal.Image, plugin: dict) -> modal.Image:
    """Install one external custom node from git into ComfyUI's custom_nodes.

    Supports optional ``branch``, ``requirements`` (a list of requirement
    files), an ``install`` script (.py), and ``ext_deps`` (a list of extra pip
    packages). User-supplied values are shell-quoted before use.
    """
    nodes_dir = "/root/comfy/ComfyUI/custom_nodes"
    url = plugin["url"]
    name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    work_dir = f"{nodes_dir}/{shlex.quote(name)}"

    branch = plugin.get("branch", "").strip()
    branch_opt = f"--branch {shlex.quote(branch)} " if branch else ""
    image = image.run_commands(
        f"cd {nodes_dir} && git clone --recurse-submodules --single-branch "
        f"{branch_opt}{shlex.quote(url)}"
    )

    requirements = plugin.get("requirements") or []
    if requirements:
        files = " ".join(f"-r {shlex.quote(f)}" for f in requirements)
        # --no-deps so a node's requirements can't pull a CPU-only torch over
        # the CUDA build; use "ext_deps" below to add back what's needed.
        image = image.run_commands(
            f"cd {work_dir} && uv pip install --no-deps "
            f"--python $(command -v python) --compile-bytecode {files}"
        )

    install = plugin.get("install", "").strip()
    if install:
        if install.endswith(".py"):
            image = image.run_commands(f"cd {work_dir} && python {shlex.quote(install)}")
        else:
            print(f"Unsupported installation script: {install}")

    ext_deps = plugin.get("ext_deps") or []
    if ext_deps:
        image = image.uv_pip_install(ext_deps, extra_options="--no-deps")

    return image


if comfy_plugins_ext:
    for plugin in comfy_plugins_ext:
        image = install_ext_plugin(image, plugin)

# Bake in the reverse-proxy fix so workflow save works behind Modal's edge
# proxy, independent of user plugin config (see vendor_nodes/reverse_proxy_fix).
image = image.add_local_dir(
    root_dir / "vendor_nodes" / "reverse_proxy_fix",
    "/root/comfy/ComfyUI/custom_nodes/reverse_proxy_fix",
    copy=True,
)


def wait_for_port(port: int, timeout: int = 60):
    """Block until the port is accepting connections."""
    import time
    import socket
    
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return  # port is open — ComfyUI is ready
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"ComfyUI never became ready on port {port}")
    
app = modal.App(name="modal-comfyui", image=image)


@app.cls(
    max_containers=1,
    gpu=GPU_TYPE,
    volumes={"/cache": vol},
    scaledown_window=60,  # idle 1 minutes to shutdown
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
@modal.concurrent(max_inputs=10)
class ComfyUI:
    @modal.enter(snap=True)
    def start_checkpoint(self):
        self.proc = subprocess.Popen(
            "comfy launch --background -- --listen 0.0.0.0 --port 8000", shell=True
        )
        # Block here — snapshot is taken only after this returns
        wait_for_port(8000, timeout=300)

    @modal.enter(snap=False)
    def start_restore(self):
        wait_for_port(8000, timeout=30)
        print("App Restored!")
    
    @modal.web_server(8000, startup_timeout=300)
    def ui(self):
        print("App Ready!")
    
    @modal.exit()
    def cleanup(self):
        proc = getattr(self, "proc", None)
        if proc is not None:
            try:
                proc.terminate()
            except (ProcessLookupError, OSError):
                pass
        print("App CleanUp!")
