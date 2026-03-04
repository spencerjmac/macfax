/** @type {import('next').NextConfig} */
const path = require('path')

const srcDir = path.resolve(__dirname, 'src')

// Backend origin for server-side proxying (evaluated at runtime, not build time)
const backendOrigin = () =>
  (process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

const nextConfig = {
  images: {
    unoptimized: true,
  },
  basePath: process.env.NODE_ENV === 'production' ? '' : '',
  webpack: (config) => {
    config.resolve.alias = config.resolve.alias || {}
    config.resolve.alias['@'] = srcDir
    config.resolve.alias['@/'] = srcDir + path.sep
    return config
  },
  // Proxy /static/* to the Django backend so logo URLs (/static/logos/foo.png)
  // resolve correctly whether the request comes from browser or SSR.
  async rewrites() {
    return [
      {
        source: '/static/:path*',
        destination: `${backendOrigin()}/static/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
