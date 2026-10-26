import { useEffect, useState } from "react";

export function useHashRoute() {
  const [route, setRoute] = useState(
    window.location.hash === "#/summary"
      ? "summary"
      : window.location.hash === "#/demo-account"
        ? "demo-account"
        : "call",
  );
  useEffect(() => {
    const onHash = () => {
      const hash = window.location.hash;
      setRoute(
        hash === "#/summary"
          ? "summary"
          : hash === "#/demo-account"
            ? "demo-account"
            : "call",
      );
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return [route, setRoute];
}
