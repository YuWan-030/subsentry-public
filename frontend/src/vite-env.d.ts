/// <reference types="vite/client" />

interface Window {
  turnstile?: {
    render: (
      container: string | HTMLElement,
      options: {
        sitekey: string;
        theme?: "auto" | "light" | "dark";
        appearance?: "always" | "execute" | "interaction-only";
        callback?: (token: string) => void;
        "expired-callback"?: () => void;
        "error-callback"?: () => void;
      },
    ) => string;
    reset: (widgetId?: string) => void;
    remove: (widgetId?: string) => void;
  };
}
