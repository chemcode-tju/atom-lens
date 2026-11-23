"""Create editable atom-only SVG assets and render them with Inkscape."""
from __future__ import annotations

# Configuration
inkscape_path = "/Applications/Inkscape.app/Contents/MacOS/inkscape"

from pathlib import Path
import subprocess


def atom_symbol(foreground: str, orbit_color: str, stroke_width: float = 5.5) -> str:
    """Keep the nucleus centered and distribute three electrons symmetrically."""
    orbits = "\n".join(
        f'<ellipse cx="128" cy="128" rx="84" ry="32" transform="rotate({angle} 128 128)"/>'
        for angle in (0, 60, -60)
    )
    return (
        f'<g fill="none" stroke="{orbit_color}" stroke-width="{stroke_width}">\n{orbits}\n</g>\n'
        f'<g fill="{foreground}">\n'
        '<circle cx="128" cy="128" r="11"/>\n'
        '<circle cx="212" cy="128" r="8"/>\n'
        '<circle cx="86" cy="55.254" r="8"/>\n'
        '<circle cx="86" cy="200.746" r="8"/>\n</g>'
    )


def app_symbol(stroke_width: float = 5.5) -> str:
    """Inset the macOS tile and center the atom within its visible surface."""
    return (
        '<rect x="100" y="100" width="824" height="824" rx="184" '
        'fill="#FAFAFA" stroke="#DCDCDC" stroke-width="2"/>\n'
        '<g transform="translate(102.4 102.4) scale(3.2)">\n'
        f'{atom_symbol("#202020", "#505050", stroke_width)}\n</g>'
    )


def svg_document(body: str, width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n<title>Atom Lens</title>\n{body}\n</svg>\n'
    )


def preview_document() -> str:
    """Show one design at app-icon scale and at actual interface sizes."""
    parts = [
        '<defs>',
        f'<g id="app">{app_symbol()}</g>',
        f'<g id="light">{atom_symbol("#202020", "#505050", 7.5)}</g>',
        f'<g id="dark">{atom_symbol("#F4F4F4", "#CCCCCC", 7.5)}</g>',
        '</defs>',
        '<rect width="1000" height="560" fill="#F5F5F5"/>',
        '<g font-family="Arial, PingFang SC, sans-serif">',
        '<text x="48" y="62" font-size="30" fill="#202020">Atom Lens</text>',
        '<text x="48" y="96" font-size="17" fill="#737373">原子核与电子 · 黑白灰</text>',
        '<rect x="48" y="128" width="336" height="356" rx="16" fill="white"/>',
        '<use href="#app" transform="translate(72 144) scale(0.28125)"/>',
        '<text x="216" y="455" text-anchor="middle" font-size="16" fill="#737373">macOS 应用图标</text>',
    ]
    for y, background, foreground, symbol in ((148, "#FFFFFF", "#202020", "light"),
                                               (254, "#202020", "#F4F4F4", "dark")):
        parts.extend([
            f'<rect x="424" y="{y}" width="528" height="78" rx="12" fill="{background}"/>',
            f'<use href="#{symbol}" transform="translate(448 {y + 23}) scale(0.125)"/>',
            f'<text x="494" y="{y + 46}" font-size="19" fill="{foreground}">Atom Lens</text>',
            f'<text x="900" y="{y + 45}" text-anchor="end" font-size="14" fill="#888888">界面标识</text>',
        ])
    for x, size in ((464, 64), (624, 32), (752, 24), (864, 16)):
        parts.extend([
            f'<use href="#light" transform="translate({x} {410 - size / 2}) scale({size / 256})"/>',
            f'<text x="{x + size / 2}" y="472" text-anchor="middle" font-size="14" fill="#737373">{size} px</text>',
        ])
    parts.extend(['<text x="48" y="528" font-size="15" fill="#737373">去掉放大镜 · 原子居中放大 · 应用图标留白统一 · 小尺寸加重线条</text>', '</g>'])
    return svg_document("\n".join(parts), 1000, 560)


def main() -> None:
    folder = Path(__file__).resolve().parent
    documents = (
        ("atom-lens", svg_document(atom_symbol("#202020", "#505050"), 256, 256)),
        ("atom-lens-dark", svg_document(atom_symbol("#F4F4F4", "#CCCCCC"), 256, 256)),
        ("app-icon", svg_document(app_symbol(), 1024, 1024)),
        ("app-icon-small", svg_document(app_symbol(7.5), 1024, 1024)),
        ("refined-preview", preview_document()),
    )
    for name, document in documents:
        source = folder / f"{name}.svg"
        source.write_text(document, encoding="utf-8")
        subprocess.run([inkscape_path, str(source), "--export-type=png",
                        f"--export-filename={folder / f'{name}.png'}"], check=True)


if __name__ == "__main__":
    main()
