import type { ReactNode } from 'react';

import { Alert, Collapse, Drawer, Empty } from 'antd';

import { StatePanel } from '../product/StatePanel';

type HistoryItem = {
  key: string;
  label: ReactNode;
  content: ReactNode;
};

type Props = {
  title: string;
  open: boolean;
  onClose: () => void;
  headerContent?: ReactNode;
  loading?: boolean;
  error?: string | null;
  items: HistoryItem[];
  emptyText: string;
  width?: number | string;
};

export function AiArtifactHistoryDrawer({
  title,
  open,
  onClose,
  headerContent,
  loading = false,
  error,
  items,
  emptyText,
  width = 520,
}: Props) {
  return (
    <Drawer title={title} placement="right" open={open} onClose={onClose} width={width}>
      {headerContent ? <div style={{ marginBottom: 12 }}>{headerContent}</div> : null}
      {loading ? (
        <StatePanel title="正在加载 AI 历史" description="正在拉取当前对象的 AI artifact 历史。" variant="loading" />
      ) : error ? (
        <Alert type="error" showIcon message={error} />
      ) : !items.length ? (
        <Empty description={emptyText} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Collapse
          ghost
          items={items.map((item) => ({
            key: item.key,
            label: item.label,
            children: item.content,
          }))}
        />
      )}
    </Drawer>
  );
}
