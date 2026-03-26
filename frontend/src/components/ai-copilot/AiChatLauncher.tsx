import {
  DeleteOutlined,
  InfoCircleOutlined,
  LoadingOutlined,
  PlusOutlined,
  StopOutlined,
} from '@ant-design/icons';
import {
  App,
  Button,
  Drawer,
  Empty,
  Input,
  Popconfirm,
  Popover,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { useLocation } from 'react-router-dom';

import { createApi } from '../../api/services';
import type { AiChatSessionSummary, Project } from '../../api/types';
import { useAuth } from '../../auth/AuthContext';
import { createClientId } from '../../utils/id';

const PROJECT_STORAGE_KEY = 'eazytest-ai-chat-project-id';
const CHAT_MODE_STORAGE_KEY = 'eazytest-ai-chat-mode';
const FLOAT_POSITION_STORAGE_KEY = 'eazytest-ai-chat-float-position';
const FLOAT_BUTTON_SIZE = 64;
const FLOAT_BUTTON_MARGIN = 16;
const FLOAT_BUTTON_DEFAULT_INSET = 24;

type ChatMode = 'project' | 'free';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

type ChatMeta = {
  session_id?: number;
  chat_mode?: ChatMode;
  project_id?: number | null;
  project_name?: string | null;
  warnings?: string[];
  redaction_applied?: boolean;
};

type FloatPosition = {
  left: number;
  top: number;
};

type FloatDragState = {
  pointerId: number;
  startX: number;
  startY: number;
  origin: FloatPosition;
  moved: boolean;
};

type SseEvent = {
  event: string;
  payload: Record<string, unknown>;
};

function createMessage(role: ChatMessage['role'], content: string): ChatMessage {
  const randomId = createClientId('chat-message');
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

function uniqueLines(lines: string[]) {
  return Array.from(new Set(lines.map((item) => item.trim()).filter(Boolean)));
}

function clampFloatPosition(position: FloatPosition): FloatPosition {
  if (typeof window === 'undefined') {
    return position;
  }
  const maxLeft = Math.max(FLOAT_BUTTON_MARGIN, window.innerWidth - FLOAT_BUTTON_SIZE - FLOAT_BUTTON_MARGIN);
  const maxTop = Math.max(FLOAT_BUTTON_MARGIN, window.innerHeight - FLOAT_BUTTON_SIZE - FLOAT_BUTTON_MARGIN);
  return {
    left: Math.min(Math.max(position.left, FLOAT_BUTTON_MARGIN), maxLeft),
    top: Math.min(Math.max(position.top, FLOAT_BUTTON_MARGIN), maxTop),
  };
}

function defaultFloatPosition(): FloatPosition {
  if (typeof window === 'undefined') {
    return { left: FLOAT_BUTTON_DEFAULT_INSET, top: FLOAT_BUTTON_DEFAULT_INSET };
  }
  return clampFloatPosition({
    left: window.innerWidth - FLOAT_BUTTON_SIZE - FLOAT_BUTTON_DEFAULT_INSET,
    top: window.innerHeight - FLOAT_BUTTON_SIZE - FLOAT_BUTTON_DEFAULT_INSET,
  });
}

function readStoredFloatPosition(): FloatPosition | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const rawValue = window.localStorage.getItem(FLOAT_POSITION_STORAGE_KEY);
    if (!rawValue) {
      return null;
    }
    const parsed = JSON.parse(rawValue) as Partial<FloatPosition>;
    if (typeof parsed.left !== 'number' || typeof parsed.top !== 'number') {
      return null;
    }
    return clampFloatPosition({ left: parsed.left, top: parsed.top });
  } catch {
    return null;
  }
}

function AiLauncherGlyph({ streaming }: { streaming: boolean }) {
  return (
    <span className={`ai-chat-launcher__glyph${streaming ? ' ai-chat-launcher__glyph--streaming' : ''}`} aria-hidden="true">
      <span className="ai-chat-launcher__sheen" />
      <span className="ai-chat-launcher__bubble">
        <span className="ai-chat-launcher__bubble-tail" />
        <span className="ai-chat-launcher__wordmark">
          <span className="ai-chat-launcher__wordmark-main">AI</span>
          <span className="ai-chat-launcher__wordmark-sub">CHAT</span>
        </span>
      </span>
      <span className="ai-chat-launcher__status">
        {streaming ? <LoadingOutlined /> : <span className="ai-chat-launcher__status-dot" />}
      </span>
    </span>
  );
}

export function AiChatLauncher() {
  const { token } = useAuth();
  const { message } = App.useApp();
  const location = useLocation();
  const api = useMemo(() => createApi(token), [token]);
  const listRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const projectsRequestRef = useRef<Promise<void> | null>(null);
  const sessionsRequestRef = useRef<Promise<void> | null>(null);
  const floatDragRef = useRef<FloatDragState | null>(null);
  const suppressFloatClickRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [floatPosition, setFloatPosition] = useState<FloatPosition>(() => readStoredFloatPosition() ?? defaultFloatPosition());
  const [floatDragging, setFloatDragging] = useState(false);
  const [chatMode, setChatMode] = useState<ChatMode>(() => {
    const saved = window.localStorage.getItem(CHAT_MODE_STORAGE_KEY);
    return saved === 'free' ? 'free' : 'project';
  });
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [sessions, setSessions] = useState<AiChatSessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [chatMeta, setChatMeta] = useState<ChatMeta | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const currentPageTitle = pageTitleFor(location.pathname);
  const contextNotes = useMemo(() => {
    const baseNotes = chatMode === 'project'
      ? [
          '聊天上下文仅包含当前项目的业务快照。',
          '环境中的敏感字段会自动脱敏。',
          '不会读取或输出用户、令牌、审计、系统表等敏感信息。',
        ]
      : [
          '自由对话不读取项目、套件、用例、执行或报告快照。',
          '适合通用问答、思路讨论和非项目化交流。',
        ];
    return uniqueLines([...baseNotes, ...(chatMeta?.warnings ?? [])]);
  }, [chatMeta?.warnings, chatMode]);
  const contextPopoverContent = (
    <div className="ai-chat-context-popover">
      <Typography.Text className="ai-chat-context-popover__lead">
        {chatMode === 'project'
          ? 'AI 会基于当前项目快照回答，但不会吞掉聊天空间。'
          : '当前处于自由对话模式，不绑定任何项目业务资产。'}
      </Typography.Text>
      <div className="ai-chat-context-popover__tags">
        {contextNotes.map((note) => (
          <Tag key={note}>{note}</Tag>
        ))}
      </div>
    </div>
  );

  function resetDraftState() {
    setMessages([]);
    setDraft('');
    setChatMeta(null);
    setStreamError(null);
  }

  function startNewConversation() {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
    setActiveSessionId(null);
    resetDraftState();
  }

  async function refreshChatSessions() {
    if (sessionsRequestRef.current) {
      await sessionsRequestRef.current;
      return;
    }
    setSessionsLoading(true);
    const request = api.listAiChatSessions()
      .then((result) => {
        setSessions(result.items);
        if (activeSessionId !== null && !result.items.some((item) => item.session_id === activeSessionId)) {
          setActiveSessionId(null);
        }
      })
      .catch((error: Error) => {
        message.error(error.message || '加载聊天历史失败。');
      })
      .finally(() => {
        sessionsRequestRef.current = null;
        setSessionsLoading(false);
      });
    sessionsRequestRef.current = request;
    await request;
  }

  async function openChatSession(sessionId: number) {
    setSessionsLoading(true);
    try {
      const session = await api.getAiChatSession(sessionId);
      setActiveSessionId(session.session_id);
      setChatMode(session.chat_mode);
      setSelectedProjectId(session.project_id);
      setMessages(session.messages.map((item) => createMessage(item.role, item.content)));
      setChatMeta({
        session_id: session.session_id,
        chat_mode: session.chat_mode,
        project_id: session.project_id,
        project_name: session.project_name,
        warnings: [],
        redaction_applied: true,
      });
      setStreamError(null);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载聊天会话失败。');
    } finally {
      setSessionsLoading(false);
    }
  }

  async function deleteCurrentConversation() {
    if (activeSessionId === null) {
      return;
    }
    const deletingSessionId = activeSessionId;
    try {
      await api.deleteAiChatSession(deletingSessionId);
      startNewConversation();
      await refreshChatSessions();
      message.success('聊天记录已删除。');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除聊天记录失败。');
    }
  }

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
    if (!open) {
      return;
    }
    void refreshChatSessions();
  }, [open]);

  useEffect(() => {
    window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, chatMode);
  }, [chatMode]);

  useEffect(() => {
    window.localStorage.setItem(FLOAT_POSITION_STORAGE_KEY, JSON.stringify(floatPosition));
  }, [floatPosition]);

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

  useEffect(() => {
    function handleWindowResize() {
      setFloatPosition((current) => clampFloatPosition(current));
    }

    window.addEventListener('resize', handleWindowResize);
    return () => window.removeEventListener('resize', handleWindowResize);
  }, []);

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
          session_id: activeSessionId ?? undefined,
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
            const nextSessionId = typeof event.payload.session_id === 'number' ? event.payload.session_id : undefined;
            setChatMeta({
              session_id: nextSessionId,
              chat_mode: event.payload.chat_mode === 'free' ? 'free' : 'project',
              project_id: typeof event.payload.project_id === 'number' ? event.payload.project_id : null,
              project_name: typeof event.payload.project_name === 'string' ? event.payload.project_name : null,
              warnings: Array.isArray(event.payload.warnings) ? event.payload.warnings.map((item) => String(item)) : [],
              redaction_applied: Boolean(event.payload.redaction_applied),
            });
            if (nextSessionId !== undefined) {
              setActiveSessionId(nextSessionId);
            }
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
            void refreshChatSessions();
            continue;
          }
          if (event.event === 'done') {
            void refreshChatSessions();
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
    startNewConversation();
  }

  function handleFloatPointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) {
      return;
    }
    floatDragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      origin: floatPosition,
      moved: false,
    };
    setFloatDragging(false);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handleFloatPointerMove(event: ReactPointerEvent<HTMLButtonElement>) {
    const dragState = floatDragRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return;
    }

    const deltaX = event.clientX - dragState.startX;
    const deltaY = event.clientY - dragState.startY;
    if (!dragState.moved && Math.hypot(deltaX, deltaY) < 6) {
      return;
    }

    dragState.moved = true;
    setFloatDragging(true);
    setFloatPosition(
      clampFloatPosition({
        left: dragState.origin.left + deltaX,
        top: dragState.origin.top + deltaY,
      }),
    );
  }

  function releaseFloatPointer(event: ReactPointerEvent<HTMLButtonElement>, suppressClick: boolean) {
    if (floatDragRef.current?.pointerId !== event.pointerId) {
      return;
    }
    floatDragRef.current = null;
    setFloatDragging(false);
    suppressFloatClickRef.current = suppressClick;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (suppressClick) {
      window.setTimeout(() => {
        suppressFloatClickRef.current = false;
      }, 120);
    }
  }

  function handleFloatPointerUp(event: ReactPointerEvent<HTMLButtonElement>) {
    releaseFloatPointer(event, Boolean(floatDragRef.current?.moved));
  }

  function handleFloatPointerCancel(event: ReactPointerEvent<HTMLButtonElement>) {
    releaseFloatPointer(event, false);
  }

  function handleFloatClick() {
    if (suppressFloatClickRef.current) {
      return;
    }
    setOpen(true);
  }

  return (
    <>
      <button
        type="button"
        className={`ai-chat-launcher${floatDragging ? ' ai-chat-launcher--dragging' : ''}`}
        style={{ left: floatPosition.left, top: floatPosition.top }}
        title="拖动或点击打开 AI 对话"
        aria-label="打开 AI 对话"
        onPointerDown={handleFloatPointerDown}
        onPointerMove={handleFloatPointerMove}
        onPointerUp={handleFloatPointerUp}
        onPointerCancel={handleFloatPointerCancel}
        onClick={handleFloatClick}
      >
        <AiLauncherGlyph streaming={streaming} />
      </button>
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
        width="min(560px, calc(100vw - 16px))"
        open={open}
        onClose={() => setOpen(false)}
        className="ai-chat-drawer"
        extra={(
          <Space size={8} className="ai-chat-drawer__actions">
            {streaming ? (
              <Button size="small" icon={<StopOutlined />} onClick={stopStreaming}>
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
            setActiveSessionId(null);
            resetDraftState();
          }}
        />
        <div className="ai-chat-drawer__history">
          <Select
            className="ai-chat-drawer__history-select"
            value={activeSessionId ?? undefined}
            placeholder={sessionsLoading ? '加载历史中...' : '切换历史会话'}
            loading={sessionsLoading}
            allowClear
            disabled={streaming}
            optionFilterProp="label"
            options={sessions.map((session) => ({
              value: session.session_id,
              label: `${session.title}${session.project_name ? ` · ${session.project_name}` : session.chat_mode === 'free' ? ' · 自由对话' : ''}`,
            }))}
            onChange={(value) => {
              if (typeof value !== 'number') {
                startNewConversation();
                return;
              }
              void openChatSession(value);
            }}
          />
          <Space size="small">
            <Button icon={<PlusOutlined />} onClick={startNewConversation} disabled={streaming}>
              新对话
            </Button>
            <Popconfirm
              title="删除当前会话？"
              description="删除后不可恢复，并会记录审计日志。"
              okText="删除"
              cancelText="取消"
              onConfirm={() => void deleteCurrentConversation()}
              disabled={activeSessionId === null}
            >
              <Button icon={<DeleteOutlined />} danger disabled={activeSessionId === null || streaming}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        </div>
        <div className="ai-chat-drawer__toolbar">
          {chatMode === 'project' ? (
            <div className="ai-chat-drawer__project-picker">
              <Typography.Text strong className="ai-chat-drawer__context-label">当前项目</Typography.Text>
              <Select
                value={selectedProjectId ?? undefined}
                placeholder={projectsLoading ? '加载项目中...' : '选择项目上下文'}
                loading={projectsLoading}
                allowClear
                disabled={projectsLoading || streaming}
                options={projects.map((project) => ({ value: project.id, label: `${project.name} #${project.id}` }))}
                onChange={(value) => {
                  setSelectedProjectId(value ?? null);
                  setActiveSessionId(null);
                  resetDraftState();
                }}
              />
            </div>
          ) : (
            <div className="ai-chat-drawer__project-picker ai-chat-drawer__project-picker--free">
              <Typography.Text strong className="ai-chat-drawer__context-label">当前模式</Typography.Text>
              <Typography.Text type="secondary">自由对话不读取项目、套件、用例、执行或报告快照。</Typography.Text>
            </div>
          )}
          <div className="ai-chat-drawer__context-rail">
            <Tag bordered={false} className="ai-chat-drawer__context-chip">{currentPageTitle}</Tag>
            <Typography.Text className="ai-chat-drawer__context-path" title={location.pathname}>
              {location.pathname}
            </Typography.Text>
            <Popover
              placement="bottomRight"
              trigger="click"
              overlayClassName="ai-chat-context-popover__overlay"
              content={contextPopoverContent}
            >
              <Button
                type="text"
                size="small"
                className="ai-chat-drawer__context-trigger"
                icon={<InfoCircleOutlined />}
              >
                上下文说明
              </Button>
            </Popover>
          </div>
        </div>

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
