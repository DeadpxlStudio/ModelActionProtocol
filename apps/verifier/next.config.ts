import type { NextConfig } from "next";

const config: NextConfig = {
  transpilePackages: ["@model-action-protocol/core"],
  typedRoutes: true,
};

export default config;
