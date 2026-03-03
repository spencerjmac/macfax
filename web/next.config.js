/** @type {import('next').NextConfig} */
const path = require('path')

const nextConfig = {
  images: {
    unoptimized: true,
  },
  basePath: process.env.NODE_ENV === 'production' ? '' : '',
  webpack: (config) => {
    config.resolve.alias['@'] = path.join(__dirname, 'src')
    return config
  },
}

module.exports = nextConfig
