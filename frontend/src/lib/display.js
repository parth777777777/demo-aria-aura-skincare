import { Ban, Check, Clock, Minus } from "lucide-react";

export const resolutionPills = {
  resolved: {
    label: "Resolved",
    Icon: Check,
    style: "bg-[var(--success)] text-[var(--success-ink)]",
  },
  not_eligible: {
    label: "Not eligible",
    Icon: Ban,
    style: "bg-[var(--warning)] text-[var(--warning-ink)]",
  },
  unresolved: {
    label: "Unresolved",
    Icon: Clock,
    style: "bg-[var(--warning)] text-[var(--warning-ink)]",
  },
  out_of_scope: {
    label: "Out of scope",
    Icon: Minus,
    style: "bg-[#e3eadf] text-primary",
  },
  no_interaction: {
    label: "No interaction",
    Icon: Minus,
    style: "bg-muted text-foreground",
  },
};

export function getResolutionPill(status) {
  return resolutionPills[status] || resolutionPills.no_interaction;
}

const intentLabels = {
  order_status: "Order status",
  cancellation: "Cancellation",
  return: "Return",
  damaged_product: "Damaged product",
  delivery_info: "Delivery info",
  place_order: "Place order",
  policy_question: "Policy question",
  out_of_scope: "Out of scope",
  unclear: "Unclear",
};

export function getCustomerIntentLabel(intent) {
  return intentLabels[intent] || intent;
}

export function getOrderIdLabel(orderId) {
  return orderId ?? "No order mentioned";
}

export function getVisibleNotice({ error, status, turnCount = 0 }) {
  const sessionLimit =
    status?.reason === "session_limit" && status.state === "ended";
  const endedWithError = status?.state === "ended" && status.reason === "error";
  const errorMessage =
    status?.state === "ended" && !endedWithError
      ? null
      : endedWithError
        ? error?.message || "This call ended unexpectedly."
        : error?.recoverable === true &&
            turnCount > 0 &&
            error.code !== "AUDIO_BLOCKED"
          ? null
          : error?.message ||
            (status?.reason === "error"
              ? "This call ended unexpectedly."
              : null);
  return { errorMessage, sessionLimit };
}

export function getOrderCardData(tool) {
  if (
    tool?.name !== "get_order_details" ||
    !tool.result ||
    tool.result.ok === false
  )
    return null;
  const order = tool.result.order || tool.result;
  return {
    orderId: order.order_id || order.id || tool.args?.order_id,
    status: order.status || "—",
    items: Array.isArray(order.items)
      ? order.items.map((item) => item.name || item).join(", ")
      : order.items || "—",
  };
}
