export type Option = { value: string; label: string; hint?: string }

export const CATEGORY_OPTIONS: Option[] = [
  { value: '服饰', label: '服饰' },
  { value: '鞋靴', label: '鞋靴' },
  { value: '箱包', label: '箱包' },
  { value: '配饰', label: '配饰（首饰/手表/眼镜）' },
  { value: '美妆', label: '美妆个护' },
  { value: '母婴', label: '母婴用品' },
  { value: '家居', label: '家居家纺' },
  { value: '家电', label: '家用电器' },
  { value: '数码', label: '数码 3C' },
  { value: '食品', label: '食品饮料' },
  { value: '运动', label: '运动户外' },
  { value: '玩具', label: '玩具乐器' },
  { value: '宠物', label: '宠物用品' },
  { value: '汽车', label: '汽车用品' },
  { value: '办公', label: '办公文教' },
  { value: '其他', label: '其他' },
]

export const MARKET_OPTIONS: Option[] = [
  { value: 'CN', label: '中国大陆 CN' },
  { value: 'US', label: '美国 US' },
  { value: 'GB', label: '英国 GB' },
  { value: 'DE', label: '德国 DE' },
  { value: 'FR', label: '法国 FR' },
  { value: 'JP', label: '日本 JP' },
  { value: 'KR', label: '韩国 KR' },
  { value: 'SG', label: '新加坡 SG' },
  { value: 'MY', label: '马来西亚 MY' },
  { value: 'TH', label: '泰国 TH' },
  { value: 'VN', label: '越南 VN' },
  { value: 'ID', label: '印尼 ID' },
  { value: 'PH', label: '菲律宾 PH' },
  { value: 'AU', label: '澳大利亚 AU' },
  { value: 'CA', label: '加拿大 CA' },
  { value: 'BR', label: '巴西 BR' },
  { value: 'AE', label: '阿联酋 AE' },
  { value: 'SA', label: '沙特 SA' },
]

export type PlatformGroup = '电商'

export const PLATFORM_OPTIONS: { value: string; label: string; group: PlatformGroup; hint: string }[] = [
  { value: 'taobao', label: '淘宝', group: '电商', hint: '默认1:1，商品清晰完整，禁止水印、二维码和虚假促销' },
  { value: 'tmall', label: '天猫', group: '电商', hint: '默认1:1；3:4需手动选择并确认类目已开放' },
  { value: 'jd', label: '京东', group: '电商', hint: '默认1:1，商品居中完整，背景简洁' },
  { value: 'pinduoduo', label: '拼多多', group: '电商', hint: '商品轮播图默认1:1，主体突出，禁止虚假活动角标' },
  { value: 'amazon', label: 'Amazon', group: '电商', hint: '主图1:1纯白底，商品约占85%，禁止文字和无关道具' },
  { value: 'shopee', label: 'Shopee', group: '电商', hint: '主图1:1，白色或干净背景，商品完整且约占75%' },
  { value: 'lazada', label: 'Lazada', group: '电商', hint: '主图1:1，商品居中完整，白色或中性背景优先' },
  { value: 'shein', label: 'SHEIN', group: '电商', hint: '主图默认1:1，详情图3:4，商品颜色、材质、图案与数量必须真实一致' },
  { value: 'temu', label: 'Temu', group: '电商', hint: '主图和详情图默认1:1，背景简洁，完整展示正面、背面与细节' },
]

export function platformRuleSummary(platforms: string[]): string {
  if (platforms.length === 0) return '请选择目标平台'
  if (platforms.length > 1) return `将为 ${platforms.length} 个平台分别应用主图与质检规则`
  return PLATFORM_OPTIONS.find((option) => option.value === platforms[0])?.hint ?? '按平台应用图片规则'
}

const PLATFORM_MARKETS: Record<string, string> = {
  taobao: 'CN',
  tmall: 'CN',
  jd: 'CN',
  pinduoduo: 'CN',
  amazon: 'US',
  shopee: 'SG',
  lazada: 'SG',
  shein: 'US',
  temu: 'US',
}

export function inferMarketFromPlatforms(platforms: string[]): string {
  const normalized = platforms.map((platform) => platform.trim().toLowerCase()).filter(Boolean)
  const mainlandPlatforms = new Set(['taobao', 'tmall', 'jd', 'pinduoduo'])

  if (normalized.some((platform) => mainlandPlatforms.has(platform))) return 'CN'
  return PLATFORM_MARKETS[normalized[0]] ?? 'US'
}

export const STYLE_PRESETS: Option[] = [
  { value: '专业摄影棚、柔和棚拍光、干净背景', label: '摄影棚' },
  { value: '居家生活场景、自然光、温暖舒适', label: '居家生活' },
  { value: '城市街拍、自然步态、现代建筑背景', label: '城市街拍' },
  { value: '户外自然场景、柔和日光、轻松氛围', label: '户外自然' },
  { value: '度假海边、明亮阳光、清爽松弛感', label: '度假海边' },
  { value: '高级商场、精致灯光、轻奢氛围', label: '高级商场' },
  { value: '简约高级、低饱和配色、克制构图', label: '简约高级' },
  { value: '活力年轻、明快色彩、自然动态姿势', label: '活力年轻' },
]
