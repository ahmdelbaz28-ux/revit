import React, { useEffect } from 'react';

interface AccessibleToastProps {
  message: string;
  type?: 'success' | 'error' | 'warning' | 'info';
  duration?: number;
  onClose: () => void;
}

export function AccessibleToast({
  message,
  type = 'info',
  duration = 5000,
  onClose,
}: AccessibleToastProps) {
  useEffect(() => {
    const timer = setTimeout(onClose, duration);
    return () => clearTimeout(timer);
  }, [duration, onClose]);

  const typeStyles = {
    success: 'bg-green-50 border-green-500 text-green-800',
    error: 'bg-red-50 border-red-500 text-red-800',
    warning: 'bg-yellow-50 border-yellow-500 text-yellow-800',
    info: 'bg-blue-50 border-blue-500 text-blue-800',
  };

  const typeLabels = {
    success: 'Success',
    error: 'Error',
    warning: 'Warning',
    info: 'Information',
  };

  return (
    <div
      role="alert"
      aria-live="assertive"
      aria-label={`${typeLabels[type]}: ${message}`}
      className={`fixed bottom-4 right-4 z-50 p-4 rounded-lg border-l-4 shadow-lg ${typeStyles[type]}`}
    >
      <div className="flex items-center gap-2">
        <p className="font-medium">{message}</p>
        <button
          onClick={onClose}
          aria-label="Dismiss notification"
          className="ml-2 text-gray-500 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-400 rounded"
        >
          ×
        </button>
      </div>
    </div>
  );
}
