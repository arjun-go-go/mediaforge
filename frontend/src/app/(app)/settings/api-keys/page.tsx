'use client'

import { useCallback, useEffect, useState } from 'react'
import { Copy, Key, Loader2, Plus, Trash2 } from 'lucide-react'

import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

type ApiKeyInfo = {
  key_id: string
  name: string
  key_prefix: string
  last_used_at: string | null
  expires_at: string | null
  revoked_at: string | null
  created_at: string
}

type ApiKeyCreated = ApiKeyInfo & { plaintext_key: string }

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const fetchKeys = useCallback(async () => {
    try {
      const res = await api.get<{ keys: ApiKeyInfo[] }>('/v1/api-keys')
      setKeys(res.keys)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchKeys() }, [fetchKeys])

  const handleCreate = async () => {
    if (!newKeyName.trim()) return
    setCreating(true)
    try {
      const res = await api.post<ApiKeyCreated>('/v1/api-keys', { name: newKeyName.trim() })
      setCreatedKey(res.plaintext_key)
      setNewKeyName('')
      fetchKeys()
    } catch {
      // error handling
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (keyId: string) => {
    try {
      await fetch(`/api/v1/api-keys/${keyId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      })
      fetchKeys()
    } catch {
      // ignore
    }
  }

  const handleCopy = () => {
    if (createdKey) {
      navigator.clipboard.writeText(createdKey)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">API Keys</h2>
          <p className="text-muted-foreground">管理您的 API 密钥，用于程序化访问 MediaForge 服务</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) { setCreatedKey(null); setCopied(false) } }}>
          <DialogTrigger asChild>
            <Button><Plus className="mr-2 h-4 w-4" />创建密钥</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{createdKey ? '密钥已创建' : '创建 API 密钥'}</DialogTitle>
              <DialogDescription>
                {createdKey
                  ? '请立即复制密钥，关闭此对话框后将无法再次查看完整密钥。'
                  : '为密钥取一个便于辨认的名称。'}
              </DialogDescription>
            </DialogHeader>
            {createdKey ? (
              <div className="space-y-4">
                <div className="flex items-center gap-2 rounded-md border bg-muted p-3 font-mono text-sm break-all">
                  {createdKey}
                </div>
                <Button variant="outline" className="w-full" onClick={handleCopy}>
                  <Copy className="mr-2 h-4 w-4" />
                  {copied ? '已复制' : '复制密钥'}
                </Button>
              </div>
            ) : (
              <>
                <Input
                  placeholder="例如: Production Backend"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                />
                <DialogFooter>
                  <Button onClick={handleCreate} disabled={creating || !newKeyName.trim()}>
                    {creating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    创建
                  </Button>
                </DialogFooter>
              </>
            )}
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">活跃密钥</CardTitle>
          <CardDescription>所有密钥拥有与您的账户相同的权限</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : keys.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center text-muted-foreground">
              <Key className="h-10 w-10" />
              <p>暂无 API 密钥</p>
              <p className="text-sm">创建一个密钥以开始使用 API</p>
            </div>
          ) : (
            <div className="divide-y divide-border rounded-md border">
              {keys.map((k) => (
                <div key={k.key_id} className="flex items-center justify-between px-4 py-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{k.name}</span>
                      {k.revoked_at && (
                        <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-xs text-destructive">
                          已吊销
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-sm text-muted-foreground">
                      <code>{k.key_prefix}...</code>
                      <span>创建于 {new Date(k.created_at).toLocaleDateString()}</span>
                      {k.last_used_at && (
                        <span>最后使用 {new Date(k.last_used_at).toLocaleDateString()}</span>
                      )}
                    </div>
                  </div>
                  {!k.revoked_at && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleRevoke(k.key_id)}
                      title="吊销密钥"
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
