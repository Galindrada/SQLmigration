#!/usr/bin/env python3
"""
Generate 200x200 AI player pictures using Stable Diffusion 1.5 (no picture database needed).

Text-to-image only: you give prompts, the model generates images.
Run in Google Colab (free GPU) or locally if you have a GPU.

Colab: Upload this script or paste the code into a notebook, then run the cells.
Local:  pip install diffusers transformers accelerate torch Pillow
        python generate_player_pictures.py
"""

import os
import random
from pathlib import Path

# Optional: run on CPU if no GPU (very slow)
DEVICE = "cuda"  # or "cpu"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "player_pictures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# How many images to generate (e.g. one per player or a batch for testing)
NUM_IMAGES = 5
# Image size from the model (will be resized to 200x200)
WIDTH, HEIGHT = 512, 512
FINAL_SIZE = 200

# Base prompt for “player portrait” – no reference images needed
# Mugshot / closeup style: tight face crop, front-facing, plain background
BASE_PROMPT = (
    "mugshot style, closeup face photo, head and shoulders, front facing, "
    "neutral expression, plain gray or white background, even lighting, "
    "passport photo style, face fill frame, sharp focus, photorealistic"
)
NEGATIVE_PROMPT = "blurry, distorted, multiple faces, cartoon, illustration, low quality, side view, profile, dramatic lighting, shadows, body shot, full body"


def get_pipeline():
    from diffusers import StableDiffusionPipeline
    import torch

    model_id = "runwayml/stable-diffusion-v1-5"
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        safety_checker=None,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    pipe = pipe.to(DEVICE)
    if DEVICE == "cpu":
        pipe.enable_attention_slicing()  # reduce memory a bit
    return pipe


def generate_and_save(pipe, prompt: str, output_path: Path, seed=None):
    from PIL import Image
    import torch

    generator = None
    if seed is not None:
        generator = torch.Generator(device=pipe.device).manual_seed(seed)

    image = pipe(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        width=WIDTH,
        height=HEIGHT,
        num_inference_steps=30,
        generator=generator,
    ).images[0]

    # Resize to 200x200 (center crop then resize if you prefer square crop)
    image = image.resize((FINAL_SIZE, FINAL_SIZE), Image.Resampling.LANCZOS)
    image.save(output_path)
    print(f"Saved: {output_path}")


def main():
    try:
        pipe = get_pipeline()
    except Exception as e:
        print("Install with: pip install diffusers transformers accelerate torch Pillow")
        raise e

    for i in range(NUM_IMAGES):
        # Vary the prompt slightly so faces differ (no picture database needed)
        seed = random.randint(0, 2**32 - 1)
        out_path = OUTPUT_DIR / f"player_{i:04d}.png"
        generate_and_save(pipe, BASE_PROMPT, out_path, seed=seed)

    print(f"Done. Images in {OUTPUT_DIR} ({FINAL_SIZE}x{FINAL_SIZE})")


if __name__ == "__main__":
    main()
