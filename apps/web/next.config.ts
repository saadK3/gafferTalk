import type { NextConfig } from "next";
import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";

initOpenNextCloudflareForDev();

const nextConfig: NextConfig = {
  async redirects() {
    const appHostname = process.env.NEXT_PUBLIC_APP_HOST;

    if (!appHostname) {
      return [];
    }

    return [
      {
        source: "/",
        has: [
          {
            type: "host",
            value: appHostname,
          },
        ],
        destination: "/team",
        permanent: false,
      },
    ];
  },
};

export default nextConfig;
