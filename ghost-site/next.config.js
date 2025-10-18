/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: false,
  experimental: {
    outputStandalone: true
  },
  
  // Serve articles from the articles folder
  async rewrites() {
    return [
      {
        source: '/articles/:path*',
        destination: '/api/articles/:path*',
      },
    ];
  },
}