import { Clock, PackageCheck, Truck } from "lucide-react";

export function getOrderDisplays(tools) {
  const seen = new Set();
  const displays = [];
  for (const tool of tools) {
    const result = tool.result;
    if (result?.ok !== true) continue;
    let orders = [];
    if (tool.name === "list_orders" && Array.isArray(result.orders)) {
      orders = result.orders;
    } else if (tool.name === "get_order_details" && result.order) {
      orders = [result.order];
    } else if (
      tool.name === "resolve_order_reference" &&
      result.match_status === "matched" &&
      result.order
    ) {
      orders = [result.order];
    }
    for (const order of orders) {
      const id = order.order_id || order.id;
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const status = order.status || "Status unavailable";
      const lowerStatus = status.toLowerCase();
      displays.push({
        id,
        product: Array.isArray(order.items)
          ? order.items
              .map((item) => (typeof item === "string" ? item : item.name))
              .filter(Boolean)
              .join(", ") || "Order details"
          : order.product_name ||
            order.product ||
            order.items ||
            "Order details",
        status,
        detail:
          order.estimated_delivery ||
          order.delivery_date ||
          order.created_at ||
          "Order details from Aura",
        hint: "Ask Aria about this order",
        Icon: lowerStatus.includes("deliver")
          ? PackageCheck
          : lowerStatus.includes("processing")
            ? Clock
            : Truck,
        tone: lowerStatus.includes("deliver")
          ? "success"
          : lowerStatus.includes("processing")
            ? "warning"
            : "sage",
        source: result.source,
      });
    }
  }
  return displays;
}
