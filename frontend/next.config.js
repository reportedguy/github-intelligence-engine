/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    serverComponentsExternalPackages: ['@xenova/transformers', '@libsql/client'],
  },
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [...(config.externals || []), '@xenova/transformers', '@libsql/client'];
    }
    return config;
  },
};

module.exports = nextConfig;
