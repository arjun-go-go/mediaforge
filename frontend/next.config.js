/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: 'dist',
  images: {
    unoptimized: true,
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '/api',
  },
  // Extend socket timeout for long-running SSE streams (image gen can take 60-90s)
  httpAgentOptions: {
    timeout: 300000, // 5 minutes
  },
  async rewrites() {
    const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000'
    return [
      {
        source: '/api/:path*',
        destination: `${backend}/api/:path*`,
      },
      {
        source: '/outputs/:path*',
        destination: `${backend}/outputs/:path*`,
      },
      {
        source: '/uploads/:path*',
        destination: `${backend}/uploads/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
