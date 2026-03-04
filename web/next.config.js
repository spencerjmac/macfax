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
  // Proxy backend paths to Django.
  // /api/*    — REST API + admin
  // /static/* — WhiteNoise static files (logos, admin CSS/JS)
  // /logos/*  — legacy logo URLs still in DB before import_logos migration;
  //             rewrite to /static/logos/* on the backend
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendOrigin()}/api/:path*`,
      },
      {
        source: '/static/:path*',
        destination: `${backendOrigin()}/static/:path*`,
      },
      {
        source: '/logos/:path*',
        destination: `${backendOrigin()}/static/logos/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
