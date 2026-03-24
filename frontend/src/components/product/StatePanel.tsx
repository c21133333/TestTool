import type { ReactNode } from 'react';

import { Empty, Result, Skeleton, Space, Typography } from 'antd';

type StatePanelProps = {
  title: string;
  description: string;
  action?: ReactNode;
  variant?: 'empty' | 'error' | 'loading' | 'info';
};

export function StatePanel({
  title,
  description,
  action,
  variant = 'empty',
}: StatePanelProps) {
  if (variant === 'loading') {
    return (
      <div className="state-panel">
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Skeleton active paragraph={{ rows: 3 }} />
          <div>
            <Typography.Title level={5}>{title}</Typography.Title>
            <Typography.Text type="secondary">{description}</Typography.Text>
          </div>
          {action}
        </Space>
      </div>
    );
  }

  if (variant === 'error') {
    return (
      <div className="state-panel">
        <Result status="error" title={title} subTitle={description} extra={action} />
      </div>
    );
  }

  return (
    <div className="state-panel">
      <Space direction="vertical" size="middle">
        <Empty description={title} />
        <Typography.Text type="secondary">{description}</Typography.Text>
        {action}
      </Space>
    </div>
  );
}
