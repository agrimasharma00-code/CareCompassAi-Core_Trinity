const nextConfig = { distDir: process.env.NEXT_DIST_DIR || ".next-verify", experimental: { cpus: 1, webpackBuildWorker: false } };
export default nextConfig;
