#!/usr/bin/env python3
"""
Gerador de ícones PNG para o Plaud Linux.
Executado automaticamente pelo install.sh após instalar Pillow.
"""
from PIL import Image, ImageDraw
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
ASSETS.mkdir(exist_ok=True)


def make_icon(fill_rgb, size=64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size
    draw.ellipse([2, 2, s-2, s-2], fill=(*fill_rgb, 255))
    mx = s // 2
    mw = max(6, s // 9)
    mh = s // 3
    # Microfone (corpo arredondado)
    draw.rounded_rectangle([mx-mw, s//8, mx+mw, s//8+mh], radius=mw, fill=(255, 255, 255, 240))
    # Arco base
    r = s // 5
    lw = max(2, s // 22)
    draw.arc([mx-r, s//8+mh//2, mx+r, s//8+mh//2+r*2], start=0, end=180, fill=(255, 255, 255, 220), width=lw)
    # Haste
    draw.line([mx, s//8+mh//2+r*2, mx, s*3//4], fill=(255, 255, 255, 220), width=lw)
    # Base horizontal
    draw.line([mx-s//8, s*3//4, mx+s//8, s*3//4], fill=(255, 255, 255, 220), width=lw)
    return img


STATES = {
    "plaud-idle":      (45, 45, 55),
    "plaud-recording": (220, 38, 38),
    "plaud-uploading": (37, 99, 235),
}

SIZES = [16, 22, 32, 48, 64, 128, 256]

for name, fill in STATES.items():
    for sz in SIZES:
        path = ASSETS / f"{name}-{sz}.png"
        make_icon(fill, sz).save(path)
    print(f"  ✓ {name} ({', '.join(str(s) for s in SIZES)}px)")

print("Icons gerados em assets/")
