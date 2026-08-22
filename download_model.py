import argparse
import os
import sys
from pathlib import Path


def download_from_huggingface(repo_id: str, target_dir: Path) -> bool:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("ERROR: huggingface_hub not installed.")
        print("Install with: pip install huggingface_hub")
        return False

    print(f"Downloading model from HuggingFace: {repo_id}")
    print(f"Target directory: {target_dir}")

    try:
        # Download only best_model subdirectory
        snapshot_download(
            repo_id=repo_id,
            local_dir=target_dir,
            local_dir_use_symlinks=False,
            allow_patterns=["best_model/*", "*.json", "*.safetensors", "tokenizer*"],
        )
        print(f"SUCCESS: Model downloaded to {target_dir}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to download model: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Download trained LayoutLMv3 model for customs extraction."
    )
    parser.add_argument(
        "--huggingface-repo",
        "--repo",
        "-r",
        type=str,
        default=os.environ.get("MODEL_REPO", ""),
        help="HuggingFace repository ID (e.g., 'username/layoutlmv3-v4-best')",
    )
    parser.add_argument(
        "--target-dir",
        "-d",
        type=str,
        default=None,
        help="Target directory (default: ml/models/layoutlmv3-v4/best_model)",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing model files",
    )

    args = parser.parse_args()

    # Determine target directory
    if args.target_dir:
        target_dir = Path(args.target_dir)
    else:
        # Default to the expected model location in the project
        script_dir = Path(__file__).parent.resolve()
        target_dir = script_dir / "ml" / "models" / "layoutlmv3-v4" / "best_model"

    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # Check if model already exists
    model_file = target_dir / "model.safetensors"
    if model_file.exists() and not args.force:
        print(f"Model already exists at {target_dir}")
        print("Use --force to overwrite.")
        return 0

    # Download from HuggingFace if repo specified
    if args.huggingface_repo:
        success = download_from_huggingface(args.huggingface_repo, target_dir)
        return 0 if success else 1

    # No source specified
    print("ERROR: No model source specified.")
    print("")
    print("Options:")
    print("  1. Upload your trained model to HuggingFace Hub:")
    print("     huggingface-cli login")
    print("     # Then upload from your training environment")
    print("")
    print("  2. Specify HuggingFace repository:")
    print("     python download_model.py --huggingface-repo your-username/layoutlmv3-v4")
    print("")
    print("  3. Set MODEL_REPO environment variable:")
    print("     MODEL_REPO=your-username/layoutlmv3-v4 python download_model.py")
    print("")
    print("NOTE: Without the model, the website will use text-based extraction")
    print("      which has lower accuracy but is fully functional.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
