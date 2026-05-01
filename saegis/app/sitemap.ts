import type { MetadataRoute } from "next";
import { products } from "@/content/products";
import { company } from "@/content/company";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = company.url;
  const staticPaths = [
    "",
    "/nosotros",
    "/personas",
    "/empresas",
    "/comunidades",
    "/seguros/vehicular",
    "/seguros/hogar",
    "/contacto",
  ];
  const now = new Date();
  return [
    ...staticPaths.map((path) => ({
      url: `${base}${path}`,
      lastModified: now,
      changeFrequency: "monthly" as const,
      priority: path === "" ? 1 : 0.8,
    })),
    ...products.map((p) => ({
      url: `${base}/personas/${p.slug}`,
      lastModified: now,
      changeFrequency: "monthly" as const,
      priority: 0.6,
    })),
  ];
}
