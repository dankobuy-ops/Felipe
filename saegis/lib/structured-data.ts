import { company } from "@/content/company";

export function insuranceAgencySchema() {
  return {
    "@context": "https://schema.org",
    "@type": "InsuranceAgency",
    name: company.name,
    url: company.url,
    logo: `${company.url}/logo.svg`,
    image: `${company.url}/og/default.png`,
    telephone: company.phone.replace(/\s/g, ""),
    email: company.email,
    description:
      "Corredora chilena de seguros para personas, empresas y comunidades. Más de 40 años de experiencia.",
    areaServed: { "@type": "Country", name: "Chile" },
    address: {
      "@type": "PostalAddress",
      streetAddress: company.address.street,
      addressLocality: company.address.city,
      addressRegion: company.address.region,
      addressCountry: company.address.countryCode,
    },
    openingHoursSpecification: [
      {
        "@type": "OpeningHoursSpecification",
        dayOfWeek: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        opens: "09:00",
        closes: "18:00",
      },
    ],
    sameAs: [],
  };
}

export function breadcrumbSchema(items: { name: string; url: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      item: `${company.url}${item.url}`,
    })),
  };
}
