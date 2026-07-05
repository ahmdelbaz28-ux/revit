import React, { useEffect } from "react";

interface AccessibleToastProps {
	message: string;
	type?: "success" | "error" | "warning" | "info";
	duration?: number;
	onClose: () => void;
}

export function AccessibleToast({
	message,
	type = "info",
	duration = 5000,
	onClose,
}: AccessibleToastProps) {
	useEffect(() => {
		const timer = setTimeout(onClose, duration);
		return () => clearTimeout(timer);
	}, [duration, onClose]);

	const typeStyles = {
		success: "bg-green-900/50 border-green-700 text-green-200",
		error: "bg-red-900/50 border-red-700 text-red-200",
		warning: "bg-yellow-900/50 border-yellow-700 text-yellow-200",
		info: "bg-blue-900/50 border-blue-700 text-blue-200",
	};

	const typeLabels = {
		success: "Success",
		error: "Error",
		warning: "Warning",
		info: "Information",
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
					className="ml-2 text-slate-400 hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-500 rounded"
				>
					×
				</button>
			</div>
		</div>
	);
}
