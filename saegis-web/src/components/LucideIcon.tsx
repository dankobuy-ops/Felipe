import * as Icons from "lucide-react";

interface Props {
  name: string;
  className?: string;
  size?: number;
}

export function LucideIcon({ name, className = "size-5", size }: Props) {
  const Icon = (Icons as Record<string, Icons.LucideIcon>)[name];
  if (!Icon) return null;
  return <Icon className={className} size={size} strokeWidth={2} />;
}
