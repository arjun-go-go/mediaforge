"""Platform-specific image generation and audit rules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformImageRule:
    main_aspect_ratio: str
    detail_aspect_ratio: str
    main_prompt: str
    scene_main_prompt: str
    detail_prompt: str
    main_audit: str
    detail_audit: str
    require_white_border: bool = False


_COMMON_DETAIL_PROMPT = (
    "Create a clear 3:4 product-detail asset. Keep the exact product identity, use no "
    "watermark, QR code, third-party marketplace logo or invented promotional text."
)

SUPPORTED_PLATFORMS = frozenset(
    {"amazon", "taobao", "tmall", "jd", "pinduoduo", "shopee", "lazada", "shein", "temu"}
)

_PLATFORM_MARKETS = {
    "taobao": "CN",
    "tmall": "CN",
    "jd": "CN",
    "pinduoduo": "CN",
    "shopee": "SG",
    "lazada": "SG",
    "amazon": "US",
    "shein": "US",
    "temu": "US",
}


PLATFORM_IMAGE_RULES: dict[str, PlatformImageRule] = {
    "amazon": PlatformImageRule(
        main_aspect_ratio="1:1",
        detail_aspect_ratio="3:4",
        main_prompt=(
            "Amazon MAIN image rules: use a pure white RGB 255,255,255 background; show only "
            "the actual product being sold; keep the complete product centered and filling about "
            "85% of the frame; do not add text, graphics, borders, color blocks, watermarks, "
            "packaging or props that are not included. Adult apparel may use a standing model, "
            "but the complete sellable garment must remain visible."
        ),
        scene_main_prompt=(
            "Amazon MAIN image rules override the requested scene: use a pure white RGB "
            "255,255,255 background, show the complete actual product centered, and add no "
            "lifestyle setting, text, graphics, borders, watermarks or unrelated props."
        ),
        detail_prompt=(
            _COMMON_DETAIL_PROMPT
            + " Amazon additional images may show use, context, different angles and product details."
        ),
        main_audit=(
            "Require a pure white background, the complete actual product centered and occupying "
            "roughly 85% of the frame, with no embedded text, graphics, border, watermark, "
            "unrelated prop or lifestyle scene."
        ),
        detail_audit=(
            "Allow lifestyle context, alternate angles and close-ups, but require an accurate, "
            "clear product with no misleading accessory or copied watermark."
        ),
        require_white_border=True,
    ),
    "taobao": PlatformImageRule(
        main_aspect_ratio="1:1",
        detail_aspect_ratio="3:4",
        main_prompt=(
            "Taobao main-image rules: use a 1:1 composition by default, keep the product clear, "
            "complete and visually prominent, and add no watermark, QR code, third-party platform "
            "logo, dense text overlay or invented price/promotion."
        ),
        scene_main_prompt=(
            "Taobao scene main image: keep the product complete and dominant in a clean commercial "
            "scene; add no watermark, QR code, third-party logo or invented price/promotion."
        ),
        detail_prompt=_COMMON_DETAIL_PROMPT,
        main_audit=(
            "Require a clear, complete and prominent product with no distortion, watermark, QR "
            "code, dense text overlay or invented promotional price. A clean scene is allowed."
        ),
        detail_audit="Require accurate product details, clear hierarchy and no misleading claims.",
    ),
    "tmall": PlatformImageRule(
        main_aspect_ratio="1:1",
        detail_aspect_ratio="3:4",
        main_prompt=(
            "Tmall main-image rules: use 1:1 by default unless the user explicitly requests the "
            "category-dependent 3:4 slot; keep the product clear, complete and prominent; add no "
            "watermark, QR code, dense text overlay or invented price/promotion."
        ),
        scene_main_prompt=(
            "Tmall scene main image: keep the product complete and dominant in a clean commercial "
            "scene; add no watermark, QR code or invented price/promotion."
        ),
        detail_prompt=_COMMON_DETAIL_PROMPT,
        main_audit=(
            "Require a clear, complete and accurate product, correct requested ratio, and no "
            "watermark, QR code, dense text overlay or invented promotional price."
        ),
        detail_audit="Require accurate product details, clear hierarchy and no misleading claims.",
    ),
    "jd": PlatformImageRule(
        main_aspect_ratio="1:1",
        detail_aspect_ratio="3:4",
        main_prompt=(
            "JD main-image safe rules: use a clean 1:1 composition, center the complete product, "
            "keep it prominent and undistorted, and add no watermark, QR code, third-party platform "
            "logo or invented promotion."
        ),
        scene_main_prompt=(
            "JD scene main image: keep the complete product prominent in a clean, uncluttered "
            "commercial scene with no watermark, QR code or invented promotion."
        ),
        detail_prompt=_COMMON_DETAIL_PROMPT,
        main_audit=(
            "Require a complete, centered, prominent and undistorted product with no watermark, "
            "QR code or misleading promotion."
        ),
        detail_audit="Require accurate product details, readable visual hierarchy and no misleading claim.",
    ),
    "pinduoduo": PlatformImageRule(
        main_aspect_ratio="1:1",
        detail_aspect_ratio="3:4",
        main_prompt=(
            "Pinduoduo product-gallery main-image safe rules: use a clear 1:1 composition, make the "
            "complete product visually dominant with strong contrast, and add no watermark, QR "
            "code, fake platform badge or invented price/promotion. Do not use advertising-banner "
            "dimensions for this product-gallery image."
        ),
        scene_main_prompt=(
            "Pinduoduo scene main image: use a clean high-contrast commercial scene while keeping "
            "the complete product dominant; add no fake badge, QR code or invented promotion."
        ),
        detail_prompt=_COMMON_DETAIL_PROMPT,
        main_audit=(
            "Require a clear, complete and dominant product with no watermark, QR code, fake "
            "platform badge or invented promotional price."
        ),
        detail_audit="Require accurate product details, strong clarity and no misleading promotion.",
    ),
    "shopee": PlatformImageRule(
        main_aspect_ratio="1:1",
        detail_aspect_ratio="3:4",
        main_prompt=(
            "Shopee standard-listing main-image rules: use a 1:1 image with a white or clean solid "
            "background, show the complete product from the front, keep it undistorted and filling "
            "about 75% of the frame, and do not let text, logos or watermarks obstruct the product."
        ),
        scene_main_prompt=(
            "Shopee category-friendly scene main image: keep the complete product unobstructed and "
            "dominant in a clean environment, with no distracting objects or obstructive text, "
            "logo or watermark."
        ),
        detail_prompt=(
            _COMMON_DETAIL_PROMPT
            + " Use alternate angles or usage context and keep the product and props visually dominant."
        ),
        main_audit=(
            "Require a clear 1:1 composition, complete front-facing and undistorted product filling "
            "roughly 75% of the frame, with a white or clean background and no obstructive overlay."
        ),
        detail_audit="Allow usage context and close-ups, but require a clear, accurate and unobstructed product.",
    ),
    "lazada": PlatformImageRule(
        main_aspect_ratio="1:1",
        detail_aspect_ratio="3:4",
        main_prompt=(
            "Lazada listing main-image safe rules: use a clean 1:1 square composition, show the "
            "complete product centered and prominent, prefer a white or neutral background, and add "
            "no watermark, QR code, third-party platform logo or invented promotion."
        ),
        scene_main_prompt=(
            "Lazada scene main image: keep the complete product centered, prominent and easy to "
            "identify in a clean scene; add no watermark, QR code or invented promotion."
        ),
        detail_prompt=_COMMON_DETAIL_PROMPT,
        main_audit=(
            "Require a clean square composition with the complete, centered and prominent product, "
            "no distortion, watermark, QR code or misleading promotion."
        ),
        detail_audit="Require accurate product details, clean composition and no misleading claim.",
    ),
    "shein": PlatformImageRule(
        main_aspect_ratio="1:1",
        detail_aspect_ratio="3:4",
        main_prompt=(
            "SHEIN listing main-image rules: use a polished square composition, show the exact "
            "product clearly and completely, keep color, material, pattern and quantity accurate, "
            "and use a clean background with no watermark, QR code or misleading overlay."
        ),
        scene_main_prompt=(
            "SHEIN fashion scene main image: present the exact product on a suitable model or in "
            "a relevant use scene, keep the product unobstructed and visually dominant, and use "
            "consistent editorial lighting with no watermark or misleading accessory."
        ),
        detail_prompt=(
            _COMMON_DETAIL_PROMPT
            + " Use a consistent portrait composition and show accurate alternate angles, fit, "
            "material and construction details; modeled or in-use views are allowed."
        ),
        main_audit=(
            "Require an accurate, clear and complete product with faithful color, material, pattern "
            "and quantity, a clean composition, and no watermark or misleading element."
        ),
        detail_audit=(
            "Require consistent imagery that accurately shows alternate angles, fit, material and "
            "construction details without obscuring or changing the product."
        ),
    ),
    "temu": PlatformImageRule(
        main_aspect_ratio="1:1",
        detail_aspect_ratio="1:1",
        main_prompt=(
            "Temu listing main-image rules: use a clear square composition with a simple clean "
            "background, keep the complete exact product centered and visually dominant, and add "
            "no watermark, QR code, cluttered text, fake badge or invented promotion."
        ),
        scene_main_prompt=(
            "Temu scene main image: show the exact product clearly in a simple relevant use scene, "
            "keep it complete and dominant, and add no watermark, fake badge or invented promotion."
        ),
        detail_prompt=(
            "Create a clear 1:1 Temu product-detail asset. Keep the exact product identity and use "
            "a simple background with no watermark, QR code, cluttered text or invented promotion. "
            "Across the detail set, cover the front, back and important material or construction details."
        ),
        main_audit=(
            "Require a clear square composition, simple background and complete accurate product "
            "with no watermark, cluttered overlay, fake badge or invented promotion."
        ),
        detail_audit=(
            "Require a clear square detail image that accurately contributes a front, back or close-up "
            "view, with a simple background and no watermark or misleading element."
        ),
    ),
}


_DEFAULT_RULE = PlatformImageRule(
    main_aspect_ratio="1:1",
    detail_aspect_ratio="3:4",
    main_prompt=(
        "Use a clean e-commerce composition. Keep the exact product complete, clear, prominent and "
        "undistorted; add no watermark, QR code, third-party logo or invented promotion."
    ),
    scene_main_prompt=(
        "Use a clean commercial scene while keeping the exact product complete, prominent and "
        "unobstructed; add no watermark, QR code or invented promotion."
    ),
    detail_prompt=_COMMON_DETAIL_PROMPT,
    main_audit="Require a complete, clear, accurate and unobstructed product with no misleading overlay.",
    detail_audit="Require accurate product details, clean composition and no misleading claim.",
)


def get_platform_rule(platform: str | None) -> PlatformImageRule:
    return PLATFORM_IMAGE_RULES.get((platform or "").strip().lower(), _DEFAULT_RULE)


def infer_market(platforms: list[str] | tuple[str, ...]) -> str:
    """Infer a practical default market from the first selected platform."""
    platform = next((item.strip().lower() for item in platforms if item.strip()), "amazon")
    return _PLATFORM_MARKETS.get(platform, "US")


def aspect_ratio_for(platform: str, output_type: str = "main_image") -> str:
    if output_type == "pdd_white_background":
        return "1:1"
    rule = get_platform_rule(platform)
    return rule.detail_aspect_ratio if output_type == "detail_page" else rule.main_aspect_ratio


def generation_instruction(
    platform: str | None,
    output_type: str,
    *,
    scene_mode: bool = False,
) -> str:
    if output_type == "pdd_white_background":
        return (
            "Pinduoduo WHITE-BACKGROUND image rules: use a pure white background and exactly one "
            "sellable product as the sole subject. Show the complete product from the front, centered "
            "and filling the frame without a white margin. Use a flat-lay or clean product-only "
            "presentation with no model, person, scene, prop, hanger, product tag, logo, watermark, "
            "text, collage or visible cast shadow."
        )
    rule = get_platform_rule(platform)
    if output_type == "detail_page":
        return rule.detail_prompt
    return rule.scene_main_prompt if scene_mode else rule.main_prompt


def audit_instruction(platform: str | None, output_type: str) -> str:
    if output_type == "pdd_white_background":
        return (
            "Require a pure white background, exactly one complete front-facing sellable product, "
            "centered and filling the frame with no white margin. Reject any model, person, scene, "
            "prop, hanger, product tag, logo, watermark, text, collage or visible cast shadow."
        )
    rule = get_platform_rule(platform)
    return rule.detail_audit if output_type == "detail_page" else rule.main_audit
