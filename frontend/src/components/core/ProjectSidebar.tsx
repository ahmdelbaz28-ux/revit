import React from 'react';
import { useStore, actions, Device } from '@/store/simpleStore';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { Box, Trash2 } from 'lucide-react';

export function ProjectSidebar() {
  const devices = useStore((s) => s.devices);
  const selectedElementId = useStore((s) => s.selectedElementId);

  const handleDelete = (id: string) => {
    actions.deleteDevice(id);
    if (selectedElementId === id) {
      actions.selectElement(null);
    }
  };

  return (
    <div className="w-60 flex flex-col border-r bg-card/30 h-full overflow-hidden">
      <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b bg-card/50">
        Project Elements (Dynamic Tree)
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 text-sm space-y-1">
          {devices.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-4">
              No elements.
            </div>
          ) : (
            devices.map((el) => (
              <div 
                key={el.id}
                className={`flex items-center justify-between py-1 px-2 rounded cursor-pointer group ${selectedElementId === el.id ? 'bg-primary/10 text-primary' : 'hover:bg-muted/50 text-muted-foreground'}`}
                onClick={() => actions.selectElement(el.id)}
              >
                <div className="flex items-center gap-2 truncate">
                  <Box className="h-3.5 w-3.5 text-blue-400" />
                  <span className="text-xs truncate">{el.id}</span>
                </div>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  className="h-5 w-5 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-500 transition-opacity"
                  onClick={(e) => { e.stopPropagation(); handleDelete(el.id); }}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
