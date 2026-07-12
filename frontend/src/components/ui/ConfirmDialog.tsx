
import type React from "react";
import { useCallback, useEffect, useRef } from "react";

interface ConfirmDialogProps {
	isOpen: boolean;
	title: string;
	message: string;
	confirmLabel?: string;
	cancelLabel?: string;
	onConfirm: () => void;
	onCancel: () => void;
	variant?: "danger" | "warning" | "default";
}

export function ConfirmDialog({
	isOpen,
	title,
	message,
	confirmLabel = "Confirm",
	cancelLabel = "Cancel",
	onConfirm,
	onCancel,
	variant = "default",
}: ConfirmDialogProps) {
	const dialogRef = useRef<HTMLDivElement>(null);
	const cancelButtonRef = useRef<HTMLButtonElement>(null);
	const previousFocusRef = useRef<HTMLElement | null>(null);

	// Store the element that triggered the dialog and auto-focus cancel button
	useEffect(() => {
		if (isOpen) {
			previousFocusRef.current = document.activeElement as HTMLElement;
			// Auto-focus the cancel button when dialog opens
			const timer = setTimeout(() => {
				cancelButtonRef.current?.focus();
			}, 50);
			return () => clearTimeout(timer);
		} else {
			// Return focus to the trigger element when dialog closes
			if (previousFocusRef.current) {
				previousFocusRef.current.focus();
				previousFocusRef.current = null;
			}
		}
	}, [isOpen]);

	// Focus trap: keep Tab cycling within dialog elements
	const handleKeyDown = useCallback(
		(e: React.KeyboardEvent) => {
			if (e.key === "Escape") {
				onCancel();
				return;
			}

			if (e.key === "Tab" && dialogRef.current) {
				const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
					'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
				);
				if (focusable.length === 0) return;

				const first = focusable[0];
				const last = focusable[focusable.length - 1];

				if (e.shiftKey) {
					if (document.activeElement === first) {
						e.preventDefault();
						last.focus();
					}
				} else {
					if (document.activeElement === last) {
						e.preventDefault();
						first.focus();
					}
				}
			}
		},
		[onCancel],
	);

	if (!isOpen) return null;

	const variantClasses = {
		danger: "bg-danger hover:bg-danger/90 focus:ring-red-500",
		warning: "bg-yellow-600 hover:bg-yellow-700 focus:ring-yellow-500",
		default: "bg-blue-600 hover:bg-blue-700 focus:ring-blue-500",
	};

	return (
		<div  // NOSONAR: typescript:S6847
			role="dialog"
			aria-modal="true"
			aria-labelledby="confirm-dialog-title"
			aria-describedby="confirm-dialog-message"
			className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
			onClick={(e) => {
				if (e.target === e.currentTarget) onCancel();
			}}
			onKeyDown={handleKeyDown}
		>
			<div
				ref={dialogRef}
				className="bg-card rounded-lg p-6 max-w-md w-full mx-4 shadow-xl"
			>
				<h2
					id="confirm-dialog-title"
					className="text-lg font-semibold mb-2 text-white"
				>
					{title}
				</h2>
				<p id="confirm-dialog-message" className="text-foreground/90 mb-6">
					{message}
				</p>
				<div className="flex justify-end gap-3">
					<button
						ref={cancelButtonRef}
						onClick={onCancel}
						className="px-4 py-2 text-foreground bg-secondary rounded hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-slate-500"
					>
						{cancelLabel}
					</button>
					<button
						onClick={onConfirm}
						className={`px-4 py-2 text-white rounded focus:outline-none focus:ring-2 focus:ring-offset-2 ${variantClasses[variant]}`}
					>
						{confirmLabel}
					</button>
				</div>
			</div>
		</div>
	);
}
