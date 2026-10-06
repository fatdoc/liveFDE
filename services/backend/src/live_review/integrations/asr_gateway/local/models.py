"""Lazy local-only FunASR construction; no hub resolver is called."""

import gc
import importlib.util
from pathlib import Path

from ..contracts import ASRError
from .config import LocalConfig

EXPECTED = {
    "fsmn-vad": ("FsmnVADStreaming", "model.pt"),
    "Fun-ASR-Nano-2512": ("FunASRNano", "model.pt"),
    "campplus": ("CAMPPlus", "campplus_cn_common.bin"),
    "emotion2vec_plus_base": ("Emotion2vec", "model.pt"),
    "ct-punc": ("CTTransformer", "model.pt"),
}


def model_path(config: LocalConfig, name: str) -> Path:
    if name not in EXPECTED:
        raise ASRError("local_model_unsupported")
    root = config.model_root.resolve()
    path = (root / name).resolve()
    if path.parent != root:
        raise ASRError("local_model_path_invalid")
    for filename in ("config.yaml", EXPECTED[name][1], "provision-manifest.json"):
        if not (path / filename).is_file():
            raise ASRError("local_model_missing")
    return path


def dependencies_available() -> bool:
    return all(importlib.util.find_spec(name) for name in ("funasr", "torch", "soundfile", "numpy"))


def resolve_device(device):
    if device == "mps":
        raise ASRError("local_mps_unsupported")
    if device == "cpu":
        return "cpu"
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if device == "auto":
        return "cpu"
    raise ASRError("local_cuda_unavailable")


class Models:
    def __init__(self, config: LocalConfig):
        self.config = config
        self.cache = {}

    def get(self, name):
        if name in self.cache:
            return self.cache[name]
        path = model_path(self.config, name)
        if not dependencies_available():
            raise ASRError("local_dependencies_missing")
        device = resolve_device(self.config.device)
        from funasr import AutoModel
        from omegaconf import OmegaConf

        cfg = OmegaConf.to_container(OmegaConf.load(path / "config.yaml"), resolve=True)
        expected, weight = EXPECTED[name]
        if cfg.get("model") != expected or "model_conf" not in cfg:
            raise ASRError("local_model_config_invalid")
        # Supplying model_conf bypasses FunASR's download_model entirely.
        cfg.update(
            init_param=str(path / weight),
            model_path=str(path),
            device=device,
            ncpu=self.config.cpu_threads,
            disable_update=True,
            trust_remote_code=False,
            disable_pbar=True,
            disable_log=True,
            batch_size=1,
            check_latest=False,
        )
        if name == "Fun-ASR-Nano-2512":
            llm_path = path / "Qwen3-0.6B"
            for filename in ("config.json", "tokenizer.json", "tokenizer_config.json"):
                if not (llm_path / filename).is_file():
                    raise ASRError("local_model_missing")
            cfg["llm_conf"].update(init_param_path=str(llm_path), llm_dtype="fp32")
            cfg["tokenizer_conf"].update(init_param_path=str(llm_path), local_files_only=True)
            # This checkpoint does not supply a verified CTC timestamp head.
            cfg["ctc_decoder"] = None
            cfg["llm_dtype"] = "fp32"
        elif name == "fsmn-vad":
            cfg["frontend_conf"]["cmvn_file"] = str(path / "am.mvn")
            cfg["model_conf"]["max_single_segment_time"] = self.config.vad_max_segment_ms
        elif name == "emotion2vec_plus_base":
            cfg.setdefault("tokenizer_conf", {})["token_list"] = str(path / "tokens.txt")
        elif name == "ct-punc":
            cfg.setdefault("tokenizer_conf", {})["token_list"] = str(path / "tokens.json")
        try:
            model = AutoModel(**cfg)
        except Exception as error:
            if "out of memory" in str(error).lower():
                raise ASRError("local_device_out_of_memory") from error
            raise
        self.cache[name] = model
        return model

    def generate(self, name, data, **kwargs):
        import torch

        try:
            if name == "Fun-ASR-Nano-2512":
                # Nano's chat template accepts Tensor/path, not numpy ndarray.
                data = torch.as_tensor(data, dtype=torch.float32)
            if name != "Fun-ASR-Nano-2512":
                kwargs["fs"] = 16000
            with torch.inference_mode():
                return self.get(name).generate(input=data, **kwargs)
        except torch.OutOfMemoryError as error:
            raise ASRError("local_device_out_of_memory") from error

    def clear(self):
        self.cache.clear()
        gc.collect()
        import sys

        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
