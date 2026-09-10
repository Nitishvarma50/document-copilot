import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./auth/ProtectedRoute";
import "./App.css";
import { ChatPage } from "./pages/ChatPage";
import { SignInPage } from "./pages/SignInPage";
import { SignUpPage } from "./pages/SignUpPage";

function App() {
  return (
    <Routes>
      <Route path="/login" element={<SignInPage />} />
      <Route path="/signup" element={<SignUpPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/chat/:threadId?" element={<ChatPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
