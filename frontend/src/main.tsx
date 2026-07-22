import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import TransactionsPage from "./pages/TransactionsPage";
import BudgetPage from "./pages/BudgetPage";
import SettingsPage from "./pages/SettingsPage";
import "./index.css";

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="nav">
          <h1 className="logo">BudgetingApp</h1>
          <div className="nav-links">
            <NavLink to="/" end>
              Dashboard
            </NavLink>
            <NavLink to="/transactions">Transactions</NavLink>
            <NavLink to="/budget">Budget</NavLink>
            <NavLink to="/settings">Settings</NavLink>
          </div>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/budget" element={<BudgetPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
