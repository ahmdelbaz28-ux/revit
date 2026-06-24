import { HelpCircle as CircleHelp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useSmartHelp } from '@/hooks/useSmartHelp';
import type { ContextHelpButtonProps } from '@/help/types';

export function ContextHelpButton({
  contextId,
  size = 'icon',
  className = '',
  variant = 'ghost',
}: ContextHelpButtonProps) {
  const { openHelp } = useSmartHelp();
  const label = 'Open help';

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      className={className}
      title={label}
      aria-label={label}
      onClick={() => openHelp(contextId)}
    >
      <CircleHelp className="h-4 w-4" />
    </Button>
  );
}
