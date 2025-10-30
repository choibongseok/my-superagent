import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface User {
  id: string;
  email: string;
  name: string;
  picture?: string;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  user: User | null;
  isGuest: boolean;
  setTokens: (accessToken: string, refreshToken: string, user: User) => void;
  setGuestMode: () => void;
  clearTokens: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      user: null,
      isGuest: false,

      setTokens: (accessToken, refreshToken, user) =>
        set({
          accessToken,
          refreshToken,
          isAuthenticated: true,
          user,
          isGuest: false
        }),

      setGuestMode: () =>
        set({
          accessToken: null,
          refreshToken: null,
          isAuthenticated: true,
          user: { id: 'guest', email: 'guest@agenthq.local', name: 'Guest' },
          isGuest: true
        }),

      clearTokens: () =>
        set({
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          user: null,
          isGuest: false
        }),
    }),
    {
      name: 'auth-storage',
    }
  )
);
