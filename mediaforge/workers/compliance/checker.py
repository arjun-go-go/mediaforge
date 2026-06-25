from dataclasses import dataclass, field
from typing import Any


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

    PLATFORM_PROMPT_ADDENDUM = {
        "amazon": (
            " Amazon 主图规范:纯白背景(RGB 255,255,255),商品占画面 85%。"
        ),
        "shopee": (
            " Shopee 主图规范:明亮干净背景,无边框,商品居中,生活化风格。"
        ),
        "tiktok": " TikTok 竖版 9:16,动感活力,强视觉冲击,适合快速滑动吸引注意力。",
    }

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

        for platform in sku.get("target_platforms", []):
            addendum = self.PLATFORM_PROMPT_ADDENDUM.get(platform, "")
            if addendum:
                result.modified_prompt += addendum

        result.passed = True
        return result
