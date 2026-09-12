import * as React from "react";

import { cn } from "@/lib/cn";

/**
 * theme.card(): a flat white surface with a hairline border and no drop
 * shadow. Keep it shadowless — that is the house style, not an oversight.
 */
const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("rounded-card border border-border bg-card p-5", className)}
    {...props}
  />
));
Card.displayName = "Card";

const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3 ref={ref} className={cn("text-lg font-bold", className)} {...props} />
));
CardTitle.displayName = "CardTitle";

export { Card, CardTitle };
