import { Clock, PackageCheck, Truck } from "lucide-react";
import { OrderCard } from "./OrderCard.jsx";

const orders = [
  {
    id: "ORD-101",
    product: "Vitamin C Serum 30ml",
    status: "Out for Delivery",
    detail: "Today by 6 PM",
    hint: "Where is my order?",
    Icon: Truck,
    tone: "sage",
  },
  {
    id: "ORD-102",
    product: "Hydrating Sunscreen SPF 50",
    status: "Delivered",
    detail: "14 days ago",
    hint: "Can I return this?",
    Icon: PackageCheck,
    tone: "success",
  },
  {
    id: "ORD-103",
    product: "Green Tea Face Wash + Toner",
    status: "Processing",
    detail: "Ordered 3 hours ago",
    hint: "Cancel this order.",
    Icon: Clock,
    tone: "warning",
  },
];

export function SampleOrders() {
  return (
    <div className="mt-6 w-full text-left">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="font-heading text-lg">Try one of these orders</h3>
        <span className="text-sm text-muted-foreground">Sample data</span>
      </div>
      <ul className="grid gap-3">
        {orders.map((order) => (
          <OrderCard key={order.id} order={order} />
        ))}
      </ul>
    </div>
  );
}
