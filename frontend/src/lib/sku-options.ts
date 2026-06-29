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

export type PlatformGroup = '电商' | '短视频' | '社交'

export const PLATFORM_OPTIONS: { value: string; label: string; group: PlatformGroup }[] = [
  { value: 'taobao', label: '淘宝', group: '电商' },
  { value: 'tmall', label: '天猫', group: '电商' },
  { value: 'jd', label: '京东', group: '电商' },
  { value: 'pinduoduo', label: '拼多多', group: '电商' },
  { value: 'amazon', label: 'Amazon', group: '电商' },
  { value: 'shopee', label: 'Shopee', group: '电商' },
  { value: 'lazada', label: 'Lazada', group: '电商' },
  { value: 'tiktok', label: 'TikTok', group: '短视频' },
  { value: 'douyin', label: '抖音', group: '短视频' },
  { value: 'kuaishou', label: '快手', group: '短视频' },
  { value: 'reels', label: 'Instagram Reels', group: '短视频' },
  { value: 'shorts', label: 'YouTube Shorts', group: '短视频' },
  { value: 'xiaohongshu', label: '小红书', group: '社交' },
  { value: 'instagram', label: 'Instagram', group: '社交' },
  { value: 'facebook', label: 'Facebook', group: '社交' },
]

export const STYLE_PRESETS: Option[] = [
  { value: '极简白底', label: '极简白底', hint: '纯白背景、产品居中、棚拍灯光' },
  { value: '生活场景', label: '生活场景', hint: '真实使用场景、自然光、生活感' },
  { value: '轻奢简约', label: '轻奢简约', hint: '高级灰背景、莫兰迪色、质感构图' },
  { value: '活力色彩', label: '活力色彩', hint: '高饱和撞色、年轻化、强视觉冲击' },
  { value: '手绘插画', label: '手绘插画', hint: '插画风背景、手绘元素装饰' },
  { value: 'UGC快节奏', label: 'UGC 风格', hint: '手机拍摄感、自然光、生活博主感' },
  { value: '日系清新', label: '日系清新', hint: '柔和光线、低饱和、文艺质感' },
  { value: '工业冷感', label: '工业冷感', hint: '深色金属背景、冷色调、科技感' },
]
