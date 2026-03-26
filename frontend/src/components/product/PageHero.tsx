import type { ReactNode } from 'react';

import { Space, Typography } from 'antd';

type PageHeroProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  tags?: ReactNode[];
  actions?: ReactNode;
};

export function PageHero({ eyebrow, title, description, tags, actions }: PageHeroProps) {
  return (
    <div className="page-hero">
      <div className="page-hero__main">
        {eyebrow ? <span className="brand-panel__eyebrow">{eyebrow}</span> : null}
        <div className="page-hero__headline" data-page-hero-anchor="true">
          <Typography.Title level={2}>{title}</Typography.Title>
          {actions ? <div className="page-hero__actions">{actions}</div> : null}
        </div>
        {description ? <Typography.Paragraph className="page-hero__description">{description}</Typography.Paragraph> : null}
        {tags?.length ? <Space wrap>{tags}</Space> : null}
      </div>
    </div>
  );
}
