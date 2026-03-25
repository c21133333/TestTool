import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';

import { Card, Empty, Pagination, Space } from 'antd';

type AiSuggestionItem = {
  key: string;
  title: ReactNode;
  tags?: ReactNode;
  content: ReactNode;
};

type Props = {
  items: AiSuggestionItem[];
  emptyText: string;
  pageSize?: number;
};

export function AiSuggestionPanel({ items, emptyText, pageSize = 10 }: Props) {
  const [page, setPage] = useState(1);

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(items.length / pageSize));
    if (page > maxPage) {
      setPage(maxPage);
    }
  }, [items.length, page, pageSize]);

  if (!items.length) {
    return <Empty description={emptyText} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const startIndex = (page - 1) * pageSize;
  const pagedItems = items.slice(startIndex, startIndex + pageSize);

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {pagedItems.map((item) => (
        <Card key={item.key} size="small" title={item.title} extra={item.tags}>
          {item.content}
        </Card>
      ))}
      <Pagination
        align="end"
        current={page}
        pageSize={pageSize}
        total={items.length}
        showSizeChanger={false}
        hideOnSinglePage
        onChange={setPage}
      />
    </Space>
  );
}
