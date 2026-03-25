import { Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import type { AiTestPoint } from '../../api/types';

type Props = {
  testPoints: AiTestPoint[];
  selectedPointIds: string[];
  canEdit: boolean;
  onSelectionChange: (selectedPointIds: string[]) => void;
};

export function AiTestPointTable({ testPoints, selectedPointIds, canEdit, onSelectionChange }: Props) {
  const columns: ColumnsType<AiTestPoint> = [
    {
      title: '测试点',
      dataIndex: 'title',
      width: 240,
      render: (_, point) => (
        <Typography.Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}>
          {point.title}
        </Typography.Paragraph>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 140,
      render: (value: string) => <Tag color={value === 'happy_path' ? 'green' : value === 'negative_path' ? 'gold' : 'blue'}>{value}</Tag>,
    },
    {
      title: '风险',
      dataIndex: 'risk_level',
      width: 100,
      render: (value: string) => <Tag color={value === 'high' ? 'red' : value === 'medium' ? 'orange' : 'default'}>{value}</Tag>,
    },
    {
      title: '现有覆盖',
      dataIndex: 'covered_by_existing_cases',
      width: 120,
      render: (value: boolean) => <Tag color={value ? 'default' : 'processing'}>{value ? '已覆盖' : '待补齐'}</Tag>,
    },
    {
      title: '建议草稿数',
      dataIndex: 'suggested_case_count',
      width: 110,
    },
    {
      title: '原因',
      dataIndex: 'reason',
      render: (value: string) => (
        <Typography.Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}>
          {value}
        </Typography.Paragraph>
      ),
    },
  ];

  return (
    <Table<AiTestPoint>
      rowKey="id"
      dataSource={testPoints}
      columns={columns}
      rowSelection={{
        selectedRowKeys: selectedPointIds,
        onChange: (nextKeys) => onSelectionChange(nextKeys.map(String)),
        getCheckboxProps: () => ({ disabled: !canEdit }),
      }}
      pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }}
      size="small"
      scroll={{ x: 980, y: 320 }}
      locale={{ emptyText: '先生成测试点，再在这里挑选需要落草稿的条目。' }}
    />
  );
}
