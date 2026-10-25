import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { getOrderCardData } from "../lib/display.js";

export function OrderCard({ order }) {
  const { Icon, tone } = order;
  return (
    <li className="pointer-events-none rounded-[20px] border border-border bg-card p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="rounded-full bg-muted px-2.5 py-1 font-mono text-sm">
          {order.id}
        </span>
        <Badge
          className={`h-auto gap-1.5 px-2.5 py-1.5 text-sm ${tone === "sage" ? "bg-[#e3eadf] text-primary" : tone === "success" ? "bg-[var(--success)] text-[var(--success-ink)]" : "bg-[var(--warning)] text-[var(--warning-ink)]"}`}
        >
          <Icon size={15} />
          {order.status}
        </Badge>
      </div>
      <p className="mt-2 text-base">{order.product}</p>
      <p className="mt-1 text-sm text-muted-foreground">{order.detail}</p>
      <p className="mt-1 text-sm text-muted-foreground">
        Try saying: &quot;{order.hint}&quot;
      </p>
    </li>
  );
}

export function OrderResult({ tool }) {
  const order = getOrderCardData(tool);
  if (!order) return null;
  return (
    <Card className="mt-3 w-full max-w-[340px] bg-card animate-in fade-in slide-in-from-bottom-2 duration-200 delay-150 motion-reduce:animate-none">
      <CardContent className="p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-bold uppercase tracking-widest text-muted-foreground">
            Order details
          </span>
          <span className="font-mono text-sm">{order.orderId}</span>
        </div>
        <div className="mt-2 grid grid-cols-[65px_1fr] gap-x-2.5 gap-y-2 border-t border-border pt-2.5 text-sm">
          <span className="text-muted-foreground">Status</span>
          <strong className="font-medium">{order.status}</strong>
          <span className="text-muted-foreground">Items</span>
          <strong className="font-medium">{order.items}</strong>
        </div>
      </CardContent>
    </Card>
  );
}
