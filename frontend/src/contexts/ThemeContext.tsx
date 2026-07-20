import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";

interface Theme {
  readonly dark: boolean;
  readonly toggle: () => void;
}

const ThemeContext = createContext<Theme | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [dark, setDark] = useState<boolean>(() =>
    localStorage.getItem("dark") === "true" ||
    (!localStorage.getItem("dark") &&
      window.matchMedia("(prefers-color-scheme: dark)").matches)
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("dark", dark.toString());
  }, [dark]);

  const toggle = useCallback(() => setDark((prev) => !prev), []);

  return (
    <ThemeContext.Provider value={{ dark, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}