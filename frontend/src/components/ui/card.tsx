import * as React from "react";

import { cn } from "@/lib/utils";

const Card = React.forwardRef<
        HTMLDivElement,
        React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
        <div
                ref={ref}
                className={cn(
                        "rounded-xl border border-white/10 bg-[rgba(17,24,39,0.6)] backdrop-blur-[20px] text-card-foreground transition-all duration-200",
                        className,
                )}
                {...props}
        />
));
Card.displayName = "Card";

const CardHeader = React.forwardRef<
        HTMLDivElement,
        React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
        <div
                ref={ref}
                className={cn("flex flex-col space-y-2 p-6", className)}
                {...props}
        />
));
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<
        HTMLDivElement,
        React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
        <div
                ref={ref}
                className={cn(
                        "text-[18px] font-semibold leading-snug tracking-tight text-foreground",
                        className,
                )}
                {...props}
        />
));
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<
        HTMLDivElement,
        React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
        <div
                ref={ref}
                className={cn("text-[14px] text-muted-foreground leading-relaxed", className)}
                {...props}
        />
));
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<
        HTMLDivElement,
        React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
        <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
));
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<
        HTMLDivElement,
        React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
        <div
                ref={ref}
                className={cn("flex items-center p-6 pt-0", className)}
                {...props}
        />
));
CardFooter.displayName = "CardFooter";

export {
        Card,
        CardContent,
        CardDescription,
        CardFooter,
        CardHeader,
        CardTitle,
};
