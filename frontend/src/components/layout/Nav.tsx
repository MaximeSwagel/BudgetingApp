import { NavLink } from "react-router-dom";

/** Top-level app navigation bar. */
export default function Nav() {
  return (
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
  );
}
