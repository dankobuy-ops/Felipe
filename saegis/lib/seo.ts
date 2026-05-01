import type { Metadata } from "next";
import { company } from "@/content/company";

const defaultDescription =
  "Corredora de seguros en Chile con más de 40 años de experiencia. Asesoría independiente en seguros vehiculares, hogar, salud, empresa y comunidades.";

export function buildMetadata({
  title,
  description = defaultDescription,
  path = "/",
  image = "/og/default.png",
  noindex = false,
}: {
  title: string;
  description?: string;
  path?: string;
  image?: string;
  noindex?: boolean;
} = { title: company.name }): Metadata {
  const absoluteUrl = `${company.url}${path}`;
  const fullTitle =
    title === company.name ? `${company.name} — ${company.tagline}` : `${title} · ${company.name}`;

  return {
    title: fullTitle,
    description,
    metadataBase: new URL(company.url),
    alternates: { canonical: path },
    openGraph: {
      title: fullTitle,
      description,
      url: absoluteUrl,
      siteName: company.name,
      locale: "es_CL",
      type: "website",
      images: [{ url: image, width: 1200, height: 630, alt: company.name }],
    },
    twitter: {
      card: "summary_large_image",
      title: fullTitle,
      description,
      images: [image],
    },
    robots: noindex ? { index: false, follow: false } : undefined,
  };
}
