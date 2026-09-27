import { useEffect, useState } from "react";
export function go(path: string) {
  window.location.hash = "/" + path;
}
export function useRoute() {
  const read = () => window.location.hash.replace(/^#\/?/, "") || "login";
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const change = () => {
      setRoute(read());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  return route;
}
