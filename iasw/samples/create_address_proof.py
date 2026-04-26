"""Script to generate a sample electricity_bill.png for address-change demo purposes.

The bill date is computed at runtime (today minus 30 days) so it always
passes the 90-day recency check during demo — never hardcoded.
"""

from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_electricity_bill() -> None:
    """Create a sample electricity bill PNG with white background and demo text."""
    output_path = Path(__file__).parent / "electricity_bill.png"

    # Bill date = 30 days ago so it always satisfies the ≤90-day recency policy.
    bill_date = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")

    img = Image.new("RGB", (800, 650), color="white")
    draw = ImageDraw.Draw(img)

    # Use system font with graceful fallback to Pillow's built-in default
    try:
        font_title = ImageFont.truetype("arial.ttf", 28)
        font_sub = ImageFont.truetype("arial.ttf", 22)
        font_body = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_body = ImageFont.load_default()

    lines = [
        ("DELHI ELECTRICITY BOARD", font_title, 50),
        ("Electricity Bill", font_sub, 100),
        ("", font_body, 140),
        ("Customer Name: Priya Sharma", font_body, 170),
        ("Address: 15 Sarojini Nagar", font_body, 220),
        ("City: New Delhi", font_body, 265),
        ("State: Delhi", font_body, 310),
        ("Pincode: 110023", font_body, 355),
        (f"Bill Date: {bill_date}", font_body, 400),
        ("Amount Due: Rs. 2,450", font_body, 445),
        ("Consumer No: DEB-2024-009812", font_body, 490),
        ("Billing Period: Monthly", font_body, 535),
        ("Official Seal: [SEAL]", font_body, 590),
    ]

    for text, font, y in lines:
        if not text:
            continue
        # Center each line horizontally
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = (800 - text_width) // 2
        draw.text((x, y), text, fill="black", font=font)

    img.save(output_path)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    create_electricity_bill()
