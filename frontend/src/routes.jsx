import { Navigate } from "react-router-dom";

import LoginPage from "./pages/LoginPage";
import PasswordsPage from "./pages/PasswordsPage";
import UsersPage from "./pages/UsersPage";
import { getCurrentUser, isAuth } from "./utils";

const ProtectedRoute = ({ children, role }) => {
  if (!isAuth()) return <Navigate to="/login" replace />;
  if (role && getCurrentUser()?.role !== role) return <Navigate to="/passwords" replace />;
  return children;
};

const routes = [
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/passwords",
    element: (
      <ProtectedRoute>
        <PasswordsPage />
      </ProtectedRoute>
    ),
  },
  {
    path: "/users",
    element: (
      <ProtectedRoute role="admin">
        <UsersPage />
      </ProtectedRoute>
    ),
  },
];

export default routes;
