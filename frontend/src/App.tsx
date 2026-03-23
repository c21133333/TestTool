import { App as AntdApp, ConfigProvider, Spin, theme } from 'antd';
import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider, useAuth } from './auth/AuthContext';
import { canManageUsers, canViewAuditLogs } from './auth/permissions';

const AppShell = lazy(async () => ({ default: (await import('./components/shell/AppShell')).AppShell }));
const AuditLogsPage = lazy(async () => ({ default: (await import('./pages/AuditLogsPage')).AuditLogsPage }));
const DashboardPage = lazy(async () => ({ default: (await import('./pages/DashboardPage')).DashboardPage }));
const EnvironmentsPage = lazy(async () => ({ default: (await import('./pages/EnvironmentsPage')).EnvironmentsPage }));
const ExecutionsPage = lazy(async () => ({ default: (await import('./pages/ExecutionsPage')).ExecutionsPage }));
const LoginPage = lazy(async () => ({ default: (await import('./pages/LoginPage')).LoginPage }));
const ReportsPage = lazy(async () => ({ default: (await import('./pages/ReportsPage')).ReportsPage }));
const UsersPage = lazy(async () => ({ default: (await import('./pages/UsersPage')).UsersPage }));
const WorkspacePage = lazy(async () => ({ default: (await import('./pages/WorkspacePage')).WorkspacePage }));

const appTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#f97316',
    colorInfo: '#fb923c',
    colorSuccess: '#22c55e',
    colorError: '#ef4444',
    colorBgBase: '#0c1117',
    colorBgContainer: 'rgba(18, 24, 33, 0.88)',
    colorTextBase: '#f8fafc',
    colorTextSecondary: '#9ca3af',
    borderRadius: 18,
    fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
  },
};

function RouteLoadingScreen() {
  return (
    <div className="loading-screen">
      <Spin size="large" />
    </div>
  );
}

function RoleGuard({
  allow,
  children,
}: {
  allow: boolean;
  children: React.ReactNode;
}) {
  return allow ? <>{children}</> : <Navigate to="/" replace />;
}

function AuthenticatedApp() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <RouteLoadingScreen />;
  }

  return (
    <Suspense fallback={<RouteLoadingScreen />}>
      {!user ? (
        <LoginPage />
      ) : (
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<AppShell />}>
              <Route index element={<DashboardPage />} />
              <Route path="workspace" element={<WorkspacePage />} />
              <Route path="environments" element={<EnvironmentsPage />} />
              <Route path="executions" element={<ExecutionsPage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route
                path="audit-logs"
                element={
                  <RoleGuard allow={canViewAuditLogs(user)}>
                    <AuditLogsPage />
                  </RoleGuard>
                }
              />
              <Route
                path="users"
                element={
                  <RoleGuard allow={canManageUsers(user)}>
                    <UsersPage />
                  </RoleGuard>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      )}
    </Suspense>
  );
}

export default function App() {
  return (
    <ConfigProvider theme={appTheme}>
      <AntdApp>
        <AuthProvider>
          <AuthenticatedApp />
        </AuthProvider>
      </AntdApp>
    </ConfigProvider>
  );
}
