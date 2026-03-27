import {
  ApiOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  EnvironmentOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { Button, Layout, Menu, Space, Typography } from 'antd';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from '../../auth/AuthContext';
import { canManageUsers, canViewAuditLogs } from '../../auth/permissions';
import { AiChatLauncher } from '../ai-copilot/AiChatLauncher';

const { Header, Content, Sider } = Layout;

type NavigationItem = {
  key: string;
  icon: ReactNode;
  label: string;
  code: string;
  description: string;
};

type NavigationGroup = {
  key: string;
  label: string;
  code: string;
  items: NavigationItem[];
};

const roleConfig = {
  admin: { label: '管理员', tone: '#bf4d4d', code: 'ADM' },
  tester: { label: '测试', tone: '#2f7a67', code: 'QAE' },
  developer: { label: '开发', tone: '#4a8bd0', code: 'DEV' },
} as const;

function buildNavigationGroups(canSeeAuditLogs: boolean, canSeeUsers: boolean): NavigationGroup[] {
  return [
    {
      key: 'observe',
      label: '观测',
      code: 'OBS',
      items: [
        {
          key: '/',
          icon: <DashboardOutlined />,
          label: '指挥台',
          code: 'OBS-01',
          description: '集中查看质量态势、执行状态与风险告警。',
        },
        {
          key: '/reports',
          icon: <FileSearchOutlined />,
          label: '报告归档',
          code: 'OBS-02',
          description: '查看报告产物、下载结果并回溯归档证据。',
        },
        ...(canSeeAuditLogs
          ? [
              {
                key: '/audit-logs',
                icon: <SafetyCertificateOutlined />,
                label: '审计日志',
                code: 'OBS-03',
                description: '追踪关键操作、资源变更和系统审计事件。',
              },
            ]
          : []),
      ],
    },
    {
      key: 'operate',
      label: '操作',
      code: 'OPS',
      items: [
        {
          key: '/workspace',
          icon: <ApiOutlined />,
          label: '工作台',
          code: 'OPS-01',
          description: '统一编排项目、套件、用例与 AI 辅助能力。',
        },
        {
          key: '/executions',
          icon: <PlayCircleOutlined />,
          label: '执行中心',
          code: 'OPS-02',
          description: '发起执行、追踪进度并处理取消或重试。',
        },
        {
          key: '/environments',
          icon: <EnvironmentOutlined />,
          label: '环境配置',
          code: 'OPS-03',
          description: '管理 Base URL、默认请求头和运行变量。',
        },
      ],
    },
    {
      key: 'schedule',
      label: '调度',
      code: 'SCH',
      items: [
        {
          key: '/scheduled-jobs',
          icon: <ClockCircleOutlined />,
          label: '定时任务',
          code: 'SCH-01',
          description: '管理套件调度、触发记录和下一次运行时间，将自动化运行与手工执行分层。',
        },
      ],
    },
    {
      key: 'govern',
      label: '治理',
      code: 'GOV',
      items: canSeeUsers
        ? [
            {
              key: '/users',
              icon: <TeamOutlined />,
              label: '用户管理',
              code: 'GOV-01',
              description: '维护账号、角色和访问权限边界。',
            },
          ]
        : [],
    },
  ].filter((group) => group.items.length > 0);
}

function getOperatorMonogram(displayName?: string | null, username?: string | null) {
  const source = (displayName || username || 'ET')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((segment) => segment[0]?.toUpperCase() ?? '');

  return source.join('') || 'ET';
}

export function AppShell() {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [showHeaderSectionMeta, setShowHeaderSectionMeta] = useState(false);

  const navigationGroups = useMemo(
    () => buildNavigationGroups(canViewAuditLogs(user), canManageUsers(user)),
    [user],
  );

  const navigationItems = navigationGroups.flatMap((group) => group.items);
  const activeItem =
    navigationItems.find((item) => item.key !== '/' && pathname.startsWith(item.key)) ??
    navigationItems.find((item) => item.key === pathname) ??
    navigationItems[0];
  const roleMeta = user ? roleConfig[user.role] : null;
  const userHandleLine =
    user?.username && user.display_name !== user.username
      ? roleMeta
        ? `@${user.username} · ${roleMeta.label}`
        : `@${user.username}`
      : roleMeta?.label ?? null;

  useEffect(() => {
    const heroAnchor = document.querySelector<HTMLElement>('[data-page-hero-anchor="true"]');

    if (!heroAnchor) {
      setShowHeaderSectionMeta(true);
      return;
    }

    setShowHeaderSectionMeta(false);

    const observer = new IntersectionObserver(
      ([entry]) => {
        setShowHeaderSectionMeta(!entry.isIntersecting);
      },
      {
        root: null,
        threshold: 0,
        rootMargin: '-72px 0px 0px 0px',
      },
    );

    observer.observe(heroAnchor);

    return () => observer.disconnect();
  }, [pathname]);

  return (
    <Layout className="app-shell">
      <Sider
        width={308}
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        collapsedWidth={96}
        breakpoint="lg"
        className="app-shell__sider"
        trigger={null}
      >
        <div className="brand-panel">
          <div className="brand-panel__serial">CTRL-01</div>
          {!collapsed ? (
            <>
              <span className="brand-panel__eyebrow">质量指挥平台</span>
              <Typography.Title level={3} className="brand-panel__title">
                EazyTest
              </Typography.Title>
              <Typography.Paragraph className="brand-panel__summary">
                面向接口测试的统一质量中台，聚合工作台、执行、报告、审计与调度视图。
              </Typography.Paragraph>
            </>
          ) : (
            <Typography.Title level={3} className="brand-panel__compact-title">
              ET
            </Typography.Title>
          )}
        </div>

        {!collapsed ? (
          <div className="app-shell__sider-signals">
            <span className="lab-chip">今日态势</span>
            <span className="lab-chip">执行调度</span>
            <span className="lab-chip">归档追踪</span>
          </div>
        ) : null}

        <div className="app-shell__menu-groups">
          {navigationGroups.map((group) => (
            <section key={group.key} className="app-shell__menu-section">
              {!collapsed ? (
                <div className="app-shell__menu-group-heading">
                  <span className="app-shell__menu-group-code">{group.code}</span>
                  <Typography.Text>{group.label}</Typography.Text>
                </div>
              ) : null}
              <Menu
                theme="light"
                mode="inline"
                className="app-shell__menu"
                selectedKeys={[activeItem.key]}
                items={group.items.map((item) => ({
                  key: item.key,
                  icon: item.icon,
                  label: <Link to={item.key}>{item.label}</Link>,
                }))}
              />
            </section>
          ))}
        </div>

        {!collapsed ? (
          <div className="app-shell__sider-footer">
            <Typography.Text className="app-shell__sider-footer-code">COMMAND STATUS</Typography.Text>
            <Typography.Paragraph className="app-shell__sider-footer-copy">
              用统一视图管理接口资产、执行记录、调度编排和归档结果，保证团队协同始终可见、可追踪。
            </Typography.Paragraph>
          </div>
        ) : null}
      </Sider>

      <Layout>
        <Header className="app-shell__header">
          <div className="app-shell__header-main">
            <Button
              type="text"
              className="app-shell__nav-trigger"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((current) => !current)}
            />
            {showHeaderSectionMeta ? (
              <div className="app-shell__section-meta">
                <div className="app-shell__section-copy">
                  <Typography.Title level={4}>{activeItem.label}</Typography.Title>
                  <Typography.Text type="secondary">{activeItem.description}</Typography.Text>
                </div>
              </div>
            ) : null}
          </div>

          <Space size="middle" className="app-shell__header-side">
            <div className="app-shell__user-meta">
              <div className="app-shell__user-avatar">{getOperatorMonogram(user?.display_name, user?.username)}</div>
              <div className="app-shell__user-copy">
                <Typography.Text className="app-shell__user-name">{user?.display_name}</Typography.Text>
                {userHandleLine ? (
                  <Typography.Text type="secondary" className="app-shell__user-handle">
                    {userHandleLine}
                  </Typography.Text>
                ) : null}
              </div>
            </div>

            <Button type="primary" className="app-shell__logout" icon={<LogoutOutlined />} onClick={() => void logout()}>
              退出登录
            </Button>
          </Space>
        </Header>

        <Content className="app-shell__content">
          <Outlet />
        </Content>
        <AiChatLauncher />
      </Layout>
    </Layout>
  );
}
