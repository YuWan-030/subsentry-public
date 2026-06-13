import React from "react";
import ReactDOM from "react-dom/client";
import { App as AntdApp } from "antd";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ThemeProvider } from "./theme/ThemeProvider";
import "antd/dist/reset.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ThemeProvider>
      <AntdApp>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntdApp>
    </ThemeProvider>
  </React.StrictMode>
);
