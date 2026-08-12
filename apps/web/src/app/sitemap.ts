import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: "https://gaffertalk.com",
      lastModified: new Date("2026-08-12"),
      changeFrequency: "weekly",
      priority: 1,
    },
  ];
}
