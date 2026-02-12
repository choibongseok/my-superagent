/**
 * WebSocket service for real-time messaging
 */

import { logger } from '../utils/logger';

type MessageHandler = (data: any) => void;

export class WebSocketService {
  private ws: WebSocket | null = null;
  private handlers: Map<string, MessageHandler[]> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000; // 최대 30초
  private userId: string | null = null;
  private accessToken: string | null = null;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private intentionalClose = false; // 의도적 종료 플래그

  connect(userId: string, accessToken: string) {
    this.userId = userId;
    this.accessToken = accessToken;
    this.intentionalClose = false; // 연결 시작 시 플래그 리셋
    const wsUrl = `ws://localhost:8000/api/v1/messages/ws?token=${accessToken}`;

    try {
      // 기존 WebSocket 정리
      if (this.ws) {
        this.ws.onclose = null; // 기존 핸들러 제거
        this.ws.close();
      }

      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        logger.debug('WebSocket connected');
        this.reconnectAttempts = 0;
        this.emit('connected', {});
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          logger.debug('WebSocket message received:', data);

          if (data.type) {
            this.emit(data.type, data);
          }
        } catch (error) {
          logger.error('Error parsing WebSocket message:', error);
        }
      };

      this.ws.onerror = (error) => {
        logger.error('WebSocket error:', error);
        this.emit('error', { error });
      };

      this.ws.onclose = (event: CloseEvent) => {
        logger.debug(`WebSocket disconnected: code=${event.code}, reason=${event.reason}`);
        this.emit('disconnected', { code: event.code, reason: event.reason });
        
        // 정상 종료(1000) 또는 의도적 종료가 아닌 경우에만 재연결
        if (!this.intentionalClose && event.code !== 1000) {
          this.attemptReconnect();
        }
      };
    } catch (error) {
      logger.error('Error creating WebSocket:', error);
      this.attemptReconnect();
    }
  }

  private attemptReconnect() {
    // 이미 재연결 타이머가 있으면 취소
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.reconnectAttempts < this.maxReconnectAttempts && this.userId && this.accessToken) {
      this.reconnectAttempts++;
      
      // Exponential backoff: min(초기지연 * 2^시도횟수, 최대지연)
      const exponentialDelay = Math.min(
        this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
        this.maxReconnectDelay
      );

      logger.info(
        `Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${exponentialDelay}ms...`
      );

      this.reconnectTimeout = setTimeout(() => {
        const userId = this.userId;
        const accessToken = this.accessToken;
        
        if (userId && accessToken) {
          this.connect(userId, accessToken);
        }
      }, exponentialDelay);
    } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      logger.error('Max reconnection attempts reached. Giving up.');
      this.emit('reconnect_failed', {});
    }
  }

  disconnect() {
    this.intentionalClose = true; // 의도적 종료 표시
    
    // 재연결 타이머 취소
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    
    if (this.ws) {
      this.ws.close(1000, 'Client disconnecting'); // 정상 종료 코드
      this.ws = null;
    }
    
    this.userId = null;
    this.accessToken = null;
    this.reconnectAttempts = 0;
    this.handlers.clear();
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      logger.error('WebSocket is not connected');
    }
  }

  on(event: string, handler: MessageHandler) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, []);
    }
    this.handlers.get(event)!.push(handler);
  }

  off(event: string, handler: MessageHandler) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    }
  }

  private emit(event: string, data: any) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      handlers.forEach((handler) => handler(data));
    }
  }

  joinChat(chatId: string) {
    this.send({
      type: 'join_chat',
      chat_id: chatId,
    });
  }

  leaveChat(chatId: string) {
    this.send({
      type: 'leave_chat',
      chat_id: chatId,
    });
  }

  ping() {
    this.send({ type: 'ping' });
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

// Singleton instance
export const websocketService = new WebSocketService();
