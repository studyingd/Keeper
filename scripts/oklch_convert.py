"""Convert the demo's OKLCH design tokens to exact sRGB hex values."""
import math


def oklch_to_rgb(L: float, C: float, H: float) -> tuple[int, int, int]:
    h = math.radians(H)
    a = C * math.cos(h)
    b = C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def gamma(x: float) -> float:
        x = min(1.0, max(0.0, x))
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055

    return tuple(round(gamma(v) * 255) for v in (r, g, bb))  # type: ignore[return-value]


TOKENS: dict[str, tuple[float, float, float]] = {
    "bg-deep": (0.145, 0.016, 235),
    "bg": (0.170, 0.018, 235),
    "surface": (0.205, 0.020, 235),
    "surface-2": (0.235, 0.022, 235),
    "border": (0.300, 0.025, 235),
    "border-soft": (0.260, 0.022, 235),
    "border-strong": (0.380, 0.030, 235),
    "text": (0.94, 0.008, 235),
    "text-muted": (0.68, 0.020, 235),
    "text-faint": (0.56, 0.018, 235),
    "accent": (0.79, 0.115, 185),
    "accent-strong": (0.845, 0.105, 185),
    "accent-deep": (0.28, 0.055, 210),
    "accent-ink": (0.19, 0.045, 205),
    "ok": (0.78, 0.15, 155),
    "warning": (0.80, 0.14, 85),
    "danger": (0.70, 0.19, 25),
    "shadow-base": (0.10, 0.02, 235),
    "sidebar-top": (0.215, 0.022, 235),
    "sidebar-bottom": (0.185, 0.020, 235),
    "btn-hover": (0.27, 0.024, 235),
    "row-hover": (0.26, 0.024, 235),
    "row-selected": (0.28, 0.045, 220),
    "primary-1": (0.86, 0.10, 185),
    "primary-2": (0.78, 0.115, 187),
    "primary-hover-1": (0.905, 0.105, 185),
    "primary-hover-2": (0.8375, 0.115, 186),
    "glow-teal": (0.24, 0.045, 210),
    "glow-blue": (0.20, 0.04, 200),
    "menu-bg": (0.255, 0.024, 235),
    "toast-bg": (0.25, 0.025, 235),
    "lock-overlay": (0.12, 0.015, 235),
}

for name, (L, C, H) in TOKENS.items():
    r, g, b = oklch_to_rgb(L, C, H)
    print(f"{name:16s} = #{r:02X}{g:02X}{b:02X}")
