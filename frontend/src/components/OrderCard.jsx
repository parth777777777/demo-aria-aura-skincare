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
      <div className="mt-3 border-t border-border pt-3">
        <h3 className="font-heading text-xl leading-snug">{order.product}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{order.detail}</p>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-sm">
          {order.itemCount != null && (
            <span className="text-muted-foreground">
              {order.itemCount} {order.itemCount === 1 ? "item" : "items"}
              {order.totalInr != null && " · "}
              {order.totalInr != null &&
                new Intl.NumberFormat("en-IN", {
                  style: "currency",
                  currency: "INR",
                  maximumFractionDigits: 0,
                }).format(order.totalInr)}
            </span>
          )}
          {order.arrival && (
            <span className="font-medium text-foreground">
              Arrives {order.arrival}
            </span>
          )}
        </div>
      </div>
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
