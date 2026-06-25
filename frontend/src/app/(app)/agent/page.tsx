import { ChatWindow } from '@/components/ChatWindow'

export default function AgentPage() {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">智能助手</h2>
        <p className="text-muted-foreground">让 MediaForge 智能助手为您的产品生成媒体素材。</p>
      </div>
      <ChatWindow />
    </div>
  )
}
