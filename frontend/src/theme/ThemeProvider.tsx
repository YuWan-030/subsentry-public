import { ConfigProvider } from "antd";
import type { ThemeConfig } from "antd";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type AppTheme = "apple" | "sweetpink";

const STORAGE_KEY = "subsentry-theme";

const THEME_ORDER: AppTheme[] = ["apple", "sweetpink"];

const THEME_LABELS: Record<AppTheme, string> = {
  apple: "Apple",
  sweetpink: "甜莓粉",
};

type ThemeContextValue = {
  theme: AppTheme;
  themeLabel: string;
  themeOptions: Array<{ value: AppTheme; label: string }>;
  setTheme: (theme: AppTheme) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

const antdThemes: Record<AppTheme, ThemeConfig> = {
  apple: {
    token: {
      colorPrimary: "#0071e3",
      colorInfo: "#0071e3",
      colorSuccess: "#34c759",
      colorWarning: "#ff9f0a",
      colorError: "#ff453a",
      borderRadius: 10,
      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif',
    },
  },
  sweetpink: {
    token: {
      colorPrimary: "#e68fb0",
      colorInfo: "#e68fb0",
      colorSuccess: "#f0a5c1",
      colorWarning: "#f3b974",
      colorError: "#ef7f9b",
      colorText: "#6d5462",
      colorTextSecondary: "#b2879a",
      colorBgLayout: "#fffafb",
      colorBgContainer: "rgba(255, 255, 255, 0.92)",
      borderRadius: 16,
      fontFamily: '"Trebuchet MS", "Segoe UI", "Helvetica Neue", sans-serif',
    },
  },
};

function isAppTheme(value: string | null): value is AppTheme {
  return value === "apple" || value === "sweetpink";
}

function readStoredTheme(): AppTheme {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return isAppTheme(stored) ? stored : "apple";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>(readStoredTheme);

  const setTheme = (nextTheme: AppTheme) => {
    setThemeState(nextTheme);
    window.localStorage.setItem(STORAGE_KEY, nextTheme);
  };

  const toggleTheme = () => {
    const currentIndex = THEME_ORDER.indexOf(theme);
    const nextTheme = THEME_ORDER[(currentIndex + 1) % THEME_ORDER.length];
    setTheme(nextTheme);
  };

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const value = useMemo(
    () => ({
      theme,
      themeLabel: THEME_LABELS[theme],
      themeOptions: THEME_ORDER.map((item) => ({ value: item, label: THEME_LABELS[item] })),
      setTheme,
      toggleTheme,
    }),
    [theme],
  );

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider theme={antdThemes[theme]}>{children}</ConfigProvider>
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return value;
}
