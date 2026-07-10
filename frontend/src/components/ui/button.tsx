import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-[14px] font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 hover:scale-[1.02]",
        {
                variants: {
                        variant: {
                                default:
                                        "bg-cyan-400/90 text-cyan-950 hover:bg-cyan-400 shadow-md shadow-cyan-500/15",
                                destructive:
                                        "bg-slate-700 text-slate-100 hover:bg-slate-600 border border-slate-600",
                                outline:
                                        "border border-cyan-400/30 bg-transparent text-cyan-300 hover:bg-cyan-400/10 hover:border-cyan-400/50",
                                secondary:
                                        "bg-white/5 text-foreground border border-white/10 hover:bg-white/10 backdrop-blur-[20px]",
                                ghost: "bg-transparent text-foreground hover:bg-white/5",
                                link: "text-cyan-300 underline-offset-4 hover:underline",
                        },
                        size: {
                                default: "h-11 px-5 py-2",
                                sm: "h-9 rounded-md px-3 text-[13px]",
                                lg: "h-12 rounded-lg px-8 text-[15px]",
                                icon: "h-11 w-11 p-0",
                        },
                },
                defaultVariants: {
                        variant: "default",
                        size: "default",
                },
        },
);

export interface ButtonProps
        extends React.ButtonHTMLAttributes<HTMLButtonElement>,
                VariantProps<typeof buttonVariants> {
        asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
        ({ className, variant, size, asChild = false, ...props }, ref) => {
                const Comp = asChild ? Slot : "button";
                return (
                        <Comp
                                className={cn(buttonVariants({ variant, size, className }))}
                                ref={ref}
                                {...props}
                        />
                );
        },
);
Button.displayName = "Button";

export { Button, buttonVariants };
