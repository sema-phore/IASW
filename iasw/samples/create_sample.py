"""Script to generate sample marriage_cert.png for demo purposes."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_marriage_certificate() -> None:
    """Create a sample marriage certificate PNG with white background and demo text."""
    output_path = Path(__file__).parent / "marriage_cert.png"

    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)

    # Use default font (no external font file required)
    try:
        font_title = ImageFont.truetype("arial.ttf", 28)
        font_body = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        # Fallback to Pillow's built-in default font
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()

    lines = [
        ("MARRIAGE CERTIFICATE", font_title, 60),
        ("This certifies that", font_body, 120),
        ("Bride Name: Dr.Shivani Raidas", font_body, 180),
        ("Groom Name: Dr.Pankaj Behera", font_body, 230),
        ("Married Name: Dr.Shivani Behera", font_body, 280),
        ("Date of Marriage: 2nd March 2025", font_body, 330),
        ("Issued by: Municipal Corporation of Delhi", font_body, 380),
        ("Official Seal: [SEAL]", font_body, 450),
    ]

    for text, font, y in lines:
        # Center each line horizontally
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = (800 - text_width) // 2
        draw.text((x, y), text, fill="black", font=font)

    img.save(output_path)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    create_marriage_certificate()
