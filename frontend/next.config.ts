import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets a second dev server (for example one pointed at a test backend) build into its own folder.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
