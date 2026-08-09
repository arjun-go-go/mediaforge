from dataclasses import dataclass, field
from typing import Any

from mediaforge.workers.platform_rules import generation_instruction


@dataclass
class ComplianceResult:
    passed: bool = True
    blocked: bool = False
    auto_fixed: bool = False
    warnings: list[str] = field(default_factory=list)
    modified_prompt: str = ""


class ComplianceChecker:
    DANGEROUS_KEYWORDS = {"bomb", "weapon", "drug", "counterfeit", "fake", "replica"}
    BRAND_BLACKLIST = {"nike", "adidas", "gucci", "chanel"}
    IP_BLACKLIST = {"disney", "marvel", "pokemon"}

    CULTURAL_FIXES = {
        "CN": {"4": "6"},
        "VN": {"4": "6"},
        "PH": {"13": "12"},
    }

    # Keywords that signal the user wants a lifestyle / outdoor / scene shoot.
    # When any of these appears in style_hint, strict layout rules are relaxed
    # in favor of the user's creative direction.
    SCENE_KEYWORDS = (
        "场景", "外景", "户外", "街头", "街景", "街道", "巷子", "巷弄",
        "水乡", "江南", "古镇", "海边", "沙滩", "海滩", "山", "森林", "树林",
        "草原", "田野", "花园", "庭院", "公园", "湖", "河", "桥", "落叶",
        "咖啡馆", "咖啡店", "餐厅", "民宿", "客厅", "卧室", "书房",
        "雪景", "雪地", "樱花", "竹林", "落日", "黄昏", "清晨", "夜景", "霓虹",
        "lifestyle", "outdoor", "scene", "street", "garden", "beach",
        "forest", "cafe", "park",
    )

    REF_WATERMARK_SUFFIX = (
        " Do not copy, reproduce, or recreate any text, watermark, logo, "
        "icon, badge, price tag, or graphic overlay visible in the reference "
        "image. Generate clean original imagery with no embedded text."
    )

    def _has_scene_hint(self, sku: dict[str, Any]) -> bool:
        style_hint = (sku.get("style_hint") or "").lower()
        if not style_hint:
            return False
        return any(kw.lower() in style_hint for kw in self.SCENE_KEYWORDS)

    def check(self, sku: dict[str, Any], prompt: str) -> ComplianceResult:
        result = ComplianceResult(modified_prompt=prompt)

        lowered = prompt.lower()
        if any(k in lowered for k in self.DANGEROUS_KEYWORDS):
            result.blocked = True
            result.passed = False
            return result

        market = sku.get("market", "US")
        fixes = self.CULTURAL_FIXES.get(market, {})
        for bad, good in fixes.items():
            if bad in result.modified_prompt:
                result.modified_prompt = result.modified_prompt.replace(bad, good)
                result.auto_fixed = True

        for brand in self.BRAND_BLACKLIST:
            if brand in lowered:
                result.warnings.append(f"L2 品牌关键词命中: {brand}(需人工确认授权)")
        for ip in self.IP_BLACKLIST:
            if ip in lowered:
                result.warnings.append(f"L3 IP 关键词命中: {ip}(需人工确认版权)")

        output_type = str(sku.get("_output_type") or "main_image")
        platform = str(
            sku.get("_current_platform")
            or next(iter(sku.get("target_platforms", [])), "")
        ).lower()
        strict_catalog_image = (
            (output_type == "main_image" and platform == "amazon")
            or output_type == "pdd_white_background"
        )
        scene_mode = self._has_scene_hint(sku) and not strict_catalog_image
        if scene_mode:
            result.warnings.append(
                "用户提供场景化 style_hint,平台严格版式规则已放宽"
            )
        result.modified_prompt += " " + generation_instruction(
            platform,
            output_type,
            scene_mode=scene_mode,
        )

        # D: instruct the model not to copy any text/watermark from the
        # reference product image, which Gemini multimodal tends to do.
        result.modified_prompt += self.REF_WATERMARK_SUFFIX

        result.passed = True
        return result
