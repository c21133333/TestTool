import { App as AntdApp, ConfigProvider, Space, Spin, Typography, theme, type ThemeConfig } from 'antd';
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
const ScheduledJobsPage = lazy(async () => ({ default: (await import('./pages/ScheduledJobsPage')).ScheduledJobsPage }));
const UsersPage = lazy(async () => ({ default: (await import('./pages/UsersPage')).UsersPage }));
const WorkspacePage = lazy(async () => ({ default: (await import('./pages/WorkspacePage')).WorkspacePage }));

dayjs.locale('zh-cn');

const appTheme: ThemeConfig = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: '#2f5f93',
    colorInfo: '#4a8bd0',
    colorSuccess: '#2f7a67',
    colorWarning: '#c48833',
    colorError: '#bf4d4d',
    colorBgBase: '#edf2f8',
    colorBgLayout: '#e7edf5',
    colorBgContainer: '#f8fbff',
    colorTextBase: '#172131',
    colorTextSecondary: '#5d6b80',
    colorBorder: '#d3dcea',
    colorSplit: '#e0e7f0',
    borderRadius: 16,
    controlHeight: 40,
    controlHeightSM: 32,
    fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
    boxShadow: '0 22px 48px rgba(24, 38, 58, 0.08)',
  },
  components: {
    Layout: {
      bodyBg: 'transparent',
      headerBg: 'rgba(248, 251, 255, 0.82)',
      siderBg: 'rgba(244, 248, 253, 0.9)',
      triggerBg: 'transparent',
    },
    Button: {
      borderRadius: 12,
      primaryShadow: 'none',
    },
    Card: {
      headerBg: 'transparent',
    },
    Input: {
      activeBorderColor: '#2f5f93',
      hoverBorderColor: '#4a8bd0',
    },
    Menu: {
      itemBg: 'transparent',
      itemColor: '#31445e',
      itemHoverBg: 'rgba(47, 95, 147, 0.08)',
      itemHoverColor: '#1e4167',
      itemSelectedBg: 'rgba(47, 95, 147, 0.12)',
      itemSelectedColor: '#1e4167',
      itemBorderRadius: 14,
      groupTitleColor: '#6c7a8f',
    },
    Tag: {
      defaultBg: 'rgba(47, 95, 147, 0.08)',
      defaultColor: '#2f5f93',
    },
    Table: {
      headerBg: 'rgba(47, 95, 147, 0.06)',
    },
  },
};

function RouteLoadingScreen() {
  return (
    <div className="loading-screen">
      <Space direction="vertical" align="center" size="middle">
        <Spin size="large" />
        <Typography.Text type="secondary">正在加载指挥舱资源...</Typography.Text>
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
              <Route path="scheduled-jobs" element={<ScheduledJobsPage />} />
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
