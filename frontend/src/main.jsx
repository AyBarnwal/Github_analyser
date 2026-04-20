import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css"; // This now contains our sleek dark theme

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {/* You could wrap App in a Layout div here if you want a fixed container */}
    <main className="app-container">
      <App />
    </main>
  </React.StrictMode>
);