/** @type {import('next').NextConfig} */
const path = require('path')

const srcDir = path.resolve(__dirname, 'src')

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
}

module.exports = nextConfig
