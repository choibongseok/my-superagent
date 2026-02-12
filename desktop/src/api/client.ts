/**
 * Unified API Client for AgentHQ Backend
 * Combines best practices from api/client.ts and services/api.ts
 * Integrated with Zustand auth store for state synchronization
 */
import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from "axios";
import { useAuthStore } from "../store/authStore";

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

class ApiClient {
  private client: AxiosInstance;
  private isRefreshing = false;
  private failedQueue: Array<{
    resolve: (value?: any) => void;
    reject: (error?: any) => void;
  }> = [];

  constructor() {
    this.client = axios.create({
      baseURL: API_URL,
      headers: {
        "Content-Type": "application/json",
      },
    });

    // Add request interceptor for auth token (dynamically from auth store)
    this.client.interceptors.request.use(
      (config) => {
        const { accessToken } = useAuthStore.getState();
        if (accessToken) {
          config.headers.Authorization = `Bearer ${accessToken}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Add response interceptor for error handling and token refresh
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

        // Handle 401 Unauthorized
        if (error.response?.status === 401 && !originalRequest._retry) {
          if (this.isRefreshing) {
            // Queue this request while refresh is in progress
            return new Promise((resolve, reject) => {
              this.failedQueue.push({ resolve, reject });
            })
              .then(() => {
                // Retry with new token
                return this.client(originalRequest);
              })
              .catch((err) => Promise.reject(err));
          }

          originalRequest._retry = true;
          this.isRefreshing = true;

          try {
            // Attempt to refresh token
            const { refreshToken } = useAuthStore.getState();
            if (!refreshToken) {
              throw new Error('No refresh token available');
            }

            const response = await axios.post<{
              access_token: string;
              refresh_token: string;
              user: {
                id: string;
                email: string;
                full_name: string | null;
              };
            }>(
              `${API_URL}/auth/refresh`,
              { refresh_token: refreshToken },
              { headers: { "Content-Type": "application/json" } }
            );

            const data = response.data;

            // Update auth store with new tokens
            useAuthStore.getState().setTokens(
              data.access_token,
              data.refresh_token,
              {
                id: data.user.id,
                email: data.user.email,
                name: data.user.full_name || data.user.email,
              }
            );

            // Retry all queued requests
            this.failedQueue.forEach((promise) => {
              promise.resolve();
            });
            this.failedQueue = [];

            // Retry original request
            return this.client(originalRequest);
          } catch (refreshError) {
            // Refresh failed - clear tokens and redirect to login
            this.failedQueue.forEach((promise) => {
              promise.reject(refreshError);
            });
            this.failedQueue = [];
            useAuthStore.getState().clearTokens();
            window.location.href = '/login';
            return Promise.reject(refreshError);
          } finally {
            this.isRefreshing = false;
          }
        }

        return Promise.reject(error);
      }
    );
  }

  async get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.get<T>(url, config);
    return response.data;
  }

  async post<T = any>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig
  ): Promise<T> {
    const response = await this.client.post<T>(url, data, config);
    return response.data;
  }

  async put<T = any>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig
  ): Promise<T> {
    const response = await this.client.put<T>(url, data, config);
    return response.data;
  }

  async patch<T = any>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig
  ): Promise<T> {
    const response = await this.client.patch<T>(url, data, config);
    return response.data;
  }

  async delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.delete<T>(url, config);
    return response.data;
  }
}

export const apiClient = new ApiClient();

// Type Definitions
export interface Task {
  id: string;
  user_id: string;
  prompt: string;
  task_type: 'docs' | 'sheets' | 'slides' | 'research';
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  result?: any;
  error_message?: string;
  document_url?: string;
  document_id?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateTaskRequest {
  prompt: string;
  task_type: 'docs' | 'sheets' | 'slides' | 'research';
  metadata?: any;
}

export interface Chat {
  id: string;
  title: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  messages?: Message[];
}

export interface CreateChatRequest {
  title: string;
}

export interface UpdateChatRequest {
  title?: string;
}

export interface Message {
  id: string;
  chat_id: string;
  user_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  updated_at: string;
}

export interface CreateMessageRequest {
  chat_id: string;
  content: string;
  role?: 'user' | 'assistant' | 'system';
}

// API Methods
export const authAPI = {
  getGoogleAuthUrl: async () => {
    return apiClient.get<{ auth_url: string }>('/auth/google');
  },

  handleCallback: async (code: string) => {
    return apiClient.post<{
      access_token: string;
      refresh_token: string;
      token_type: string;
      user: {
        id: string;
        email: string;
        full_name: string | null;
      };
    }>('/auth/callback', { code });
  },
};

export const tasksAPI = {
  create: async (data: CreateTaskRequest) => {
    return apiClient.post<Task>('/tasks', data);
  },

  list: async (page = 1, pageSize = 20) => {
    return apiClient.get<{
      tasks: Task[];
      total: number;
      page: number;
      page_size: number;
    }>('/tasks', {
      params: { page, page_size: pageSize },
    });
  },

  get: async (taskId: string) => {
    return apiClient.get<Task>(`/tasks/${taskId}`);
  },

  cancel: async (taskId: string) => {
    return apiClient.delete(`/tasks/${taskId}`);
  },
};

export const chatsAPI = {
  create: async (data: CreateChatRequest) => {
    return apiClient.post<Chat>('/chats', data);
  },

  list: async (skip = 0, limit = 50) => {
    return apiClient.get<{
      chats: Chat[];
      total: number;
    }>('/chats', {
      params: { skip, limit },
    });
  },

  get: async (chatId: string) => {
    return apiClient.get<Chat>(`/chats/${chatId}`);
  },

  update: async (chatId: string, data: UpdateChatRequest) => {
    return apiClient.patch<Chat>(`/chats/${chatId}`, data);
  },

  delete: async (chatId: string) => {
    return apiClient.delete(`/chats/${chatId}`);
  },
};

export const messagesAPI = {
  create: async (data: CreateMessageRequest) => {
    return apiClient.post<Message>('/messages', data);
  },

  list: async (chatId: string, skip = 0, limit = 100) => {
    return apiClient.get<{
      messages: Message[];
      total: number;
    }>('/messages', {
      params: { chat_id: chatId, skip, limit },
    });
  },
};
