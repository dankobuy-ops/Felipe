export interface NavItem {
  label: string;
  href: string;
  description?: string;
}

export const mainNav: NavItem[] = [
  { label: "Inicio", href: "/" },
  { label: "Nosotros", href: "/nosotros" },
  {
    label: "Personas",
    href: "/personas",
    description: "Soluciones para ti y tu familia",
  },
  {
    label: "Empresas",
    href: "/empresas",
    description: "Protección integral para tu negocio",
  },
  {
    label: "Comunidades",
    href: "/comunidades",
    description: "Seguros para edificios y condominios",
  },
  { label: "Contacto", href: "/contacto" },
];

export const footerNav: NavItem[] = [
  { label: "Inicio", href: "/" },
  { label: "Nosotros", href: "/nosotros" },
  { label: "Personas", href: "/personas" },
  { label: "Empresas", href: "/empresas" },
  { label: "Comunidades", href: "/comunidades" },
  { label: "Seguro Vehicular", href: "/seguros/vehicular" },
  { label: "Seguro Hogar", href: "/seguros/hogar" },
  { label: "Contacto", href: "/contacto" },
];
