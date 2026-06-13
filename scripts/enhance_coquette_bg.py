from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


SOURCE = Path("source.jpg")
TARGET = Path("frontend/src/assets/coquette-reference-bg.png")


def main() -> None:
    image = Image.open(SOURCE).convert("RGB")

    # Keep the original pastel mood, only lift the contrast slightly so the
    # center banner and doodles read more clearly in the app background.
    image = ImageOps.autocontrast(image, cutoff=0.4)
    image = ImageEnhance.Brightness(image).enhance(1.02)
    image = ImageEnhance.Contrast(image).enhance(1.06)
    image = ImageEnhance.Color(image).enhance(1.08)

    # Blend in a gentle sharpen pass instead of a hard edge boost.
    sharpened = image.filter(ImageFilter.UnsharpMask(radius=1.5, percent=70, threshold=3))
    image = Image.blend(image, sharpened, alpha=0.35)

    # Add a tiny warm tint so it sits naturally with the coquette palette.
    tint = Image.new("RGB", image.size, (255, 248, 250))
    image = Image.blend(image, tint, alpha=0.06)

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    image.save(TARGET, format="PNG", optimize=True)
    print(TARGET)


if __name__ == "__main__":
    main()
