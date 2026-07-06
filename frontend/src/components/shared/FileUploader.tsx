/**
 * FileUploader.tsx — Drag & Drop file uploader for DWG/RVT files
 */

import { FileText, Upload, X } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

interface FileUploaderProps {
	accept?: string; // e.g. '.dwg,.dxf' or '.rvt'
	label?: string;
	onUpload: (file: File) => Promise<void>;
	maxSize?: number; // MB
}

export function FileUploader({
	accept = ".dwg,.dxf,.rvt",
	label = "Upload File",
	onUpload,
	maxSize = 100,
}: FileUploaderProps) {
	const [dragging, setDragging] = useState(false);
	const [uploading, setUploading] = useState(false);
	const [selectedFile, setSelectedFile] = useState<File | null>(null);
	const inputRef = useRef<HTMLInputElement>(null);

	const handleDrop = useCallback(
		(e: React.DragEvent) => {
			e.preventDefault();
			setDragging(false);
			const file = e.dataTransfer.files[0];
			if (file) {
				const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
				if (!accept.includes(ext)) {
					toast.error(`Invalid file type. Accepted: ${accept}`);
					return;
				}
				if (file.size > maxSize * 1024 * 1024) {
					toast.error(`File too large. Max ${maxSize}MB.`);
					return;
				}
				setSelectedFile(file);
			}
		},
		[accept, maxSize],
	);

	const handleUpload = async () => {
		if (!selectedFile) return;
		setUploading(true);
		try {
			await onUpload(selectedFile);
			toast.success(`${selectedFile.name} uploaded successfully`);
			setSelectedFile(null);
		} catch (err) {
			toast.error(
				`Upload failed: ${err instanceof Error ? err.message : "Unknown error"}`,
			);
		} finally {
			setUploading(false);
		}
	};

	return (
		<div className="space-y-3">
			<label className="text-sm font-medium text-slate-300">{label}</label>
			<div
				className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer ${
					dragging
						? "border-orange-500 bg-orange-500/10"
						: "border-slate-600 hover:border-slate-500 bg-slate-800/50"
				}`}
				onDragOver={(e) => {
					e.preventDefault();
					setDragging(true);
				}}
				onDragLeave={() => setDragging(false)}
				onDrop={handleDrop}
				onClick={{() => inputRef.current?.click() onKeyDown={(e) => e.key === "Enter" && {() => inputRef.current?.click()}			>
				<input
					ref={inputRef}
					type="file"
					accept={accept}
					className="hidden"
					onChange={(e) => {
						const file = e.target.files?.[0];
						if (file) setSelectedFile(file);
					}}
				/>
				<Upload className="h-10 w-10 text-slate-500 mx-auto mb-3" />
				<p className="text-sm text-slate-400">
					{dragging ? "Drop file here" : "Drag & drop or click to browse"}
				</p>
				<p className="text-xs text-slate-500 mt-1">
					Accepted: {accept} (max {maxSize}MB)
				</p>
			</div>
			{selectedFile && (
				<div className="flex items-center gap-3 p-3 bg-slate-800 rounded-lg border border-slate-700">
					<FileText className="h-5 w-5 text-orange-400 shrink-0" />
					<div className="flex-1 min-w-0">
						<p className="text-sm text-slate-200 truncate">
							{selectedFile.name}
						</p>
						<p className="text-xs text-slate-500">
							{(selectedFile.size / 1024).toFixed(1)} KB
						</p>
					</div>
					<Button
						size="sm"
						onClick={{handleUpload onKeyDown={(e) => e.key === "Enter" && {handleUpload}						disabled={uploading}
						className="bg-orange-600 hover:bg-orange-700 text-white"
					>
						{uploading ? "Uploading..." : "Upload"}
					</Button>
					<Button
						size="sm"
						variant="ghost"
						onClick={{() => setSelectedFile(null) onKeyDown={(e) => e.key === "Enter" && {() => setSelectedFile(null)}						disabled={uploading}
					>
						<X className="h-4 w-4" />
					</Button>
				</div>
			)}
		</div>
	);
}
