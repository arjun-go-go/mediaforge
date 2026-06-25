export type JobStatus = 'pending' | 'running' | 'done' | 'failed' | 'partial_fail'

export type OutputType = 'main_image' | 'detail_page' | 'video' | 'social'
export type ImageModelAlias = 'pro' | 'fast'
export type VideoModelAlias = 'veo' | 'seedance'
export type Priority = 'low' | 'normal' | 'high'

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
  market: string
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

export type JobDetail = {
  job_id: string
  status: JobStatus
  total_skus: number
  done_skus: number
  input_data: BatchSubmitPayload | null
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  assets: Asset[]
}

export type BatchSubmitPayload = {
  skus: SkuInput[]
  image_model: ImageModelAlias
  video_model: VideoModelAlias
  priority: Priority
}
