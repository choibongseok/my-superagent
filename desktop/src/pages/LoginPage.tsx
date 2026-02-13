import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authAPI } from '../services/api';
import { useAuthStore } from '../store/authStore';
import { logger } from '../utils/logger';

interface OAuthCallbackMessage {
  type: 'agenthq:oauth:callback';
  code?: string | null;
  error?: string | null;
  error_description?: string | null;
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const API_ORIGIN = new URL(API_URL, window.location.origin).origin;

const waitForOAuthCallback = (authUrl: string): Promise<string> =>
  new Promise((resolve, reject) => {
    const popup = window.open(authUrl, 'agenthq-oauth', 'popup=yes,width=520,height=720');

    if (!popup) {
      reject(new Error('Unable to open OAuth popup. Please allow popups and try again.'));
      return;
    }

    const cleanup = (closePopup = false) => {
      window.removeEventListener('message', onMessage);
      window.clearTimeout(timeoutId);
      window.clearInterval(closePollId);

      if (closePopup && !popup.closed) {
        popup.close();
      }
    };

    const onMessage = (event: MessageEvent<OAuthCallbackMessage>) => {
      if (event.origin !== API_ORIGIN) {
        return;
      }

      const data = event.data;
      if (!data || data.type !== 'agenthq:oauth:callback') {
        return;
      }

      if (data.error) {
        cleanup(true);
        reject(new Error(data.error_description || data.error));
        return;
      }

      if (!data.code) {
        cleanup(true);
        reject(new Error('Authorization code was not received.'));
        return;
      }

      cleanup(true);
      resolve(data.code);
    };

    const timeoutId = window.setTimeout(() => {
      cleanup(true);
      reject(new Error('Login timed out. Please try again.'));
    }, 120000);

    const closePollId = window.setInterval(() => {
      if (popup.closed) {
        cleanup(false);
        reject(new Error('Login was cancelled.'));
      }
    }, 400);

    window.addEventListener('message', onMessage);
  });

export default function LoginPage() {
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { setTokens, setGuestMode } = useAuthStore();

  const handleGoogleLogin = async () => {
    try {
      setIsLoading(true);

      const { auth_url } = await authAPI.getGoogleAuthUrl();
      const code = await waitForOAuthCallback(auth_url);

      const data = await authAPI.handleCallback(code);
      setTokens(data.access_token, data.refresh_token, {
        id: data.user.id,
        email: data.user.email,
        name: data.user.full_name || data.user.email,
      });
      navigate('/');
    } catch (error) {
      logger.error('Login error:', error);
      const message = error instanceof Error ? error.message : 'Login failed. Please try again.';
      alert(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSkipLogin = () => {
    setGuestMode();
    navigate('/');
  };

  return (
    <div className="min-h-screen flex bg-white dark:bg-gray-900">
      {/* Left Side - Branding & Info */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-blue-600 to-indigo-700 dark:from-blue-800 dark:to-indigo-900 p-12 flex-col justify-between">
        <div>
          <h1 className="text-5xl font-bold text-white mb-4">
            AgentHQ
          </h1>
          <p className="text-xl text-blue-100 mb-8">
            AI Super Agent Hub
          </p>
        </div>

        <div className="space-y-8">
          <div className="flex items-start space-x-4">
            <div className="flex-shrink-0 w-12 h-12 bg-white/20 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Powerful AI Agents</h3>
              <p className="text-blue-100">Deploy and manage multiple AI agents for complex tasks</p>
            </div>
          </div>

          <div className="flex items-start space-x-4">
            <div className="flex-shrink-0 w-12 h-12 bg-white/20 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Secure & Private</h3>
              <p className="text-blue-100">Your data stays secure with enterprise-grade encryption</p>
            </div>
          </div>

          <div className="flex items-start space-x-4">
            <div className="flex-shrink-0 w-12 h-12 bg-white/20 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
              </svg>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Intelligent Workflows</h3>
              <p className="text-blue-100">Automate complex workflows with memory and context</p>
            </div>
          </div>
        </div>

        <div className="text-blue-100 text-sm">
          © 2025 AgentHQ. All rights reserved.
        </div>
      </div>

      {/* Right Side - Login Form */}
      <div className="flex-1 flex items-center justify-center p-8 lg:p-12">
        <div className="w-full max-w-md space-y-8">
          {/* Mobile Header */}
          <div className="text-center lg:hidden mb-8">
            <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
              AgentHQ
            </h1>
            <p className="text-gray-600 dark:text-gray-400">
              AI Super Agent Hub
            </p>
          </div>

          {/* Login Form */}
          <div>
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
              Welcome back
            </h2>
            <p className="text-gray-600 dark:text-gray-400 mb-8">
              Sign in to your account to continue
            </p>

            <div className="space-y-4">
              <button
                onClick={handleGoogleLogin}
                disabled={isLoading}
                className="group relative w-full flex items-center justify-center py-4 px-6 border border-gray-300 dark:border-gray-600 text-base font-medium rounded-lg text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm hover:shadow-md"
              >
                {isLoading ? (
                  <span>Connecting...</span>
                ) : (
                  <>
                    <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
                      <path
                        fill="#4285F4"
                        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                      />
                      <path
                        fill="#34A853"
                        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                      />
                      <path
                        fill="#FBBC04"
                        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                      />
                      <path
                        fill="#EA4335"
                        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                      />
                    </svg>
                    Continue with Google
                  </>
                )}
              </button>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300 dark:border-gray-600"></div>
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-4 bg-white dark:bg-gray-900 text-gray-500 dark:text-gray-400">
                    Or
                  </span>
                </div>
              </div>

              <button
                onClick={handleSkipLogin}
                className="group relative w-full flex items-center justify-center py-4 px-6 border-2 border-gray-300 dark:border-gray-600 text-base font-medium rounded-lg text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-400 transition-all"
              >
                <svg className="w-5 h-5 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
                Continue as Guest
              </button>
            </div>

            <div className="mt-8 text-center text-sm text-gray-500 dark:text-gray-400">
              By signing in, you agree to our{' '}
              <a href="#" className="text-blue-600 dark:text-blue-400 hover:underline">Terms of Service</a>
              {' '}and{' '}
              <a href="#" className="text-blue-600 dark:text-blue-400 hover:underline">Privacy Policy</a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
