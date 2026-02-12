/**
 * API Service - Compatibility Layer
 * Re-exports from unified API client
 */
import { apiClient as client, authAPI, tasksAPI, chatsAPI, messagesAPI } from '../api/client';

export const api = client;
export { authAPI, tasksAPI, chatsAPI, messagesAPI };

// Re-export types
export type {
  Task,
  CreateTaskRequest,
  Chat,
  CreateChatRequest,
  UpdateChatRequest,
  Message,
  CreateMessageRequest,
} from '../api/client';
