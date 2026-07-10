/**
 * ComplianceBadge.tsx — NFPA 72 compliance status indicator.
 *
 * Engineering convention: color + icon + text (never color alone).
 * Colors follow IEC 60204-1 / NFPA 79 safety-critical HMI standard.
 * Never animated — compliance status is static, not a live alarm.
 */
import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, CheckCircle2, MinusCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const complianceVariants = cva(
	"inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 " +
		"text-[10px] font-mono font-semibold uppercase tracking-wider [&_svg]:size-3",
	{
		variants: {
			status: {
				pass: "bg-success/10 text-success border-success/30",
				warn: "bg-warning/10 text-warning border-warning/30",
				fail: "bg-danger/10 text-danger border-danger/30",
				na: "bg-muted text-muted-foreground border-border",
			},
		},
		defaultVariants: { status: "na" },
	},
);

const ICONS = {
	pass: CheckCircle2,
	warn: AlertTriangle,
	fail: XCircle,
	na: MinusCircle,
} as const;

const LABELS = {
	pass: "PASS",
	warn: "WARN",
	fail: "FAIL",
	na: "N/A",
} as const;

interface ComplianceBadgeProps
	extends React.HTMLAttributes<HTMLSpanElement>,
		VariantProps<typeof complianceVariants> {
	readonly status: keyof typeof ICONS;
	readonly label?: string;
	readonly nfpaSection?: string;
}

export function ComplianceBadge({
	status,
	label,
	nfpaSection,
	className,
	...props
}: ComplianceBadgeProps) {
	const Icon = ICONS[status];
	return (
		<span
			className={cn(complianceVariants({ status }), className)}
			{...props}
		>
			<Icon />
			<span>{label ?? LABELS[status]}</span>
			{nfpaSection && (
				<span className="text-muted-foreground font-normal normal-case">
					· NFPA 72 §{nfpaSection}
				</span>
			)}
		</span>
	);
}
