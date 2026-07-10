import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
	({ className, type, ...props }, ref) => {
		return (
			<input
				type={type}
				className={cn(
					"flex h-11 w-full rounded-lg border border-white/10 bg-white/5 backdrop-blur-[20px] px-4 py-1 text-[14px] transition-all duration-200 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:border-cyan-400/50 focus-visible:ring-1 focus-visible:ring-cyan-400/30 disabled:cursor-not-allowed disabled:opacity-50 hover:border-white/20",
					className,
				)}
				ref={ref}
				{...props}
			/>
		);
	},
);
Input.displayName = "Input";

export { Input };
