import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { RequireAdmin, RequireAuth } from './auth/guards'
import { Layout } from './components/Layout'
import { AdminPage } from './pages/AdminPage'
import { ChatPage } from './pages/ChatPage'
import { LoginPage } from './pages/LoginPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          {['/chat', '/chat/:sessionId'].map((path) => (
            <Route
              key={path}
              path={path}
              element={
                <RequireAuth>
                  <Layout>
                    <ChatPage />
                  </Layout>
                </RequireAuth>
              }
            />
          ))}
          <Route
            path="/admin"
            element={
              <RequireAdmin>
                <Layout>
                  <AdminPage />
                </Layout>
              </RequireAdmin>
            }
          />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
