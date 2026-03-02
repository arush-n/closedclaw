/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow connections to closedclaw API
  async rewrites() {
    return [
      {
        source: '/closedclaw-api/:path*',
        destination: `${process.env.CLOSEDCLAW_API_URL || process.env.MEM0_API_URL || 'http://localhost:8765'}/:path*`,
      },
      {
        source: '/mem0-api/:path*',
        destination: `${process.env.CLOSEDCLAW_API_URL || process.env.MEM0_API_URL || 'http://localhost:8765'}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
