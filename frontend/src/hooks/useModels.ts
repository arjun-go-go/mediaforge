import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

export type ModelOption = {
  alias: string
  model_id: string
  label: string
}

type ModelsResponse = {
  image_models: ModelOption[]
  video_models: ModelOption[]
}

type UseModelsResult = {
  imageModels: ModelOption[]
  videoModels: ModelOption[]
  loading: boolean
}

const FALLBACK_IMAGE: ModelOption[] = [
  { alias: 'pro', model_id: 'google/gemini-3-pro-image', label: 'google/gemini-3-pro-image' },
  { alias: 'fast', model_id: 'openai/gpt-5.4-image-2', label: 'openai/gpt-5.4-image-2' },
]

const FALLBACK_VIDEO: ModelOption[] = [
  { alias: 'veo', model_id: 'google/veo-3.1', label: 'google/veo-3.1' },
  { alias: 'seedance', model_id: 'bytedance/seedance-2.0', label: 'bytedance/seedance-2.0' },
]

export function useModels(): UseModelsResult {
  const [imageModels, setImageModels] = useState<ModelOption[]>(FALLBACK_IMAGE)
  const [videoModels, setVideoModels] = useState<ModelOption[]>(FALLBACK_VIDEO)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<ModelsResponse>('/v1/models')
      .then((data) => {
        if (data.image_models?.length) setImageModels(data.image_models)
        if (data.video_models?.length) setVideoModels(data.video_models)
      })
      .catch(() => {
        // keep fallback values on error
      })
      .finally(() => setLoading(false))
  }, [])

  return { imageModels, videoModels, loading }
}
