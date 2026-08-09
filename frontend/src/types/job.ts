export type JobStatus = 'pending' | 'running' | 'done' | 'failed' | 'partial_fail'

export type OutputType = 'main_image' | 'detail_page' | 'pdd_white_background'
export type ImageModelAlias = 'pro' | 'fast' | 'base'
export type VideoModelAlias = 'veo' | 'seedance'
export type Priority = 'low' | 'normal' | 'high'
export type AspectRatio = 'auto' | '1:1' | '3:4' | '4:5' | '9:16' | '16:9' | '4:1' | '1:4'
export type ImageSize = '1K' | '2K' | '4K'
export type ReferenceMode = 'auto' | 'specified' | 'none'
export type PresentationMode = 'auto' | 'model_wear' | 'product_only'
export type ModelPreference = 'auto' | 'female' | 'male' | 'no_face'

export type Job = {
  job_id: string
  status: JobStatus
  total_skus: number
  done_skus: number
  created_at: string | null
}

export type SkuInput = {
  sku_id: string
  product_image_url: string
  product_name: string
  category: string
  target_platforms: string[]
  output_types: OutputType[]
  style_hint: string | null
  presentation_mode: PresentationMode
  model_preference: ModelPreference
  market: string
  aspect_ratio: AspectRatio
  image_size: ImageSize
  reference_mode: ReferenceMode
  ref_sku_id: string | null
}

export type AssetStatus = 'pending' | 'success' | 'failed' | 'retrying'

export type Asset = {
  asset_id: string
  job_id: string
  tenant_id: string
  sku_id: string
  output_type: string
  platform: string | null
  model_used: string
  file_path: string | null
  status: AssetStatus
  error_msg: string | null
  created_at: string
}

export type ReferenceProductSummary = {
  sku_code: string
  image_url: string
  description: string
  category: string
}

export type JobDetail = {
  job_id: string
  status: JobStatus
  total_skus: number
  done_skus: number
  input_data: BatchSubmitPayload | null
  reference_products: Record<string, ReferenceProductSummary>
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  assets: Asset[]
  job_items: JobItem[]
}

export type ReferenceCandidate = {
  product_id: string
  image_url: string
  score: number
  metadata: Record<string, unknown>
}

export type GenerationContext = {
  input_matches: boolean
  input_reason: string
  retrieval_mode: 'none' | 'specified' | 'hybrid'
  retrieval_query: string
  retrieval_routes: string[]
  reference_candidates: ReferenceCandidate[]
  selected_reference_id: string | null
  ref_image_path: string | null
  style_prompt: string | null
  presentation_mode: 'model_wear' | 'product_only'
  model_preference: ModelPreference
  product_attributes: Record<string, unknown>
  prompts: Record<string, string>
  quality_results: Array<Record<string, unknown>>
  retry_count: number
  retry_mode: 'none' | 'strict' | 'staged'
}

export type JobItem = {
  job_id: string
  sku_id: string
  status: string
  completed_assets: number
  failed_assets: number
  error_msg: string | null
  generation_context: GenerationContext | null
  updated_at: string
}

export type BatchSubmitPayload = {
  skus: SkuInput[]
  image_model: ImageModelAlias
  video_model: VideoModelAlias
  priority: Priority
}
