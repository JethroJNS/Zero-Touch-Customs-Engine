import os
import sys
import argparse
from pathlib import Path


def download_model_from_hf(repo_id: str, target_dir: Path) -> bool:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[HF_DOWNLOAD] ERROR: huggingface_hub not installed")
        print("[HF_DOWNLOAD] Run: pip install huggingface_hub")
        return False

    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"[HF_DOWNLOAD] Downloading model from HuggingFace Hub")
    print(f"[HF_DOWNLOAD] Repo: {repo_id}")
    print(f"[HF_DOWNLOAD] Target: {target_dir}")

    # Check if model already exists
    model_file = target_dir / "model.safetensors"
    if model_file.exists():
        size_mb = model_file.stat().st_size / (1024 * 1024)
        print(f"[HF_DOWNLOAD] Model already exists ({size_mb:.1f} MB)")
        if size_mb > 100:  # Sanity check
            return True
        else:
            print(f"[HF_DOWNLOAD] Model file too small, re-downloading")
            model_file.unlink()

    try:
        # Download only necessary files
        snapshot_download(
            repo_id=repo_id,
            local_dir=target_dir,
            local_dir_use_symlinks=False,
            allow_patterns=[
                "*.safetensors",
                "*.bin",
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "vocab.txt",
                "merges.txt",
                "label_map.json",
            ],
        )

        # Verify download
        if model_file.exists():
            size_mb = model_file.stat().st_size / (1024 * 1024)
            print(f"[HF_DOWNLOAD] SUCCESS: Model downloaded ({size_mb:.1f} MB)")
            return True
        else:
            print(f"[HF_DOWNLOAD] ERROR: model.safetensors not found after download")
            return False

    except Exception as e:
        print(f"[HF_DOWNLOAD] ERROR: {type(e).__name__}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download model from HuggingFace Hub")
    parser.add_argument("--repo", "-r", type=str, default=os.environ.get("MODEL_REPO", ""),
                        help="HuggingFace repository ID (e.g., 'username/model-name')")
    parser.add_argument("--target-dir", "-d", type=str, default=None,
                        help="Target directory")

    args = parser.parse_args()

    if not args.repo:
        print("[HF_DOWNLOAD] ERROR: No repository specified")
        print("[HF_DOWNLOAD] Set MODEL_REPO environment variable or use --repo")
        return 1

    if args.target_dir:
        target_dir = Path(args.target_dir)
    else:
        script_dir = Path(__file__).parent.resolve()
        target_dir = script_dir / "ml" / "models" / "layoutlmv3-v4" / "best_model"

    success = download_model_from_hf(args.repo, target_dir)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
