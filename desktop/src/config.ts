/**
 * Application configuration
 */

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const config = {
  apiUrl: API_URL,
  endpoints: {
    auth: {
      google: "/auth/google",
      callback: "/auth/callback",
      me: "/auth/me",
    },
    tasks: {
      list: "/tasks",
      create: "/tasks",
      get: (id: string) => `/tasks/${id}`,
    },
  },
} as const;
