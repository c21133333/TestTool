import { App as AntdApp, ConfigProvider, Space, Spin, Typography, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import dayjs from 'dayjs';
import 'dayjs/locale/zh-cn';
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

dayjs.locale('zh-cn');

const appTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: '#a14c2f',
    colorInfo: '#315d7a',
    colorSuccess: '#3f6a45',
    colorWarning: '#b7791f',
    colorError: '#b4473a',
    colorBgBase: '#f3eadb',
    colorBgLayout: '#efe4d0',
    colorBgContainer: '#fffaf2',
    colorTextBase: '#2f241c',
    colorTextSecondary: '#766455',
    colorBorder: '#d6c4ae',
    colorSplit: '#e6d9c7',
    borderRadius: 18,
    fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
    boxShadow: '0 18px 40px rgba(102, 74, 38, 0.08)',
  },
};

function RouteLoadingScreen() {
  return (
    <div className="loading-screen">
      <Space direction="vertical" align="center" size="middle">
        <Spin size="large" />
        <Typography.Text type="secondary">正在装载页面资源...</Typography.Text>
      </Space>
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
    <ConfigProvider theme={appTheme} locale={zhCN}>
      <AntdApp>
        <AuthProvider>
          <AuthenticatedApp />
        </AuthProvider>
      </AntdApp>
    </ConfigProvider>
  );
}
