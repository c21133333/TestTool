import { createContext, useContext, useEffect, useState } from 'react';

import { createApi } from '../api/services';
import type { User } from '../api/types';

type AuthState = {
  token: string | null;
  user: User | null;
  isLoading: boolean;
  login: (
    username: string,
    password: string,
    options?: {
      beforeCommit?: () => Promise<void> | void;
    },
  ) => Promise<void>;
  logout: () => Promise<void>;
};

const STORAGE_KEY = 'eazytest-web-auth';

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      setIsLoading(false);
      return;
    }
    try {
      const parsed = JSON.parse(raw) as { token: string; user: User };
      setToken(parsed.token);
      setUser(parsed.user);
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    } finally {
      setIsLoading(false);
    }
  }, []);

  async function login(
    username: string,
    password: string,
    options?: {
      beforeCommit?: () => Promise<void> | void;
    },
  ) {
    const session = await createApi(null).login(username, password);
    await options?.beforeCommit?.();
    setToken(session.access_token);
    setUser(session.user);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: session.access_token, user: session.user }));
  }

  async function logout() {
    if (token) {
      await createApi(token).logout().catch(() => undefined);
    }
    setToken(null);
    setUser(null);
    window.localStorage.removeItem(STORAGE_KEY);
  }

  return (
    <AuthContext.Provider value={{ token, user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('认证上下文尚未初始化。');
  }
  return value;
}
