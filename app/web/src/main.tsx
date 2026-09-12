import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
import { seedDevToken } from "@/api/token";
import "@/index.css";

seedDevToken();

const root = document.getElementById("root");
if (!root) throw new Error("#root not found");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
