import axios from 'axios';
import { useAuthStore } from '../store/authStore';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const { accessToken } = useAuthStore.getState();
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const { refreshToken } = useAuthStore.getState();
        const response = await axios.post(`${API_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        });

        const { access_token, refresh_token } = response.data;
        useAuthStore.getState().setTokens(access_token, refresh_token);

        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        useAuthStore.getState().clearTokens();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  getGoogleAuthUrl: async () => {
    const response = await api.get<{ auth_url: string }>('/auth/google');
    return response.data;
  },

  handleCallback: async (code: string) => {
    const response = await api.post<{
      access_token: string;
      refresh_token: string;
    }>('/auth/callback', { code });
    return response.data;
  },
};

// Tasks API
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

export const tasksAPI = {
  create: async (data: CreateTaskRequest) => {
    const response = await api.post<Task>('/tasks', data);
    return response.data;
  },

  list: async (page = 1, pageSize = 20) => {
    const response = await api.get<{
      tasks: Task[];
      total: number;
      page: number;
      page_size: number;
    }>('/tasks', {
      params: { page, page_size: pageSize },
    });
    return response.data;
  },

  get: async (taskId: string) => {
    const response = await api.get<Task>(`/tasks/${taskId}`);
    return response.data;
  },

  cancel: async (taskId: string) => {
    await api.delete(`/tasks/${taskId}`);
  },
};
