import type { ReactNode } from 'react';

import { Alert, Card, Space, Typography } from 'antd';

import { AiWarningList } from './AiWarningList';

type Props = {
  title: string;
  actions?: ReactNode;
  error?: string | null;
  warnings?: string[];
  empty?: ReactNode;
  hasContent?: boolean;
  children?: ReactNode;
};

export function AiCapabilityActionCard({ title, actions, error, warnings = [], empty, hasContent, children }: Props) {
  const shouldRenderContent = hasContent ?? Boolean(children);

  return (
    <Card size="small" title={title} extra={actions}>
      <Space direction="vertical" style={{ width: '100%' }}>
        {error ? <Alert type="error" showIcon message={error} /> : null}
        <AiWarningList warnings={warnings} />
        {shouldRenderContent ? children : empty ?? <Typography.Text type="secondary">暂无 AI 结果。</Typography.Text>}
      </Space>
    </Card>
  );
}
