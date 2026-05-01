import { Phone, Mail, MapPin, Clock, MessageCircle } from "lucide-react";
import { company } from "@/content/company";

export function ContactInfo() {
  const items = [
    {
      icon: Phone,
      label: "Teléfono",
      value: company.phone,
      href: company.phoneHref,
    },
    {
      icon: MessageCircle,
      label: "WhatsApp",
      value: "Escríbenos",
      href: company.whatsappHref,
    },
    {
      icon: Mail,
      label: "Email",
      value: company.email,
      href: company.emailHref,
    },
    {
      icon: MapPin,
      label: "Oficina",
      value: `${company.address.street}, ${company.address.city}`,
    },
    {
      icon: Clock,
      label: "Horario",
      value: company.schedule,
    },
  ];

  return (
    <ul className="space-y-4">
      {items.map(({ icon: Icon, label, value, href }) => {
        const content = (
          <>
            <span className="inline-flex size-10 items-center justify-center rounded-xl bg-primary/5 text-primary">
              <Icon className="size-4" />
            </span>
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground">
                {label}
              </p>
              <p className="mt-0.5 font-medium text-foreground">{value}</p>
            </div>
          </>
        );
        return (
          <li key={label}>
            {href ? (
              <a
                href={href}
                target={href.startsWith("http") ? "_blank" : undefined}
                rel={href.startsWith("http") ? "noopener noreferrer" : undefined}
                className="flex items-start gap-4 rounded-xl border border-border bg-background p-4 transition-colors hover:border-primary/30"
              >
                {content}
              </a>
            ) : (
              <div className="flex items-start gap-4 rounded-xl border border-border bg-background p-4">
                {content}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
