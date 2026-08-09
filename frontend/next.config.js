/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: 'dist',
  outputFileTracingRoot: __dirname,
  turbopack: {
    root: __dirname,
  },
  images: {
    unoptimized: true,
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '/api',
  },
  // Extend socket timeout for long-running SSE streams (image gen can take 60-90s)
  httpAgentOptions: {
    keepAlive: true,
  },
  async rewrites() {
    const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8100'
    return [
      {
        source: '/api/:path*',
        destination: `${backend}/api/:path*`,
      },
    ]
  },
  async headers() {
    const noStore = [
      { key: 'Cache-Control', value: 'no-store, no-cache, must-revalidate' },
    ]
    return [
      '/',
      '/login',
      '/signup',
      '/dashboard',
      '/agent',
      '/batch',
      '/tasks',
      '/products',
      '/settings/:path*',
    ].map((source) => ({ source, headers: noStore }))
  },
}

module.exports = nextConfig
