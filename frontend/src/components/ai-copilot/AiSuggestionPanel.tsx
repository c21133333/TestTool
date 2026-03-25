import type { ReactNode } from 'react';

import { Card, Empty, Space } from 'antd';

type AiSuggestionItem = {
  key: string;
  title: ReactNode;
  tags?: ReactNode;
  content: ReactNode;
};

type Props = {
  items: AiSuggestionItem[];
  emptyText: string;
};

export function AiSuggestionPanel({ items, emptyText }: Props) {
  if (!items.length) {
    return <Empty description={emptyText} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {items.map((item) => (
        <Card key={item.key} size="small" title={item.title} extra={item.tags}>
          {item.content}
        </Card>
      ))}
    </Space>
  );
}
