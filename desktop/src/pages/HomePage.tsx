import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { tasksAPI, CreateTaskRequest } from '../services/api';
import { useAuthStore } from '../store/authStore';

export default function HomePage() {
  const [prompt, setPrompt] = useState('');
  const [taskType, setTaskType] = useState<'docs' | 'sheets' | 'slides'>('docs');
  const queryClient = useQueryClient();
  const clearTokens = useAuthStore((state) => state.clearTokens);

  // Fetch tasks
  const { data: tasksData, isLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => tasksAPI.list(),
  });

  // Create task mutation
  const createTaskMutation = useMutation({
    mutationFn: (data: CreateTaskRequest) => tasksAPI.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      setPrompt('');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (prompt.trim()) {
      createTaskMutation.mutate({
        prompt: prompt.trim(),
        task_type: taskType,
      });
    }
  };

  const handleLogout = () => {
    clearTokens();
    window.location.reload();
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            AgentHQ
          </h1>
          <button
            onClick={handleLogout}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
          >
            Logout
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Input Section */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6 mb-8">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                What would you like to create?
              </label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="E.g., Create a quarterly sales report for Q4 2024..."
                className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white resize-none"
                rows={4}
                disabled={createTaskMutation.isPending}
              />
            </div>

            <div className="flex items-center gap-4">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Output Type:
              </label>
              <div className="flex gap-2">
                {(['docs', 'sheets', 'slides'] as const).map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setTaskType(type)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      taskType === type
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                    }`}
                  >
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={!prompt.trim() || createTaskMutation.isPending}
              className="w-full py-3 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {createTaskMutation.isPending ? 'Creating...' : 'Create'}
            </button>
          </form>
        </div>

        {/* Tasks List */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
            Recent Tasks
          </h2>

          {isLoading ? (
            <div className="text-center py-8 text-gray-500">Loading...</div>
          ) : tasksData?.tasks.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              No tasks yet. Create your first task above!
            </div>
          ) : (
            <div className="space-y-4">
              {tasksData?.tasks.map((task) => (
                <div
                  key={task.id}
                  className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:border-blue-500 transition-colors"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1">
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                        {task.task_type.toUpperCase()}
                      </p>
                      <p className="text-gray-900 dark:text-white">
                        {task.prompt}
                      </p>
                    </div>
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-medium ${
                        task.status === 'completed'
                          ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                          : task.status === 'failed'
                          ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                          : task.status === 'processing'
                          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                          : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                      }`}
                    >
                      {task.status}
                    </span>
                  </div>

                  {task.document_url && (
                    <a
                      href={task.document_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center text-sm text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      Open in Google {task.task_type.charAt(0).toUpperCase() + task.task_type.slice(1)}
                      <svg
                        className="w-4 h-4 ml-1"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                        />
                      </svg>
                    </a>
                  )}

                  {task.error_message && (
                    <p className="text-sm text-red-600 dark:text-red-400 mt-2">
                      Error: {task.error_message}
                    </p>
                  )}

                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                    {new Date(task.created_at).toLocaleString()}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
