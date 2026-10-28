/** @type {import('next').NextConfig} */
const path = require('path')

const srcDir = path.resolve(__dirname, 'src')
const { routes: hiddenRoutes } = require('../packages/core/src/config/hidden-routes.json')

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
  turbopack: {
    root: path.resolve(__dirname, '..'),
  },
  // Redirects:
  //  - World Cup 2026 pages were removed (the backend app is kept); old links land on the homepage.
  //  - Hidden pages: single list in packages/core/src/config/hidden-routes.json (also drives
  //    nav, hub tiles, footer and Expo). Delete an entry there to bring a page back.
  async redirects() {
    return [
      { source: '/world-cup/:path*', destination: '/', permanent: false },
      ...hiddenRoutes.map((r) => ({
        source: `${r.path}/:path*`,
        destination: r.redirectTo,
        permanent: false,
      })),
    ]
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
