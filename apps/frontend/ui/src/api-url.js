const hasProtocol = (value) => /^[a-zA-Z][a-zA-Z\d+.-]*:/.test(value);

const resolveOrigin = (windowRef, baseUrl) => {
  const location = windowRef.location ?? {};
  if (location.origin && hasProtocol(location.origin)) {
    return location.origin;
  }
  if (location.protocol && location.host) {
    return `${location.protocol}//${location.host}`;
  }
  if (location.href) {
    try {
      return new (windowRef.URL ?? URL)(location.href).origin;
    } catch (error) {
      // ignore and fallback below
    }
  }
  if (baseUrl) {
    return `${baseUrl.protocol}//${baseUrl.host}`;
  }
  return "";
};

export const createApiUrlBuilder = (windowLike) => {
  const windowRef =
    windowLike || (typeof window !== "undefined" ? window : undefined);
  if (!windowRef) {
    throw new Error("createApiUrlBuilder requires a window-like object");
  }

  const documentRef =
    windowRef.document || (typeof document !== "undefined" ? document : undefined);
  const URLCtor = windowRef.URL || URL;

  let cachedBase = null;

  const resolveBase = () => {
    if (cachedBase) {
      return cachedBase;
    }

    const baseElement = documentRef?.querySelector?.("base[href]");
    if (baseElement) {
      const href = baseElement.getAttribute?.("href");
      if (href) {
        try {
          cachedBase = new URLCtor(href, windowRef.location?.href || undefined);
          return cachedBase;
        } catch (error) {
          console.warn("Base href inválido; se ignorará.", error);
        }
      }
    }

    const location = windowRef.location ?? {};
    const origin = resolveOrigin(windowRef);
    const pathname = typeof location.pathname === "string" ? location.pathname : "/";
    const marker = "/ui/";
    let basePath = "/";

    if (pathname.endsWith("/ui")) {
      basePath = `${pathname}/`;
    } else if (pathname.includes(marker)) {
      basePath = pathname.slice(0, pathname.indexOf(marker) + marker.length);
    } else if (pathname.endsWith("/")) {
      basePath = pathname;
    } else {
      const lastSlashIndex = pathname.lastIndexOf("/");
      basePath = lastSlashIndex >= 0 ? pathname.slice(0, lastSlashIndex + 1) : "/";
    }

    try {
      cachedBase = new URLCtor(basePath, origin || location.href || undefined);
    } catch (error) {
      console.warn("No se pudo resolver la base a partir de window.location.", error);
      cachedBase = new URLCtor("/", origin || "http://localhost");
    }
    return cachedBase;
  };

  return (path = "") => {
    if (path instanceof URLCtor || path instanceof URL) {
      return path.toString();
    }

    const normalized = typeof path === "string" ? path.trim() : "";
    if (!normalized) {
      return resolveBase().toString();
    }

    if (hasProtocol(normalized)) {
      return normalized;
    }

    const baseUrl = resolveBase();

    if (normalized.startsWith("/")) {
      const origin = resolveOrigin(windowRef, baseUrl) || baseUrl;
      return new URLCtor(normalized, origin).toString();
    }

    return new URLCtor(normalized, baseUrl).toString();
  };
};
