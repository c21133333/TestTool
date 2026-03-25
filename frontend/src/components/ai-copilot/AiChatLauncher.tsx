import { CommentOutlined, LoadingOutlined, StopOutlined } from '@ant-design/icons';
import { Alert, App, Button, Drawer, Empty, FloatButton, Input, Segmented, Select, Space, Spin, Tag, Typography } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { createApi } from '../../api/services';
import type { Project } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';

const PROJECT_STORAGE_KEY = 'eazytest-ai-chat-project-id';
const CHAT_MODE_STORAGE_KEY = 'eazytest-ai-chat-mode';

type ChatMode = 'project' | 'free';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

type ChatMeta = {
  chat_mode?: ChatMode;
  project_id?: number | null;
  project_name?: string | null;
  warnings?: string[];
  redaction_applied?: boolean;
};

type SseEvent = {
  event: string;
  payload: Record<string, unknown>;
};

function createMessage(role: ChatMessage['role'], content: string): ChatMessage {
  const randomId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return { id: randomId, role, content };
}

function pageTitleFor(pathname: string) {
  if (pathname.startsWith('/workspace')) return '工作台';
  if (pathname.startsWith('/environments')) return '环境';
  if (pathname.startsWith('/executions')) return '执行';
  if (pathname.startsWith('/reports')) return '报告';
  if (pathname.startsWith('/audit-logs')) return '审计日志';
  if (pathname.startsWith('/users')) return '用户管理';
  return '概览';
}

function parseSseChunks(buffer: string): { events: SseEvent[]; rest: string } {
  const blocks = buffer.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? '';
  const events = blocks
    .map((block) => {
      const lines = block.split(/\r?\n/);
      let event = 'message';
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith('event:')) {
          event = line.slice(6).trim();
          continue;
        }
        if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trim());
        }
      }
      if (!dataLines.length) {
        return null;
      }
      try {
        return { event, payload: JSON.parse(dataLines.join('\n')) as Record<string, unknown> };
      } catch {
        return null;
      }
    })
    .filter((item): item is SseEvent => item !== null);
  return { events, rest };
}

function appendAssistantDelta(messages: ChatMessage[], delta: string) {
  const nextMessages = [...messages];
  for (let index = nextMessages.length - 1; index >= 0; index -= 1) {
    if (nextMessages[index].role !== 'assistant') {
      continue;
    }
    nextMessages[index] = { ...nextMessages[index], content: `${nextMessages[index].content}${delta}` };
    return nextMessages;
  }
  return [...nextMessages, createMessage('assistant', delta)];
}

export function AiChatLauncher() {
  const { token } = useAuth();
  const { message } = App.useApp();
  const location = useLocation();
  const api = useMemo(() => createApi(token), [token]);
  const listRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const projectsRequestRef = useRef<Promise<void> | null>(null);
  const [open, setOpen] = useState(false);
  const [chatMode, setChatMode] = useState<ChatMode>(() => {
    const saved = window.localStorage.getItem(CHAT_MODE_STORAGE_KEY);
    return saved === 'free' ? 'free' : 'project';
  });
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [chatMeta, setChatMeta] = useState<ChatMeta | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const currentPageTitle = pageTitleFor(location.pathname);

  useEffect(() => {
    if (chatMode !== 'project' || !open || projects.length > 0 || projectsLoading || projectsRequestRef.current) {
      return;
    }
    setProjectsLoading(true);
    const request = api.listProjects()
      .then((items) => {
        setProjects(items);
        const savedProjectId = Number(window.localStorage.getItem(PROJECT_STORAGE_KEY) || '');
        if (Number.isFinite(savedProjectId) && items.some((project) => project.id === savedProjectId)) {
          setSelectedProjectId(savedProjectId);
          return;
        }
        setSelectedProjectId(items[0]?.id ?? null);
      })
      .catch((error: Error) => {
        message.error(error.message || '加载项目列表失败。');
      })
      .finally(() => {
        projectsRequestRef.current = null;
        setProjectsLoading(false);
      });
    projectsRequestRef.current = request;
  }, [api, chatMode, message, open, projects.length, projectsLoading]);

  useEffect(() => {
    window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, chatMode);
  }, [chatMode]);

  useEffect(() => {
    if (selectedProjectId === null) {
      window.localStorage.removeItem(PROJECT_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(PROJECT_STORAGE_KEY, String(selectedProjectId));
  }, [selectedProjectId]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streaming, chatMeta]);

  useEffect(() => () => {
    abortRef.current?.abort();
  }, []);

  async function readErrorMessage(response: Response) {
    const contentType = response.headers.get('Content-Type') ?? '';
    if (contentType.includes('application/json')) {
      try {
        const payload = await response.json() as { detail?: string; message?: string };
        return payload.detail || payload.message || 'AI 对话请求失败。';
      } catch {
        return 'AI 对话请求失败。';
      }
    }
    return (await response.text()) || 'AI 对话请求失败。';
  }

  async function sendMessage() {
    const trimmedDraft = draft.trim();
    if (!trimmedDraft || streaming) {
      return;
    }
    if (chatMode === 'project' && projects.length > 0 && selectedProjectId === null) {
      message.warning('请先选择一个项目，再让 AI 基于项目内容回答。');
      return;
    }

    const userMessage = createMessage('user', trimmedDraft);
    const assistantMessage = createMessage('assistant', '');
    const requestMessages = [...messages, userMessage].map((item) => ({ role: item.role, content: item.content }));

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setDraft('');
    setStreamError(null);
    setStreaming(true);
    setChatMeta(null);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch('/api/v1/ai-copilot/chat/stream', {
        method: 'POST',
        headers: {
          Authorization: token ? `Bearer ${token}` : '',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chat_mode: chatMode,
          project_id: chatMode === 'project' ? selectedProjectId ?? undefined : undefined,
          page_path: location.pathname,
          page_title: currentPageTitle,
          messages: requestMessages,
        }),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(await readErrorMessage(response));
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        const parsed = parseSseChunks(buffer);
        buffer = parsed.rest;

        for (const event of parsed.events) {
          if (event.event === 'meta') {
            setChatMeta({
              chat_mode: event.payload.chat_mode === 'free' ? 'free' : 'project',
              project_id: typeof event.payload.project_id === 'number' ? event.payload.project_id : null,
              project_name: typeof event.payload.project_name === 'string' ? event.payload.project_name : null,
              warnings: Array.isArray(event.payload.warnings) ? event.payload.warnings.map((item) => String(item)) : [],
              redaction_applied: Boolean(event.payload.redaction_applied),
            });
            continue;
          }
          if (event.event === 'delta') {
            const delta = typeof event.payload.content === 'string' ? event.payload.content : '';
            if (delta) {
              setMessages((current) => appendAssistantDelta(current, delta));
            }
            continue;
          }
          if (event.event === 'error') {
            const errorMessage = typeof event.payload.message === 'string' ? event.payload.message : 'AI 对话暂时不可用。';
            setStreamError(errorMessage);
            setMessages((current) =>
              current.map((item) =>
                item.id === assistantMessage.id && !item.content.trim()
                  ? { ...item, content: `当前无法完成回答：${errorMessage}` }
                  : item,
              ),
            );
          }
        }

        if (done) {
          break;
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantMessage.id && item.content.trim()
              ? { ...item, content: `${item.content}\n\n[对话已中止]` }
              : item,
          ),
        );
      } else {
        const nextMessage = error instanceof Error ? error.message : 'AI 对话请求失败。';
        setStreamError(nextMessage);
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantMessage.id && !item.content.trim()
              ? { ...item, content: `当前无法完成回答：${nextMessage}` }
              : item,
          ),
        );
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function stopStreaming() {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }

  function resetConversation() {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
    setMessages([]);
    setDraft('');
    setChatMeta(null);
    setStreamError(null);
  }

  return (
    <>
      <FloatButton
        className="ai-chat-float"
        icon={streaming ? <LoadingOutlined /> : <CommentOutlined />}
        tooltip={<span>AI 对话</span>}
        onClick={() => setOpen(true)}
      />
      <Drawer
        title={(
          <div className="ai-chat-drawer__title">
            <Typography.Title level={4}>AI 对话</Typography.Title>
            <Typography.Text type="secondary">
              {chatMode === 'project' ? '基于当前项目业务快照回答，敏感字段自动脱敏。' : '自由对话模式，不依赖任何项目业务资产。'}
            </Typography.Text>
          </div>
        )}
        placement="right"
        width={520}
        open={open}
        onClose={() => setOpen(false)}
        className="ai-chat-drawer"
        extra={(
          <Space>
            {streaming ? (
              <Button icon={<StopOutlined />} onClick={stopStreaming}>
                停止
              </Button>
            ) : null}
            <Button onClick={resetConversation}>清空</Button>
          </Space>
        )}
      >
        <Segmented<ChatMode>
          className="ai-chat-drawer__mode"
          value={chatMode}
          disabled={streaming}
          options={[
            { label: '项目对话', value: 'project' },
            { label: '自由对话', value: 'free' },
          ]}
          onChange={(value) => {
            setChatMode(value);
            setMessages([]);
            setDraft('');
            setChatMeta(null);
            setStreamError(null);
          }}
        />
        <div className="ai-chat-drawer__toolbar">
          {chatMode === 'project' ? (
            <div className="ai-chat-drawer__project">
              <Typography.Text strong>当前项目</Typography.Text>
              <Select
                value={selectedProjectId ?? undefined}
                placeholder={projectsLoading ? '加载项目中...' : '选择项目上下文'}
                loading={projectsLoading}
                allowClear
                disabled={projectsLoading || streaming}
                options={projects.map((project) => ({ value: project.id, label: `${project.name} #${project.id}` }))}
                onChange={(value) => {
                  setSelectedProjectId(value ?? null);
                  setMessages([]);
                  setChatMeta(null);
                  setStreamError(null);
                }}
              />
            </div>
          ) : (
            <div className="ai-chat-drawer__project ai-chat-drawer__project--free">
              <Typography.Text strong>当前模式</Typography.Text>
              <Typography.Text type="secondary">自由对话不读取项目、套件、用例、执行或报告快照。</Typography.Text>
            </div>
          )}
          <div className="ai-chat-drawer__page">
            <Tag color="blue">{currentPageTitle}</Tag>
            <Typography.Text type="secondary">{location.pathname}</Typography.Text>
          </div>
        </div>

        <Alert
          className="ai-chat-drawer__notice"
          type="info"
          showIcon
          message={chatMode === 'project' ? 'AI 仅读取当前项目业务数据快照' : 'AI 当前处于自由对话模式'}
          description={
            chatMode === 'project'
              ? '不会读取或输出用户、令牌、审计、系统表等信息；环境中的敏感字段会自动脱敏。'
              : '自由对话不绑定项目信息，适合做通用问答、思路讨论和非项目化交流。'
          }
        />

        {chatMeta?.warnings?.length ? (
          <div className="ai-chat-drawer__warnings">
            {chatMeta.warnings.map((warning) => (
              <Tag key={warning}>{warning}</Tag>
            ))}
          </div>
        ) : null}

        <div ref={listRef} className="ai-chat-drawer__messages">
          {!messages.length ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                chatMode === 'project'
                  ? '可以问它：这个项目里有哪些高风险接口？最近失败执行集中在哪些场景？'
                  : '可以问它：帮我解释一个测试概念；帮我润色一段说明；帮我梳理一个排查思路。'
              }
            />
          ) : (
            messages.map((item) => (
              <div key={item.id} className={`ai-chat-message ai-chat-message--${item.role}`}>
                <div className="ai-chat-message__bubble">
                  <Typography.Paragraph>{item.content || (item.role === 'assistant' && streaming ? <Spin size="small" /> : '')}</Typography.Paragraph>
                </div>
              </div>
            ))
          )}
        </div>

        {streamError ? (
          <Typography.Text type="danger" className="ai-chat-drawer__error">
            {streamError}
          </Typography.Text>
        ) : null}

        <div className="ai-chat-drawer__composer">
          <Input.TextArea
            value={draft}
            autoSize={{ minRows: 3, maxRows: 8 }}
            placeholder={
              chatMode === 'project'
                ? '输入你的问题，AI 会优先结合当前项目内容回答。Enter 发送，Shift+Enter 换行。'
                : '输入你的问题，AI 将以自由对话模式回答。Enter 发送，Shift+Enter 换行。'
            }
            disabled={streaming}
            onChange={(event) => setDraft(event.target.value)}
            onPressEnter={(event) => {
              if (event.shiftKey) {
                return;
              }
              event.preventDefault();
              void sendMessage();
            }}
          />
          <div className="ai-chat-drawer__composer-actions">
            <Typography.Text type="secondary">
              {chatMode === 'project'
                ? (chatMeta?.project_name ? `当前上下文：${chatMeta.project_name}` : '当前未绑定具体项目')
                : '当前上下文：自由对话'}
            </Typography.Text>
            <Button type="primary" onClick={() => void sendMessage()} loading={streaming}>
              发送
            </Button>
          </div>
        </div>
      </Drawer>
    </>
  );
}
