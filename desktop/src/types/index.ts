/**
 * TypeScript type definitions
 */

export type TaskType = "research" | "document" | "slides" | "sheets" | "custom";
export type TaskStatus = "pending" | "processing" | "completed" | "failed";

export interface User {
  id: string;
  email: string;
  full_name?: string;
  profile_picture?: string;
  created_at: string;
}

export interface Task {
  id: string;
  type: TaskType;
  status: TaskStatus;
  prompt: string;
  config: Record<string, any>;
  result?: Record<string, any>;
  error_message?: string;
  google_doc_url?: string;
  google_slides_url?: string;
  google_sheets_url?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface CreateTaskRequest {
  type: TaskType;
  prompt: string;
  config?: Record<string, any>;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}
