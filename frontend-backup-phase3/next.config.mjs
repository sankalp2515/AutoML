/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow images from the backend
  images: {
    remotePatterns: [
      { protocol: 'http', hostname: 'localhost', port: '8000' },
      { protocol: 'http', hostname: 'backend', port: '8000' },
    ],
    unoptimized: true,
  },
  // Expose backend URL to server components
  experimental: {},
};

export default nextConfig;
