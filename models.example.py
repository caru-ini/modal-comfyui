# Models to download during image build.
#
# `model_dir` accepts two styles:
#
#   1. Relative path (recommended for standard ComfyUI model folders):
#        "checkpoints"       -> /root/comfy/ComfyUI/models/checkpoints
#        "loras/wan22"       -> /root/comfy/ComfyUI/models/loras/wan22
#
#   2. Absolute path (use when the target is outside ComfyUI/models/,
#      e.g. a custom node's own model directory):
#        "/root/comfy/ComfyUI/custom_nodes/ComfyUI-ReActor/models/insightface"
#
# Common subdirectories under ComfyUI/models/:
#   checkpoints, diffusion_models, vae, loras, text_encoders,
#   clip_vision, controlnet, upscale_models, embeddings.

models = [
    # Hugging Face downloads (via huggingface_hub).
    # {
    #     "repo_id": "HF_REPO_ID",
    #     "filename": "FILENAME",
    #     "model_dir": "checkpoints",
    # },
]

models_ext = [
    # External downloads (via aria2c). Use for civitai, direct URLs, etc.
    # {
    #     "url": "URL",
    #     "filename": "FILENAME",
    #     "model_dir": "loras",
    # },
]
